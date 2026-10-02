-- Group B: bounded label pull at cutoff 2022-09-01 from the frozen as-of table.
-- Labels = [2022-09-01, 2022-10-01) built by Group 0/1 SQL (fwd30_*).
-- Partition filter required; this reads only the 2022-09-01 partition of a
-- compact aggregated table (18,519 rows), NOT raw event tables.
SELECT
  target_address,
  fwd30_evt_cnt,
  fwd30_cp_distinct,
  fwd30_cp_out_distinct,
  fwd30_new_cp
FROM `ictdata-507912.exgraph.wallet_asof_features_20220901`
WHERE snapshot_date = '2022-09-01'
