-- Standard SQL template for the Google Cloud Blockchain Analytics Ethereum
-- Mainnet dataset. Replace YOUR_PROJECT.YOUR_DATASET.target_addresses with a
-- permanent table made from data/metadata/target_addresses.csv.
-- Current public-view schema verified on 2026-09-07:
--   transactions.transaction_hash (not hash)
--   token_transfers.event_index, address, quantity (not log_index,
--   token_address, value).
-- Freeze the query text, execution date, table metadata and exported result.

DECLARE start_ts TIMESTAMP DEFAULT TIMESTAMP('2021-08-01 00:00:00+00');
DECLARE end_ts   TIMESTAMP DEFAULT TIMESTAMP('2022-08-01 00:00:00+00');

-- 1. Native/external Ethereum transactions.
CREATE TEMP TABLE target_external_transactions AS
SELECT
  'external_tx' AS event_type,
  t.block_timestamp,
  t.block_number,
  t.transaction_index,
  t.transaction_hash AS transaction_hash,
  LOWER(t.from_address) AS from_address,
  LOWER(t.to_address) AS to_address,
  t.value,
  ARRAY_AGG(DISTINCT IF(LOWER(t.from_address) = LOWER(a.ethereum_address),
                        a.exgraph_node_id, NULL) IGNORE NULLS) AS matched_from_node_ids,
  ARRAY_AGG(DISTINCT IF(LOWER(t.to_address) = LOWER(a.ethereum_address),
                        a.exgraph_node_id, NULL) IGNORE NULLS) AS matched_to_node_ids
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.transactions` AS t
JOIN `YOUR_PROJECT.YOUR_DATASET.target_addresses` AS a
  ON LOWER(t.from_address) = LOWER(a.ethereum_address)
  OR LOWER(t.to_address) = LOWER(a.ethereum_address)
WHERE t.block_timestamp >= start_ts
  AND t.block_timestamp < end_ts
GROUP BY
  event_type, block_timestamp, block_number, transaction_index,
  transaction_hash, from_address, to_address, value;

-- 2. Token movement events. Keep these separate from external transactions.
CREATE TEMP TABLE target_token_transfers AS
SELECT
  'token_transfer' AS event_type,
  tt.block_timestamp,
  tt.block_number,
  tt.transaction_index,
  tt.event_index,
  tt.transaction_hash,
  LOWER(tt.from_address) AS from_address,
  LOWER(tt.to_address) AS to_address,
  LOWER(tt.address) AS contract_address,
  tt.token_id,
  tt.quantity,
  ARRAY_AGG(DISTINCT a.exgraph_node_id IGNORE NULLS) AS matched_node_ids
FROM `bigquery-public-data.goog_blockchain_ethereum_mainnet_us.token_transfers` AS tt
JOIN `YOUR_PROJECT.YOUR_DATASET.target_addresses` AS a
  ON LOWER(tt.from_address) = LOWER(a.ethereum_address)
  OR LOWER(tt.to_address) = LOWER(a.ethereum_address)
WHERE tt.block_timestamp >= start_ts
  AND tt.block_timestamp < end_ts
GROUP BY
  event_type, block_timestamp, block_number, transaction_index, event_index,
  transaction_hash, from_address, to_address, contract_address, token_id, quantity;

-- 3. For internal value flows, query traces separately and label them as
-- internal_trace. Do not union them with token transfers until the event
-- semantics and duplicate policy have been fixed.
SELECT * FROM target_external_transactions;
SELECT * FROM target_token_transfers;

-- Before execution, confirm the exact table/schema namespace in the current
-- BigQuery console. Google Cloud's Blockchain Analytics docs have changed
-- table naming during the preview/public-dataset transition.
