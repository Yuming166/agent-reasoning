#!/usr/bin/env python3
"""Fetch event-level 2026 Ethereum seed neighborhood with bounded BigQuery jobs.

Requires the project's existing Google ADC setup and HTTPS_PROXY. SQL jobs are
persisted before result download so a failed download can resume without a new
billable scan. This is limited to the twelve account-confirmed seed wallets.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode


PROJECT = "ictdata-507912"
GCLOUD = "/storage/gaoym/tools/google-cloud-sdk/bin/gcloud"
END = "2026-09-24 17:24:10 UTC"
CAPS = {"native": 120_000_000_000, "token": 250_000_000_000}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def iso_timestamp(value: str) -> str:
    """BigQuery REST returns TIMESTAMP query cells as epoch seconds."""
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except ValueError:
        return str(value)


def query_sql(kind: str, addresses: set[str]) -> str:
    values = ",".join("'" + a + "'" for a in sorted(addresses))
    where = ("block_timestamp >= TIMESTAMP('2026-01-01 00:00:00 UTC') "
             f"AND block_timestamp < TIMESTAMP('{END}') "
             f"AND (LOWER(from_address) IN ({values}) OR LOWER(to_address) IN ({values}))")
    source = "bigquery-public-data.goog_blockchain_ethereum_mainnet_us"
    if kind == "native":
        return ("SELECT block_timestamp,transaction_hash,"
                "from_address,to_address,value FROM `" + source + ".transactions` WHERE " + where)
    return ("SELECT block_timestamp,transaction_hash,event_index,batch_index,"
            "from_address,to_address,address,event_type,quantity,token_id "
            "FROM `" + source + ".token_transfers` WHERE " + where)


def fetch_rows(client, job_id: str):
    token = None
    while True:
        params = {"location": "US", "maxResults": "10000"}
        if token:
            params["pageToken"] = token
        path = (f"/bigquery/v2/projects/{PROJECT}/queries/{job_id}?" + urlencode(params))
        page = client.request("GET", path, timeout=120).json()
        if not page.get("jobComplete"):
            raise RuntimeError(f"Saved BigQuery job not complete: {job_id}")
        fields = [f["name"] for f in page.get("schema", {}).get("fields", [])]
        for row in page.get("rows", []):
            yield dict(zip(fields, (cell.get("v") for cell in row["f"])))
        token = page.get("pageToken")
        if not token:
            break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with (out / "crosswalk_confirmed_unique.csv").open(encoding="utf-8", newline="") as handle:
        addresses = {row["address"].lower() for row in csv.DictReader(handle)}
    if len(addresses) != 12:
        raise ValueError(f"Expected 12 confirmed seed addresses, got {len(addresses)}")
    sys.path.insert(0, str(root / "src"))
    from run_google_coverage_validation import BigQueryClient
    client = BigQueryClient(PROJECT, GCLOUD)
    all_edges = []
    jobs = {}
    for kind in ("native", "token"):
        sql = query_sql(kind, addresses)
        (out / f"chain_{kind}_query.sql").write_text(sql + "\n", encoding="utf-8")
        dry = client.query(sql, dry_run=True)
        estimated = int(dry.get("totalBytesProcessed", "0"))
        if estimated > CAPS[kind]:
            raise RuntimeError(f"{kind} dry run {estimated} exceeds cap {CAPS[kind]}")
        print(f"{kind}: dry run {estimated} bytes, cap {CAPS[kind]}", flush=True)
        if args.dry_run_only:
            continue
        job_path = out / f"chain_{kind}_query_job.json"
        if job_path.is_file():
            saved = json.loads(job_path.read_text(encoding="utf-8"))
            if saved["sql"] != sql:
                raise RuntimeError(f"SQL changed since saved job {job_path}")
            job_id = saved["job_id"]
        else:
            result = client.query(sql, dry_run=False, max_bytes=CAPS[kind])
            job_id = result.get("jobReference", {}).get("jobId")
            if not job_id:
                raise RuntimeError(f"No job ID for {kind}")
            metadata = result.get("_job_metadata", {})
            saved = {
                "job_id": job_id,
                "sql": sql,
                "dry_run_bytes": estimated,
                "maximum_bytes_billed": CAPS[kind],
                "total_bytes_billed": metadata.get("statistics", {}).get("query", {}).get("totalBytesBilled"),
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            job_path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        jobs[kind] = saved
        count = 0
        for row in fetch_rows(client, job_id):
            if kind == "token" and str(row.get("removed", "")).lower() == "true":
                continue
            source = (row.get("from_address") or "").lower()
            target = (row.get("to_address") or "").lower()
            if not source or not target or not (source in addresses or target in addresses):
                raise RuntimeError(f"Out-of-scope {kind} event in query result")
            if kind == "native":
                event_id = f"native:{row['transaction_hash']}:{row.get('transaction_index','')}"
            else:
                event_id = (f"token:{row['transaction_hash']}:"
                            f"{row.get('event_index','')}:{row.get('batch_index','')}")
            all_edges.append({
                "event_id": event_id,
                "event_type": kind,
                "source_address": source,
                "target_address": target,
                "block_timestamp_utc": iso_timestamp(row["block_timestamp"]),
                "transaction_hash": row["transaction_hash"],
                "transaction_index": row.get("transaction_index") or "",
                "event_index": row.get("event_index") or "",
                "batch_index": row.get("batch_index") or "",
                "token_contract_address": (row.get("address") or "").lower(),
                "token_event_type": row.get("event_type") or "",
                "amount_raw_source_units": row.get("value") if kind == "native" else row.get("quantity") or "",
                "token_id": row.get("token_id") or "",
            })
            count += 1
        print(f"{kind}: {count} event rows", flush=True)

    if args.dry_run_only:
        return
    keys = ["event_id", "event_type", "source_address", "target_address", "block_timestamp_utc",
            "transaction_hash", "transaction_index", "event_index", "batch_index",
            "token_contract_address", "token_event_type", "amount_raw_source_units", "token_id"]
    duplicates = len(all_edges) - len({e["event_id"] for e in all_edges})
    if duplicates:
        raise RuntimeError(f"Nonunique chain event IDs: {duplicates}")
    all_edges.sort(key=lambda e: (e["block_timestamp_utc"], e["event_id"]))
    write_csv(out / "eth_transfer_edges_2026_seed_neighborhood.csv", all_edges, keys)
    node_ids = addresses | {e["source_address"] for e in all_edges} | {e["target_address"] for e in all_edges}
    in_count = Counter(e["target_address"] for e in all_edges)
    out_count = Counter(e["source_address"] for e in all_edges)
    nodes = [{"address": address, "role": "account_confirmed_seed" if address in addresses else "event_counterparty",
              "incoming_events": in_count[address], "outgoing_events": out_count[address]}
             for address in sorted(node_ids)]
    write_csv(out / "eth_address_nodes_2026_seed_neighborhood.csv", nodes,
              ["address", "role", "incoming_events", "outgoing_events"])
    report_path = out / "seed_quality_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["chain_graph"] = {
        "source": "Google Blockchain Analytics BigQuery Ethereum mainnet transactions and token_transfers views",
        "window_start_inclusive_utc": "2026-01-01 00:00:00 UTC",
        "window_end_exclusive_utc": END,
        "seed_address_count": len(addresses),
        "nodes": len(nodes),
        "event_edges": len(all_edges),
        "event_edges_by_type": dict(Counter(e["event_type"] for e in all_edges)),
        "query_jobs": jobs,
        "edge_scope": "transfers with at least one endpoint in the confirmed seed addresses",
        "note": "Counterparty addresses have no X identity link unless separately confirmed; internal traces excluded.",
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["chain_graph"], indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
