-- OW-010A future outcomes.  Evaluation-only and physically separate from the
-- discovery feature table.  This table is never referenced by ranking or
-- discovery eligibility SQL.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1`
OPTIONS(
  description='OW-010A evaluation-only future outcomes; generated separately from discovery features and never used for discovery eligibility or ranking'
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
history_cp AS (
  SELECT DISTINCT
    g.anchor_wallet,
    g.cutoff_time,
    e.counterparty_identity
  FROM grid AS g
  JOIN `ictdata-507912.exgraph.openworld_anchor_events_v1` AS e
    ON e.anchor_wallet = g.anchor_wallet
   AND e.event_timestamp >= TIMESTAMP_SUB(g.cutoff_time, INTERVAL 30 DAY)
   AND e.event_timestamp < g.cutoff_time
   AND e.event_timestamp >= TIMESTAMP('2022-05-01 00:00:00+00')
   AND e.event_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
  WHERE e.counterparty_identity IS NOT NULL
),
future_events AS (
  SELECT
    g.anchor_wallet,
    g.anchor_exgraph_node_id,
    g.cutoff_time,
    e.anchor_event_identity,
    e.event_identity,
    e.event_timestamp,
    e.event_family,
    e.direction,
    e.counterparty_identity,
    e.counterparty_is_exgraph_mapped,
    e.native_value
  FROM grid AS g
  LEFT JOIN `ictdata-507912.exgraph.openworld_anchor_events_v1` AS e
    ON e.anchor_wallet = g.anchor_wallet
   AND e.event_timestamp >= g.cutoff_time
   AND e.event_timestamp < TIMESTAMP_ADD(g.cutoff_time, INTERVAL 30 DAY)
   AND e.event_timestamp >= TIMESTAMP('2022-06-01 00:00:00+00')
   AND e.event_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
),
future_agg AS (
  SELECT
    anchor_wallet,
    anchor_exgraph_node_id,
    cutoff_time,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY)) AS future7_event_count,
    COUNTIF(event_identity IS NOT NULL) AS future30_event_count,
    COUNT(DISTINCT IF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY), DATE(event_timestamp), NULL)) AS future7_active_days,
    COUNT(DISTINCT IF(event_identity IS NOT NULL, DATE(event_timestamp), NULL)) AS future30_active_days,
    COUNT(DISTINCT IF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY), counterparty_identity, NULL)) AS future7_unique_counterparties,
    COUNT(DISTINCT IF(event_identity IS NOT NULL, counterparty_identity, NULL)) AS future30_unique_counterparties,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND event_family = 'external_tx') AS future7_native_events,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND event_family = 'token_transfer') AS future7_token_events,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND event_family = 'internal_trace') AS future7_internal_events,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND direction = 'incoming') AS future7_incoming_events,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND direction = 'outgoing') AS future7_outgoing_events,
    COUNTIF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND direction = 'self') AS future7_self_events,
    SUM(IF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND event_family = 'external_tx' AND direction = 'incoming', native_value, CAST(NULL AS BIGNUMERIC))) AS future7_native_inflow,
    SUM(IF(event_identity IS NOT NULL AND event_timestamp < TIMESTAMP_ADD(cutoff_time, INTERVAL 7 DAY) AND event_family = 'external_tx' AND direction = 'outgoing', native_value, CAST(NULL AS BIGNUMERIC))) AS future7_native_outflow
  FROM future_events
  GROUP BY anchor_wallet, anchor_exgraph_node_id, cutoff_time
),
new_cp AS (
  SELECT
    f.anchor_wallet,
    f.anchor_exgraph_node_id,
    f.cutoff_time,
    COUNT(DISTINCT IF(
      f.event_identity IS NOT NULL
      AND f.event_timestamp < TIMESTAMP_ADD(f.cutoff_time, INTERVAL 7 DAY)
      AND f.counterparty_identity IS NOT NULL
      AND h.counterparty_identity IS NULL,
      f.counterparty_identity,
      NULL
    )) AS future7_new_counterparties,
    COUNT(DISTINCT IF(
      f.event_identity IS NOT NULL
      AND f.counterparty_identity IS NOT NULL
      AND h.counterparty_identity IS NULL,
      f.counterparty_identity,
      NULL
    )) AS future30_new_counterparties
  FROM future_events AS f
  LEFT JOIN history_cp AS h
    ON h.anchor_wallet = f.anchor_wallet
   AND h.cutoff_time = f.cutoff_time
   AND h.counterparty_identity = f.counterparty_identity
  GROUP BY f.anchor_wallet, f.anchor_exgraph_node_id, f.cutoff_time
)
SELECT
  fa.*,
  COALESCE(nc.future7_new_counterparties, 0) AS future7_new_counterparties,
  COALESCE(nc.future30_new_counterparties, 0) AS future30_new_counterparties,
  IF(fa.future30_event_count = 0, 'TRUE_ZERO', 'OBSERVED_ACTIVITY') AS future30_activity_status,
  'OBSERVED_FULL_WINDOW' AS future7_window_coverage_status,
  'OBSERVED_FULL_WINDOW' AS future30_window_coverage_status,
  TRUE AS evaluation_only,
  'EVALUATION_ONLY' AS data_role,
  '2026-09-18_ow010a_v1' AS outcome_version
FROM future_agg AS fa
LEFT JOIN new_cp AS nc
  USING (anchor_wallet, anchor_exgraph_node_id, cutoff_time);
