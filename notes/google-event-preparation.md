# Google temporal event preparation

**Run date:** 2026-09-07

## Materialized tables

The six-month pilot was materialized inside BigQuery; no source event rows were
streamed through or downloaded to the jump host.

| Event family | BigQuery table | Rows | Logical bytes | Partition / clustering |
|---|---|---:|---:|---|
| Native transaction | `ictdata-507912.exgraph.external_transactions_20220301_20220901` | 2,877,009 | 729,336,363 | `DATE(block_timestamp)` / `from_address, to_address` |
| Token transfer | `ictdata-507912.exgraph.token_transfers_20220301_20220901` | 4,275,544 | 1,164,125,153 | `DATE(block_timestamp)` / `from_address, to_address, token_contract_address` |
| Internal trace | `ictdata-507912.exgraph.internal_traces_20220301_20220901` | 4,478,515 | 1,229,594,363 | `DATE(block_timestamp)` / `from_address, to_address` |

All three tables have `require_partition_filter=true`.

## Filtering and retained fields

A row is kept when either endpoint matches one of the 27,613 EX-Graph-mapped
addresses. The non-mapped endpoint is retained, so the tables can be used for
counterparty prediction rather than only mapped-to-mapped edges.

Each output row contains the event timestamp, block number, transaction index,
transaction hash, normalized endpoints, source value/quantity fields, and the
EX-Graph node IDs for the mapped endpoints. Native transactions and token
transfers remain separate event families; they are not silently deduplicated.

## Query accounting

- External transaction CTAS: 48,075,704,989 bytes processed; 48,076,161,024 bytes billed.
- Token transfer CTAS: 48,493,917,084 bytes processed; 48,494,542,848 bytes billed.
- Internal trace CTAS: 219,165,989,799 bytes processed; 219,166,015,488 bytes billed.
- Combined billed source scan: 315,736,719,360 bytes.
- External/token CTAS jobs used a 100 GB `maximumBytesBilled` guard; the trace CTAS used a 300 GB guard after its dry-run estimate was checked.
- The local target CSV uploaded to BigQuery was 1,412,793 bytes.

The output tables are stored in the US BigQuery dataset and have not been
exported to Cloud Storage or downloaded locally. This keeps jump-host traffic
at approximately the target-table upload plus API metadata/result responses.
The three tables contain 11,631,068 rows and about 2.91 GiB of logical table
data in BigQuery; that logical data has not crossed the jump-host connection.

A count-only quality check found zero null transaction hashes and zero rows
without a matched EX-Graph node. External transactions are one row per
transaction hash in this materialization; token transfers and traces are
event-level, so multiple rows per transaction hash are expected. The token
transfer table had zero `removed=true` rows in this window. The traces table
retains 122,317 rows with a non-null `error` field for downstream filtering.
See `artifacts/google_event_prep_quality_2022-03_2022-09.json` and
`src/check_google_event_prep_quality.py`.

## Reproduction

```bash
cd /storage/gaoym/ex-graph-microtransaction-analysis
export HTTPS_PROXY=http://10.63.0.72:7890
export HTTP_PROXY=http://10.63.0.72:7890
export ALL_PROXY=http://10.63.0.72:7890
python src/prepare_google_event_tables.py \
  --project-id ictdata-507912 \
  --dataset-id exgraph \
  --target-table target_addresses \
  --start 2022-03-01 \
  --end 2022-09-01 \
  --max-bytes-billed 100000000000 \
  --output artifacts/google_event_prep_2022-03_2022-09.json
```

The execution manifests are `artifacts/google_event_prep_2022-03_2022-09.json` and
`artifacts/google_trace_prep_2022-03_2022-09.json`. Dry-run-only manifests are
`artifacts/google_event_prep_2022-03_2022-09_dryrun.json` and
`artifacts/google_trace_prep_2022-03_2022-09_dryrun.json`.
For traces, use `src/prepare_google_trace_table.py` with a 300 GB guard.

## Unified view

On 2026-09-07, the three materialized tables were combined with `UNION ALL` into:

```text
ictdata-507912.exgraph.target_events_20220301_20220901
```

The view preserves event-family semantics and does not deduplicate by
`transaction_hash`. A validation query over the full 2022-03-01 through
2022-09-01 UTC window returned 2,877,009 `external_tx` rows, 4,275,544
`token_transfer` rows, and 4,478,515 `internal_trace` rows. All 11,631,068
rows had a non-null EX-Graph node on at least one endpoint and the corresponding
`touches_target_from`/`touches_target_to` flag was true.

Reproduction files:

```text
src/sql/create_target_events_view_ictdata.sql
src/create_target_events_view.py
artifacts/google_target_events_view_2022-03_2022-09.json
```

The other endpoint is intentionally retained when it is not in EX-Graph so
that downstream counterparty prediction is not restricted to mapped-to-mapped
edges.

## Official EX-Graph match dimension and directional sequences

On 2026-09-07, the released local `vendor/EX-Graph-repo/twitter_matching.csv`
was verified to contain 27,613 unique `(exgraph_node_id, ethereum_address)`
pairs. The source repository snapshot is commit
`298a52564f5d7f8e30f7f8e6919ae1b3168db481`; the source file SHA-256 is
`1d2e3d5a0dbf44797a2026ac9cdb23b76f20e227630c90393e80f00172c9b5ba`.

The mapping dimension was materialized as:

```text
ictdata-507912.exgraph.exgraph_x_matches_v1
```

It includes the normalized address, EX-Graph node ID,
`official_exgraph_match` status, source provenance, and mapping version. It
does not include a raw X/Twitter handle or user ID.

The directional event table was materialized as:

```text
ictdata-507912.exgraph.target_event_sequences_20220301_20220901
```

Its semantics are:

- `target_address` is the matched endpoint and `counterparty_address` is the
  other endpoint.
- A source event with two different matched endpoints produces two role rows;
  a self-transaction produces one row with `direction=self`.
- `external_tx` and `token_transfer` are `sequence_role=primary`;
  `internal_trace` is retained as `sequence_role=auxiliary` for ablations.
- `target_sequence_index` is deterministic for each target address. It orders
  by timestamp, block, transaction index, event-family order, event index or
  trace address, then deterministic tie-breakers. Cross-family ordering within
  the same transaction is a deterministic tie-breaker, not a canonical EVM
  event order.
- Rows without a destination address are retained with
  `counterparty_present=false`; they should not be used as next-counterparty
  labels.

### Materialization accounting

| Table | Rows | Logical bytes |
|---|---:|---:|
| `exgraph_x_matches_v1` | 27,613 | 7,068,928 |
| `target_event_sequences_20220301_20220901` | 11,836,196 | 5,095,709,899 |

The sequence CTAS read 3,125,154,467 bytes and billed 3,125,805,056 bytes.
The source event tables were not downloaded to the jump host.

### Sequence quality checks

- All 11,836,196 sequence rows have a non-null target address, target EX-Graph
  node, transaction hash, sequence index, and official target match status.
- 21,469 of the 27,613 mapped addresses occur in this six-month window when
  internal traces are included.
- 11,832,912 rows have a non-null counterparty; 3,284 rows are retained with
  `counterparty_present=false`.
- 27,499 rows are self-transactions.
- The `(target_address, target_sequence_index)` pair is unique.
- 437,755 directional rows have an officially matched counterparty.

Reproduction SQL:

```text
src/sql/create_exgraph_sequence_tables_ictdata.sql
```

Execution and validation manifest:

```text
artifacts/google_sequence_tables_2022-03_2022-09.json
```
