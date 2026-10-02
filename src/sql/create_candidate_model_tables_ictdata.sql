-- Next-counterparty candidate model inputs (all primary outgoing events,
-- present non-self counterparty).
--
-- 1) nc_events_v1: one row per distinct outgoing event per month, tagged
--    repeat (counterparty seen in prior 90d window) vs new.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.nc_events_v1`
PARTITION BY month AS
WITH e AS (
  SELECT DATE_TRUNC(DATE(block_timestamp), MONTH) AS month,
         target_address AS u, counterparty_address AS v,
         block_timestamp, target_sequence_index
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-03-01')
    AND block_timestamp <  TIMESTAMP('2022-09-01')
    AND sequence_role='primary' AND direction='outgoing'
    AND counterparty_present AND NOT self_transaction
  GROUP BY 1,2,3,4,5
),
prior AS (   -- distinct u->v pairs seen in the 90d before the FIRST day of month
  SELECT DISTINCT DATE_TRUNC(DATE(e2.block_timestamp), MONTH) AS month,
         e2.target_address AS u, e2.counterparty_address AS v
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901` e2
  WHERE e2.block_timestamp >= TIMESTAMP('2022-03-01')
    AND e2.block_timestamp <  TIMESTAMP('2022-09-01')
    AND e2.sequence_role='primary' AND e2.direction='outgoing'
    AND e2.counterparty_present AND NOT e2.self_transaction
)
SELECT e.*, IF(p.v IS NULL, 'new', 'repeat') AS cp_type
FROM e LEFT JOIN prior p
  ON p.month=e.month AND p.u=e.u AND p.v=e.v
 AND e2_block_check();
