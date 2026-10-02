#!/usr/bin/env python3
"""Materialize the official EX-Graph match dimension and directional sequences.

The SQL is intentionally kept in src/sql/create_exgraph_sequence_tables_ictdata.sql
so the exact BigQuery statements can be reviewed independently. Queries run
inside BigQuery; source event rows are not downloaded to the jump host.
"""

from __future__ import annotations

import argparse
import json
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

MAPPING_MARKER = (
    "CREATE OR REPLACE TABLE `ictdata-507912.exgraph.exgraph_x_matches_v1`"
)
SEQUENCE_MARKER = (
    "CREATE OR REPLACE TABLE `ictdata-507912.exgraph."
    "target_event_sequences_20220301_20220901`"
)


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


def get_table(client: BigQueryClient, project: str, dataset: str, table: str) -> dict[str, Any]:
    return client.request(
        "GET",
        f"/bigquery/v2/projects/{project}/datasets/{dataset}/tables/{table}",
    ).json()


def table_summary(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta.get("id"),
        "type": meta.get("type"),
        "num_rows": int(meta["numRows"]) if meta.get("numRows") else None,
        "num_bytes": int(meta["numBytes"]) if meta.get("numBytes") else None,
        "description": meta.get("description"),
        "time_partitioning": meta.get("timePartitioning"),
        "clustering": meta.get("clustering"),
        "schema_fields": [
            {"name": f.get("name"), "type": f.get("type"), "mode": f.get("mode")}
            for f in meta.get("schema", {}).get("fields", [])
        ],
    }


def load_statements(sql_path: Path) -> tuple[str, str]:
    text = sql_path.read_text(encoding="utf-8")
    if MAPPING_MARKER not in text or SEQUENCE_MARKER not in text:
        raise BQError(f"Expected table markers were not found in {sql_path}")
    mapping_start = text.index(MAPPING_MARKER)
    sequence_start = text.index(SEQUENCE_MARKER)
    return text[mapping_start:sequence_start], text[sequence_start:]


def run_one(
    client: BigQueryClient,
    sql: str,
    *,
    max_bytes: int,
    dry_run_only: bool,
) -> dict[str, Any]:
    dry = client.query(sql, dry_run=True, max_bytes=max_bytes)
    result: dict[str, Any] = {"dry_run": job_summary(dry)}
    if not dry_run_only:
        actual = client.query(sql, dry_run=False, max_bytes=max_bytes)
        result["actual"] = job_summary(actual)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default="ictdata-507912")
    parser.add_argument("--dataset-id", default="exgraph")
    parser.add_argument(
        "--sql",
        type=Path,
        default=Path("src/sql/create_exgraph_sequence_tables_ictdata.sql"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/google_sequence_tables_2022-03_2022-09.json"),
    )
    parser.add_argument("--max-bytes-billed", type=int, default=10_000_000_000)
    parser.add_argument("--dry-run-only", action="store_true")
    parser.add_argument(
        "--gcloud-bin",
        default="/storage/gaoym/tools/google-cloud-sdk/bin/gcloud",
    )
    args = parser.parse_args()

    if args.project_id != "ictdata-507912" or args.dataset_id != "exgraph":
        raise BQError(
            "The checked-in SQL is pinned to project ictdata-507912 and dataset exgraph; "
            "edit the SQL explicitly before using another namespace."
        )

    mapping_sql, sequence_sql = load_statements(args.sql)
    client = BigQueryClient(args.project_id, args.gcloud_bin)
    mapping = run_one(
        client,
        mapping_sql,
        max_bytes=args.max_bytes_billed,
        dry_run_only=args.dry_run_only,
    )
    sequence = run_one(
        client,
        sequence_sql,
        max_bytes=args.max_bytes_billed,
        dry_run_only=args.dry_run_only,
    )

    manifest: dict[str, Any] = {
        "run_date": time.strftime("%Y-%m-%d"),
        "project_id": args.project_id,
        "dataset_id": args.dataset_id,
        "location": LOCATION,
        "sql": str(args.sql),
        "max_bytes_billed": args.max_bytes_billed,
        "dry_run_only": args.dry_run_only,
        "mapping": mapping,
        "sequence": sequence,
    }
    if not args.dry_run_only:
        manifest["tables"] = {
            "exgraph_x_matches_v1": table_summary(
                get_table(client, args.project_id, args.dataset_id, "exgraph_x_matches_v1")
            ),
            "target_event_sequences_20220301_20220901": table_summary(
                get_table(
                    client,
                    args.project_id,
                    args.dataset_id,
                    "target_event_sequences_20220301_20220901",
                )
            ),
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
