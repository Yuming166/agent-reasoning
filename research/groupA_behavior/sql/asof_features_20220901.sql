-- Bounded pull: wallet_asof_features_20220901, cutoff 2022-09-01 only.
-- All *_90d features use events in [2022-06-03, 2022-09-01); fwd30_* labels use
-- events in [2022-09-01, 2022-10-01). Partition filter required.
SELECT *
FROM `ictdata-507912.exgraph.wallet_asof_features_20220901`
WHERE snapshot_date = '2022-09-01'
