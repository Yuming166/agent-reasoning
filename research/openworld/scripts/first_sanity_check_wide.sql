-- OW-001 / OW-002: label-free transaction-level baselines.
-- The wash table is external evaluation only and is not used by the scores.
WITH base AS (
  SELECT
    LOWER(transaction_hash) AS tx_hash,
    MIN(block_timestamp) AS block_timestamp,
    COUNT(*) AS seq_rows,
    COUNT(DISTINCT target_exgraph_node_id) AS target_n,
    COUNT(DISTINCT counterparty_address) AS cp_n,
    COUNT(DISTINCT event_family) AS family_n,
    COUNTIF(direction = 'outgoing') AS outgoing_n,
    COUNTIF(direction = 'incoming') AS incoming_n,
    COUNTIF(self_transaction) AS self_n,
    COUNTIF(counterparty_present) AS cp_present_n
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
    AND transaction_hash IS NOT NULL
  GROUP BY tx_hash
), day_stats AS (
  SELECT
    DATE(block_timestamp) AS day,
    AVG(seq_rows) AS day_mean_seq,
    STDDEV_POP(seq_rows) AS day_sd_seq
  FROM base
  GROUP BY day
), labeled AS (
  SELECT
    b.*,
    DATE_TRUNC(DATE(b.block_timestamp), MONTH) AS month,
    IF(l.tx_hash IS NULL, 0, 1) AS external_label
  FROM base AS b
  LEFT JOIN `ictdata-507912.exgraph.openworld_wash_labels_v1` AS l
    USING (tx_hash)
), scored AS (
  SELECT
    l.*,
    'activity' AS score_name,
    LN(1.0 + CAST(seq_rows AS FLOAT64)) AS score
  FROM labeled AS l
  UNION ALL
  SELECT
    l.*,
    'counterparty_breadth' AS score_name,
    LN(1.0 + CAST(cp_n AS FLOAT64)) AS score
  FROM labeled AS l
  UNION ALL
  SELECT
    l.*,
    'structural_complexity' AS score_name,
    LN(1.0 + CAST(seq_rows AS FLOAT64))
      + 0.5 * LN(1.0 + CAST(target_n AS FLOAT64))
      + 0.5 * LN(1.0 + CAST(cp_n AS FLOAT64))
      + 0.25 * CAST(family_n AS FLOAT64) AS score
  FROM labeled AS l
  UNION ALL
  SELECT
    l.*,
    'directional_imbalance' AS score_name,
    SAFE_DIVIDE(ABS(outgoing_n - incoming_n), GREATEST(1, seq_rows)) AS score
  FROM labeled AS l
  UNION ALL
  SELECT
    l.*,
    'self_fraction' AS score_name,
    SAFE_DIVIDE(self_n, GREATEST(1, seq_rows)) AS score
  FROM labeled AS l
), ranked AS (
  SELECT
    s.*,
    ROW_NUMBER() OVER (
      PARTITION BY month, score_name
      ORDER BY score DESC, tx_hash
    ) AS score_rank
  FROM scored AS s
), ks AS (
  SELECT k FROM UNNEST([1000, 5000, 10000, 25000, 50000, 100000]) AS k
)
SELECT
  month,
  score_name,
  k,
  COUNT(*) AS n_transactions,
  SUM(external_label) AS positive_transactions,
  COUNTIF(score_rank <= k) AS top_k_transactions,
  SUM(IF(score_rank <= k, external_label, 0)) AS top_k_positive,
  SAFE_DIVIDE(SUM(IF(score_rank <= k, external_label, 0)), NULLIF(SUM(external_label), 0)) AS recall_at_k,
  SAFE_DIVIDE(SUM(IF(score_rank <= k, external_label, 0)), NULLIF(COUNTIF(score_rank <= k), 0)) AS precision_at_k,
  SAFE_DIVIDE(
    SAFE_DIVIDE(SUM(IF(score_rank <= k, external_label, 0)), NULLIF(COUNTIF(score_rank <= k), 0)),
    SAFE_DIVIDE(SUM(external_label), NULLIF(COUNT(*), 0))
  ) AS enrichment_at_k
FROM ranked
CROSS JOIN ks
GROUP BY month, score_name, k
ORDER BY month, score_name, k
