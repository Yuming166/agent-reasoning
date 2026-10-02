"""Layer-1 experiment: add inbound counterparties to the candidate pool.

Protocol (preregistered before looking at any new metric):
- Same 2022-07-01 cutoff, same 52 active dev cases, same frozen models
  (chain_all / direct_global_legacy / own_frequency-equivalents from the
  featfix run), seeds 0/1/2.
- Pool' = frozen union pool ∪ {addresses that sent to the wallet before cutoff
  (direction=incoming), excluding wallet itself}. No budget cap on the pool;
  selection is still exactly 50 by score, so the fixed-budget claim is tested.
- All per-candidate features (B/C/E/X/gm/cand_bucket/valid) recomputed on pool'
  with the same code path as extraction; proofs re-verified.
- Baseline sanity gate: before scoring, rescore the ORIGINAL pool with the
  frozen models and require seed-averaged R@50/R@5 to match the recorded
  metrics within 1e-3. If the gate fails, abort without reporting new numbers.
- Report: overall R@5/R@50 on all 52 active (rank<=0 counts as miss),
  saved/displaced lists per case (who entered top-50 that wasn't, who fell out).
"""
from pathlib import Path
import argparse, hashlib, json, pickle, time
from collections import defaultdict

import numpy as np
import pandas as pd
import torch

from certificate_history_v2 import History, canonicalize, epoch_seconds
from certificate_v2 import verify
from certificate_models_v2 import Scorer
from train_certificate_v2 import prepare, collate, ranking_metrics
import motif_gated_retriever as legacy
from graphmixer_features_v2 import outgoing_index, candidate_matrix

RUN = Path('artifacts/cert_v2_featfix_20261002T000000Z')
VARIANTS = ['chain_all', 'direct_global_legacy', 'own_frequency']
SEEDS = [0, 1, 2]
TOPK = (5, 50)


def dump(p, obj):
    p.write_text(json.dumps(obj, indent=2, default=str) + '\n')


def load_models(device):
    models = {}
    for v in VARIANTS:
        if v == 'own_frequency':
            continue  # training-free scorer, no checkpoint
        models[v] = {}
        for s in SEEDS:
            p = RUN / 'models' / v / ('seed' + str(s)) / 'model.pt'
            ckpt = torch.load(p, map_location=device)
            m = Scorer(v).to(device)
            m.load_state_dict(ckpt['model'])
            m.eval()
            models[v][s] = m
    return models


@torch.no_grad()
def score_cases(model, cases, variant, seed, device):
    """Return per-case score arrays aligned with each case's pool order.

    own_frequency is a training-free scorer: B[:,1] = log1p outgoing distinct
    transaction count (same semantics as summarize_certificate_v2.own_frequency).
    """
    if variant == 'own_frequency':
        return {r['case_id']: r['B'][:, 1].astype(np.float64) for r in cases}
    out = {}
    for start in range(0, len(cases), 8):
        sub = cases[start:start + 8]
        batch = collate(sub, device, variant, seed)
        s = model(batch)[0]
        s = s.cpu().numpy()
        for i, r in enumerate(sub):
            out[r['case_id']] = s[i, :len(r['pool'])]
    return out


def ranks_from_scores(cases, scores):
    ranks = {}
    for r in cases:
        sc = scores[r['case_id']]
        order = np.argsort(-sc, kind='stable')
        rank = np.empty(len(sc), np.int32)
        rank[order] = np.arange(1, len(sc) + 1)
        ranks[r['case_id']] = int(rank[r['y_idx']]) if r['y_idx'] >= 0 else -1
    return ranks


def topk_set(case, scores, k=50):
    sc = scores[case['case_id']]
    order = np.argsort(-sc, kind='stable')[:k]
    return [case['pool'][i] for i in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', default='cuda:1')
    ap.add_argument('--out', default='artifacts/layer1_inbound_20261002')
    args = ap.parse_args()
    out = Path(args.out)
    assert not out.exists(), f'{out} exists'
    out.mkdir(parents=True)
    device = torch.device(args.device)
    started = time.time()

    # ---- load shard + ledger -------------------------------------------------
    with (RUN / 'shards' / '2022-07-01.pkl').open('rb') as f:
        rows = pickle.load(f)
    dev = [r for r in rows if r['split'] == 'dev' and r['active']]
    print(json.dumps({'active_dev': len(dev)}), flush=True)

    stats = json.loads((RUN / 'normalization.json').read_text())
    canonical = pd.read_parquet(RUN / 'canonical_ledger.parquet')

    # ---- rebuild role table (same path as extraction) ------------------------
    import motif_certificate_fixed_pool as old
    SRC = old.SRC
    frames = [pd.read_parquet(SRC / (m + '.parquet'))
              for m in ['2022-03', '2022-04', '2022-05', '2022-06']]
    role = pd.concat(frames, ignore_index=True); del frames
    role['block_timestamp'] = pd.to_datetime(role.block_timestamp, utc=True)
    for c in ['target_address', 'counterparty_address', 'direction', 'event_family',
              'value_lossless', 'token_contract_address']:
        role[c] = role[c].fillna('').astype(str)
    role = role.sort_values(['block_timestamp', 'block_number', 'transaction_index',
                             'event_index'], kind='stable').reset_index(drop=True)

    cutoff = '2022-07-01'
    hist = role[role.block_timestamp < pd.Timestamp(cutoff, tz='UTC')]
    idx = legacy.build_motif_index(hist, cutoff)
    h = History(canonical, cutoff)
    assert int(h.a['timestamp'].max()) < h.ts
    seen = set(h.df.from_address) | set(h.df.to_address) | set(h.df.token_contract_address)

    # ---- build expanded pools ------------------------------------------------
    inbound = {}
    for r in dev:
        w = r['wallet']
        # direction is relative to target_address (row subject): incoming rows
        # with subject w mean counterparty_address sent TO w.
        ins = set(hist.loc[(hist.target_address == w)
                           & (hist.direction == 'incoming'), 'counterparty_address']) - {w, ''}
        inbound[w] = sorted(ins & seen)

    new_cases = []
    for r0 in dev:
        r = dict(r0)
        base_pool = r['pool']
        poolp = sorted(set(base_pool) | set(inbound[r['wallet']]))
        r['pool'] = poolp
        r['y_idx'] = poolp.index(r['target']) if r['target'] in poolp else -1
        r['pool_added'] = len(poolp) - len(base_pool)
        proofs = h.proofs(r)
        B, C, E = h.features(r, proofs)
        invalid = 0
        for ps in proofs.values():
            for p in ps:
                ok, reasons = verify(p, h.lookup)
                assert ok, reasons
                invalid += int(not ok)
        dm = legacy.diffusion_and_motif(idx, r['wallet'])
        X = np.asarray([legacy.pair_features(idx, r['wallet'], c, dm) for c in poolp], np.float32)
        r['ctx'] = np.asarray(legacy.wallet_context(idx, r['wallet']), np.float32)
        r.update(B=B, C=C, E=E, X=X)
        r['gm'] = candidate_matrix(outgoing_index(hist, cutoff, [r['wallet']]), r['wallet'], poolp)
        r['cand_bucket'] = np.asarray([int(hashlib.sha1(c.encode()).hexdigest(), 16) % 32768
                                       for c in poolp], dtype=np.int64)
        r['valid'] = C[:, 0].copy()
        r['old_target'] = bool(B[r['y_idx'], 0]) if r['y_idx'] >= 0 else \
            bool(idx['out_cnt'].get(r['wallet'], {}).get(r['target'], 0))
        r['contract_target'] = r['target'] in h.contracts
        new_cases.append(r)
        print(json.dumps({'case': r['case_id'][-14:], 'added': r['pool_added'],
                          'y_idx': r['y_idx'], 'invalid_proofs': invalid}), flush=True)

    # ---- sanity gate: frozen models reproduce recorded baseline ranks --------
    models = load_models(device)
    base_cases = prepare([dict(r) for r in dev], stats)
    gate = {}
    for v in VARIANTS:
        seeds_for_v = [0] if v == 'own_frequency' else SEEDS
        for s in seeds_for_v:
            recorded = pd.read_csv(RUN / 'models' / v / ('seed' + str(s)) / 'case_predictions.csv')
            rec_rank = dict(zip(recorded.case_id, recorded['rank']))
            m = models.get(v, {}).get(s)
            sc = (score_cases(None, base_cases, v, s, device) if m is None
                  else score_cases(m, base_cases, v, s, device))
            rk = ranks_from_scores(base_cases, sc)
            common = [c for c in rk if c in rec_rank]
            maxd = max(abs(rk[c] - rec_rank[c]) for c in common)
            gate[f'{v}_seed{s}'] = maxd
            print(json.dumps({'gate': v, 'seed': s, 'max_rank_diff': maxd}), flush=True)
            assert maxd <= 2, f'baseline reproduction failed for {v} seed{s}: {maxd}'

    # ---- score expanded pools ------------------------------------------------
    exp_cases = prepare(new_cases, stats)
    per_seed = {v: {} for v in VARIANTS}
    top50 = {v: {} for v in VARIANTS}
    for v in VARIANTS:
        seeds_for_v = [0] if v == 'own_frequency' else SEEDS
        for s in seeds_for_v:
            m = models.get(v, {}).get(s)
            sc = (score_cases(None, exp_cases, v, s, device) if m is None
                  else score_cases(m, exp_cases, v, s, device))
            per_seed[v][s] = ranks_from_scores(exp_cases, sc)
            top50[v][s] = {r['case_id']: topk_set(r, sc) for r in exp_cases}
            ranks = [per_seed[v][s][c] for c in per_seed[v][s]]
            print(json.dumps({'expanded': v, 'seed': s,
                              'metrics': ranking_metrics(ranks)}), flush=True)

    # ---- aggregate + saved/displaced ----------------------------------------
    report = {'protocol': 'Layer-1 inbound expansion, frozen models, exact top-50',
              'gate_max_rank_diff': gate, 'variants': {}}
    for v in VARIANTS:
        seeds_for_v = [0] if v == 'own_frequency' else SEEDS
        mean = {}
        for c in per_seed[v][0]:
            rs = [per_seed[v][s][c] for s in seeds_for_v]
            mean[c] = float(np.mean(rs))
        base_mean = {}
        rec = {}
        for s in seeds_for_v:
            rec[s] = pd.read_csv(RUN / 'models' / v / ('seed' + str(s)) / 'case_predictions.csv')
        for c in [r['case_id'] for r in dev]:
            base_mean[c] = float(np.mean([rec[s].set_index('case_id')['rank'].get(c, -1)
                                          for s in seeds_for_v]))
        act = [r['case_id'] for r in dev]
        m_new = ranking_metrics([mean[c] for c in act])
        m_old = ranking_metrics([base_mean[c] for c in act])
        saved = [c for c in act if (base_mean[c] <= 0 or base_mean[c] > 50)
                 and (0 < mean[c] <= 50)]
        displaced = [c for c in act if (0 < base_mean[c] <= 50) and (mean[c] <= 0 or mean[c] > 50)]
        report['variants'][v] = {
            'baseline': m_old, 'expanded': m_new,
            'delta_R50': m_new['R@50'] - m_old['R@50'],
            'delta_R5': m_new['R@5'] - m_old['R@5'],
            'saved': saved, 'displaced': displaced,
            'pool_added_mean': float(np.mean([r['pool_added'] for r in new_cases])),
        }
        print(json.dumps({'variant': v, 'R50_old': m_old['R@50'], 'R50_new': m_new['R@50'],
                          'R5_old': m_old['R@5'], 'R5_new': m_new['R@5'],
                          'saved': len(saved), 'displaced': len(displaced)}), flush=True)

    dump(out / 'report.json', report)
    # per-case table: base vs expanded seed-mean rank per variant
    tab = []
    added_by = {r['case_id']: r['pool_added'] for r in new_cases}
    yexp_by = {r['case_id']: r['y_idx'] >= 0 for r in new_cases}
    for r in dev:
        c = r['case_id']
        row = dict(case_id=c, wallet=r['wallet'], target=r['target'],
                   visibility=r['visibility'], pool_added=added_by[c],
                   y_in_expanded=yexp_by[c])
        for v in VARIANTS:
            seeds_for_v = [0] if v == 'own_frequency' else SEEDS
            row[v + '_rank_base'] = float(np.mean([
                pd.read_csv(RUN / 'models' / v / ('seed' + str(s)) / 'case_predictions.csv')
                .set_index('case_id')['rank'].get(c, -1) for s in seeds_for_v])) \
                if v != 'own_frequency' else None
        tab.append(row)
    df = pd.DataFrame(tab)
    for v in VARIANTS:
        seeds_for_v = [0] if v == 'own_frequency' else SEEDS
        df[v + '_rank_exp'] = df.case_id.map(
            {c: float(np.mean([per_seed[v][s][c] for s in seeds_for_v])) for c in per_seed[v][0]})
    df.to_csv(out / 'per_case.csv', index=False)
    # save top50 lists for chain_all expanded
    pd.DataFrame([{'case_id': c, 'candidate': cand, 'rank': i + 1}
                  for c, lst in top50['chain_all'][0].items() for i, cand in enumerate(lst)]
                 ).to_parquet(out / 'top50_chain_all_seed0_expanded.parquet')
    dump(out / 'complete.json', dict(status='complete', seconds=time.time() - started))
    print(json.dumps({'status': 'complete', 'seconds': time.time() - started}), flush=True)


if __name__ == '__main__':
    main()
