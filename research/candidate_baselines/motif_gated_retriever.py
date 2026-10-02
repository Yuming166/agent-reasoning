#!/usr/bin/env python3
"""Typed Temporal Motif Retriever with learned source gating (EX-Graph).

Method: each (wallet, candidate) pair gets a feature vector decomposed into
auditable sources:
  s_direct    - direct dyadic history (counts, recency, bidirectionality,
                value fingerprint, failed-attempt intent)
  s_diffusion - typed temporal walk weight (wallet -> typed key -> peer -> c)
  s_motif     - typed path/motif structure (shared keys, co-counterparty
                overlap, path recency, temporal-order validity)
  s_global    - global dynamics (popularity, recency, burstiness, first-seen
                age, ecosystem membership)
  (s_tgn      - added in phase B by a separate module)

A wallet-conditioned gate alpha_w = softmax(MLP(wallet_context)) mixes the
per-case normalized source scores:
  s(w,c,t) = sum_i alpha_i * s_i(w,c,t)
so the top candidates carry an interpretable provenance label (argmax
contribution) that can feed natural-language hypothesis generation.

Leakage protocol: identical to run_openworld_diffusion_baseline.py.
All statistics use events with block_timestamp < cutoff; frozen holdout
(2022-08-01) labels are never read.  OPEN_WORLD targets mask the ranking loss.
"""
from __future__ import annotations
import argparse, hashlib, json, math, pickle, sys, time, traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_openworld_diffusion_baseline as base  # noqa: E402

ROOT = base.ROOT
SRC = base.SRC
TAU = 90.0
MAX_SEED_KEYS = 60
MAX_PEERS_PER_KEY = 25
MAX_RECIPS_PER_PEER = 40
MAX_OWN_FOR_OVERLAP = 50
POOL_OWN = 500
POOL_GLOBAL = 2000
POOL_RECENT = 2000
POOL_DIFF = 500
ADDR_BUCKETS = 32768

FEATS = [
    # direct (8)
    'is_own', 'log_cnt', 'last_decay', 'log_in_cnt', 'bidir',
    'log_value_repeat', 'value_mean_dist', 'log_failed_cnt',
    # motif (6)
    'log_key_n', 'motif_w_max', 'motif_w_sum', 'motif_recency',
    'log_co_overlap', 'motif_order_frac',
    # global (6)
    'log_gcnt', 'log_rcnt30', 'log_rcnt7', 'burst', 'log_age', 'ecosystem',
]
DIRECT = FEATS[0:8]
MOTIF = FEATS[8:14]
GLOBL = FEATS[14:20]
CTX = ['log_n_ev', 'log_n_uniq', 'last_ev_decay', 'cp_entropy', 'explore_rate', 'log_in_total']


def load_events_full() -> pd.DataFrame:
    """Both directions, only columns needed for motif features."""
    cols = ['target_address', 'counterparty_address', 'direction', 'event_family',
            'block_timestamp', 'value_lossless', 'receipt_status', 'token_contract_address']
    parts = []
    for p in sorted(SRC.glob('2022-??.parquet')):
        if p.stem >= '2022-09':
            continue
        use = [c for c in cols if c in pq.read_schema(p).names]
        x = pd.read_parquet(p, engine='pyarrow', columns=use)
        x['block_timestamp'] = pd.to_datetime(x['block_timestamp'], utc=True)
        for c in ['target_address', 'counterparty_address', 'event_family', 'direction',
                  'token_contract_address', 'value_lossless']:
            x[c] = base.norm_series(x[c])
        x = x[x.counterparty_address.ne('') & x.target_address.ne('')].copy()
        parts.append(x)
        print(json.dumps({'load': p.name, 'rows': int(len(x))}), flush=True)
    ev = pd.concat(parts, ignore_index=True)
    ev = ev.sort_values(['block_number' if 'block_number' in ev else 'block_timestamp'],
                        kind='mergesort').reset_index(drop=True)
    return ev


def build_motif_index(hist: pd.DataFrame, cutoff: str) -> dict:
    """Single-pass per-cutoff index with dyadic, typed-key, and global stats."""
    t = pd.Timestamp(cutoff, tz='UTC')
    out_cnt = defaultdict(Counter)          # w -> c -> outgoing count
    in_cnt = defaultdict(Counter)           # w -> c -> incoming count
    last_decay = defaultdict(dict)          # w -> c -> max decay (outgoing)
    pair_val = defaultdict(dict)            # w -> c -> [n, sum_logv, repeat_max, failed]
    val_seen = defaultdict(dict)            # w -> c -> {value_str: count}  (capped)
    key_users = defaultdict(set)
    wallet_key_weight = defaultdict(Counter)
    # Typed ecosystem keys: token transfers share (event_family, token_contract),
    # while native/internal interactions use an endpoint-qualified key. This
    # prevents a popular token from being confused with a particular recipient.
    typed_users = defaultdict(set)
    wallet_typed_weight = defaultdict(Counter)
    typed_key_last_ts = {}
    peer_recent_weight = defaultdict(dict)
    gcnt = Counter(); rcnt30 = Counter(); rcnt7 = Counter()
    first_seen = {}; last_seen = {}
    w_events = Counter(); w_first_touch = Counter(); w_seen_pairs = defaultdict(set)

    recent30_start = t - pd.Timedelta(days=30)
    recent7_start = t - pd.Timedelta(days=7)

    for r in hist.itertuples(index=False):
        w, c = r.target_address, r.counterparty_address
        ts = pd.Timestamp(r.block_timestamp)
        age = max(0.0, (t - ts).total_seconds() / 86400.0)
        decay = math.exp(-age / TAU)
        outgoing = (r.direction == 'outgoing')
        if outgoing:
            out_cnt[w][c] += 1
            if decay > last_decay[w].get(c, 0.0):
                last_decay[w][c] = decay
            pv = pair_val[w].get(c)
            if pv is None:
                pv = [0, 0.0, 0, 0]
                pair_val[w][c] = pv
            pv[0] += 1
            v = r.value_lossless
            if v and v != '0':
                try:
                    pv[1] += math.log10(max(1.0, float(v)))
                except (ValueError, OverflowError):
                    pass
                vc = val_seen[w].setdefault(c, {})
                if len(vc) < 8 or v in vc:
                    vc[v] = vc.get(v, 0) + 1
                    if vc[v] > pv[2]:
                        pv[2] = vc[v]
            rs = getattr(r, 'receipt_status', None)
            if rs is not None and not (isinstance(rs, float) and math.isnan(rs)) and float(rs) == 0.0:
                pv[3] += 1
            if c not in w_seen_pairs[w]:
                w_seen_pairs[w].add(c)
                w_first_touch[w] += 1
            w_events[w] += 1
        elif r.direction == 'incoming':
            in_cnt[w][c] += 1
        # global candidate stats use outgoing send-events only (activity as counterparty)
        gcnt[c] += 1
        if ts >= recent30_start:
            rcnt30[c] += 1
        if ts >= recent7_start:
            rcnt7[c] += 1
        if c not in first_seen:
            first_seen[c] = ts
        last_seen[c] = ts
        if outgoing:
            fam = getattr(r, 'event_family', '') or ''
            tok = getattr(r, 'token_contract_address', '') or ''
            k = (c, fam, tok)
            key_users[k].add(w)
            wallet_key_weight[w][k] += decay
            typed = (fam, tok) if tok else (fam, c)
            typed_users[typed].add(w)
            wallet_typed_weight[w][typed] += decay
            typed_key_last_ts[typed] = max(typed_key_last_ts.get(typed, ts), ts)
            old = peer_recent_weight[w].get(c, 0.0)
            if decay > old:
                peer_recent_weight[w][c] = decay

    # hub-normalize key users with deterministic cap
    key_users_capped = {k: (set(sorted(u)[:250]) if len(u) > 250 else u) for k, u in key_users.items()}
    typed_users_capped = {k: (set(sorted(u)[:250]) if len(u) > 250 else u) for k, u in typed_users.items()}
    global_rank = [c for c, _ in sorted(gcnt.items(), key=lambda kv: (-kv[1], kv[0]))]
    recent_rank = [c for c, _ in sorted(rcnt30.items(), key=lambda kv: (-kv[1], kv[0]))]
    peer_sets = {w: set(d) for w, d in peer_recent_weight.items()}
    return {
        'cutoff': cutoff, 't': t, 'out_cnt': out_cnt, 'in_cnt': in_cnt,
        'last_decay': last_decay, 'pair_val': pair_val,
        'key_users': key_users_capped, 'wallet_key_weight': wallet_key_weight,
        'typed_users': typed_users_capped, 'wallet_typed_weight': wallet_typed_weight,
        'typed_key_last_ts': typed_key_last_ts,
        'peer_recent_weight': peer_recent_weight, 'peer_sets': peer_sets,
        'gcnt': gcnt, 'rcnt30': rcnt30, 'rcnt7': rcnt7,
        'first_seen': first_seen, 'last_seen': last_seen,
        'global_rank': global_rank, 'recent_rank': recent_rank,
        'w_events': w_events, 'w_first_touch': w_first_touch,
        'w_n_uniq': {w: len(s) for w, s in w_seen_pairs.items()},
    }


def wallet_context(index: dict, w: str) -> List[float]:
    oc = index['out_cnt'].get(w, Counter())
    n_ev = sum(oc.values())
    n_uniq = len(oc)
    if n_uniq > 1:
        ps = np.array([v / n_ev for v in oc.values()])
        ent = float(-(ps * np.log(ps)).sum() / math.log(n_uniq))
    else:
        ent = 0.0
    ld = index['last_decay'].get(w, {})
    last_ev = max(ld.values()) if ld else 0.0
    explore = index['w_first_touch'].get(w, 0) / max(1, index['w_events'].get(w, 1))
    in_total = sum(index['in_cnt'].get(w, Counter()).values())
    return [math.log1p(n_ev), math.log1p(n_uniq), last_ev, ent, explore, math.log1p(in_total)]


def diffusion_and_motif(index: dict, w: str) -> Dict[str, dict]:
    """One bounded typed walk; returns per-candidate motif aggregates + diffusion weight."""
    t = index['t']
    agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0, 0])  # sum,max,recency,n_paths,n_ordered
    # Use typed ecosystem keys as the primary motif source. A token contract is
    # a blockchain-specific shared context; endpoint-qualified keys retain a
    # conservative fallback for native/internal interactions.
    seed_keys = index['wallet_typed_weight'].get(w, Counter())
    total_seed = sum(seed_keys.values()) or 1.0
    for key, seed in sorted(seed_keys.items(), key=lambda kv: (-kv[1], str(kv[0])))[:MAX_SEED_KEYS]:
        users = index['typed_users'].get(key, set())
        peers = [u for u in sorted(users) if u != w][:MAX_PEERS_PER_KEY]
        if not peers:
            continue
        p_key = seed / total_seed
        p_peer = 1.0 / len(peers)
        hub = math.sqrt(max(1, len(users)))
        key_ts = index['typed_key_last_ts'].get(key, index['t'])
        for peer in peers:
            rw = index['peer_recent_weight'].get(peer, {})
            recips = sorted(rw.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_RECIPS_PER_PEER]
            z = sum(v for _, v in recips) or 1.0
            for c, wgt in recips:
                if c == w:
                    continue
                contrib = p_key * p_peer * (wgt / z) / hub
                a = agg[c]
                a[0] += contrib
                a[1] = max(a[1], contrib)
                a[2] = max(a[2], wgt)
                a[3] += 1
                # A valid temporal motif requires the shared typed context to
                # precede the peer's later recipient event. This is conservative:
                # missing timestamps never receive credit.
                if index['first_seen'].get(c, key_ts) >= key_ts:
                    a[4] += 1
    # co-counterparty overlap: past counterparties of w that recently sent to c
    own = index['last_decay'].get(w, {})
    own_top = [c for c, _ in sorted(own.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_OWN_FOR_OVERLAP]]
    co = Counter()
    for p in own_top:
        for c in index['peer_sets'].get(p, ()):
            if c != w:
                co[c] += 1
    out = {}
    cands = set(agg) | set(co)
    for c in cands:
        a = agg.get(c, [0.0, 0.0, 0.0, 0, 0])
        out[c] = {'diff_w': a[0], 'w_max': a[1], 'recency': a[2], 'key_n': a[3],
                  'order_frac': a[4] / max(1, a[3]), 'co_overlap': co.get(c, 0)}
    return out


def pair_features(index: dict, w: str, c: str, dm: dict) -> List[float]:
    oc = index['out_cnt'].get(w, Counter())
    cnt = oc.get(c, 0)
    ic = index['in_cnt'].get(w, Counter()).get(c, 0)
    ld = index['last_decay'].get(w, {}).get(c, 0.0)
    pv = index['pair_val'].get(w, {}).get(c, [0, 0.0, 0, 0])
    # value fingerprint: exact-repeat count, and distance of pair mean log-value
    # from the wallet's overall mean log-value (approximated by pair mean if no wallet mean)
    mean_lv = pv[1] / pv[0] if pv[0] else 0.0
    vrep = pv[2] if pv[2] >= 2 else 0
    failed = pv[3]
    g = index['gcnt'].get(c, 0)
    r30 = index['rcnt30'].get(c, 0)
    r7 = index['rcnt7'].get(c, 0)
    burst = (r7 + 0.5) / (r30 / 4.0 + 0.5)
    fs = index['first_seen'].get(c)
    age = max(0.0, (index['t'] - fs).total_seconds() / 86400.0) if fs is not None else 0.0
    d = dm.get(c, {'diff_w': 0.0, 'w_max': 0.0, 'recency': 0.0, 'key_n': 0, 'order_frac': 0.0, 'co_overlap': 0})
    return [
        1.0 if cnt > 0 else 0.0, math.log1p(cnt), ld,
        math.log1p(ic), 1.0 if (cnt > 0 and ic > 0) else 0.0,
        math.log1p(vrep), mean_lv / 25.0, math.log1p(failed),
        math.log1p(d['key_n']), d['w_max'], d['diff_w'], d['recency'],
        math.log1p(d['co_overlap']), d.get('order_frac', 0.0),
        math.log1p(g), math.log1p(r30), math.log1p(r7), min(burst, 10.0) / 10.0,
        math.log1p(age), 1.0 if d['key_n'] > 0 or cnt > 0 else 0.0,
    ]


def build_pool(index: dict, w: str, dm: dict) -> List[str]:
    oc = index['out_cnt'].get(w, Counter())
    ld = index['last_decay'].get(w, {})
    own = list(dict.fromkeys(
        [c for c, _ in sorted(ld.items(), key=lambda kv: (-kv[1], kv[0]))[:POOL_OWN]]
        + [c for c, _ in sorted(oc.items(), key=lambda kv: (-kv[1], kv[0]))[:POOL_OWN]]))
    diff = [c for c, _ in sorted(dm.items(), key=lambda kv: (-kv[1]['diff_w'], kv[0]))[:POOL_DIFF]]
    return list(dict.fromkeys(own + diff
                              + index['recent_rank'][:POOL_RECENT]
                              + index['global_rank'][:POOL_GLOBAL]))


def extract_dataset(ev: pd.DataFrame, cases: pd.DataFrame, cache: Path) -> List[dict]:
    per_case = []
    for cutoff, g in cases.groupby('cutoff', sort=True):
        t0 = time.time()
        hist = ev[ev.block_timestamp < pd.Timestamp(cutoff, tz='UTC')]
        index = build_motif_index(hist, cutoff)
        print(json.dumps({'extract_index': cutoff, 'hist_rows': int(len(hist)),
                          'seconds': round(time.time() - t0, 1)}), flush=True)
        for r in g.itertuples(index=False):
            if r.split == 'train_expanded' and r.cutoff >= '2022-07-01':
                continue
            w = r.wallet
            dm = diffusion_and_motif(index, w)
            pool = build_pool(index, w, dm)
            X = np.array([pair_features(index, w, c, dm) for c in pool], dtype=np.float32)
            cb = np.array([base_h(c) for c in pool], dtype=np.int32)
            ctx = np.array(wallet_context(index, w), dtype=np.float32)
            y = r.target if r.active else ''
            y_idx = pool.index(y) if (y and y in pool) else -1
            if y:
                oc = index['out_cnt'].get(w, Counter())
                vis = 'own_seen' if y in oc else ('global_seen' if y in index['gcnt'] else 'open_world')
            else:
                vis = 'none'
            per_case.append({'case_id': r.case_id, 'split': r.split, 'cutoff': r.cutoff,
                             'wallet': w, 'active': int(r.active), 'target': y,
                             'visibility': vis, 'X': X, 'cand_bucket': cb, 'ctx': ctx,
                             'y_idx': y_idx, 'pool': pool})
        print(json.dumps({'extract_cases': cutoff, 'cases': int(len(g)),
                          'seconds_total': round(time.time() - t0, 1)}), flush=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    with cache.open('wb') as f:
        pickle.dump(per_case, f, protocol=4)
    return per_case


def base_h(addr: str) -> int:
    return int(hashlib.sha1(addr.encode()).hexdigest(), 16) % ADDR_BUCKETS

# ---------------- learned source-gated retriever ----------------
import torch
import torch.nn as nn
import torch.nn.functional as F


class SourceMLP(nn.Module):
    def __init__(self, n_in: int, hidden: int = 48):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_in, hidden), nn.GELU(),
                                 nn.Dropout(0.10), nn.Linear(hidden, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


class MotifGatedScorer(nn.Module):
    """Wallet-conditioned mixture of auditable feature-source scores."""
    def __init__(self, hidden: int = 64):
        super().__init__()
        self.direct = SourceMLP(len(DIRECT), hidden)
        # Diffusion is separated from motif shape: these are the walk weight,
        # maximum path contribution, and path recency features.
        self.diffusion = SourceMLP(3, hidden)
        self.motif = SourceMLP(3, hidden)
        self.global_prior = SourceMLP(len(GLOBL), hidden)
        self.gate = nn.Sequential(nn.Linear(len(CTX), hidden), nn.GELU(),
                                  nn.Linear(hidden, 4))
        self.activity = nn.Sequential(nn.Linear(len(CTX), hidden), nn.GELU(),
                                      nn.Linear(hidden, 1))
        self.open_world = nn.Sequential(nn.Linear(len(CTX), hidden), nn.GELU(),
                                        nn.Linear(hidden, 1))

    def forward(self, x, ctx):
        # x=(B,C,20), ctx=(B,6)
        source = torch.stack([
            self.direct(x[:, :, 0:8]),
            self.diffusion(x[:, :, [9, 10, 11]]),
            self.motif(x[:, :, [8, 12, 13]]),
            self.global_prior(x[:, :, 14:20]),
        ], dim=-1)  # (B,C,4)
        gate = torch.softmax(self.gate(ctx), dim=-1)  # (B,4)
        contribution = source * gate.unsqueeze(1)
        logits = contribution.sum(dim=-1)
        return logits, contribution, gate, self.activity(ctx).squeeze(-1), self.open_world(ctx).squeeze(-1)


def collate_retriever(cases: List[dict], device: str):
    bsz = len(cases)
    max_c = max(len(c['pool']) for c in cases)
    nfeat = len(FEATS)
    x = torch.zeros(bsz, max_c, nfeat, dtype=torch.float32, device=device)
    mask = torch.zeros(bsz, max_c, dtype=torch.bool, device=device)
    ctx = torch.zeros(bsz, len(CTX), dtype=torch.float32, device=device)
    y = torch.full((bsz,), -1, dtype=torch.long, device=device)
    active = torch.zeros(bsz, dtype=torch.float32, device=device)
    ow = torch.zeros(bsz, dtype=torch.float32, device=device)
    support = torch.zeros(bsz, dtype=torch.bool, device=device)
    for i, c in enumerate(cases):
        n = len(c['pool'])
        x[i, :n] = torch.as_tensor(c['X'], dtype=torch.float32, device=device)
        mask[i, :n] = True
        ctx[i] = torch.as_tensor(c['ctx'], dtype=torch.float32, device=device)
        active[i] = float(c['active'])
        ow[i] = float(c['visibility'] == 'open_world')
        if c['y_idx'] >= 0:
            y[i] = int(c['y_idx'])
            support[i] = True
    return x, mask, ctx, y, active, ow, support


def _auc(scores, labels):
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(labels, scores)) if len(set(labels)) > 1 else None
    except Exception:
        return None


@torch.no_grad()
def evaluate_retriever(model, cases: List[dict], device: str, batch_size: int = 32,
                        return_rows: bool = False):
    model.eval()
    ks = [1, 5, 50, 100, 500, 2000]
    hits = {k: 0 for k in ks}
    active = support = 0
    act_scores, act_labels, ow_scores, ow_labels = [], [], [], []
    rows = []
    for start in range(0, len(cases), batch_size):
        chunk = cases[start:start + batch_size]
        x, mask, ctx, y, act, ow, has = collate_retriever(chunk, device)
        logits, contrib, gate, act_logit, ow_logit = model(x, ctx)
        logits = logits.masked_fill(~mask, -1e9)
        order = logits.argsort(dim=1, descending=True)
        act_scores.extend(act_logit.cpu().tolist()); act_labels.extend(act.cpu().tolist())
        ow_scores.extend(ow_logit.cpu().tolist()); ow_labels.extend(ow.cpu().tolist())
        for j, c in enumerate(chunk):
            if not c['active']:
                continue
            active += 1
            if not bool(has[j]):
                continue
            support += 1
            rank_pos = (order[j] == y[j]).nonzero(as_tuple=False)
            rank = int(rank_pos[0].item()) + 1 if len(rank_pos) else None
            if rank is not None:
                for k in ks:
                    hits[k] += int(rank <= k)
            if return_rows:
                topn = min(100, len(c['pool']))
                for rank0 in range(topn):
                    idx = int(order[j, rank0].item())
                    source_contrib = contrib[j, idx].cpu().tolist()
                    dom = int(np.argmax(source_contrib))
                    rows.append({
                        'case_id': c['case_id'], 'cutoff': c['cutoff'], 'wallet': c['wallet'],
                        'target': c['target'], 'target_rank': rank, 'rank': rank0 + 1,
                        'candidate': c['pool'][idx], 'score': float(logits[j, idx].item()),
                        'direct_contribution': float(source_contrib[0]),
                        'diffusion_contribution': float(source_contrib[1]),
                        'motif_contribution': float(source_contrib[2]),
                        'global_contribution': float(source_contrib[3]),
                        'dominant_source': ('direct', 'diffusion', 'motif', 'global')[dom],
                        'gate_direct': float(gate[j, 0].item()),
                        'gate_diffusion': float(gate[j, 1].item()),
                        'gate_motif': float(gate[j, 2].item()),
                        'gate_global': float(gate[j, 3].item()),
                    })
    active_ow = [(s, l) for s, l, a in zip(ow_scores, ow_labels, act_labels) if a > 0.5]
    metrics = {
        'active': active, 'pool_support': support,
        'pool_support_rate': support / max(1, active),
        'recall_hits_supported': {str(k): hits[k] for k in ks},
        'recall_at_50_all_active': hits[50] / max(1, active),
        'recall_at_100_all_active': hits[100] / max(1, active),
        'activity_auroc': _auc(act_scores, act_labels),
        'open_world_auroc_active': _auc([s for s, _ in active_ow], [l for _, l in active_ow]),
    }
    return (metrics, rows) if return_rows else metrics


def train_retriever(cases: List[dict], epochs: int, batch_size: int, lr: float,
                    seed: int, device: str):
    torch.manual_seed(seed); np.random.seed(seed)
    rng = np.random.default_rng(seed)
    train = [c for c in cases if c['split'] in ('train', 'train_expanded')]
    dev = [c for c in cases if c['split'] == 'dev']
    model = MotifGatedScorer().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    log = []
    for epoch in range(epochs):
        model.train()
        order = rng.permutation(len(train))
        total = 0.0
        n_seen = 0
        for pos in range(0, len(order), batch_size):
            chunk = [train[k] for k in order[pos:pos + batch_size]]
            x, mask, ctx, y, active, ow, support = collate_retriever(chunk, device)
            logits, _, _, act_logit, ow_logit = model(x, ctx)
            logits = logits.masked_fill(~mask, -1e9)
            rank_mask = support & active.bool()
            rank_loss = F.cross_entropy(logits[rank_mask], y[rank_mask]) if rank_mask.any() else logits.sum() * 0.0
            act_loss = F.binary_cross_entropy_with_logits(act_logit, active)
            ow_mask = active.bool()
            ow_loss = (F.binary_cross_entropy_with_logits(ow_logit[ow_mask], ow[ow_mask])
                       if ow_mask.any() else ow_logit.sum() * 0.0)
            loss = rank_loss + 0.5 * act_loss + 0.5 * ow_loss
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            total += float(loss.item()) * len(chunk); n_seen += len(chunk)
        met = evaluate_retriever(model, dev, device)
        rec = {'epoch': epoch, 'train_loss': total / max(1, n_seen),
               **{'dev_' + k: v for k, v in met.items()}}
        log.append(rec); print(json.dumps(rec), flush=True)
    return model, log, train, dev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases-csv', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--epochs', type=int, default=6)
    ap.add_argument('--batch-size', type=int, default=32)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--device', default='cuda:0')
    ap.add_argument('--feature-cache', type=Path)
    args = ap.parse_args()
    out = args.out; out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    cache = args.feature_cache or (out / 'motif_cases.pkl')
    if cache.exists():
        with cache.open('rb') as f:
            cases = pickle.load(f)
        print(json.dumps({'cache_loaded': str(cache), 'cases': len(cases)}), flush=True)
    else:
        ev = load_events_full()
        df = pd.read_csv(args.cases_csv, dtype={'wallet': str, 'target': str})
        df['wallet'] = df.wallet.fillna('').astype(str).str.lower()
        df['target'] = df.target.fillna('').astype(str).str.lower()
        cases = extract_dataset(ev, df, cache)
        print(json.dumps({'cache_written': str(cache), 'cases': len(cases)}), flush=True)
    model, log, train, dev = train_retriever(cases, args.epochs, args.batch_size,
                                               args.lr, args.seed, args.device)
    final, rows = evaluate_retriever(model, dev, args.device, return_rows=True)
    torch.save({'state_dict': model.state_dict(),
                'config': {'features': FEATS, 'context': CTX,
                           'sources': ['direct', 'diffusion', 'motif', 'global']}},
               out / 'motif_gated_retriever_v1.pt')
    if rows:
        pd.DataFrame(rows).to_csv(out / 'dev_provenance_top100.csv', index=False)
    dev_active = [c for c in dev if c['active']]
    visibility = Counter(c['visibility'] for c in dev_active)
    summary = {
        'status': 'complete_train_dev_only_holdout_locked',
        'run': out.name, 'cases_csv': str(args.cases_csv),
        'train_cases': len(train), 'dev_cases': len(dev), 'dev_active': len(dev_active),
        'dev_visibility_active': dict(visibility),
        'dev_pool_support_active': sum(c['y_idx'] >= 0 for c in dev_active),
        'holdout_labels_materialized': False, 'holdout_future_rows_read': False,
        'model_note': 'typed temporal motif retriever with wallet-conditioned four-source gating; no TGN source yet',
        'source_groups': {'direct': DIRECT, 'diffusion': ['motif_w_max', 'motif_w_sum', 'motif_recency'],
                          'motif': ['log_key_n', 'log_co_overlap', 'motif_order_frac'],
                          'global': GLOBL},
        'loss': 'in-pool ranking + 0.5 activity BCE + 0.5 OPEN_WORLD BCE',
        'final_dev': final, 'train_log': log,
        'finished_seconds': time.time() - t0,
    }
    (out / 'motif_gated_retriever_summary.json').write_text(
        json.dumps(summary, indent=2, default=str) + '\n')
    print(json.dumps({'status': summary['status'], 'out': str(out),
                      'seconds': summary['finished_seconds']}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc(); raise
