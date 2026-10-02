-- OW-010A event-level as-of substrate.
-- Creates a compact event-level table with one row per
-- (anchor_wallet, source_event_identity, anchor_direction).  It keeps
-- unmapped counterparties, preserves sub-day ordering, and expands an event
-- touching two mapped wallets into one row for each anchor.  Exact duplicate
-- source rows are removed only when the semantic identity AND full row
-- signature agree.  Identity collisions are retained and flagged.
CREATE OR REPLACE TABLE `ictdata-507912.exgraph.openworld_anchor_events_v1`
PARTITION BY DATE(event_timestamp)
CLUSTER BY anchor_wallet, event_family, counterparty_identity
OPTIONS(
  description='OW-010A event-level as-of anchor substrate; label-blind; source events deduplicated by family-specific identity plus row signature; counterparty mapping is not an eligibility filter'
)
AS
WITH mapping AS (
  SELECT
    LOWER(ethereum_address) AS wallet_address,
    ANY_VALUE(exgraph_node_id) AS exgraph_node_id
  FROM `ictdata-507912.exgraph.exgraph_x_matches_v1`
  WHERE ethereum_address IS NOT NULL
    AND exgraph_node_id IS NOT NULL
  GROUP BY wallet_address
),
source0 AS (
  SELECT
    event_family,
    block_timestamp AS event_timestamp,
    block_number,
    transaction_index,
    transaction_hash,
    event_index,
    LOWER(from_address) AS from_address,
    LOWER(to_address) AS to_address,
    value AS native_value,
    value_lossless AS native_value_lossless,
    transaction_type,
    quantity AS token_quantity,
    LOWER(token_contract_address) AS token_contract_address,
    token_id,
    removed,
    trace_type,
    trace_address,
    TO_JSON_STRING(trace_address) AS trace_address_json,
    subtrace_count,
    call_type,
    error,
    from_exgraph_node_id AS source_from_exgraph_node_id,
    to_exgraph_node_id AS source_to_exgraph_node_id,
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
      block_timestamp AS event_timestamp,
      block_number AS block_number,
      transaction_index AS transaction_index,
      transaction_hash AS transaction_hash,
      event_index AS event_index,
      LOWER(from_address) AS from_address,
      LOWER(to_address) AS to_address,
      value_lossless AS native_value_lossless,
      transaction_type AS transaction_type,
      quantity AS token_quantity,
      LOWER(token_contract_address) AS token_contract_address,
      token_id AS token_id,
      removed AS removed,
      trace_type AS trace_type,
      trace_address AS trace_address,
      subtrace_count AS subtrace_count,
      call_type AS call_type,
      error AS error,
      from_exgraph_node_id AS source_from_exgraph_node_id,
      to_exgraph_node_id AS source_to_exgraph_node_id
    )))) AS source_row_signature
  FROM `ictdata-507912.exgraph.target_events_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
),
source1 AS (
  SELECT
    s.*,
    fm.exgraph_node_id AS from_anchor_node,
    tm.exgraph_node_id AS to_anchor_node,
    COUNT(DISTINCT source_row_signature) OVER (PARTITION BY event_identity) > 1
      AS identity_collision_flag,
    COUNT(*) OVER (PARTITION BY event_identity, source_row_signature)
      AS exact_row_repetition_count,
    ROW_NUMBER() OVER (
      PARTITION BY event_identity, source_row_signature
      ORDER BY event_timestamp, block_number, transaction_index,
               event_index, trace_address_json, source_row_signature
    ) AS exact_duplicate_rank
  FROM source0 AS s
  LEFT JOIN mapping AS fm ON fm.wallet_address = s.from_address
  LEFT JOIN mapping AS tm ON tm.wallet_address = s.to_address
),
deduped AS (
  SELECT * EXCEPT(exact_duplicate_rank)
  FROM source1
  WHERE exact_duplicate_rank = 1
),
expanded AS (
  -- A self event produces one self row.  This also handles the case where
  -- two distinct addresses resolve to the same mapped EX-Graph node.
  SELECT
    event_identity,
    source_row_signature,
    identity_collision_flag,
    exact_row_repetition_count,
    event_timestamp,
    block_number,
    transaction_index,
    transaction_hash,
    event_index,
    trace_address_json,
    from_address,
    to_address,
    native_value,
    native_value_lossless,
    transaction_type,
    token_quantity,
    token_contract_address,
    token_id,
    removed,
    trace_type,
    subtrace_count,
    call_type,
    error,
    source_from_exgraph_node_id,
    source_to_exgraph_node_id,
    from_anchor_node AS anchor_exgraph_node_id,
    from_address AS anchor_wallet,
    COALESCE(to_address, from_address) AS counterparty_address,
    to_anchor_node AS counterparty_exgraph_node_id,
    'self' AS direction,
    event_family,
    touches_target_from,
    touches_target_to
  FROM deduped
  WHERE from_anchor_node IS NOT NULL
    AND (
      (from_address IS NOT NULL AND to_address IS NOT NULL AND from_address = to_address)
      OR (from_anchor_node IS NOT NULL AND to_anchor_node IS NOT NULL AND from_anchor_node = to_anchor_node)
    )

  UNION ALL

  -- Non-self source endpoint is the anchor: outgoing.
  SELECT
    event_identity,
    source_row_signature,
    identity_collision_flag,
    exact_row_repetition_count,
    event_timestamp,
    block_number,
    transaction_index,
    transaction_hash,
    event_index,
    trace_address_json,
    from_address,
    to_address,
    native_value,
    native_value_lossless,
    transaction_type,
    token_quantity,
    token_contract_address,
    token_id,
    removed,
    trace_type,
    subtrace_count,
    call_type,
    error,
    source_from_exgraph_node_id,
    source_to_exgraph_node_id,
    from_anchor_node AS anchor_exgraph_node_id,
    from_address AS anchor_wallet,
    to_address AS counterparty_address,
    to_anchor_node AS counterparty_exgraph_node_id,
    'outgoing' AS direction,
    event_family,
    touches_target_from,
    touches_target_to
  FROM deduped
  WHERE from_anchor_node IS NOT NULL
    AND NOT (
      (from_address IS NOT NULL AND to_address IS NOT NULL AND from_address = to_address)
      OR (from_anchor_node IS NOT NULL AND to_anchor_node IS NOT NULL AND from_anchor_node = to_anchor_node)
    )

  UNION ALL

  -- Non-self destination endpoint is the anchor: incoming.
  SELECT
    event_identity,
    source_row_signature,
    identity_collision_flag,
    exact_row_repetition_count,
    event_timestamp,
    block_number,
    transaction_index,
    transaction_hash,
    event_index,
    trace_address_json,
    from_address,
    to_address,
    native_value,
    native_value_lossless,
    transaction_type,
    token_quantity,
    token_contract_address,
    token_id,
    removed,
    trace_type,
    subtrace_count,
    call_type,
    error,
    source_from_exgraph_node_id,
    source_to_exgraph_node_id,
    to_anchor_node AS anchor_exgraph_node_id,
    to_address AS anchor_wallet,
    from_address AS counterparty_address,
    from_anchor_node AS counterparty_exgraph_node_id,
    'incoming' AS direction,
    event_family,
    touches_target_from,
    touches_target_to
  FROM deduped
  WHERE to_anchor_node IS NOT NULL
    AND NOT (
      (from_address IS NOT NULL AND to_address IS NOT NULL AND from_address = to_address)
      OR (from_anchor_node IS NOT NULL AND to_anchor_node IS NOT NULL AND from_anchor_node = to_anchor_node)
    )
),
finalized AS (
  SELECT
    e.*,
    CASE
      WHEN e.counterparty_exgraph_node_id IS NOT NULL
        THEN CONCAT('mapped_node:', CAST(e.counterparty_exgraph_node_id AS STRING))
      WHEN e.counterparty_address IS NOT NULL
        THEN CONCAT('unmapped_address:', e.counterparty_address)
      ELSE NULL
    END AS counterparty_identity,
    e.counterparty_exgraph_node_id IS NOT NULL AS counterparty_is_exgraph_mapped,
    TO_HEX(SHA256(CONCAT(
      e.event_identity, '|anchor=', e.anchor_wallet, '|direction=', e.direction
    ))) AS anchor_event_identity
  FROM expanded AS e
  WHERE e.anchor_wallet IS NOT NULL
)
SELECT
  anchor_wallet,
  anchor_exgraph_node_id,
  counterparty_address,
  counterparty_exgraph_node_id,
  counterparty_identity,
  counterparty_is_exgraph_mapped,
  direction,
  event_family,
  event_timestamp,
  block_number,
  transaction_index,
  transaction_hash,
  event_index,
  trace_address_json,
  event_identity,
  anchor_event_identity,
  source_row_signature,
  identity_collision_flag,
  exact_row_repetition_count,
  native_value,
  native_value_lossless,
  token_quantity,
  token_contract_address,
  token_id,
  transaction_type,
  trace_type,
  subtrace_count,
  call_type,
  removed,
  error,
  source_from_exgraph_node_id,
  source_to_exgraph_node_id,
  touches_target_from,
  touches_target_to
FROM finalized;
