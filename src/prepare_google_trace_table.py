#!/usr/bin/env python3
"""Materialize target-touching internal Ethereum traces in BigQuery.

Trace rows stay in BigQuery. The jump host receives only job metadata, so this
is safe for a low-egress preparation workflow. The table is intentionally kept
separate from native transactions and token transfers because trace semantics
and deduplication are different.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

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


def trace_sql(project: str, dataset: str, target_table: str,
              output_table: str, start: str, end: str) -> str:
    target = qname(project, dataset, target_table)
    output = qname(project, dataset, output_table)
    source = qname(PUBLIC_PROJECT, PUBLIC_DATASET, "traces")
    return f"""-- Materialize target-touching internal value-flow traces.
-- Keep traces separate from external transactions and token transfers.
CREATE OR REPLACE TABLE {output}
PARTITION BY DATE(block_timestamp)
CLUSTER BY from_address, to_address
OPTIONS(
  description = 'EX-Graph target-touching internal Ethereum traces; six-month pilot',
  require_partition_filter = TRUE
)
AS
WITH target AS (
  SELECT LOWER(ethereum_address) AS address, ANY_VALUE(exgraph_node_id) AS exgraph_node_id
  FROM {target}
  GROUP BY address
)
SELECT
  'internal_trace' AS event_family,
  tr.block_timestamp,
  tr.block_number,
  tr.transaction_index,
  tr.transaction_hash,
  tr.trace_type,
  tr.trace_address,
  tr.subtrace_count,
  LOWER(tr.action.from_address) AS from_address,
  LOWER(tr.action.to_address) AS to_address,
  tr.action.call_type,
  tr.action.value,
  tr.action.value_lossless,
  tr.error,
  a_from.exgraph_node_id AS from_exgraph_node_id,
  a_to.exgraph_node_id AS to_exgraph_node_id,
  a_from.address IS NOT NULL AS touches_target_from,
  a_to.address IS NOT NULL AS touches_target_to
FROM {source} AS tr
LEFT JOIN target AS a_from
  ON LOWER(tr.action.from_address) = a_from.address
LEFT JOIN target AS a_to
  ON LOWER(tr.action.to_address) = a_to.address
WHERE tr.block_timestamp >= TIMESTAMP('{start} 00:00:00+00')
  AND tr.block_timestamp < TIMESTAMP('{end} 00:00:00+00')
  AND (a_from.address IS NOT NULL OR a_to.address IS NOT NULL);
"""


def get_table(client: BigQueryClient, project: str, dataset: str,
              table: str) -> dict[str, Any]:
    return client.request(
        "GET",
        f"/bigquery/v2/projects/{project}/datasets/{dataset}/tables/{table}",
    ).json()


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


def table_summary(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta.get("id"),
        "num_rows": int(meta["numRows"]) if meta.get("numRows") is not None else None,
        "num_bytes": int(meta["numBytes"]) if meta.get("numBytes") is not None else None,
        "time_partitioning": meta.get("timePartitioning"),
        "clustering": meta.get("clustering"),
        "require_partition_filter": meta.get("requirePartitionFilter"),
        "schema_fields": [f.get("name") for f in meta.get("schema", {}).get("fields", [])],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--dataset-id", default="exgraph")
    ap.add_argument("--target-table", default="target_addresses")
    ap.add_argument("--start", default="2022-03-01")
    ap.add_argument("--end", default="2022-09-01")
    ap.add_argument("--max-bytes-billed", type=int, default=300_000_000_000)
    ap.add_argument("--dry-run-only", action="store_true")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--gcloud-bin", default=os.environ.get("GCLOUD_BIN", "gcloud"))
    args = ap.parse_args()

    client = BigQueryClient(args.project_id, args.gcloud_bin)
    output_table = f"internal_traces_{args.start.replace('-', '')}_{args.end.replace('-', '')}"
    sql = trace_sql(
        args.project_id, args.dataset_id, args.target_table,
        output_table, args.start, args.end
    )
    dry = client.query(sql, dry_run=True, max_bytes=args.max_bytes_billed)
    dry_s = job_summary(dry)
    print(json.dumps({"table": output_table, "dry_run": dry_s}, indent=2))
    if dry_s["total_bytes_processed"] > args.max_bytes_billed:
        raise BQError(
            f"Refusing {output_table}: dry-run estimate "
            f"{dry_s['total_bytes_processed']} exceeds guard {args.max_bytes_billed}"
        )

    actual_s = None
    meta_s = None
    if not args.dry_run_only:
        actual = client.query(sql, dry_run=False, max_bytes=args.max_bytes_billed)
        actual_s = job_summary(actual)
        print(json.dumps({"table": output_table, "actual": actual_s}, indent=2))
        meta = get_table(client, args.project_id, args.dataset_id, output_table)
        meta_s = table_summary(meta)
        print(json.dumps({"table": output_table, "metadata": meta_s}, indent=2))

    manifest = {
        "run_date": time.strftime("%Y-%m-%d"),
        "project_id": args.project_id,
        "dataset_id": args.dataset_id,
        "target_table": f"{args.project_id}.{args.dataset_id}.{args.target_table}",
        "output_table": f"{args.project_id}.{args.dataset_id}.{output_table}",
        "public_source": f"{PUBLIC_PROJECT}.{PUBLIC_DATASET}.traces",
        "location": LOCATION,
        "window_utc": {"start_inclusive": args.start, "end_exclusive": args.end},
        "max_bytes_billed": args.max_bytes_billed,
        "transport_policy": "materialize in BigQuery; do not stream source rows through jump host",
        "dry_run": dry_s,
        "actual_query": actual_s,
        "metadata": meta_s,
        "sql": sql,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"saved: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BQError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
