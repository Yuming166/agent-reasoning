# Decision-State frozen artifact-first falsification audit

- Run time: `2026-09-20T13:30:23Z`
- Mode: `DETERMINISTIC_ARTIFACT_FIRST_AUDIT`
- Source rows: `3000`; OOS rows used: `2000` (dev `1000`, test `1000`)
- Wallets in OOS: `1946`
- Bootstrap: wallet-clustered, `2000` replicates, seed `20260920`

## Scope and immutability

This is a deterministic audit of already-frozen artifacts. It does not generate new LLM outputs, fit a new predictor, change a probability, select cases by outcome, or reopen the August frozen test. The official Astra6 cycle and claim/experiment ledgers are untouched.

## Main F–Delta audit

`F` is the existing intervention-response magnitude (`intervention_sensitivity`), not semantic validity or faithfulness. `Delta` is frozen B4 macro log-loss minus frozen B0/M1 macro log-loss; negative means B4 improved.

- OOS pooled Pearson(F, Delta): `-0.0334`; Spearman: `-0.0194`; n=`2000`.
- July development Pearson: `-0.0213`; August frozen test Pearson: `-0.0549`.
- Activity-bin residualized OOS Pearson: `-0.0366`; this removes only fixed activity-bin means and is not a causal adjustment.
- Wallet-cluster bootstrap Pearson 95% CI: `[-0.0807, 0.0140]`; wallet-collapsed estimates are in `cluster_correlations.csv`.

A correlation near zero, or a confidence interval crossing zero, is a falsification of a simple monotone F-to-effectiveness story in this artifact set; it is not evidence that true belief, intent, or semantic validity is absent.

## Decomposition and controls

The CSV outputs report intervention type (self/market/placebo), each consequence dimension, split, activity strata, repeat-wallet status, dominant event family, event-history quartiles, and wallet-clustered estimates. They are descriptive audits over the frozen OOS rows, not post-hoc model tuning.

## Representation boundary

The panel contains narrative hypothesis text, but the frozen B2/B3/B4 evaluation lineage converts hypotheses into closed consequence distributions and intervention features. This artifact set does not contain a text-only/text-free matched downstream ablation or embeddings. Therefore it cannot attribute any observed B2/B3/B4 behavior to narrative text itself; B1 and B0 are text-free comparator baselines, not a controlled text ablation.

## Current deterministic conclusion

The next defensible action is a falsification/reliability gate, not a large new LLM experiment. If semantic human audit is later considered, its sampling and rubric must be locked before inspecting F, Delta, success/failure, or August outcomes. Any Luna Max interpretation of this directory remains `OFF_CHARTER_EXPLORATORY_FALLBACK` and cannot be promoted to the official claim ledger or experiment registry.

## Files

- `audit_manifest.json`: input fingerprints and protocol metadata.
- `overall_correlations.csv`: raw and activity-bin-adjusted correlations.
- `cluster_correlations.csv`: wallet-cluster bootstrap and wallet-collapsed correlations.
- `dimension_correlations.csv`: consequence-dimension level associations.
- `strata_summary.csv`: descriptive stratified audit.
- `model_strata_summary.csv`: frozen model loss summaries by scope/stratum.
- `variant_summary.csv`: frozen panel variant parse/text presence audit.
