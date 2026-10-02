#!/usr/bin/env python3
"""Upload the small per-address structural-feature CSV to BigQuery.

Small upload: 27,613 rows gzip-compressed before the multipart POST. The
feature table is keyed by (ethereum_address, exgraph_node_id) and is the
bridge for later static-graph ablations (README ablation D / centrality
routing). Auth is Application Default Credentials via gcloud, mirroring the
other scripts in this repository.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_google_coverage_validation import BigQueryClient, LOCATION, BQError  # noqa: E402

TABLE_ID = "exgraph_structural_features_v1"
FIELDS = [
    {"name": "ethereum_address", "type": "STRING", "mode": "REQUIRED"},
    {"name": "exgraph_node_id", "type": "INTEGER", "mode": "REQUIRED"},
    {"name": "graph_node_present", "type": "BOOLEAN", "mode": "REQUIRED"},
    {"name": "in_degree", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "out_degree", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "w_in_degree", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "w_out_degree", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "degree", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "w_degree", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "pagerank", "type": "FLOAT", "mode": "NULLABLE"},
]


def table_summary(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": meta.get("id"),
        "type": meta.get("type"),
        "num_rows": int(meta["numRows"]) if meta.get("numRows") else None,
        "num_bytes": int(meta["numBytes"]) if meta.get("numBytes") else None,
        "schema_fields": [
            {"name": f.get("name"), "type": f.get("type"), "mode": f.get("mode")}
            for f in meta.get("schema", {}).get("fields", [])
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--dataset-id", default="exgraph")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--gcloud-bin", default="gcloud")
    ap.add_argument("--no-gzip", action="store_true")
    args = ap.parse_args()

    client = BigQueryClient(args.project_id, args.gcloud_bin)

    raw = args.csv.read_bytes()
    # Normalize Python booleans to the canonical lowercase form BQ CSV accepts.
    csv_text = raw.decode("utf-8").replace(",True", ",true").replace(",False", ",false")
    csv_bytes = csv_text.encode("utf-8")
    if not args.no_gzip:
        csv_bytes = gzip.compress(csv_bytes, compresslevel=9)
        compression = "GZIP"
    else:
        compression = "NONE"

    metadata = {
        "jobReference": {
            "projectId": args.project_id,
            "jobId": f"exgraph_structural_load_{uuid.uuid4().hex[:16]}",
            "location": LOCATION,
        },
        "configuration": {
            "load": {
                "destinationTable": {
                    "projectId": args.project_id,
                    "datasetId": args.dataset_id,
                    "tableId": TABLE_ID,
                },
                "sourceFormat": "CSV",
                "compression": compression,
                "skipLeadingRows": 1,
                "fieldDelimiter": ",",
                "encoding": "UTF-8",
                "schema": {"fields": FIELDS},
                "writeDisposition": "WRITE_TRUNCATE",
                "createDisposition": "CREATE_IF_NEEDED",
                "maxBadRecords": 0,
                "allowJaggedRows": False,
                "ignoreUnknownValues": False,
            }
        },
    }

    boundary = f"===============bq{uuid.uuid4().hex}=="
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(metadata, separators=(",", ":"))
        + f"\r\n--{boundary}\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + csv_bytes + f"\r\n--{boundary}--\r\n".encode("ascii")

    started = time.time()
    resp = client.request(
        "POST",
        f"/upload/bigquery/v2/projects/{args.project_id}/jobs?uploadType=multipart",
        data=body,
        headers={
            "Content-Type": f"multipart/related; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        timeout=180,
    )
    job = resp.json()
    job_ref = job.get("jobReference", {})
    finished = client.wait_job(job_ref.get("jobId"), job_ref.get("location", LOCATION))

    meta = client.request(
        "GET",
        f"/bigquery/v2/projects/{args.project_id}/datasets/"
        f"{args.dataset_id}/tables/{TABLE_ID}",
    ).json()

    summary = {
        "run_seconds": round(time.time() - started, 2),
        "source_csv_bytes": len(raw),
        "uploaded_body_bytes": len(body),
        "compression": compression,
        "job_reference": job_ref,
        "status": finished.get("status", {}).get("state"),
        "errors": finished.get("status", {}).get("errors"),
        "table": table_summary(meta),
    }
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
