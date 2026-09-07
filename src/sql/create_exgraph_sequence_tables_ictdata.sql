-- Build the official EX-Graph match dimension and a directional temporal event
-- table for the 2022-03-01 (inclusive) through 2022-09-01 (exclusive) window.
--
-- The match table is copied from the already loaded target_addresses table,
-- whose rows were verified against vendor/EX-Graph-repo/twitter_matching.csv.
-- It deliberately stores provenance but no raw Twitter handle/user metadata.
--
-- The sequence table emits one row per matched endpoint role:
--   * outgoing: from_address is the target and to_address is the counterparty
--   * incoming: to_address is the target and from_address is the counterparty
--   * self: one row for a self-transaction, not two duplicate endpoint rows
-- If both endpoints are different EX-Graph-matched addresses, two directional
-- rows are emitted. Native transactions and token transfers are primary events;
-- internal traces are retained but marked auxiliary for later ablations.

CREATE OR REPLACE TABLE `ictdata-507912.exgraph.exgraph_x_matches_v1`
OPTIONS(
  description = 'Official EX-Graph Ethereum-to-X/Twitter match dimension derived from the released matching file; 27,613 local release rows; no raw handles included.'
)
AS
SELECT
  CAST(exgraph_node_id AS INT64) AS exgraph_node_id,
  LOWER(ethereum_address) AS ethereum_address,
  'official_exgraph_match' AS match_status,
  'EX-Graph / OpenSea' AS mapping_source,
  'Persdre/EX-Graph' AS source_repository,
  '298a52564f5d7f8e30f7f8e6919ae1b3168db481' AS source_repository_commit,
  'twitter_matching.csv' AS source_file,
  '1d2e3d5a0dbf44797a2026ac9cdb23b76f20e227630c90393e80f00172c9b5ba' AS source_file_sha256,
  DATE '2026-09-07' AS source_retrieved_date,
  'v1' AS mapping_version
FROM `ictdata-507912.exgraph.target_addresses`;

CREATE OR REPLACE TABLE `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`
PARTITION BY DATE(block_timestamp)
CLUSTER BY target_exgraph_node_id, counterparty_address, event_family
OPTIONS(
  description = 'Directional EX-Graph target event sequences for 2022-03-01 through 2022-09-01 UTC. External transactions and token transfers are primary; internal traces are auxiliary. Each matched endpoint gets a target/counterparty role; self-transactions emit one row. Rows with no destination address are retained and marked counterparty_present=false.',
  require_partition_filter = TRUE
)
AS
WITH base AS (
  SELECT
    event_family,
    block_timestamp,
    block_number,
    transaction_index,
    transaction_hash,
    event_index,
    from_address,
    to_address,
    value,
    value_lossless,
    transaction_type,
    quantity,
    token_contract_address,
    token_id,
    removed,
    trace_type,
    trace_address,
    subtrace_count,
    call_type,
    error,
    from_exgraph_node_id AS source_from_exgraph_node_id,
    to_exgraph_node_id AS source_to_exgraph_node_id,
    touches_target_from,
    touches_target_to,
    CASE event_family
      WHEN 'external_tx' THEN 0
      WHEN 'token_transfer' THEN 1
      WHEN 'internal_trace' THEN 2
      ELSE 9
    END AS event_family_order
  FROM `ictdata-507912.exgraph.target_events_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
),
roles AS (
  -- Distinct endpoints: outgoing role.
  SELECT
    b.*,
    LOWER(from_address) AS target_address,
    LOWER(to_address) AS counterparty_address,
    'outgoing' AS direction,
    FALSE AS self_transaction
  FROM base AS b
  WHERE touches_target_from
    AND NOT (
      touches_target_to
      AND LOWER(from_address) = LOWER(to_address)
    )

  UNION ALL

  -- Distinct endpoints: incoming role.
  SELECT
    b.*,
    LOWER(to_address) AS target_address,
    LOWER(from_address) AS counterparty_address,
    'incoming' AS direction,
    FALSE AS self_transaction
  FROM base AS b
  WHERE touches_target_to
    AND NOT (
      touches_target_from
      AND LOWER(from_address) = LOWER(to_address)
    )

  UNION ALL

  -- Self-transaction: emit one row instead of two duplicate endpoint roles.
  SELECT
    b.*,
    LOWER(from_address) AS target_address,
    LOWER(to_address) AS counterparty_address,
    'self' AS direction,
    TRUE AS self_transaction
  FROM base AS b
  WHERE touches_target_from
    AND touches_target_to
    AND LOWER(from_address) = LOWER(to_address)
),
enriched AS (
  SELECT
    r.*,
    target_match.exgraph_node_id AS target_exgraph_node_id,
    counterparty_match.exgraph_node_id AS counterparty_exgraph_node_id,
    target_match.match_status AS target_match_status,
    counterparty_match.match_status AS counterparty_match_status,
    target_match.exgraph_node_id IS NOT NULL AS target_is_x_matched,
    counterparty_match.exgraph_node_id IS NOT NULL AS counterparty_is_x_matched,
    r.counterparty_address IS NOT NULL AS counterparty_present,
    CASE
      WHEN r.event_family = 'internal_trace' THEN 'auxiliary'
      ELSE 'primary'
    END AS sequence_role,
    target_match.exgraph_node_id IS NOT NULL
      AND counterparty_match.exgraph_node_id IS NOT NULL
      AS both_endpoints_are_x_matched
  FROM roles AS r
  LEFT JOIN `ictdata-507912.exgraph.exgraph_x_matches_v1` AS target_match
    ON r.target_address = target_match.ethereum_address
  LEFT JOIN `ictdata-507912.exgraph.exgraph_x_matches_v1` AS counterparty_match
    ON r.counterparty_address = counterparty_match.ethereum_address
)
SELECT
  ROW_NUMBER() OVER (
    PARTITION BY target_address
    ORDER BY
      block_timestamp,
      block_number,
      transaction_index,
      event_family_order,
      COALESCE(event_index, -1),
      COALESCE(TO_JSON_STRING(trace_address), ''),
      direction,
      counterparty_address,
      transaction_hash
  ) - 1 AS target_sequence_index,
  target_exgraph_node_id,
  target_address,
  target_match_status,
  target_is_x_matched,
  counterparty_exgraph_node_id,
  counterparty_address,
  counterparty_match_status,
  counterparty_is_x_matched,
  counterparty_present,
  both_endpoints_are_x_matched,
  direction,
  self_transaction,
  sequence_role,
  event_family,
  event_family_order,
  block_timestamp,
  block_number,
  transaction_index,
  event_index,
  transaction_hash,
  from_address,
  to_address,
  value,
  value_lossless,
  transaction_type,
  token_contract_address,
  token_id,
  quantity,
  removed,
  trace_type,
  trace_address,
  subtrace_count,
  call_type,
  error,
  source_from_exgraph_node_id,
  source_to_exgraph_node_id,
  touches_target_from,
  touches_target_to
FROM enriched;
