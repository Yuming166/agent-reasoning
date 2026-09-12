-- Bounded pull: wallet_asof_features_v1 monthly snapshots (May-Aug 2022) for
-- temporal-persistence analysis. Each row uses a 90-day lookback before its
-- own snapshot_date; labels use the following 30 days. Partition filter required.
SELECT *
FROM `ictdata-507912.exgraph.wallet_asof_features_v1`
WHERE snapshot_date IN ('2022-05-01','2022-06-01','2022-07-01','2022-08-01')
