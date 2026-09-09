# Corrected v2 LLM panel results

Generated on 2026-09-09 from four frozen 1,000-event snapshots using
`glm-5.3` and the tie-aware corrected evaluator.

## Protocol

- `cheap`: frozen June-trained structured ranker;
- `nocf`: one-shot LLM ranking without a counterfactual mask;
- `full`: `OBSERVE_HISTORY -> RUN_COUNTERFACTUAL_MASK -> UPDATE_BELIEF ->
  STOP_AND_PREDICT`;
- exact score ties use average competition ranks;
- every snapshot contains 1,000 events and the positive is supported by the
  v2 candidate pool;
- invalid Full/NoCF parses are retained and operationally fall back to the
  cheap reciprocal rank; they are not silently removed.

The raw `*_gonogo_eval_floatfix.jsonl` files report the existing evaluator's
parse-conditioned arm metrics. `operational_eval_floatfix.jsonl` reports the
production fallback metric used for routing and the table below.

## Operational weighted MRR

| Snapshot | Full parse | NoCF parse | Cheap | NoCF with fallback | Full with fallback | Full - Cheap |
|---|---:|---:|---:|---:|---:|---:|
| 2022-06 | 0.322 | 0.339 | 0.3281 | 0.4647 | 0.5088 | +0.1807 |
| 2022-07 | 0.959 | 0.974 | 0.2831 | 0.3579 | 0.5029 | +0.2198 |
| 2022-08 | 1.000 | 0.999 | 0.2795 | 0.3797 | 0.5605 | +0.2810 |
| 2022-09 | 1.000 | 1.000 | 0.3003 | 0.4089 | 0.5499 | +0.2496 |

Paired bootstrap 95% intervals for `Full - Cheap` are `[0.1514, 0.2115]`,
`[0.1768, 0.2635]`, `[0.2389, 0.3239]`, and `[0.2077, 0.2929]` for June through
September, respectively. The corresponding `Full - NoCF` deltas are +0.0440,
+0.1451, +0.1808, and +0.1410, with intervals `[0.0221, 0.0661]`,
`[0.1149, 0.1758]`, `[0.1521, 0.2112]`, and `[0.1140, 0.1689]`.

## Interpretation boundary

The corrected run supports the component hypothesis that the structured
counterfactual FSM adds value beyond a one-shot LLM, especially on repeated
and difficult interactions. It also shows heterogeneity: the largest gains are
in `repeat_hard`, while `new_tail` is often close to the cheap baseline.
September is a temporal holdout and remains positive, which is encouraging.

This is **not yet** the final budget-router result. The pre-existing
`router_dataset_v2.csv` was produced before the reciprocal-rank bug was fixed
and must not be used. Rebuild the router dataset from the corrected runs with
failure fallback, then evaluate learned routing against random, repeat-only,
uncertainty, all-cheap, all-full, and oracle policies at matched budgets.

June has an anomalously low parse rate (32.2% Full, 33.9% NoCF). It is retained
for audit and fallback evaluation, but should be diagnosed or rerun before it
is used as clean router-training evidence. The September result uses the frozen
v2 cheap panel and is the valid temporal holdout, not the earlier v1 September
run.

## Files

- `corrected_v2_manifest.json`: hashes, row counts, protocol, and parse rates;
- `operational_eval_floatfix.jsonl`: fallback-adjusted weighted MRR and paired
  bootstrap intervals;
- `runs/*_gonogo_eval_floatfix.jsonl`: original by-stratum evaluator output;
- `runs/*_gonogo_glm53_v2_floatfix.csv`: compact per-event audit outputs;
- `cheap_ranker_v2_metrics.json` and `../llm_panel_20220901/cheap_ranker_sept_v2_metrics.json`:
  frozen cheap-ranker metrics.

Full panel-scoring tables and candidate shards remain outside Git; see
`DATA_ACCESS.md` and `corrected_v2_manifest.json`.
