"""Plan B step 2: build 150 new dev cases — labels, three-source union pool, seq.

Follows notes/expanded_dev_protocol_20261002.md sections 3-4.
Label semantics verified on the 52 old active dev cases (attempted first
qualifying outgoing external counterparty in [07-01, 07-08): 52/52 match).
Each pool source uses its own as-of construction, exactly as the 2300-case run:
- motif pool:  motif_gated_retriever.build_pool on build_motif_index(role-months < cutoff)
- gm pool:     graphmixer_train.case_pool on base.build_temporal_index(outgoing external... < cutoff)
- tgn pool:    typed_tgn.make_pool on the same base temporal index
Output: parts/2022-07-01.newcases.pkl with {case_id, wallet, cutoff, split='dev',
active, target, visibility, pool, y_idx, seq, source_sizes}.
"""
from pathlib import Path
import json, math, pickle, sys, time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC = ROOT / 'artifacts/offline_chain_events_v1_20260929_full'
OUT = ROOT / 'artifacts/expanded_dev_B_20261002'
sys.path.insert(0, str(ROOT / 'research/candidate_baselines'))
import motif_gated_retriever as legacy
import graphmixer_train as gmt
import run_openworld_diffusion_baseline as base
import typed_tgn as tgn

CUTOFF = '2022-07-01'
ZERO = '0x' + '0' * 40
HIST_COLS = base.HIST_COLS

def dump(p, obj):
    tmp = Path(str(p) + '.tmp.' + str(__import__('os').getpid()))
    tmp.write_text(json.dumps(obj, indent=2, default=str) + '\n')
    tmp.rename(p)

t0 = time.time()
sel = pd.read_csv(OUT / 'selection/selected_wallets.csv', dtype={'wallet': str})
wallets = sel.wallet.tolist()
assert len(wallets) == 150 and len(set(wallets)) == 150
wset = set(wallets)

# ---------- events: role table (all families, for motif + seq) ----------
role_cols = ['target_address', 'counterparty_address', 'direction', 'event_family',
             'block_timestamp', 'block_number', 'transaction_index', 'transaction_hash',
             'event_index', 'token_contract_address', 'value_lossless']
frames = []
for m in ['2022-03', '2022-04', '2022-05', '2022-06']:
    frames.append(pd.read_parquet(SRC / f'{m}.parquet', columns=role_cols))
role = pd.concat(frames, ignore_index=True); del frames
role['block_timestamp'] = pd.to_datetime(role.block_timestamp, utc=True)
for c in ['target_address', 'counterparty_address', 'direction', 'event_family',
          'transaction_hash', 'token_contract_address']:
    role[c] = role[c].fillna('').astype(str).str.lower()
role = role.sort_values(['block_timestamp', 'block_number', 'transaction_index',
                         'event_index'], kind='mergesort').reset_index(drop=True)
print(json.dumps({'role_rows': len(role), 'secs': round(time.time() - t0, 1)}), flush=True)

# ---------- gm/tgn event table: outgoing-only, base.load_events semantics ----------
gcols = [c for c in base.HIST_COLS]
gframes = []
for m in ['2022-03', '2022-04', '2022-05', '2022-06']:
    schema = sorted(pd.read_parquet(SRC / f'{m}.parquet').columns) if False else gcols
    use = [c for c in gcols if c in schema]
    x = pd.read_parquet(SRC / f'{m}.parquet', columns=use)
    x['block_timestamp'] = pd.to_datetime(x['block_timestamp'], utc=True)
    for c in ['target_address', 'counterparty_address', 'transaction_hash',
              'token_contract_address', 'event_family', 'direction']:
        x[c] = base.norm_series(x[c])
    x = x[(x.direction == 'outgoing') & x.counterparty_address.ne('')].copy()
    gframes.append(x)
gev = pd.concat(gframes, ignore_index=True); del gframes
sort_cols = [c for c in ['block_number', 'transaction_index', 'event_index',
                         'transaction_hash'] if c in gev]
gev = gev.sort_values(sort_cols, kind='mergesort').reset_index(drop=True)
print(json.dumps({'gev_rows': len(gev), 'secs': round(time.time() - t0, 1)}), flush=True)

# ---------- labels (attempted first qualifying) ----------
# July + August windows loaded separately (label-only; never enters history
# indices, which stay strictly < cutoff).
LCOLS = ['target_address', 'counterparty_address', 'direction', 'event_family',
         'block_timestamp', 'block_number', 'transaction_index', 'transaction_hash',
         'event_index']
lframes = []
for m in ['2022-07', '2022-08']:
    lframes.append(pd.read_parquet(SRC / f'{m}.parquet', columns=LCOLS))
lwin = pd.concat(lframes, ignore_index=True); del lframes
lwin['block_timestamp'] = pd.to_datetime(lwin.block_timestamp, utc=True)
for c in ['target_address', 'counterparty_address', 'transaction_hash']:
    lwin[c] = lwin[c].fillna('').astype(str).str.lower()

cut = pd.Timestamp(CUTOFF, tz='UTC'); end = cut + pd.Timedelta(days=7)
q = lwin[(lwin.direction == 'outgoing') & (lwin.event_family == 'external_tx')
         & (lwin.counterparty_address != '') & (lwin.counterparty_address != ZERO)]
win = q[(q.block_timestamp >= cut) & (q.block_timestamp < end)
        & q.target_address.isin(wset)]
win = win.sort_values(['target_address', 'block_number', 'transaction_index',
                       'event_index', 'transaction_hash'], kind='mergesort')
first = win.drop_duplicates('target_address').set_index('target_address')

cases = []
meta = []
for w in wallets:
    y = first.counterparty_address.loc[w] if w in first.index else ''
    active = int(bool(y))
    cases.append({'case_id': 'devx_2022-07-01_' + w, 'wallet': w, 'cutoff': CUTOFF,
                  'split': 'dev', 'active': active, 'target': str(y)})
print(json.dumps({'active_new': sum(c['active'] for c in cases)}), flush=True)

# ---------- as-of indices (once) ----------
gm_index = base.build_temporal_index(gev[gev.block_timestamp < cut], CUTOFF)
motif_hist = role[role.block_timestamp < cut]
motif_index = legacy.build_motif_index(motif_hist, CUTOFF)
print(json.dumps({'indices_built': True, 'secs': round(time.time() - t0, 1)}), flush=True)

# ---------- seq per wallet (wallet-level, pool-independent) ----------
seqs = gmt.build_wallet_sequences(gev[gev.block_timestamp < cut], CUTOFF)

# ---------- pools ----------
rows = []
for c in cases:
    w = c['wallet']
    dm = legacy.diffusion_and_motif(motif_index, w)
    p_motif = legacy.build_pool(motif_index, w, dm)
    p_gm = gmt.case_pool(gm_index, w, CUTOFF)
    p_tgn = tgn.make_pool(gm_index, w)
    pool = sorted(set(p_motif) | set(p_gm) | set(p_tgn))
    y = c['target']
    y_idx = pool.index(y) if y and y in pool else -1
    if y:
        vis = ('own_seen' if y in gm_index['by_wallet_counter'].get(w, Counter())
               else ('global_seen' if y in gm_index['global_counter'] else 'open_world'))
    else:
        vis = 'none'
    s = np.zeros((gmt.SEQ_LEN, 6), dtype=np.int64)
    sq = seqs.get(w, [])
    if sq:
        arr = np.array(sq, dtype=np.int64)
        s[gmt.SEQ_LEN - len(arr):] = arr
    r = dict(c)
    r.update(visibility=vis, pool=pool, y_idx=y_idx, seq=s,
             source_sizes=[len(p_motif), len(p_gm), len(p_tgn)])
    rows.append(r)
    meta.append({'case_id': r['case_id'], 'wallet': w, 'active': r['active'],
                 'target': y, 'visibility': vis, 'pool': len(pool),
                 'y_idx': y_idx, 'motif': len(p_motif), 'gm': len(p_gm),
                 'tgn': len(p_tgn),
                 'target_in_gm_global': bool(y and y in gm_index['global_counter'])})
    print(json.dumps(meta[-1]), flush=True)

(OUT / 'parts').mkdir(exist_ok=True)
with (OUT / 'parts' / '2022-07-01.newcases.pkl').open('wb') as f:
    pickle.dump(rows, f, protocol=4)
pd.DataFrame(meta).to_csv(OUT / 'parts' / 'case_meta.csv', index=False)
support = [r for r in cases if r['active'] and any(r['target'] == x['target'] for x in cases)]
n_active = sum(c['active'] for c in cases)
n_support = sum(1 for r in rows if r['active'] and r['y_idx'] >= 0)
audit = {'cases': len(rows), 'active': n_active, 'supported': n_support,
         'support_rate': n_support / max(1, n_active),
         'pool_rule': 'sorted union of motif/graphmixer/typed_tgn as-of pools; no target injection',
         'label_rule': 'attempted first qualifying outgoing external in [07-01,07-08), verified 52/52 on old active dev',
         'secs': round(time.time() - t0, 1)}
dump(OUT / 'parts' / 'build_audit.json', audit)
print(json.dumps(audit), flush=True)
