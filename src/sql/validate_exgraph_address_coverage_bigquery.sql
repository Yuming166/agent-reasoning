-- Validate, rather than assume, overlap between the EX-Graph mapping and
-- Google Blockchain Analytics Ethereum Mainnet data.
-- This query returns counts only; it does not export transaction rows.
-- The public table names below were verified through the BigQuery API on
-- 2026-09-07. Replace only YOUR_PROJECT.YOUR_DATASET.target_addresses with
-- the project-local target table.

DECLARE start_ts TIMESTAMP DEFAULT TIMESTAMP('2022-03-01 00:00:00+00');
DECLARE end_ts   TIMESTAMP DEFAULT TIMESTAMP('2022-09-01 00:00:00+00');

CREATE TEMP TABLE target AS
SELECT DISTINCT
  LOWER(ethereum_address) AS address,
  exgraph_node_id
FROM `YOUR_PROJECT.YOUR_DATASET.target_addresses`;

-- Keep source and destination checks separate to make address clustering usable.
CREATE TEMP TABLE external_observed AS
SELECT DISTINCT LOWER(t.from_address) AS address
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.transactions` AS t
JOIN target AS a ON LOWER(t.from_address) = a.address
WHERE t.block_timestamp >= start_ts AND t.block_timestamp < end_ts
UNION DISTINCT
SELECT DISTINCT LOWER(t.to_address) AS address
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.transactions` AS t
JOIN target AS a ON LOWER(t.to_address) = a.address
WHERE t.block_timestamp >= start_ts AND t.block_timestamp < end_ts;

CREATE TEMP TABLE token_observed AS
SELECT DISTINCT LOWER(tt.from_address) AS address
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers` AS tt
JOIN target AS a ON LOWER(tt.from_address) = a.address
WHERE tt.block_timestamp >= start_ts AND tt.block_timestamp < end_ts
UNION DISTINCT
SELECT DISTINCT LOWER(tt.to_address) AS address
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers` AS tt
JOIN target AS a ON LOWER(tt.to_address) = a.address
WHERE tt.block_timestamp >= start_ts AND tt.block_timestamp < end_ts;

SELECT
  (SELECT COUNT(*) FROM target) AS target_addresses,
  (SELECT COUNT(*) FROM external_observed) AS external_tx_observed,
  (SELECT COUNT(*) FROM token_observed) AS token_transfer_observed,
  (SELECT COUNT(*) FROM (
     SELECT address FROM external_observed
     UNION DISTINCT
     SELECT address FROM token_observed
   )) AS observed_in_any_source,
  SAFE_DIVIDE(
    (SELECT COUNT(*) FROM (
       SELECT address FROM external_observed
       UNION DISTINCT
       SELECT address FROM token_observed
     )),
    (SELECT COUNT(*) FROM target)
  ) AS coverage_ratio;

-- Optional: return the small list of target addresses with no observed event.
-- SELECT a.*
-- FROM target AS a
-- LEFT JOIN (
--   SELECT address FROM external_observed
--   UNION DISTINCT
--   SELECT address FROM token_observed
-- ) AS o USING (address)
-- WHERE o.address IS NULL;
