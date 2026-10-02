-- Combined March-September directional event view with a continuous per-wallet
-- sequence index over the frozen Mar-Aug table plus the September table.

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
  SELECT
    target_sequence_index, target_exgraph_node_id, target_address, target_match_status,
    target_is_x_matched, counterparty_exgraph_node_id, counterparty_address,
    counterparty_match_status, counterparty_is_x_matched, counterparty_present,
    both_endpoints_are_x_matched, direction, self_transaction, sequence_role,
    event_family, event_family_order, block_timestamp, block_number, transaction_index,
    event_index, transaction_hash, from_address, to_address, value, value_lossless,
    transaction_type, token_contract_address, token_id, quantity, removed, trace_type,
    COALESCE(TO_JSON_STRING(trace_address), '') AS trace_address, subtrace_count,
    call_type, error, source_from_exgraph_node_id, source_to_exgraph_node_id,
    touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
  UNION ALL
  SELECT
    target_sequence_index, target_exgraph_node_id, target_address, target_match_status,
    target_is_x_matched, counterparty_exgraph_node_id, counterparty_address,
    counterparty_match_status, counterparty_is_x_matched, counterparty_present,
    both_endpoints_are_x_matched, direction, self_transaction, sequence_role,
    event_family, event_family_order, block_timestamp, block_number, transaction_index,
    event_index, transaction_hash, from_address, to_address, value, value_lossless,
    transaction_type, token_contract_address, token_id, quantity, removed, trace_type,
    COALESCE(trace_address, '') AS trace_address, subtrace_count,
    call_type, error, source_from_exgraph_node_id, source_to_exgraph_node_id,
    touches_target_from, touches_target_to
  FROM `ictdata-507912.exgraph.target_event_sequences_20220901_20221001`
);
