# OW-010B Preregistration
## Blind Incremental Temporal-Structural Signal Test

**Freeze date:** 2026-09-18 UTC
**Experiment:** OW-010B
**Status at freeze:** protocol frozen before primary OW-010B model results
**Substrate status:** `SUBSTRATE_READY_FOR_OW010B`
**External-label access:** `wash_label_accessed = false`

## 1. Scientific question and estimand

The question is whether pre-cutoff temporal and structural Ethereum behavior improves prediction of future behavioral change beyond a strong baseline of historical scale, activity, native flow, event-family composition, counterparty count, and degree.

The primary estimand is the August 2022 out-of-sample incremental predictive utility of:

- **M1 over M0** for temporal information;
- **M2_CORE over M1** for structural information;
- **M2_CORE over M0** for total incremental information.

The estimand is predictive, not causal. A positive result is not evidence of a wash-trading category, illicit behavior, identity-level generalization, or deployment utility.

Primary hypotheses are directional:

- `H0_temporal`: M1 does not reduce expected August multivariate standardized loss relative to M0.
- `H1_temporal`: M1 reduces that loss.
- `H0_structural`: M2_CORE does not reduce expected loss relative to M1.
- `H1_structural`: M2_CORE reduces that loss.
- `H0_total`: M2_CORE does not reduce expected loss relative to M0.
- `H1_total`: M2_CORE reduces that loss.

The point estimate is `improvement = loss(baseline) - loss(model)`; positive means better. The relative improvement is `improvement / loss(baseline)`.

## 2. Population and eligibility

### 2.1 Discovery population

The discovery table is the complete `27,613 anchors x 3 cutoffs` grid. It is not filtered by future activity, future outcomes, or matching.

The primary discovery cohort at each cutoff is:

```text
history_event_count_30d >= 1
```

where history is the half-open interval `[cutoff_time - 30 days, cutoff_time)`. This gives the preregistered expected counts:

| cutoff | primary discovery rows |
|---|---:|
| 2022-06-01 | 17,156 |
| 2022-07-01 | 15,736 |
| 2022-08-01 | 14,683 |

A zero-event score window is allowed. It is represented using zero counts, smoothed shares, and missingness indicators where appropriate. The following sensitivity cohorts are fixed before results and are not used to select the primary conclusion: `event_count_7d >= 1`, `>=3`, and `>=5`, conditional on history `>=1`.

### 2.2 Evaluation cohorts

For the primary 7-day target, evaluation uses discovery rows with:

- `history_event_count_30d >= 1`;
- `future7_window_coverage_status == 'OBSERVED_FULL_WINDOW'`;
- all seven target dimensions finite after deterministic construction.

Future zero counts remain valid observations. For the secondary 30-day target, the corresponding 30-day coverage status is used. Discovery eligibility and future-evaluation eligibility are reported separately.

The feature table is discovery-only. A compact pre-cutoff score composition aggregate is materialized from the event-level substrate by `sql/score7_asof_composition.sql`; it contains counts only, not raw events. The future table is joined only after the protocol and feature/target definitions are frozen and is never used for discovery eligibility, ranking, feature selection, normalization of discovery features, or matching.

## 3. As-of windows and target

All intervals are UTC and half-open.

- Discovery history: `[t-30d, t)`.
- Recent score reference: `[t-7d, t)`.
- Primary future horizon: `[t, t+7d)`.
- Secondary future horizon: `[t, t+30d)`.

### 3.1 Primary signed target vector

Let `q(c, k, alpha) = (count(c,k) + alpha) / (total(c) + alpha*K)`, with `alpha=0.5` and `K=3`. This is applied to the three exhaustive direction categories (`incoming`, `outgoing`, `self`) and the three exhaustive event families (`external/native`, `token_transfer`, `internal_trace`). Internal/self are reference categories; they are not included as independent coordinates.

For each wallet-cutoff row, construct the seven-dimensional signed future-change vector `Y7`:

1. `log1p(future7_event_count) - log1p(event_count_7d)`;
2. `log1p(future7_unique_counterparties) - log1p(score_unique_counterparties_7d)`;
3. `future7_active_days - active_days_7d`;
4. `q(future7_incoming, future7_total, 0.5) - q(score_incoming_7d, event_count_7d, 0.5)`;
5. `q(future7_outgoing, future7_total, 0.5) - q(score_outgoing_7d, event_count_7d, 0.5)`;
6. `q(future7_external/native, future7_total, 0.5) - q(score_external/native, event_count_7d, 0.5)`;
7. `q(future7_token, future7_total, 0.5) - q(score_token, event_count_7d, 0.5)`.

The compact as-of score aggregate supplies `score_external_native_7d`, `score_token_7d`, `score_internal_7d`, and exact score-window direction counts. `future7_total` is `future7_event_count`. The aggregate is computed only with `event_timestamp < cutoff_time` and no raw event rows are exported.

The signed vector preserves direction. The target uses future outcomes only in `[t,t+7d)` and pre-cutoff reference counts in `[t-7d,t)`. No M1/M2 structural feature defines the target. The target is partly activity-related by design, but it is not future activity alone: it includes active-day persistence, direction composition, and event-family composition changes. The strong M0 controls the historical scale and recent level used in the change reference.

### 3.2 Training-only target standardization

For a given fitting phase:

1. fit the mean and standard deviation of each `Y7` dimension on the fitting cutoffs only;
2. use those parameters unchanged on development/test rows;
3. if a training standard deviation is zero, use scale 1 for that coordinate and record it;
4. no test or future-window statistic is used to standardize or impute the target.

No post-hoc winsorization is used in the primary analysis.

### 3.3 Scalar Future Behavioral Surprise

The primary model predicts the signed vector. A deterministic scalar summary is reported secondarily:

```text
Future Behavioral Surprise S7 = sqrt(mean_j(z7_j^2))
```

where `z7_j` are the training-standardized signed target dimensions. `S7` is a multivariate magnitude-of-change summary, not a pure anomaly label and not a future-activity proxy. Because it discards direction, it is not the primary estimand and cannot replace the signed-vector analysis.

### 3.4 Secondary 30-day target

The available 30-day outcome table supports a prespecified three-dimensional target:

- `log1p(future30_event_count) - log1p(history_event_count_30d)`;
- `log1p(future30_unique_counterparties) - log1p(unique_counterparties_30d)`;
- `future30_active_days - active_days_30d`.

The 30-day target is secondary and is not used to change the primary 7-day protocol.

## 4. Feature ladder

All features satisfy `event_timestamp < cutoff_time`. No wallet address, raw counterparty ID, or unrestricted categorical ID is used.

### M0 — scale/activity/volume/degree baseline

M0 includes only frozen level/scale covariates:

- log1p historical and recent event counts: `history_event_count_30d`, `event_count_1d`, `event_count_7d`, `event_count_30d`;
- `active_days_7d`, `active_days_30d`, `active_hours_30d`;
- incoming/outgoing/self event counts in 7d and 30d;
- unique, mapped, unmapped, and recent unique counterparty counts;
- native inflow, native outflow, native netflow, native event count, and native amount-observed indicator;
- native/token/internal event counts and 30-day composition ratios.

Nonnegative totals use `log1p`; signed net flow uses `asinh`. A native amount with no native events is represented as zero for total flow plus an explicit observed indicator; undefined native mean/max statistics are not used in M0.

### M1 — M0 plus temporal dynamics

M1 adds:

- inter-event gap mean, standard deviation, median, minimum, and maximum over 30d;
- explicit gap-statistic missing indicator (`history_event_count_30d < 2` or source null);
- gap coefficient of variation where defined;
- 7-day active-hour mean/std/max and derived hourly burst/concentration ratios;
- recent-vs-prior changes in event counts, active days, counterparty counts, and family composition using the compact score7 as-of aggregate;
- counterparty novelty, repeat, turnover, and growth derived from `new_counterparties_7d`, `repeat_counterparties_7d`, `prior_unique_counterparties_23d`, and `score_unique_counterparties_7d`.

Time-of-day/day-of-week features are not included because they are not independent frozen columns in OW-010A v1.

### M2_CORE — M1 plus conservative structure

M2_CORE adds only QA-supported aggregate structural proxies:

- counterparty entropy and normalized entropy;
- prior and 30-day reciprocal-counterparty rates and their change;
- maximum hourly fan-in and fan-out counterparties;
- rapid-forwarding adjacent count and normalized rate, using the exact OW-010A definition: adjacent ordered events with incoming followed by outgoing within 0–3600 seconds;
- event-per-counterparty and temporal-degree ratios not containing identifiers.

The rapid-forwarding proxy is included because its SQL definition is frozen in OW-010A; it is not interpreted as a semantic motif. If the implementation QA cannot reproduce that exact definition, the affected feature is removed from M2_CORE and the deviation is logged before evaluation.

### M2_EXTENDED

Not part of the primary analysis. It remains a reserved exploratory set only: validated reciprocity-change parity, temporal-cycle summaries, or asset-aware split/merge summaries would require a preregistered amendment before any result inspection. Cross-asset token aggregation, unrestricted motifs, semantic graph labels, and unreviewed cycles are excluded.

## 5. Preprocessing and missingness

Preprocessing is fit separately for each fitting phase and each feature ladder:

1. construct deterministic finite features;
2. append declared missingness indicators;
3. median-impute numeric structural N/A values using the fitting rows only;
4. standardize numeric columns using fitting rows only.

Zero counts and zero shares are not imputed missing values. No row is dropped because a wallet has no native event, no counterparty, or fewer than two historical events. Feature completeness means key uniqueness, required schema presence, and deterministic finite post-transform values.

## 6. Models and equal tuning budget

### Primary model

Multi-output ridge regression, fitted separately for each feature ladder. Hyperparameter grid:

```text
alpha in {0.01, 0.1, 1, 10, 100}
```

The same grid, preprocessing, fitting calls, and development rows are used for M0, M1, and M2_CORE. Select alpha by July multivariate standardized MSE. If losses differ by at most 0.001, select the larger alpha. The final August model is refit on June+July using the selected alpha for that ladder; the August test is evaluated once.

### Secondary robustness model

A fixed `sklearn.ensemble.HistGradientBoostingRegressor` specification wrapped for multi-output prediction is preregistered as a robustness analysis:

```text
learning_rate=0.05, max_iter=200, max_leaf_nodes=15,
min_samples_leaf=50, l2_regularization=1.0, random_state=20260918
```

The same settings and rows are used for all ladders. It is not used to select the primary result or decision rule. If resource failure occurs, this secondary model may be omitted with a logged deviation; the ridge primary remains frozen.

No GNN, representation-learning model, LLM latent-strategy model, raw address feature, or raw counterparty categorical is permitted.

## 7. Temporal protocol

The fixed split is:

- **TRAIN:** June 1, 2022 rows; target/feature preprocessing fit here for July selection.
- **DEV:** July 1, 2022 rows; select ridge alpha and record all five losses.
- **TEST:** August 1, 2022 rows; refit on June+July and evaluate once.

No random wallet-cutoff split is used. No cutoff is added after results are seen. June training metrics are not inferential. July is a development diagnostic. August is the primary held-out temporal evaluation.

Repeated-wallet analysis: August primary-evaluation wallets with an eligible June or July primary row. Unseen-wallet analysis: August primary-evaluation wallets with no eligible June or July primary row. The address is used only to define the audit stratum, never as a feature. If the unseen stratum has fewer than 500 wallets, report descriptively without nominal formal inference.

## 8. Metrics and uncertainty

### Primary metric

For each row, compute the mean squared error across the seven standardized target dimensions. Report:

- M0/M1/M2 loss;
- paired test-row improvement `loss(baseline)-loss(model)`;
- relative loss reduction;
- wallet count and row count;
- 95% confidence interval for paired improvement.

The three nested contrasts are reported; Holm adjustment is used if all three are presented as formal claims. M1-vs-M0 is the first-priority temporal contrast. M2-vs-M1 is the first-priority structural contrast.

### Secondary metrics

- per-dimension MSE and MAE;
- scalar `S7` MSE/MAE and rank correlation for a separately fitted scalar ridge;
- 30-day three-dimensional target results;
- activity/volume/degree strata;
- repeated versus unseen wallet strata;
- negative-control gains;
- fixed high-activity-tail removal audit.

### Bootstrap

Use 2,000 cluster bootstrap replicates sampled with replacement over August wallet clusters, retaining all rows for each sampled wallet (one primary row per wallet at August). Recompute paired loss differences in each replicate. Report percentile 95% intervals and the bootstrap seed. No IID assumption over cutoff rows is used for pooled inference.

## 9. Activity, volume, and identity audits

Fixed activity strata are based on training history event count:

```text
1-2, 3-9, 10-19, >=20
```

Volume and degree quartile cut points are computed on June+July fitting rows only and applied unchanged to August. Report gains by stratum, with no subgroup used to alter the primary conclusion. Remove the training-defined top 5% activity tail as a sensitivity audit. Report rank correlations between added temporal/structural features and M0 scale features, and whether added features are nearly deterministic functions of activity.

## 10. Negative controls

Before model fitting, create fixed-seed null features:

- permute M1-added features within cutoff × fixed history-activity stratum;
- permute M2-added features within cutoff × fixed history-activity stratum while preserving M0/M1;
- use the same ridge grid, preprocessing, rows, and bootstrap reporting.

Permutation uses only feature values and prespecified strata, never targets. A negative-control gain comparable to or larger than the intended gain triggers an audit and blocks a positive interpretation.

## 11. Matching

Matching is not a primary analysis. No OW-010B causal treatment/control estimand is defined, and the inherited OW-009 matcher did not meet balance. A secondary matching analysis is not required for the primary signal test and will not be used to select candidates or interpret the nested predictive result. If a future amendment adds matching, it must predeclare treatment definition, calipers/balance rejection, reuse, and clustered uncertainty.

## 12. GO / MODIFY / NO-GO

These rules are frozen before primary results:

- **Temporal support:** M1-vs-M0 relative loss reduction >= 2%, paired 95% CI lower bound > 0, and at least 4 of 7 target dimensions have nonnegative point improvement.
- **Structural support:** M2_CORE-vs-M1 relative loss reduction >= 2%, paired 95% CI lower bound > 0, and the gain is not confined to one target dimension (at least 3 of 7 dimensions have positive point improvement).
- **Total support:** M2_CORE-vs-M0 is reported but is not sufficient by itself to claim structural increment.
- **Negative controls:** no permuted incremental ladder may show a gain as large as the intended same-level gain; otherwise the corresponding claim is blocked.
- **QA:** all as-of, key, future-separation, and provenance checks must pass.

`GO_TO_OW010C` requires structural support, no leakage/QA failure, no negative-control failure, and no preregistration violation. Because August is only one held-out cutoff, GO remains a bounded preliminary opening, not confirmation. If temporal/structural support is absent, the corresponding claim is `NO_GO_OPENWORLD_STRUCTURAL_SIGNAL`. If the primary protocol is sound but the evidence is insufficient or a non-fatal design limitation remains, use `MODIFY_BEFORE_EXTERNAL_VALIDATION` and do not open external labels.

Any change to target, windows, cutoffs, inclusion, features, model, tuning budget, metric, or decision rule requires a dated amendment before inspecting the affected result.

## 13. Cheap falsification order

First run the deterministic ridge nested comparison on the frozen 7-day target. If there is no stable M1-vs-M0 incremental signal and no structural signal, do not attempt to rescue the branch with trees, GNNs, or LLM reasoning. The secondary tree robustness run is not a rescue mechanism.

## 14. Blind stop condition

OW-010B ends after the frozen primary/secondary analyses, Astra6 posthoc hostile review, Codex response, and decision report. No external wash-label evaluation, GNN, or latent-strategy track is started automatically.
