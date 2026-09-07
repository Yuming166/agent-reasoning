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
cd .
export HTTPS_PROXY=<your-proxy-if-needed>
export HTTP_PROXY=<your-proxy-if-needed>
export ALL_PROXY=<your-proxy-if-needed>
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
