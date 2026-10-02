"""Plan B step 5b (FIXED): selector v2 (direction-symmetric evidence strength) on the
150 new dev cases + gate + sensitivity on the 52 old cases.

Protocol notes/expanded_dev_protocol_20261002.md section 6 (formula frozen
before any new-dev metric was computed):

    strength_v2 = 1.0*log1p(n_in)*exp(-days_in/30)      # wallet <- candidate
                + 0.5*exp(-days_in/30)                  # recency bonus (cap 0.5)
                + 1.0*log1p(n_out_back)*exp(-days_out/30)  # wallet -> candidate loop
                - 0.5*hub(candidate)                    # global out-degree > 109

Qualification: candidates added by L1 inbound expansion (not in main pool),
n_in >= 1. Seats appended at ranks (51-k)..50, never inside top-5.
Primary: k=5 vs chain_all k=0 on R@50 (paired wallet-cluster bootstrap CI) and
R@5 (must not drop by more than 0.02). k in {0,1,2,3} sensitivity.
Evidence table built label-free from the ledger, as-of cutoff.
"""
from pathlib import Path
import json, pickle, sys, time

import numpy as np
import pandas as pd
import torch

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RUN = ROOT / 'artifacts/cert_v2_featfix_20261002T000000Z'
OUT = ROOT / 'artifacts/expanded_dev_B_20261002'
sys.path.insert(0, str(ROOT / 'research/candidate_baselines'))
from train_certificate_v2 import collate
from certificate_models_v2 import Scorer, ranking_metrics

SEEDS = [0, 1, 2]
KS = [0, 1, 2, 3, 5]
HUB_THR = 109.0  # frozen 99th pct of sender global out-degree (52-case audit)

def dump(p, obj):
    tmp = Path(str(p) + '.tmp.' + str(__import__('os').getpid()))
    tmp.write_text(json.dumps(obj, indent=2, default=str) + '\n')
    tmp.rename(p)

t0 = time.time()
device = torch.device('cuda:1')

# ---------------- evidence table (label-free, as-of) ----------------
led = pd.read_parquet(RUN / 'canonical_ledger.parquet',
                      columns=['from_address', 'to_address', 'block_timestamp',
                               'transaction_hash'])
led['block_timestamp'] = pd.to_datetime(led.block_timestamp, utc=True)
hist = led[led.block_timestamp < pd.Timestamp('2022-07-01', tz='UTC')].copy()
del led
hist['snd'] = hist.from_address.fillna('')
CUT = pd.Timestamp('2022-07-01', tz='UTC')

with (OUT / 'scores' / 'l1_case_index.pkl').open('rb') as f:
    case_idx = pickle.load(f)
with (OUT / 'scores' / 'l1_chain_all_scores.pkl').open('rb') as f:
    scores = pickle.load(f)  # case_id -> {seed: np.array aligned with pool}

# MAIN pools (protocol section 6: qualification = L1-added candidate that is
# not in the three-source union); c['pool'] in the index is the experiment pool
with (OUT / 'shards' / '2022-07-01.newdev_main.pkl').open('rb') as f:
    main_pools = {r['case_id']: set(r['pool']) for r in pickle.load(f)}

# group once: wallet -> inbound rows (avoids 129 full-table scans)
by_to = {w: g for w, g in hist.groupby('to_address', sort=False)}
snd_g = hist.groupby('snd', sort=False)
snd_groups = {w: g for w, g in snd_g}  # sender -> rows, reused for n_out_back

stats_rows = []
ev = {}
for c in case_idx:
    if not c['active']:
        continue
    w = c['wallet']; main_pool = main_pools[c['case_id']]
    ins = by_to.get(w)
    if ins is None or len(ins) == 0:
        ev[c['case_id']] = []
        continue
    g = ins.groupby('snd').agg(n=('transaction_hash', 'size'),
                               last=('block_timestamp', 'max')).reset_index()
    g = g[(g.snd != w) & (g.snd != '') & (~g.snd.isin(main_pool))]
    lst = []
    for row in g.itertuples(index=False):
        d = row.snd
        n_in = int(row.n)
        days_in = max(0.0, (CUT - row.last).total_seconds() / 86400.0)
        back = snd_groups.get(d)
        back = back[back.to_address == w] if back is not None else back
        n_out = int(len(back)) if back is not None else 0
        days_out = max(0.0, (CUT - back.block_timestamp.max()).total_seconds() / 86400.0) \
            if n_out else 365.0
        lst.append((d, n_in, days_in, n_out, days_out))
    ev[c['case_id']] = lst
    for (d, n_in, di, n_out, do) in lst:
        stats_rows.append({'case_id': c['case_id'], 'addr': d, 'n_in': n_in,
                           'days_in': round(di, 2), 'n_out_back': n_out,
                           'days_out': round(do, 2)})

# hub = candidate's global OUT-degree over sender rows (outgoing edges in ledger)
outdeg = hist.groupby('snd').to_address.nunique()

def strength(n_in, days_in, n_out, days_out, addr):
    hub = 1.0 if float(outdeg.get(addr, 0)) > HUB_THR else 0.0
    return (1.0 * np.log1p(n_in) * np.exp(-days_in / 30.0)
            + 0.5 * np.exp(-days_in / 30.0)
            + 1.0 * np.log1p(n_out) * np.exp(-days_out / 30.0)
            - 0.5 * hub)

ranked = {}
for cid, lst in ev.items():
    rows = sorted(((strength(ni, di, no, do_, a), a) for (a, ni, di, no, do_) in lst),
                  key=lambda t: (-t[0], t[1]))
    ranked[cid] = rows

# ---------------- seat mechanism ----------------
def choose(cid, pool, sc, k):
    q = [(st, a) for st, a in ranked.get(cid, []) if a in pool]
    seats = [a for _, a in q[:k]]
    seat_set = set(seats)
    rest = [i for i, a in enumerate(pool) if a not in seat_set]
    order = sorted(rest, key=lambda i: (-sc[i], i))
    return [pool[i] for i in order[:50 - k]] + seats

def topk_hits(k, topk):
    hits = []
    for c in case_idx:
        if not c['active']:
            continue
        cid = c['case_id']; pool = c['pool']
        hit_seeds = []
        for s in SEEDS:
            sc = scores[cid][s]
            ch = choose(cid, pool, sc, k)[:topk]
            hit_seeds.append(int(c['target'] in ch) if c['y_idx'] >= 0 else 0)
        hits.append(np.mean(hit_seeds))
    return float(np.mean(hits)), hits

(out := OUT / 'selector_v2_fixed').mkdir(exist_ok=True)
pd.DataFrame(stats_rows).to_csv(out / 'evidence_table.csv', index=False)
report = {'protocol': 'selector v2: direction-symmetric strength, k seats at tail',
          'formula': '1.0*log1p(n_in)*exp(-days_in/30) + 0.5*exp(-days_in/30) '
                     '+ 1.0*log1p(n_out)*exp(-days_out/30) - 0.5*hub(outdeg>109)',
          'hub_threshold': HUB_THR, 'n_cases': sum(1 for c in case_idx if c['active']),
          'qualified_mean': float(np.mean([len(ranked.get(c['case_id'], []))
                                           for c in case_idx if c['active']]))}
kres = {}
for k in KS:
    r50, h50 = topk_hits(k, 50)
    r5, _ = topk_hits(k, 5)
    kres[k] = {'R@50': r50, 'R@5': r5}
    report.setdefault('k', {})[k] = kres[k]
    print(json.dumps({'k': k, 'R@50': round(r50, 4), 'R@5': round(r5, 4)}), flush=True)

# per-case seed-averaged contributions for the paired bootstrap (k=5 vs k=0)
avg = {}
for c in case_idx:
    if not c['active']:
        continue
    cid = c['case_id']; pool = c['pool']
    h0 = np.mean([int(c['target'] in choose(cid, pool, scores[cid][s], 0)[:50])
                  for s in SEEDS]) if c['y_idx'] >= 0 else 0.
    h5 = np.mean([int(c['target'] in choose(cid, pool, scores[cid][s], 5)[:50])
                  for s in SEEDS]) if c['y_idx'] >= 0 else 0.
    g0 = np.mean([int(c['target'] in choose(cid, pool, scores[cid][s], 0)[:5])
                  for s in SEEDS]) if c['y_idx'] >= 0 else 0.
    g5 = np.mean([int(c['target'] in choose(cid, pool, scores[cid][s], 5)[:5])
                  for s in SEEDS]) if c['y_idx'] >= 0 else 0.
    avg[cid] = {'wallet': c['wallet'], 'R@50_k0': h0, 'R@50_k5': h5,
                'R@5_k0': g0, 'R@5_k5': g5}
adf = pd.DataFrame(avg).T.reset_index().rename(columns={'index': 'case_id'})
adf.to_csv(out / 'per_case_k5.csv', index=False)
rng = np.random.default_rng(20261002)
for metric, l, r in [('R@50', 'R@50_k5', 'R@50_k0'), ('R@5', 'R@5_k5', 'R@5_k0')]:
    d = adf[l] - adf[r]
    wallets = sorted(adf.wallet.unique())
    counts = np.array([(adf.wallet == w).sum() for w in wallets])
    draws = rng.integers(0, len(wallets), size=(2000, len(wallets)))
    totals = np.array([d[adf.wallet == w].sum() for w in wallets])
    sampled = totals[draws].sum(1) / counts[draws].sum(1)
    lo, hi = np.quantile(sampled, [.025, .975])
    report[f'paired_{metric}_k5_vs_k0'] = {
        'difference': float(d.mean()), 'ci_low': float(lo), 'ci_high': float(hi),
        'wallet_clusters': len(wallets), 'replicates': 2000}
    print(json.dumps({'metric': metric, 'diff': round(float(d.mean()), 4),
                      'ci': [round(float(lo), 4), round(float(hi), 4)]}), flush=True)

# saved/displaced at k=5
saved = [cid for cid in avg if avg[cid]['R@50_k5'] > 0 >= avg[cid]['R@50_k0']]
disp = [cid for cid in avg if avg[cid]['R@50_k0'] > 0 >= avg[cid]['R@50_k5']]
report['saved_k5'] = saved; report['displaced_k5'] = disp

# ---------------- gate: k=0 == raw chain_all R@50 ----------------
raw50 = float(np.mean([
    np.mean([int(c['target'] in [c['pool'][i] for i in
                np.argsort(-scores[c['case_id']][s], kind='stable')[:50]])
             for s in SEEDS]) if c['y_idx'] >= 0 else 0.
    for c in case_idx if c['active']]))
gate_pass = abs(raw50 - kres[0]['R@50']) < 1e-9
report['gate'] = {'raw_chain_R50': raw50, 'k0_R50': kres[0]['R@50'], 'pass': gate_pass}
assert gate_pass, 'selector gate failed'

dump(out / 'report.json', report)
dump(out / 'complete.json', dict(status='complete', secs=time.time() - t0))
print(json.dumps({'status': 'complete', 'secs': round(time.time() - t0, 1)}), flush=True)
