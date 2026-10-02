"""Plan B step 7 (mechanism cross-check, not primary evidence): recompute the
52 old active dev cases under selector v2's formula and compare v1 vs v2
rankings of the evidence candidates — in particular the 0xeabb case where v1's
recency-dominance lost a 2-in/72-day donor to a 1-in/recent one.

No model calls: only evidence-strength recomputation on the v1 evidence table
(.tmp/inbound_candidates_20261002.csv) + out_back counts from the ledger.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RUN = ROOT / 'artifacts/cert_v2_featfix_20261002T000000Z'
OUT = ROOT / 'artifacts/expanded_dev_B_20261002'
HUB_THR = 109.0

cand = pd.read_csv(ROOT / '.tmp/inbound_candidates_20261002.csv')
led = pd.read_parquet(RUN / 'canonical_ledger.parquet',
                      columns=['from_address', 'to_address', 'block_timestamp',
                               'transaction_hash'])
led['block_timestamp'] = pd.to_datetime(led.block_timestamp, utc=True)
hist = led[led.block_timestamp < pd.Timestamp('2022-07-01', tz='UTC')].copy()
hist['snd'] = hist.from_address.fillna('')
outdeg = hist.groupby('snd').to_address.nunique()
CUT = pd.Timestamp('2022-07-01', tz='UTC')

# v1 formula
cand['strength_v1'] = (np.log1p(cand.n_in) * np.exp(-cand.days_back / 30.0)
                       - 0.5 * cand.addr.map(lambda a: 1.0 if float(outdeg.get(a, 0)) > HUB_THR else 0.0))
# v2 needs n_out_back ages; recompute from ledger per (addr, case wallet)
# case -> wallet is recoverable from the frozen dev shard (14-char suffix)
import pickle
with (RUN / 'shards' / '2022-07-01.pkl').open('rb') as f:
    rows = pickle.load(f)
dev = {r['case_id'][-14:]: r['wallet'] for r in rows if r['split'] == 'dev' and r['active']}

# pre-group once: sender -> its rows, and sender+wallet -> outgoing-back rows
# (8.5M-row full scans per candidate are infeasible; step5b uses the same pattern)
snd_groups = {w: g for w, g in hist.groupby('snd', sort=False)}
back_groups = {}
for s, g in snd_groups.items():
    for w, sub in g.groupby('to_address', sort=False):
        back_groups[(s, w)] = sub

def v2_rows(g, w):
    outs = []
    for row in g.itertuples(index=False):
        back = back_groups.get((row.addr, w))
        n_out = int(len(back)) if back is not None else 0
        days_out = (max(0.0, (CUT - back.block_timestamp.max()).total_seconds() / 86400.0)
                    if n_out else 365.0)
        hub = 1.0 if float(outdeg.get(row.addr, 0)) > HUB_THR else 0.0
        s = (1.0 * np.log1p(row.n_in) * np.exp(-row.days_back / 30.0)
             + 0.5 * np.exp(-row.days_back / 30.0)
             + 1.0 * np.log1p(n_out) * np.exp(-days_out / 30.0)
             - 0.5 * hub)
        outs.append((row.addr, s, row.strength_v1, row.n_in, row.days_back, n_out))
    return outs

res = []
for case, g in cand.groupby('case'):
    if case not in dev:
        continue
    ranked_v2 = sorted(v2_rows(g, dev[case]), key=lambda t: (-t[1], t[0]))
    ranked_v1 = sorted(((r.addr, r.strength_v1) for r in g.itertuples(index=False)),
                       key=lambda t: (-t[1], t[0]))
    for i, (a, s2, s1, n_in, db, n_out) in enumerate(ranked_v2):
        j = [x[0] for x in ranked_v1].index(a)
        res.append({'case': case, 'addr': a, 'rank_v2': i + 1, 'rank_v1': j + 1,
                    'strength_v2': round(s2, 4), 'strength_v1': round(s1, 4),
                    'n_in': n_in, 'days_in': db, 'n_out_back': n_out})
df = pd.DataFrame(res)
(out := OUT / 'selector_v2').mkdir(exist_ok=True, parents=True)
df.to_csv(out / 'old52_v1_vs_v2_ranks.csv', index=False)

# the 0xeabb case
eabb = df[df.addr.str.startswith('0xeabb')] if len(df) else df
summary = {
    'n_cases_compared': int(df.case.nunique()), 'n_candidates': len(df),
    'rank_changed': int((df['rank_v2'] != df['rank_v1']).sum()),
    'max_rank_jump_up': int((df['rank_v1'] - df['rank_v2']).max()),
    'eabb_rows': eabb.to_dict('records') if len(eabb) else [],
}
(out / 'old52_mechanism_check.json').write_text(json.dumps(summary, indent=2, default=str) + '\n')
print(json.dumps({k: summary[k] for k in ['n_cases_compared', 'n_candidates',
                                          'rank_changed', 'max_rank_jump_up']}), flush=True)
if len(eabb):
    print(json.dumps(summary['eabb_rows'][:2]), flush=True)
