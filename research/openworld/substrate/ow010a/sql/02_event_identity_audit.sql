-- OW-010A event identity audit. Aggregate-only output.
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
    subtrace_count,
    call_type,
    error,
    from_exgraph_node_id,
    to_exgraph_node_id,
    TO_JSON_STRING(trace_address) AS trace_address_json,
    TO_HEX(SHA256(TO_JSON_STRING(STRUCT(
      event_family AS event_family,
      block_timestamp AS event_timestamp,
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
    )))) AS row_signature,
    CASE
      WHEN event_family = 'external_tx' THEN CONCAT('external_tx|', COALESCE(transaction_hash, '<NULL_TX>'))
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
      ELSE CONCAT(COALESCE(event_family, '<NULL_FAMILY>'), '|', COALESCE(transaction_hash, '<NULL_TX>'))
    END AS event_identity
  FROM `ictdata-507912.exgraph.target_events_20220301_20220901`
  WHERE block_timestamp >= TIMESTAMP('2022-03-01 00:00:00+00')
    AND block_timestamp < TIMESTAMP('2022-09-01 00:00:00+00')
),
ids AS (
  SELECT event_family, event_identity, COUNT(*) AS identity_rows,
         COUNT(DISTINCT row_signature) AS identity_variants
  FROM source
  GROUP BY event_family, event_identity
),
family AS (
  SELECT
    'family_summary' AS audit_section,
    event_family,
    'source_rows' AS metric_name,
    CAST(COUNT(*) AS STRING) AS metric_value,
    'Family-specific source row count.' AS notes
  FROM source GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'unique_transaction_hashes', CAST(COUNT(DISTINCT transaction_hash) AS STRING), 'Distinct transaction hashes; not event identity.' FROM source GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'unique_event_identities', CAST(COUNT(DISTINCT event_identity) AS STRING), 'Distinct family-specific semantic identity.' FROM source GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'exact_duplicate_identity_groups', CAST(COUNTIF(identity_rows > 1 AND identity_variants = 1) AS STRING), 'Same identity and same full-row signature.' FROM ids GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'exact_duplicate_extra_rows', CAST(SUM(IF(identity_rows > 1 AND identity_variants = 1, identity_rows - 1, 0)) AS STRING), 'Rows removed by exact-duplicate policy.' FROM ids GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'identity_collision_groups', CAST(COUNTIF(identity_variants > 1) AS STRING), 'Same semantic identity but differing source fields; retained and flagged.' FROM ids GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'identity_collision_rows', CAST(SUM(IF(identity_variants > 1, identity_rows, 0)) AS STRING), 'Rows in collision groups; never silently overwritten.' FROM ids GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'null_transaction_hash_rows', CAST(COUNTIF(transaction_hash IS NULL) AS STRING), 'Missing transaction hash.' FROM source GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'missing_identity_component_rows', CAST(COUNTIF(
      (event_family = 'token_transfer' AND (event_index IS NULL OR token_contract_address IS NULL OR from_address IS NULL OR to_address IS NULL))
      OR (event_family = 'internal_trace' AND trace_address IS NULL)
    ) AS STRING), 'Rows missing a family-specific identity component.' FROM source GROUP BY event_family
  UNION ALL
  SELECT 'family_summary', event_family, 'self_address_rows', CAST(COUNTIF(from_address IS NOT NULL AND LOWER(from_address) = LOWER(to_address)) AS STRING), 'Same source endpoint address.' FROM source GROUP BY event_family
),
token_batch AS (
  SELECT
    'token_batch_diagnostic' AS audit_section,
    'token_transfer' AS event_family,
    metric_name,
    metric_value,
    notes
  FROM (
    SELECT 'event_index_groups_with_multiple_extended_items' AS metric_name,
           CAST(COUNTIF(n_items > 1) AS STRING) AS metric_value,
           'Groups by (transaction_hash,event_index) that contain multiple extended token items.' AS notes
    FROM (
      SELECT transaction_hash, event_index, COUNT(DISTINCT event_identity) AS n_items
      FROM source WHERE event_family = 'token_transfer'
      GROUP BY transaction_hash, event_index
    )
    UNION ALL
    SELECT 'event_index_extra_extended_items',
           CAST(SUM(IF(n_items > 1, n_items - 1, 0)) AS STRING),
           'Extra extended identities beyond one per transaction/event_index.'
    FROM (
      SELECT transaction_hash, event_index, COUNT(DISTINCT event_identity) AS n_items
      FROM source WHERE event_family = 'token_transfer'
      GROUP BY transaction_hash, event_index
    )
    UNION ALL
    SELECT 'max_extended_items_per_event_index', CAST(MAX(n_items) AS STRING),
           'Maximum number of extended token items in one transaction/event_index group.'
    FROM (
      SELECT transaction_hash, event_index, COUNT(DISTINCT event_identity) AS n_items
      FROM source WHERE event_family = 'token_transfer'
      GROUP BY transaction_hash, event_index
    )
  )
),
internal_diag AS (
  SELECT
    'internal_trace_diagnostic' AS audit_section,
    'internal_trace' AS event_family,
    metric_name,
    metric_value,
    notes
  FROM (
    SELECT 'null_trace_address_rows' AS metric_name,
           CAST(COUNTIF(trace_address IS NULL) AS STRING) AS metric_value,
           'Trace path is required for internal semantic identity.' AS notes
    FROM source WHERE event_family = 'internal_trace'
    UNION ALL
    SELECT 'distinct_transaction_hashes', CAST(COUNT(DISTINCT transaction_hash) AS STRING),
           'Transactions can contain many trace paths; transaction hash alone is insufficient.'
    FROM source WHERE event_family = 'internal_trace'
    UNION ALL
    SELECT 'distinct_trace_identities', CAST(COUNT(DISTINCT event_identity) AS STRING),
           'Internal identity uses transaction hash plus trace path.'
    FROM source WHERE event_family = 'internal_trace'
  )
)
SELECT * FROM family
UNION ALL SELECT * FROM token_batch
UNION ALL SELECT * FROM internal_diag
ORDER BY audit_section, event_family, metric_name;
