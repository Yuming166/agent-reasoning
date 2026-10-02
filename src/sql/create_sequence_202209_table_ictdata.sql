-- September 2022 directional sequence table, same role/match/index semantics
-- as the frozen target_event_sequences_20220301_20220901 table.

CREATE OR REPLACE TABLE `ictdata-507912.exgraph.target_event_sequences_20220901_20221001`
PARTITION BY DATE(block_timestamp)
CLUSTER BY target_exgraph_node_id, counterparty_address, event_family
OPTIONS(
  description = 'Directional EX-Graph target event sequences for 2022-09-01 through 2022-10-01 UTC, same semantics as the frozen Mar-Aug sequence table.',
  require_partition_filter = TRUE
)
AS
WITH src AS (
  SELECT event_family, block_timestamp, block_number, transaction_index,
         transaction_hash, CAST(NULL AS INT64) AS event_index, from_address, to_address,
         value, value_lossless, transaction_type, CAST(NULL AS STRING) AS quantity,
         CAST(NULL AS STRING) AS token_contract_address, CAST(NULL AS STRING) AS token_id,
         CAST(NULL AS BOOL) AS removed, CAST(NULL AS STRING) AS trace_type,
         CAST(NULL AS STRING) AS trace_address, CAST(NULL AS INT64) AS subtrace_count,
         CAST(NULL AS STRING) AS call_type, CAST(NULL AS STRING) AS error,
         from_exgraph_node_id AS source_from_exgraph_node_id,
         to_exgraph_node_id AS source_to_exgraph_node_id,
         touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.external_transactions_20220901_20221001`
  UNION ALL
  SELECT event_family, block_timestamp, block_number, transaction_index,
         transaction_hash, event_index, from_address, to_address,
         CAST(NULL AS BIGNUMERIC) AS value, CAST(NULL AS STRING) AS value_lossless,
         CAST(NULL AS INT64) AS transaction_type, quantity,
         token_contract_address, token_id, removed,
         CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS INT64),
         CAST(NULL AS STRING), CAST(NULL AS STRING),
         from_exgraph_node_id, to_exgraph_node_id,
         touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.token_transfers_20220901_20221001`
  UNION ALL
  SELECT event_family, block_timestamp, block_number, transaction_index,
         transaction_hash, CAST(NULL AS INT64), from_address, to_address,
         value, value_lossless, CAST(NULL AS INT64), CAST(NULL AS STRING),
         CAST(NULL AS STRING), CAST(NULL AS STRING), CAST(NULL AS BOOL),
         trace_type, TO_JSON_STRING(trace_address), subtrace_count, call_type, error,
         from_exgraph_node_id, to_exgraph_node_id,
         touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.internal_traces_20220901_20221001`
),
b0 AS (
  SELECT *,
    CASE event_family WHEN 'external_tx' THEN 0 WHEN 'token_transfer' THEN 1
         WHEN 'internal_trace' THEN 2 ELSE 9 END AS event_family_order
  FROM src
  WHERE block_timestamp >= TIMESTAMP('2022-09-01 00:00:00+00')
    AND block_timestamp <  TIMESTAMP('2022-10-01 00:00:00+00')
),
base AS (
  SELECT event_family, block_timestamp, block_number, transaction_index,
         transaction_hash, event_index, from_address, to_address, value,
         value_lossless, transaction_type, quantity, token_contract_address, token_id,
         removed, trace_type, trace_address, subtrace_count, call_type, error,
         source_from_exgraph_node_id, source_to_exgraph_node_id,
         touches_target_from, touches_target_to, event_family_order
  FROM b0
),
roles AS (
  SELECT b.*, LOWER(from_address) AS target_address, LOWER(to_address) AS counterparty_address,
         'outgoing' AS direction, FALSE AS self_transaction
  FROM base b WHERE touches_target_from
    AND NOT (touches_target_to AND LOWER(from_address)=LOWER(to_address))
  UNION ALL
  SELECT b.*, LOWER(to_address), LOWER(from_address), 'incoming', FALSE
  FROM base b WHERE touches_target_to
    AND NOT (touches_target_from AND LOWER(from_address)=LOWER(to_address))
  UNION ALL
  SELECT b.*, LOWER(from_address), LOWER(to_address), 'self', TRUE
  FROM base b WHERE touches_target_from AND touches_target_to
    AND LOWER(from_address)=LOWER(to_address)
),
enriched AS (
  SELECT r.*,
    tm.exgraph_node_id AS target_exgraph_node_id,
    cm.exgraph_node_id AS counterparty_exgraph_node_id,
    tm.match_status AS target_match_status,
    cm.match_status AS counterparty_match_status,
    tm.exgraph_node_id IS NOT NULL AS target_is_x_matched,
    cm.exgraph_node_id IS NOT NULL AS counterparty_is_x_matched,
    r.counterparty_address IS NOT NULL AS counterparty_present,
    IF(r.event_family='internal_trace','auxiliary','primary') AS sequence_role,
    tm.exgraph_node_id IS NOT NULL AND cm.exgraph_node_id IS NOT NULL AS both_endpoints_are_x_matched
  FROM roles r
  LEFT JOIN `ictdata-507912.exgraph.exgraph_x_matches_v1` tm
    ON r.target_address=tm.ethereum_address
  LEFT JOIN `ictdata-507912.exgraph.exgraph_x_matches_v1` cm
    ON r.counterparty_address=cm.ethereum_address
)
SELECT
  ROW_NUMBER() OVER (
    PARTITION BY target_address ORDER BY block_timestamp, block_number,
      transaction_index, event_family_order, COALESCE(event_index,-1),
      COALESCE(TO_JSON_STRING(trace_address),''), direction, counterparty_address,
      transaction_hash) - 1 AS target_sequence_index,
  target_exgraph_node_id, target_address, target_match_status, target_is_x_matched,
  counterparty_exgraph_node_id, counterparty_address, counterparty_match_status,
  counterparty_is_x_matched, counterparty_present, both_endpoints_are_x_matched,
  direction, self_transaction, sequence_role, event_family, event_family_order,
  block_timestamp, block_number, transaction_index, event_index, transaction_hash,
  from_address, to_address, value, value_lossless, transaction_type,
  token_contract_address, token_id, quantity, removed, trace_type, trace_address,
  subtrace_count, call_type, error, source_from_exgraph_node_id,
  source_to_exgraph_node_id, touches_target_from, touches_target_to
FROM enriched;
