# OW-009 candidate attrition and substrate diagnosis

**Audit date:** 2026-09-18
**Label status:** blind to EX-Graph wash-trading labels; no label file/table was read.
**Detector status:** no detector, threshold, matching rule, or latent-strategy track was optimized.

## Executive conclusion

OW-009 did not test the intended full `(wallet, cutoff_time)` population. Its local input is a day-level projection that already requires primary events, a present counterparty, non-self transactions, and both endpoints EX-Graph-mapped. The code then keeps only `direction=outgoing`, and only after that applies `active_days>=3` and `events>=10` in a 30-day window. This explains the 370/282/359 strict counts.

The largest single upstream stage is local-artifact observability before cutoff, which removes 16,243/15,518/15,002 wallets at June/July/August. The largest explicit OW-009 predicate drop is `hist_active_days>=3` (3,344/2,663/2,454); `hist_events>=10` is next. The existing all-primary 90-day compact table shows 16,326/15,554/14,557 wallets at `active_days>=3 AND events>=10`, so the project has enough substrate for a later rerun if the compact event/as-of table is rebuilt correctly.

**Final status: `DESIGN_REVISION_NEEDED` with current local representation `SUBSTRATE_UNDERPOWERED`.** This is not a method-level NO-GO and not READY_FOR_RERUN.

## 1. Exact OW-009 dependency chain

```text
11,836,196 sequence rows (BigQuery metadata; not downloaded by OW-009)
  -> edges_asof_day.sql: primary + counterparty_present + non-self + both endpoints mapped
  -> 142,300 day-level (u,v,direction,day) aggregate rows in edges_day_20220303_20220901.csv
  -> temporal_structure_residual.py filters direction=outgoing
  -> 30-day history [t-30d,t), group by u
  -> hist_active_days >= 3 AND hist_events >= 10 (strict)
  -> left-join prior/score aggregates and fillna(0); no score-window eligibility filter
  -> calculate structural features for every remaining row; no null filter
  -> materialize future outcome rows for every discovery wallet for evaluation only; outcomes do not feed ranking or matching
  -> rank fixed structure_residual and select ceil(5% N)
  -> 1:5 nearest controls from the same candidate pool excluding treated
  -> report future outcomes for selected treated/control rows; future activity is not required for entry
```

Source SQL and row-generating code are preserved in the output manifest and the code/query locations in `candidate_attrition_by_cutoff.csv`.

### BigQuery raw-row and unique-wallet cross-check (aggregate-only; no raw export)

| cutoff | raw_sequence_rows_pre_cutoff | unique_endpoint_wallets_pre_cutoff_all_roles | unique_endpoint_wallets_upstream_accepted | accepted_target_wallets | accepted_counterparty_wallets | upstream_accepted_rows |
| --- | --- | --- | --- | --- | --- | --- |
| 2022-06-01 | 7095200 | 20461 | 11532 | 11532 | 11532 | 158770 |
| 2022-07-01 | 8671849 | 20818 | 12241 | 12241 | 12241 | 190352 |
| 2022-08-01 | 10344286 | 21123 | 12747 | 12747 | 12747 | 229940 |

These counts establish the missing early stages: raw sequence rows and unique endpoint wallets before the local `edges_day` projection. The query read only bounded aggregate counts; it did not export event rows or read external labels. The full-window accepted upstream condition has 266,998 sequence rows and 13,147 unique endpoint nodes, whereas the local day-level file contains 142,300 aggregate rows and 13,020 endpoint nodes because its pull starts on 2022-03-03 and performs daily pair aggregation.

## 2. Strict attrition table

| cutoff | stage | wallets_before | wallets_after | n_removed | percent_removed | cumulative_percent_remaining | exact_filter_condition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2022-06-01 | all_mapped_wallets | 27613 | 27613 | 0 | 0.0 | 100.0 | released twitter_matching.csv unique node_id |
| 2022-06-01 | source_artifact_observed_before_cutoff_any_role | 27613 | 11370 | 16243 | 58.8237 | 41.1763 | u OR v appears in local edges_day artifact with day < t |
| 2022-06-01 | 30d_history_visible_any_role | 11370 | 6033 | 5337 | 46.9393 | 21.8484 | u OR v appears in [t-30d,t) |
| 2022-06-01 | 30d_history_outgoing_source_wallet | 6033 | 4403 | 1630 | 27.0181 | 15.9454 | direction == outgoing; wallet is u; [t-30d,t) |
| 2022-06-01 | history_active_days_ge_3 | 4403 | 1059 | 3344 | 75.9482 | 3.8352 | hist_active_days >= 3 |
| 2022-06-01 | history_events_ge_10 | 1059 | 370 | 689 | 65.0614 | 1.3399 | hist_events >= 10 |
| 2022-06-01 | score_window_activity_diagnostic_no_filter | 370 | 370 | 0 | 0.0 | 1.3399 | No score_events/score_active_days predicate in code; diagnostics: score_events>0 and score_active_days>0 |
| 2022-06-01 | feature_complete_after_fillna | 370 | 370 | 0 | 0.0 | 1.3399 | left joins then fillna(0.0) |
| 2022-06-01 | structural_feature_complete | 370 | 370 | 0 | 0.0 | 1.3399 | fixed-length novelty/growth/reciprocity/burst arrays; no null filter |
| 2022-06-01 | top5_percent_anomaly_cohort | 370 | 19 | 351 | 94.8649 | 0.0688 | ceil(0.05 * candidate_count), rank by fixed structure_residual |
| 2022-06-01 | matched_treated_cohort | 19 | 19 | 0 | 0.0 | 0.0688 | 1:5 nearest-neighbor matching; treated retained if 5 controls assigned |
| 2022-06-01 | unique_matched_controls | 95 | 72 | 23 | 24.2105 | 0.2607 | unique control node IDs among 5 assignments per treated |
| 2022-07-01 | all_mapped_wallets | 27613 | 27613 | 0 | 0.0 | 100.0 | released twitter_matching.csv unique node_id |
| 2022-07-01 | source_artifact_observed_before_cutoff_any_role | 27613 | 12095 | 15518 | 56.1982 | 43.8018 | u OR v appears in local edges_day artifact with day < t |
| 2022-07-01 | 30d_history_visible_any_role | 12095 | 4869 | 7226 | 59.7437 | 17.633 | u OR v appears in [t-30d,t) |
| 2022-07-01 | 30d_history_outgoing_source_wallet | 4869 | 3474 | 1395 | 28.6506 | 12.581 | direction == outgoing; wallet is u; [t-30d,t) |
| 2022-07-01 | history_active_days_ge_3 | 3474 | 811 | 2663 | 76.6552 | 2.937 | hist_active_days >= 3 |
| 2022-07-01 | history_events_ge_10 | 811 | 282 | 529 | 65.2281 | 1.0213 | hist_events >= 10 |
| 2022-07-01 | score_window_activity_diagnostic_no_filter | 282 | 282 | 0 | 0.0 | 1.0213 | No score_events/score_active_days predicate in code; diagnostics: score_events>0 and score_active_days>0 |
| 2022-07-01 | feature_complete_after_fillna | 282 | 282 | 0 | 0.0 | 1.0213 | left joins then fillna(0.0) |
| 2022-07-01 | structural_feature_complete | 282 | 282 | 0 | 0.0 | 1.0213 | fixed-length novelty/growth/reciprocity/burst arrays; no null filter |
| 2022-07-01 | top5_percent_anomaly_cohort | 282 | 15 | 267 | 94.6809 | 0.0543 | ceil(0.05 * candidate_count), rank by fixed structure_residual |
| 2022-07-01 | matched_treated_cohort | 15 | 15 | 0 | 0.0 | 0.0543 | 1:5 nearest-neighbor matching; treated retained if 5 controls assigned |
| 2022-07-01 | unique_matched_controls | 75 | 53 | 22 | 29.3333 | 0.1919 | unique control node IDs among 5 assignments per treated |
| 2022-08-01 | all_mapped_wallets | 27613 | 27613 | 0 | 0.0 | 100.0 | released twitter_matching.csv unique node_id |
| 2022-08-01 | source_artifact_observed_before_cutoff_any_role | 27613 | 12611 | 15002 | 54.3295 | 45.6705 | u OR v appears in local edges_day artifact with day < t |
| 2022-08-01 | 30d_history_visible_any_role | 12611 | 4468 | 8143 | 64.5706 | 16.1808 | u OR v appears in [t-30d,t) |
| 2022-08-01 | 30d_history_outgoing_source_wallet | 4468 | 3352 | 1116 | 24.9776 | 12.1392 | direction == outgoing; wallet is u; [t-30d,t) |
| 2022-08-01 | history_active_days_ge_3 | 3352 | 898 | 2454 | 73.21 | 3.2521 | hist_active_days >= 3 |
| 2022-08-01 | history_events_ge_10 | 898 | 359 | 539 | 60.0223 | 1.3001 | hist_events >= 10 |
| 2022-08-01 | score_window_activity_diagnostic_no_filter | 359 | 359 | 0 | 0.0 | 1.3001 | No score_events/score_active_days predicate in code; diagnostics: score_events>0 and score_active_days>0 |
| 2022-08-01 | feature_complete_after_fillna | 359 | 359 | 0 | 0.0 | 1.3001 | left joins then fillna(0.0) |
| 2022-08-01 | structural_feature_complete | 359 | 359 | 0 | 0.0 | 1.3001 | fixed-length novelty/growth/reciprocity/burst arrays; no null filter |
| 2022-08-01 | top5_percent_anomaly_cohort | 359 | 18 | 341 | 94.9861 | 0.0652 | ceil(0.05 * candidate_count), rank by fixed structure_residual |
| 2022-08-01 | matched_treated_cohort | 18 | 18 | 0 | 0.0 | 0.0652 | 1:5 nearest-neighbor matching; treated retained if 5 controls assigned |
| 2022-08-01 | unique_matched_controls | 90 | 66 | 24 | 26.6667 | 0.239 | unique control node IDs among 5 assignments per treated |

The full machine-readable table, including code locations and scientific rationale, is `candidate_attrition_by_cutoff.csv`.

Largest stage drops in the strict audit:

| cutoff | stage | n_removed | exact_filter_condition |
| --- | --- | --- | --- |
| 2022-06-01 | source_artifact_observed_before_cutoff_any_role | 16243 | u OR v appears in local edges_day artifact with day < t |
| 2022-07-01 | source_artifact_observed_before_cutoff_any_role | 15518 | u OR v appears in local edges_day artifact with day < t |
| 2022-08-01 | source_artifact_observed_before_cutoff_any_role | 15002 | u OR v appears in local edges_day artifact with day < t |
| 2022-08-01 | 30d_history_visible_any_role | 8143 | u OR v appears in [t-30d,t) |
| 2022-07-01 | 30d_history_visible_any_role | 7226 | u OR v appears in [t-30d,t) |
| 2022-06-01 | 30d_history_visible_any_role | 5337 | u OR v appears in [t-30d,t) |
| 2022-06-01 | history_active_days_ge_3 | 3344 | hist_active_days >= 3 |
| 2022-07-01 | history_active_days_ge_3 | 2663 | hist_active_days >= 3 |

## 3. Filter classification

| classification | n_filters |
| --- | --- |
| SCIENTIFIC_DESIGN | 8 |
| POSSIBLY_OVERRESTRICTIVE | 3 |
| ESSENTIAL | 3 |
| IMPLEMENTATION_CONVENIENCE | 2 |
| BUG_RISK | 2 |
| LEGACY | 1 |

The full registry with exact conditions, locations, and rationale is `filter_registry.csv`. The important population-changing filters are the upstream `both endpoints mapped` requirement, the code's `outgoing` role filter, and the 3-day/10-event history thresholds. There is no score-window activity filter and no future-outcome eligibility filter in the executable code.

## 4. Discovery, future evaluation, and matched cohorts

- **Discovery cohort:** the strict rows after `[t-30d,t)`, `direction=outgoing`, `active_days>=3`, and `events>=10`: 370/282/359. In the intended repaired population, this should instead be an outer-joined wallet×cutoff cohort built from all mapped wallets and all pre-cutoff roles.
- **Future-evaluation cohort:** current `future_outcomes()` is called for every discovery wallet and creates zeros for absent future events; it does not filter discovery. Because the local artifact covers June/July/August 7/30-day future intervals, current evaluation coverage is numerically the full discovery cohort, not a future-active subset.
- **Matched-analysis cohort:** Top-5% treated wallets for the fixed `structure_residual` method that receive five controls. In the current candidate sizes, the control pool is large enough that all treated wallets receive five assignments; this does not mean balance is acceptable.

## 5. Matching diagnostic

| variant | cutoff | method | top_n | candidate_count | treated_entering | treated_matched | unmatched | unique_controls | control_assignments | reused_assignments | fallback_reuse | reuse_rate | before_max_smd | after_max_smd | before_failed_covariates | after_failed_covariates | before_smd__log_hist_events | before_smd__hist_active_days | before_smd__log_hist_counterparties | before_smd__log_score_events | before_smd__score_active_days | before_smd__activity_change | after_smd__log_hist_events | after_smd__hist_active_days | after_smd__log_hist_counterparties | after_smd__log_score_events | after_smd__score_active_days | after_smd__activity_change | matching_constraint_causing_failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| registered_strict_10_events | 2022-06-01 | structure_residual | 19 | 370 | 19 | 19 | 0 | 72 | 95 | 23 | 23 | 0.24210526315789474 | 1.0033768281582693 | 0.6575162098968281 | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;score_active_days;activity_change | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;score_active_days;activity_change | 1.0033768281582693 | 0.841866600687188 | 0.8533505051226338 | 0.7080000431186215 | 0.819061045525962 | 0.6814818647864704 | 0.5338776761397322 | 0.18901322592300637 | 0.30503112830826135 | 0.11232576140989589 | 0.14421390869305892 | 0.6575162098968281 | no hard failure; post-match balance fails where after SMD > 0.10 |
| registered_strict_10_events | 2022-07-01 | structure_residual | 15 | 282 | 15 | 15 | 0 | 53 | 75 | 22 | 22 | 0.29333333333333333 | 1.4036358530354258 | 0.8698818475726455 | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;score_active_days;activity_change | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;activity_change | 1.1846156160427637 | 0.8716461139916376 | 1.4036358530354258 | 0.9626493278561257 | 0.8851614685530177 | 0.5015257209575442 | 0.7012230110124443 | 0.2818085252623578 | 0.8698818475726455 | 0.37612350104904524 | 0.05945612883110831 | 0.19798148703699328 | no hard failure; post-match balance fails where after SMD > 0.10 |
| registered_strict_10_events | 2022-08-01 | structure_residual | 18 | 359 | 18 | 18 | 0 | 66 | 90 | 24 | 24 | 0.26666666666666666 | 1.265714591313399 | 0.4705666538519481 | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;score_active_days;activity_change | log_hist_events;hist_active_days;log_hist_counterparties;log_score_events;score_active_days;activity_change | 0.543152043881332 | 0.44783317205914047 | 1.265714591313399 | 0.5327316669608944 | 0.6044594950546877 | 0.7987285370494968 | 0.4281466770588186 | 0.17489342814143974 | 0.4705666538519481 | 0.13388357510478924 | 0.12034048549601796 | 0.39653482715840127 | no hard failure; post-match balance fails where after SMD > 0.10 |

The current procedure has no caliper and no hard balance rejection. Its nearest-neighbor assignment therefore reports all strict treated wallets as matched even when post-match absolute SMD exceeds 0.10. Across the three strict cutoffs, control reuse is 0.242--0.293 of assignments and unique controls are 53--72 for 15--19 treated wallets. The recurrent post-match failures are log_hist_events, log_hist_counterparties, log_score_events, and activity_change; this is a support/balance failure, not a reason to tune the method. See `matching_diagnostics.csv` for covariate-level before/after SMD.

## 6. Feature availability

| feature | time_window_relative_to_cutoff | missing_rate_before_zero_fill | requires_raw_event_level_data | requires_future_data | implementation_note |
| --- | --- | --- | --- | --- | --- |
| counterparty_novelty | prior vs [t-7d,t) | 0.0 | no | no | set difference of day-level counterparties; discovery cohort n=370 |
| counterparty_growth | prior vs [t-7d,t) | 0.0 | no | no | log score CP minus scaled prior CP; discovery cohort n=370 |
| reciprocity_change | prior vs [t-7d,t) | 0.0 | no | no | reverse directed pair test; no event-family semantics; discovery cohort n=370 |
| score_burstiness | [t-7d,t) | 0.0 | no (day-level only) | no | max daily weight / mean active-day weight; no sub-day gaps; discovery cohort n=370 |
| event_timestamp | not present in local artifact | 1.0 | yes | no | collapsed to calendar day; discovery cohort n=370 |
| event_family | not present in local artifact | 1.0 | yes | no | external/token/internal distinction lost; discovery cohort n=370 |
| native_value | not present in local artifact | 1.0 | yes | no | amount semantics lost; discovery cohort n=370 |
| token_contract_or_id | not present in local artifact | 1.0 | yes | no | asset identity lost; discovery cohort n=370 |
| internal_trace_identity | not present in local artifact | 1.0 | yes | no | trace path/subtrace semantics lost; discovery cohort n=370 |
| inter_event_gap | not present in local artifact | 1.0 | yes | no | requires timestamped event sequence; discovery cohort n=370 |
| rapid_forwarding | not present in local artifact | 1.0 | yes | no | requires timestamped directed events; discovery cohort n=370 |
| event_composition | not present in local artifact | 1.0 | yes | no | native/token/internal ratios unavailable; discovery cohort n=370 |

The current code has no score-window eligibility predicate. Before `fillna(0)`, the strict candidates with no score-window event are 29.73%/25.53%/23.68% at June/July/August; they remain in discovery with zero-filled score features. Prior-window absence is 1.08%/1.42%/0.84%. This is not future leakage, but it is an important coverage distinction.
| cutoff | missing_rate_before_zero_fill | wallet_coverage_after_current_code |
| --- | --- | --- |
| 2022-06-01 | 0.2972972972972973 | 1.0 |
| 2022-07-01 | 0.2553191489361702 | 1.0 |
| 2022-08-01 | 0.23676880222841226 | 1.0 |

The current local representation preserves only day, directed pair, role direction, and count. It loses sub-day ordering, transaction/event identity, event family, native/token amounts, token identity, and trace identity. Consequently it cannot support a faithful rapid-forward, inter-event-gap, event-composition, or amount-aware analysis. The three fixed rank/change baselines (`volume_activity`, `fine_temporal_activity`, `simple_temporal`) are available from the same day-level aggregates; their availability does not restore the missing event semantics.

## 7. Cohort sensitivity

Local 30-day outgoing diagnostic with no score-window filter and history `active_days>=3`:
| cutoff | history_min_events | n_wallets | top5_n |
| --- | --- | --- | --- |
| 2022-06-01 | 1 | 1059 | 53 |
| 2022-06-01 | 3 | 1059 | 53 |
| 2022-06-01 | 5 | 778 | 39 |
| 2022-06-01 | 10 | 370 | 19 |
| 2022-06-01 | 20 | 130 | 7 |
| 2022-07-01 | 1 | 811 | 41 |
| 2022-07-01 | 3 | 811 | 41 |
| 2022-07-01 | 5 | 588 | 30 |
| 2022-07-01 | 10 | 282 | 15 |
| 2022-07-01 | 20 | 89 | 5 |
| 2022-08-01 | 1 | 898 | 45 |
| 2022-08-01 | 3 | 898 | 45 |
| 2022-08-01 | 5 | 680 | 34 |
| 2022-08-01 | 10 | 359 | 18 |
| 2022-08-01 | 20 | 149 | 8 |

Existing all-primary 90-day compact as-of table, same activity/event thresholds:
| cutoff | history_min_events | n_wallets | top5_n |
| --- | --- | --- | --- |
| 2022-06-01 | 1 | 17600 | 880 |
| 2022-06-01 | 3 | 17600 | 880 |
| 2022-06-01 | 5 | 17311 | 866 |
| 2022-06-01 | 10 | 16326 | 817 |
| 2022-06-01 | 20 | 14653 | 733 |
| 2022-07-01 | 1 | 16905 | 846 |
| 2022-07-01 | 3 | 16905 | 846 |
| 2022-07-01 | 5 | 16590 | 830 |
| 2022-07-01 | 10 | 15554 | 778 |
| 2022-07-01 | 20 | 13783 | 690 |
| 2022-08-01 | 1 | 15922 | 797 |
| 2022-08-01 | 3 | 15922 | 797 |
| 2022-08-01 | 5 | 15590 | 780 |
| 2022-08-01 | 10 | 14557 | 728 |
| 2022-08-01 | 20 | 12680 | 634 |

The complete score-window sensitivity grid is in `cohort_sensitivity.csv`; it is diagnostic and was not selected by future or label results.

## 8. BigQuery repair specification and restart plan

See `BIGQUERY_FEATURE_SPEC.md` for exact wallet×cutoff grain, half-open intervals, event keys, feature families, and separate evaluation outcomes. See `SUBSTRATE_REPAIR_PLAN.md` for the no-tuning restart sequence.

## 9. Required final answers

**1. Why did ~27,613 become ~370/282/359?**  Because the local input had already narrowed the population to primary, counterparty-present, non-self, both-endpoints-mapped day-level edges; the code then kept outgoing-source wallets, a 30-day history, active_days>=3, and events>=10.

**2. Which single filter caused largest attrition?**  As a single observed-population stage, source-artifact observability before cutoff is largest: it removes 16,243/15,518/15,002 wallets at June/July/August. Among explicit OW-009 code predicates, active_days>=3 is largest (3,344/2,663/2,454 removed), followed by events>=10.

**3. Which filters are scientifically necessary?**  Strict as-of cutoff, explicit event identity/deduplication, and declared history windows. Counterparty-present/non-self/primary-only are only necessary for particular estimands, not for all wallet behavioral discovery.

**4. Which are artifacts or unnecessarily restrictive?**  Both-endpoints-mapped, outgoing-only role filtering, day aggregation for event-level questions, and active_days>=3/events>=10 as universal discovery eligibility.

**5. Future-conditioned eligibility or leakage risk?**  No future-conditioned entry filter exists in OW-009. `future_outcomes()` is materialized for every discovery wallet before method evaluation, but it is not used for ranking or matching; only selected rows enter the reported treated/control comparison, and absent future events become zeros. The repaired table must preserve this separation.

**6. How large is true discovery cohort before future evaluation/matching?**  The direct BigQuery pre-cutoff endpoint universe is 20,461/20,818/21,123 wallets before the local matched-matched projection, and 11,532/12,241/12,747 after the upstream primary/counterparty-present/non-self/both-mapped predicate. The existing all-primary 90-day compact table has 17,600/16,905/15,922 wallets at active_days>=3 and 16,326/15,554/14,557 at active_days>=3 plus events>=10. Exact full all-event 30-day discovery counts require the new compact CTAS.

**7. Why did matching fail |SMD|<=0.10?**  Matching has no caliper or balance rejection; Top-5% treated wallets are often in activity tails, so nearest controls remain imbalanced. The failure is balance/support, not lack of assigned control rows.

**8. What is missing locally?**  Sub-day timestamps, event-family labels, transaction/event identity, native/token amounts, token contract/id, internal trace identity, and full in/out role coverage.

**9. What should be materialized?**  A BigQuery wallet×cutoff feature table from timestamped native/token/internal events with 1h/6h/1d/7d/30d and prior-23d windows, plus a separate future-outcomes table.

**10. Can >=2,000 be obtained?**  Yes, plausibly after restoring the full target-touching substrate: existing 90-day as-of data already has roughly 19--20k wallets per cutoff and >14k at the strict 90-day activity/event rule. It is not plausible from the current matched-matched outgoing day-level extract without changing the population.

**11. Should >=2,000 remain unchanged?**  Keep it unchanged for now as a conservative restart gate; it is a heuristic precision/coverage gate, not a demonstrated power calculation. Revisit only by preregistered amendment after the repaired cohort is measured.

**12. Current OW-009 status?**  DESIGN_REVISION_NEEDED, with the current local representation SUBSTRATE_UNDERPOWERED. Not METHOD_NO_GO, not IMPLEMENTATION_BUG as the sole diagnosis, and not READY_FOR_RERUN.
