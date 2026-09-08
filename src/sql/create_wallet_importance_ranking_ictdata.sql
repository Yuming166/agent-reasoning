-- Ranked wallet-selection table: P3 as-of importance proxy, one row per
-- active-in-future wallet per snapshot. Partitioned by snapshot_date.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.wallet_importance_ranking_v1`
PARTITION BY snapshot_date
CLUSTER BY target_address AS
SELECT
  snapshot_date, target_address, target_exgraph_node_id,
  evt_cnt_90d, cp_distinct_90d, cp_entropy_90d, cp_new_rate_30d,
  cp_reciprocity_90d, self_tx_rate_90d, token_hhi_90d, token_distinct_90d,
  active_days_90d, fwd30_evt_cnt, fwd30_cp_distinct, fwd30_new_cp,
  importance_proxy_p3,
  ROW_NUMBER() OVER (PARTITION BY snapshot_date
                     ORDER BY importance_proxy_p3 DESC) AS p3_rank,
  PERCENT_RANK() OVER (PARTITION BY snapshot_date
                       ORDER BY importance_proxy_p3) AS p3_percentile
FROM `ictdata-507912.exgraph.wallet_asof_features_v1`
WHERE fwd30_evt_cnt > 0;
