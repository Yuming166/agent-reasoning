#!/usr/bin/env python3
"""Fetch only compact OW-010A aggregate inputs for OW-010B.

This script queries only compact aggregates from the event-level substrate (never raw event rows) and never queries any
external-label table.  It exports the already-materialized discovery feature
and evaluation-only outcome rows (82,839 rows each) needed for the frozen
nested predictive test.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from run_google_coverage_validation import BigQueryClient  # type: ignore  # noqa: E402

PROJECT = "ictdata-507912"
DATASET = "exgraph"
GCLOUD = "gcloud"
OUT = ROOT / "research" / "openworld" / "ow010b" / "data"
LOCATION = "US"
MAX_BYTES = 500_000_000

FEATURE_COLUMNS = [
    "anchor_wallet", "anchor_exgraph_node_id", "cutoff_time", "history_start", "score_start", "history_end",
    "observed_before_cutoff", "first_event_timestamp", "history_event_count_30d", "history_unique_event_count_30d",
    "event_count_1h", "event_count_6h", "event_count_1d", "event_count_7d", "event_count_30d",
    "unique_event_count_1d", "unique_event_count_7d", "active_days_30d", "active_hours_30d",
    "native_event_count_7d", "native_event_count_30d", "token_event_count_30d", "internal_event_count_30d",
    "incoming_event_count_30d", "outgoing_event_count_30d", "self_event_count_30d",
    "incoming_event_count_7d", "outgoing_event_count_7d", "self_event_count_7d",
    "native_inflow_30d", "native_outflow_30d", "native_netflow_30d", "native_value_mean_30d", "native_value_max_30d",
    "token_contract_diversity_30d", "token_item_diversity_30d", "native_event_ratio_30d", "token_event_ratio_30d",
    "internal_event_ratio_30d", "active_days_7d", "inter_event_gap_mean_sec_30d", "inter_event_gap_std_sec_30d",
    "inter_event_gap_median_sec_30d", "inter_event_gap_min_sec_30d", "inter_event_gap_max_sec_30d",
    "mean_events_per_active_hour_7d", "std_events_per_active_hour_7d", "unique_counterparties_30d",
    "mapped_counterparties_30d", "unmapped_counterparties_30d", "score_unique_counterparties_7d",
    "prior_unique_counterparties_23d", "new_counterparties_7d", "repeat_counterparties_7d",
    "reciprocal_counterparties_prior_23d", "reciprocal_counterparties_30d", "counterparty_entropy_30d",
    "rapid_forwarding_adjacent_count_30d", "max_events_per_active_hour_7d", "max_fan_in_counterparties_per_hour_7d",
    "max_fan_out_counterparties_per_hour_7d", "history_activity_status", "score_activity_status",
    "history_window_coverage_status", "data_role", "temporal_cycle_status", "split_merge_status",
    "native_amount_status", "token_quantity_status", "feature_version",
]
SCORE_COLUMNS = [
    "anchor_wallet", "anchor_exgraph_node_id", "cutoff_time",
    "score_external_native_7d", "score_token_7d", "score_internal_7d",
    "score_incoming_7d", "score_outgoing_7d", "score_self_7d", "score_event_count_7d"
]
OUTCOME_COLUMNS = [
    "anchor_wallet", "anchor_exgraph_node_id", "cutoff_time", "future7_event_count", "future30_event_count",
    "future7_active_days", "future30_active_days", "future7_unique_counterparties", "future30_unique_counterparties",
    "future7_native_events", "future7_token_events", "future7_internal_events", "future7_incoming_events",
    "future7_outgoing_events", "future7_self_events", "future7_native_inflow", "future7_native_outflow",
    "future7_new_counterparties", "future30_new_counterparties", "future30_activity_status",
    "future7_window_coverage_status", "future30_window_coverage_status", "evaluation_only", "data_role", "outcome_version",
]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def rows_from_result(result: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    fields = [f["name"] for f in result.get("schema", {}).get("fields", [])]
    rows = []
    for row in result.get("rows", []) or []:
        values = [cell.get("v") for cell in row.get("f", [])]
        rows.append(dict(zip(fields, values)))
    return fields, rows


def fetch_all(client: BigQueryClient, sql: str, name: str, max_bytes: int = MAX_BYTES) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    dry = client.query(sql, dry_run=True, max_bytes=max_bytes)
    result = client.query(sql, dry_run=False, max_bytes=max_bytes)
    fields, rows = rows_from_result(result)
    ref = result.get("jobReference", {})
    job_id = ref.get("jobId")
    page_token = result.get("pageToken")
    pages = 1
    while page_token:
        path = f"/bigquery/v2/projects/{PROJECT}/queries/{quote(str(job_id), safe='')}?location={LOCATION}&pageToken={quote(str(page_token), safe='')}&maxResults=100000"
        page = client.request("GET", path, timeout=180).json()
        if page.get("errors"):
            raise RuntimeError(f"page fetch failed for {name}: {page['errors']}")
        page_fields, page_rows = rows_from_result(page)
        if page_fields and page_fields != fields:
            raise RuntimeError(f"schema changed between pages for {name}")
        rows.extend(page_rows)
        page_token = page.get("pageToken")
        pages += 1
    stats = result.get("_job_metadata", {}).get("statistics", {}).get("query", {})
    manifest = {
        "name": name,
        "sql_sha256": sha_text(sql),
        "job_id": job_id,
        "dry_bytes_processed": int(dry.get("totalBytesProcessed", 0) or 0),
        "bytes_processed": int(stats.get("totalBytesProcessed", result.get("totalBytesProcessed", 0)) or 0),
        "bytes_billed": int(stats.get("totalBytesBilled", result.get("totalBytesBilled", 0)) or 0),
        "cache_hit": stats.get("cacheHit", result.get("cacheHit")),
        "row_count": len(rows),
        "pages": pages,
        "source_is_aggregate_only": True,
        "raw_event_rows_exported": False,
        "external_label_source_accessed": False,
    }
    return fields, rows, manifest


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    client = BigQueryClient(PROJECT, GCLOUD)
    feature_sql = "SELECT " + ", ".join(f"`{c}`" for c in FEATURE_COLUMNS) + " FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`"
    outcome_sql = "SELECT " + ", ".join(f"`{c}`" for c in OUTCOME_COLUMNS) + " FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1`"
    f_fields, f_rows, f_manifest = fetch_all(client, feature_sql, "discovery_features")
    score_sql = (ROOT / "research" / "openworld" / "ow010b" / "sql" / "score7_asof_composition.sql").read_text(encoding="utf-8")

    o_fields, o_rows, o_manifest = fetch_all(client, outcome_sql, "future_outcomes_evaluation_only")
    s_fields, s_rows, s_manifest = fetch_all(client, score_sql, "score7_asof_composition", max_bytes=8_000_000_000)
    if f_fields != FEATURE_COLUMNS:
        raise RuntimeError(f"feature schema mismatch: {f_fields}")
    if o_fields != OUTCOME_COLUMNS:
        raise RuntimeError(f"outcome schema mismatch: {o_fields}")
    if s_fields != SCORE_COLUMNS:
        raise RuntimeError(f"score schema mismatch: {s_fields}")
    write_csv(OUT / "ow010b_discovery_features.csv", f_fields, f_rows)
    write_csv(OUT / "ow010b_future_outcomes_evaluation_only.csv", o_fields, o_rows)
    write_csv(OUT / "ow010b_score7_asof_composition.csv", s_fields, s_rows)
    manifest = {
        "experiment_id": "OW-010B",
        "retrieved_utc": "2026-09-18",
        "tables": {
            "discovery_features": "ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1",
            "future_outcomes": "ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1",
        },
        "feature_columns": FEATURE_COLUMNS,
        "outcome_columns": OUTCOME_COLUMNS,
        "score_columns": SCORE_COLUMNS,
        "queries": [f_manifest, o_manifest, s_manifest],
        "blind_boundary": {
            "external_label_source_accessed": False,
            "external_label_rows_exported": False,
            "old_ow009_local_artifact_used": False,
            "raw_event_rows_exported": False,
            "compact_score_aggregate_only": True,
        },
    }
    (OUT / "BQ_INPUT_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"feature_rows": len(f_rows), "outcome_rows": len(o_rows), "output": str(OUT), "manifest": str(OUT / "BQ_INPUT_MANIFEST.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
