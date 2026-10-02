#!/usr/bin/env python3
"""Fixed-pool event-certificate repair for the Typed Temporal Motif Retriever.

This run is train/dev only.  It physically reads only the 2022-03..2022-07
offline partitions; the frozen 2022-08 holdout partition is not opened.
All features are recomputed with block_timestamp < cutoff.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import pickle
import random
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
ART = ROOT / 'artifacts'
SRC = ART / 'offline_chain_events_v1_20260929_full'
CASES_CSV = ART / 'candidate_openworld_temporal_baselines_full_20260930T085705Z' / 'cases_train_dev_with_expansion.csv'
MOTIF_CACHE = ART / 'motif_gated_full_20260930T190500Z' / 'motif_cases.pkl'
GM_CACHE = ART / 'graphmixer_full_v1' / 'feature_cache.pkl'
TGN_CACHE = ART / 'typed_tgn_full_20260930T173000Z' / 'tgn_cases.pkl'
MOTIF_MODEL = ART / 'motif_source_ablation_20260930T194000Z' / 'direct_global' / 'model.pt'
LEGACY_MOTIF_MODEL = ART / 'motif_gated_full_20260930T190500Z' / 'motif_gated_retriever_v1.pt'
GM_MODEL = ART / 'graphmixer_full_v1' / 'graphmixer_v1.pt'

TAU_DAYS = 90.0
MAX_PATH_PEERS = 100
MAX_PEER_EVENTS_PER_CAND = 30
MAX_W_EVENTS_PER_PEER = 30
MAX_WALLET_TOKENS = 50
MAX_TOKEN_EVENTS_PER_ACTOR = 20
MAX_CERTS_PER_PAIR = 2
MAX_TRAIN_CERT_PAIRS_PER_CASE = 25

OLD_DIRECT_IDX = list(range(0, 8))
OLD_MOTIF_IDX = list(range(8, 14))
OLD_GLOBAL_IDX = list(range(14, 20))
OLD_BASE_IDX = OLD_DIRECT_IDX + OLD_GLOBAL_IDX

OLD_FEATS = [
    'is_own', 'log_cnt', 'last_decay', 'log_in_cnt', 'bidir',
    'log_value_repeat', 'pair_mean_log_value_raw', 'log_failed_cnt',
    'log_key_n_proxy', 'motif_w_max_proxy', 'motif_w_sum_proxy', 'motif_recency_proxy',
    'log_co_overlap_proxy', 'motif_order_frac_proxy',
    'log_gcnt', 'log_rcnt30', 'log_rcnt7', 'burst', 'log_age', 'ecosystem_proxy',
]
CERT_FEATS = [
    'cert_valid_any',
    'cert_path_tx_n_log', 'cert_path_peer_n_log', 'cert_path_recent_weight',
    'cert_path_span_days_log',
    'cert_wedge_token_n_log', 'cert_wedge_tx_n_log', 'cert_wedge_recent_weight',
    'cert_repeat_tx_n_log', 'cert_repeat_recent_weight', 'cert_bidir',
    'pair_log_value_mean_offset', 'pair_exact_value_repeat_log',
    'pair_failed_frac', 'pair_internal_frac', 'pair_trace_depth_mean',
    'pair_token_out_frac', 'pair_token_in_frac', 'pair_token_signed_balance',
    'wallet_burst_7_30', 'candidate_burst_7_30', 'candidate_hub_degree_log',
]


def norm_addr(x) -> str:
    if pd.isna(x):
        return ''
    return str(x).strip().lower()


def event_id(row) -> str:
    # transaction_hash + family + event index + endpoints + asset context is the
    # closest offline event identity available in this extract.  target_address is
    # deliberately excluded so the same chain event is not counted once per target.
    parts = [
        norm_addr(getattr(row, 'transaction_hash', '')),
        str(getattr(row, 'event_family', '') or ''),
        str(getattr(row, 'event_index', '')),
        norm_addr(getattr(row, 'from_address', '')),
        norm_addr(getattr(row, 'to_address', '')),
        norm_addr(getattr(row, 'token_contract_address', '')),
        str(getattr(row, 'value_lossless', '') or ''),
        str(getattr(row, 'quantity', '') or ''),
    ]
    return hashlib.sha1('|'.join(parts).encode()).hexdigest()[:24]


def trace_depth(x) -> float:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0.0
    s = str(x).strip()
    if not s or s == '[]':
        return 0.0
    # trace_address_json looks like [0,0,1].  Parsing via JSON is safer than
    # counting commas because malformed values simply become zero.
    try:
        v = json.loads(s)
        return float(len(v)) if isinstance(v, list) else 0.0
    except Exception:
        return 0.0


def schema_audit(out: Path) -> dict:
    wanted = [
        'target_address', 'counterparty_address', 'direction', 'event_family',
        'block_timestamp', 'block_number', 'transaction_index', 'transaction_hash',
        'event_index', 'from_address', 'to_address', 'value_lossless', 'quantity',
        'token_contract_address', 'trace_address_json', 'error', 'receipt_status',
        'receipt_contract_address', 'input', 'nonce', 'gas_used',
    ]
    parts = {}
    for p in sorted(SRC.glob('2022-0[3-7].parquet')):
        schema = pq.read_schema(p)
        meta = pq.ParquetFile(p).metadata
        parts[p.name] = {
            'rows': meta.num_rows,
            'columns': schema.names,
            'missing_wanted': [c for c in wanted if c not in schema.names],
        }
    audit = {
        'status': 'complete',
        'partitions_physically_read_for_schema': sorted(parts),
        'august_partition_opened': False,
        'availability': {
            'input_4byte_selector': False,
            'nonce': False,
            'gas_used': False,
            'protocol_label': False,
            'token_decimals': False,
            'trace_depth_proxy': True,
            'receipt_status': True,
            'value_lossless': True,
            'token_contract_address': True,
        },
        'semantic_notes': [
            'shared token/contract context is a wedge, not a directed two-hop path',
            'token raw quantity is not compared across tokens because trusted decimals are absent',
            'same-transaction supports are deduplicated by transaction_hash',
        ],
        'partitions': parts,
    }
    (out / 'schema_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    return audit


def load_events() -> pd.DataFrame:
    cols = [
        'target_address', 'counterparty_address', 'direction', 'event_family',
        'block_timestamp', 'block_number', 'transaction_index', 'transaction_hash',
        'event_index', 'from_address', 'to_address', 'value_lossless', 'quantity',
        'token_contract_address', 'trace_address_json', 'error', 'receipt_status',
    ]
    frames = []
    for p in sorted(SRC.glob('2022-0[3-7].parquet')):
        schema_names = pq.read_schema(p).names
        use = [c for c in cols if c in schema_names]
        x = pd.read_parquet(p, columns=use)
        x['partition'] = p.stem
        frames.append(x)
        print(json.dumps({'loaded_partition': p.name, 'rows': len(x)}), flush=True)
    ev = pd.concat(frames, ignore_index=True)
    ev['block_timestamp'] = pd.to_datetime(ev['block_timestamp'], utc=True)
    for c in ['target_address', 'counterparty_address', 'direction', 'event_family',
              'transaction_hash', 'from_address', 'to_address', 'value_lossless',
              'quantity', 'token_contract_address', 'error']:
        if c in ev.columns:
            ev[c] = ev[c].map(norm_addr) if c.endswith('address') else ev[c].fillna('').astype(str)
    ev['event_id'] = [event_id(r) for r in ev.itertuples(index=False)]
    ev['trace_depth'] = ev['trace_address_json'].map(trace_depth)
    ev = ev.sort_values(['block_timestamp', 'block_number', 'transaction_index', 'event_index'],
                        kind='mergesort').reset_index(drop=True)
    return ev


def load_cache(path: Path) -> Dict[str, dict]:
    with path.open('rb') as f:
        rows = pickle.load(f)
    return {r['case_id']: r for r in rows}


def build_fixed_dataset(out: Path) -> List[dict]:
    motif = load_cache(MOTIF_CACHE)
    gm = load_cache(GM_CACHE)
    tgn = load_cache(TGN_CACHE)
    case_ids = sorted(set(motif) & set(gm) & set(tgn))
    fixed = []
    pool_rows = []
    for case_id in case_ids:
        m, g, n = motif[case_id], gm[case_id], tgn[case_id]
        assert (m['wallet'], m['cutoff'], m.get('target', '')) == (g['wallet'], g['cutoff'], g.get('target', ''))
        assert (m['wallet'], m['cutoff'], m.get('target', '')) == (n['wallet'], n['cutoff'], n.get('target', ''))
        sets = [set(m['pool']), set(g['pool']), set(n['pool'])]
        common = sets[0] & sets[1] & sets[2]
        # deterministic order: the motif pool's source order, restricted to the common set
        pool = [c for c in m['pool'] if c in common]
        mi = {c: i for i, c in enumerate(m['pool'])}
        gi = {c: i for i, c in enumerate(g['pool'])}
        ti = {c: i for i, c in enumerate(n['pool'])}
        midx = np.array([mi[c] for c in pool], dtype=np.int64)
        gidx = np.array([gi[c] for c in pool], dtype=np.int64)
        tidx = np.array([ti[c] for c in pool], dtype=np.int64)
        target = m.get('target', '') or ''
        y_idx = pool.index(target) if target and target in common else -1
        rec = {
            'case_id': case_id, 'split': m['split'], 'cutoff': m['cutoff'],
            'wallet': m['wallet'], 'active': int(m['active']), 'target': target,
            'visibility': m.get('visibility', ''), 'pool': pool,
            'X_old': m['X'][midx].astype(np.float32),
            'ctx': np.asarray(m['ctx'], dtype=np.float32),
            'gm_cand_bucket': g['cand_bucket'][gidx].astype(np.int64),
            'gm_cand_feats': g['cand_feats'][gidx].astype(np.float32),
            'gm_seq': g['seq'],
            'y_idx': y_idx,
            'source_pool_sizes': {'motif': len(m['pool']), 'graphmixer': len(g['pool']), 'typed_tgn': len(n['pool'])},
        }
        fixed.append(rec)
        for rank0, c in enumerate(pool):
            pool_rows.append({
                'case_id': case_id, 'cutoff': m['cutoff'], 'wallet': m['wallet'],
                'candidate': c, 'pool_rank': rank0 + 1,
                'in_motif_pool': True, 'in_graphmixer_pool': True, 'in_typed_tgn_pool': True,
                'is_target': bool(target and c == target),
            })
    fixed.sort(key=lambda r: (r['cutoff'], r['split'], r['case_id']))
    pd.DataFrame(pool_rows).to_parquet(out / 'fixed_candidate_pools.parquet', index=False)
    pd.DataFrame([{k: v for k, v in r.items() if k not in ('pool', 'X_old', 'ctx', 'gm_cand_bucket', 'gm_cand_feats', 'gm_seq')}
                  for r in fixed]).to_csv(out / 'fixed_cases.csv', index=False)
    with (out / 'fixed_dataset_base.pkl').open('wb') as f:
        pickle.dump(fixed, f, protocol=4)
    support = [int(r['active'] and r['y_idx'] >= 0) for r in fixed if r['split'] == 'dev']
    active = [int(r['active']) for r in fixed if r['split'] == 'dev']
    audit = {
        'cases': len(fixed),
        'dev_cases': len(support),
        'dev_active': sum(active),
        'dev_active_pool_support': sum(support),
        'dev_active_pool_support_rate': sum(support) / max(1, sum(active)),
        'pool_rule': 'per-case intersection of the three existing as-of candidate pools; no target injection',
        'candidate_rows': len(pool_rows),
    }
    (out / 'fixed_pool_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps({'fixed_dataset': audit}), flush=True)
    return fixed


def compact_event(r) -> dict:
    return {
        'event_id': r.event_id,
        'transaction_hash': norm_addr(r.transaction_hash),
        'block_timestamp': str(pd.Timestamp(r.block_timestamp).isoformat()),
        'block_number': int(r.block_number),
        'transaction_index': int(r.transaction_index),
        'event_index': int(r.event_index) if not pd.isna(r.event_index) else None,
        'event_family': str(r.event_family or ''),
        'from_address': norm_addr(r.from_address),
        'to_address': norm_addr(r.to_address),
        'token_contract_address': norm_addr(r.token_contract_address),
        'direction': str(r.direction or ''),
        'value_lossless': str(r.value_lossless or ''),
        'receipt_status': None if pd.isna(r.receipt_status) else int(r.receipt_status),
        'trace_depth': float(r.trace_depth),
    }


def make_cert(case: dict, candidate: str, motif_type: str, events: List[dict], roles: List[str]) -> dict:
    txs = [e['transaction_hash'] for e in events]
    return {
        'case_id': case['case_id'], 'cutoff': case['cutoff'], 'wallet': case['wallet'],
        'candidate': candidate, 'motif_type': motif_type,
        'events': events, 'roles': roles,
        'transaction_hashes': sorted(set(txs)),
        'same_transaction_support': len(set(txs)) == 1,
        'certificate_version': 'event_cert_v1',
    }


def add_cert(cert_sink: List[dict], pair_cert_counts: Counter, case: dict,
             candidate: str, motif_type: str, events: List[dict], roles: List[str],
             emitted_counts: Counter = None):
    key = (case['case_id'], candidate)
    # Dev gets bounded certificates for every supported pair.  Train keeps target
    # pairs plus the first few supported pairs per case to control artifact size.
    if case['split'] != 'dev' and candidate != case.get('target', ''):
        if pair_cert_counts[case['case_id']] >= MAX_TRAIN_CERT_PAIRS_PER_CASE:
            return
        pair_cert_counts[case['case_id']] += 1
    # O(1) per-pair cap; the old list scan was quadratic in the number of certs.
    if emitted_counts is None:
        emitted_counts = Counter()
        for c in cert_sink:
            emitted_counts[(c['case_id'], c['candidate'])] += 1
    if emitted_counts[key] >= MAX_CERTS_PER_PAIR:
        return
    emitted_counts[key] += 1
    cert_sink.append(make_cert(case, candidate, motif_type, events, roles))


def actor_event_maps(hist: pd.DataFrame, actors: set) -> Dict[str, List[dict]]:
    sub = hist[hist.target_address.isin(actors)]
    out = defaultdict(list)
    for r in sub.itertuples(index=False):
        out[r.target_address].append({
            'ts': pd.Timestamp(r.block_timestamp), 'cp': r.counterparty_address,
            'direction': r.direction, 'family': r.event_family, 'token': r.token_contract_address,
            'tx': r.transaction_hash, 'event_id': r.event_id,
            'value': r.value_lossless, 'receipt': r.receipt_status,
            'depth': float(r.trace_depth), 'raw': r,
        })
    for v in out.values():
        v.sort(key=lambda e: (e['ts'], e['tx'], e['event_id']))
    return out


def compute_case_cert_features(case: dict, hist: pd.DataFrame, actor_events: Dict[str, List[dict]],
                               global_stats: dict, cert_sink: List[dict],
                               pair_cert_counts: Counter,
                               emitted_counts: Counter = None) -> Tuple[np.ndarray, dict]:
    if emitted_counts is None:
        emitted_counts = Counter()
    cutoff = pd.Timestamp(case['cutoff'], tz='UTC')
    w = case['wallet']
    pool = case['pool']
    pool_set = set(pool)
    n = len(pool)
    F = np.zeros((n, len(CERT_FEATS)), dtype=np.float32)
    c_index = {c: i for i, c in enumerate(pool)}
    wevs = actor_events.get(w, [])
    outgoing = [e for e in wevs if e['direction'] == 'outgoing']
    incoming = [e for e in wevs if e['direction'] == 'incoming']
    wallet_values = []
    for e in outgoing:
        try:
            v = float(e['value'] or 0)
            if v > 0:
                wallet_values.append(math.log10(v))
        except Exception:
            pass
    wallet_value_mean = float(np.mean(wallet_values)) if wallet_values else 0.0
    w7 = sum(e['ts'] >= cutoff - pd.Timedelta(days=7) for e in outgoing)
    w30 = sum(e['ts'] >= cutoff - pd.Timedelta(days=30) for e in outgoing)
    wallet_burst = min(10.0, (w7 + 0.5) / (w30 / 4.0 + 0.5)) / 10.0

    # Direct pair evidence and chain-specific pair behavior.
    direct_acc = {}
    for e in wevs:
        c = e['cp']
        if c not in pool_set:
            continue
        a = direct_acc.setdefault(c, {
            'out_n': 0, 'in_n': 0, 'txs': set(), 'recent_w': 0.0,
            'events': [], 'values': [], 'value_counts': Counter(), 'failed': 0,
            'internal': 0, 'depth': [], 'token_out': 0, 'token_in': 0,
        })
        if e['direction'] == 'outgoing':
            a['out_n'] += 1
            if e['family'] == 'token_transfer':
                a['token_out'] += 1
        elif e['direction'] == 'incoming':
            a['in_n'] += 1
            if e['family'] == 'token_transfer':
                a['token_in'] += 1
        a['txs'].add(e['tx'])
        age = max(0.0, (cutoff - e['ts']).total_seconds() / 86400.0)
        a['recent_w'] += math.exp(-age / TAU_DAYS)
        if len(a['events']) < 8:
            a['events'].append(e)
        try:
            v = float(e['value'] or 0)
            if v > 0:
                a['values'].append(math.log10(v))
                a['value_counts'][str(e['value'])] += 1
        except Exception:
            pass
        if e['receipt'] is not None and not pd.isna(e['receipt']) and int(e['receipt']) == 0:
            a['failed'] += 1
        if e['family'] == 'internal_trace':
            a['internal'] += 1
            a['depth'].append(e['depth'])

    # Directed wallet -> peer -> candidate paths.  Only target-centric outgoing
    # peer rows can serve as the second hop in this offline extract.
    w_by_peer = defaultdict(list)
    for e in outgoing:
        if e['cp'] and e['cp'] != w:
            w_by_peer[e['cp']].append(e)
    path_acc = defaultdict(lambda: {'txs': set(), 'peers': set(), 'recent_w': 0.0,
                                    'first': None, 'last': None})
    peer_items = sorted(w_by_peer.items(),
                        key=lambda kv: (-len(kv[1]), max(e['ts'] for e in kv[1]), kv[0]))[:MAX_PATH_PEERS]
    for peer, evs1 in peer_items:
        pevs = [e for e in actor_events.get(peer, []) if e['direction'] == 'outgoing' and e['cp'] in pool_set]
        if not pevs:
            continue
        evs1 = evs1[-MAX_W_EVENTS_PER_PEER:]
        ts1 = [e['ts'] for e in evs1]
        by_c = defaultdict(list)
        for e2 in pevs:
            by_c[e2['cp']].append(e2)
        for c, evs2 in by_c.items():
            for e2 in evs2[-MAX_PEER_EVENTS_PER_CAND:]:
                j = bisect.bisect_left(ts1, e2['ts']) - 1
                if j < 0:
                    continue
                e1 = evs1[j]
                if e1['tx'] == e2['tx']:
                    continue
                a = path_acc[c]
                a['txs'].add(e2['tx'])
                a['peers'].add(peer)
                age = max(0.0, (cutoff - e2['ts']).total_seconds() / 86400.0)
                gap = max(0.0, (e2['ts'] - e1['ts']).total_seconds() / 86400.0)
                a['recent_w'] += math.exp(-age / TAU_DAYS) * math.exp(-min(gap, 90.0) / 90.0)
                a['first'] = e1['ts'] if a['first'] is None else min(a['first'], e1['ts'])
                a['last'] = e2['ts'] if a['last'] is None else max(a['last'], e2['ts'])
                if len(a['txs']) <= MAX_CERTS_PER_PAIR:
                    add_cert(cert_sink, pair_cert_counts, case, c, 'wallet_to_peer_to_candidate',
                             [compact_event(e1['raw']), compact_event(e2['raw'])],
                             ['wallet_to_peer', 'peer_to_candidate'], emitted_counts)

    # Shared token-contract wedges (common context, explicitly not a directed path).
    wallet_tokens = defaultdict(list)
    for e in wevs:
        if e['family'] == 'token_transfer' and e['token']:
            wallet_tokens[e['token']].append(e)
    token_weights = {tok: sum(math.exp(-max(0.0, (cutoff - e['ts']).total_seconds() / 86400.0) / TAU_DAYS)
                              for e in evs) for tok, evs in wallet_tokens.items()}
    top_tokens = [tok for tok, _ in sorted(token_weights.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_WALLET_TOKENS]]
    pool_token_to_cands = defaultdict(list)
    cand_token_events = {}
    for c in pool:
        tok_map = defaultdict(list)
        for e in actor_events.get(c, []):
            if e['family'] == 'token_transfer' and e['token']:
                tok_map[e['token']].append(e)
        cand_token_events[c] = tok_map
        for tok in tok_map:
            pool_token_to_cands[tok].append(c)
    wedge_acc = defaultdict(lambda: {'txs': set(), 'tokens': set(), 'recent_w': 0.0})
    for tok in top_tokens:
        wtok = wallet_tokens[tok][-MAX_TOKEN_EVENTS_PER_ACTOR:]
        for c in pool_token_to_cands.get(tok, []):
            if c == w:
                continue
            ctok = cand_token_events[c].get(tok, [])[-MAX_TOKEN_EVENTS_PER_ACTOR:]
            if not ctok:
                continue
            a = wedge_acc[c]
            a['tokens'].add(tok)
            # Count transaction-level common context, bounded per pair.
            for ew in wtok[:3]:
                for ec in ctok[:3]:
                    if ew['tx'] == ec['tx']:
                        continue
                    a['txs'].add((ew['tx'], ec['tx']))
                    recent = max(ew['ts'], ec['ts'])
                    age = max(0.0, (cutoff - recent).total_seconds() / 86400.0)
                    a['recent_w'] += math.exp(-age / TAU_DAYS) / 9.0
                    if len(a['txs']) <= MAX_CERTS_PER_PAIR:
                        add_cert(cert_sink, pair_cert_counts, case, c, 'shared_token_contract_wedge',
                                 [compact_event(ew['raw']), compact_event(ec['raw'])],
                                 ['wallet_token_context', 'candidate_token_context'], emitted_counts)

    # Fill aligned features.
    for c, i in c_index.items():
        d = direct_acc.get(c, {'out_n': 0, 'in_n': 0, 'txs': set(), 'recent_w': 0.0,
                               'events': [], 'values': [], 'value_counts': Counter(),
                               'failed': 0, 'internal': 0, 'depth': [],
                               'token_out': 0, 'token_in': 0})
        p = path_acc.get(c, {'txs': set(), 'peers': set(), 'recent_w': 0.0, 'first': None, 'last': None})
        g = wedge_acc.get(c, {'txs': set(), 'tokens': set(), 'recent_w': 0.0})
        repeat_tx = len(d['txs'])
        if repeat_tx >= 2 and d['events']:
            # A bounded direct-repeat certificate; distinct transaction hashes are
            # mandatory for repeat support.
            evs = []
            seen_tx = set()
            for e in d['events']:
                if e['tx'] not in seen_tx:
                    evs.append(compact_event(e['raw'])); seen_tx.add(e['tx'])
                if len(evs) == 2:
                    break
            if len(evs) == 2:
                add_cert(cert_sink, pair_cert_counts, case, c, 'repeat_direct_interaction',
                         evs, ['wallet_candidate_direct_1', 'wallet_candidate_direct_2'], emitted_counts)
        pair_n = d['out_n'] + d['in_n']
        value_mean = float(np.mean(d['values'])) if d['values'] else 0.0
        value_repeat = max(d['value_counts'].values()) if d['value_counts'] else 0
        span = 0.0
        if p['first'] is not None and p['last'] is not None:
            span = max(0.0, (p['last'] - p['first']).total_seconds() / 86400.0)
        cert_any = bool(p['txs'] or g['txs'] or repeat_tx >= 2)
        cand30 = global_stats['rcnt30'].get(c, 0)
        cand7 = global_stats['rcnt7'].get(c, 0)
        cand_burst = min(10.0, (cand7 + 0.5) / (cand30 / 4.0 + 0.5)) / 10.0
        F[i] = np.array([
            1.0 if cert_any else 0.0,
            math.log1p(len(p['txs'])), math.log1p(len(p['peers'])), min(p['recent_w'], 20.0) / 20.0,
            math.log1p(span),
            math.log1p(len(g['tokens'])), math.log1p(len(g['txs'])), min(g['recent_w'], 20.0) / 20.0,
            math.log1p(repeat_tx), min(d['recent_w'], 20.0) / 20.0,
            1.0 if d['out_n'] and d['in_n'] else 0.0,
            abs(value_mean - wallet_value_mean) / 25.0 if d['values'] else 0.0,
            math.log1p(value_repeat),
            d['failed'] / max(1, pair_n),
            d['internal'] / max(1, pair_n),
            float(np.mean(d['depth'])) / 10.0 if d['depth'] else 0.0,
            d['token_out'] / max(1, pair_n), d['token_in'] / max(1, pair_n),
            (d['token_out'] - d['token_in']) / max(1, pair_n),
            wallet_burst, cand_burst,
            math.log1p(global_stats['hub_degree'].get(c, 0)),
        ], dtype=np.float32)
    cert_summary = {
        'candidates': n,
        'unsupported_candidates': int(np.sum(F[:, 0] <= 0)),
        'supported_candidates': int(np.sum(F[:, 0] > 0)),
        'path_supported_candidates': int(np.sum(F[:, 1] > 0)),
        'wedge_supported_candidates': int(np.sum(F[:, 5] > 0)),
        'repeat_supported_candidates': int(np.sum(F[:, 8] > 0)),
    }
    return F, cert_summary


def extract_cert_features(ev: pd.DataFrame, cases: List[dict], out: Path) -> List[dict]:
    cert_path = out / 'cert_features_by_case.pkl'
    if cert_path.exists():
        with cert_path.open('rb') as f:
            return pickle.load(f)
    cert_sink: List[dict] = []
    pair_cert_counts = Counter()
    emitted_counts = Counter()
    case_cert_summary = []
    by_cutoff = defaultdict(list)
    for c in cases:
        by_cutoff[c['cutoff']].append(c)
    enriched = []
    for cutoff in sorted(by_cutoff):
        t0 = time.time()
        group = by_cutoff[cutoff]
        t = pd.Timestamp(cutoff, tz='UTC')
        hist = ev[ev.block_timestamp < t]
        wallets = {c['wallet'] for c in group}
        candidates = set()
        for c in group:
            candidates.update(c['pool'])
        # First pass over wallet rows finds path peers; actor maps are then built
        # for wallets, candidates, and those peers.
        wsub = hist[hist.target_address.isin(wallets)]
        peers = set(wsub.loc[wsub.direction.eq('outgoing'), 'counterparty_address'])
        actors = wallets | candidates | peers
        amap = actor_event_maps(hist, actors)
        outgoing_hist = hist[hist.direction.eq('outgoing')]
        gcnt = Counter(outgoing_hist.counterparty_address)
        recent30 = outgoing_hist[outgoing_hist.block_timestamp >= t - pd.Timedelta(days=30)]
        recent7 = outgoing_hist[outgoing_hist.block_timestamp >= t - pd.Timedelta(days=7)]
        rcnt30 = Counter(recent30.counterparty_address)
        rcnt7 = Counter(recent7.counterparty_address)
        hub_degree = Counter()
        for c, nuniq in outgoing_hist.groupby('counterparty_address').target_address.nunique().items():
            hub_degree[c] = int(nuniq)
        global_stats = {'gcnt': gcnt, 'rcnt30': rcnt30, 'rcnt7': rcnt7, 'hub_degree': hub_degree}
        for c in group:
            Fcert, summ = compute_case_cert_features(c, hist, amap, global_stats,
                                                     cert_sink, pair_cert_counts,
                                                     emitted_counts)
            c = dict(c)
            c['X_cert'] = Fcert
            c['cert_summary'] = summ
            enriched.append(c)
            summ.update({'case_id': c['case_id'], 'cutoff': cutoff, 'split': c['split'], 'wallet': c['wallet']})
            case_cert_summary.append(summ)
        print(json.dumps({'cert_cutoff': cutoff, 'cases': len(group), 'hist_rows': len(hist),
                          'actors': len(actors), 'seconds': round(time.time() - t0, 1)}), flush=True)
    with cert_path.open('wb') as f:
        pickle.dump(enriched, f, protocol=4)
    pd.DataFrame(case_cert_summary).to_csv(out / 'certificate_feature_summary_by_case.csv', index=False)
    with (out / 'event_certificates.jsonl').open('w') as f:
        for c in cert_sink:
            f.write(json.dumps(c, sort_keys=True) + '\n')
    return enriched
