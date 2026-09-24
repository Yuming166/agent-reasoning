# OW-010B Result Report
## Blind Incremental Temporal-Structural Signal Test

**Date:** 2026-09-18 UTC
**Status:** frozen primary analysis completed; external-label branch remains closed
**Final decision:** `NO_GO_OPENWORLD_STRUCTURAL_SIGNAL`

## Scope and blind boundary

OW-010B tested whether pre-cutoff temporal/structural Ethereum behavior predicts **future behavioral change** beyond a strong scale/activity/volume/degree baseline. It was not a wash-trading or illicit-activity detection experiment. No external wash/illicit label source was accessed, loaded, inspected, summarized, used for feature design, model selection, threshold selection, or sent to Astra6. The old OW-009 day-level local artifact was not used. No matching analysis, GNN, or latent-strategy/LLM track was run.

The primary analysis used the repaired OW-010A event-level as-of substrate:

- discovery table: `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`;
- evaluation-only outcome table: `ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1`;
- pre-result compact score-window aggregate: `data/ow010b_score7_asof_composition.csv` generated from `sql/score7_asof_composition.sql`;
- observational unit: `(anchor_wallet, cutoff_time)`;
- cutoffs: June 1, July 1, and August 1, 2022 UTC;
- chronological role: June train, July development, August frozen test.

The primary preregistration was frozen before inspecting primary OW-010B results. Its SHA256 is recorded in `preregistration/PREREGISTRATION_MANIFEST.json` and `results/RUN_MANIFEST.json` as:

```text
be137e844be4013080f158c31c2d42419f806f11dca25809168958020592255d
```

A pre-result amendment added only a compact as-of score-window family/direction aggregate because OW-010A did not expose independent token/internal 7-day counts. It did not change the population, target horizon, model classes, split, metrics, or decision rules. The amendment is documented in `PREREGISTRATION_AMENDMENT_20260918_PRE_RESULT.md`.

---

## Executive conclusion

1. **M1 temporal/recent-dynamics features improve prediction over M0** on the frozen August test under the primary Ridge model: absolute multivariate standardized-MSE improvement `0.090486`, relative improvement `11.660%`, paired wallet-bootstrap 95% CI `[0.085655, 0.095335]`. The same direction appears under the preregistered HGB robustness model: `6.064%`, CI `[0.040019, 0.047789]` in absolute MSE units.
2. **M2_CORE does not provide the preregistered structural support.** Ridge adds only `0.1338%` over M1, below the frozen `2%` structural gate; HGB's incremental change is negative (`-0.0301%`) and its CI crosses zero.
3. The apparent M2-over-M0 result is therefore almost entirely the M1 gain. It is not evidence that the conservative structural proxies add meaningful information beyond M0/M1.
4. The M1 finding is a bounded predictive pilot finding, not a causal, external-label, identity-generalization, or deployment claim. It likely mixes recency, burstiness, turnover, gap dynamics, and autoregressive activity persistence.
5. The frozen decision is **`NO_GO_OPENWORLD_STRUCTURAL_SIGNAL`**. Do not open OW-010C, build a GNN, or use LLM latent-strategy inference. A future continuation would require a new preregistered design amendment made without using the current test result to tune the protocol.

---

## 1. What exactly is Future Behavioral Surprise?

The primary target is not a single future count. It is a signed seven-dimensional future-change vector for the 7-day future window `[t,t+7d)` relative to the as-of score window `[t-7d,t)`:

```text
Y7 = [
  log1p(event_count_future_7d) - log1p(event_count_score_7d),
  log1p(unique_counterparties_future_7d) - log1p(unique_counterparties_score_7d),
  active_days_future_7d - active_days_score_7d,
  incoming_share_future_7d - incoming_share_score_7d,
  outgoing_share_future_7d - outgoing_share_score_7d,
  native_share_future_7d - native_share_score_7d,
  token_share_future_7d - token_share_score_7d
]
```

The share coordinates use three-category additive smoothing with `alpha=0.5`; internal/self categories are reference categories. Future-zero counts are valid zeros. Target standardization is fitted on the fitting cutoffs only: June for development and June+July for the frozen August test.

The primary metric is mean squared error averaged over the seven standardized signed coordinates. The secondary scalar summary is:

```text
S7 = sqrt(mean(z_j^2))
```

where `z_j` are the training-standardized signed target coordinates. `S7` measures the magnitude of future change while discarding direction; it is not a separate anomaly label and does not replace the signed-vector estimand.

The complete target definition is frozen in `data/TARGET_SPECIFICATION.md`.

## 2. Why is it not mechanically equivalent to future activity?

It contains activity-related coordinates, but it is not future activity alone:

- event count and unique-counterparty changes are log-scaled changes rather than raw future totals;
- active-day change measures temporal occupancy rather than only volume;
- incoming/outgoing share changes measure direction/composition;
- native/token share changes measure event-family composition, with internal as a reference category;
- the target is a change relative to an as-of window, not a future-only level.

A wallet can have the same future event count but a different directional or event-family composition and therefore a nonzero target. However, the target is intentionally autoregressive: it is defined relative to recent past behavior, and M1 also contains recent score-window features. This is a valid forecasting setup for behavioral change, but it means a positive M1 result should be interpreted as predicting change conditional on recent state, not as evidence of an isolated “temporal organization” mechanism. This is one of the main limitations retained from the Astra6 hostile review.

## 3. What is the final discovery cohort?

The complete as-of discovery grid contains `27,613` mapped anchors at each of three cutoffs (`82,839` rows). Primary discovery eligibility is only:

```text
history_event_count_30d >= 1
```

where history is `[t-30d,t)`. A zero-event score window is allowed; it is represented by valid zeros, smoothed shares, and the declared missingness procedure. This avoids conditioning discovery on immediate pre-cutoff activity.

| cutoff | primary discovery rows | future 7d coverage among source rows | role |
|---|---:|---:|---|
| 2022-06-01 | 17,156 | complete for eligible rows | train |
| 2022-07-01 | 15,736 | complete for eligible rows | development |
| 2022-08-01 | 14,683 | complete for eligible rows | frozen test |
| **total** | **47,575** | — | — |

The source future-outcome table is physically/logically separate and marked evaluation-only. In the available OW-010A materialization, the primary eligible rows have complete future 7-day and 30-day coverage, so the discovery and primary 7-day evaluation counts coincide. This is a reporting fact about coverage, not a change to the cohort definition: future outcomes were not used to construct eligibility.

No matching requirement, future activity requirement, external label, or address identity was used to define discovery eligibility.

## 4. What are M0, M1, and M2?

| ladder | frozen content | scientific role |
|---|---|---|
| **M0** | Historical/recent event counts, active days/hours, incoming/outgoing/self counts, unique/mapped/unmapped counterparties, native flow and volume where observed, token/internal counts, event-family ratios, temporal degree proxies | Strong scale/activity/volume/degree explanation |
| **M1** | M0 plus inter-event gap statistics, hourly burstiness, recent-vs-prior activity changes, counterparty growth/novelty/turnover/repeat rates, recent event-family and direction counts/ratios | Temporal and recent-dynamics increment |
| **M2_CORE** | M1 plus counterparty entropy, reciprocity rates/change, peak fan-in/fan-out, rapid-forwarding adjacent count/rate, events-per-counterparty ratios | Conservative structural-proxy increment |
| **M2_EXTENDED** | Ambiguous/unreviewed motif, split/merge, cycle, cross-asset semantics | Excluded from primary and secondary analysis |

No wallet address was a feature. Raw counterparty IDs were not used as unconstrained categorical features. `rapid_forwarding` is only the frozen adjacent incoming-to-outgoing-within-3600-seconds proxy; it was not interpreted as an exact motif.

Models and budgets were comparable across ladders:

- primary: multi-output Ridge with the preregistered alpha grid `0.01, 0.1, 1, 10, 100`;
- secondary robustness: histogram gradient boosting;
- all three Ridge ladders selected `alpha=100`, the top of the frozen grid. This is a protocol limitation, not a post-result repair.

## 5. Does M1 improve over M0?

**Yes under the frozen primary test, with a bounded interpretation.**

| model family | M0 test loss | M1 test loss | absolute improvement | relative improvement | paired 95% CI for absolute improvement |
|---|---:|---:|---:|---:|---:|
| Ridge | 0.776007 | 0.685521 | 0.090486 | 11.660% | [0.085655, 0.095335] |
| HGB | 0.723895 | 0.679997 | 0.043898 | 6.064% | [0.040018, 0.047789] |

The Ridge per-dimension improvements are positive for all seven coordinates. HGB has positive improvements for five of seven coordinates and negative improvements for incoming/outgoing share change. This supports an M1 predictive increment, but not a claim that one uniquely identified temporal mechanism is responsible.

## 6. Does M2 improve over M1?

**Not at the preregistered level.**

| model family | M1 test loss | M2_CORE test loss | absolute improvement | relative improvement | paired 95% CI for absolute improvement |
|---|---:|---:|---:|---:|---:|
| Ridge | 0.685521 | 0.684604 | 0.000917 | 0.134% | [0.000316, 0.001559] |
| HGB | 0.679997 | 0.680201 | -0.000205 | -0.030% | [-0.001043, 0.000621] |

The Ridge result is positive but far below the frozen `2%` structural gate and is not model-family robust. The HGB estimate is slightly negative and its interval includes zero. Therefore M2_CORE fails the preregistered structural-support rule.

Ridge per-dimension M2-over-M1 improvements are positive for six of seven dimensions and negative for event-log change, but all are very small. HGB has only three positive per-dimension point improvements. This does not justify a structural claim.

## 7. Does M2 improve over M0?

**Numerically yes, but scientifically this is not a structural result.**

| model family | M0 test loss | M2_CORE test loss | absolute improvement | relative improvement | paired 95% CI for absolute improvement |
|---|---:|---:|---:|---:|---:|
| Ridge | 0.776007 | 0.684604 | 0.091403 | 11.779% | [0.086436, 0.096363] |
| HGB | 0.723895 | 0.680201 | 0.043693 | 6.036% | [0.039787, 0.047747] |

The total gain is almost entirely the M1 gain. The preregistration explicitly states that M2-over-M0 alone is insufficient to claim structural increment.

## 8. What are the paired 95% confidence intervals?

The primary intervals are wallet-cluster bootstrap percentile intervals with 2,000 replicates. The August test contains one eligible row per wallet, but clustering by `anchor_wallet` preserves the declared dependence unit. The intervals below are for absolute paired loss reduction `loss(baseline)-loss(model)`:

| family | contrast | point | 95% CI | n wallets |
|---|---|---:|---:|---:|
| Ridge | M1 - M0 | 0.090486 | [0.085655, 0.095335] | 14,683 |
| Ridge | M2_CORE - M1 | 0.000917 | [0.000316, 0.001559] | 14,683 |
| Ridge | M2_CORE - M0 | 0.091403 | [0.086436, 0.096363] | 14,683 |
| HGB | M1 - M0 | 0.043898 | [0.040018, 0.047789] | 14,683 |
| HGB | M2_CORE - M1 | -0.000205 | [-0.001043, 0.000621] | 14,683 |
| HGB | M2_CORE - M0 | 0.043693 | [0.039787, 0.047747] | 14,683 |

The complete machine-readable records are in `results/bootstrap_intervals.csv` and `results/incremental_gain.csv`.

## 9. Are gains temporally stable?

There is a development-to-test directional replication, but not enough independent temporal replication for a strong stability claim.

| model family | cutoff role | M1-M0 relative gain | M2-M1 relative gain |
|---|---|---:|---:|
| Ridge | July development | 12.209% | 0.033% |
| Ridge | August frozen test | 11.660% | 0.134% |
| HGB | July development | 6.726% | 0.016% |
| HGB | August frozen test | 6.064% | -0.030% |

July was used for development/model selection and is not an independent confirmatory test. August is the only frozen held-out cutoff. Thus M1 is directionally stable across the available development/test transition, but the study cannot establish broad temporal generalization. M2 is not stable across model families and does not meet the gate.

## 10. Are gains present for repeated and unseen wallets?

The August test is dominated by repeated wallets:

- repeated: `13,989` (`95.27%`), defined as an August wallet with an eligible June or July row;
- unseen/no prior eligible row: `694` (`4.73%`).

Ridge descriptive losses and gains:

| stratum | n | M1-M0 MSE gain | M1-M0 relative to stratum M0 | M2-M1 MSE gain |
|---|---:|---:|---:|---:|
| repeated | 13,989 | 0.091136 | 11.47% | 0.000922 |
| unseen | 694 | 0.077382 | 19.41% | 0.000821 |

The unseen stratum meets the preregistered descriptive size floor of 500, but it is still small relative to the repeated stratum and was not a separately powered formal test. These results do not demonstrate identity-level generalization. The dominant result is within-wallet temporal forecasting.

## 11. Do gains survive activity/volume/degree stratification?

The Ridge M1-minus-M0 gain remains positive in every fixed audit stratum:

| audit | strata M1-M0 gain range | M2-M1 gain range |
|---|---:|---:|
| history activity (`1-2`, `3-9`, `10-19`, `>=20`) | 0.059909 to 0.101112 | 0.000357 to 0.001431 |
| native inflow quartile | 0.071591 to 0.113082 | 0.000686 to 0.001270 |
| degree quartile | 0.076125 to 0.108811 | 0.000078 to 0.002339 |

This means the M1 improvement is not visible only in the highest-volume or highest-degree stratum. It does **not** prove that M1 is independent of activity: the added variables remain correlated with scale and recent activity, and the target itself is autoregressive.

The strongest observed structural/activity associations include:

- counterparty entropy vs `log1p(unique_counterparties_30d)`: Spearman `0.963`;
- rapid-forwarding count vs history/event count: approximately `0.907`;
- counterparty entropy vs history event count: approximately `0.893`;
- fan-in/fan-out peaks vs recent event count: approximately `0.885` to `0.887`.

The complete audit is in `results/confound_audit.csv`.

## 12. Do gains survive removal of extreme-activity wallets?

Yes for M1, in the fixed reporting audit. After excluding the training-defined top 5% activity tail, the remaining `13,912` August rows retained a Ridge M1-minus-M0 gain of `0.090243` MSE units, versus `0.094868` within the 771-row top-tail stratum. The result is therefore not solely produced by the extreme-activity tail.

This audit remains observational: removal of the tail does not orthogonalize temporal features from activity or establish a causal mechanism.

## 13. Do negative controls reproduce the gain?

Not in the preregistered Ridge negative-control audit:

| negative control | relative improvement | 95% CI for absolute improvement |
|---|---:|---:|
| M1-added features permuted within cutoff × activity stratum | -0.0062% | [-0.000696, 0.000627] |
| M2-added features permuted within cutoff × activity stratum | -0.0758% | [-0.000883, -0.000157] |

The permuted controls do not reproduce the intended positive gain. This is evidence against a simple feature-order/permutation artifact. It is not proof that all activity confounding, target autoregression, or temporal non-replication has been eliminated.

## 14. Is any result dependent on ambiguous motif features?

No ambiguous M2_EXTENDED motif features were used in the primary or secondary frozen analysis. The primary M2_CORE contains only conservative aggregate proxies. Rapid forwarding was frozen as an adjacent incoming-to-outgoing event within 0–3600 seconds, not as an exact motif or causal flow pattern.

However, no preregistered feature ablation was run, so the marginal contribution of each M2_CORE feature cannot be identified. The important conclusion is that the aggregate M2_CORE increment is too small and HGB-unstable even without adding the ambiguous extended motifs. The positive result that survives is M1, not a motif result.

## 15. Did any leakage or preregistration violation occur?

No known primary leakage or post-result protocol change was identified.

Passed QA and protocol controls include:

- discovery features use event timestamps strictly before cutoff;
- future outcomes are physically/logically separated and evaluation-only;
- feature/outcome keys are one-to-one with zero mismatches;
- score7 aggregate counts reconcile exactly with event/family/direction totals;
- transformers, target scaling, imputation, and feature scaling are fit on fitting cutoffs only;
- chronological split; no random wallet-cutoff split;
- no wallet address or raw counterparty ID feature;
- no external label access;
- `results/RUN_MANIFEST.json` records `primary_protocol_changed_after_test=false` and `wash_label_accessed=false`.

Two deviations/limitations are explicitly disclosed:

1. **Pre-result materialization amendment:** independent 7-day token/internal counts were compactly materialized before primary model/target results. The amendment changed the input aggregate only, not the scientific protocol.
2. **Reporting-only code repair:** the first auxiliary confound-audit generation had an index-alignment bug. It was corrected and the full result package was regenerated. The bug affected reporting-only confound calculations, not the model fits, target, split, thresholds, primary metrics, bootstrap intervals, or result selection. The corrected files are the only files used here.

Additional limitations are not violations: all Ridge alphas selected the top grid value `100`; August is one held-out cutoff; and repeated wallets dominate the test.

## 16. What did Astra6's hostile review identify?

Astra6's post-result review (`reports/ASTRA6_POSTHOC_CRITIQUE.json`) agreed that the frozen pipeline was internally coherent and that M1 improved under Ridge, but identified the following threats:

- M1 is a mixture of recency, burstiness, turnover, gap dynamics, and autoregressive activity persistence, not a clean test of temporal organization;
- M2's `0.134%` Ridge increment is below the frozen 2% gate and is not HGB-robust;
- structural variables are strong activity/degree proxies;
- only one held-out August cutoff limits temporal generalization;
- repeated wallets dominate the test, so the result is mainly within-wallet forecasting;
- alpha=100 at the boundary limits the interpretation of the Ridge tuning result;
- aggregate QA is reassuring but is not a substitute for independent re-audit of every upstream event query.

The review recommended no external-label opening under the frozen rule and a new preregistered design before any future validation.

## 17. Which claims survive the red-team review?

The following bounded claims survive:

- OW-010B is a predictive future-behavior-change study, not a causal or external-category detection study.
- The discovery cohort is leakage-safe under the documented OW-010A contract and contains 47,575 history-eligible wallet-cutoff rows across the three cutoffs.
- Under the frozen Ridge protocol, M1 reduces August multivariate standardized loss relative to M0.
- The M1 improvement is positive across the fixed activity, native-inflow, degree, and high-activity-tail audits.
- The M1 direction is also present descriptively for repeated and unseen/no-prior-eligible-row wallets.
- The M2 structural increment is small, below the preregistered gate, and not robust across Ridge and HGB.
- Negative controls do not reproduce the intended M1/M2 gain.

The following claims do **not** survive:

- M2 demonstrates meaningful or robust structural information beyond M1.
- The result establishes an independent structural mechanism rather than activity/recency-related proxies.
- The result generalizes across many future time periods.
- The result demonstrates identity-level or cross-wallet generalization.
- The scalar `S7` is a distinct anomaly construct.
- The M1 gain specifically identifies temporal organization.
- Any claim about wash-trading, illicit activity, external labels, or external validity.

## 18. Is a Temporal GNN now scientifically justified?

**No.** The pre-GNN signal test did not meet the preregistered structural support rule. M2_CORE was below the 2% gate and failed model-family robustness. A GNN would add complexity before establishing that simple structural features contain a stable incremental signal, violating the stated falsification-first sequence.

## 19. Should OW-010C external wash-label validation be opened?

**No.** OW-010C remains closed. Opening it would over-interpret a positive M1 predictive result and a failed M2 structural test. The current result is not a validated external-category detector. Any future opening requires a new protocol decision after a preregistered design revision, not a post-result rescue.

## 20. Final decision

```text
NO_GO_OPENWORLD_STRUCTURAL_SIGNAL
```

Operational disposition: **do not open OW-010C; do not build a GNN; do not start LLM latent-strategy inference; do not tune the current branch after seeing August.**

A future continuation, if desired, should be a new preregistered design that:

1. separates recent-activity autoregression from temporal organization;
2. residualizes or otherwise controls structural proxies against activity/degree without using the present test result to choose the method;
3. adds predeclared temporal replication rather than relying on one held-out cutoff;
4. records a wider predeclared alpha/model budget or explicitly treats the current Ridge result as a boundary-limited pilot;
5. keeps any external-label validation separate and one-shot after the revised signal test.

This report stops at OW-010B as required.

---

## Artifact index

- `preregistration/ASTRA6_PREREGISTRATION_ADVICE.json`
- `preregistration/CODEX_DESIGN_REVIEW.md`
- `preregistration/OW010B_PREREGISTRATION.md`
- `preregistration/PREREGISTRATION_MANIFEST.json`
- `data/FEATURE_SET_REGISTRY.json`
- `data/TARGET_SPECIFICATION.md`
- `data/SPLIT_MANIFEST.json`
- `data/DATA_QA.md`
- `results/primary_metrics.csv`
- `results/incremental_gain.csv`
- `results/per_cutoff_metrics.csv`
- `results/per_dimension_incremental.csv`
- `results/bootstrap_intervals.csv`
- `results/confound_audit.csv`
- `results/negative_control_results.csv`
- `results/wallet_overlap_audit.csv`
- `results/wallet_stratum_metrics.csv`
- `results/scalar_surprise_incremental.csv`
- `reports/ASTRA6_POSTHOC_CRITIQUE.json`
- `reports/OW010B_RED_TEAM_REPORT.md`
- `reports/CODEX_RESPONSE_TO_CRITIQUE.md`
- `reports/OW010B_DECISION.md`
