#!/usr/bin/env python3
"""Leakage-audited candidate baselines for EX-Graph.

This run deliberately keeps the frozen train/dev/holdout split untouched.  It
adds a train-only expansion and evaluates address retrieval plus an explicit
OPEN_WORLD option.  OPEN_WORLD is never counted as a concrete address hit.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, shutil, sys, time, traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC = ROOT / 'artifacts/offline_chain_events_v1_20260929_full'
FROZEN = ROOT / 'artifacts/candidate_teacher_student_autoresearch_20260930T040500Z_fix02'
EXPL = ROOT / 'artifacts/pure_chain_next_recipient_v1_20260929_run02/wallet_cutoff_labels.csv'
DEFAULT_OUT = ROOT / ('artifacts/candidate_openworld_temporal_baselines_20260930T' + time.strftime('%H%M%SZ', time.gmtime()))

HIST_COLS = [
    'target_address','counterparty_address','direction','event_family',
    'block_timestamp','block_number','transaction_index','transaction_hash',
    'event_index','token_contract_address','receipt_status'
]
CUTS = [('train','2022-06-01'), ('dev','2022-07-01')]
K_VALUES = [1, 5, 50, 100, 500, 2000]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def norm_series(x: pd.Series) -> pd.Series:
    return x.fillna('').astype(str).str.lower()


def load_events() -> pd.DataFrame:
    parts = []
    for p in sorted(SRC.glob('2022-??.parquet')):
        if p.stem >= '2022-09':
            continue
        schema_cols = pq.read_schema(p).names
        use = [c for c in HIST_COLS if c in schema_cols]
        x = pd.read_parquet(p, engine='pyarrow', columns=use)
        x['block_timestamp'] = pd.to_datetime(x['block_timestamp'], utc=True)
        for c in ['target_address','counterparty_address','transaction_hash','token_contract_address','event_family','direction']:
            if c in x:
                x[c] = norm_series(x[c])
        x = x[(x.direction == 'outgoing') & x.counterparty_address.ne('')].copy()
        parts.append(x)
        print(json.dumps({'load': p.name, 'retained_outgoing_rows': int(len(x))}), flush=True)
    ev = pd.concat(parts, ignore_index=True)
    sort_cols = [c for c in ['block_number','transaction_index','event_index','transaction_hash'] if c in ev]
    ev = ev.sort_values(sort_cols, kind='mergesort').reset_index(drop=True)
    return ev


def load_locked_wallets() -> set[str]:
    frozen = set(pd.read_csv(FROZEN/'cases_frozen.csv', dtype=str).wallet.str.lower())
    frozen |= set(pd.read_csv(FROZEN/'holdout_case_ids_locked.csv', dtype=str).wallet.str.lower())
    explored = set(pd.read_csv(EXPL, dtype=str).wallet.dropna().str.lower())
    return frozen | explored


def first_future_labels(ev: pd.DataFrame, cutoff: str, wallets: Iterable[str]) -> Dict[str, str]:
    t = pd.Timestamp(cutoff, tz='UTC')
    end = t + pd.Timedelta(days=7)
    wset = set(wallets)
    fut = ev[(ev.block_timestamp >= t) & (ev.block_timestamp < end) &
             (ev.event_family == 'external_tx') & ev.target_address.isin(wset)]
    fut = fut.sort_values(['target_address','block_number','transaction_index','event_index','transaction_hash'], kind='mergesort')
    out = {}
    for r in fut.itertuples(index=False):
        out.setdefault(r.target_address, r.counterparty_address)
    return out


def make_expanded_train_cases(ev: pd.DataFrame, n_per_cutoff: int = 400) -> pd.DataFrame:
    """Create extra train-only cases using only pre-2022-07-01 information.

    Extra wallets are disjoint from frozen train/dev/holdout and previously
    explored wallets.  Labels use the same frozen first outgoing external_tx
    definition, but are never used for dev/holdout retrieval.
    """
    locked = load_locked_wallets()
    rows = []
    audit = []
    selected = set()
    # Keep all training cutoffs strictly before the frozen July dev cutoff.
    extra_cuts = ['2022-04-01', '2022-04-15', '2022-05-01', '2022-05-15', '2022-06-15']
    for cutoff in extra_cuts:
        t = pd.Timestamp(cutoff, tz='UTC')
        hist = ev[ev.block_timestamp < t]
        eligible = set(hist.target_address.dropna()) - locked - selected - {''}
        ordered = sorted(eligible, key=lambda w: hashlib.sha256((w+'|'+cutoff+'|expanded').encode()).hexdigest())
        chosen = ordered[:n_per_cutoff]
        selected.update(chosen)
        labels = first_future_labels(ev, cutoff, chosen)
        for w in chosen:
            y = labels.get(w, '')
            rows.append({
                'case_id': f'exp_train_{cutoff}_{w}', 'split': 'train_expanded',
                'cutoff': cutoff, 'wallet': w, 'active': int(bool(y)), 'target': y,
            })
        audit.append({
            'cutoff': cutoff, 'history_rows': int(len(hist)),
            'eligible_before_selection': int(len(eligible)), 'chosen': int(len(chosen)),
            'active': int(sum(bool(labels.get(w, '')) for w in chosen)),
            'future_labels_used_only_for_train_case_construction': True,
        })
    out = pd.DataFrame(rows)
    return out, audit


def build_cases(ev: pd.DataFrame, out: Path, n_extra: int) -> Tuple[pd.DataFrame, dict]:
    frozen = pd.read_csv(FROZEN/'cases_frozen.csv', dtype={'wallet':str, 'target':str})
    # Only train/dev are materialized; holdout IDs remain locked and unread.
    frozen = frozen[frozen.split.isin(['train','dev'])].copy()
    expanded, audit = make_expanded_train_cases(ev, n_extra)
    cases = pd.concat([frozen, expanded], ignore_index=True)
    cases['wallet'] = cases.wallet.str.lower()
    cases['target'] = cases.target.fillna('').astype(str).str.lower()
    cases.to_csv(out/'cases_train_dev_with_expansion.csv', index=False)
    frozen.to_csv(out/'cases_frozen_train_dev_copy.csv', index=False)
    (out/'expanded_case_audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    meta = {
        'frozen_case_count': int(len(frozen)), 'expanded_case_count': int(len(expanded)),
        'expanded_active': int(expanded.active.sum()), 'expanded_cutoffs': sorted(expanded.cutoff.unique().tolist()),
        'frozen_holdout_labels_materialized': False, 'frozen_holdout_future_rows_read': False,
        'wallet_overlap_expanded_vs_frozen': int(len(set(expanded.wallet) & set(frozen.wallet))),
    }
    return cases, meta


def _key(row) -> Tuple[str, str, str]:
    return (row.counterparty_address, row.event_family, getattr(row, 'token_contract_address', '') or '')


def build_temporal_index(hist: pd.DataFrame, cutoff: str, max_users_per_key: int = 250,
                         max_keys_per_wallet: int = 400, max_recent_per_wallet: int = 200) -> dict:
    """Build a truncated typed temporal diffusion index.

    The diffusion is a normalized wallet -> typed interaction key -> peer wallet
    -> peer recipient walk.  Each transition is time-decayed as of cutoff and
    hub-normalized.  It is intentionally an auditable approximation to typed
    temporal personalized PageRank, not a full-graph PPR implementation.
    """
    t = pd.Timestamp(cutoff, tz='UTC')
    tau = 90.0
    by_wallet_counter = defaultdict(Counter)
    by_wallet_last = defaultdict(dict)
    by_wallet_recent = defaultdict(list)
    key_users = defaultdict(set)
    wallet_key_weight = defaultdict(Counter)
    key_order = {}
    global_counter = Counter()
    recent_counter = Counter()
    peer_recent = defaultdict(list)
    peer_recent_weight = defaultdict(dict)

    # Canonical order is already event order; use one pass for counters and keys.
    for r in hist.itertuples(index=False):
        w, c = r.target_address, r.counterparty_address
        if not w or not c:
            continue
        fam = getattr(r, 'event_family', '') or ''
        tok = getattr(r, 'token_contract_address', '') or ''
        k = (c, fam, tok)
        if k not in key_order:
            key_order[k] = len(key_order)
        by_wallet_counter[w][c] += 1
        ts = pd.Timestamp(r.block_timestamp)
        age = max(0.0, (t - ts).total_seconds() / 86400.0)
        decay = math.exp(-age / tau)
        by_wallet_last[w][c] = max(by_wallet_last[w].get(c, 0.0), decay)
        global_counter[c] += 1
        key_users[k].add(w)
        wallet_key_weight[w][k] += decay
        if fam == 'external_tx':
            # Keep a decayed recipient trace for the peer->candidate transition.
            old = peer_recent_weight[w].get(c, 0.0)
            peer_recent_weight[w][c] = max(old, decay)
    # Recent lists and recent global popularity are deterministic.
    recent_start = t - pd.Timedelta(days=30)
    recent = hist[hist.block_timestamp >= recent_start]
    for c, n in recent.counterparty_address.value_counts().items():
        recent_counter[c] = int(n)
    for w, d in peer_recent_weight.items():
        peer_recent[w] = [c for c, _ in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:max_recent_per_wallet]]
    # cap key users but preserve deterministic address order
    key_users_capped = {}
    for k, users in key_users.items():
        if len(users) <= max_users_per_key:
            key_users_capped[k] = users
        else:
            key_users_capped[k] = set(sorted(users)[:max_users_per_key])
    global_rank = [c for c,_ in sorted(global_counter.items(), key=lambda kv:(-kv[1],kv[0]))]
    recent_rank = [c for c,_ in sorted(recent_counter.items(), key=lambda kv:(-kv[1],kv[0]))]
    return {
        'cutoff': cutoff, 'tau_days': tau,
        'by_wallet_counter': by_wallet_counter,
        'by_wallet_last': by_wallet_last,
        'by_wallet_recent': by_wallet_recent,
        'key_users': key_users_capped,
        'wallet_key_weight': wallet_key_weight,
        'peer_recent': peer_recent,
        'peer_recent_weight': peer_recent_weight,
        'global_counter': global_counter,
        'recent_counter': recent_counter,
        'global_rank': global_rank,
        'recent_rank': recent_rank,
        'key_count': len(key_users),
    }


def _norm_scores(score: Counter) -> Counter:
    if not score:
        return score
    vals = np.array(list(score.values()), dtype=float)
    lo, hi = float(vals.min()), float(vals.max())
    if hi <= lo:
        return Counter({k: 1.0 for k in score})
    return Counter({k: (float(v)-lo)/(hi-lo) for k,v in score.items()})


def rank_for_wallet(index: dict, wallet: str, method: str, max_candidates: int = 2000) -> Tuple[List[str], dict]:
    direct_counts = index['by_wallet_counter'].get(wallet, Counter())
    direct_last = index['by_wallet_last'].get(wallet, {})
    global_rank = index['global_rank']
    recent_rank = index['recent_rank']

    evidence = {
        'direct_count': int(sum(direct_counts.values())),
        'direct_unique': int(len(direct_counts)),
    }
    if method == 'global':
        return global_rank[:max_candidates], evidence
    if method == 'recent_popularity':
        return recent_rank[:max_candidates], evidence
    if method == 'own_frequency':
        ranked = [c for c,_ in sorted(direct_counts.items(), key=lambda kv:(-kv[1],kv[0]))]
        return ranked[:max_candidates], evidence
    if method == 'own_recency':
        ranked = [c for c,_ in sorted(direct_last.items(), key=lambda kv:(-kv[1],kv[0]))]
        return ranked[:max_candidates], evidence

    # Normalized typed temporal diffusion: wallet -> typed key -> peer -> recipient.
    # Bounded fan-out keeps this auditable and fast: top seed keys, deterministic
    # peer/recipient caps, hub-normalized key users.
    diff = Counter()
    seed_keys = index['wallet_key_weight'].get(wallet, Counter())
    total_seed = sum(seed_keys.values()) or 1.0
    for key, seed in sorted(seed_keys.items(), key=lambda kv: (-kv[1], str(kv[0])))[:60]:
        users = index['key_users'].get(key, set())
        peers = [u for u in sorted(users) if u != wallet][:25]
        if not peers:
            continue
        p_key = seed / total_seed
        p_peer = 1.0 / len(peers)
        hub = math.sqrt(max(1, len(users)))
        for peer in peers:
            rw = index['peer_recent_weight'].get(peer, {})
            recips = index['peer_recent'].get(peer, [])[:40]
            z = sum(rw.get(c, 0.0) for c in recips) or 1.0
            for c in recips:
                if c == wallet:
                    continue
                diff[c] += p_key * p_peer * (rw.get(c, 0.0) / z) / hub
    evidence['diffusion_unique'] = int(len(diff))
    evidence['seed_key_count'] = int(len(seed_keys))
    evidence['open_world_option'] = 'OPEN_WORLD'

    # Deterministic block-concatenation, mirroring the frozen hybrid baseline:
    # wallet-specific evidence first, then shared popularity tails.
    own_freq_rank = [c for c,_ in sorted(direct_counts.items(), key=lambda kv:(-kv[1],kv[0]))]
    own_rec_rank = [c for c,_ in sorted(direct_last.items(), key=lambda kv:(-kv[1],kv[0]))]
    ndiff = _norm_scores(diff)
    nrec = _norm_scores(Counter(direct_last))
    if method == 'typed_temporal_diffusion':
        score = Counter({c: ndiff.get(c,0.0) + 0.35*nrec.get(c,0.0)
                         for c in set(direct_counts) | set(diff)})
        ranked = [c for c,_ in sorted(score.items(), key=lambda kv:(-kv[1],kv[0]))[:600]]
        merged = list(dict.fromkeys(ranked + recent_rank[:max_candidates]))
        return merged[:max_candidates], evidence
    if method == 'typed_temporal_diffusion_union':
        diff_rank = [c for c,_ in sorted(diff.items(), key=lambda kv:(-kv[1],kv[0]))]
        merged = list(dict.fromkeys(own_rec_rank[:500] + diff_rank[:500] + own_freq_rank[:500]
                                    + recent_rank[:1000] + global_rank[:1000]))
        return merged[:max_candidates], evidence
    if method == 'hybrid':
        merged = list(dict.fromkeys(own_rec_rank[:500] + own_freq_rank[:500]
                                    + recent_rank[:1000] + global_rank[:1000]))
        return merged[:max_candidates], evidence
    raise ValueError(method)

def visibility(ev: pd.DataFrame, cases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cutoff, g in cases.groupby('cutoff', sort=True):
        t = pd.Timestamp(cutoff, tz='UTC')
        hist = ev[ev.block_timestamp < t]
        endpoints = set(hist.target_address) | set(hist.counterparty_address)
        own = defaultdict(set)
        for r in hist.itertuples(index=False):
            own[r.target_address].add(r.counterparty_address)
        for r in g.itertuples(index=False):
            y = r.target
            if not y:
                continue
            own_seen = y in own.get(r.wallet, set())
            global_seen = y in endpoints
            rows.append({
                'case_id': r.case_id, 'split': r.split, 'cutoff': r.cutoff, 'wallet': r.wallet,
                'target': y, 'active': int(r.active),
                'target_visibility': 'own_seen' if own_seen else ('global_seen' if global_seen else 'open_world'),
                'own_seen': int(own_seen), 'global_seen': int(global_seen),
                'new_to_wallet': int(global_seen and not own_seen), 'open_world': int(not global_seen),
            })
    return pd.DataFrame(rows)


def evaluate_retrieval(ev: pd.DataFrame, cases: pd.DataFrame, out: Path, methods: List[str]) -> Tuple[pd.DataFrame, List[dict]]:
    rows = []
    for cutoff, g in cases.groupby('cutoff', sort=True):
        t = pd.Timestamp(cutoff, tz='UTC')
        hist = ev[ev.block_timestamp < t]
        start = time.time()
        index = build_temporal_index(hist, cutoff)
        print(json.dumps({'cutoff': cutoff, 'hist_rows': int(len(hist)), 'index_seconds': time.time()-start, 'typed_keys': index['key_count']}), flush=True)
        for r in g.itertuples(index=False):
            if r.split == 'train_expanded' and r.cutoff >= '2022-07-01':
                continue
            ranks = {}
            evid = {}
            for m in methods:
                ranks[m], evid[m] = rank_for_wallet(index, r.wallet, m)
            y = r.target
            for m in methods:
                cand = ranks[m]
                z = {
                    'case_id': r.case_id, 'split': r.split, 'cutoff': r.cutoff, 'wallet': r.wallet,
                    'active': int(r.active), 'target': y, 'method': m,
                    'candidate_count': len(cand), 'open_world_option': 'OPEN_WORLD',
                    'target_in_pool': int(bool(y) and y in cand),
                    'target_visibility': '', 'own_seen': '', 'global_seen': '', 'open_world': '',
                    **{f'hit_{k}': int(bool(y) and y in cand[:k]) for k in K_VALUES},
                    **{f'evidence_{k}': v for k,v in evid[m].items()},
                }
                rows.append(z)
    pred = pd.DataFrame(rows)
    pred.to_csv(out/'candidate_predictions_train_dev.csv', index=False)
    vis = visibility(ev, cases)
    # Join visibility to active predictions; do not use it to rank.
    pred = pred.drop(columns=['target_visibility','own_seen','global_seen','open_world'])
    pred = pred.merge(vis[['case_id','target_visibility','own_seen','global_seen','open_world']], on='case_id', how='left')
    pred.to_csv(out/'candidate_predictions_train_dev_with_visibility.csv', index=False)
    summaries = []
    for method, g in pred.groupby('method', sort=True):
        active = g[g.active.eq(1)]
        rec = {'method': method, 'cases': int(len(g)), 'active': int(len(active)),
               'support_closed_world': int(active.global_seen.sum()),
               'address_recall_at_1': int(active.hit_1.sum()),
               'address_recall_at_5': int(active.hit_5.sum()),
               'address_recall_at_50': int(active.hit_50.sum()),
               'address_recall_at_100': int(active.hit_100.sum()),
               'address_recall_at_500': int(active.hit_500.sum()),
               'address_recall_at_2000': int(active.hit_2000.sum()),
               'closed_world_ceiling': float(active.global_seen.mean()) if len(active) else None,
               'new_to_wallet': int((active.target_visibility == 'global_seen').sum()),
               'own_seen': int((active.target_visibility == 'own_seen').sum()),
               'open_world': int((active.target_visibility == 'open_world').sum()),
               'schemeA_extended_coverage_at_50': float((active.hit_50.eq(1) | active.open_world.eq(1)).mean()) if len(active) else None,
               'open_world_option_always_available': True,
               'status': 'diagnostic_train_dev_only'}
        summaries.append(rec)
    (out/'retrieval_summary.json').write_text(json.dumps(summaries, indent=2)+'\n')
    vis_summary = []
    for (split, cutoff), g in vis.groupby(['split','cutoff'], sort=True):
        a = g[g.active.eq(1)]
        vis_summary.append({'split': split, 'cutoff': cutoff, 'active': int(len(a)),
                            'own_seen': int((a.target_visibility=='own_seen').sum()),
                            'global_seen_not_own': int((a.target_visibility=='global_seen').sum()),
                            'open_world': int((a.target_visibility=='open_world').sum()),
                            'closed_world_ceiling': float(a.global_seen.mean()) if len(a) else None})
    vis.to_csv(out/'target_visibility_by_case.csv', index=False)
    (out/'visibility_summary.json').write_text(json.dumps(vis_summary, indent=2)+'\n')
    return pred, summaries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--n-extra-per-cutoff', type=int, default=400)
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.time()
    ev = load_events()
    cases, case_meta = build_cases(ev, out, args.n_extra_per_cutoff)
    methods = ['own_frequency','own_recency','recent_popularity','global','hybrid','typed_temporal_diffusion','typed_temporal_diffusion_union']
    pred, summaries = evaluate_retrieval(ev, cases, out, methods)
    manifest = {
        'run': out.name, 'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'status': 'complete_train_dev_openworld_audit_and_temporal_diffusion',
        'source_dir': str(SRC), 'source_manifest_sha256': sha256(SRC/'manifest.json'),
        'source_months_loaded': [p.name for p in sorted(SRC.glob('2022-??.parquet')) if p.stem < '2022-09'],
        'source_rows_retained_outgoing_nonempty_counterparty': int(len(ev)),
        'frozen_protocol': str(FROZEN/'protocol_v2.md'), 'frozen_protocol_sha256': sha256(FROZEN/'protocol_v2.md'),
        'frozen_cases_sha256': sha256(FROZEN/'cases_frozen.csv'),
        'holdout_ids_sha256': sha256(FROZEN/'holdout_case_ids_locked.csv'),
        'holdout_labels_materialized': False, 'holdout_future_rows_read': False,
        'evaluation_splits': ['train','dev'], 'evaluation_cutoffs': sorted(cases.cutoff.unique().tolist()),
        'methods': methods, 'k_values': K_VALUES,
        'open_world_protocol': 'OPEN_WORLD is appended as a non-address option and never counted as concrete address hit',
        'schemeA': 'top-K known addresses plus separate OPEN_WORLD option; extended coverage reported separately',
        'expanded_train': case_meta,
        'algorithm_note': 'typed_temporal_diffusion is a truncated normalized wallet-key-peer-recipient temporal walk; not exact full-graph PPR',
        'finished_seconds': time.time()-t0,
    }
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    report = ['# Candidate baseline report', '', f"Run: `{out.name}`", '',
              'This run is train/dev only. August holdout labels were not materialized or read.', '',
              '## Frozen boundary', json.dumps(case_meta, indent=2), '',
              '## Retrieval summaries', json.dumps(summaries, indent=2), '',
              '## Interpretation',
              '- Address recall counts only concrete addresses in the as-of candidate universe.',
              '- `OPEN_WORLD` is an explicit option outside the address Top-K and is not an address hit.',
              '- `schemeA_extended_coverage_at_50` is an availability-style diagnostic, not Top-50 address accuracy.',
              '- The expanded cases are train-only and must not be used to retune the frozen dev/holdout split.']
    (out/'REPORT.md').write_text('\n'.join(report)+'\n')
    print(json.dumps({'status': manifest['status'], 'out': str(out), 'seconds': manifest['finished_seconds']}), flush=True)

if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
