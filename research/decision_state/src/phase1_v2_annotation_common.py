"""Shared fail-closed validation helpers for the frozen Phase-1 V2 protocol.

This module contains operational validation only. It does not read future
outcomes, prediction scores, or Phase 2/3 artifacts, and it does not change the
frozen V2 schema.
"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable

TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
PASS_A_ALLOWED = {
    "proposition_boundary": {"atomic", "compound", "none", "unclear"},
    "proposition_status": {"well_formed", "ill_formed", "absent", "unclear"},
    "scope_status": {"explicit", "partial", "absent", "unclear"},
    "time_horizon_status": {"explicit", "implicit", "absent", "unclear"},
    **{f"consequence_{target}_text": {"up", "same", "down", "not_stated", "unclear"} for target in TARGETS},
    "consequence_observability": {"observable", "non_observable", "unclear"},
    "falsifier_status": {"explicit", "implicit", "absent", "unclear"},
    "falsifier_executability": {"executable", "caveat_only", "absent", "unclear"},
    "qualification_status": {"assert", "qualify", "abstain", "unclear"},
    "qualification_substantive": {"non_trivial", "trivial_or_none", "not_applicable", "unclear"},
}
ALIGNMENT_ALLOWED = {"entailed", "unsupported", "contradicted", "unclear"}
HORIZON_ALLOWED = {"compatible", "incompatible", "unclear"}
POINTER_ALLOWED = {"direct_descriptive", "predictive_consistent", "unsupported", "contradicted", "unclear", "not_applicable"}
PLACEBO_POINTER_ALLOWED = {"negative_control_failure", "irrelevant", "unclear", "not_applicable"}
PLACEBO_HANDLING_ALLOWED = {"negative_control_failure", "irrelevant", "no_placebo_evidence", "unclear"}
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")
METADATA_RE = re.compile(
    r"(?i)(?:\bcase[_ -]?id\b|\banchor[_ -]?wallet\b|\bwallet\b|\bcutoff\b|\bsplit\b|\baugust\b|\bjuly\b|\bjune\b|\bdelta\b|\blog[_ -]?loss\b|\bprobability\b|\bconfidence\b|\bmodel\s+(?:loss|score|performance)\b|\boutcome\b|\bprediction\s+score\b)"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean(value) -> str:
    return "" if value is None else str(value).strip()


def read_csv_exact(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing CSV header")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    return fieldnames, rows


def _err(errors, kind: str, row: int | None, field: str | None, detail: str):
    errors.append({"type": kind, "row": row, "field": field, "detail": detail})


def _check_exact_span(errors, row_index: int, text: str, field: str, value: str, required: bool):
    if required and not value:
        _err(errors, "missing_exact_span", row_index, field, "required span is blank")
    elif value and value not in text:
        _err(errors, "span_not_substring", row_index, field, "span is not an exact contiguous substring")


def _check_no_metadata(errors, row_index: int, row: dict[str, str], fieldnames: list[str]):
    for field in fieldnames[2:]:
        value = clean(row.get(field))
        if not value:
            continue
        if WALLET_RE.search(value) or METADATA_RE.search(value):
            _err(errors, "metadata_or_identity_leak", row_index, field, "annotation contains forbidden metadata/identity term")


def _check_pass_a_row(errors, row_index: int, row: dict[str, str], allow_blank: bool):
    text = clean(row.get("hypothesis_text"))
    if WALLET_RE.search(text):
        _err(errors, "wallet_in_text", row_index, "hypothesis_text", "wallet identifier is not allowed in displayed text")
    if allow_blank and all(not clean(row.get(field)) for field in list(PASS_A_ALLOWED) + ["proposition_span", "scope_span", "time_horizon_span", "falsifier_span", "qualification_span"]):
        return
    for field, allowed in PASS_A_ALLOWED.items():
        value = clean(row.get(field))
        if not value:
            if not allow_blank:
                _err(errors, "missing_annotation", row_index, field, "required annotation is blank")
        elif value not in allowed:
            _err(errors, "invalid_label", row_index, field, value)

    span_rules = {
        "proposition_span": ("proposition_boundary", {"atomic", "compound"}),
        "scope_span": ("scope_status", {"explicit", "partial"}),
        "time_horizon_span": ("time_horizon_status", {"explicit", "implicit"}),
        "falsifier_span": ("falsifier_status", {"explicit", "implicit"}),
        "qualification_span": ("qualification_status", {"qualify", "abstain"}),
    }
    for span, (status, required_values) in span_rules.items():
        _check_exact_span(errors, row_index, text, span, clean(row.get(span)), clean(row.get(status)) in required_values)
        if clean(row.get(status)) not in required_values and clean(row.get(span)):
            _err(errors, "unexpected_span", row_index, span, f"span is not allowed for status {clean(row.get(status))}")

    boundary = clean(row.get("proposition_boundary"))
    proposition = clean(row.get("proposition_status"))
    if proposition == "well_formed" and boundary != "atomic":
        _err(errors, "inconsistent_label", row_index, "proposition_status", "well_formed requires atomic boundary")
    if proposition == "absent" and boundary not in {"none", "unclear"}:
        _err(errors, "inconsistent_label", row_index, "proposition_status", "absent requires none or unclear boundary")

    falsifier_status = clean(row.get("falsifier_status"))
    falsifier_exec = clean(row.get("falsifier_executability"))
    if falsifier_exec in {"executable", "caveat_only"} and falsifier_status not in {"explicit", "implicit"}:
        _err(errors, "inconsistent_label", row_index, "falsifier_executability", "executable/caveat_only requires explicit or implicit falsifier")
    if falsifier_exec == "executable" and clean(row.get("time_horizon_status")) not in {"explicit", "implicit"}:
        _err(errors, "inconsistent_label", row_index, "falsifier_executability", "executable falsifier requires an explicit/implicit operational horizon")

    qualification_status = clean(row.get("qualification_status"))
    qualification_substantive = clean(row.get("qualification_substantive"))
    if qualification_status == "assert" and qualification_substantive == "non_trivial":
        _err(errors, "inconsistent_label", row_index, "qualification_substantive", "assert cannot be a non-trivial qualification")
    if qualification_status in {"qualify", "abstain"} and qualification_substantive == "not_applicable":
        _err(errors, "inconsistent_label", row_index, "qualification_substantive", "qualify/abstain requires substantive judgment")

    _check_no_metadata(errors, row_index, row, list(row))


def validate_pass_a_submission(expected_path: Path, submission_path: Path, allow_blank: bool = False) -> dict:
    expected_columns, expected_rows = read_csv_exact(expected_path)
    actual_columns, actual_rows = read_csv_exact(submission_path)
    errors: list[dict] = []
    if actual_columns != expected_columns:
        _err(errors, "schema", None, None, "submission columns do not exactly match frozen assignment schema")
        return {"status": "FAIL", "errors": errors, "rows": len(actual_rows), "sha256": sha256_file(submission_path)}
    expected_by_handle = {clean(row.get("row_handle")): row for row in expected_rows}
    actual_handles = [clean(row.get("row_handle")) for row in actual_rows]
    if len(actual_handles) != len(set(actual_handles)):
        _err(errors, "duplicate_handle", None, "row_handle", "duplicate row handle")
    if set(actual_handles) != set(expected_by_handle):
        _err(errors, "roster", None, "row_handle", "submission handle set differs from assignment")
    if len(actual_rows) != len(expected_rows):
        _err(errors, "row_count", None, None, f"expected {len(expected_rows)} rows, got {len(actual_rows)}")
    for i, row in enumerate(actual_rows):
        handle = clean(row.get("row_handle"))
        expected = expected_by_handle.get(handle)
        if expected is None:
            continue
        if clean(row.get("hypothesis_text")) != clean(expected.get("hypothesis_text")):
            _err(errors, "text_changed", i, "hypothesis_text", "hypothesis text differs from frozen assignment")
        _check_pass_a_row(errors, i, row, allow_blank)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors[:1000],
        "errors_truncated": len(errors) > 1000,
        "rows": len(actual_rows),
        "expected_rows": len(expected_rows),
        "sha256": sha256_file(submission_path),
        "expected_assignment_sha256": sha256_file(expected_path),
        "allow_blank": allow_blank,
    }


def _check_pass_b_row(errors, row_index: int, row: dict[str, str], expected: dict[str, str], allow_blank: bool):
    text = clean(row.get("hypothesis_text"))
    if WALLET_RE.search(text):
        _err(errors, "wallet_in_text", row_index, "hypothesis_text", "wallet identifier is not allowed in displayed text")
    for field in ["recorded_activity", "recorded_active_days", "recorded_counterparty_breadth", "recorded_new_counterparties", "recorded_horizon_days", "evidence_labels"]:
        if clean(row.get(field)) != clean(expected.get(field)):
            _err(errors, "recorded_field_changed", row_index, field, "locked structured field was changed")

    annotation_fields = [
        *(f"alignment_{target}" for target in TARGETS),
        *(f"alignment_span_{target}" for target in TARGETS),
        "horizon_compatibility",
        *(f"evidence_pointer_{group}" for group in EVIDENCE_GROUPS),
        *(f"evidence_span_{group}" for group in EVIDENCE_GROUPS),
        "placebo_handling",
    ]
    if allow_blank and all(not clean(row.get(field)) for field in annotation_fields):
        return
    for target in TARGETS:
        label_field = f"alignment_{target}"
        span_field = f"alignment_span_{target}"
        label = clean(row.get(label_field)); span = clean(row.get(span_field))
        if not label:
            _err(errors, "missing_annotation", row_index, label_field, "required annotation is blank")
        elif label not in ALIGNMENT_ALLOWED:
            _err(errors, "invalid_label", row_index, label_field, label)
        if label in {"entailed", "unsupported", "contradicted"}:
            _check_exact_span(errors, row_index, text, span_field, span, True)
        elif span:
            _err(errors, "unexpected_span", row_index, span_field, "span requires a non-unclear alignment label")

    horizon = clean(row.get("horizon_compatibility"))
    if not horizon:
        _err(errors, "missing_annotation", row_index, "horizon_compatibility", "required annotation is blank")
    elif horizon not in HORIZON_ALLOWED:
        _err(errors, "invalid_label", row_index, "horizon_compatibility", horizon)

    present = {x for x in clean(row.get("evidence_labels")).split(";") if x}
    if not present.issubset(set(EVIDENCE_GROUPS)):
        _err(errors, "unknown_evidence_id", row_index, "evidence_labels", ";".join(sorted(present - set(EVIDENCE_GROUPS))))
    for group in EVIDENCE_GROUPS:
        label_field = f"evidence_pointer_{group}"
        span_field = f"evidence_span_{group}"
        label = clean(row.get(label_field)); span = clean(row.get(span_field))
        if group == "E_PLACEBO":
            allowed = PLACEBO_POINTER_ALLOWED
            requiring_span = {"negative_control_failure", "irrelevant"}
        else:
            allowed = POINTER_ALLOWED
            requiring_span = {"direct_descriptive", "predictive_consistent", "unsupported", "contradicted"}
        if not label:
            _err(errors, "missing_annotation", row_index, label_field, "required annotation is blank")
        elif label not in allowed:
            _err(errors, "invalid_label", row_index, label_field, label)
        elif group in present and label == "not_applicable":
            _err(errors, "not_applicable_present_label", row_index, label_field, "present evidence cannot be not_applicable")
        elif group not in present and label != "not_applicable":
            _err(errors, "missing_not_applicable", row_index, label_field, "absent evidence must be not_applicable")
        if label in requiring_span:
            _check_exact_span(errors, row_index, text, span_field, span, True)
        elif span:
            _err(errors, "unexpected_span", row_index, span_field, "span is not allowed for this evidence label")

    placebo = clean(row.get("placebo_handling"))
    if not placebo:
        _err(errors, "missing_annotation", row_index, "placebo_handling", "required annotation is blank")
    elif placebo not in PLACEBO_HANDLING_ALLOWED:
        _err(errors, "invalid_label", row_index, "placebo_handling", placebo)
    elif "E_PLACEBO" in present and placebo == "no_placebo_evidence":
        _err(errors, "inconsistent_label", row_index, "placebo_handling", "E_PLACEBO is present")
    elif "E_PLACEBO" not in present and placebo != "no_placebo_evidence":
        _err(errors, "inconsistent_label", row_index, "placebo_handling", "E_PLACEBO is absent")
    _check_no_metadata(errors, row_index, row, list(row))


def validate_pass_b_submission(expected_path: Path, submission_path: Path, allow_blank: bool = False) -> dict:
    expected_columns, expected_rows = read_csv_exact(expected_path)
    actual_columns, actual_rows = read_csv_exact(submission_path)
    errors: list[dict] = []
    if actual_columns != expected_columns:
        _err(errors, "schema", None, None, "submission columns do not exactly match frozen Pass-B assignment schema")
        return {"status": "FAIL", "errors": errors, "rows": len(actual_rows), "sha256": sha256_file(submission_path)}
    expected_by_handle = {clean(row.get("row_handle")): row for row in expected_rows}
    actual_handles = [clean(row.get("row_handle")) for row in actual_rows]
    if len(actual_handles) != len(set(actual_handles)):
        _err(errors, "duplicate_handle", None, "row_handle", "duplicate row handle")
    if set(actual_handles) != set(expected_by_handle):
        _err(errors, "roster", None, "row_handle", "submission handle set differs from assignment")
    if len(actual_rows) != len(expected_rows):
        _err(errors, "row_count", None, None, f"expected {len(expected_rows)} rows, got {len(actual_rows)}")
    for i, row in enumerate(actual_rows):
        handle = clean(row.get("row_handle")); expected = expected_by_handle.get(handle)
        if expected is None: continue
        if clean(row.get("hypothesis_text")) != clean(expected.get("hypothesis_text")):
            _err(errors, "text_changed", i, "hypothesis_text", "hypothesis text differs from frozen assignment")
        _check_pass_b_row(errors, i, row, expected, allow_blank)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors[:1000],
        "errors_truncated": len(errors) > 1000,
        "rows": len(actual_rows),
        "expected_rows": len(expected_rows),
        "sha256": sha256_file(submission_path),
        "expected_assignment_sha256": sha256_file(expected_path),
        "allow_blank": allow_blank,
    }
