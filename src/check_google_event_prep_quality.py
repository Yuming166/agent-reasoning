#!/usr/bin/env python3
"""Run count-only quality checks on materialized BigQuery event tables."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_google_coverage_validation import BQError, BigQueryClient  # noqa: E402


def timestamp_value(value: Any) -> Any:
    """BigQuery REST returns TIMESTAMP scalar cells as Unix seconds."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return value


def make_sql(project: str, dataset: str, start: str, end: str) -> str:
    base = f"{project}.{dataset}"
    return f"""SELECT * FROM (
SELECT 'external_tx' AS event_family, COUNT(*) AS row_count,
  COUNT(DISTINCT transaction_hash) AS distinct_transaction_hashes,
  MIN(block_timestamp) AS min_ts, MAX(block_timestamp) AS max_ts,
  COUNTIF(transaction_hash IS NULL) AS null_transaction_hashes,
  COUNTIF(from_exgraph_node_id IS NOT NULL OR to_exgraph_node_id IS NOT NULL) AS rows_with_target_node,
  COUNTIF(touches_target_from) AS touches_from, COUNTIF(touches_target_to) AS touches_to,
  CAST(NULL AS INT64) AS removed_rows, CAST(NULL AS INT64) AS error_rows
FROM `{base}.external_transactions_{start.replace('-', '')}_{end.replace('-', '')}`
WHERE block_timestamp >= TIMESTAMP('{start} 00:00:00+00')
  AND block_timestamp < TIMESTAMP('{end} 00:00:00+00')
UNION ALL
SELECT 'token_transfer', COUNT(*), COUNT(DISTINCT transaction_hash), MIN(block_timestamp), MAX(block_timestamp),
  COUNTIF(transaction_hash IS NULL),
  COUNTIF(from_exgraph_node_id IS NOT NULL OR to_exgraph_node_id IS NOT NULL),
  COUNTIF(touches_target_from), COUNTIF(touches_target_to), COUNTIF(removed IS TRUE), CAST(NULL AS INT64)
FROM `{base}.token_transfers_{start.replace('-', '')}_{end.replace('-', '')}`
WHERE block_timestamp >= TIMESTAMP('{start} 00:00:00+00')
  AND block_timestamp < TIMESTAMP('{end} 00:00:00+00')
UNION ALL
SELECT 'internal_trace', COUNT(*), COUNT(DISTINCT transaction_hash), MIN(block_timestamp), MAX(block_timestamp),
  COUNTIF(transaction_hash IS NULL),
  COUNTIF(from_exgraph_node_id IS NOT NULL OR to_exgraph_node_id IS NOT NULL),
  COUNTIF(touches_target_from), COUNTIF(touches_target_to), CAST(NULL AS INT64), COUNTIF(error IS NOT NULL)
FROM `{base}.internal_traces_{start.replace('-', '')}_{end.replace('-', '')}`
WHERE block_timestamp >= TIMESTAMP('{start} 00:00:00+00')
  AND block_timestamp < TIMESTAMP('{end} 00:00:00+00')
) ORDER BY event_family"""


def job_summary(result: dict[str, Any]) -> dict[str, Any]:
    stats = result.get("_job_metadata", {}).get("statistics", {}).get("query", {})
    source = stats or result
    return {
        "job_reference": result.get("jobReference"),
        "total_bytes_processed": int(source.get("totalBytesProcessed", 0)),
        "total_bytes_billed": int(source.get("totalBytesBilled", 0)),
        "cache_hit": source.get("cacheHit"),
    }


def parse_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [f["name"] for f in result.get("schema", {}).get("fields", [])]
    rows = []
    for row in result.get("rows", []):
        values = [cell.get("v") for cell in row.get("f", [])]
        out = dict(zip(fields, values))
        out["min_ts"] = timestamp_value(out.get("min_ts"))
        out["max_ts"] = timestamp_value(out.get("max_ts"))
        rows.append(out)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--dataset-id", default="exgraph")
    ap.add_argument("--start", default="2022-03-01")
    ap.add_argument("--end", default="2022-09-01")
    ap.add_argument("--max-bytes-billed", type=int, default=10_000_000_000)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--gcloud-bin", default=os.environ.get("GCLOUD_BIN", "gcloud"))
    args = ap.parse_args()

    client = BigQueryClient(args.project_id, args.gcloud_bin)
    sql = make_sql(args.project_id, args.dataset_id, args.start, args.end)
    dry = client.query(sql, dry_run=True, max_bytes=args.max_bytes_billed)
    dry_s = job_summary(dry)
    print(json.dumps({"dry_run": dry_s}, indent=2))
    if dry_s["total_bytes_processed"] > args.max_bytes_billed:
        raise BQError(
            f"Quality check estimate {dry_s['total_bytes_processed']} exceeds guard "
            f"{args.max_bytes_billed}"
        )
    actual = client.query(sql, dry_run=False, max_bytes=args.max_bytes_billed)
    actual_s = job_summary(actual)
    rows = parse_rows(actual)
    print(json.dumps({"actual": actual_s, "rows": rows}, indent=2))
    out = {
        "project_id": args.project_id,
        "dataset_id": args.dataset_id,
        "window_utc": {"start_inclusive": args.start, "end_exclusive": args.end},
        "dry_run": dry_s,
        "actual_query": actual_s,
        "rows": rows,
        "sql": sql,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"saved: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BQError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
