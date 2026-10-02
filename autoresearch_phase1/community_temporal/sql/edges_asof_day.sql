-- COMM group: day-level bounded pull of matched-matched primary directed edges
-- over [2022-03-03, 2022-09-01) UTC. One pull supports exact reconstruction of
-- every per-cutoff as-of graph with lookback [t-90d, t):
--   cutoff 2022-06-01 -> [2022-03-03, 2022-06-01)
--   cutoff 2022-07-01 -> [2022-04-02, 2022-07-01)
--   cutoff 2022-08-01 -> [2022-05-03, 2022-08-01)
--   cutoff 2022-09-01 -> [2022-06-03, 2022-09-01)
-- Identical filters to groupC_temporal_graph/sql/edges_asof.sql
-- (sequence_role='primary', counterparty_present, not self_transaction,
-- both endpoints EX-Graph-mapped), plus calendar month/day grouping so the same
-- bounded pull also reproduces Group C's calendar-month slices (Jun/Jul/Aug).
-- Frozen protocol: research/audit/temporal_protocol.yaml v1.0.
SELECT
  target_exgraph_node_id AS u,
  counterparty_exgraph_node_id AS v,
  direction,
  FORMAT_DATE('%Y-%m', DATE(block_timestamp)) AS month,
  FORMAT_DATE('%Y-%m-%d', DATE(block_timestamp)) AS day,
  COUNT(*) AS weight
FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
WHERE block_timestamp >= TIMESTAMP('2022-03-03')
  AND block_timestamp <  TIMESTAMP('2022-09-01')
  AND sequence_role = 'primary'
  AND counterparty_present
  AND NOT self_transaction
  AND target_exgraph_node_id IS NOT NULL
  AND counterparty_exgraph_node_id IS NOT NULL
GROUP BY 1, 2, 3, 4, 5
