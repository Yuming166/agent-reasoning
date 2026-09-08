-- P4 router dataset: as-of features (P3/P5) + P1 occlusion + P2 trigger,
-- joined to the future-30d popularity-headroom label per snapshot.
-- Train = 2022-06-01, validation = 2022-07-01, frozen test = 2022-08-01.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.router_dataset_v1` AS
SELECT
  f.snapshot_date, f.target_address, f.target_exgraph_node_id,
  f.target_is_x_matched,
  -- as-of features
  f.evt_cnt_90d, f.evt_out_90d, f.evt_in_90d, f.evt_self_90d,
  f.evt_native_90d, f.evt_token_90d, f.active_days_90d, f.tx_cnt_90d,
  f.active_span_days_90d,
  f.cp_distinct_90d, f.cp_out_distinct_90d, f.cp_in_distinct_90d,
  f.cp_out_interact_90d, f.cp_in_interact_90d, f.token_distinct_90d,
  f.cp_entropy_90d, f.cp_new_30d, f.cp_new_rate_30d, f.cp_both_dir_90d,
  f.cp_reciprocity_90d, f.self_tx_rate_90d, f.token_event_rate_90d,
  f.token_hhi_90d, f.events_per_active_day_90d,
  -- P1 / P2 scores (snapshot-specific; 0 when no bridge/trigger signal)
  COALESCE(p1.icf_score_p1, 0)     AS icf_score_p1,
  COALESCE(p1.bridges_events, 0)   AS p1_bridges_events,
  COALESCE(p2.trigger_score_p2, 0) AS trigger_score_p2,
  COALESCE(p2.trigger_strong_pairs,0) AS trigger_strong_pairs,
  -- labels
  COALESCE(h.fwd_out_events, 0)  AS y_fwd_out_events,
  COALESCE(h.headroom_sum, 0.0)  AS y_headroom_sum,
  COALESCE(h.hard_events, 0)     AS y_hard_events,
  COALESCE(h.pop_mrr, 1.0)       AS y_pop_mrr
FROM `ictdata-507912.exgraph.wallet_asof_features_v1` f
LEFT JOIN `ictdata-507912.exgraph.p1_wallet_icf_v2` p1
  ON p1.snapshot_date=f.snapshot_date AND p1.target_address=f.target_address
LEFT JOIN `ictdata-507912.exgraph.p2_trigger_v2` p2
  ON p2.snapshot_date=f.snapshot_date AND p2.target_address=f.target_address
LEFT JOIN `ictdata-507912.exgraph.wallet_future_headroom_v1` h
  ON h.snapshot_date=f.snapshot_date AND h.target_address=f.target_address
WHERE f.snapshot_date IN (DATE '2022-06-01', DATE '2022-07-01', DATE '2022-08-01');
