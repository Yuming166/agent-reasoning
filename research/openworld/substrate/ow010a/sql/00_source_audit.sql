-- OW-010A source audit. Aggregate-only; no raw events are exported.
-- The source view is a UNION ALL of native, token, and internal event tables.
-- Event identities are deliberately family-specific.  In particular, token
-- event_index alone is not treated as a sufficient identity.
WITH source AS (
  SELECT
    event_family,
    block_timestamp,
    block_number,
    transaction_index,
    transaction_hash,
    event_index,
    from_address,
    to_address,
    value_lossless,
    transaction_type,
    quantity,
    token_contract_address,
    token_id,
    removed,
    trace_type,
    trace_address,
    TO_JSON_STRING(trace_address) AS trace_address_json,
    subtrace_count,
    call_type,
    error,
    from_exgraph_node_id,
    to_exgraph_node_id,
    touches_target_from,
    touches_target_to,
    CASE
      WHEN event_family = 'external_tx' THEN CONCAT(
        'external_tx|', COALESCE(transaction_hash, '<NULL_TX>')
      )
      WHEN event_family = 'token_transfer' THEN CONCAT(
        'token_transfer|', COALESCE(transaction_hash, '<NULL_TX>'), '|',
        COALESCE(CAST(event_index AS STRING), '<NULL_EVENT_INDEX>'), '|',
        COALESCE(LOWER(token_contract_address), '<NULL_TOKEN_CONTRACT>'), '|',
        COALESCE(token_id, '<NULL_TOKEN_ID>'), '|',
        COALESCE(LOWER(from_address), '<NULL_FROM>'), '|',
        COALESCE(LOWER(to_address), '<NULL_TO>')
      )
      WHEN event_family = 'internal_trace' THEN CONCAT(
        'internal_trace|', COALESCE(transaction_hash, '<NULL_TX>'), '|',
        COALESCE(TO_JSON_STRING(trace_address), '<NULL_TRACE>')
      )
      ELSE CONCAT(
        COALESCE(event_family, '<NULL_FAMILY>'), '|',
        COALESCE(transaction_hash, '<NULL_TX>')
      )
    END AS event_identity,
    TO_HEX(SHA256(TO_JSON_STRING(STRUCT(
      event_family AS event_family,
      block_timestamp AS block_timestamp,
      block_number AS block_number,
      transaction_index AS transaction_index,
      transaction_hash AS transaction_hash,
      event_index AS event_index,
      from_address AS from_address,
      to_address AS to_address,
      value_lossless AS value_lossless,
      transaction_type AS transaction_type,
      quantity AS quantity,
      token_contract_address AS token_contract_address,
      token_id AS token_id,
      removed AS removed,
      trace_type AS trace_type,
      trace_address AS trace_address,
      subtrace_count AS subtrace_count,
      call_type AS call_type,
      error AS error,
      from_exgraph_node_id AS from_exgraph_node_id,
      to_exgraph_node_id AS to_exgraph_node_id
    )))) AS row_signature
  FROM `ictdata-507912.exgraph.target_events_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
),
identity_stats AS (
  SELECT
    event_family,
    event_identity,
    COUNT(*) AS identity_rows,
    COUNT(DISTINCT row_signature) AS identity_variants
  FROM source
  GROUP BY event_family, event_identity
),
summary AS (
  SELECT
    event_family,
    COUNT(*) AS source_rows,
    COUNT(DISTINCT transaction_hash) AS unique_transaction_hashes,
    COUNT(DISTINCT event_identity) AS unique_event_identities,
    COUNTIF(transaction_hash IS NULL) AS null_transaction_hash_rows,
    COUNTIF(from_address IS NULL OR to_address IS NULL) AS incomplete_endpoint_rows,
    COUNTIF(LOWER(from_address) = LOWER(to_address) AND from_address IS NOT NULL) AS self_address_rows,
    COUNTIF(from_exgraph_node_id IS NOT NULL AND to_exgraph_node_id IS NOT NULL) AS both_mapped_rows,
    COUNTIF(from_exgraph_node_id IS NOT NULL AND to_exgraph_node_id IS NULL) AS from_only_mapped_rows,
    COUNTIF(from_exgraph_node_id IS NULL AND to_exgraph_node_id IS NOT NULL) AS to_only_mapped_rows,
    COUNTIF(from_exgraph_node_id IS NULL AND to_exgraph_node_id IS NULL) AS neither_mapped_rows,
    COUNTIF(event_family = 'token_transfer' AND removed) AS token_removed_rows,
    COUNTIF(event_family = 'internal_trace' AND error IS NOT NULL) AS internal_error_rows,
    COUNTIF(event_family = 'token_transfer' AND event_index IS NULL) AS token_null_event_index_rows,
    COUNTIF(event_family = 'token_transfer' AND token_contract_address IS NULL) AS token_null_contract_rows,
    COUNTIF(event_family = 'internal_trace' AND trace_address IS NULL) AS internal_null_trace_rows,
    MIN(block_timestamp) AS min_event_timestamp,
    MAX(block_timestamp) AS max_event_timestamp
  FROM source
  GROUP BY event_family
),
duplicate_summary AS (
  SELECT
    event_family,
    COUNTIF(identity_rows > 1) AS duplicate_identity_groups,
    SUM(IF(identity_rows > 1, identity_rows - 1, 0)) AS duplicate_identity_extra_rows,
    COUNTIF(identity_variants > 1) AS identity_collision_groups,
    SUM(IF(identity_variants > 1, identity_rows, 0)) AS identity_collision_rows
  FROM identity_stats
  GROUP BY event_family
)
SELECT
  s.*,
  d.duplicate_identity_groups,
  d.duplicate_identity_extra_rows,
  d.identity_collision_groups,
  d.identity_collision_rows
FROM summary s
JOIN duplicate_summary d USING (event_family)
ORDER BY event_family;
