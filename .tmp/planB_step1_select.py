"""Plan B step 1: deterministic stratified selection of 150 new dev wallets.

Implements notes/expanded_dev_protocol_20261002.md sections 2-3 exactly.
Also runs the leakage audit (overlap with 2150 train wallets and their
counterparty universe) required by section 1.
"""
from pathlib import Path
import hashlib, json

import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
SRC = ROOT / 'artifacts/offline_chain_events_v1_20260929_full'
OUT = ROOT / 'artifacts/expanded_dev_B_20261002' / 'selection'
ZERO = '0x' + '0' * 40

if OUT.exists():
    raise SystemExit(f'refusing to overwrite {OUT}')
OUT.mkdir(parents=True)

frames = []
for m in ['2022-06']:
    frames.append(pd.read_parquet(SRC / f'{m}.parquet',
        columns=['target_address', 'counterparty_address', 'direction', 'event_family',
                 'block_timestamp']))
ev = pd.concat(frames, ignore_index=True)
ev['block_timestamp'] = pd.to_datetime(ev.block_timestamp, utc=True)
for c in ['target_address', 'counterparty_address']:
    ev[c] = ev[c].fillna('').str.lower()
qual = ev[(ev.event_family == 'external_tx') & (ev.direction == 'outgoing')
          & (ev.counterparty_address != '') & (ev.counterparty_address != ZERO)]
cnt = qual.target_address.value_counts()
frame = cnt[cnt >= 10]

excluded = set(Path('/storage/gaoym/ex-graph-microtransaction-analysis/'
                    '.tmp/planB_excluded_wallets_20261002.txt').read_text().split())
excluded.discard('')
cands = sorted(w for w in frame.index if w not in excluded)

def bucket(n):
    if n < 20: return 'Q1'
    if n < 50: return 'Q2'
    if n < 150: return 'Q3'
    return 'Q4'

quota = {'Q1': 37, 'Q2': 38, 'Q3': 38, 'Q4': 37}
by_q = {q: [] for q in quota}
for w in cands:
    by_q[bucket(int(frame[w]))].append(w)
chosen = []
for q in sorted(quota):
    # deterministic: sha1 hex ascending after activity bucketing
    by_q[q].sort(key=lambda w: hashlib.sha1(w.encode()).hexdigest())
    take = by_q[q][:quota[q]]
    assert len(take) == quota[q], (q, len(take))
    chosen += [(w, int(frame[w]), q) for w in take]
chosen.sort(key=lambda t: t[0])
assert len(chosen) == 150 and len({w for w, _, _ in chosen}) == 150

sel = pd.DataFrame(chosen, columns=['wallet', 'june_events', 'activity_bucket'])
sel['case_id'] = ['devx_2022-07-01_' + w for w in sel.wallet]
sel['cutoff'] = '2022-07-01'
sel['split'] = 'dev'
sel.to_csv(OUT / 'selected_wallets.csv', index=False)

audit = {
    'sampling_frame_definition': 'June-2022 qualifying outgoing external >= 10, not in the 2300-case wallet set',
    'qualifying_rule': "event_family=='external_tx' & direction=='outgoing' & counterparty non-empty non-zero, lowercase",
    'frame_candidates': len(cands),
    'per_bucket_available': {q: len(by_q[q]) for q in quota},
    'quota': quota, 'selected': len(sel),
    'wallets_unique': int(sel.wallet.nunique()),
    'deterministic_rule': 'bucket by June count; order by sha1(wallet); take first N',
}
(OUT / 'selection_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
print(json.dumps(audit), flush=True)

# ---- leakage audit: overlap of selected wallets with 2150 train wallets ----
rows = []
for p in sorted((ROOT / 'artifacts/cert_v2_featfix_20261002T000000Z/shards').glob('*.pkl')):
    import pickle
    rows += pickle.load(open(p, 'rb'))
train_w = sorted({r['wallet'] for r in rows if r['split'] != 'dev'})
train_set = set(train_w)

# counterparty universe of train wallets, as-of their own cutoffs (approximate:
# use full 6-month panel; disclose the over-approximation)
if not (OUT / 'train_cp_universe.json').exists():
    frames = []
    for m in ['2022-03', '2022-04', '2022-05', '2022-06']:
        frames.append(pd.read_parquet(SRC / f'{m}.parquet',
            columns=['target_address', 'counterparty_address', 'direction', 'event_family']))
    ev6 = pd.concat(frames, ignore_index=True)
    ev6['target_address'] = ev6.target_address.fillna('').str.lower()
    ev6['counterparty_address'] = ev6.counterparty_address.fillna('').str.lower()
    tr = ev6[ev6.target_address.isin(train_set)
             & (ev6.direction == 'outgoing') & (ev6.counterparty_address != '')]
    uni = set(tr.counterparty_address.unique())
    uni.discard('')
    (OUT / 'train_cp_universe.json').write_text(json.dumps(sorted(uni)) + '\n')
else:
    uni = set(json.loads((OUT / 'train_cp_universe.json').read_text()))

hits_train = [w for w in sel.wallet if w in train_set]
hits_cp = [w for w in sel.wallet if w in uni]
leak = {
    'definition': 'leakage = case enters training (protocol section 1); overlap is disclosed, not excluded',
    'selected_in_train_wallets': len(hits_train),
    'selected_in_train_counterparty_universe': len(hits_cp),
    'train_wallets': len(train_set),
    'train_counterparty_universe': len(uni),
    'counterparty_universe_approximation': 'full Mar-Jun panel (over-approximates per-cutoff as-of views)',
    'overlap_wallet_list': hits_train,
}
(OUT / 'leakage_audit.json').write_text(json.dumps(leak, indent=2) + '\n')
print(json.dumps({k: leak[k] for k in ['selected_in_train_wallets',
                                       'selected_in_train_counterparty_universe',
                                       'train_counterparty_universe']}), flush=True)
(OUT / 'complete.json').write_text(json.dumps({'status': 'complete'}) + '\n')
