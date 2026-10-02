#!/usr/bin/env python3
"""Compute pre-adjudication Gate 1B substantive validity for frozen V2.

No future outcomes, prediction scores, or Phase 2/3 artifacts are read. The
report keeps coder-specific estimates separate and reports an ambiguity range
for the 20 shared double-coded cases rather than silently adjudicating them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import csv
import json
from collections import Counter
from pathlib import Path

from phase1_v2_annotation_common import read_csv_exact

TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
THRESHOLDS = {
    "well_formed_proposition": 0.80,
    "explicit_scope": 0.70,
    "explicit_time_horizon": 0.70,
    "observable_consequence": 0.80,
    "executable_falsifier": 0.50,
    "valid_evidence_link": 0.70,
    "non_trivial_qualification_or_abstention": 0.20,
}
CRITERIA = list(THRESHOLDS)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(v) -> str:
    return "" if v is None else str(v).strip()


def read_rows(path: Path) -> list[dict[str, str]]:
    _, rows = read_csv_exact(path)
    return rows


def row_criteria(a: dict[str, str], b: dict[str, str]) -> dict[str, bool]:
    evidence = {x for x in clean(b.get("evidence_labels")).split(";") if x}
    valid_evidence = any(
        group in evidence and clean(b.get(f"evidence_pointer_{group}")) in {"direct_descriptive", "predictive_consistent"}
        for group in ["E_SELF", "E_MARKET", "E_COVERAGE"]
    )
    return {
        "well_formed_proposition": clean(a.get("proposition_boundary")) == "atomic" and clean(a.get("proposition_status")) == "well_formed",
        "explicit_scope": clean(a.get("scope_status")) == "explicit",
        "explicit_time_horizon": clean(a.get("time_horizon_status")) == "explicit",
        "observable_consequence": clean(a.get("consequence_observability")) == "observable",
        "executable_falsifier": clean(a.get("falsifier_executability")) == "executable",
        "valid_evidence_link": valid_evidence,
        "non_trivial_qualification_or_abstention": clean(a.get("qualification_substantive")) == "non_trivial",
    }


def criterion_counts(rows_a, rows_b=None):
    if rows_b is None:
        rows_b = [{"row_handle": r["row_handle"]} for r in rows_a]
    by_b = {clean(r["row_handle"]): r for r in rows_b}
    values = []
    for row in rows_a:
        values.append(row_criteria(row, by_b[clean(row["row_handle"])]))
    return {
        criterion: {"n": len(values), "positive": sum(int(v[criterion]) for v in values), "proportion": (sum(int(v[criterion]) for v in values) / len(values) if values else None)}
        for criterion in CRITERIA
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    ap.add_argument("--pass-a-coder-a", required=True)
    ap.add_argument("--pass-a-coder-b", required=True)
    ap.add_argument("--pass-b-coder-a", required=True)
    ap.add_argument("--pass-b-coder-b", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    package = Path(args.package_dir)
    pa = {"CODER_A": read_rows(Path(args.pass_a_coder_a)), "CODER_B": read_rows(Path(args.pass_a_coder_b))}
    pb = {"CODER_A": read_rows(Path(args.pass_b_coder_a)), "CODER_B": read_rows(Path(args.pass_b_coder_b))}
    a_by_handle = {coder: {clean(r["row_handle"]): r for r in rows} for coder, rows in pa.items()}
    b_by_handle = {coder: {clean(r["row_handle"]): r for r in rows} for coder, rows in pb.items()}
    handles_a, handles_b = set(a_by_handle["CODER_A"]), set(a_by_handle["CODER_B"])
    shared = sorted(handles_a & handles_b)
    unique_a = sorted(handles_a - handles_b)
    unique_b = sorted(handles_b - handles_a)
    if len(shared) != 60 or len(unique_a) != 120 or len(unique_b) != 120:
        raise SystemExit(f"unexpected assignment sets: shared={len(shared)}, unique_a={len(unique_a)}, unique_b={len(unique_b)}")

    coder_results = {}
    for coder in ["CODER_A", "CODER_B"]:
        coder_results[coder] = criterion_counts(pa[coder], pb[coder])

    # A unique-row estimate uses each coder for their non-shared cases. On the
    # shared rows, disagreements are not adjudicated: report a conservative
    # lower bound (both must be positive), an upper bound (either may be
    # positive), and the unambiguous point estimate.
    shared_rows = []
    for handle in shared:
        ca = row_criteria(a_by_handle["CODER_A"][handle], b_by_handle["CODER_A"][handle])
        cb = row_criteria(a_by_handle["CODER_B"][handle], b_by_handle["CODER_B"][handle])
        shared_rows.append((ca, cb))
    unique_rows = []
    for handle in unique_a:
        unique_rows.append(row_criteria(a_by_handle["CODER_A"][handle], b_by_handle["CODER_A"][handle]))
    for handle in unique_b:
        unique_rows.append(row_criteria(a_by_handle["CODER_B"][handle], b_by_handle["CODER_B"][handle]))
    total_rows = len(unique_rows) + len(shared_rows)
    unique_estimates = {}
    for criterion in CRITERIA:
        unique_positive = sum(int(v[criterion]) for v in unique_rows)
        both_positive = sum(int(a[criterion] and b[criterion]) for a, b in shared_rows)
        either_positive = sum(int(a[criterion] or b[criterion]) for a, b in shared_rows)
        disagreements = sum(int(a[criterion] != b[criterion]) for a, b in shared_rows)
        unambiguous = sum(int(a[criterion] == b[criterion]) for a, b in shared_rows)
        unique_estimates[criterion] = {
            "n_unique_rows": len(unique_rows),
            "n_shared_rows": len(shared_rows),
            "n_total_rows": total_rows,
            "shared_disagreements": disagreements,
            "shared_agreement_rate": unambiguous / len(shared_rows) if shared_rows else None,
            "conservative_lower_positive": unique_positive + both_positive,
            "conservative_lower_proportion": (unique_positive + both_positive) / total_rows if total_rows else None,
            "conservative_upper_positive": unique_positive + either_positive,
            "conservative_upper_proportion": (unique_positive + either_positive) / total_rows if total_rows else None,
            "unambiguous_positive": unique_positive + sum(int(a[criterion]) for a, b in shared_rows if a[criterion] == b[criterion]),
            "unambiguous_rows": len(unique_rows) + unambiguous,
            "unambiguous_proportion": ((unique_positive + sum(int(a[criterion]) for a, b in shared_rows if a[criterion] == b[criterion])) / (len(unique_rows) + unambiguous) if len(unique_rows) + unambiguous else None),
        }

    threshold_checks = {}
    for criterion, threshold in THRESHOLDS.items():
        lower = unique_estimates[criterion]["conservative_lower_proportion"]
        upper = unique_estimates[criterion]["conservative_upper_proportion"]
        coder_a = coder_results["CODER_A"][criterion]["proportion"]
        coder_b = coder_results["CODER_B"][criterion]["proportion"]
        if lower is not None and lower >= threshold:
            status = "PASS_CONSERVATIVE"
        elif upper is not None and upper < threshold:
            status = "FAIL_CONSERVATIVE"
        else:
            status = "INDETERMINATE_PRE_ADJUDICATION"
        threshold_checks[criterion] = {
            "threshold": threshold,
            "coder_a_pass": coder_a >= threshold if coder_a is not None else None,
            "coder_b_pass": coder_b >= threshold if coder_b is not None else None,
            "conservative_range_pass_status": status,
        }

    report = {
        "created_at": utc_now(),
        "status": "GATE_1B_REPORTED_PRE_ADJUDICATION",
        "protocol_version": "phase1_annotation_gate_v2_dev",
        "package_dir": str(package),
        "primary_unit": "annotation_row_with_case_cluster_context",
        "adjudication_included": False,
        "future_outcomes_joined": False,
        "prediction_scores_joined": False,
        "phase_2_or_phase_3_accessed": False,
        "thresholds": THRESHOLDS,
        "coder_specific": coder_results,
        "shared_double_code": {"rows": len(shared), "cases": 20},
        "unique_row_estimates": unique_estimates,
        "threshold_checks": threshold_checks,
        "interpretation": "Coder-specific estimates and non-adjudicated lower/upper ranges are reported separately; no disagreement is silently adjudicated.",
    }
    out = Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(out), "shared_rows": len(shared)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
