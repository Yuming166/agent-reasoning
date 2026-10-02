"""Auditable full-dev summary; no network, holdout access or checkpoint selection."""
from pathlib import Path
from collections import Counter
import argparse, hashlib, json, pickle, shutil
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from certificate_models_v2 import VARIANTS, ranking_metrics
from train_certificate_v2 import dump

METRICS = ['R@5', 'R@50', 'R@100', 'MRR@5']

def contribution(rank, metric):
    r = np.asarray(rank)
    if metric == 'MRR@5':
        return np.where((r > 0) & (r <= 5), 1 / np.maximum(r, 1), 0.)
    return ((r > 0) & (r <= int(metric.split('@')[1]))).astype(float)

def own_frequency(root):
    out = root / 'models' / 'own_frequency' / 'seed0'
    if (out / 'complete.json').exists():
        return
    out.mkdir(parents=True, exist_ok=True)
    with (root / 'shards' / '2022-07-01.pkl').open('rb') as f:
        dev = [r for r in pickle.load(f) if r['split'] == 'dev']
    threshold = json.loads((root / 'normalization.json').read_text())['high_activity_threshold']
    rows = []; writer = None
    for r in dev:
        score = r['B'][:, 1]
        order = np.argsort(-score, kind='stable')
        rank = np.empty(len(score), np.int32); rank[order] = np.arange(1, len(score) + 1)
        row = {k: r[k] for k in ['case_id', 'wallet', 'cutoff', 'target', 'active', 'visibility', 'old_target', 'contract_target']}
        row.update(rank=int(rank[r['y_idx']]) if r['y_idx'] >= 0 else -1,
                   high_activity=bool(r['B'][0, 9] >= threshold), supported=r['y_idx'] >= 0,
                   seed=0, variant='own_frequency', top1=r['pool'][order[0]],
                   valid_fraction=float(r['C'][:, 0].mean()),
                   target_valid=bool(r['C'][r['y_idx'], 0]) if r['y_idx'] >= 0 else False)
        rows.append(row)
        tab = pa.Table.from_pydict(dict(case_id=[r['case_id']] * len(score), candidate=r['pool'],
                                       pool_index=np.arange(len(score), dtype=np.int32), score=score, rank=rank))
        if writer is None:
            writer = pq.ParquetWriter(out / 'predictions.parquet', tab.schema, compression='zstd')
        writer.write_table(tab)
    writer.close()
    frame = pd.DataFrame(rows); frame.to_csv(out / 'case_predictions.csv', index=False)
    active = frame[frame.active.astype(bool)]
    metrics = ranking_metrics(active['rank'])
    metrics['supported_only'] = ranking_metrics(active.loc[active.supported, 'rank'])
    dump(out / 'metrics.json', metrics)
    dump(out / 'complete.json', dict(variant='own_frequency', seed=0, parameters=0, seconds=0,
         optimizer_updates=0, training_cases=0, dev_cases=len(dev), metrics=metrics,
         semantics='log1p outgoing distinct transaction count B[:,1]; fixed union pool; stable address tie break'))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--run', required=True); a = ap.parse_args()
    root = Path(a.run)
    missing = [f'{v}/seed{s}' for v in VARIANTS for s in range(3)
               if not (root / 'models' / v / f'seed{s}' / 'complete.json').exists()]
    if missing:
        raise SystemExit('Incomplete required training: ' + ', '.join(missing))
    own_frequency(root)
    results = []; frames = []; completes = []
    strata = []; heads = []; gates = []
    for v in [*VARIANTS, 'own_frequency']:
        for seed in ([0] if v == 'own_frequency' else range(3)):
            d = root / 'models' / v / f'seed{seed}'
            rec = json.loads((d / 'complete.json').read_text()); completes.append(rec)
            f = pd.read_csv(d / 'case_predictions.csv'); f['active']=f['active'].astype(bool); frames.append(f)
            assert len(f) == 150 and int(f.active.sum()) == 52
            assert int((f.active & f.supported).sum()) == 40
            if v != 'own_frequency':
                assert rec['optimizer_updates'] == 408
                log = json.loads((d / 'train_log.json').read_text())
                assert len(log) == 6 and all(t['updates'] == 68 for t in log)
                assert all(np.isfinite(t['loss']) for t in log)
            m = ranking_metrics(f.loc[f.active, 'rank'])
            for k in METRICS:
                assert abs(m[k] - rec['metrics'][k]) < 1e-9
            results.append(dict(variant=v, seed=seed, parameters=rec['parameters'],
                                seconds=rec['seconds'], **m))
            af = f[f.active]
            groups = dict(all_active=af, supported_only=af[af.supported],
                          old_target=af[af.old_target], new_target=af[~af.old_target],
                          observed_contract=af[af.contract_target], contract_unknown=af[~af.contract_target],
                          high_activity=af[af.high_activity], lower_activity=af[~af.high_activity],
                          target_certified=af[af.target_valid], target_uncertified=af[~af.target_valid])
            for group, subset in groups.items():
                strata.append(dict(variant=v, seed=seed, stratum=group, **ranking_metrics(subset['rank'])))
            if v != 'own_frequency':
                mm = rec['metrics']
                heads.append(dict(variant=v, seed=seed, activity_auroc=mm['activity']['auroc'],
                                  activity_brier=mm['activity']['brier'], open_world_auroc=mm['open_world']['auroc']))
                gates.append(dict(variant=v, seed=seed, **mm['gate']))
    per = pd.DataFrame(results); per.to_csv(root / 'metrics_by_seed.csv', index=False)
    summary = []
    for v in [*VARIANTS, 'own_frequency']:
        x = per[per.variant == v]; r = dict(variant=v, seeds=len(x), active_n=52,
             parameters=int(x.parameters.iloc[0]), runtime_seconds_total=float(x.seconds.sum()))
        for k in METRICS:
            r[k + '_mean'] = float(x[k].mean()); r[k + '_std'] = float(x[k].std(ddof=1)) if len(x) > 1 else 0.
        summary.append(r)
    pd.DataFrame(summary).to_csv(root / 'main_metrics.csv', index=False)
    pd.DataFrame(strata).to_csv(root / 'strata_by_seed.csv', index=False)
    pd.DataFrame(heads).to_csv(root / 'separate_heads.csv', index=False)
    pd.DataFrame(gates).to_csv(root / 'gate_audit.csv', index=False)
    f = pd.concat(frames, ignore_index=True); f.to_csv(root / 'all_case_predictions.csv', index=False)
    active = f[f.active].copy()
    for k in METRICS: active[k] = contribution(active['rank'], k)
    averaged = active.groupby(['variant', 'case_id', 'wallet'], as_index=False)[METRICS].mean()
    pairs = [(v, 'direct_global') for v in [*VARIANTS, 'own_frequency'] if v != 'direct_global']
    # The strongest pre-certificate comparator is the legacy scorer; keep its
    # paired case/wallet comparison explicit for the new fusion variants.
    pairs += [(v, 'direct_global_legacy') for v in
              ['legacy_cert_fusion', 'legacy_cert_nogate', 'legacy_cert_frozen', 'legacy_all_mlp']]
    pairs += [('chain_all', v) for v in ['bounded_residual', 'direct_global_chain', 'graphmixer',
              'popularity_control', 'invalid_control', *[x for x in VARIANTS if x.startswith('minus_')]]]
    boot = []
    for lhs, rhs in pairs:
        l = averaged[averaged.variant == lhs]; r = averaged[averaged.variant == rhs]
        joint = l.merge(r, on=['case_id', 'wallet'], suffixes=('_l', '_r'), validate='one_to_one')
        assert len(joint) == 52
        wallets = sorted(joint.wallet.unique()); counts = np.array([(joint.wallet == w).sum() for w in wallets])
        draws = np.random.default_rng(20261001).integers(0, len(wallets), size=(2000, len(wallets)))
        for k in METRICS:
            d = joint[k + '_l'] - joint[k + '_r']
            totals = np.array([d[joint.wallet == w].sum() for w in wallets])
            sampled = totals[draws].sum(1) / counts[draws].sum(1)
            lo, hi = np.quantile(sampled, [.025, .975])
            boot.append(dict(lhs=lhs, rhs=rhs, metric=k, difference=float(d.mean()),
                             ci_low=float(lo), ci_high=float(hi), wallet_clusters=len(wallets),
                             active_cases=52, replicates=2000, seed_averaged_first=True))
    pd.DataFrame(boot).to_csv(root / 'paired_bootstrap.csv', index=False)
    # Candidate coverage and held-out support are computed from actual saved dev cases.
    with (root / 'shards' / '2022-07-01.pkl').open('rb') as handle: dev = pickle.load(handle)
    total = sum(len(r['pool']) for r in dev); certified = sum(int(r['C'][:, 0].sum()) for r in dev)
    coverage = dict(dev_candidate_rows=total, certified_candidate_rows=certified,
                    certified_candidate_fraction=certified / total,
                    active_cases=52, supported_active=40,
                    active_target_certified=sum(bool(r['C'][r['y_idx'], 0]) for r in dev if r['active'] and r['y_idx'] >= 0),
                    cert_kinds={key: sum(int((r['C'][:, i] > 0).sum()) for r in dev)
                                for key, i in [('ordered_path', 1), ('shared_token_wedge', 5), ('repeat_interaction', 8)]})
    dump(root / 'certificate_coverage.json', coverage)
    ext = json.loads((root / 'extraction_complete.json').read_text())
    # Recovered/fixed extraction records keep runtime per cutoff rather than a
    # top-level total.  Sum those bounded runtimes when needed.
    extraction_seconds = float(ext.get('seconds', sum(float(c.get('seconds', 0.0)) for c in ext.get('cutoffs', []))))
    train_seconds = float(per.seconds.sum())
    learned_runs = len(VARIANTS) * 3
    optimizer_updates_per_run = 6 * 68
    cost = dict(extraction_seconds=extraction_seconds, summed_training_and_evaluation_seconds=train_seconds,
                learned_runs=learned_runs, epochs_per_run=6, optimizer_updates_per_run=optimizer_updates_per_run,
                optimizer_updates_total=learned_runs * optimizer_updates_per_run, candidate_rows=8412223,
                inference_api_calls=0, paid_queries=0, holdout_opened=False)
    dump(root / 'cost_summary.json', cost)
    sensitivity = root / 'sensitivity' / 'summary.json'
    sens = json.loads(sensitivity.read_text()) if sensitivity.exists() else None
    gm_path = root / 'graphmixer_extension_audit.json'
    gm = json.loads(gm_path.read_text()) if gm_path.exists() else None
    rows = {r['variant']: r for r in summary}
    lines = ['# Certificate v2 — full train/dev report', '',
             f'Completed {len(VARIANTS)} learned variants × 3 seeds × 6 epochs. The primary denominator is all **52 active dev wallets**, '
             'including 12 unsupported targets with zero credit. There are 150 dev cases and 2,150 training cases. '
             'This is offline retriever development; it is not an LLM experiment or an untouched August test.', '',
             '## Primary results', '', '| Variant | R@5 mean ± sd | R@50 | R@100 | MRR@5 mean ± sd | Parameters |',
             '|---|---:|---:|---:|---:|---:|']
    for r in summary:
        lines.append(f"| {r['variant']} | {r['R@5_mean']:.4f} ± {r['R@5_std']:.4f} | {r['R@50_mean']:.4f} | "
                     f"{r['R@100_mean']:.4f} | {r['MRR@5_mean']:.4f} ± {r['MRR@5_std']:.4f} | {r['parameters']:,} |")
    lines += ['', '## Paired uncertainty', '',
              'Seeds are averaged per case before a 2,000-replicate paired wallet-cluster bootstrap. '
              'Intervals are descriptive dev uncertainty, with no multiple-comparison correction or test-set claim.', '',
              '| Comparison | Metric | Difference | 95% interval |', '|---|---|---:|---:|']
    for b in boot:
        if b['lhs'] in ['chain_all', 'bounded_residual'] and b['rhs'] in ['direct_global', 'direct_global_chain', 'popularity_control', 'invalid_control'] and b['metric'] in ['R@5', 'MRR@5']:
            lines.append(f"| {b['lhs']} − {b['rhs']} | {b['metric']} | {b['difference']:.4f} | [{b['ci_low']:.4f}, {b['ci_high']:.4f}] |")
    lines += ['', '## Coverage, protocol and costs', '',
              f"- Candidate union: 8,412,223 rows over 2,300 cases; no target injection; active target support 40/52 (76.92%).",
              f"- Valid certificates: {ext['certificates']:,}; invalid saved proofs: {ext['invalid']}; strict event timestamp < cutoff.",
              f"- Dev candidate certificate coverage: {certified:,}/{total:,} ({certified/total:.2%}); active target coverage {coverage['active_target_certified']}/52.",
              f"- Extraction: {extraction_seconds/60:.1f} min; summed model training plus evaluation: {train_seconds/60:.1f} min (parallel workers; not wall time).",
              f'- {learned_runs} final-epoch checkpoints; {optimizer_updates_per_run} optimizer steps per run; train-only feature normalization; no dev checkpoint selection.',
              '- No inference API calls, paid cloud queries, or August reads in this round.',
              '- Own-frequency is outgoing distinct transaction count; its one deterministic run has no seed uncertainty.',
              '- Full scores/ranks/gates are in each models/<variant>/seed*/predictions.parquet; heads and supported-only strata are separate CSVs.',
              '', '## Interpretation boundaries', '',
              '- Pool support caps recall at 40/52. OPEN_WORLD predictions never count as address top-k hits.',
              '- Controls share the certificate-model architecture; GraphMixer and legacy baselines have different parameter counts and runtime. Equal training steps do not mean equal capacity.',
              '- Popularity control permutes normalized certificate summaries within per-case integer log-global bins, preserving true validity. Chain covariates E remain attached to their original candidates, so this is a partial identity control.',
              '- Invalid control zeros the validity mask; it should reduce to the direct/global branch. No-evidence bounded-fusion corrections must be exactly zero.',
              '- Native values and same-token flow are separated. Token decimals, selector/input, nonce, gas and trusted protocol labels are unavailable.',
              '- Contract status is only observed token-contract or creation-receipt evidence before cutoff; unobserved is unknown, not EOA.',
              '- Physical-event deduplication and distinct-transaction support prevent counting multiple families of the same transaction as independent evidence.',
              '- Directed temporal paths, shared-token wedges and repeated interactions are different evidence types; wedges are not paths.',
              '- A repaired implementation and full run do not establish predictive superiority, causal effects or LLM improvement. Small dev strata and repeated development limit external validity.',
              '', '## Feature and deletion audits', '']
    if gm:
        lines += [f"GraphMixer candidate-extension audit: {gm.get('status')}; see graphmixer_extension_audit.json.", '']
    else: lines += ['GraphMixer extension audit not yet complete.', '']
    if sens:
        lines += [f"Recomputed event-deletion sensitivity: {sens['cases']} cases; {sens['random_controls']} matched random deletions. "
                  'Pools, model and normalization stay frozen; histories, certificates, B/C/E and wallet context are rebuilt.',
                  'This is controlled evidence sensitivity, not causal identification. See sensitivity/REPORT.md and structured JSON case records.', '']
    else: lines += ['Event-deletion sensitivity is not complete; do not treat this report as a final completion marker.', '']
    lines += ['## Artifact guide', '',
              '- main_metrics.csv / metrics_by_seed.csv: all-active metrics and seed variation.',
              '- paired_bootstrap.csv: all paired intervals; strata_by_seed.csv: support, old/new, contract and activity groups.',
              '- separate_heads.csv / gate_audit.csv: activity and OPEN_WORLD heads; gate distributions and bound checks.',
              '- certificates.jsonl / canonical_ledger.parquet: verifiable proofs and physical events.',
              '- source/ / source_manifest.json: execution sources and hashes; frozen RESUME_PROTOCOL_20261001.md.',
              '- cost_summary.json / extraction_complete.json / models/*/seed*/complete.json: work and runtime evidence.', '']
    (root / 'REPORT.md').write_text('\n'.join(lines))
    dump(root / 'summary_complete.json', dict(learned_runs=learned_runs, primary_active=52, supported_active=40,
         bootstrap_repeats=2000, sensitivity_complete=bool(sens), graphmixer_audit_complete=bool(gm),
         final_complete=bool(sens and gm and gm.get('status') == 'passed')))
    print(json.dumps(dict(summary='complete', learned_runs=learned_runs, sensitivity_complete=bool(sens))), flush=True)

if __name__ == '__main__': main()
