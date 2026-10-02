#!/usr/bin/env python3
"""Fail-closed validator for Semantic Gate V2.1 annotation files.

The validator never joins outcomes, F, Delta, split, wallet, or August labels.
It checks exact worksheet schemas, immutable displayed fields, closed labels,
exact substring spans, known evidence IDs, missingness, and blind-sheet leakage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
COMMITMENT = {"explicit", "hedged", "generic", "none", "unclear"}
OPERATIONALITY = {"operational", "non_operational", "unclear"}
ALIGNMENT = {"entailed", "unsupported", "contradicted", "unclear"}
HORIZON = {"compatible", "incompatible", "unclear"}
RELEVANCE = {"relevant", "irrelevant", "unclear", "not_applicable"}
PASS_A_COLUMNS = ["row_handle", "hypothesis_text", "pass_a_commitment", "pass_a_operationality", "pass_a_text_span", "pass_a_notes"]
PASS_B_COLUMNS = [
    "row_handle", "hypothesis_text", "recorded_activity", "recorded_active_days",
    "recorded_counterparty_breadth", "recorded_new_counterparties", "horizon_days",
    "evidence_labels", "alignment_activity", "alignment_active_days",
    "alignment_counterparty_breadth", "alignment_new_counterparties",
    "alignment_span_activity", "alignment_span_active_days",
    "alignment_span_counterparty_breadth", "alignment_span_new_counterparties",
    "horizon_compatibility",
] + [f"evidence_relevance_{group}" for group in EVIDENCE_GROUPS] + ["pass_b_notes"]
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")
DATE_RE = re.compile(r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b")
LEAK_RE = re.compile(r"(?i)(?:\bdelta\b|\baugust\b|\bjuly\b|\bsplit\b|\blog[_ -]?loss\b|\bmodel\s+(?:loss|performance|output)\b|\bF\s*=)" )


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def add_error(errors: list[dict], kind: str, row: int | None, column: str | None, detail: str) -> None:
    errors.append({"kind": kind, "row": row, "column": column, "detail": detail})


def check_exact_columns(frame: pd.DataFrame, expected: list[str], errors: list[dict], label: str) -> None:
    actual = list(frame.columns)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    for column in missing:
        add_error(errors, "missing_column", None, column, f"{label} required column missing")
    for column in extra:
        add_error(errors, "unexpected_column", None, column, f"{label} exact schema rejects extra column")
    if not missing and not extra and actual != expected:
        add_error(errors, "column_order", None, None, f"{label} columns must use the locked order")


def validate_common(frame: pd.DataFrame, expected: pd.DataFrame, errors: list[dict], label: str, expected_columns: list[str]) -> None:
    check_exact_columns(frame, expected_columns, errors, label)
    if "row_handle" not in frame.columns:
        return
    if frame["row_handle"].duplicated().any():
        add_error(errors, "duplicate_row_handle", None, "row_handle", f"{label} has duplicate row handles")
    expected_handles = set(expected["row_handle"])
    actual_handles = set(frame["row_handle"])
    for handle in sorted(expected_handles - actual_handles):
        add_error(errors, "missing_row_handle", None, "row_handle", f"{label} missing {handle}")
    for handle in sorted(actual_handles - expected_handles):
        add_error(errors, "unexpected_row_handle", None, "row_handle", f"{label} unexpected {handle}")
    if len(frame) != len(expected):
        add_error(errors, "row_count", None, None, f"{label} rows={len(frame)} expected={len(expected)}")
    # All non-text-source cells are annotator-controlled and must remain blind.
    for row_index, row in frame.iterrows():
        for column in frame.columns:
            value = text(row[column])
            if not value or column == "hypothesis_text":
                continue
            if WALLET_RE.search(value) or DATE_RE.search(value) or LEAK_RE.search(value):
                add_error(errors, "blindness_suspect_value", int(row_index), column, f"{label} contains possible unblinded metadata")


def validate_pass_a(frame: pd.DataFrame, reference: pd.DataFrame, allow_blank: bool) -> tuple[list[dict], dict]:
    errors: list[dict] = []
    validate_common(frame, reference, errors, "Pass A", PASS_A_COLUMNS)
    if set(PASS_A_COLUMNS) - set(frame.columns):
        return errors, {"rows": int(len(frame)), "missing_cells": None, "total_annotation_cells": int(len(frame) * 2)}
    ref = reference.set_index("row_handle", drop=False)
    missing_cells = 0
    total_cells = len(frame) * 2
    for idx, row in frame.iterrows():
        handle = text(row["row_handle"])
        if handle not in ref.index:
            continue
        if text(row["hypothesis_text"]) != text(ref.loc[handle, "hypothesis_text"]):
            add_error(errors, "immutable_field_changed", int(idx), "hypothesis_text", "Pass A source text differs")
        commitment = text(row["pass_a_commitment"])
        operationality = text(row["pass_a_operationality"])
        span = text(row["pass_a_text_span"])
        if commitment == "":
            missing_cells += 1
            if not allow_blank:
                add_error(errors, "missing_annotation", int(idx), "pass_a_commitment", "missing commitment")
        elif commitment not in COMMITMENT:
            add_error(errors, "invalid_label", int(idx), "pass_a_commitment", commitment)
        if operationality == "":
            missing_cells += 1
            if not allow_blank:
                add_error(errors, "missing_annotation", int(idx), "pass_a_operationality", "missing operationality")
        elif operationality not in OPERATIONALITY:
            add_error(errors, "invalid_label", int(idx), "pass_a_operationality", operationality)
        if commitment not in {"", "unclear"} or operationality not in {"", "unclear"}:
            if span == "":
                add_error(errors, "missing_exact_span", int(idx), "pass_a_text_span", "non-unclear Pass A label requires an exact text span")
            elif span not in text(row["hypothesis_text"]):
                add_error(errors, "span_not_substring", int(idx), "pass_a_text_span", "Pass A span is not an exact substring of hypothesis_text")
    return errors, {"rows": int(len(frame)), "missing_cells": missing_cells, "total_annotation_cells": int(total_cells), "missing_rate": float(missing_cells / total_cells) if total_cells else None}


def validate_pass_b(frame: pd.DataFrame, reference: pd.DataFrame, allow_blank: bool) -> tuple[list[dict], dict]:
    errors: list[dict] = []
    validate_common(frame, reference, errors, "Pass B", PASS_B_COLUMNS)
    if set(PASS_B_COLUMNS) - set(frame.columns):
        return errors, {"rows": int(len(frame)), "missing_cells": None, "total_annotation_cells": int(len(frame) * 9)}
    ref = reference.set_index("row_handle", drop=False)
    missing_cells = 0
    total_cells = len(frame) * 9
    for idx, row in frame.iterrows():
        handle = text(row["row_handle"])
        if handle not in ref.index:
            continue
        for column in [
            "hypothesis_text", "recorded_activity", "recorded_active_days",
            "recorded_counterparty_breadth", "recorded_new_counterparties",
            "horizon_days", "evidence_labels",
        ]:
            if text(row[column]) != text(ref.loc[handle, column]):
                add_error(errors, "immutable_field_changed", int(idx), column, f"Pass B {column} differs from source")
        recorded = {text(row[f"recorded_{target}"]) for target in TARGETS}
        if not recorded.issubset({"up", "same", "down"}):
            add_error(errors, "invalid_recorded_category", int(idx), None, "recorded consequence category is not closed")
        present = {item.strip() for item in text(row["evidence_labels"]).split(";") if item.strip()}
        unknown = present - set(EVIDENCE_GROUPS)
        if unknown:
            add_error(errors, "unknown_evidence_id", int(idx), "evidence_labels", ";".join(sorted(unknown)))
        for target in TARGETS:
            label_column = f"alignment_{target}"
            span_column = f"alignment_span_{target}"
            value = text(row[label_column])
            span = text(row[span_column])
            if value == "":
                missing_cells += 1
                if not allow_blank:
                    add_error(errors, "missing_annotation", int(idx), label_column, "missing alignment")
            elif value not in ALIGNMENT:
                add_error(errors, "invalid_label", int(idx), label_column, value)
            if value not in {"", "unclear"}:
                if span == "":
                    add_error(errors, "missing_exact_span", int(idx), span_column, "non-unclear alignment requires an exact text span")
                elif span not in text(row["hypothesis_text"]):
                    add_error(errors, "span_not_substring", int(idx), span_column, "alignment span is not an exact substring of hypothesis_text")
        horizon = text(row["horizon_compatibility"])
        if horizon == "":
            missing_cells += 1
            if not allow_blank:
                add_error(errors, "missing_annotation", int(idx), "horizon_compatibility", "missing horizon compatibility")
        elif horizon not in HORIZON:
            add_error(errors, "invalid_label", int(idx), "horizon_compatibility", horizon)
        for group in EVIDENCE_GROUPS:
            column = f"evidence_relevance_{group}"
            value = text(row[column])
            if value == "":
                missing_cells += 1
                if not allow_blank:
                    add_error(errors, "missing_annotation", int(idx), column, "missing evidence relevance")
            elif value not in RELEVANCE:
                add_error(errors, "invalid_label", int(idx), column, value)
            elif group in present and value == "not_applicable":
                add_error(errors, "not_applicable_present_label", int(idx), column, "present evidence label cannot be not_applicable")
            elif group not in present and value not in {"", "not_applicable"}:
                add_error(errors, "missing_not_applicable", int(idx), column, "absent evidence label must be not_applicable")
    return errors, {"rows": int(len(frame)), "missing_cells": missing_cells, "total_annotation_cells": int(total_cells), "missing_rate": float(missing_cells / total_cells) if total_cells else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--pass-a", required=True)
    parser.add_argument("--pass-b", required=True)
    parser.add_argument("--allow-blank", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    package = Path(args.package_dir)
    pass_a = Path(args.pass_a)
    pass_b = Path(args.pass_b)
    ref_a = pd.read_csv(package / "PASS_A_TEXT_ONLY_BLIND.csv", dtype=str, keep_default_na=False)
    ref_b = pd.read_csv(package / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv", dtype=str, keep_default_na=False)
    frame_a = pd.read_csv(pass_a, dtype=str, keep_default_na=False)
    frame_b = pd.read_csv(pass_b, dtype=str, keep_default_na=False)
    errors_a, summary_a = validate_pass_a(frame_a, ref_a, args.allow_blank)
    errors_b, summary_b = validate_pass_b(frame_b, ref_b, args.allow_blank)
    errors = [{"pass": "A", **item} for item in errors_a] + [{"pass": "B", **item} for item in errors_b]
    report = {
        "created_at": utc_now(),
        "status": "PASS" if not errors else "FAIL",
        "allow_blank": bool(args.allow_blank),
        "package_dir": str(package),
        "pass_a": {"path": str(pass_a), "sha256": sha256_file(pass_a), **summary_a},
        "pass_b": {"path": str(pass_b), "sha256": sha256_file(pass_b), **summary_b},
        "error_count": len(errors),
        "errors": errors[:500],
        "errors_truncated": len(errors) > 500,
        "future_outcomes_joined": False,
        "f_delta_joined": False,
    }
    out = Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "error_count": report["error_count"], "out": str(out)}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
