-- OW-010A population and coverage summary.  This query is discovery-only;
-- it reads no label table and does not use future outcomes.
WITH thresholds AS (
  SELECT * FROM UNNEST([
    STRUCT(1 AS min_history_events),
    STRUCT(3 AS min_history_events),
    STRUCT(5 AS min_history_events),
    STRUCT(10 AS min_history_events),
    STRUCT(20 AS min_history_events),
    STRUCT(50 AS min_history_events)
  ])
),
score_thresholds AS (
  SELECT * FROM UNNEST([
    STRUCT(0 AS min_score_events),
    STRUCT(1 AS min_score_events),
    STRUCT(3 AS min_score_events),
    STRUCT(5 AS min_score_events),
    STRUCT(10 AS min_score_events)
  ])
),
base AS (
  SELECT *
  FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`
),
section_history AS (
  SELECT
    'history_sensitivity' AS section,
    CAST(cutoff_time AS STRING) AS cutoff_time,
    CAST(t.min_history_events AS STRING) AS parameter_1,
    'none' AS parameter_2,
    CAST(COUNTIF(history_event_count_30d >= t.min_history_events) AS STRING) AS value,
    'mapped anchors retained in discovery table; history is [cutoff-30d,cutoff)' AS notes
  FROM base CROSS JOIN thresholds AS t
  GROUP BY cutoff_time, t.min_history_events
),
section_score AS (
  SELECT
    'score_window_sensitivity' AS section,
    CAST(cutoff_time AS STRING) AS cutoff_time,
    CAST(t.min_score_events AS STRING) AS parameter_1,
    'history>=1' AS parameter_2,
    CAST(COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= t.min_score_events) AS STRING) AS value,
    'score activity is [cutoff-7d,cutoff); no future activity is required' AS notes
  FROM base CROSS JOIN score_thresholds AS t
  GROUP BY cutoff_time, t.min_score_events
),
section_activity_days AS (
  SELECT
    'active_day_sensitivity' AS section,
    CAST(cutoff_time AS STRING) AS cutoff_time,
    CAST(x.min_active_days AS STRING) AS parameter_1,
    'history>=1' AS parameter_2,
    CAST(COUNTIF(history_event_count_30d >= 1 AND active_days_30d >= x.min_active_days) AS STRING) AS value,
    'active days are counted from event timestamps in the 30-day history window' AS notes
  FROM base CROSS JOIN UNNEST([STRUCT(0 AS min_active_days), STRUCT(1 AS min_active_days), STRUCT(2 AS min_active_days), STRUCT(3 AS min_active_days), STRUCT(5 AS min_active_days), STRUCT(10 AS min_active_days)]) AS x
  GROUP BY cutoff_time, x.min_active_days
),
section_roles AS (
  SELECT
    'direction_coverage' AS section,
    CAST(cutoff_time AS STRING) AS cutoff_time,
    'history>=1' AS parameter_1,
    'role' AS parameter_2,
    CAST(COUNTIF(history_event_count_30d >= 1 AND incoming_event_count_30d > 0 AND outgoing_event_count_30d = 0) AS STRING) AS value,
    'incoming_only' AS notes
  FROM base GROUP BY cutoff_time
  UNION ALL
  SELECT 'direction_coverage', CAST(cutoff_time AS STRING), 'history>=1', 'role', CAST(COUNTIF(history_event_count_30d >= 1 AND outgoing_event_count_30d > 0 AND incoming_event_count_30d = 0) AS STRING), 'outgoing_only' FROM base GROUP BY cutoff_time
  UNION ALL
  SELECT 'direction_coverage', CAST(cutoff_time AS STRING), 'history>=1', 'role', CAST(COUNTIF(history_event_count_30d >= 1 AND incoming_event_count_30d > 0 AND outgoing_event_count_30d > 0) AS STRING), 'both_direction' FROM base GROUP BY cutoff_time
  UNION ALL
  SELECT 'direction_coverage', CAST(cutoff_time AS STRING), 'history>=1', 'role', CAST(COUNTIF(history_event_count_30d >= 1 AND self_event_count_30d > 0) AS STRING), 'has_self_event' FROM base GROUP BY cutoff_time
),
section_mapping AS (
  SELECT
    'counterparty_mapping_coverage' AS section,
    CAST(cutoff_time AS STRING) AS cutoff_time,
    'history>=1' AS parameter_1,
    'counterparty_type' AS parameter_2,
    CAST(COUNTIF(history_event_count_30d >= 1 AND mapped_counterparties_30d > 0) AS STRING) AS value,
    'has_mapped_counterparty' AS notes
  FROM base GROUP BY cutoff_time
  UNION ALL
  SELECT 'counterparty_mapping_coverage', CAST(cutoff_time AS STRING), 'history>=1', 'counterparty_type', CAST(COUNTIF(history_event_count_30d >= 1 AND unmapped_counterparties_30d > 0) AS STRING), 'has_unmapped_counterparty' FROM base GROUP BY cutoff_time
  UNION ALL
  SELECT 'counterparty_mapping_coverage', CAST(cutoff_time AS STRING), 'history>=1', 'counterparty_type', CAST(COUNTIF(history_event_count_30d >= 1 AND unique_counterparties_30d > 0 AND mapped_counterparties_30d = unique_counterparties_30d) AS STRING), 'all_observed_counterparties_mapped' FROM base GROUP BY cutoff_time
),
section_observed AS (
  SELECT
    'observability' AS section,
    CAST(cutoff_time AS STRING) AS cutoff_time,
    'mapped_anchors' AS parameter_1,
    'pre_cutoff' AS parameter_2,
    CAST(COUNTIF(observed_before_cutoff) AS STRING) AS value,
    'any source event before cutoff; discovery table itself retains all anchors' AS notes
  FROM base GROUP BY cutoff_time
  UNION ALL
  SELECT 'observability', CAST(cutoff_time AS STRING), 'mapped_anchors', 'history_30d', CAST(COUNTIF(history_event_count_30d > 0) AS STRING), 'at least one history event' FROM base GROUP BY cutoff_time
)
SELECT * FROM section_history
UNION ALL SELECT * FROM section_score
UNION ALL SELECT * FROM section_activity_days
UNION ALL SELECT * FROM section_roles
UNION ALL SELECT * FROM section_mapping
UNION ALL SELECT * FROM section_observed
ORDER BY section, cutoff_time, parameter_1, notes;
