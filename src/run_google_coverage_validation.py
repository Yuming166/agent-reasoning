#!/usr/bin/env python3
"""Run a bounded EX-Graph address-coverage check against Google BigQuery.

This script intentionally does not download the public Ethereum tables. It:
1. creates/refreshes a small BigQuery table containing the EX-Graph target
   addresses;
2. dry-runs a count-only query over the public Ethereum transactions and
   token_transfers views; and
3. optionally executes that same query when the dry-run estimate is below the
   configured byte guard.

Authentication is obtained from Google Application Default Credentials through
`gcloud auth application-default print-access-token`. HTTP(S)_PROXY may be set
in the environment for a jump host.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import requests

API = "https://bigquery.googleapis.com"
PUBLIC_PROJECT = "bigquery-public-data"
PUBLIC_DATASET = "goog_blockchain_ethereum_mainnet_us"
LOCATION = "US"
DEFAULT_GCLOUD = "gcloud"


class BQError(RuntimeError):
    pass


def get_token(gcloud_bin: str) -> str:
    proc = subprocess.run(
        [gcloud_bin, "auth", "application-default", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    token = proc.stdout.strip()
    if not token:
        raise BQError("gcloud returned an empty Application Default access token")
    return token


class BigQueryClient:
    def __init__(self, project_id: str, gcloud_bin: str):
        self.project_id = project_id
        self.gcloud_bin = gcloud_bin
        self.session = requests.Session()
        self.token = get_token(gcloud_bin)

    def request(self, method: str, path: str, *, json_body: Any = None,
                data: bytes | None = None, headers: dict[str, str] | None = None,
                timeout: int = 60) -> requests.Response:
        hdr = {"Authorization": f"Bearer {self.token}"}
        if headers:
            hdr.update(headers)
        url = f"{API}{path}"
        resp = self.session.request(
            method, url, headers=hdr, json=json_body, data=data, timeout=timeout
        )
        if resp.status_code == 401:
            self.token = get_token(self.gcloud_bin)
            hdr["Authorization"] = f"Bearer {self.token}"
            resp = self.session.request(
                method, url, headers=hdr, json=json_body, data=data, timeout=timeout
            )
        if not resp.ok:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text[:2000]
            raise BQError(f"{method} {path} -> HTTP {resp.status_code}: {detail}")
        return resp

    def create_dataset_if_missing(self, dataset_id: str) -> dict[str, Any]:
        path = f"/bigquery/v2/projects/{self.project_id}/datasets/{dataset_id}"
        # A missing dataset is expected on the first run, so inspect this GET
        # directly instead of routing it through request(), which raises on all
        # non-2xx responses.
        resp = self.session.get(
            f"{API}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code != 404:
            raise BQError(f"GET {path} -> HTTP {resp.status_code}: {resp.text[:2000]}")
        body = {
            "datasetReference": {
                "projectId": self.project_id,
                "datasetId": dataset_id,
            },
            "friendlyName": "EX-Graph microtransaction analysis",
            "description": (
                "Small staging tables and validation artifacts for joining EX-Graph "
                "mapped Ethereum addresses to temporal Ethereum events."
            ),
            "location": LOCATION,
        }
        try:
            return self.request(
                "POST",
                f"/bigquery/v2/projects/{self.project_id}/datasets",
                json_body=body,
            ).json()
        except BQError as exc:
            if "HTTP 409" in str(exc):
                return self.request("GET", path).json()
            raise

    def table_exists(self, dataset_id: str, table_id: str) -> bool:
        path = (
            f"/bigquery/v2/projects/{self.project_id}/datasets/"
            f"{dataset_id}/tables/{table_id}"
        )
        resp = self.session.get(
            f"{API}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=60,
        )
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        raise BQError(f"GET {path} -> HTTP {resp.status_code}: {resp.text[:2000]}")

    def load_csv(self, csv_path: Path, dataset_id: str, table_id: str) -> dict[str, Any]:
        metadata = {
            "jobReference": {
                "projectId": self.project_id,
                "jobId": f"exgraph_target_load_{uuid.uuid4().hex[:16]}",
                "location": LOCATION,
            },
            "configuration": {
                "load": {
                    "destinationTable": {
                        "projectId": self.project_id,
                        "datasetId": dataset_id,
                        "tableId": table_id,
                    },
                    "sourceFormat": "CSV",
                    "skipLeadingRows": 1,
                    "fieldDelimiter": ",",
                    "encoding": "UTF-8",
                    "schema": {
                        "fields": [
                            {"name": "ethereum_address", "type": "STRING", "mode": "REQUIRED"},
                            {"name": "exgraph_node_id", "type": "INTEGER", "mode": "REQUIRED"},
                        ]
                    },
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
        resp = self.request(
            "POST",
            f"/upload/bigquery/v2/projects/{self.project_id}/jobs?uploadType=multipart",
            data=body,
            headers={
                "Content-Type": f"multipart/related; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
            timeout=120,
        )
        job = resp.json()
        job_ref = job.get("jobReference", {})
        return self.wait_job(job_ref.get("jobId"), job_ref.get("location", LOCATION))

    def wait_job(self, job_id: str | None, location: str = LOCATION) -> dict[str, Any]:
        if not job_id:
            raise BQError("BigQuery response did not include a job ID")
        path = f"/bigquery/v2/projects/{self.project_id}/jobs/{job_id}"
        deadline = time.time() + 600
        while time.time() < deadline:
            resp = self.request("GET", f"{path}?location={location}").json()
            status = resp.get("status", {})
            if status.get("errorResult"):
                raise BQError(f"BigQuery job failed: {status}")
            if status.get("state") == "DONE":
                return resp
            time.sleep(2)
        raise BQError(f"Timed out waiting for BigQuery job {job_id}")

    def query(self, sql: str, *, dry_run: bool, max_bytes: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "query": sql,
            "useLegacySql": False,
            "dryRun": dry_run,
            "location": LOCATION,
        }
        if max_bytes is not None:
            body["maximumBytesBilled"] = str(max_bytes)
        resp = self.request(
            "POST",
            f"/bigquery/v2/projects/{self.project_id}/queries",
            json_body=body,
            timeout=120,
        )
        result = resp.json()
        if result.get("errors"):
            raise BQError(f"BigQuery query failed: {result['errors']}")

        def attach_job_metadata(value: dict[str, Any]) -> dict[str, Any]:
            # DDL/CTAS responses can omit totalBytesBilled at the top level;
            # the authoritative query statistics are available from jobs.get.
            if not dry_run:
                ref = value.get("jobReference", {})
                job_id = ref.get("jobId")
                if job_id:
                    value["_job_metadata"] = self.request(
                        "GET",
                        f"/bigquery/v2/projects/{self.project_id}/jobs/{job_id}"
                        f"?location={ref.get('location', LOCATION)}",
                    ).json()
            return value

        if dry_run or result.get("jobComplete", False):
            return attach_job_metadata(result)
        job_ref = result.get("jobReference", {})
        job_id = job_ref.get("jobId")
        if not job_id:
            raise BQError("BigQuery query did not return a complete result or job ID")
        deadline = time.time() + 1800
        while time.time() < deadline:
            qpath = (
                f"/bigquery/v2/projects/{self.project_id}/queries/{job_id}"
                f"?location={job_ref.get('location', LOCATION)}"
            )
            result = self.request("GET", qpath).json()
            if result.get("errors"):
                raise BQError(f"BigQuery query failed: {result['errors']}")
            if result.get("jobComplete", False):
                return attach_job_metadata(result)
            time.sleep(5)
        raise BQError(f"Timed out waiting for query job {job_id}")


def make_sql(project_id: str, dataset_id: str, table_id: str,
             start_ts: str, end_ts: str) -> str:
    target = f"`{project_id}.{dataset_id}.{table_id}`"
    tx = f"`{PUBLIC_PROJECT}.{PUBLIC_DATASET}.transactions`"
    token = f"`{PUBLIC_PROJECT}.{PUBLIC_DATASET}.token_transfers`"
    return f"""-- Count-only coverage validation; no source rows are downloaded.
DECLARE start_ts TIMESTAMP DEFAULT TIMESTAMP('{start_ts} 00:00:00+00');
DECLARE end_ts TIMESTAMP DEFAULT TIMESTAMP('{end_ts} 00:00:00+00');

WITH target AS (
  SELECT DISTINCT LOWER(ethereum_address) AS address
  FROM {target}
),
external_observed AS (
  SELECT DISTINCT LOWER(t.from_address) AS address
  FROM {tx} AS t
  JOIN target AS a ON LOWER(t.from_address) = a.address
  WHERE t.block_timestamp >= start_ts AND t.block_timestamp < end_ts
  UNION DISTINCT
  SELECT DISTINCT LOWER(t.to_address) AS address
  FROM {tx} AS t
  JOIN target AS a ON LOWER(t.to_address) = a.address
  WHERE t.block_timestamp >= start_ts AND t.block_timestamp < end_ts
),
token_observed AS (
  SELECT DISTINCT LOWER(tt.from_address) AS address
  FROM {token} AS tt
  JOIN target AS a ON LOWER(tt.from_address) = a.address
  WHERE tt.block_timestamp >= start_ts AND tt.block_timestamp < end_ts
  UNION DISTINCT
  SELECT DISTINCT LOWER(tt.to_address) AS address
  FROM {token} AS tt
  JOIN target AS a ON LOWER(tt.to_address) = a.address
  WHERE tt.block_timestamp >= start_ts AND tt.block_timestamp < end_ts
),
observed_any AS (
  SELECT address FROM external_observed
  UNION DISTINCT
  SELECT address FROM token_observed
)
SELECT
  (SELECT COUNT(*) FROM target) AS target_addresses,
  (SELECT COUNT(*) FROM external_observed) AS external_tx_observed,
  (SELECT COUNT(*) FROM token_observed) AS token_transfer_observed,
  (SELECT COUNT(*) FROM observed_any) AS observed_in_any_source,
  SAFE_DIVIDE((SELECT COUNT(*) FROM observed_any), (SELECT COUNT(*) FROM target)) AS coverage_ratio;
"""


def result_rows(query_result: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [x["name"] for x in query_result.get("schema", {}).get("fields", [])]
    rows = []
    for row in query_result.get("rows", []):
        vals = []
        for cell in row.get("f", []):
            vals.append(cell.get("v"))
        rows.append(dict(zip(fields, vals)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--target-csv", type=Path, required=True)
    parser.add_argument("--dataset-id", default="exgraph")
    parser.add_argument("--table-id", default="target_addresses")
    parser.add_argument("--start", default="2022-03-01")
    parser.add_argument("--end", default="2022-09-01")
    parser.add_argument("--max-bytes-billed", type=int, default=100_000_000_000)
    parser.add_argument("--run", action="store_true", help="execute after dry-run")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gcloud-bin", default=os.environ.get("GCLOUD_BIN", DEFAULT_GCLOUD))
    args = parser.parse_args()

    if not args.target_csv.is_file():
        raise SystemExit(f"target CSV not found: {args.target_csv}")
    client = BigQueryClient(args.project_id, args.gcloud_bin)
    dataset = client.create_dataset_if_missing(args.dataset_id)
    loaded = client.load_csv(args.target_csv, args.dataset_id, args.table_id)
    sql = make_sql(args.project_id, args.dataset_id, args.table_id, args.start, args.end)
    dry = client.query(sql, dry_run=True, max_bytes=args.max_bytes_billed)
    dry_info = {
        "total_bytes_processed": int(dry.get("totalBytesProcessed", 0)),
        "total_bytes_billed": int(dry.get("totalBytesBilled", 0)),
        "job_reference": dry.get("jobReference"),
        "location": dry.get("location", LOCATION),
    }
    output: dict[str, Any] = {
        "project_id": args.project_id,
        "dataset": f"{args.project_id}:{args.dataset_id}",
        "target_table": f"{args.project_id}.{args.dataset_id}.{args.table_id}",
        "public_source": f"{PUBLIC_PROJECT}.{PUBLIC_DATASET}",
        "window_utc": {"start_inclusive": args.start, "end_exclusive": args.end},
        "target_csv": str(args.target_csv),
        "target_csv_bytes": args.target_csv.stat().st_size,
        "dataset_metadata": {
            "dataset_id": dataset.get("id"),
            "location": dataset.get("location"),
        },
        "load_job": {
            "job_id": loaded.get("jobReference", {}).get("jobId"),
            "output_rows": loaded.get("statistics", {}).get("load", {}).get("outputRows"),
            "input_file_bytes": loaded.get("statistics", {}).get("load", {}).get("inputFileBytes"),
        },
        "dry_run": dry_info,
        "query_sql": sql,
    }
    print(json.dumps({"dry_run": dry_info, "load_job": output["load_job"]}, indent=2))

    if args.run:
        if dry_info["total_bytes_processed"] > args.max_bytes_billed:
            raise SystemExit(
                "Refusing to execute: dry-run estimate exceeds --max-bytes-billed "
                f"({dry_info['total_bytes_processed']} > {args.max_bytes_billed})."
            )
        actual = client.query(sql, dry_run=False, max_bytes=args.max_bytes_billed)
        rows = result_rows(actual)
        output["actual_query"] = {
            "job_reference": actual.get("jobReference"),
            "total_bytes_processed": int(actual.get("totalBytesProcessed", 0)),
            "total_bytes_billed": int(actual.get("totalBytesBilled", 0)),
            "cache_hit": actual.get("cacheHit"),
            "rows": rows,
        }
        print(json.dumps(output["actual_query"], indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(f"saved: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BQError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
