#!/usr/bin/env python3
"""TGB tgbl-coin-v2 improved MLP edge-scoring (torch-only, no PyG/dgl).

Leak-free prefix features (see tgb_features.py, 23 dims), strictly from
observations with timestamp < t. Training negatives match the official
hist_rnd protocol: per source, 1 historical dst (distinct train dsts of the
source) + 1 uniform random dst, per positive.

Evaluation uses the official NegativeEdgeSampler (20 fixed negatives/positive),
official Evaluator (one-vs-many MRR), official splits, no backprop, streaming
state (all edges with t' < t via prefix structures, which is equivalent).

Run: .venv-cuda/bin/python tgb_mlp2.py --eval-split val --tag v1 --device cuda:5
"""
import os, os.path as osp, json, math, time, argparse
import numpy as np
import torch
import torch.nn as nn
from tgb.linkproppred.dataset import LinkPropPredDataset
from tgb.linkproppred.evaluate import Evaluator
from tgb.utils.utils import set_random_seed
from tgb_features import PrefixGraphFeatures, FEATURE_NAMES

OUT_DIR = osp.dirname(osp.abspath(__file__))
SEED = 1


class MLP(nn.Module):
    def __init__(self, in_dim=23, hidden=512, dropout=0.1, layers=2):
        super().__init__()
        blocks = [nn.Linear(in_dim, hidden), nn.ReLU(), nn.Dropout(dropout)]
        for _ in range(layers - 1):
            blocks += [nn.Linear(hidden, hidden), nn.ReLU(), nn.Dropout(dropout)]
        blocks += [nn.Linear(hidden, 1)]
        self.net = nn.Sequential(*blocks)

    def forward(self, x):
        return self.net(x).squeeze(-1)


def build_hist_dst_by_src(s, d, tr_idx, N):
    """distinct train dsts per source (matches official hist_rnd source history)."""
    codes = s[tr_idx] * N + d[tr_idx]
    uniq = np.unique(codes)
    srcs = uniq // N
    dsts = uniq % N
    order = np.argsort(srcs, kind="stable")
    srcs = srcs[order]; dsts = dsts[order]
    out = {}
    # group boundaries
    bounds = np.where(np.diff(srcs) != 0)[0] + 1
    bounds = np.concatenate([[0], bounds, [len(srcs)]])
    for i in range(len(bounds) - 1):
        s0 = int(srcs[bounds[i]])
        out[s0] = dsts[bounds[i]:bounds[i + 1]]
    return out


def build_train_data(feat, s, d, t, tr_idx, sample_n, hist_map, rng,
                     neg_hist=1, neg_rnd=1, chunk=1_000_000):
    idx = tr_idx[np.argsort(t[tr_idx], kind="mergesort")]
    n = len(idx)
    if sample_n and sample_n < n:
        sel = rng.choice(n, sample_n, replace=False)
        sel.sort()
        idx = idx[sel]
    n = len(idx)
    su = s[idx].astype(np.int64); dv = d[idx].astype(np.int64); tt = t[idx].astype(np.int64)
    N = feat.N
    srcs = su.tolist(); dsts = dv.tolist()
    hist_nd = np.full(n, -1, dtype=np.int64)
    rnd_nd = np.empty(n, dtype=np.int64)
    t0 = time.time()
    for j in range(n):
        s0 = srcs[j]; d0 = dsts[j]
        arr = hist_map.get(s0)
        nd = -1
        if arr is not None and len(arr):
            if len(arr) > 1:
                k = rng.randint(len(arr)); nd = int(arr[k]); tries = 0
                while nd == d0 and tries < 12:
                    k = rng.randint(len(arr)); nd = int(arr[k]); tries += 1
                if nd == d0:
                    alt = arr[arr != d0]
                    nd = int(alt[rng.randint(len(alt))]) if len(alt) else -1
            else:
                nd = int(arr[0]) if int(arr[0]) != d0 else -1
        hist_nd[j] = nd
        ndr = int(rng.randint(N)); tries = 0
        while (ndr == d0 or ndr == nd) and tries < 25:
            ndr = int(rng.randint(N)); tries += 1
        rnd_nd[j] = ndr
    print(f"[{time.time()-t0:.1f}s] negatives sampled", flush=True)
    # fallback: hist unavailable -> use rnd
    bad = hist_nd < 0
    hist_nd[bad] = rnd_nd[bad]
    n_neg = n * (neg_hist + neg_rnd)
    Xp = np.empty((n, 23), dtype=np.float32)
    Xn = np.empty((n_neg, 23), dtype=np.float32)
    pos = 0
    for p0 in range(0, n, chunk):
        p1 = min(p0 + chunk, n)
        Xp[p0:p1] = feat.features(su[p0:p1], dv[p0:p1], tt[p0:p1])
        pos += p1 - p0
        print(f"[{time.time()-t0:.1f}s] pos features {pos}/{n}", flush=True)
    off = 0
    for _ in range(neg_hist):
        for p0 in range(0, n, chunk):
            p1 = min(p0 + chunk, n)
            Xn[off:off + (p1 - p0)] = feat.features(su[p0:p1], hist_nd[p0:p1], tt[p0:p1])
            off += p1 - p0
    for _ in range(neg_rnd):
        for p0 in range(0, n, chunk):
            p1 = min(p0 + chunk, n)
            Xn[off:off + (p1 - p0)] = feat.features(su[p0:p1], rnd_nd[p0:p1], tt[p0:p1])
            off += p1 - p0
        print(f"[{time.time()-t0:.1f}s] neg features {off}/{n_neg}", flush=True)
    X = np.concatenate([Xp, Xn], axis=0)
    y = np.concatenate([np.ones(n, np.float32),
                        np.zeros(n_neg, np.float32)]).astype(np.float32)
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-subset", type=int, default=0, help="0 = all train positives")
    ap.add_argument("--neg-hist", type=int, default=1)
    ap.add_argument("--neg-rnd", type=int, default=1)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--hidden", type=int, default=512)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--batch", type=int, default=16384)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--eval-split", choices=["val", "test"], default="val")
    ap.add_argument("--device", default="cuda:5")
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--eval-batch", type=int, default=1000)
    ap.add_argument("--feat-cols", type=str, default="all",
                    help="comma-separated 0-based feature columns (or 'all')")
    ap.add_argument("--eval-only", action="store_true",
                    help="skip training; load {tag}.pt and {tag}_scaler.npz, run eval")
    args = ap.parse_args()

    t0 = time.time()
    set_random_seed(SEED); torch.manual_seed(SEED)
    rng = np.random.RandomState(SEED)
    dataset = LinkPropPredDataset(name="tgbl-coin", root="datasets", preprocess=True)
    data = dataset.full_data
    s = data["sources"].astype(np.int64); d = data["destinations"].astype(np.int64)
    t = data["timestamps"].astype(np.int64)
    metric = dataset.eval_metric
    tr, va, te = dataset.train_mask, dataset.val_mask, dataset.test_mask
    print(f"[{time.time()-t0:.1f}s] data loaded n_edges={len(s)}", flush=True)
    feat = PrefixGraphFeatures(s, d, t, tau_node=7 * 86400, tau_pair=86400)
    print(f"[{time.time()-t0:.1f}s] prefix structures built", flush=True)

    tr_idx = np.where(tr)[0]
    hist_map = build_hist_dst_by_src(s, d, tr_idx, feat.N)
    print(f"[{time.time()-t0:.1f}s] hist dst map: {len(hist_map)} sources", flush=True)

    cols = None if args.feat_cols == "all" else [int(c) for c in args.feat_cols.split(",")]
    if args.eval_only:
        scal = np.load(osp.join(OUT_DIR, f"tgb_mlp2_{args.tag}_scaler.npz"))
        mean, std = scal["mean"], scal["std"]
        in_dim = len(mean)
        model = MLP(in_dim=in_dim, hidden=args.hidden, dropout=args.dropout,
                    layers=args.layers).to(args.device)
        model.load_state_dict(torch.load(osp.join(OUT_DIR, f"tgb_mlp2_{args.tag}.pt"),
                                         map_location=args.device))
        print(f"[{time.time()-t0:.1f}s] eval-only: loaded {args.tag} model (in_dim={in_dim})", flush=True)
    else:
        X, y = build_train_data(feat, s, d, t, tr_idx, args.train_subset, hist_map, rng,
                                args.neg_hist, args.neg_rnd)
        print(f"[{time.time()-t0:.1f}s] train data X={X.shape} pos={int(y.sum())}", flush=True)
        if cols is not None:
            X = X[:, cols]
        mean = X.mean(0); std = X.std(0) + 1e-6
        X = (X - mean) / std
        np.savez(osp.join(OUT_DIR, f"tgb_mlp2_{args.tag}_scaler.npz"), mean=mean, std=std)

        Xt = torch.tensor(X); yt = torch.tensor(y)
        del X
        in_dim = Xt.shape[1]
        model = MLP(in_dim=in_dim, hidden=args.hidden, dropout=args.dropout,
                    layers=args.layers).to(args.device)
        opt = torch.optim.Adam(model.parameters(), lr=args.lr)
        lossf = nn.BCEWithLogitsLoss()
        n_batches = math.ceil(len(Xt) / args.batch)
        for ep in range(args.epochs):
            perm = torch.randperm(len(Xt))
            tot = 0.0
            for bi in range(n_batches):
                b = perm[bi * args.batch:(bi + 1) * args.batch]
                opt.zero_grad()
                loss = lossf(model(Xt[b].to(args.device)), yt[b].to(args.device))
                loss.backward(); opt.step()
                tot += loss.item()
            print(f"[{time.time()-t0:.1f}s] epoch {ep+1} loss={tot/n_batches:.4f}", flush=True)
        torch.save(model.state_dict(), osp.join(OUT_DIR, f"tgb_mlp2_{args.tag}.pt"))

    # ---------------- official evaluation ----------------
    evaluator = Evaluator(name="tgbl-coin")
    neg_sampler = dataset.negative_sampler
    eval_mask = va if args.eval_split == "val" else te
    idx = np.where(eval_mask)[0]
    order = np.argsort(t[idx], kind="mergesort")
    idx = idx[order]
    BATCH = args.eval_batch
    nb = math.ceil(len(idx) / BATCH)
    perf = []
    (dataset.load_val_ns() if args.eval_split == "val" else dataset.load_test_ns())
    model.eval()
    eb = time.time()
    for bi in range(nb):
        sl = idx[bi * BATCH:(bi + 1) * BATCH]
        pos_src, pos_dst, pos_t = s[sl], d[sl], t[sl]
        negs = neg_sampler.query_batch(pos_src, pos_dst, pos_t, split_mode=args.eval_split)
        total = sum(len(n) + 1 for n in negs)
        U = np.empty(total, dtype=np.int64)
        V = np.empty(total, dtype=np.int64)
        T = np.empty(total, dtype=np.int64)
        off = 0
        for j in range(len(sl)):
            k = len(negs[j]) + 1
            U[off:off + k] = pos_src[j]
            V[off] = pos_dst[j]
            V[off + 1:off + k] = np.asarray(negs[j], dtype=np.int64)
            T[off:off + k] = pos_t[j]
            off += k
        F = feat.features(U, V, T)
        if cols is not None:
            F = F[:, cols]
        F = (F - mean) / std
        with torch.no_grad():
            scores = torch.sigmoid(model(torch.tensor(F).to(args.device))).cpu().numpy()
        off = 0
        for j in range(len(sl)):
            k = len(negs[j]) + 1
            inp = {"y_pred_pos": scores[off:off + 1], "y_pred_neg": scores[off + 1:off + k],
                   "eval_metric": [metric]}
            perf.append(evaluator.eval(inp)[metric])
            off += k
        if bi % 500 == 0:
            print(f"[{time.time()-t0:.1f}s] {args.eval_split} batch {bi}/{nb} cur_mrr={np.mean(perf):.4f}", flush=True)
    print(f"[{time.time()-t0:.1f}s] eval done, eval_time={time.time()-eb:.1f}s", flush=True)

    res = {"model": "MLP-edge-scoring v2 (torch-only)", "data": "tgbl-coin-v2",
           "seed": SEED, "eval_split": args.eval_split, "mrr": float(np.mean(perf)),
           "train_subset": args.train_subset or int(tr.sum()), "neg_hist": args.neg_hist,
           "neg_rnd": args.neg_rnd, "epochs": args.epochs, "hidden": args.hidden,
           "layers": args.layers, "dropout": args.dropout, "lr": args.lr,
           "device": args.device, "tag": args.tag,
           "total_time_s": round(time.time() - t0, 2),
           "leaderboard_refs": {"TPNet": "0.832±0.001", "Heuristic": 0.774,
                                "HyperEvent": "0.773±0.002", "DyGFormer": "0.752±0.004",
                                "TGN": "0.586±0.037"},
           "features": FEATURE_NAMES}
    with open(osp.join(OUT_DIR, f"tgb_mlp2_{args.tag}_{args.eval_split}_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2), flush=True)


if __name__ == "__main__":
    main()
