-- Group C: as-of matched-matched directed edge list at cutoff 2022-09-01.
-- Window: 90-day lookback [2022-06-03, 2022-09-01) UTC (strictly before cutoff),
-- matching wallet_asof_features_20220901 semantics. Primary event families only
-- (external_tx + token_transfer), counterparty_present, no self-transactions.
-- Rows are aggregated by (u, v, direction, calendar month) with event-count
-- weight so the same bounded pull supports both the full rolling-window graph
-- and monthly temporal snapshots (Jun/Jul/Aug 2022). No future data.
SELECT
  target_exgraph_node_id AS u,
  counterparty_exgraph_node_id AS v,
  direction,
  FORMAT_DATE('%Y-%m', DATE(block_timestamp)) AS month,
  COUNT(*) AS weight
FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
WHERE block_timestamp >= TIMESTAMP('2022-06-03')
  AND block_timestamp <  TIMESTAMP('2022-09-01')
  AND sequence_role = 'primary'
  AND counterparty_present
  AND NOT self_transaction
  AND target_exgraph_node_id IS NOT NULL
  AND counterparty_exgraph_node_id IS NOT NULL
GROUP BY 1, 2, 3, 4
