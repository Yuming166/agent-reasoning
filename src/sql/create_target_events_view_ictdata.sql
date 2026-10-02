-- Unified event view over the three six-month BigQuery materializations.
--
-- IMPORTANT: each source table already contains rows where at least one
-- endpoint matches the EX-Graph address set. The non-matching counterparty is
-- intentionally retained. This view is UNION ALL by design: native
-- transactions, token transfers, and internal traces have different event
-- semantics and are not deduplicated by transaction_hash.
CREATE OR REPLACE VIEW `ictdata-507912.exgraph.target_events_20220301_20220901`
OPTIONS(
  description = 'Unified EX-Graph target-touching Ethereum events; 2022-03-01 through 2022-09-01 UTC'
)
AS
SELECT
  event_family,
  block_timestamp,
  block_number,
  transaction_index,
  transaction_hash,
  CAST(NULL AS INT64) AS event_index,
  from_address,
  to_address,
  value,
  value_lossless,
  transaction_type,
  CAST(NULL AS STRING) AS quantity,
  CAST(NULL AS STRING) AS token_contract_address,
  CAST(NULL AS STRING) AS token_id,
  CAST(NULL AS BOOL) AS removed,
  CAST(NULL AS STRING) AS trace_type,
  CAST(NULL AS ARRAY<INT64>) AS trace_address,
  CAST(NULL AS INT64) AS subtrace_count,
  CAST(NULL AS STRING) AS call_type,
  CAST(NULL AS STRING) AS error,
  from_exgraph_node_id,
  to_exgraph_node_id,
  touches_target_from,
  touches_target_to
FROM `ictdata-507912.exgraph.external_transactions_20220301_20220901`

UNION ALL

SELECT
  event_family,
  block_timestamp,
  block_number,
  transaction_index,
  transaction_hash,
  event_index,
  from_address,
  to_address,
  CAST(NULL AS BIGNUMERIC) AS value,
  CAST(NULL AS STRING) AS value_lossless,
  CAST(NULL AS INT64) AS transaction_type,
  quantity,
  token_contract_address,
  token_id,
  removed,
  CAST(NULL AS STRING) AS trace_type,
  CAST(NULL AS ARRAY<INT64>) AS trace_address,
  CAST(NULL AS INT64) AS subtrace_count,
  CAST(NULL AS STRING) AS call_type,
  CAST(NULL AS STRING) AS error,
  from_exgraph_node_id,
  to_exgraph_node_id,
  touches_target_from,
  touches_target_to
FROM `ictdata-507912.exgraph.token_transfers_20220301_20220901`

UNION ALL

SELECT
  event_family,
  block_timestamp,
  block_number,
  transaction_index,
  transaction_hash,
  CAST(NULL AS INT64) AS event_index,
  from_address,
  to_address,
  value,
  value_lossless,
  CAST(NULL AS INT64) AS transaction_type,
  CAST(NULL AS STRING) AS quantity,
  CAST(NULL AS STRING) AS token_contract_address,
  CAST(NULL AS STRING) AS token_id,
  CAST(NULL AS BOOL) AS removed,
  trace_type,
  trace_address,
  subtrace_count,
  call_type,
  error,
  from_exgraph_node_id,
  to_exgraph_node_id,
  touches_target_from,
  touches_target_to
FROM `ictdata-507912.exgraph.internal_traces_20220301_20220901`;
