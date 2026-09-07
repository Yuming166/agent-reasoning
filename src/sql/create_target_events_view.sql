-- Portable template for the unified target-touching Ethereum event view.
-- The Python wrapper replaces {{VIEW}}, {{EXTERNAL}}, {{TOKEN}}, and {{TRACE}}
-- with identifiers derived from --project-id/--dataset-id/--start/--end.
CREATE OR REPLACE VIEW `{{VIEW}}`
OPTIONS(
  description = 'Unified EX-Graph target-touching Ethereum events'
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
FROM `{{EXTERNAL}}`
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
FROM `{{TOKEN}}`
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
FROM `{{TRACE}}`;
