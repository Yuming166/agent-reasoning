-- P2 temporal trigger-influence proxy (Hawkes-spillover, SQL-bounded).
-- For each directed target -> counterparty active in [2022-06-01, 2022-07-01):
-- aggregate hourly event counts (primary families) for both endpoints,
-- corr(a_h, b_{h+1}) over 720 hours, weighted by interaction volume.
-- Wallet outgoing trigger score = mean positive-lag correlation to the
-- counterparties it interacts with, weighted by volume. As-of July snapshot;
-- strictly within history window. 720h grid keeps the self-join bounded.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.wallet_trigger_proxy_v1` AS
WITH hourly AS (
  SELECT target_address AS addr,
         TIMESTAMP_TRUNC(block_timestamp, HOUR) AS hr,
         COUNT(*) AS act
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-06-01')
    AND block_timestamp <  TIMESTAMP('2022-07-01')
    AND sequence_role = 'primary'
  GROUP BY 1,2
),
pairs AS (   -- directed target -> counterparty, with volume (June window)
  SELECT target_address AS a, counterparty_address AS b, COUNT(*) AS vol
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-06-01')
    AND block_timestamp <  TIMESTAMP('2022-07-01')
    AND sequence_role = 'primary'
    AND counterparty_present AND NOT self_transaction
    AND direction = 'outgoing'
  GROUP BY 1,2
),
grid AS (   -- 720 hours June
  SELECT TIMESTAMP_ADD(TIMESTAMP('2022-06-01'), INTERVAL k HOUR) AS hr,
         TIMESTAMP_ADD(TIMESTAMP('2022-06-01'), INTERVAL k+1 HOUR) AS hr_next
  FROM UNNEST(GENERATE_ARRAY(0,719)) AS k
),
panel AS (
  SELECT p.a, p.b, p.vol, g.hr,
         IFNULL(ha.act,0) AS a_act,
         IFNULL(hb.act,0) AS b_next
  FROM pairs p
  CROSS JOIN grid g
  LEFT JOIN hourly ha ON ha.addr = p.a AND ha.hr = g.hr
  LEFT JOIN hourly hb ON hb.addr = p.b AND hb.hr = g.hr_next
),
paircorr AS (
  SELECT a, b, ANY_VALUE(vol) AS vol,
    CASE WHEN COUNTIF(a_act>0 OR b_next>0) < 24 THEN NULL
    ELSE CORR(a_act, b_next) END AS lag1_corr
  FROM panel
  GROUP BY a, b
)
SELECT
  a AS target_address,
  COUNT(*) AS trigger_pairs,
  SUM(vol) AS trigger_total_vol,
  AVG(IF(lag1_corr > 0, lag1_corr, NULL)) AS trigger_pos_corr_mean,
  -- volume-weighted mean of positive lag correlations:
  SAFE_DIVIDE(
    SUM(IF(lag1_corr > 0, lag1_corr * vol, 0)),
    NULLIF(SUM(IF(lag1_corr > 0, vol, 0)),0)) AS trigger_score_p2,
  COUNTIF(lag1_corr > 0.3) AS trigger_strong_pairs
FROM paircorr
GROUP BY a;
