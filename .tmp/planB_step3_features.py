"""Plan B step 3: features for the 150 new dev cases.

For every new case (protocol section 4-5):
- main pool rows: B/C/E from History on canonical_ledger (proofs verified), X
  (legacy pair_features), gm (candidate_matrix), ctx, cand_bucket (already have seq)
- L1 inbound expansion rows (EXPERIMENT pool, protocol section 4): main ∪ inbound
  counterparties; all feature blocks recomputed on the expanded pool.
Output: shards/2022-07-01.newdev_main.pkl (main pool) and
        shards/2022-07-01.newdev_l1.pkl (experiment pool).
History: canonical_ledger.parquet from the frozen run (epoch seconds asserted).
"""
from pathlib import Path
import hashlib, json, os, pickle, sys, time

import numpy as np
import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RUN = ROOT / 'artifacts/cert_v2_featfix_20261002T000000Z'
OUT = ROOT / 'artifacts/expanded_dev_B_20261002'
sys.path.insert(0, str(ROOT / 'research/candidate_baselines'))
from certificate_history_v2 import History, epoch_seconds, canonicalize
from certificate_v2 import verify
import motif_gated_retriever as legacy
from graphmixer_features_v2 import outgoing_index, candidate_matrix

CUTOFF = '2022-07-01'

def dump(p, obj):
    tmp = Path(str(p) + '.tmp.' + str(os.getpid()))
    tmp.write_text(json.dumps(obj, indent=2, default=str) + '\n')
    tmp.rename(p)

t0 = time.time()
with (OUT / 'parts' / '2022-07-01.newcases.pkl').open('rb') as f:
    base_cases = pickle.load(f)
n_active = sum(c['active'] for c in base_cases)
print(json.dumps({'cases': len(base_cases), 'active': n_active}), flush=True)

canonical = pd.read_parquet(RUN / 'canonical_ledger.parquet')
canonical['timestamp'] = epoch_seconds(canonical['block_timestamp']).to_numpy()
h = History(canonical, CUTOFF)
assert int(h.a['timestamp'].max()) < h.ts, 'history must end strictly before cutoff'
assert int(h.a['timestamp'].min()) > 1600000000, 'timestamps not epoch seconds'
seen = set(h.df.from_address) | set(h.df.to_address) | set(h.df.token_contract_address)
# any main-pool candidate not observed before cutoff breaks the no-injection audit
bad = sorted({c for r in base_cases for c in r['pool'] if c not in seen})
assert not bad, f'candidates not observed pre-cutoff: {bad[:5]}'
print(json.dumps({'history_rows': len(h.df), 'secs': round(time.time() - t0, 1)}), flush=True)

# role table for motif index (X features) — same construction as selector run
import motif_certificate_fixed_pool as oldpool
frames = [pd.read_parquet(oldpool.SRC / (m + '.parquet'))
          for m in ['2022-03', '2022-04', '2022-05', '2022-06']]
role = pd.concat(frames, ignore_index=True); del frames
role['block_timestamp'] = pd.to_datetime(role.block_timestamp, utc=True)
for c in ['target_address', 'counterparty_address', 'direction', 'event_family',
          'value_lossless', 'token_contract_address']:
    role[c] = role[c].fillna('').astype(str)
role = role.sort_values(['block_timestamp', 'block_number', 'transaction_index',
                         'event_index'], kind='stable').reset_index(drop=True)
hist_role = role[role.block_timestamp < pd.Timestamp(CUTOFF, tz='UTC')]
idx = legacy.build_motif_index(hist_role, CUTOFF)
del role, hist_role
print(json.dumps({'motif_index_built': True, 'secs': round(time.time() - t0, 1)}), flush=True)

# gm index over the 150 new wallets only — outgoing_index needs the role table
# (direction columns) rebuilt from the SRC month parquets
wallets = [c['wallet'] for c in base_cases]
rframes = [pd.read_parquet(oldpool.SRC / (m + '.parquet'),
           columns=['target_address', 'counterparty_address', 'direction', 'event_family',
                    'block_timestamp', 'token_contract_address'])
           for m in ['2022-03', '2022-04', '2022-05', '2022-06']]
grole = pd.concat(rframes, ignore_index=True)
grole['block_timestamp'] = pd.to_datetime(grole.block_timestamp, utc=True)
for c in ['target_address', 'counterparty_address', 'direction', 'event_family',
          'token_contract_address']:
    grole[c] = grole[c].fillna('').astype(str)
gm_index = outgoing_index(grole, CUTOFF, wallets)
del grole
print(json.dumps({'gm_index_built': True, 'secs': round(time.time() - t0, 1)}), flush=True)

# L1 inbound counterparties per wallet (as-of cutoff, event-table based)
ins_by_case = {}
qc = canonical  # columns include from_address/to_address/block_timestamp/timestamp
for c in base_cases:
    w = c['wallet']
    ins = set(qc.loc[(qc.to_address == w) & (qc.from_address != w), 'from_address'])
    ins &= seen  # only provable pre-cutoff addresses
    ins_by_case[c['case_id']] = sorted(ins - {''})
print(json.dumps({'inbound_done': True,
                  'mean_added': float(np.mean([len(v) for v in ins_by_case.values()]))}), flush=True)

def extract(r, pool):
    r = dict(r)
    r['pool'] = pool
    r['y_idx'] = pool.index(r['target']) if r['target'] in pool else -1
    for k in ('B', 'C', 'E', 'X', 'gm', 'ctx', 'cand_bucket', 'old_target',
              'contract_target'):
        r.pop(k, None)
    proofs = h.proofs(r)
    B, C, E = h.features(r, proofs)
    invalid = 0
    for ps in proofs.values():
        for pr in ps:
            ok, reasons = verify(pr, h.lookup)
            invalid += int(not ok)
            if not ok:
                raise AssertionError((r['case_id'], reasons))
    dm = legacy.diffusion_and_motif(idx, r['wallet'])
    X = np.asarray([legacy.pair_features(idx, r['wallet'], c, dm) for c in pool], np.float32)
    r['ctx'] = np.asarray(legacy.wallet_context(idx, r['wallet']), np.float32)
    r.update(B=B, C=C, E=E, X=X)
    r['gm'] = candidate_matrix(gm_index, r['wallet'], pool)
    r['cand_bucket'] = np.asarray([int(hashlib.sha1(c.encode()).hexdigest(), 16) % 32768
                                   for c in pool], dtype=np.int64)
    r['old_target'] = bool(B[r['y_idx'], 0]) if r['y_idx'] >= 0 else False
    r['contract_target'] = r['target'] in h.contracts
    return r, len(proofs)

main_rows = []
l1_rows = []
total_proofs = 0
for j, r0 in enumerate(base_cases):
    main_pool = r0['pool']
    r, npf = extract(r0, main_pool)
    main_rows.append(r); total_proofs += npf
    exp_pool = sorted(set(main_pool) | set(ins_by_case[r0['case_id']]))
    r2, _ = extract(r0, exp_pool)
    l1_rows.append(r2)
    if (j + 1) % 10 == 0:
        print(json.dumps({'done': j + 1, 'secs': round(time.time() - t0, 1)}), flush=True)

(OUT / 'shards').mkdir(exist_ok=True)
with (OUT / 'shards' / '2022-07-01.newdev_main.pkl').open('wb') as f:
    pickle.dump(main_rows, f, protocol=4)
with (OUT / 'shards' / '2022-07-01.newdev_l1.pkl').open('wb') as f:
    pickle.dump(l1_rows, f, protocol=4)
audit = {'cases': len(main_rows), 'invalid_proofs': 0, 'total_proofs': total_proofs,
         'main_pool_mean': float(np.mean([len(r['pool']) for r in main_rows])),
         'l1_pool_mean': float(np.mean([len(r['pool']) for r in l1_rows])),
         'supported_main': int(sum(1 for r in main_rows if r['active'] and r['y_idx'] >= 0)),
         'supported_l1': int(sum(1 for r in l1_rows if r['active'] and r['y_idx'] >= 0)),
         'secs': round(time.time() - t0, 1)}
dump(OUT / 'features_audit.json', audit)
print(json.dumps(audit), flush=True)
