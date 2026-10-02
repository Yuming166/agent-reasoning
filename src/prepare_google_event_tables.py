#!/usr/bin/env python3
"""Materialize filtered temporal Ethereum events in BigQuery.

The source tables are scanned and filtered inside BigQuery. No source rows are
streamed through the jump host. The result is two partitioned, clustered tables
(one native transaction table and one token-transfer table), retaining all
counterparties for any event touching an EX-Graph-mapped address.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Allow execution as `python src/prepare_google_event_tables.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_google_coverage_validation import (  # noqa: E402
    BQError,
    BigQueryClient,
    LOCATION,
    PUBLIC_DATASET,
    PUBLIC_PROJECT,
)


def qname(project: str, dataset: str, table: str) -> str:
    return f"`{project}.{dataset}.{table}`"


def external_sql(project: str, dataset: str, target_table: str,
                 output_table: str, start: str, end: str) -> str:
    target = qname(project, dataset, target_table)
    output = qname(project, dataset, output_table)
    source = qname(PUBLIC_PROJECT, PUBLIC_DATASET, "transactions")
    return f"""-- Materialize target-touching native Ethereum transactions.
-- All counterparties are retained; only one endpoint must be in the target set.
CREATE OR REPLACE TABLE {output}
PARTITION BY DATE(block_timestamp)
CLUSTER BY from_address, to_address
OPTIONS(
  description = 'EX-Graph target-touching native Ethereum transactions; six-month pilot',
  require_partition_filter = TRUE
)
AS
WITH target AS (
  SELECT LOWER(ethereum_address) AS address, ANY_VALUE(exgraph_node_id) AS exgraph_node_id
  FROM {target}
  GROUP BY address
)
SELECT
  'external_tx' AS event_family,
  t.block_timestamp,
  t.block_number,
  t.transaction_index,
  t.transaction_hash,
  LOWER(t.from_address) AS from_address,
  LOWER(t.to_address) AS to_address,
  t.value,
  t.value_lossless,
  t.transaction_type,
  a_from.exgraph_node_id AS from_exgraph_node_id,
  a_to.exgraph_node_id AS to_exgraph_node_id,
  a_from.address IS NOT NULL AS touches_target_from,
  a_to.address IS NOT NULL AS touches_target_to
FROM {source} AS t
LEFT JOIN target AS a_from
  ON LOWER(t.from_address) = a_from.address
LEFT JOIN target AS a_to
  ON LOWER(t.to_address) = a_to.address
WHERE t.block_timestamp >= TIMESTAMP('{start} 00:00:00+00')
  AND t.block_timestamp < TIMESTAMP('{end} 00:00:00+00')
  AND (a_from.address IS NOT NULL OR a_to.address IS NOT NULL);
"""


def token_sql(project: str, dataset: str, target_table: str,
              output_table: str, start: str, end: str) -> str:
    target = qname(project, dataset, target_table)
    output = qname(project, dataset, output_table)
    source = qname(PUBLIC_PROJECT, PUBLIC_DATASET, "token_transfers")
    return f"""-- Materialize target-touching token transfer events.
-- All counterparties are retained; only one endpoint must be in the target set.
CREATE OR REPLACE TABLE {output}
PARTITION BY DATE(block_timestamp)
CLUSTER BY from_address, to_address, token_contract_address
OPTIONS(
  description = 'EX-Graph target-touching token transfers; six-month pilot',
  require_partition_filter = TRUE
)
AS
WITH target AS (
  SELECT LOWER(ethereum_address) AS address, ANY_VALUE(exgraph_node_id) AS exgraph_node_id
  FROM {target}
  GROUP BY address
)
SELECT
  'token_transfer' AS event_family,
  tt.block_timestamp,
  tt.block_number,
  tt.transaction_index,
  tt.transaction_hash,
  tt.event_index,
  LOWER(tt.address) AS token_contract_address,
  LOWER(tt.from_address) AS from_address,
  LOWER(tt.to_address) AS to_address,
  tt.token_id,
  tt.quantity,
  tt.removed,
  a_from.exgraph_node_id AS from_exgraph_node_id,
  a_to.exgraph_node_id AS to_exgraph_node_id,
  a_from.address IS NOT NULL AS touches_target_from,
  a_to.address IS NOT NULL AS touches_target_to
FROM {source} AS tt
LEFT JOIN target AS a_from
  ON LOWER(tt.from_address) = a_from.address
LEFT JOIN target AS a_to
  ON LOWER(tt.to_address) = a_to.address
WHERE tt.block_timestamp >= TIMESTAMP('{start} 00:00:00+00')
  AND tt.block_timestamp < TIMESTAMP('{end} 00:00:00+00')
  AND (a_from.address IS NOT NULL OR a_to.address IS NOT NULL);
"""


def get_table(client: BigQueryClient, project: str, dataset: str,
              table: str) -> dict[str, Any]:
    path = f"/bigquery/v2/projects/{project}/datasets/{dataset}/tables/{table}"
    return client.request("GET", path).json()


def table_summary(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta.get("id"),
        "type": meta.get("type"),
        "num_rows": int(meta["numRows"]) if meta.get("numRows") is not None else None,
        "num_bytes": int(meta["numBytes"]) if meta.get("numBytes") is not None else None,
        "creation_time": meta.get("creationTime"),
        "last_modified_time": meta.get("lastModifiedTime"),
        "time_partitioning": meta.get("timePartitioning"),
        "clustering": meta.get("clustering"),
        "require_partition_filter": meta.get("requirePartitionFilter"),
        "schema_fields": [f.get("name") for f in meta.get("schema", {}).get("fields", [])],
    }


def job_summary(result: dict[str, Any]) -> dict[str, Any]:
    stats = result.get("_job_metadata", {}).get("statistics", {}).get("query", {})
    source = stats or result
    return {
        "job_reference": result.get("jobReference"),
        "total_bytes_processed": int(source.get("totalBytesProcessed", 0)),
        "total_bytes_billed": int(source.get("totalBytesBilled", 0)),
        "cache_hit": source.get("cacheHit"),
        "statement_type": source.get("statementType"),
    }


def run_one(client: BigQueryClient, sql: str, output_table: str,
            max_bytes: int) -> tuple[dict[str, Any], dict[str, Any]]:
    dry = client.query(sql, dry_run=True, max_bytes=max_bytes)
    dry_s = job_summary(dry)
    print(json.dumps({"table": output_table, "dry_run": dry_s}, indent=2))
    if dry_s["total_bytes_processed"] > max_bytes:
        raise BQError(
            f"Refusing {output_table}: dry-run estimate "
            f"{dry_s['total_bytes_processed']} exceeds guard {max_bytes}"
        )
    actual = client.query(sql, dry_run=False, max_bytes=max_bytes)
    actual_s = job_summary(actual)
    print(json.dumps({"table": output_table, "actual": actual_s}, indent=2))
    return dry_s, actual_s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--dataset-id", default="exgraph")
    ap.add_argument("--target-table", default="target_addresses")
    ap.add_argument("--start", default="2022-03-01")
    ap.add_argument("--end", default="2022-09-01")
    ap.add_argument("--max-bytes-billed", type=int, default=100_000_000_000)
    ap.add_argument("--dry-run-only", action="store_true", help="do not materialize output tables")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--gcloud-bin", default=os.environ.get("GCLOUD_BIN", "gcloud"))
    args = ap.parse_args()

    client = BigQueryClient(args.project_id, args.gcloud_bin)
    external_table = f"external_transactions_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
    token_table = f"token_transfers_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
    sqls = {
        external_table: external_sql(
            args.project_id, args.dataset_id, args.target_table,
            external_table, args.start, args.end
        ),
        token_table: token_sql(
            args.project_id, args.dataset_id, args.target_table,
            token_table, args.start, args.end
        ),
    }

    manifest: dict[str, Any] = {
        "run_date": time.strftime("%Y-%m-%d"),
        "project_id": args.project_id,
        "dataset_id": args.dataset_id,
        "target_table": f"{args.project_id}.{args.dataset_id}.{args.target_table}",
        "public_source": f"{PUBLIC_PROJECT}.{PUBLIC_DATASET}",
        "location": LOCATION,
        "window_utc": {
            "start_inclusive": args.start,
            "end_exclusive": args.end,
        },
        "max_bytes_billed": args.max_bytes_billed,
        "transport_policy": "materialize in BigQuery; do not stream source rows through jump host",
        "tables": {},
    }

    for table, sql in sqls.items():
        dry = client.query(sql, dry_run=True, max_bytes=args.max_bytes_billed)
        dry_s = job_summary(dry)
        print(json.dumps({"table": table, "dry_run": dry_s}, indent=2))
        if dry_s["total_bytes_processed"] > args.max_bytes_billed:
            raise BQError(
                f"Refusing {table}: dry-run estimate "
                f"{dry_s['total_bytes_processed']} exceeds guard {args.max_bytes_billed}"
            )
        actual_s = None
        meta = None
        if not args.dry_run_only:
            actual = client.query(sql, dry_run=False, max_bytes=args.max_bytes_billed)
            actual_s = job_summary(actual)
            print(json.dumps({"table": table, "actual": actual_s}, indent=2))
            meta = table_summary(get_table(client, args.project_id, args.dataset_id, table))
        manifest["tables"][table] = {
            "fully_qualified": f"{args.project_id}.{args.dataset_id}.{table}",
            "dry_run": dry_s,
            "actual_query": actual_s,
            "metadata": meta,
            "sql": sql,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"saved: {args.output}")
    for table, info in manifest["tables"].items():
        if info["metadata"] is not None:
            print(json.dumps({"table": table, "metadata": info["metadata"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BQError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
