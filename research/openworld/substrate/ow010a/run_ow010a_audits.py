#!/usr/bin/env python3
"""Export compact OW-010A substrate QA tables after BigQuery materialization.

This script never reads EX-Graph labels and never downloads event-level rows.
It only downloads aggregate rows from the event-level materialized tables.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from run_google_coverage_validation import BigQueryClient  # type: ignore  # noqa: E402

PROJECT = "ictdata-507912"
DATASET = "exgraph"
GCLOUD = "/storage/gaoym/tools/google-cloud-sdk/bin/gcloud"
OUT = ROOT / "research" / "openworld" / "substrate" / "ow010a"
RESULTS = OUT / "results"


def rows_from_result(result: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    fields = [x["name"] for x in result.get("schema", {}).get("fields", [])]
    rows = [
        dict(zip(fields, [cell.get("v") for cell in row.get("f", [])]))
        for row in result.get("rows", [])
    ]
    return fields, rows


def run_compact(client: BigQueryClient, name: str, sql: str, output: Path, max_bytes: int = 10_000_000_000) -> dict[str, Any]:
    dry = client.query(sql, dry_run=True, max_bytes=max_bytes)
    actual = client.query(sql, dry_run=False, max_bytes=max_bytes)
    fields, rows = rows_from_result(actual)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    stats = actual.get("_job_metadata", {}).get("statistics", {}).get("query", {})
    manifest = {
        "query_name": name,
        "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "job_id": actual.get("jobReference", {}).get("jobId"),
        "dry_bytes_processed": int(dry.get("totalBytesProcessed", 0) or 0),
        "bytes_processed": int(stats.get("totalBytesProcessed", actual.get("totalBytesProcessed", 0)) or 0),
        "bytes_billed": int(stats.get("totalBytesBilled", actual.get("totalBytesBilled", 0)) or 0),
        "cache_hit": stats.get("cacheHit", actual.get("cacheHit")),
        "row_count": len(rows),
        "raw_rows_not_exported": True,
        "output": str(output),
    }
    (RESULTS / f"{name}_manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"manifest": manifest, "rows": rows}


def candidate_sql() -> str:
    return r"""
WITH b AS (SELECT * FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`)
SELECT 'full_observation_grid' AS cohort, 'all_mapped_anchors' AS stage,
       CAST(cutoff_time AS STRING) AS cutoff_time, '0' AS requirement,
       COUNT(*) AS n_wallets, COUNT(*) AS denominator,
       SAFE_DIVIDE(COUNT(*), COUNT(*)) AS coverage_rate,
       'All (anchor_wallet, cutoff_time) rows retained; no activity requirement.' AS definition
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'observability', 'observed_before_cutoff', CAST(cutoff_time AS STRING), 'any_pre_cutoff_event',
       COUNTIF(observed_before_cutoff), COUNT(*), SAFE_DIVIDE(COUNTIF(observed_before_cutoff), COUNT(*)),
       'At least one source event before cutoff; discovery table itself retains non-observed anchors.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_events_ge_1', CAST(cutoff_time AS STRING), '1', COUNTIF(history_event_count_30d >= 1), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1), COUNT(*)), '[cutoff-30d, cutoff) has at least one event.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_events_ge_3', CAST(cutoff_time AS STRING), '3', COUNTIF(history_event_count_30d >= 3), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 3), COUNT(*)), '[cutoff-30d, cutoff) has at least three events.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_events_ge_5', CAST(cutoff_time AS STRING), '5', COUNTIF(history_event_count_30d >= 5), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 5), COUNT(*)), '[cutoff-30d, cutoff) has at least five events.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_events_ge_10', CAST(cutoff_time AS STRING), '10', COUNTIF(history_event_count_30d >= 10), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 10), COUNT(*)), '[cutoff-30d, cutoff) has at least ten events.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_events_ge_20', CAST(cutoff_time AS STRING), '20', COUNTIF(history_event_count_30d >= 20), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 20), COUNT(*)), '[cutoff-30d, cutoff) has at least twenty events.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_events_ge_50', CAST(cutoff_time AS STRING), '50', COUNTIF(history_event_count_30d >= 50), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 50), COUNT(*)), '[cutoff-30d, cutoff) has at least fifty events.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_ge_1_score_events_ge_0', CAST(cutoff_time AS STRING), 'history>=1;score>=0', COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 0), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 0), COUNT(*)), 'Discovery scoreable with history>=1; no score-window activity requirement.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_ge_1_score_events_ge_1', CAST(cutoff_time AS STRING), 'history>=1;score>=1', COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 1), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 1), COUNT(*)), 'Diagnostic sensitivity only; score activity is pre-cutoff.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_ge_1_score_events_ge_3', CAST(cutoff_time AS STRING), 'history>=1;score>=3', COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 3), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 3), COUNT(*)), 'Diagnostic sensitivity only; score activity is pre-cutoff.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_ge_1_score_events_ge_5', CAST(cutoff_time AS STRING), 'history>=1;score>=5', COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 5), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 5), COUNT(*)), 'Diagnostic sensitivity only; score activity is pre-cutoff.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'discovery', 'history_ge_1_score_events_ge_10', CAST(cutoff_time AS STRING), 'history>=1;score>=10', COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 10), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= 10), COUNT(*)), 'Diagnostic sensitivity only; score activity is pre-cutoff.'
FROM b GROUP BY cutoff_time
UNION ALL
SELECT 'future_evaluation', 'history_ge_1_with_future_table_row', CAST(cutoff_time AS STRING), 'history>=1', COUNTIF(history_event_count_30d >= 1), COUNT(*), SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1), COUNT(*)), 'Future metrics can be evaluated for discovery rows; future outcomes are not an entry filter.'
FROM b GROUP BY cutoff_time
ORDER BY cutoff_time, cohort, stage;
"""


def sensitivity_sql() -> str:
    return r"""
WITH b AS (SELECT * FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`),
he AS (SELECT * FROM UNNEST([1,3,5,10,20]) AS min_history_events),
se AS (SELECT * FROM UNNEST([0,1,3,5,10]) AS min_score_events),
ad AS (SELECT * FROM UNNEST([1,2,3,5,10]) AS min_history_active_days)
SELECT 'history_events' AS sensitivity_dimension, CAST(cutoff_time AS STRING) AS cutoff_time,
       CAST(he.min_history_events AS STRING) AS requirement_1, 'none' AS requirement_2,
       COUNTIF(history_event_count_30d >= he.min_history_events) AS n_wallets, COUNT(*) AS denominator,
       SAFE_DIVIDE(COUNTIF(history_event_count_30d >= he.min_history_events), COUNT(*)) AS coverage_rate
FROM b CROSS JOIN he GROUP BY cutoff_time, he.min_history_events
UNION ALL
SELECT 'score_window_events_given_history_ge_1', CAST(cutoff_time AS STRING), CAST(se.min_score_events AS STRING), 'history>=1',
       COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= se.min_score_events), COUNT(*),
       SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1 AND event_count_7d >= se.min_score_events), COUNT(*))
FROM b CROSS JOIN se GROUP BY cutoff_time, se.min_score_events
UNION ALL
SELECT 'history_active_days_given_history_ge_1', CAST(cutoff_time AS STRING), CAST(ad.min_history_active_days AS STRING), 'history>=1',
       COUNTIF(history_event_count_30d >= 1 AND active_days_30d >= ad.min_history_active_days), COUNT(*),
       SAFE_DIVIDE(COUNTIF(history_event_count_30d >= 1 AND active_days_30d >= ad.min_history_active_days), COUNT(*))
FROM b CROSS JOIN ad GROUP BY cutoff_time, ad.min_history_active_days
ORDER BY sensitivity_dimension, cutoff_time, requirement_1;
"""


def feature_coverage_sql() -> str:
    specs = [
        ("log_hist_events", "LOG(1 + history_event_count_30d)", "[t-30d,t)", "MATERIALIZED_DERIVABLE", "TRUE_ZERO when no history events"),
        ("hist_active_days", "active_days_30d", "[t-30d,t)", "MATERIALIZED", "TRUE_ZERO when no history events"),
        ("log_hist_counterparties", "LOG(1 + unique_counterparties_30d)", "[t-30d,t)", "MATERIALIZED_DERIVABLE", "Counterparty count is explicit zero when no counterparties"),
        ("log_score_events", "LOG(1 + event_count_7d)", "[t-7d,t)", "MATERIALIZED_DERIVABLE", "TRUE_ZERO when no score-window events"),
        ("score_active_days", "active_days_7d", "[t-7d,t)", "MATERIALIZED", "TRUE_ZERO when no score-window events"),
        ("activity_change", "SAFE_DIVIDE(event_count_7d, 7) - SAFE_DIVIDE(history_event_count_30d - event_count_7d, 23)", "[t-30d,t), split [t-30d,t-7d)/[t-7d,t)", "MATERIALIZED_DERIVABLE", "No future data; zero activity is a true zero"),
        ("counterparty_novelty", "SAFE_DIVIDE(new_counterparties_7d, score_unique_counterparties_7d)", "prior [t-30d,t-7d), score [t-7d,t)", "MATERIALIZED_DERIVABLE", "NOT_APPLICABLE when score window has no counterparties"),
        ("counterparty_growth", "IF(score_unique_counterparties_7d > 0, LOG(1 + score_unique_counterparties_7d) - LOG(1 + prior_unique_counterparties_23d * 7 / 23), NULL)", "prior [t-30d,t-7d), score [t-7d,t)", "MATERIALIZED_DERIVABLE", "Requires event-level counterparty set counts"),
        ("reciprocity_change", "NULL", "prior [t-30d,t-7d), score [t-7d,t)", "NOT_MATERIALIZED_EXACT", "Anchor event table permits reconstruction, but the exact OW-009 delta is not a column in v1"),
        ("score_burstiness", "SAFE_DIVIDE(max_events_per_active_hour_7d, mean_events_per_active_hour_7d)", "[t-7d,t)", "MATERIALIZED_DERIVABLE", "NOT_APPLICABLE when score window has no active hour"),
        ("inter_event_gap", "inter_event_gap_mean_sec_30d", "[t-30d,t)", "MATERIALIZED", "NOT_APPLICABLE when fewer than two ordered events"),
        ("event_family", "native_event_count_30d + token_event_count_30d + internal_event_count_30d", "[t-30d,t)", "MATERIALIZED", "Family counts preserve native/token/internal composition"),
        ("native_type", "native_event_count_30d", "[t-30d,t)", "MATERIALIZED", "Native external transaction count"),
        ("token_type", "token_event_count_30d", "[t-30d,t)", "MATERIALIZED", "Token transfer count and contract diversity"),
        ("internal_type", "internal_event_count_30d", "[t-30d,t)", "MATERIALIZED", "Internal trace count"),
        ("native_amount", "native_value_mean_30d", "[t-30d,t)", "MATERIALIZED", "NOT_APPLICABLE when no native events; BIGNUMERIC source"),
        ("token_quantity", "NULL", "[t-30d,t)", "UNSUPPORTED_CROSS_ASSET", "Raw quantity is retained in anchor events but not summed across contracts"),
        ("temporal_ordering", "inter_event_gap_mean_sec_30d", "[t-30d,t)", "MATERIALIZED", "Sub-day timestamp and deterministic event order retained"),
        ("rapid_forwarding", "rapid_forwarding_adjacent_count_30d", "[t-30d,t)", "MATERIALIZED_PROXY", "Adjacent incoming-to-outgoing <=1h proxy"),
        ("fan_in_out", "max_fan_in_counterparties_per_hour_7d + max_fan_out_counterparties_per_hour_7d", "[t-7d,t)", "MATERIALIZED_PROXY", "Hourly fan-in/fan-out proxy"),
        ("temporal_cycles", "NULL", "[t-30d,t)", "UNSUPPORTED", "Requires higher-order temporal path materialization"),
        ("split_merge", "NULL", "[t-30d,t)", "UNSUPPORTED", "Requires asset-aware event/path semantics"),
    ]
    parts = []
    for name, expr, window, status, notes in specs:
        if expr == "NULL":
            parts.append(f"SELECT CAST(cutoff_time AS STRING) AS cutoff_time, '{name}' AS feature, 'ictdata-507912.exgraph.openworld_anchor_events_v1' AS source_table, '{window}' AS time_window, COUNT(*) AS total_rows, COUNT(*) AS missing_rows, 1.0 AS missing_rate, 0.0 AS wallet_coverage, 'yes' AS requires_raw_event_level_data, 'no' AS requires_future_data, '{status}' AS availability_status, '{notes}' AS notes FROM b GROUP BY cutoff_time")
        else:
            parts.append(f"SELECT CAST(cutoff_time AS STRING) AS cutoff_time, '{name}' AS feature, 'ictdata-507912.exgraph.openworld_anchor_events_v1' AS source_table, '{window}' AS time_window, COUNT(*) AS total_rows, COUNTIF(({expr}) IS NULL) AS missing_rows, SAFE_DIVIDE(COUNTIF(({expr}) IS NULL), COUNT(*)) AS missing_rate, SAFE_DIVIDE(COUNTIF(({expr}) IS NOT NULL), COUNT(*)) AS wallet_coverage, 'yes' AS requires_raw_event_level_data, 'no' AS requires_future_data, '{status}' AS availability_status, '{notes}' AS notes FROM b GROUP BY cutoff_time")
    # Add evaluation-only rows explicitly so the separation is visible in the report.
    parts.append("SELECT 'all cutoffs' AS cutoff_time, 'future_outcomes' AS feature, 'ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1' AS source_table, '[t,t+7d) and [t,t+30d)' AS time_window, COUNT(*) AS total_rows, 0 AS missing_rows, 0.0 AS missing_rate, 1.0 AS wallet_coverage, 'yes' AS requires_raw_event_level_data, 'yes' AS requires_future_data, 'EVALUATION_ONLY_SEPARATE_TABLE' AS availability_status, 'Never use for discovery eligibility, ranking, normalization, or matching.' AS notes FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1`")
    return "WITH b AS (SELECT * FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`)\n" + "\nUNION ALL\n".join(parts) + "\nORDER BY 1, 2"


def direction_sql() -> str:
    return r"""
SELECT CAST(cutoff_time AS STRING) AS cutoff_time, 'incoming_only' AS role,
       COUNTIF(history_event_count_30d >= 1 AND incoming_event_count_30d > 0 AND outgoing_event_count_30d = 0) AS wallet_count,
       'history>=1; [t-30d,t)' AS condition FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
UNION ALL
SELECT CAST(cutoff_time AS STRING), 'outgoing_only', COUNTIF(history_event_count_30d >= 1 AND outgoing_event_count_30d > 0 AND incoming_event_count_30d = 0), 'history>=1; [t-30d,t)' FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
UNION ALL
SELECT CAST(cutoff_time AS STRING), 'both_direction', COUNTIF(history_event_count_30d >= 1 AND incoming_event_count_30d > 0 AND outgoing_event_count_30d > 0), 'history>=1; [t-30d,t)' FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
UNION ALL
SELECT CAST(cutoff_time AS STRING), 'has_self_event', COUNTIF(history_event_count_30d >= 1 AND self_event_count_30d > 0), 'history>=1; [t-30d,t)' FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
ORDER BY cutoff_time, role;
"""


def mapping_sql() -> str:
    return r"""
SELECT CAST(cutoff_time AS STRING) AS cutoff_time, 'has_mapped_counterparty' AS coverage_type,
       COUNTIF(history_event_count_30d >= 1 AND mapped_counterparties_30d > 0) AS wallet_count,
       'history>=1; [t-30d,t)' AS condition FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
UNION ALL
SELECT CAST(cutoff_time AS STRING), 'has_unmapped_counterparty', COUNTIF(history_event_count_30d >= 1 AND unmapped_counterparties_30d > 0), 'history>=1; [t-30d,t)' FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
UNION ALL
SELECT CAST(cutoff_time AS STRING), 'all_counterparties_mapped', COUNTIF(history_event_count_30d >= 1 AND unique_counterparties_30d > 0 AND mapped_counterparties_30d = unique_counterparties_30d), 'history>=1; [t-30d,t)' FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
UNION ALL
SELECT CAST(cutoff_time AS STRING), 'has_any_counterparty', COUNTIF(history_event_count_30d >= 1 AND unique_counterparties_30d > 0), 'history>=1; [t-30d,t)' FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` GROUP BY cutoff_time
ORDER BY cutoff_time, coverage_type;
"""


def leakage_sql() -> str:
    return r"""
WITH bounds AS (
  SELECT
    COUNT(*) AS feature_rows,
    COUNTIF(history_start >= cutoff_time) AS bad_history_start,
    COUNTIF(history_end > cutoff_time) AS bad_history_end,
    COUNTIF(score_start >= cutoff_time) AS bad_score_start,
    COUNTIF(data_role != 'DISCOVERY_ONLY') AS bad_discovery_role,
    COUNTIF(history_window_coverage_status != 'OBSERVED_FULL_WINDOW') AS bad_history_coverage
  FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1`
),
future_sep AS (
  SELECT
    COUNT(*) AS future_rows,
    COUNTIF(NOT evaluation_only) AS non_evaluation_rows,
    COUNTIF(data_role != 'EVALUATION_ONLY') AS bad_future_role
  FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_future_outcomes_v1`
),
feature_schema AS (
  SELECT COUNTIF(LOWER(column_name) LIKE '%future%') AS future_named_columns
  FROM `ictdata-507912.exgraph.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name = 'openworld_wallet_cutoff_features_v1'
),
recomputed AS (
  SELECT
    f.anchor_wallet, f.cutoff_time,
    COUNTIF(e.event_identity IS NOT NULL) AS recomputed_history_events,
    COUNTIF(e.event_identity IS NOT NULL AND e.event_timestamp >= TIMESTAMP_SUB(f.cutoff_time, INTERVAL 7 DAY)) AS recomputed_score_events
  FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` AS f
  LEFT JOIN `ictdata-507912.exgraph.openworld_anchor_events_v1` AS e
    ON e.anchor_wallet = f.anchor_wallet
   AND e.event_timestamp >= TIMESTAMP('2022-05-01 00:00:00+00')
   AND e.event_timestamp < TIMESTAMP('2022-08-01 00:00:00+00')
   AND e.event_timestamp >= TIMESTAMP_SUB(f.cutoff_time, INTERVAL 30 DAY)
   AND e.event_timestamp < f.cutoff_time
  GROUP BY f.anchor_wallet, f.cutoff_time
),
comparison AS (
  SELECT
    COUNT(*) AS compared_rows,
    COUNTIF(f.history_event_count_30d != r.recomputed_history_events) AS history_count_mismatches,
    COUNTIF(f.event_count_7d != r.recomputed_score_events) AS score_count_mismatches
  FROM `ictdata-507912.exgraph.openworld_wallet_cutoff_features_v1` AS f
  JOIN recomputed AS r USING (anchor_wallet, cutoff_time)
)
SELECT 'bounds' AS audit, 'feature_rows' AS metric, CAST(feature_rows AS STRING) AS value, 'zero means no issue' AS notes FROM bounds
UNION ALL SELECT 'bounds','bad_history_start',CAST(bad_history_start AS STRING),'must be 0' FROM bounds
UNION ALL SELECT 'bounds','bad_history_end',CAST(bad_history_end AS STRING),'must be 0; history is half-open before cutoff' FROM bounds
UNION ALL SELECT 'bounds','bad_score_start',CAST(bad_score_start AS STRING),'must be 0; score window is still pre-cutoff' FROM bounds
UNION ALL SELECT 'bounds','bad_discovery_role',CAST(bad_discovery_role AS STRING),'must be 0' FROM bounds
UNION ALL SELECT 'bounds','bad_history_coverage',CAST(bad_history_coverage AS STRING),'must be 0 for the three cutoffs' FROM bounds
UNION ALL SELECT 'future_separation','future_rows',CAST(future_rows AS STRING),'separate table' FROM future_sep
UNION ALL SELECT 'future_separation','non_evaluation_rows',CAST(non_evaluation_rows AS STRING),'must be 0' FROM future_sep
UNION ALL SELECT 'future_separation','bad_future_role',CAST(bad_future_role AS STRING),'must be 0' FROM future_sep
UNION ALL SELECT 'schema','future_named_columns_in_discovery_table',CAST(future_named_columns AS STRING),'must be 0' FROM feature_schema
UNION ALL SELECT 'recomputed_asof','compared_rows',CAST(compared_rows AS STRING),'must equal 82,839' FROM comparison
UNION ALL SELECT 'recomputed_asof','history_count_mismatches',CAST(history_count_mismatches AS STRING),'must be 0' FROM comparison
UNION ALL SELECT 'recomputed_asof','score_count_mismatches',CAST(score_count_mismatches AS STRING),'must be 0' FROM comparison
ORDER BY audit, metric;
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    client = BigQueryClient(PROJECT, GCLOUD)
    runs = {}
    runs["candidate_counts_by_cutoff"] = run_compact(client, "candidate_counts_by_cutoff", candidate_sql(), RESULTS / "candidate_counts_by_cutoff.csv")
    runs["cohort_sensitivity"] = run_compact(client, "cohort_sensitivity", sensitivity_sql(), RESULTS / "cohort_sensitivity.csv")
    runs["feature_coverage"] = run_compact(client, "feature_coverage", feature_coverage_sql(), RESULTS / "feature_coverage.csv", max_bytes=5_000_000_000)
    runs["direction_coverage"] = run_compact(client, "direction_coverage", direction_sql(), RESULTS / "direction_coverage.csv")
    runs["counterparty_mapping_coverage"] = run_compact(client, "counterparty_mapping_coverage", mapping_sql(), RESULTS / "counterparty_mapping_coverage.csv")
    runs["temporal_leakage_audit"] = run_compact(client, "temporal_leakage_audit", leakage_sql(), RESULTS / "temporal_leakage_audit.csv")

    # Keep the current OW-009 matching diagnostic frozen and traceable.  It is
    # copied, not recomputed with a new procedure and not used for discovery.
    parent_matching = ROOT / "research" / "openworld" / "substrate" / "matching_diagnostics.csv"
    if parent_matching.exists():
        shutil.copy2(parent_matching, RESULTS / "matching_diagnostics.csv")
        shutil.copy2(parent_matching, OUT / "matching_diagnostics.csv")
    identity = RESULTS / "event_identity_audit.csv"
    if identity.exists():
        shutil.copy2(identity, OUT / "event_identity_audit.csv")
    source_cov = RESULTS / "event_family_coverage.csv"
    if source_cov.exists():
        shutil.copy2(source_cov, OUT / "event_family_coverage.csv")

    # Add the pre-existing local OW-009 strict/top-5 numbers as a clearly
    # separate, local-substrate comparison to the event-level population table.
    parent_candidate = ROOT / "research" / "openworld" / "substrate" / "candidate_attrition_by_cutoff.csv"
    if parent_candidate.exists():
        with parent_candidate.open() as f:
            local_rows = list(csv.DictReader(f))
        extra = []
        for r in local_rows:
            if r.get("stage") in {"all_mapped_wallets", "top5_percent_anomaly_cohort", "matched_treated_cohort"} and r.get("variant") == "registered_strict_10_events":
                extra.append({
                    "cohort": "ow009_local_comparison",
                    "stage": r["stage"],
                    "cutoff_time": r["cutoff"],
                    "requirement": r.get("variant", ""),
                    "n_wallets": r["wallets_after"],
                    "denominator": r["wallets_before"],
                    "coverage_rate": "",
                    "definition": r["exact_filter_condition"],
                })
        path = RESULTS / "candidate_counts_by_cutoff.csv"
        with path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["cohort", "stage", "cutoff_time", "requirement", "n_wallets", "denominator", "coverage_rate", "definition"])
            writer.writerows(extra)
        shutil.copy2(path, OUT / "candidate_counts_by_cutoff.csv")
    for name in ["cohort_sensitivity", "feature_coverage", "direction_coverage", "counterparty_mapping_coverage", "temporal_leakage_audit"]:
        shutil.copy2(RESULTS / f"{name}.csv", OUT / f"{name}.csv")

    manifests = {}
    for p in sorted(RESULTS.glob("*_manifest.json")):
        manifests[p.stem] = json.loads(p.read_text())
    (RESULTS / "materialization_manifest.json").write_text(json.dumps({"label_blind": True, "raw_rows_not_exported": True, "queries": manifests}, indent=2))
    shutil.copy2(RESULTS / "materialization_manifest.json", OUT / "materialization_manifest.json")
    print(json.dumps({k: v["manifest"] for k, v in runs.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
