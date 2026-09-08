-- One row per distinct outgoing primary event (Mar-Aug 2022), tagged
-- cp_type='repeat' if the same u->v pair was observed in the preceding 90d,
-- else 'new'. Partitioned by month.
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
)
SELECT e.*,
  IF(EXISTS(
       SELECT 1 FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901` h
       WHERE h.target_address=e.u AND h.counterparty_address=e.v
         AND h.direction='outgoing' AND h.sequence_role='primary'
         AND h.counterparty_present AND NOT h.self_transaction
         AND h.block_timestamp >= TIMESTAMP('2022-03-01')
         AND h.block_timestamp <  e.block_timestamp
         AND h.block_timestamp >= TIMESTAMP_SUB(e.block_timestamp, INTERVAL 90 DAY)),
     'repeat','new') AS cp_type
FROM e;
