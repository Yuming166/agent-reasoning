-- Selection-layer evaluation table (Jul snapshot / Aug test window):
-- joins P3 as-of features with P2 June trigger proxy and a cheap
-- global-popularity baseline MRR per wallet over outgoing August events.
-- MRR: for each outgoing primary event with present, non-self counterparty,
-- rank of actual counterparty among candidates ordered by global popularity
-- (all-target outgoing counts, test window).
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.selection_eval_v1` AS
WITH aug AS (
  SELECT target_address, counterparty_address,
         target_sequence_index, block_timestamp
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-08-01')
    AND block_timestamp <  TIMESTAMP('2022-09-01')
    AND sequence_role = 'primary'
    AND direction = 'outgoing'
    AND counterparty_present AND NOT self_transaction
),
pop AS (   -- global candidate popularity over the same test window
  SELECT counterparty_address AS cand,
         ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS pop_rank,
         COUNT(*) AS pop_cnt
  FROM aug GROUP BY 1
),
ev AS (
  SELECT a.target_address, a.counterparty_address, a.target_sequence_index,
         p.pop_rank
  FROM aug a JOIN pop p ON p.cand = a.counterparty_address
),
mrr AS (
  SELECT target_address,
         COUNT(*) AS aug_out_events,
         AVG(1.0/pop_rank) AS pop_mrr,
         COUNTIF(pop_rank > 100) AS hard_events_pop100plus,
         SAFE_DIVIDE(COUNTIF(pop_rank <= 100), COUNT(*)) AS pop_recall100
  FROM ev GROUP BY 1
)
SELECT
  f.snapshot_date,
  f.target_address,
  f.target_exgraph_node_id,
  f.evt_cnt_90d, f.cp_distinct_90d, f.cp_entropy_90d, f.cp_new_rate_30d,
  f.cp_reciprocity_90d, f.token_hhi_90d, f.token_distinct_90d,
  f.self_tx_rate_90d,
  f.fwd30_evt_cnt, f.fwd30_cp_distinct, f.fwd30_new_cp,
  f.importance_proxy_p3, f.p3_rank, f.p3_percentile,
  t.trigger_score_p2, t.trigger_strong_pairs, t.trigger_pairs,
  m.aug_out_events, m.pop_mrr, m.hard_events_pop100plus, m.pop_recall100,
  -- selection headroom = room for an agent to improve over popularity:
  (1.0 - IFNULL(m.pop_mrr,1.0)) AS headroom_vs_pop
FROM `ictdata-507912.exgraph.wallet_importance_ranking_v1` f
LEFT JOIN `ictdata-507912.exgraph.wallet_trigger_proxy_v1` t
  ON t.target_address = f.target_address
LEFT JOIN mrr m ON m.target_address = f.target_address
WHERE f.snapshot_date = DATE '2022-08-01';
