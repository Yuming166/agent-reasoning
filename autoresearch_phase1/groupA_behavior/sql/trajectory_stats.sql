-- Per-wallet trajectory statistics at cutoff 2022-09-01, strictly within the
-- as-of lookback window [2022-06-03 00:00:00, 2022-09-01 00:00:00) UTC,
-- matching wallet_asof_features_20220901 semantics (sequence_role='primary',
-- dedup on (target, block_number, transaction_index, event_index)).
-- Output is one compact row per wallet (<=18,519 rows); no event-level export.
WITH targets AS (
  SELECT DISTINCT target_address
  FROM `ictdata-507912.exgraph.wallet_asof_features_20220901`
  WHERE snapshot_date = '2022-09-01'
),
ev AS (
  SELECT e.target_address, e.block_timestamp, e.block_number,
         e.transaction_index, e.event_index, e.direction, e.self_transaction,
         e.counterparty_present, e.event_family
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901` e
  JOIN targets t ON t.target_address = e.target_address
  WHERE e.block_timestamp >= TIMESTAMP('2022-06-03')
    AND e.block_timestamp <  TIMESTAMP('2022-09-01')
    AND e.sequence_role = 'primary'
),
dedup AS (
  SELECT DISTINCT target_address, block_timestamp, block_number,
         transaction_index, event_index, direction, self_transaction,
         counterparty_present, event_family
  FROM ev
),
seq AS (
  SELECT target_address, block_timestamp,
         LAG(block_timestamp) OVER (
           PARTITION BY target_address
           ORDER BY block_timestamp, block_number, transaction_index, event_index
         ) AS prev_ts
  FROM dedup
),
gaps AS (
  SELECT target_address,
         IFNULL(TIMESTAMP_DIFF(block_timestamp, prev_ts, SECOND) / 86400.0, NULL) AS gap_days,
         block_timestamp
  FROM seq
),
agg AS (
  SELECT target_address,
    COUNT(*) AS n_events_90d,
    COUNT(DISTINCT DATE(block_timestamp)) AS active_days_90d_traj,
    DATE_DIFF(MAX(DATE(block_timestamp)), MIN(DATE(block_timestamp)), DAY) AS active_span_days_traj,
    TIMESTAMP_DIFF(MIN(block_timestamp), TIMESTAMP('2022-06-03'), DAY) AS first_event_offset_days,
    TIMESTAMP_DIFF(TIMESTAMP('2022-09-01'), MAX(block_timestamp), DAY) AS last_event_recency_days,
    AVG(gap_days) AS mean_gap_days,
    APPROX_QUANTILES(gap_days, 2)[OFFSET(1)] AS median_gap_days,
    MAX(gap_days) AS max_gap_days,
    STDDEV(gap_days) AS std_gap_days,
    COUNTIF(gap_days > 7) AS n_gaps_gt7d,
    SUM(CASE WHEN gap_days IS NOT NULL THEN 1 ELSE 0 END) AS n_gaps
  FROM gaps
  GROUP BY target_address
),
dir AS (
  SELECT target_address,
    COUNTIF(direction = 'outgoing' AND counterparty_present AND NOT self_transaction) AS out_interact_90d,
    COUNTIF(direction = 'incoming' AND counterparty_present AND NOT self_transaction) AS in_interact_90d,
    COUNTIF(event_family = 'external_tx') AS native_90d,
    COUNTIF(event_family = 'token_transfer') AS token_90d
  FROM dedup
  GROUP BY target_address
)
SELECT a.target_address,
  a.n_events_90d, a.active_days_90d_traj, a.active_span_days_traj,
  a.first_event_offset_days, a.last_event_recency_days,
  a.mean_gap_days, a.median_gap_days, a.max_gap_days, a.std_gap_days,
  a.n_gaps_gt7d, a.n_gaps,
  d.out_interact_90d, d.in_interact_90d, d.native_90d, d.token_90d
FROM agg a
JOIN dir d USING (target_address)
