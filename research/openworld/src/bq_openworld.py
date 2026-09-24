#!/usr/bin/env python3
"""Small BigQuery helper for bounded open-world audits.

All source-side filtering/joining stays in BigQuery. This module only downloads
compact aggregate/result rows and never streams the temporal source tables.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from run_google_coverage_validation import (  # type: ignore  # noqa: E402
    BigQueryClient,
    LOCATION,
)


def load_csv(client: BigQueryClient, csv_path: Path, dataset: str, table: str,
             fields: Iterable[dict[str, str]], description: str) -> dict[str, Any]:
    metadata = {
        "jobReference": {
            "projectId": client.project_id,
            "jobId": f"openworld_load_{uuid.uuid4().hex[:16]}",
            "location": LOCATION,
        },
        "configuration": {
            "load": {
                "destinationTable": {
                    "projectId": client.project_id,
                    "datasetId": dataset,
                    "tableId": table,
                },
                "sourceFormat": "CSV",
                "skipLeadingRows": 1,
                "fieldDelimiter": ",",
                "encoding": "UTF-8",
                "schema": {"fields": list(fields)},
                "writeDisposition": "WRITE_TRUNCATE",
                "createDisposition": "CREATE_IF_NEEDED",
                "maxBadRecords": 0,
                "allowJaggedRows": False,
                "ignoreUnknownValues": False,
            }
        },
    }
    boundary = f"===============bq{uuid.uuid4().hex}=="
    csv_bytes = csv_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(metadata, separators=(",", ":"))
        + f"\r\n--{boundary}\r\n"
        "Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + csv_bytes + f"\r\n--{boundary}--\r\n".encode("ascii")
    response = client.request(
        "POST",
        f"/upload/bigquery/v2/projects/{client.project_id}/jobs?uploadType=multipart",
        data=body,
        headers={
            "Content-Type": f"multipart/related; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        timeout=180,
    )
    ref = response.json().get("jobReference", {})
    result = client.wait_job(ref.get("jobId"), ref.get("location", LOCATION))
    stats = result.get("statistics", {}).get("load", {})
    return {
        "table": f"{client.project_id}.{dataset}.{table}",
        "input_bytes": csv_path.stat().st_size,
        "output_rows": stats.get("outputRows"),
        "output_bytes": stats.get("outputBytes"),
        "description": description,
        "job_id": ref.get("jobId"),
    }


def run_query(client: BigQueryClient, sql: str, *, max_bytes: int,
              dry_run: bool = False) -> dict[str, Any]:
    return client.query(sql, dry_run=dry_run, max_bytes=max_bytes)


def job_summary(result: dict[str, Any]) -> dict[str, Any]:
    stats = result.get("_job_metadata", {}).get("statistics", {}).get("query", {})
    return {
        "job_id": result.get("jobReference", {}).get("jobId"),
        "bytes_processed": int(stats.get("totalBytesProcessed", result.get("totalBytesProcessed", 0)) or 0),
        "bytes_billed": int(stats.get("totalBytesBilled", result.get("totalBytesBilled", 0)) or 0),
        "cache_hit": stats.get("cacheHit", result.get("cacheHit")),
        "total_rows": result.get("totalRows"),
    }
