# OW-010B Codex Design Review

**Review date:** 2026-09-18 UTC
**Stage:** completed before OW-010B primary result inspection
**Astra6 advice:** `ASTRA6_PREREGISTRATION_ADVICE.json`
**Astra6 response SHA256:** `af5d9964420bf9f945a773b448c7ab00ba5786ec5c7ceee2c13b983a06a39d11`
**Model identity:** requested and returned `gpt-6-astra`; the raw response contains the non-secret call audit.

## Scope and blind boundary

Astra6 received only the OW-010A substrate contract, available feature/outcome families, candidate counts, and the scientific question. No external wash/illicit labels, label prevalence, label matches, label-derived outcomes, or OW-010B results were included. This review does not load or inspect such labels either. The experiment remains a future-behavior-change prediction study, not an external-label detection study.

## Astra6 recommendations retained

The following parts are scientifically sound and are retained:

- the estimand is nested out-of-sample predictive utility, not causality;
- compare nested M0/M1/M2 models rather than optimize an anomaly score;
- use a signed multivariate future-change vector, with a scalar surprise summary only as secondary reporting;
- fit target scaling, imputation, and feature scaling on training data only;
- use June/July/August as train/development/frozen-test cutoffs;
- distinguish repeated-wallet forecasting from wallets with no eligible earlier row;
- use wallet-cluster paired bootstrap intervals;
- make matching secondary, not the primary design;
- use simple regularized models before any GNN or latent-strategy analysis;
- fix negative controls, activity strata, and GO/MODIFY/NO-GO rules before test evaluation.

## Independent audit and revisions

### 1. Primary inclusion rule: remove the score-window activity gate

Astra6 proposed requiring `event_count_7d >= 1` in addition to `history_event_count_30d >= 1`. That is not necessary for a leakage-safe change target: zero score-window counts can be represented by `log1p(0)`, and smoothed composition shares are defined for a zero-event reference window. Requiring score activity would change the scientific population from wallets with any observable pre-cutoff history to wallets active in every immediate score window, and would select on recency/high activity.

**Frozen revision:** primary discovery eligibility is `history_event_count_30d >= 1` only. `event_count_7d >= 1/3/5` are prespecified sensitivity cohorts, never replacements for the primary cohort.

### 2. Make the target dimensionally explicit

Astra6 described a six-item vector whose final event-family-composition item is itself a vector of contrasts. That is mathematically ambiguous for equal weighting. The feature table and future table contain three exhaustive event-family categories and three exhaustive direction categories. Each simplex has two degrees of freedom.

**Frozen revision:** the primary signed target has seven scalar dimensions:

1. log future event count change;
2. log future unique-counterparty change;
3. active-day change;
4. incoming-share change;
5. outgoing-share change;
6. native/external-family-share change;
7. token-family-share change.

Internal/self shares are the fixed reference categories. Each scalar target dimension is standardized using training data only, and the multivariate loss averages the seven standardized squared errors equally.

### 3. Do not make the squared surprise norm the primary target

The norm of a signed change vector discards direction and makes a large movement in either direction look identical. It is also not a direct test of whether the model predicts the behavioral change components. The signed vector is therefore primary; the scalar `Future Behavioral Surprise` is a deterministic secondary summary:

`S = sqrt(mean(z_j^2))`, where `z_j` are the training-standardized seven signed changes.

No model or threshold is selected using `S` after results are observed.

### 4. Use only feature semantics actually frozen in OW-010A

The Astra6 proposal mentioned time-of-day/day-of-week summaries and counterparty concentration features that are not independent columns in the materialized v1 table. They are excluded rather than reconstructed post hoc. Exact reciprocity-change parity, temporal cycles, asset-aware split/merge, cross-asset token aggregation, and ambiguous motifs are also excluded from the primary M2_CORE. The included M2 features have executable definitions in `substrate/ow010a/sql/03_discovery_features.sql` and are documented as aggregate proxies.

### 5. Preserve zero and structural missingness semantics

A global `fillna(0)` would conflate a true zero with an undefined statistic. The implementation uses explicit missing indicators for gap statistics and training-only median imputation for structural N/A values. Count totals and composition denominators use declared zero/smoothing rules. No future-derived imputation is allowed.

### 6. Keep the three-cutoff limitation explicit

Only August is a strictly held-out temporal test cutoff. July is development and June is training. July and August test-like subgroup summaries are not independent temporal replications. A positive August interval is a bounded pilot result, not evidence of stable generalization across many dates.

### 7. Keep the model family simple and budgets equal

Primary: multi-output ridge regression with the same five penalty values for M0, M1, M2_CORE and fixed preprocessing. Secondary robustness: one preregistered `HistGradientBoostingRegressor` specification wrapped for multi-output prediction, with the same fixed settings across feature ladders. No GNN, LLM reasoning, address feature, or raw counterparty identifier is allowed.

### 8. Guard against target/activity circularity

The change target references the immediately preceding score window, which is also represented in M0. This is intentional autoregressive forecasting, not leakage: the score window ends at the cutoff and the target begins at the cutoff. It makes the baseline stronger and the incremental test more conservative. The target is not constructed from M1/M2 structural columns.

### 9. Evaluation eligibility is not discovery eligibility

The full discovery grid remains 27,613 rows per cutoff. The discovery cohort is history-observed (`history_event_count_30d >= 1`). Future 7-day/30-day completeness is checked only when evaluating the corresponding outcome, and evaluation rows are reported separately. A future-zero outcome is retained; it is not treated as missing.

## Critical failure conditions

Any of the following blocks interpretation and requires an amendment or repair before the affected result is used:

- a feature uses an event with `event_timestamp >= cutoff_time`;
- a target transformation or imputation parameter uses July/August values before the relevant evaluation;
- duplicate `(anchor_wallet, cutoff_time)` keys or feature/outcome join multiplication;
- incomplete future-window coverage is silently treated as zero;
- any address/counterparty identifier enters a model;
- August predictions are used to alter features, targets, thresholds, or model budgets;
- an external label source is accessed or enters the pipeline.

## Final Codex verdict

The Astra6 design is usable after the above conservative revisions. The frozen primary question is a nested, blinded, temporal predictive test on an explicitly defined signed seven-dimensional future-change vector. No empirical conclusion is implied by this design review.
