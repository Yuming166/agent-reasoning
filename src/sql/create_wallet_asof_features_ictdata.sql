-- As-of monthly wallet feature + future-label table for influence-aware
-- wallet selection (P3 difficulty/activity, P5 behavioural motifs; P2 trigger
-- proxy is in a separate bounded join query).
--
-- Leakage rule: every feature in *_90d uses only events strictly before
-- snapshot_date; every label in fwd30_* uses only events in
-- [snapshot_date, snapshot_date + 30 days). Router training snapshots are
-- May/June/July 2022; August is the frozen test snapshot.
--
-- Behavioural events = primary families (external_tx, token_transfer) only,
-- deduplicated on (target_address, block_number, transaction_index,
-- event_index, direction). internal_trace (auxiliary) is excluded to avoid
-- per-transaction event inflation.
CREATE TABLE IF NOT EXISTS `ictdata-507912.exgraph.wallet_asof_features_v1`
PARTITION BY snapshot_date
CLUSTER BY target_address AS
WITH snapshots AS (
  SELECT DATE(s) AS snapshot_date
  FROM UNNEST([
    DATE '2022-05-01', DATE '2022-06-01',
    DATE '2022-07-01', DATE '2022-08-01']) AS s
),
targets AS (
  SELECT DISTINCT target_address, target_exgraph_node_id
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-03-01')
    AND block_timestamp <  TIMESTAMP('2022-09-01')
),
events AS (
  SELECT
    target_address, target_exgraph_node_id,
    direction, counterparty_address, counterparty_present, self_transaction,
    event_family, block_timestamp, block_number, transaction_index,
    event_index, transaction_hash,
    token_contract_address, value, target_is_x_matched
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-02-01')   -- lookback buffer
    AND block_timestamp <  TIMESTAMP('2022-09-01')
    AND sequence_role = 'primary'
),
win AS (
  SELECT s.snapshot_date, t.target_address, t.target_exgraph_node_id,
         e.direction, e.counterparty_address, e.counterparty_present,
         e.self_transaction, e.event_family, e.block_timestamp,
         e.block_number, e.transaction_index, e.event_index, e.transaction_hash,
         e.token_contract_address, e.value, e.target_is_x_matched
  FROM snapshots s
  CROSS JOIN targets t
  JOIN events e
    ON e.target_address = t.target_address
   AND e.block_timestamp >= TIMESTAMP(DATETIME_SUB(s.snapshot_date, INTERVAL 90 DAY))
   AND e.block_timestamp <  TIMESTAMP(s.snapshot_date)
),
dedup AS (
  SELECT snapshot_date, target_address, target_exgraph_node_id, direction,
         counterparty_address, counterparty_present, self_transaction,
         event_family, block_timestamp, block_number, transaction_index,
         event_index, transaction_hash, token_contract_address, value,
         target_is_x_matched
  FROM win
  GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16
),
cp AS (   -- non-self, present-counterparty interactions
  SELECT * FROM dedup
  WHERE counterparty_present AND NOT self_transaction
),
feat AS (
  SELECT
    snapshot_date, target_address, ANY_VALUE(target_exgraph_node_id) AS target_exgraph_node_id,
    COUNT(*) AS evt_cnt_90d,
    COUNTIF(direction='outgoing') AS evt_out_90d,
    COUNTIF(direction='incoming') AS evt_in_90d,
    COUNTIF(self_transaction) AS evt_self_90d,
    COUNTIF(event_family='external_tx') AS evt_native_90d,
    COUNTIF(event_family='token_transfer') AS evt_token_90d,
    COUNT(DISTINCT DATE(block_timestamp)) AS active_days_90d,
    COUNT(DISTINCT CONCAT(block_number, ':', transaction_hash)) AS tx_cnt_90d,
    COUNT(DISTINCT counterparty_address) AS cp_distinct_90d,
    COUNTIF(counterparty_present AND NOT self_transaction
            AND direction='outgoing') AS cp_out_interact_90d,
    COUNTIF(counterparty_present AND NOT self_transaction
            AND direction='incoming') AS cp_in_interact_90d,
    COUNT(DISTINCT IF(direction='outgoing' AND counterparty_present
            AND NOT self_transaction, counterparty_address, NULL)) AS cp_out_distinct_90d,
    COUNT(DISTINCT IF(direction='incoming' AND counterparty_present
            AND NOT self_transaction, counterparty_address, NULL)) AS cp_in_distinct_90d,
    COUNT(DISTINCT token_contract_address) AS token_distinct_90d,
    COUNTIF(token_contract_address IS NULL) AS native_or_no_token_90d,
    DATE_DIFF(MAX(DATE(block_timestamp)), MIN(DATE(block_timestamp)), DAY) AS active_span_days_90d,
    ANY_VALUE(target_is_x_matched) AS target_is_x_matched
  FROM dedup GROUP BY 1,2
),
cp_entropy AS (   -- P3: counterparty-distribution entropy (interactions, non-self)
  SELECT snapshot_date, target_address,
    SUM(-p * LOG(p, 2)) AS cp_entropy_90d
  FROM (
    SELECT snapshot_date, target_address, counterparty_address,
           COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY snapshot_date, target_address) AS p
    FROM cp GROUP BY 1,2,3)
  GROUP BY 1,2
),
cp_new AS (   -- P3: distinct counterparties first seen in the last 30 days of window
  SELECT w.snapshot_date, w.target_address,
         COUNT(DISTINCT w.counterparty_address) AS cp_new_30d
  FROM cp w
  LEFT JOIN (
    SELECT snapshot_date, target_address, counterparty_address
    FROM cp GROUP BY 1,2,3
    HAVING MAX(block_timestamp) < TIMESTAMP(DATETIME_SUB(snapshot_date, INTERVAL 30 DAY))
  ) old
    ON old.snapshot_date = w.snapshot_date
   AND old.target_address = w.target_address
   AND old.counterparty_address = w.counterparty_address
  WHERE old.counterparty_address IS NULL
    AND w.block_timestamp >= TIMESTAMP(DATETIME_SUB(w.snapshot_date, INTERVAL 30 DAY))
  GROUP BY 1,2
),
recip AS (   -- P5: reciprocity / round-trips: cps observed in BOTH directions
  SELECT snapshot_date, target_address,
         COUNTIF(n_out > 0 AND n_in > 0) AS cp_both_dir_90d
  FROM (
    SELECT snapshot_date, target_address, counterparty_address,
           COUNTIF(direction='outgoing') AS n_out,
           COUNTIF(direction='incoming') AS n_in
    FROM cp GROUP BY 1,2,3)
  GROUP BY 1,2
),
tkn_hhi AS (   -- P5: token interaction concentration (HHI over tokens)
  SELECT snapshot_date, target_address, SUM(p*p) AS token_hhi_90d
  FROM (
    SELECT snapshot_date, target_address, token_contract_address,
           COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY snapshot_date, target_address) AS p
    FROM dedup
    WHERE event_family = 'token_transfer'
    GROUP BY 1,2,3 HAVING token_contract_address IS NOT NULL)
  GROUP BY 1,2
),
fwd AS (   -- labels: future 30 days, primary events
  SELECT s.snapshot_date, t.target_address, e.direction,
         e.counterparty_address, e.counterparty_present, e.self_transaction
  FROM snapshots s
  CROSS JOIN targets t
  JOIN events e
    ON e.target_address = t.target_address
   AND e.block_timestamp >= TIMESTAMP(s.snapshot_date)
   AND e.block_timestamp <  TIMESTAMP(DATETIME_ADD(s.snapshot_date, INTERVAL 30 DAY))
),
fwd_dedup AS (
  SELECT snapshot_date, target_address, direction, counterparty_address,
         counterparty_present, self_transaction
  FROM fwd GROUP BY 1,2,3,4,5,6
),
labels AS (
  SELECT f.snapshot_date, f.target_address,
    COUNT(*) AS fwd30_evt_cnt,
    COUNT(DISTINCT f.counterparty_address) AS fwd30_cp_distinct,
    COUNT(DISTINCT IF(f.counterparty_present AND NOT f.self_transaction
          AND f.direction='outgoing', f.counterparty_address, NULL)) AS fwd30_cp_out_distinct
  FROM fwd_dedup f
  GROUP BY 1,2
),
fwd_new AS (   -- future counterparties never seen in the 90d lookback
  SELECT f.snapshot_date, f.target_address,
         COUNT(DISTINCT f.counterparty_address) AS fwd30_new_cp
  FROM (SELECT * FROM fwd_dedup
        WHERE counterparty_present AND NOT self_transaction
              AND direction='outgoing') f
  LEFT JOIN (SELECT DISTINCT snapshot_date, target_address, counterparty_address
             FROM cp) c
    ON c.snapshot_date = f.snapshot_date
   AND c.target_address = f.target_address
   AND c.counterparty_address = f.counterparty_address
  WHERE c.counterparty_address IS NULL
  GROUP BY 1,2
)
SELECT
  f.snapshot_date,
  f.target_address,
  f.target_exgraph_node_id,
  f.target_is_x_matched,
  f.evt_cnt_90d, f.evt_out_90d, f.evt_in_90d, f.evt_self_90d,
  f.evt_native_90d, f.evt_token_90d, f.active_days_90d, f.tx_cnt_90d,
  f.active_span_days_90d,
  f.cp_distinct_90d, f.cp_out_distinct_90d, f.cp_in_distinct_90d,
  f.cp_out_interact_90d, f.cp_in_interact_90d,
  f.token_distinct_90d,
  COALESCE(e.cp_entropy_90d, 0) AS cp_entropy_90d,
  COALESCE(n.cp_new_30d, 0) AS cp_new_30d,
  SAFE_DIVIDE(COALESCE(n.cp_new_30d,0), NULLIF(f.cp_out_distinct_90d,0)) AS cp_new_rate_30d,
  COALESCE(r.cp_both_dir_90d, 0) AS cp_both_dir_90d,
  SAFE_DIVIDE(COALESCE(r.cp_both_dir_90d,0), NULLIF(f.cp_distinct_90d,0)) AS cp_reciprocity_90d,
  SAFE_DIVIDE(f.evt_self_90d, NULLIF(f.evt_cnt_90d,0)) AS self_tx_rate_90d,
  SAFE_DIVIDE(f.evt_token_90d, NULLIF(f.evt_cnt_90d,0)) AS token_event_rate_90d,
  COALESCE(h.token_hhi_90d, 1.0) AS token_hhi_90d,
  SAFE_DIVIDE(f.evt_cnt_90d, NULLIF(f.active_days_90d,0)) AS events_per_active_day_90d,
  -- labels (router training / selection evaluation):
  COALESCE(l.fwd30_evt_cnt, 0) AS fwd30_evt_cnt,
  COALESCE(l.fwd30_cp_distinct, 0) AS fwd30_cp_distinct,
  COALESCE(l.fwd30_cp_out_distinct, 0) AS fwd30_cp_out_distinct,
  COALESCE(fn.fwd30_new_cp, 0) AS fwd30_new_cp,
  -- P3 importance proxy: future new counterparty mass weighted by as-of
  -- behavioural unpredictability (entropy normalized to log2(cp count)).
  SAFE_DIVIDE(COALESCE(fn.fwd30_new_cp,0) * COALESCE(e.cp_entropy_90d,0),
              NULLIF(LOG(GREATEST(f.cp_distinct_90d,2),2),0)) AS importance_proxy_p3
FROM feat f
LEFT JOIN cp_entropy e USING (snapshot_date, target_address)
LEFT JOIN cp_new     n USING (snapshot_date, target_address)
LEFT JOIN recip      r USING (snapshot_date, target_address)
LEFT JOIN tkn_hhi    h USING (snapshot_date, target_address)
LEFT JOIN labels     l USING (snapshot_date, target_address)
LEFT JOIN fwd_new    fn USING (snapshot_date, target_address);
