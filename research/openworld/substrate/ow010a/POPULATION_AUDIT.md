# OW-010A Population Audit

## Full event-level discovery population

The event-level table restores the declared `(wallet, cutoff)` population. Counts below are based on the materialized discovery feature table and are label-blind.

|cutoff|mapped|observed pre-cutoff|history >=1|history >=3|history >=5|history >=10|history >=20|score >=1 | history>=1|
|---|---|---|---|---|---|---|---|---|
|2022-06-01|27613|20461|17156|15647|14758|13130|11013|12525|
|2022-07-01|27613|20818|15736|14212|13200|11469|9172|9934|
|2022-08-01|27613|21123|14683|13020|11932|10294|8222|9562|


The full discovery grid has 27,613 rows per cutoff. If the analysis requires at least one history event, the discovery cohort is 17,156 / 15,736 / 14,683. If it requires at least one score-window event as well, it is 12,525 / 9,934 / 9,562. These are pre-cutoff conditions; they are not future-conditioned.

## Exact old OW-009 attrition

The following table reconstructs the frozen local OW-009 path from executable code and the local day-level artifact. It is intentionally kept separate from the repaired event-level table.

|cutoff|stage|before|after|removed|% removed|% remaining|condition|location|
|---|---|---|---|---|---|---|---|---|
|2022-06-01|all_mapped_wallets|27613|27613|0|0.0|100.0|released twitter_matching.csv unique node_id|vendor/EX-Graph-repo/twitter_matching.csv:1-27614|
|2022-06-01|source_artifact_observed_before_cutoff_any_role|27613|11370|16243|58.8237|41.1763|u OR v appears in local edges_day artifact with day < t|research/community_temporal/sql/edges_asof_day.sql:13-28|
|2022-06-01|30d_history_visible_any_role|11370|6033|5337|46.9393|21.8484|u OR v appears in [t-30d,t)|research/openworld/baselines/temporal_structure_residual.py:123-127; research/community_temporal/sql/edges_asof_day.sql:21-28|
|2022-06-01|30d_history_outgoing_source_wallet|6033|4403|1630|27.0181|15.9454|direction == outgoing; wallet is u; [t-30d,t)|research/openworld/baselines/temporal_structure_residual.py:540-550|
|2022-06-01|history_active_days_ge_3|4403|1059|3344|75.9482|3.8352|hist_active_days >= 3|research/openworld/baselines/temporal_structure_residual.py:129-137|
|2022-06-01|history_events_ge_10|1059|370|689|65.0614|1.3399|hist_events >= 10|research/openworld/baselines/temporal_structure_residual.py:134-137; constants:34-36|
|2022-06-01|score_window_activity_diagnostic_no_filter|370|370|0|0.0|1.3399|No score_events/score_active_days predicate in code; diagnostics: score_events>0 and score_active_days>0|research/openworld/baselines/temporal_structure_residual.py:141-150|
|2022-06-01|feature_complete_after_fillna|370|370|0|0.0|1.3399|left joins then fillna(0.0)|research/openworld/baselines/temporal_structure_residual.py:151-157|
|2022-06-01|structural_feature_complete|370|370|0|0.0|1.3399|fixed-length novelty/growth/reciprocity/burst arrays; no null filter|research/openworld/baselines/temporal_structure_residual.py:159-202|
|2022-06-01|top5_percent_anomaly_cohort|370|19|351|94.8649|0.0688|ceil(0.05 * candidate_count), rank by fixed structure_residual|research/openworld/baselines/temporal_structure_residual.py:383-385|
|2022-06-01|matched_treated_cohort|19|19|0|0.0|0.0688|1:5 nearest-neighbor matching; treated retained if 5 controls assigned|research/openworld/baselines/temporal_structure_residual.py:300-353|
|2022-06-01|unique_matched_controls|95|72|23|24.2105|0.2607|unique control node IDs among 5 assignments per treated|research/openworld/baselines/temporal_structure_residual.py:300-353|
|2022-07-01|all_mapped_wallets|27613|27613|0|0.0|100.0|released twitter_matching.csv unique node_id|vendor/EX-Graph-repo/twitter_matching.csv:1-27614|
|2022-07-01|source_artifact_observed_before_cutoff_any_role|27613|12095|15518|56.1982|43.8018|u OR v appears in local edges_day artifact with day < t|research/community_temporal/sql/edges_asof_day.sql:13-28|
|2022-07-01|30d_history_visible_any_role|12095|4869|7226|59.7437|17.633|u OR v appears in [t-30d,t)|research/openworld/baselines/temporal_structure_residual.py:123-127; research/community_temporal/sql/edges_asof_day.sql:21-28|
|2022-07-01|30d_history_outgoing_source_wallet|4869|3474|1395|28.6506|12.581|direction == outgoing; wallet is u; [t-30d,t)|research/openworld/baselines/temporal_structure_residual.py:540-550|
|2022-07-01|history_active_days_ge_3|3474|811|2663|76.6552|2.937|hist_active_days >= 3|research/openworld/baselines/temporal_structure_residual.py:129-137|
|2022-07-01|history_events_ge_10|811|282|529|65.2281|1.0213|hist_events >= 10|research/openworld/baselines/temporal_structure_residual.py:134-137; constants:34-36|
|2022-07-01|score_window_activity_diagnostic_no_filter|282|282|0|0.0|1.0213|No score_events/score_active_days predicate in code; diagnostics: score_events>0 and score_active_days>0|research/openworld/baselines/temporal_structure_residual.py:141-150|
|2022-07-01|feature_complete_after_fillna|282|282|0|0.0|1.0213|left joins then fillna(0.0)|research/openworld/baselines/temporal_structure_residual.py:151-157|
|2022-07-01|structural_feature_complete|282|282|0|0.0|1.0213|fixed-length novelty/growth/reciprocity/burst arrays; no null filter|research/openworld/baselines/temporal_structure_residual.py:159-202|
|2022-07-01|top5_percent_anomaly_cohort|282|15|267|94.6809|0.0543|ceil(0.05 * candidate_count), rank by fixed structure_residual|research/openworld/baselines/temporal_structure_residual.py:383-385|
|2022-07-01|matched_treated_cohort|15|15|0|0.0|0.0543|1:5 nearest-neighbor matching; treated retained if 5 controls assigned|research/openworld/baselines/temporal_structure_residual.py:300-353|
|2022-07-01|unique_matched_controls|75|53|22|29.3333|0.1919|unique control node IDs among 5 assignments per treated|research/openworld/baselines/temporal_structure_residual.py:300-353|
|2022-08-01|all_mapped_wallets|27613|27613|0|0.0|100.0|released twitter_matching.csv unique node_id|vendor/EX-Graph-repo/twitter_matching.csv:1-27614|
|2022-08-01|source_artifact_observed_before_cutoff_any_role|27613|12611|15002|54.3295|45.6705|u OR v appears in local edges_day artifact with day < t|research/community_temporal/sql/edges_asof_day.sql:13-28|
|2022-08-01|30d_history_visible_any_role|12611|4468|8143|64.5706|16.1808|u OR v appears in [t-30d,t)|research/openworld/baselines/temporal_structure_residual.py:123-127; research/community_temporal/sql/edges_asof_day.sql:21-28|
|2022-08-01|30d_history_outgoing_source_wallet|4468|3352|1116|24.9776|12.1392|direction == outgoing; wallet is u; [t-30d,t)|research/openworld/baselines/temporal_structure_residual.py:540-550|
|2022-08-01|history_active_days_ge_3|3352|898|2454|73.21|3.2521|hist_active_days >= 3|research/openworld/baselines/temporal_structure_residual.py:129-137|
|2022-08-01|history_events_ge_10|898|359|539|60.0223|1.3001|hist_events >= 10|research/openworld/baselines/temporal_structure_residual.py:134-137; constants:34-36|
|2022-08-01|score_window_activity_diagnostic_no_filter|359|359|0|0.0|1.3001|No score_events/score_active_days predicate in code; diagnostics: score_events>0 and score_active_days>0|research/openworld/baselines/temporal_structure_residual.py:141-150|
|2022-08-01|feature_complete_after_fillna|359|359|0|0.0|1.3001|left joins then fillna(0.0)|research/openworld/baselines/temporal_structure_residual.py:151-157|
|2022-08-01|structural_feature_complete|359|359|0|0.0|1.3001|fixed-length novelty/growth/reciprocity/burst arrays; no null filter|research/openworld/baselines/temporal_structure_residual.py:159-202|
|2022-08-01|top5_percent_anomaly_cohort|359|18|341|94.9861|0.0652|ceil(0.05 * candidate_count), rank by fixed structure_residual|research/openworld/baselines/temporal_structure_residual.py:383-385|
|2022-08-01|matched_treated_cohort|18|18|0|0.0|0.0652|1:5 nearest-neighbor matching; treated retained if 5 controls assigned|research/openworld/baselines/temporal_structure_residual.py:300-353|
|2022-08-01|unique_matched_controls|90|66|24|26.6667|0.239|unique control node IDs among 5 assignments per treated|research/openworld/baselines/temporal_structure_residual.py:300-353|


The strict path is therefore 370 / 282 / 359 before Top-5% ranking, with Top-5% treated counts 19 / 15 / 18. The event-level substrate is not the same population: it retains incoming, self, unmapped-counterparty and all three event families.

## Discovery, future evaluation, matched analysis

1. **Discovery cohort:** rows in `openworld_wallet_cutoff_features_v1`, with an explicitly declared history requirement if the eventual detector needs one. The table is not reduced to wallets with future activity.
2. **Future-evaluation cohort:** discovery rows joined to `openworld_wallet_cutoff_future_outcomes_v1` only after scores are frozen. The future table has 82,839 rows and all are `evaluation_only=TRUE`; for a history>=1 analysis the counts equal 17,156 / 15,736 / 14,683 because every grid row has an outcome record.
3. **Matched-analysis cohort:** the current OW-009 Top-5% treated rows for which the frozen local matcher returns five controls. This is 19 / 15 / 18 treated rows, not the discovery cohort.

## Scientific interpretation

The old collapse was not caused by feature completeness or structural-feature null filtering: those stages removed zero local candidates. It was caused upstream by a restrictive local substrate, then active-day and event-count eligibility. The largest single observed stage in the old strict path is local source-artifact observability before cutoff; among explicit OW-009 predicates, `active_days >= 3` is the largest removal.
