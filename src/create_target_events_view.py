#!/usr/bin/env python3
"""Create and verify the portable unified target-touching Ethereum view."""

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
)

TEMPLATE = Path(__file__).resolve().parent / "sql" / "create_target_events_view.sql"


def qname(project: str, dataset: str, table: str) -> str:
    return f"{project}.{dataset}.{table}"


def view_sql(project: str, dataset: str, start: str, end: str) -> tuple[str, str]:
    suffix_start = start.replace("-", "")
    suffix_end = end.replace("-", "")
    names = {
        "VIEW": qname(project, dataset, f"target_events_{suffix_start}_{suffix_end}"),
        "EXTERNAL": qname(project, dataset, f"external_transactions_{suffix_start}_{suffix_end}"),
        "TOKEN": qname(project, dataset, f"token_transfers_{suffix_start}_{suffix_end}"),
        "TRACE": qname(project, dataset, f"internal_traces_{suffix_start}_{suffix_end}"),
    }
    template = TEMPLATE.read_text(encoding="utf-8")
    sql = template
    for key, value in names.items():
        sql = sql.replace("{{" + key + "}}", value)
    if "{{" in sql or "}}" in sql:
        raise BQError("unresolved placeholder remains in view SQL template")
    return names["VIEW"].split(".")[-1], sql


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
    view = meta.get("view", {})
    return {
        "id": meta.get("id"),
        "type": meta.get("type"),
        "description": meta.get("description"),
        "view_query_present": bool(view.get("query")),
        "schema_fields": [
            f.get("name") for f in meta.get("schema", {}).get("fields", [])
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--dataset-id", default="exgraph")
    ap.add_argument("--start", default="2022-03-01")
    ap.add_argument("--end", default="2022-09-01")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--dry-run-only", action="store_true")
    ap.add_argument("--gcloud-bin", default=os.environ.get("GCLOUD_BIN", "gcloud"))
    args = ap.parse_args()

    view_table, sql = view_sql(args.project_id, args.dataset_id, args.start, args.end)
    client = BigQueryClient(args.project_id, args.gcloud_bin)
    dry = client.query(sql, dry_run=True)
    dry_s = job_summary(dry)
    print(json.dumps({"view": view_table, "dry_run": dry_s}, indent=2))

    actual_s = None
    meta_s = None
    if not args.dry_run_only:
        actual = client.query(sql, dry_run=False)
        actual_s = job_summary(actual)
        print(json.dumps({"view": view_table, "actual": actual_s}, indent=2))
        meta = client.request(
            "GET",
            f"/bigquery/v2/projects/{args.project_id}/datasets/"
            f"{args.dataset_id}/tables/{view_table}",
        ).json()
        meta_s = table_summary(meta)
        if meta_s["type"] != "VIEW":
            raise BQError(f"Expected VIEW, got {meta_s['type']!r}")
        print(json.dumps({"view": view_table, "metadata": meta_s}, indent=2))

    manifest = {
        "run_date": time.strftime("%Y-%m-%d"),
        "project_id": args.project_id,
        "dataset_id": args.dataset_id,
        "view": qname(args.project_id, args.dataset_id, view_table),
        "location": LOCATION,
        "address_filter_semantics": (
            "Each source row has at least one endpoint matched to the EX-Graph "
            "mapped addresses; the other endpoint is retained."
        ),
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
