"""Plan B step 4: frozen-model scoring on the new dev + paired wallet bootstrap.

- main-pool shard: all 22 variants x seeds {0,1,2} + own_frequency (seed0)
- l1 shard: chain_all x 3 seeds (for the selector v2 base scores)
- normalization from the frozen run (train set unchanged => stats unchanged)
- paired bootstrap: wallet clusters, 2000 reps, rng 20261002, seed-averaged
  per-case contributions; pairs per protocol section 5.
Outputs: scores/*.parquet, metrics/metrics_by_variant.csv, metrics/paired_bootstrap.csv
"""
from pathlib import Path
import json, pickle, sys, time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RUN = ROOT / 'artifacts/cert_v2_featfix_20261002T000000Z'
OUT = ROOT / 'artifacts/expanded_dev_B_20261002'
sys.path.insert(0, str(ROOT / 'research/candidate_baselines'))
from certificate_models_v2 import Scorer, VARIANTS, ranking_metrics
from train_certificate_v2 import prepare, collate

SEEDS = [0, 1, 2]
CUTOFF = '2022-07-01'

def dump(p, obj):
    tmp = Path(str(p) + '.tmp.' + str(__import__('os').getpid()))
    tmp.write_text(json.dumps(obj, indent=2, default=str) + '\n')
    tmp.rename(p)

t0 = time.time()
device = torch.device('cuda:1')
stats = json.loads((RUN / 'normalization.json').read_text())

def load_shard(p):
    with p.open('rb') as f:
        return pickle.load(f)

def score_variant(model, cases, variant, seed):
    out = {}
    for start in range(0, len(cases), 8):
        sub = cases[start:start + 8]
        batch = collate(sub, device, variant, seed)
        with torch.no_grad():
            s = model(batch)[0].cpu().numpy()
        for i, r in enumerate(sub):
            out[r['case_id']] = s[i, :len(r['pool'])]
    return out

def rank_rows(cases, sc):
    rows = []
    for r in cases:
        s = sc[r['case_id']]
        order = np.argsort(-s, kind='stable')
        rank = np.empty(len(s), np.int32); rank[order] = np.arange(1, len(s) + 1)
        tr = int(rank[r['y_idx']]) if r['y_idx'] >= 0 else -1
        rows.append({'case_id': r['case_id'], 'wallet': r['wallet'],
                     'active': int(r['active']), 'supported': int(r['y_idx'] >= 0),
                     'visibility': r['visibility'], 'target': r['target'],
                     'old_target': int(r['old_target']),
                     'contract_target': int(r['contract_target']),
                     'rank': tr})
    return rows

def write_preds(path, cases, sc):
    writer = None
    for r in cases:
        s = sc[r['case_id']]
        order = np.argsort(-s, kind='stable')
        rank = np.empty(len(s), np.int32); rank[order] = np.arange(1, len(s) + 1)
        tab = pa.Table.from_pydict(dict(
            case_id=[r['case_id']] * len(s), candidate=r['pool'],
            pool_index=np.arange(len(s), dtype=np.int32),
            score=s.astype(np.float32), rank=rank))
        if writer is None:
            writer = pq.ParquetWriter(path, tab.schema, compression='zstd')
        writer.write_table(tab)
    writer.close()

def deep_case(r):
    """prepare() mutates B/C/E/X/gm/ctx/seq in place; the frozen shards must not
    be touched (step 5 and the retrain gate re-load them independently, but the
    in-memory arrays here would silently carry normalization across variants)."""
    r = dict(r)
    for k in ['B', 'C', 'E', 'X', 'gm', 'ctx', 'seq']:
        r[k] = r[k].copy()
    return r

# ---------------- main-pool scoring ----------------
main = load_shard(OUT / 'shards' / '2022-07-01.newdev_main.pkl')
main = [r for r in main if r['active']]
print(json.dumps({'main_active': len(main)}), flush=True)
prep = prepare([deep_case(r) for r in main], stats)

sc_dir = OUT / 'scores'; sc_dir.mkdir(exist_ok=True)
mrows = []
for v in VARIANTS:
    for s in SEEDS:
        model = Scorer(v).to(device)
        ckpt = torch.load(RUN / 'models' / v / f'seed{s}' / 'model.pt', map_location=device)
        model.load_state_dict(ckpt['model']); model.eval()
        sc = score_variant(model, prep, v, s)
        write_preds(sc_dir / f'{v}_seed{s}.parquet', prep, sc)
        for rr in rank_rows(prep, sc):
            rr.update(variant=v, seed=s)
            mrows.append(rr)
        del model
    print(json.dumps({'variant': v, 'secs': round(time.time() - t0, 1)}), flush=True)

# own_frequency (seed0): B[:,1] raw (unnormalized copy preserved in shard)
for r in prep:
    r['own_score'] = r['own_scores']  # prepare() copies B[:,1] into own_scores pre-norm
scf = {r['case_id']: r['own_scores'].astype(np.float64) for r in prep}
write_preds(sc_dir / 'own_frequency_seed0.parquet', prep, scf)
for rr in rank_rows(prep, scf):
    rr.update(variant='own_frequency', seed=0)
    mrows.append(rr)

f = pd.DataFrame(mrows)
act = f[f.active == 1]
met = []
for (v, s), g in act.groupby(['variant', 'seed']):
    r = {'variant': v, 'seed': s, 'n_active': len(g)}
    r.update(ranking_metrics(g['rank'].values))
    r['supported_only'] = json.dumps(ranking_metrics(g.loc[g.supported == 1, 'rank'].values))
    met.append(r)
mdf = pd.DataFrame(met).sort_values(['variant', 'seed'])
(met_dir := OUT / 'metrics').mkdir(exist_ok=True)
mdf.to_csv(met_dir / 'metrics_by_variant.csv', index=False)

# ---------------- paired wallet-cluster bootstrap ----------------
act = act.copy()
K = [5, 50, 100]
def contribution(rank, k):
    return float((rank > 0) and (rank <= k))
for k in K:
    act[f'R@{k}'] = [contribution(r, k) for r in act['rank']]
avg = act.groupby(['variant', 'case_id', 'wallet'], as_index=False)[[f'R@{k}' for k in K]].mean()
base_v = 'direct_global_legacy'
pairs = [(v, base_v) for v in sorted(set(avg.variant)) if v != base_v]
pairs += [(v, 'chain_all') for v in sorted(set(avg.variant))
          if v not in ('chain_all', base_v)]
pairs += [('chain_all', 'legacy_motif'), ('chain_all', 'graphmixer'),
          ('chain_all', 'own_frequency')]
rng = np.random.default_rng(20261002)
boot = []
for lhs, rhs in pairs:
    l = avg[avg.variant == lhs]; r = avg[avg.variant == rhs]
    j = l.merge(r, on=['case_id', 'wallet'], suffixes=('_l', '_r'), validate='one_to_one')
    if len(j) == 0:
        continue
    wallets = sorted(j.wallet.unique())
    counts = np.array([(j.wallet == w).sum() for w in wallets])
    draws = rng.integers(0, len(wallets), size=(2000, len(wallets)))
    for k in K:
        d = j[f'R@{k}_l'] - j[f'R@{k}_r']
        totals = np.array([d[j.wallet == w].sum() for w in wallets])
        sampled = totals[draws].sum(1) / counts[draws].sum(1)
        lo, hi = np.quantile(sampled, [.025, .975])
        boot.append(dict(lhs=lhs, rhs=rhs, metric=f'R@{k}', difference=float(d.mean()),
                         ci_low=float(lo), ci_high=float(hi),
                         wallet_clusters=len(wallets), active_cases=len(j),
                         replicates=2000))
pd.DataFrame(boot).to_csv(met_dir / 'paired_bootstrap.csv', index=False)

# ---------------- l1 shard chain_all (selector base) ----------------
l1 = load_shard(OUT / 'shards' / '2022-07-01.newdev_l1.pkl')
l1_act = [r for r in l1 if r['active']]
prep1 = prepare([deep_case(r) for r in l1_act], stats)
models = {}
for s in SEEDS:
    model = Scorer('chain_all').to(device)
    ckpt = torch.load(RUN / 'models' / 'chain_all' / f'seed{s}' / 'model.pt', map_location=device)
    model.load_state_dict(ckpt['model']); model.eval()
    models[s] = model
sc1 = {s: score_variant(models[s], prep1, 'chain_all', s) for s in SEEDS}
with (OUT / 'scores' / 'l1_chain_all_scores.pkl').open('wb') as f:
    pickle.dump({cid: {s: sc1[s][cid].astype(np.float32) for s in SEEDS}
                 for cid in sc1[0]}, f, protocol=4)
# pool order for the selector: l1 shard pools + case rows (pre-normalization fields kept)
with (OUT / 'scores' / 'l1_case_index.pkl').open('wb') as f:
    pickle.dump([{'case_id': r['case_id'], 'wallet': r['wallet'], 'target': r['target'],
                  'active': r['active'], 'y_idx': r['y_idx'], 'pool': r['pool']}
                 for r in l1_act], f, protocol=4)

summary = {'variants_scored': len(VARIANTS) * 3 + 1, 'main_active': len(main),
           'l1_active': len(l1_act), 'secs': round(time.time() - t0, 1)}
dump(OUT / 'metrics' / 'scoring_complete.json', summary)
print(json.dumps(summary), flush=True)
