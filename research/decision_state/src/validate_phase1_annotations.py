#!/usr/bin/env python3
"""Fail-closed validator for the Phase-1 annotation gate.

The validator checks only the fixed, outcome-blind annotation package.  It does
not join or read future outcomes, F, Delta, losses, split/date, wallet IDs, or
August membership.  It rejects extra columns, changed displayed source text,
unknown labels, invalid evidence IDs, and spans that are not exact substrings.
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
DIRECTIONS = {"up", "same", "down", "not_stated", "unclear"}
BOUNDARY = {"atomic", "compound", "none", "unclear"}
SCOPE = {"explicit", "partial", "absent", "unclear"}
HORIZON_STATUS = {"explicit", "implicit", "absent", "unclear"}
FALSIFIER = {"explicit", "implicit", "absent", "unclear"}
QUALIFICATION = {"assert", "qualify", "abstain", "unclear"}
ALIGNMENT = {"entailed", "unsupported", "contradicted", "unclear"}
HORIZON_COMPAT = {"compatible", "incompatible", "unclear"}
POINTER = {"supported", "unsupported", "unclear", "not_applicable"}
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
PASS_A_COLUMNS = [
    "row_handle", "hypothesis_text", "proposition_boundary", "proposition_span",
    "scope_status", "scope_span", "time_horizon_status", "time_horizon_span",
    "consequence_activity_text", "consequence_active_days_text",
    "consequence_counterparty_breadth_text", "consequence_new_counterparties_text",
    "falsifier_status", "falsifier_span", "qualification_status", "qualification_span",
    "pass_a_notes",
]
PASS_B_COLUMNS = [
    "row_handle", "hypothesis_text", "recorded_activity", "recorded_active_days",
    "recorded_counterparty_breadth", "recorded_new_counterparties", "recorded_horizon_days",
    "evidence_labels", "alignment_activity", "alignment_active_days",
    "alignment_counterparty_breadth", "alignment_new_counterparties",
    "alignment_span_activity", "alignment_span_active_days",
    "alignment_span_counterparty_breadth", "alignment_span_new_counterparties",
    "horizon_compatibility", "evidence_pointer_E_SELF", "evidence_pointer_E_MARKET",
    "evidence_pointer_E_COVERAGE", "evidence_pointer_E_PLACEBO", "pass_b_notes",
]
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")
LEAK_RE = re.compile(r"(?i)(?:\bdelta\b|\baugust\b|\bjuly\b|\bsplit\b|\blog[_ -]?loss\b|\bmodel\s+(?:loss|performance|output)\b|\bF\s*=)")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def err(errors, kind, row, column, detail):
    errors.append({"kind": kind, "row": row, "column": column, "detail": detail})


def exact_schema(frame, expected, label, errors):
    actual = list(frame.columns)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            err(errors, "missing_column", None, None, f"{label}: {missing}")
        if extra:
            err(errors, "unexpected_column", None, None, f"{label}: {extra}")
        if not missing and not extra:
            err(errors, "column_order", None, None, f"{label} column order differs from locked schema")


def validate_common(frame, reference, expected_columns, label, errors):
    exact_schema(frame, expected_columns, label, errors)
    if "row_handle" not in frame.columns:
        return 0
    if frame["row_handle"].duplicated().any():
        err(errors, "duplicate_row_handle", None, "row_handle", f"{label} has duplicate row handles")
    expected_handles = set(reference["row_handle"])
    actual_handles = set(frame["row_handle"])
    for handle in sorted(expected_handles - actual_handles):
        err(errors, "missing_row_handle", None, "row_handle", f"{label} missing {handle}")
    for handle in sorted(actual_handles - expected_handles):
        err(errors, "unexpected_row_handle", None, "row_handle", f"{label} unexpected {handle}")
    if len(frame) != len(reference):
        err(errors, "row_count", None, None, f"{label} rows={len(frame)} expected={len(reference)}")
    ref = reference.set_index("row_handle", drop=False)
    for idx, row in frame.iterrows():
        handle = clean(row.get("row_handle"))
        if handle not in ref.index:
            continue
        if clean(row.get("hypothesis_text")) != clean(ref.loc[handle, "hypothesis_text"]):
            err(errors, "source_text_changed", int(idx), "hypothesis_text", f"{label} source text changed for {handle}")
        for col in frame.columns:
            value = clean(row.get(col))
            if WALLET_RE.search(value) or LEAK_RE.search(value):
                # Notes are not allowed to introduce evaluation metadata either.
                if col not in {"hypothesis_text"}:
                    err(errors, "blindness_violation", int(idx), col, f"forbidden outcome/model text in {label}")
    return int(len(frame))


def check_span(row, status_col, span_col, allowed_status, required_statuses, text_col, errors, idx, allow_blank):
    status = clean(row.get(status_col))
    span = clean(row.get(span_col))
    if status == "":
        if not allow_blank:
            err(errors, "missing_annotation", int(idx), status_col, "missing status")
        return
    if status not in allowed_status:
        err(errors, "invalid_label", int(idx), status_col, status)
        return
    if status in required_statuses:
        if span == "":
            err(errors, "missing_exact_span", int(idx), span_col, f"{status_col}={status} requires a span")
        elif span not in clean(row.get(text_col)):
            err(errors, "span_not_substring", int(idx), span_col, "span is not an exact substring of hypothesis_text")
    elif span != "":
        err(errors, "unexpected_span", int(idx), span_col, f"{status_col}={status} must leave span blank")


def check_cat(row, col, allowed, errors, idx, allow_blank):
    value = clean(row.get(col))
    if value == "":
        if not allow_blank:
            err(errors, "missing_annotation", int(idx), col, "missing categorical annotation")
    elif value not in allowed:
        err(errors, "invalid_label", int(idx), col, value)


def validate_pass_a(frame, reference, allow_blank):
    errors = []
    validate_common(frame, reference, PASS_A_COLUMNS, "pass_a", errors)
    for idx, row in frame.iterrows():
        check_span(row, "proposition_boundary", "proposition_span", BOUNDARY, {"atomic", "compound"}, "hypothesis_text", errors, idx, allow_blank)
        check_span(row, "scope_status", "scope_span", SCOPE, {"explicit", "partial"}, "hypothesis_text", errors, idx, allow_blank)
        check_span(row, "time_horizon_status", "time_horizon_span", HORIZON_STATUS, {"explicit", "implicit"}, "hypothesis_text", errors, idx, allow_blank)
        check_span(row, "falsifier_status", "falsifier_span", FALSIFIER, {"explicit", "implicit"}, "hypothesis_text", errors, idx, allow_blank)
        check_span(row, "qualification_status", "qualification_span", QUALIFICATION, {"qualify", "abstain"}, "hypothesis_text", errors, idx, allow_blank)
        for target in TARGETS:
            check_cat(row, f"consequence_{target}_text", DIRECTIONS, errors, idx, allow_blank)
    required = ["proposition_boundary", "scope_status", "time_horizon_status", "falsifier_status", "qualification_status"] + [f"consequence_{target}_text" for target in TARGETS]
    missing = sum(1 for _, row in frame.iterrows() for col in required if clean(row.get(col)) == "")
    return errors, {"rows": int(len(frame)), "required_cells": int(len(frame) * len(required)), "missing_required_cells": int(missing)}


def validate_pass_b(frame, reference, allow_blank):
    errors = []
    validate_common(frame, reference, PASS_B_COLUMNS, "pass_b", errors)
    ref = reference.set_index("row_handle", drop=False)
    for idx, row in frame.iterrows():
        handle = clean(row.get("row_handle"))
        if handle not in ref.index:
            continue
        for col in ["recorded_activity", "recorded_active_days", "recorded_counterparty_breadth", "recorded_new_counterparties", "recorded_horizon_days", "evidence_labels"]:
            if clean(row.get(col)) != clean(ref.loc[handle, col]):
                err(errors, "recorded_field_changed", int(idx), col, f"recorded Pass B field changed for {handle}")
        for target in TARGETS:
            label_col = f"alignment_{target}"
            span_col = f"alignment_span_{target}"
            value = clean(row.get(label_col))
            span = clean(row.get(span_col))
            if value == "":
                if not allow_blank:
                    err(errors, "missing_annotation", int(idx), label_col, "missing alignment")
            elif value not in ALIGNMENT:
                err(errors, "invalid_label", int(idx), label_col, value)
            if value != "unclear" and value != "":
                if span == "":
                    err(errors, "missing_exact_span", int(idx), span_col, f"{label_col}={value} requires a span")
                elif span not in clean(row.get("hypothesis_text")):
                    err(errors, "span_not_substring", int(idx), span_col, "alignment span is not an exact substring")
            elif value == "unclear" and span != "":
                err(errors, "unexpected_span", int(idx), span_col, "unclear alignment must leave span blank")
        check_cat(row, "horizon_compatibility", HORIZON_COMPAT, errors, idx, allow_blank)
        present = {x for x in clean(row.get("evidence_labels")).split(";") if x}
        unknown = present - set(EVIDENCE_GROUPS)
        if unknown:
            err(errors, "unknown_evidence_id", int(idx), "evidence_labels", ";".join(sorted(unknown)))
        for group in EVIDENCE_GROUPS:
            col = f"evidence_pointer_{group}"
            value = clean(row.get(col))
            if value == "":
                if not allow_blank:
                    err(errors, "missing_annotation", int(idx), col, "missing evidence-pointer annotation")
            elif value not in POINTER:
                err(errors, "invalid_label", int(idx), col, value)
            elif group in present and value == "not_applicable":
                err(errors, "not_applicable_present_label", int(idx), col, "present evidence ID cannot be not_applicable")
            elif group not in present and value not in {"", "not_applicable"}:
                err(errors, "missing_not_applicable", int(idx), col, "absent evidence ID must be not_applicable")
    required = [f"alignment_{target}" for target in TARGETS] + ["horizon_compatibility"] + [f"evidence_pointer_{group}" for group in EVIDENCE_GROUPS]
    missing = sum(1 for _, row in frame.iterrows() for col in required if clean(row.get(col)) == "")
    return errors, {"rows": int(len(frame)), "required_cells": int(len(frame) * len(required)), "missing_required_cells": int(missing)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--pass-a", required=True)
    parser.add_argument("--pass-b", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-blank", action="store_true")
    args = parser.parse_args()
    package = Path(args.package_dir)
    ref_a = pd.read_csv(package / "PASS_A_TEXT_ONLY_BLIND.csv", dtype=str, keep_default_na=False)
    ref_b = pd.read_csv(package / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv", dtype=str, keep_default_na=False)
    frame_a = pd.read_csv(args.pass_a, dtype=str, keep_default_na=False)
    frame_b = pd.read_csv(args.pass_b, dtype=str, keep_default_na=False)
    errors_a, summary_a = validate_pass_a(frame_a, ref_a, args.allow_blank)
    errors_b, summary_b = validate_pass_b(frame_b, ref_b, args.allow_blank)
    errors = [{"pass": "A", **e} for e in errors_a] + [{"pass": "B", **e} for e in errors_b]
    report = {
        "created_at": utc_now(),
        "status": "PASS" if not errors else "FAIL",
        "allow_blank": bool(args.allow_blank),
        "package_dir": str(package),
        "pass_a": {"path": str(args.pass_a), "sha256": sha256_file(Path(args.pass_a)), **summary_a},
        "pass_b": {"path": str(args.pass_b), "sha256": sha256_file(Path(args.pass_b)), **summary_b},
        "error_count": len(errors),
        "errors": errors[:1000],
        "errors_truncated": len(errors) > 1000,
        "future_outcomes_joined": False,
        "f_delta_joined": False,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "error_count": report["error_count"], "out": str(args.out)}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
