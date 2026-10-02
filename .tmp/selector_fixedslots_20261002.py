"""Unified 50-slot selector: fixed k evidence seats + (50-k) base seats.

Preregistered protocol (frozen 2026-10-02 before any metric was computed):
- Seat split: k seats to "evidence-qualified NEW candidates" ranked by evidence
  strength; 50-k seats to chain_all scores over the remaining pool.
- Evidence qualification (as-of cutoff, all auditable):
    a) inbound-only candidates (added by Layer-1 expansion) with n_in >= 1
    b) ranked by strength = log1p(n_in) * recency_decay - hub_penalty
       hub_penalty when the sender's global out-degree exceeds the 99th pct.
  The target never enters qualification: labels are untouched at build time.
- k sweep: 0 (baseline reproduction), 1, 2, 3, 5. All reported.
- Metrics: ALL-52 R@5/R@50 seed-averaged; saved/displaced lists per k.
- Gate: k=0 must reproduce recorded chain_all metrics exactly.
"""
from pathlib import Path
import argparse, hashlib, json, pickle, time
from collections import defaultdict

import numpy as np
import pandas as pd
import torch

from certificate_history_v2 import History
from certificate_models_v2 import Scorer
from train_certificate_v2 import prepare, collate, ranking_metrics
import motif_gated_retriever as legacy
from graphmixer_features_v2 import outgoing_index, candidate_matrix
from certificate_v2 import verify

RUN = Path('artifacts/cert_v2_featfix_20261002T000000Z')
SEEDS = [0, 1, 2]
KS = [0, 1, 2, 3, 5]
TOPK = (5, 50)
CUTOFF_TS = pd.Timestamp('2022-07-01', tz='UTC')


def dump(p, obj):
    p.write_text(json.dumps(obj, indent=2, default=str) + '\n')


def load_models(device):
    models = {}
    for s in SEEDS:
        p = RUN / 'models' / 'chain_all' / ('seed' + str(s)) / 'model.pt'
        ckpt = torch.load(p, map_location=device)
        m = Scorer('chain_all').to(device)
        m.load_state_dict(ckpt['model'])
        m.eval()
        models[s] = m
    return models


@torch.no_grad()
def chain_scores(model, cases, seed, device):
    out = {}
    for start in range(0, len(cases), 8):
        sub = cases[start:start + 8]
        batch = collate(sub, device, 'chain_all', seed)
        s = model(batch)[0].cpu().numpy()
        for i, r in enumerate(sub):
            out[r['case_id']] = s[i, :len(r['pool'])]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--device', default='cuda:1')
    ap.add_argument('--out', default='artifacts/selector_fixedslots_20261002')
    args = ap.parse_args()
    out = Path(args.out)
    assert not out.exists()
    out.mkdir(parents=True)
    device = torch.device(args.device)
    t0 = time.time()

    # reuse the audited inbound-candidate table (built pre-registration, labels untouched)
    cand = pd.read_csv('.tmp/inbound_candidates_20261002.csv')
    with (RUN / 'shards' / '2022-07-01.pkl').open('rb') as f:
        rows = pickle.load(f)
    dev = [r for r in rows if r['split'] == 'dev' and r['active']]
    stats = json.loads((RUN / 'normalization.json').read_text())

    # hub penalty table: sender global out-degree over the whole history
    led = pd.read_parquet(RUN / 'canonical_ledger.parquet',
                          columns=['from_address', 'to_address', 'block_timestamp'])
    led['block_timestamp'] = pd.to_datetime(led.block_timestamp, utc=True)
    hist = led[led.block_timestamp < CUTOFF_TS]
    outdeg = hist.groupby(hist.from_address.fillna('')).to_address.nunique()
    hub_thr = float(np.quantile(outdeg.values, 0.99))

    # evidence strength per (case, sender) — as-of, label-free
    ev = {}
    for (cid, a, n, db) in cand[['case', 'addr', 'n_in', 'days_back']].itertuples(index=False):
        hub = 1.0 if outdeg.get(a, 0) > hub_thr else 0.0
        rec = float(np.exp(-db / 30.0))
        strength = float(np.log1p(n)) * rec - 0.5 * hub
        ev.setdefault(cid, []).append((strength, a))
    for cid in ev:
        ev[cid].sort(key=lambda t: (-t[0], t[1]))

    models = load_models(device)

    # ---- per-cutoff shared inputs (built ONCE, outside the case loop) --------
    # role table -> motif index (same construction as Layer-1 experiment)
    import motif_gated_retriever as legacy
    import motif_certificate_fixed_pool as oldpool
    t_role = time.time()
    frames = [pd.read_parquet(oldpool.SRC / (m + '.parquet'))
              for m in ['2022-03', '2022-04', '2022-05', '2022-06']]
    role = pd.concat(frames, ignore_index=True); del frames
    role['block_timestamp'] = pd.to_datetime(role.block_timestamp, utc=True)
    for c in ['target_address', 'counterparty_address', 'direction', 'event_family',
              'value_lossless', 'token_contract_address']:
        role[c] = role[c].fillna('').astype(str)
    role = role.sort_values(['block_timestamp', 'block_number', 'transaction_index',
                             'event_index'], kind='stable').reset_index(drop=True)
    hist = role[role.block_timestamp < pd.Timestamp('2022-07-01', tz='UTC')]
    idx = legacy.build_motif_index(hist, '2022-07-01')
    gm_index = outgoing_index(hist, '2022-07-01', [r['wallet'] for r in dev])
    print(json.dumps({'shared_index_built': round(time.time() - t_role, 1)}), flush=True)

    # expand pool + recompute features exactly like the Layer-1 experiment
    # (score rows must align with pool rows; frozen shard arrays belong to the
    # old pool and cannot be reused)
    from certificate_history_v2 import canonicalize, epoch_seconds
    canonical = pd.read_parquet(RUN / 'canonical_ledger.parquet')
    canonical['timestamp'] = epoch_seconds(canonical['block_timestamp']).to_numpy()
    h = History(canonical, '2022-07-01')
    assert int(h.a['timestamp'].max()) < h.ts
    new_cases = []
    for r0 in dev:
        r = dict(r0)
        key = r['case_id'][-14:]
        ins = sorted(set(cand[cand.case == key].addr)) if (cand.case == key).any() else []
        poolp = sorted(set(r['pool']) | set(ins))
        r['pool'] = poolp
        r['y_idx'] = poolp.index(r['target']) if r['target'] in poolp else -1
        # seq is wallet-level (pool-independent) and required by prepare(); keep it.
        r.pop('B', None); r.pop('C', None); r.pop('E', None); r.pop('X', None)
        r.pop('gm', None); r.pop('cand_bucket', None); r.pop('ctx', None)
        proofs = h.proofs(r)
        B, C, E = h.features(r, proofs)
        for ps in proofs.values():
            for pr in ps:
                ok, _ = verify(pr, h.lookup)
                assert ok
        dm = legacy.diffusion_and_motif(idx, r['wallet'])
        X = np.asarray([legacy.pair_features(idx, r['wallet'], c, dm) for c in poolp], np.float32)
        r['ctx'] = np.asarray(legacy.wallet_context(idx, r['wallet']), np.float32)
        r.update(B=B, C=C, E=E, X=X)
        r['gm'] = candidate_matrix(gm_index, r['wallet'], poolp)
        r['cand_bucket'] = np.asarray([int(hashlib.sha1(c.encode()).hexdigest(), 16) % 32768
                                       for c in poolp], dtype=np.int64)
        new_cases.append(r)
        print(json.dumps({'feat': key, 'pool': len(poolp), 'y': r['y_idx']}), flush=True)
    exp_cases = prepare(new_cases, stats)

    # frozen chain_all scores on expanded pools
    sc_by_seed = {}
    for s in SEEDS:
        sc_by_seed[s] = chain_scores(models[s], exp_cases, s, device)

    report = {'protocol': 'fixed k evidence seats + (50-k) chain_all seats',
              'k': {}, 'gate': {}}
    per_case_rows = []
    for k in KS:
        agg = {}
        saved_disp = {'saved': set(), 'displaced': set()}
        for s in SEEDS:
            for r in exp_cases:
                cid = r['case_id']
                sc = sc_by_seed[s][cid]
                pool = r['pool']
                n = len(pool)
                # evidence seats: strongest k qualified (inbound-only, in pool)
                q = [(st, a) for st, a in ev.get(cid[-14:], []) if a in set(pool)]
                seats = [a for _, a in q[:k]]
                seat_set = set(seats)
                rest_idx = [i for i, a in enumerate(pool) if a not in seat_set]
                order = sorted(rest_idx, key=lambda i: (-sc[i], i))
                # evidence seats appended at ranks (51-k)..50, never inside top-5:
                # the base scorer owns ranks 1..(50-k) exactly as without the sweep.
                chosen = [pool[i] for i in order[:50 - k]] + seats
                chosen = chosen[:50]
                hit = int(r['target'] in chosen) if r['y_idx'] >= 0 else 0
                # also need base-only top50 for saved/displaced on k=0
                base_order = sorted(range(n), key=lambda i: (-sc[i], i))
                base50 = {pool[i] for i in base_order[:50]}
                if r['target'] in chosen and r['target'] not in base50 and r['y_idx'] >= 0:
                    saved_disp['saved'].add(cid)
                if r['target'] in base50 and r['target'] not in chosen:
                    saved_disp['displaced'].add(cid)
                agg.setdefault(cid, []).append(hit)
                if s == 0 and k == KS[-1]:
                    per_case_rows.append(dict(case_id=cid, k=k, hit=hit))
        r50 = float(np.mean([np.mean(v) for v in agg.values()]))
        # R@5 approximation: evidence seats displace top-5 only when k>=5;
        # for k<5 the top-5 of chain_all is untouched -> equals baseline R@5
        r5 = None
        report['k'][k] = {'R@50': r50, 'saved': sorted(saved_disp['saved']),
                          'displaced': sorted(saved_disp['displaced'])}
        print(json.dumps({'k': k, 'R@50': round(r50, 4),
                          'saved': len(saved_disp['saved']),
                          'displaced': len(saved_disp['displaced'])}), flush=True)

    # exact R@5: recompute top-5 hits for each k (evidence seats can push into top5 only via seat order)
    for k in KS:
        hits = []
        for s in SEEDS:
            for r in exp_cases:
                cid = r['case_id']
                sc = sc_by_seed[s][cid]
                pool = r['pool']
                q = [(st, a) for st, a in ev.get(cid[-14:], []) if a in pool]
                seats = [a for _, a in q[:k]]
                seat_set = set(seats)
                rest_idx = [i for i, a in enumerate(pool) if a not in seat_set]
                order = sorted(rest_idx, key=lambda i: (-sc[i], i))
                chosen = [pool[i] for i in order[:50 - k]] + seats
                top5 = chosen[:5]
                hits.append(int(r['target'] in top5) if r['y_idx'] >= 0 else 0)
        # hits currently per (seed,case) flattened; average per case over seeds
        n = len(exp_cases)
        per_case = [np.mean(hits[j::n]) for j in range(n)]
        report['k'][k]['R@5'] = float(np.mean(per_case))
        print(json.dumps({'k': k, 'R@5': round(report['k'][k]['R@5'], 4)}), flush=True)

    # gate: k=0 R@50 must equal the Layer-1 expanded-pool chain_all seed mean
    # (0.596154+0.615385+0.615385)/3 = 0.608974..., NOT the frozen-pool 32/52
    l1_expected = (0.5961538461538461 + 0.6153846153846154 + 0.6153846153846154) / 3
    recorded = report['k'][0]['R@50']
    assert abs(recorded - l1_expected) < 1e-6, f'gate failed: {recorded} vs {l1_expected}'
    report['gate'] = {'k0_R50': recorded, 'expected': l1_expected, 'pass': True}

    dump(out / 'report.json', report)
    pd.DataFrame(per_case_rows).to_csv(out / 'per_case_k.csv', index=False)
    dump(out / 'complete.json', dict(status='complete', seconds=time.time() - t0))
    print(json.dumps({'status': 'complete', 'seconds': time.time() - t0}), flush=True)


if __name__ == '__main__':
    main()
