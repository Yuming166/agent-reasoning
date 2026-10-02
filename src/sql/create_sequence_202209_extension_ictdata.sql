-- September 2022 extension directional sequence table, built with the SAME
-- role/match/index semantics as target_event_sequences_20220301_20220901.
-- Sources: the three September-only materialized tables. A combined
-- 2022-03..2022-10 view is created after so history windows for September
-- events cover June-August without modifying the frozen table.

CREATE OR REPLACE TABLE `ictdata-507912.exgraph.target_event_sequences_20220901_20221001`
PARTITION BY DATE(block_timestamp)
CLUSTER BY target_exgraph_node_id, counterparty_address, event_family
OPTIONS(
  description = 'Directional EX-Graph target event sequences for 2022-09-01 through 2022-10-01 UTC; same role/index semantics as the frozen Mar-Aug sequence table.',
  require_partition_filter = TRUE
)
AS
WITH src AS (
  SELECT event_family, block_timestamp, block_number, transaction_index,
         transaction_hash, event_index, from_address, to_address, value,
         value_lossless, transaction_type, NULL AS quantity,
         NULL AS token_contract_address, NULL AS token_id, NULL AS removed,
         NULL AS trace_type, NULL AS trace_address, NULL AS subtrace_count,
         NULL AS call_type, NULL AS error,
         from_exgraph_node_id AS source_from_exgraph_node_id,
         to_exgraph_node_id AS source_to_exgraph_node_id,
         touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.external_transactions_20220901_20221001`
  UNION ALL
  SELECT event_family, block_timestamp, block_number, transaction_index,
         transaction_hash, event_index, from_address, to_address, value,
         value_lossless, transaction_type, quantity,
         token_contract_address, token_id, removed,
         NULL AS trace_type, NULL AS trace_address, NULL AS subtrace_count,
         NULL AS call_type, NULL AS error,
         from_exgraph_node_id AS source_from_exgraph_node_id,
         to_exgraph_node_id AS source_to_exgraph_node_id,
         touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.token_transfers_20220901_20221001`
  UNION ALL
  SELECT event_family, block_timestamp, block_number, transaction_index,
         transaction_hash, NULL AS event_index, from_address, to_address, value,
         value_lossless, NULL AS transaction_type, NULL AS quantity,
         NULL AS token_contract_address, NULL AS token_id, NULL AS removed,
         trace_type, trace_address, subtrace_count, call_type, error,
         from_exgraph_node_id AS source_from_exgraph_node_id,
         to_exgraph_node_id AS source_to_exgraph_node_id,
         touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.internal_traces_20220901_20221001`
),
base AS (
  SELECT *,
    CASE event_family WHEN 'external_tx' THEN 0 WHEN 'token_transfer' THEN 1
         WHEN 'internal_trace' THEN 2 ELSE 9 END AS event_family_order
  FROM src
  WHERE block_timestamp >= TIMESTAMP('2022-09-01 00:00:00+00')
    AND block_timestamp <  TIMESTAMP('2022-10-01 00:00:00+00')
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
  -- September-only local index; the combined view reindexes continuously.
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

-- Combined Mar-Sep view with a continuous per-wallet sequence index.
CREATE OR REPLACE VIEW `ictdata-507912.exgraph.target_event_sequences_20220301_20221001`
AS
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
FROM (
  SELECT * FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  UNION ALL
  SELECT * FROM `ictdata-507912.exgraph.target_event_sequences_20220901_20221001`
);
