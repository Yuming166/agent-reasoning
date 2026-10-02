-- Candidate-model support tables, history strictly before August test month.

-- 1) personalized edge weights (Mar-Jul): count + last-seen recency
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.nc_edges_hist_v1` AS
SELECT target_address AS u, counterparty_address AS v,
       COUNT(*) AS cnt,
       MAX(block_timestamp) AS last_seen,
       DATE_DIFF(DATE '2022-08-01', DATE(MAX(block_timestamp)), DAY) AS days_since_last
FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
WHERE block_timestamp >= TIMESTAMP('2022-03-01')
  AND block_timestamp <  TIMESTAMP('2022-08-01')
  AND sequence_role='primary' AND direction='outgoing'
  AND counterparty_present AND NOT self_transaction
GROUP BY 1,2;

-- 2) global historical popularity (incoming interaction volume Mar-Jul)
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.nc_global_pop_v1` AS
SELECT counterparty_address AS v, COUNT(*) AS hist_cnt
FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
WHERE block_timestamp >= TIMESTAMP('2022-03-01')
  AND block_timestamp <  TIMESTAMP('2022-08-01')
  AND sequence_role='primary' AND direction='outgoing'
  AND counterparty_present AND NOT self_transaction
GROUP BY 1;

-- 3) two-hop bridge candidates u->w->v aggregated over Mar-Jul, with the
--    occlusion-consistent signal sum_w 1/outdeg(w)
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.nc_bridge_cand_v1` AS
WITH outdeg AS (
  SELECT u, COUNT(DISTINCT v) AS outdeg FROM `ictdata-507912.exgraph.nc_edges_hist_v1`
  GROUP BY 1
)
SELECT e1.u AS u, e2.v AS v,
       COUNT(*) AS bridge_paths,
       SUM(1.0/d.outdeg) AS bridge_signal
FROM `ictdata-507912.exgraph.nc_edges_hist_v1` e1
JOIN `ictdata-507912.exgraph.nc_edges_hist_v1` e2 ON e2.u = e1.v
JOIN outdeg d ON d.u = e1.v
WHERE e1.u <> e2.v
GROUP BY 1,2;
