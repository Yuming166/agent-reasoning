-- OW-010A leakage-safe discovery features.
-- Grain: (anchor_wallet, cutoff_time).  Every mapped anchor is retained,
-- including anchors with no activity in a window.  All event joins are
-- strictly event_timestamp < cutoff_time; no future table is referenced.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`
OPTIONS(
  description='OW-010A discovery-only wallet by cutoff feature table; all values are computed from event_timestamp < cutoff_time; missingness is not globally zero-filled'
)
AS
WITH mapping AS (
  SELECT
    LOWER(ethereum_address) AS anchor_wallet,
    ANY_VALUE(exgraph_node_id) AS anchor_exgraph_node_id
  FROM `ictdata-507912.exgraph.exgraph_x_matches_v1`
  WHERE ethereum_address IS NOT NULL
    AND exgraph_node_id IS NOT NULL
  GROUP BY anchor_wallet
),
cutoffs AS (
  SELECT cutoff_time
  FROM UNNEST([
    TIMESTAMP('2022-06-01 00:00:00+00'),
    TIMESTAMP('2022-07-01 00:00:00+00'),
    TIMESTAMP('2022-08-01 00:00:00+00')
  ]) AS cutoff_time
),
grid AS (
  SELECT m.anchor_wallet, m.anchor_exgraph_node_id, c.cutoff_time
  FROM mapping AS m CROSS JOIN cutoffs AS c
),
first_event AS (
  SELECT anchor_wallet, MIN(event_timestamp) AS first_event_timestamp
  FROM `ictdata-507912.exgraph.openworld_anchor_events_v1`
  WHERE event_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND event_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
  GROUP BY anchor_wallet
),
window_events AS (
  SELECT
    g.anchor_wallet,
    g.anchor_exgraph_node_id,
    g.cutoff_time,
    e.anchor_event_identity,
    e.event_identity,
    e.event_timestamp,
    e.block_number,
    e.transaction_index,
    e.event_index,
    e.trace_address_json,
    e.direction,
    e.event_family,
    e.counterparty_identity,
    e.counterparty_is_exgraph_mapped,
    e.native_value,
    e.token_contract_address
  FROM grid AS g
  LEFT JOIN `ictdata-507912.exgraph.openworld_anchor_events_v1` AS e
    ON e.anchor_wallet = g.anchor_wallet
   AND e.event_timestamp >= TIMESTAMP('2022-05-01 00:00:00+00')
   AND e.event_timestamp < TIMESTAMP('2022-08-01 00:00:00+00')
   AND e.event_timestamp >= TIMESTAMP_SUB(g.cutoff_time, INTERVAL 30 DAY)
   AND e.event_timestamp < g.cutoff_time
),
event_agg AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    COUNTIF(event_identity IS NOT NULL) AS history_event_count_30d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL, event_identity, NULL)) AS history_unique_event_count_30d,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 1 HOUR)) AS event_count_1h,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 6 HOUR)) AS event_count_6h,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 1 DAY)) AS event_count_1d,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY)) AS event_count_7d,
    COUNTIF(event_identity IS NOT NULL) AS event_count_30d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 1 DAY), event_identity, NULL)) AS unique_event_count_1d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY), event_identity, NULL)) AS unique_event_count_7d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL, DATE(event_timestamp), NULL)) AS active_days_30d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL, TIMESTAMP_TRUNC(event_timestamp, HOUR), NULL)) AS active_hours_30d,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND event_family = 'external_tx') AS native_event_count_7d,
    COUNTIF(event_identity IS NOT NULL AND event_family = 'external_tx') AS native_event_count_30d,
    COUNTIF(event_identity IS NOT NULL AND event_family = 'token_transfer') AS token_event_count_30d,
    COUNTIF(event_identity IS NOT NULL AND event_family = 'internal_trace') AS internal_event_count_30d,
    COUNTIF(event_identity IS NOT NULL AND direction = 'incoming') AS incoming_event_count_30d,
    COUNTIF(event_identity IS NOT NULL AND direction = 'outgoing') AS outgoing_event_count_30d,
    COUNTIF(event_identity IS NOT NULL AND direction = 'self') AS self_event_count_30d,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND direction = 'incoming') AS incoming_event_count_7d,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND direction = 'outgoing') AS outgoing_event_count_7d,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND direction = 'self') AS self_event_count_7d,
    SUM(IF(event_identity IS NOT NULL AND event_family = 'external_tx' AND direction = 'incoming', native_value, CAST(NULL AS BIGNUMERIC))) AS native_inflow_30d,
    SUM(IF(event_identity IS NOT NULL AND event_family = 'external_tx' AND direction = 'outgoing', native_value, CAST(NULL AS BIGNUMERIC))) AS native_outflow_30d,
    SUM(IF(event_identity IS NOT NULL AND event_family = 'external_tx' AND direction = 'incoming', native_value, CAST(NULL AS BIGNUMERIC)))
      - SUM(IF(event_identity IS NOT NULL AND event_family = 'external_tx' AND direction = 'outgoing', native_value, CAST(NULL AS BIGNUMERIC))) AS native_netflow_30d,
    AVG(IF(event_identity IS NOT NULL AND event_family = 'external_tx', native_value, CAST(NULL AS BIGNUMERIC))) AS native_value_mean_30d,
    MAX(IF(event_identity IS NOT NULL AND event_family = 'external_tx', native_value, CAST(NULL AS BIGNUMERIC))) AS native_value_max_30d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL AND event_family = 'token_transfer', token_contract_address, NULL)) AS token_contract_diversity_30d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL AND event_family = 'token_transfer', CONCAT(COALESCE(token_contract_address, '<NULL_CONTRACT>'), '|', COALESCE(CAST(event_index AS STRING), '<NULL_INDEX>')), NULL)) AS token_item_diversity_30d,
    SAFE_DIVIDE(COUNTIF(event_identity IS NOT NULL AND event_family = 'external_tx'), COUNTIF(event_identity IS NOT NULL)) AS native_event_ratio_30d,
    SAFE_DIVIDE(COUNTIF(event_identity IS NOT NULL AND event_family = 'token_transfer'), COUNTIF(event_identity IS NOT NULL)) AS token_event_ratio_30d,
    SAFE_DIVIDE(COUNTIF(event_identity IS NOT NULL AND event_family = 'internal_trace'), COUNTIF(event_identity IS NOT NULL)) AS internal_event_ratio_30d,
    COUNT(DISTINCT IF(event_identity IS NOT NULL AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY), DATE(event_timestamp), NULL)) AS active_days_7d
  FROM window_events
  GROUP BY anchor_wallet, anchor_exgraph_node_id, cutoff_time
),
cp_rows AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    counterparty_identity,
    COUNTIF(event_timestamp < TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY)) AS prior_23d_event_count,
    COUNTIF(event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY)) AS score_7d_event_count,
    COUNTIF(event_timestamp < TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND direction = 'incoming') AS prior_incoming_count,
    COUNTIF(event_timestamp < TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND direction = 'outgoing') AS prior_outgoing_count,
    COUNTIF(event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND direction = 'incoming') AS score_incoming_count,
    COUNTIF(event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY) AND direction = 'outgoing') AS score_outgoing_count,
    LOGICAL_OR(counterparty_is_exgraph_mapped) AS counterparty_is_mapped
  FROM window_events
  WHERE event_identity IS NOT NULL AND counterparty_identity IS NOT NULL
  GROUP BY anchor_wallet, anchor_exgraph_node_id, cutoff_time, counterparty_identity
),
cp_rows_with_total AS (
  SELECT
    c.*,
    SUM(prior_23d_event_count + score_7d_event_count) OVER (
      PARTITION BY anchor_wallet, cutoff_time
    ) AS total_counterparty_events_30d
  FROM cp_rows AS c
),
cp_agg AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    COUNT(*) AS unique_counterparties_30d,
    COUNTIF(counterparty_is_mapped) AS mapped_counterparties_30d,
    COUNTIF(NOT counterparty_is_mapped) AS unmapped_counterparties_30d,
    COUNTIF(score_7d_event_count > 0) AS score_unique_counterparties_7d,
    COUNTIF(prior_23d_event_count > 0) AS prior_unique_counterparties_23d,
    COUNTIF(score_7d_event_count > 0 AND prior_23d_event_count = 0) AS new_counterparties_7d,
    COUNTIF(score_7d_event_count > 0 AND prior_23d_event_count > 0) AS repeat_counterparties_7d,
    COUNTIF(prior_incoming_count > 0 AND prior_outgoing_count > 0) AS reciprocal_counterparties_prior_23d,
    COUNTIF((prior_incoming_count + score_incoming_count) > 0 AND (prior_outgoing_count + score_outgoing_count) > 0) AS reciprocal_counterparties_30d,
    -SUM(SAFE_DIVIDE(prior_23d_event_count + score_7d_event_count, total_counterparty_events_30d) * LOG(SAFE_DIVIDE(prior_23d_event_count + score_7d_event_count, total_counterparty_events_30d))) AS counterparty_entropy_30d
  FROM cp_rows_with_total
  GROUP BY anchor_wallet, anchor_exgraph_node_id, cutoff_time
),
ordered_events AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    event_identity,
    event_timestamp,
    direction,
    LEAD(event_timestamp) OVER (
      PARTITION BY anchor_wallet, cutoff_time
      ORDER BY event_timestamp, block_number, transaction_index, event_index, trace_address_json, anchor_event_identity
    ) AS next_event_timestamp,
    LEAD(direction) OVER (
      PARTITION BY anchor_wallet, cutoff_time
      ORDER BY event_timestamp, block_number, transaction_index, event_index, trace_address_json, anchor_event_identity
    ) AS next_direction
  FROM window_events
  WHERE event_identity IS NOT NULL
),
gap_agg AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    AVG(TIMESTAMP_DIFF(next_event_timestamp, event_timestamp, SECOND)) AS inter_event_gap_mean_sec_30d,
    STDDEV_POP(TIMESTAMP_DIFF(next_event_timestamp, event_timestamp, SECOND)) AS inter_event_gap_std_sec_30d,
    APPROX_QUANTILES(TIMESTAMP_DIFF(next_event_timestamp, event_timestamp, SECOND), 100)[OFFSET(50)] AS inter_event_gap_median_sec_30d,
    MIN(TIMESTAMP_DIFF(next_event_timestamp, event_timestamp, SECOND)) AS inter_event_gap_min_sec_30d,
    MAX(TIMESTAMP_DIFF(next_event_timestamp, event_timestamp, SECOND)) AS inter_event_gap_max_sec_30d,
    COUNTIF(direction = 'incoming' AND next_direction = 'outgoing' AND TIMESTAMP_DIFF(next_event_timestamp, event_timestamp, SECOND) BETWEEN 0 AND 3600) AS rapid_forwarding_adjacent_count_30d
  FROM ordered_events
  WHERE next_event_timestamp IS NOT NULL
  GROUP BY anchor_wallet, anchor_exgraph_node_id, cutoff_time
),
hour_counts AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    TIMESTAMP_TRUNC(event_timestamp, HOUR) AS event_hour,
    COUNT(*) AS hour_event_count,
    COUNT(DISTINCT IF(direction = 'incoming' AND counterparty_identity IS NOT NULL, counterparty_identity, NULL)) AS hour_fan_in_cp,
    COUNT(DISTINCT IF(direction = 'outgoing' AND counterparty_identity IS NOT NULL, counterparty_identity, NULL)) AS hour_fan_out_cp
  FROM window_events
  WHERE event_identity IS NOT NULL
    AND event_timestamp >= TIMESTAMP_SUB(cutoff_time, INTERVAL 7 DAY)
  GROUP BY anchor_wallet, anchor_exgraph_node_id, cutoff_time, event_hour
),
hour_agg AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    MAX(hour_event_count) AS max_events_per_active_hour_7d,
    AVG(hour_event_count) AS mean_events_per_active_hour_7d,
    STDDEV_POP(hour_event_count) AS std_events_per_active_hour_7d,
    MAX(hour_fan_in_cp) AS max_fan_in_counterparties_per_hour_7d,
    MAX(hour_fan_out_cp) AS max_fan_out_counterparties_per_hour_7d
  FROM hour_counts
  GROUP BY anchor_wallet, anchor_exgraph_node_id, cutoff_time
),
joined AS (
  SELECT
    g.anchor_wallet,
    g.anchor_exgraph_node_id,
    g.cutoff_time,
    TIMESTAMP_SUB(g.cutoff_time, INTERVAL 30 DAY) AS history_start,
    TIMESTAMP_SUB(g.cutoff_time, INTERVAL 7 DAY) AS score_start,
    g.cutoff_time AS history_end,
    IF(fe.first_event_timestamp IS NOT NULL AND fe.first_event_timestamp < g.cutoff_time, TRUE, FALSE) AS observed_before_cutoff,
    fe.first_event_timestamp,
    ea.* EXCEPT(anchor_wallet, anchor_exgraph_node_id, cutoff_time),
    ca.* EXCEPT(anchor_wallet, anchor_exgraph_node_id, cutoff_time),
    ga.* EXCEPT(anchor_wallet, anchor_exgraph_node_id, cutoff_time),
    ha.* EXCEPT(anchor_wallet, anchor_exgraph_node_id, cutoff_time)
  FROM grid AS g
  LEFT JOIN first_event AS fe USING (anchor_wallet)
  LEFT JOIN event_agg AS ea USING (anchor_wallet, anchor_exgraph_node_id, cutoff_time)
  LEFT JOIN cp_agg AS ca USING (anchor_wallet, anchor_exgraph_node_id, cutoff_time)
  LEFT JOIN gap_agg AS ga USING (anchor_wallet, anchor_exgraph_node_id, cutoff_time)
  LEFT JOIN hour_agg AS ha USING (anchor_wallet, anchor_exgraph_node_id, cutoff_time)
)
SELECT
  j.* EXCEPT(
    unique_counterparties_30d, mapped_counterparties_30d, unmapped_counterparties_30d,
    score_unique_counterparties_7d, prior_unique_counterparties_23d,
    new_counterparties_7d, repeat_counterparties_7d,
    reciprocal_counterparties_prior_23d, reciprocal_counterparties_30d,
    counterparty_entropy_30d, rapid_forwarding_adjacent_count_30d,
    max_events_per_active_hour_7d, max_fan_in_counterparties_per_hour_7d,
    max_fan_out_counterparties_per_hour_7d
  ),
  COALESCE(unique_counterparties_30d, 0) AS unique_counterparties_30d,
  COALESCE(mapped_counterparties_30d, 0) AS mapped_counterparties_30d,
  COALESCE(unmapped_counterparties_30d, 0) AS unmapped_counterparties_30d,
  COALESCE(score_unique_counterparties_7d, 0) AS score_unique_counterparties_7d,
  COALESCE(prior_unique_counterparties_23d, 0) AS prior_unique_counterparties_23d,
  COALESCE(new_counterparties_7d, 0) AS new_counterparties_7d,
  COALESCE(repeat_counterparties_7d, 0) AS repeat_counterparties_7d,
  COALESCE(reciprocal_counterparties_prior_23d, 0) AS reciprocal_counterparties_prior_23d,
  COALESCE(reciprocal_counterparties_30d, 0) AS reciprocal_counterparties_30d,
  COALESCE(counterparty_entropy_30d, 0.0) AS counterparty_entropy_30d,
  COALESCE(rapid_forwarding_adjacent_count_30d, 0) AS rapid_forwarding_adjacent_count_30d,
  COALESCE(max_events_per_active_hour_7d, 0) AS max_events_per_active_hour_7d,
  COALESCE(max_fan_in_counterparties_per_hour_7d, 0) AS max_fan_in_counterparties_per_hour_7d,
  COALESCE(max_fan_out_counterparties_per_hour_7d, 0) AS max_fan_out_counterparties_per_hour_7d,
  IF(history_event_count_30d = 0, 'TRUE_ZERO', 'OBSERVED_ACTIVITY') AS history_activity_status,
  IF(event_count_7d = 0, 'TRUE_ZERO', 'OBSERVED_ACTIVITY') AS score_activity_status,
  'OBSERVED_FULL_WINDOW' AS history_window_coverage_status,
  'DISCOVERY_ONLY' AS data_role,
  'UNSUPPORTED' AS temporal_cycle_status,
  'UNSUPPORTED' AS split_merge_status,
  IF(native_event_count_30d = 0, 'NOT_APPLICABLE', 'OBSERVED') AS native_amount_status,
  IF(token_event_count_30d = 0, 'NOT_APPLICABLE', 'UNSUPPORTED_CROSS_ASSET_AGGREGATION') AS token_quantity_status,
  '2026-09-18_ow010a_v1' AS feature_version
FROM joined AS j;
