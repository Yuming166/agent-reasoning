-- Bounded pull: as-of matched-matched directed edge list for cutoff 2022-09-01,
-- restricted to the 90-day lookback [2022-06-03, 2022-09-01) UTC and to primary
-- events whose counterparty is an EX-Graph-matched node. Aggregated by
-- (u,v,direction) with event-count weight; output is compact (est. < 300k rows).
SELECT
  target_exgraph_node_id AS u,
  counterparty_exgraph_node_id AS v,
  direction,
  COUNT(*) AS weight
FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
WHERE block_timestamp >= TIMESTAMP('2022-06-03')
  AND block_timestamp <  TIMESTAMP('2022-09-01')
  AND sequence_role = 'primary'
  AND counterparty_present
  AND NOT self_transaction
  AND target_exgraph_node_id IS NOT NULL
  AND counterparty_exgraph_node_id IS NOT NULL
GROUP BY 1, 2, 3
