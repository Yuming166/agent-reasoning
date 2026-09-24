# Protocol V1 Amendment: Incremental Meta-Head Evaluation

**Freeze timestamp:** 2026-09-19 before the full new LLM panel
**Reason:** clarify the meaning of `M1 + hypothesis` in the baseline ladder before any test-set LLM responses are collected.

## Amendment

The B1-B4 labels denote **feature augmentation of the M1 baseline**, not standalone replacement of M1.

```text
B0 = M1 direct consequence classifier
B1 = M1 + deterministic as-of consequence proxies
B2 = M1 + single-hypothesis LLM consequence/probability features
B3 = M1 + multi-hypothesis LLM mixture features
B4 = M1 + multi-hypothesis features + intervention-response/alignment features
```

The direct LLM consequence distribution remains a secondary descriptive analysis. The primary effectiveness gate asks whether LLM-generated hypothesis features add value beyond the strong M1 model.

## Fixed feature construction

- B2 uses only the top-probability valid hypothesis from the full packet.
- B3 uses the probability-weighted consequence distribution from all valid full-packet hypotheses.
- B4 adds probability-vector JS distances (`R_self`, `R_market`, `R_placebo`), relevant-minus-placebo response margins, claimed evidence indicators, parse-valid flags, and abstention/uncertainty features.
- Natural-language hypothesis text is not passed to the downstream head in this first gate; the evaluator tests structured state/consequence information, not text-surface memorization.
- B1 uses the deterministic trend proxy specified in the main protocol.

## Meta-head fitting

- Same target dimensions, same sampled cases, and same temporal split.
- Fit on June; July is used for a single pre-specified development check; final test head is refit on June+July without changing features or hyperparameters, then evaluated once on August.
- Meta-head: `HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=42)` per consequence dimension.
- Missing LLM features are imputed using training-fit medians; invalid response indicators remain explicit features and are never silently dropped.
- No test outcome is used to select a prompt, feature, threshold, or model.

## Gate interpretation

The primary pass remains:

```text
B4 < B0 test macro log loss
```

with paired address-bootstrap 95% CI for `B0 - B4` entirely above zero.

Secondary claims:

- `B4 < B2` tests intervention value;
- `B3 < B0` tests whether competing hypotheses add value before intervention;
- `B4` may pass a reliability-only gate if predictive loss is not worse than B2 and intervention alignment improves with a pre-registered paired CI.

This amendment was written before the full panel and does not use test results.
