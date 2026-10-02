#!/usr/bin/env python3
"""GraphMixer-style candidate scorer for EX-Graph next-counterparty retrieval.

Design notes (leakage protocol):
- Train on train_expanded + frozen train cases only.  Frozen dev is used only
  for validation; frozen holdout (2022-08-01) is never touched.
- All features are computed from outgoing events with block_timestamp < cutoff.
- Ranking loss is masked when the target is open_world (not visible pre-cutoff).
- OPEN_WORLD is a separate calibrated head; it never counts as an address hit.
- Candidate pool per case is a retrieve-then-rerank union of heuristic pools;
  pool support is reported so model recall is not confused with pool ceiling.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys, time, traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_openworld_diffusion_baseline as base  # noqa: E402

ROOT = base.ROOT
ADDR_BUCKETS = 32768
TOK_BUCKETS = 4096
FAM_VOCAB = {'': 0, 'external_tx': 1, 'internal_trace': 2, 'token_transfer': 3}
SEQ_LEN = 64
POOL_OWN = 500
POOL_GLOBAL = 2000
POOL_RECENT = 2000
POOL_DIFF = 500


def h_bucket(addr: str, buckets: int) -> int:
    return int(hashlib.sha1(addr.encode()).hexdigest(), 16) % buckets


def build_wallet_sequences(hist: pd.DataFrame, cutoff: str) -> Dict[str, list]:
    """Last-SEQ_LEN outgoing events per wallet, with per-event scalar features."""
    t = pd.Timestamp(cutoff, tz='UTC')
    seqs: Dict[str, list] = {}
    gcount = hist.counterparty_address.value_counts()
    own_counter = defaultdict(Counter)
    rows = []
    # single chronological pass; keep deque-like tail per wallet
    for r in hist.itertuples(index=False):
        w, c = r.target_address, r.counterparty_address
        if not w or not c:
            continue
        own_counter[w][c] += 1
        age = max(0.0, (t - pd.Timestamp(r.block_timestamp)).total_seconds() / 86400.0)
        rows.append((w, c, getattr(r, 'event_family', '') or '',
                     getattr(r, 'token_contract_address', '') or '', age))
    # own counts are now final; build sequences from the tail
    tail: Dict[str, list] = defaultdict(list)
    for w, c, fam, tok, age in rows:
        lst = tail[w]
        lst.append((c, fam, tok, age))
        if len(lst) > SEQ_LEN:
            lst.pop(0)
    for w, lst in tail.items():
        feats = []
        for c, fam, tok, age in lst:
            feats.append((
                h_bucket(c, ADDR_BUCKETS), FAM_VOCAB.get(fam, 0), h_bucket(tok, TOK_BUCKETS),
                int(round(math.log1p(age) * 100)), int(round(math.log1p(own_counter[w][c]) * 100)),
                int(round(math.log1p(int(gcount.get(c, 0))) * 100)),
            ))
        seqs[w] = feats
    return seqs


def case_pool(index: dict, wallet: str, cutoff: str) -> List[str]:
    """Retrieve-then-rerank pool: own history + diffusion + popularity tails."""
    own_freq = index['by_wallet_counter'].get(wallet, Counter())
    own_last = index['by_wallet_last'].get(wallet, {})
    own = list(dict.fromkeys(
        [c for c, _ in sorted(own_last.items(), key=lambda kv: (-kv[1], kv[0]))[:POOL_OWN]]
        + [c for c, _ in sorted(own_freq.items(), key=lambda kv: (-kv[1], kv[0]))[:POOL_OWN]]))
    # typed diffusion shortlist (reuse base.rank_for_wallet on the pure method)
    diff_list, _ = base.rank_for_wallet(index, wallet, 'typed_temporal_diffusion', max_candidates=POOL_DIFF)
    pool = list(dict.fromkeys(own + diff_list
                              + index['recent_rank'][:POOL_RECENT]
                              + index['global_rank'][:POOL_GLOBAL]))
    return pool


def candidate_features(index: dict, wallet: str, cand: str, cutoff: str) -> List[float]:
    t = pd.Timestamp(cutoff, tz='UTC')
    own_c = index['by_wallet_counter'].get(wallet, Counter())
    own_l = index['by_wallet_last'].get(wallet, {})
    g = index['global_counter'].get(cand, 0)
    r = index['recent_counter'].get(cand, 0)
    oc = own_c.get(cand, 0)
    # days since last interaction: invert decay weight approximately
    dl = own_l.get(cand, 0.0)
    days_since = -90.0 * math.log(max(dl, 1e-9)) if dl > 0 else 365.0
    days_since = min(days_since, 365.0)
    return [math.log1p(g), math.log1p(r), math.log1p(oc), math.log1p(days_since),
            1.0 if oc > 0 else 0.0]


def extract_dataset(ev: pd.DataFrame, cases: pd.DataFrame, cache: Path) -> Path:
    """Extract per-case sequences, pools, and labels into an .npz cache."""
    per_case = []
    for cutoff, g in cases.groupby('cutoff', sort=True):
        t0 = time.time()
        hist = ev[ev.block_timestamp < pd.Timestamp(cutoff, tz='UTC')]
        index = base.build_temporal_index(hist, cutoff)
        seqs = build_wallet_sequences(hist, cutoff)
        print(json.dumps({'extract_cutoff': cutoff, 'cases': int(len(g)),
                          'seconds': round(time.time() - t0, 1)}), flush=True)
        for r in g.itertuples(index=False):
            if r.split == 'train_expanded' and r.cutoff >= '2022-07-01':
                continue
            pool = case_pool(index, r.wallet, cutoff)
            cand_feats = np.array([candidate_features(index, r.wallet, c, cutoff) for c in pool],
                                  dtype=np.float32) if pool else np.zeros((0, 5), dtype=np.float32)
            cand_bucket = np.array([h_bucket(c, ADDR_BUCKETS) for c in pool], dtype=np.int32)
            seq = seqs.get(r.wallet, [])
            s = np.zeros((SEQ_LEN, 6), dtype=np.int64)
            if seq:
                arr = np.array(seq, dtype=np.int64)
                s[SEQ_LEN - len(arr):] = arr
            y = r.target if r.active else ''
            y_idx = pool.index(y) if (y and y in pool) else -1
            vis = 'none'
            if y:
                own_seen = y in index['by_wallet_counter'].get(r.wallet, Counter())
                glob_seen = (y in index['global_counter'])
                vis = 'own_seen' if own_seen else ('global_seen' if glob_seen else 'open_world')
            per_case.append({
                'case_id': r.case_id, 'split': r.split, 'cutoff': r.cutoff, 'wallet': r.wallet,
                'active': int(r.active), 'target': y, 'visibility': vis,
                'seq': s, 'cand_bucket': cand_bucket, 'cand_feats': cand_feats,
                'y_idx': y_idx, 'pool': pool,
            })
    cache.parent.mkdir(parents=True, exist_ok=True)
    import pickle
    with cache.open('wb') as f:
        pickle.dump(per_case, f, protocol=4)
    return per_case


# ---------------- model ----------------
import torch
import torch.nn as nn
import torch.nn.functional as F


class MixerBlock(nn.Module):
    def __init__(self, seq_len: int, dim: int, dropout: float = 0.1):
        super().__init__()
        self.ln1 = nn.LayerNorm(dim)
        self.token_mlp = nn.Sequential(nn.Linear(seq_len, seq_len), nn.GELU(), nn.Dropout(dropout))
        self.ln2 = nn.LayerNorm(dim)
        self.chan_mlp = nn.Sequential(nn.Linear(dim, dim * 2), nn.GELU(), nn.Dropout(dropout), nn.Linear(dim * 2, dim))

    def forward(self, x, mask):
        # x: (B, S, D); mask: (B, S) 1=valid
        y = self.ln1(x).transpose(1, 2)          # (B, D, S)
        y = self.token_mlp(y).transpose(1, 2)     # (B, S, D)
        y = y * mask.unsqueeze(-1)
        x = x + y
        x = x + self.chan_mlp(self.ln2(x)) * mask.unsqueeze(-1)
        return x


class GraphMixerScorer(nn.Module):
    def __init__(self, dim: int = 128, seq_len: int = SEQ_LEN, n_blocks: int = 2):
        super().__init__()
        self.addr_emb = nn.Embedding(ADDR_BUCKETS, 48)
        self.fam_emb = nn.Embedding(len(FAM_VOCAB), 8)
        self.tok_emb = nn.Embedding(TOK_BUCKETS, 16)
        self.ev_proj = nn.Linear(48 + 8 + 16 + 3, dim)
        self.blocks = nn.ModuleList([MixerBlock(seq_len, dim) for _ in range(n_blocks)])
        self.out_ln = nn.LayerNorm(dim)
        self.cand_addr_emb = nn.Embedding(ADDR_BUCKETS, 48)
        self.cand_mlp = nn.Sequential(nn.Linear(48 + 5, dim), nn.GELU(), nn.Linear(dim, dim))
        self.score_head = nn.Sequential(nn.Linear(dim * 3, dim), nn.GELU(), nn.Linear(dim, 1))
        self.act_head = nn.Linear(dim, 1)
        self.ow_head = nn.Linear(dim, 1)

    def encode_wallet(self, seq):
        # seq: (B, S, 6) int64: bucket, fam, tok, log-age(scaled x100), log-own(x100), log-global(x100)
        b = seq[:, :, 0]
        fam = seq[:, :, 1].clamp(0, len(FAM_VOCAB) - 1)
        tok = seq[:, :, 2]
        scal = seq[:, :, 3:].float() / 100.0
        mask = fam > 0  # padding rows have fam==0; real events always have fam>=1
        e = torch.cat([self.addr_emb(b), self.fam_emb(fam), self.tok_emb(tok), scal], dim=-1)
        x = self.ev_proj(e) * mask.unsqueeze(-1)
        for blk in self.blocks:
            x = blk(x, mask)
        denom = mask.sum(dim=1, keepdim=True).clamp(min=1)
        h = (x * mask.unsqueeze(-1)).sum(dim=1) / denom
        return self.out_ln(h)

    def score_candidates(self, h, cand_bucket, cand_feats):
        # h: (B, D); cand_bucket: (B, C); cand_feats: (B, C, 5)
        B, C = cand_bucket.shape
        hc = self.cand_mlp(torch.cat([self.cand_addr_emb(cand_bucket), cand_feats], dim=-1))  # (B,C,D)
        hw = h.unsqueeze(1).expand(-1, C, -1)
        z = torch.cat([hw, hc, hw * hc], dim=-1)
        return self.score_head(z).squeeze(-1)  # (B, C)


def batch_iter(cases: List[dict], bs: int, shuffle: bool, rng: np.random.Generator):
    idx = np.arange(len(cases))
    if shuffle:
        rng.shuffle(idx)
    for i in range(0, len(idx), bs):
        yield [cases[j] for j in idx[i:i + bs]]


NEG_PER_CASE = 32


def collate(batch: List[dict], rng: np.random.Generator, train: bool):
    seqs = torch.from_numpy(np.stack([c['seq'] for c in batch]))  # scalar slots pre-scaled x100
    max_c = max(len(c['pool']) for c in batch)
    cb = torch.zeros(len(batch), max_c, dtype=torch.long)
    cf = torch.zeros(len(batch), max_c, 5, dtype=torch.float)
    cmask = torch.zeros(len(batch), max_c, dtype=torch.bool)
    ypos = torch.full((len(batch),), -1, dtype=torch.long)
    act = torch.tensor([c['active'] for c in batch], dtype=torch.float)
    ow = torch.tensor([1.0 if c['visibility'] == 'open_world' else 0.0 for c in batch], dtype=torch.float)
    has_target = torch.zeros(len(batch), dtype=torch.bool)
    for i, c in enumerate(batch):
        n = len(c['pool'])
        if n:
            cb[i, :n] = torch.from_numpy(c['cand_bucket'].astype(np.int64))
            cf[i, :n] = torch.from_numpy(c['cand_feats'])
            cmask[i, :n] = True
        if c['y_idx'] >= 0:
            ypos[i] = c['y_idx']
            has_target[i] = True
    return seqs, cb, cf, cmask, ypos, act, ow, has_target


def train_model(per_case: List[dict], out: Path, epochs: int, bs: int, lr: float, seed: int,
                device: str) -> dict:
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    train_cases = [c for c in per_case if c['split'] in ('train', 'train_expanded')]
    dev_cases = [c for c in per_case if c['split'] == 'dev']
    model = GraphMixerScorer().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    hist_log = []
    for ep in range(epochs):
        model.train()
        tot = {'loss': 0.0, 'rank': 0.0, 'act': 0.0, 'ow': 0.0, 'n': 0}
        for batch in batch_iter(train_cases, bs, True, rng):
            seqs, cb, cf, cmask, ypos, act, ow, has_target = [x.to(device) if torch.is_tensor(x) else x for x in collate(batch, rng, True)]
            h = model.encode_wallet(seqs)
            logits = model.score_candidates(h, cb, cf)
            logits = logits.masked_fill(~cmask, -1e9)
            loss_rank = torch.tensor(0.0, device=device)
            if has_target.any():
                lt = logits[has_target]
                yt = ypos[has_target]
                loss_rank = F.cross_entropy(lt, yt)
            loss_act = F.binary_cross_entropy_with_logits(model.act_head(h).squeeze(-1), act)
            ow_mask = act.bool()
            loss_ow = torch.tensor(0.0, device=device)
            if ow_mask.any():
                loss_ow = F.binary_cross_entropy_with_logits(model.ow_head(h).squeeze(-1)[ow_mask], ow[ow_mask])
            loss = loss_rank + 0.5 * loss_act + 0.5 * loss_ow
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            n = len(batch)
            tot['loss'] += loss.item() * n
            tot['rank'] += loss_rank.item() * n
            tot['act'] += loss_act.item() * n
            tot['ow'] += loss_ow.item() * n
            tot['n'] += n
        metrics = evaluate(model, dev_cases, device)
        hist_log.append({'epoch': ep, **{k: round(v / max(1, tot['n']), 4) for k, v in tot.items() if k != 'n'},
                         **{f'dev_{k}': v for k, v in metrics.items()}})
        print(json.dumps(hist_log[-1]), flush=True)
    return {'model': model, 'log': hist_log, 'dev_cases': dev_cases, 'train_cases': train_cases}


@torch.no_grad()
def evaluate(model: nn.Module, dev_cases: List[dict], device: str) -> dict:
    model.eval()
    hits = {1: 0, 5: 0, 50: 0, 100: 0}
    n_active = 0
    n_support = 0
    act_scores, act_labels, ow_scores, ow_labels = [], [], [], []
    rng = np.random.default_rng(0)
    for batch in batch_iter(dev_cases, 64, False, rng):
        seqs, cb, cf, cmask, ypos, act, ow, has_target = [x.to(device) if torch.is_tensor(x) else x for x in collate(batch, rng, False)]
        h = model.encode_wallet(seqs)
        logits = model.score_candidates(h, cb, cf).masked_fill(~cmask, -1e9)
        act_scores += model.act_head(h).squeeze(-1).tolist()
        act_labels += act.tolist()
        ow_scores += model.ow_head(h).squeeze(-1).tolist()
        ow_labels += ow.tolist()
        order = torch.argsort(logits, dim=1, descending=True)
        for i in range(len(batch)):
            if not has_target[i]:
                continue
            n_active += 1
            n_support += 1  # has_target implies target in pool
            rank = (order[i] == ypos[i]).nonzero()
            if len(rank):
                r = int(rank[0].item()) + 1
                for k in hits:
                    if r <= k:
                        hits[k] += 1
    # recall denominators must include active cases whose target is outside pool;
    # those never enter has_target, so compute support separately at summary time.
    def auroc(s, l):
        try:
            from sklearn.metrics import roc_auc_score
            return float(roc_auc_score(l, s)) if len(set(l)) > 1 else None
        except Exception:
            return None
    res = {f'recall_at_{k}': hits[k] for k in hits}
    res['active_with_target_in_pool'] = n_active
    res['act_auroc'] = auroc(act_scores, act_labels)
    ow_pairs = [(s, l) for s, l, a in zip(ow_scores, ow_labels, act_labels) if a > 0.5]
    res['ow_auroc_active_only'] = auroc([p[0] for p in ow_pairs], [p[1] for p in ow_pairs]) if ow_pairs else None
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases-csv', type=Path, required=True,
                    help='cases_train_dev_with_expansion.csv from the full baseline run')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--epochs', type=int, default=6)
    ap.add_argument('--bs', type=int, default=32)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--device', type=str, default='cuda:0')
    ap.add_argument('--feature-cache', type=Path, default=None)
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()

    cache = args.feature_cache or (out / 'feature_cache.pkl')
    if cache.exists():
        import pickle
        per_case = pickle.load(cache.open('rb'))
        print(json.dumps({'feature_cache_loaded': str(cache), 'cases': len(per_case)}), flush=True)
    else:
        ev = base.load_events()
        cases = pd.read_csv(args.cases_csv, dtype={'wallet': str, 'target': str})
        cases['wallet'] = cases.wallet.str.lower()
        cases['target'] = cases.target.fillna('').astype(str).str.lower()
        per_case = extract_dataset(ev, cases, cache)
        print(json.dumps({'feature_cache_written': str(cache), 'cases': len(per_case)}), flush=True)

    # Support ceiling on dev: active cases whose target is inside the rerank pool.
    dev = [c for c in per_case if c['split'] == 'dev']
    dev_active = [c for c in dev if c['active'] == 1]
    pool_support = sum(1 for c in dev_active if c['y_idx'] >= 0)
    ow = sum(1 for c in dev_active if c['visibility'] == 'open_world')

    result = train_model(per_case, out, args.epochs, args.bs, args.lr, args.seed, args.device)
    model = result['model']
    torch.save({'state_dict': model.state_dict(),
                'config': {'dim': 128, 'seq_len': SEQ_LEN, 'addr_buckets': ADDR_BUCKETS}},
               out / 'graphmixer_v1.pt')

    # final dev recall with correct active-case denominators
    final = evaluate(model, result['dev_cases'], args.device)
    summary = {
        'run': out.name,
        'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'status': 'complete_train_dev_only_holdout_locked',
        'cases_csv': str(args.cases_csv),
        'cases_csv_sha256': base.sha256(args.cases_csv),
        'train_cases': len(result['train_cases']),
        'dev_cases': len(result['dev_cases']),
        'dev_active': len(dev_active),
        'dev_pool_support_active': pool_support,
        'dev_pool_support_rate': pool_support / max(1, len(dev_active)),
        'dev_open_world_active': ow,
        'dev_open_world_rate': ow / max(1, len(dev_active)),
        'dev_recall_hits_among_pool_supported': final,
        'dev_recall_at_50_all_active': final['recall_at_50'] / max(1, len(dev_active)),
        'dev_recall_at_100_all_active': final['recall_at_100'] / max(1, len(dev_active)),
        'hyperparams': {'epochs': args.epochs, 'bs': args.bs, 'lr': args.lr, 'seed': args.seed,
                        'pool': {'own': POOL_OWN, 'global': POOL_GLOBAL, 'recent': POOL_RECENT, 'diff': POOL_DIFF},
                        'negatives': 'in-pool InfoNCE over retrieved candidates',
                        'loss': 'rank(InfoNCE) + 0.5*activity(BCE) + 0.5*open_world(BCE)'},
        'leakage': {'all_features_pre_cutoff': True, 'holdout_labels_materialized': False,
                    'ranking_loss_masked_for_open_world_targets': True},
        'model_note': 'GraphMixer-style MLP-mixer over last-64 event sequence; hash embeddings; not the official GraphMixer codebase',
        'train_log': result['log'],
        'finished_seconds': time.time() - t0,
    }
    (out / 'graphmixer_summary.json').write_text(json.dumps(summary, indent=2, default=str) + '\n')
    print(json.dumps({'status': summary['status'], 'out': str(out),
                      'seconds': summary['finished_seconds']}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
