-- Compact leakage-safe as-of aggregate for OW-010B.
-- No raw event rows are exported. The only retained rows are one row per
-- history-eligible (anchor_wallet, cutoff_time) with counts in [t-7d,t).
WITH eligible AS (
  SELECT anchor_wallet, anchor_exgraph_node_id, cutoff_time
  FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`
  WHERE history_event_count_30d >= 1
), score AS (
  SELECT
    g.anchor_wallet,
    g.anchor_exgraph_node_id,
    g.cutoff_time,
    COUNTIF(e.event_identity IS NOT NULL AND e.event_family = 'external_tx') AS score_external_native_7d,
    COUNTIF(e.event_identity IS NOT NULL AND e.event_family = 'token_transfer') AS score_token_7d,
    COUNTIF(e.event_identity IS NOT NULL AND e.event_family = 'internal_trace') AS score_internal_7d,
    COUNTIF(e.event_identity IS NOT NULL AND e.direction = 'incoming') AS score_incoming_7d,
    COUNTIF(e.event_identity IS NOT NULL AND e.direction = 'outgoing') AS score_outgoing_7d,
    COUNTIF(e.event_identity IS NOT NULL AND e.direction = 'self') AS score_self_7d,
    COUNTIF(e.event_identity IS NOT NULL) AS score_event_count_7d
  FROM eligible AS g
  LEFT JOIN `ictdata-507912.exgraph.openworld_anchor_events_v1` AS e
    ON e.anchor_wallet = g.anchor_wallet
   AND e.event_timestamp >= TIMESTAMP_SUB(g.cutoff_time, INTERVAL 7 DAY)
   AND e.event_timestamp < g.cutoff_time
   AND e.event_timestamp >= TIMESTAMP('2022-05-01 00:00:00+00')
   AND e.event_timestamp < TIMESTAMP('2022-08-01 00:00:00+00')
  GROUP BY g.anchor_wallet, g.anchor_exgraph_node_id, g.cutoff_time
)
SELECT * FROM score
