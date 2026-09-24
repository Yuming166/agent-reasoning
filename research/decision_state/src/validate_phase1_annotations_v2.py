#!/usr/bin/env python3
"""Fail-closed validator for the repaired Phase-1 V2 package."""
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
COMMON_POINTER = {"direct_descriptive", "predictive_consistent", "unsupported", "contradicted", "unclear", "not_applicable"}
PLACEBO_POINTER = {"negative_control_failure", "irrelevant", "unclear", "not_applicable"}
PASS_A_COLUMNS = [
    "row_handle", "hypothesis_text", "proposition_boundary", "proposition_span", "proposition_status",
    "scope_status", "scope_span", "time_horizon_status", "time_horizon_span",
    "consequence_activity_text", "consequence_active_days_text", "consequence_counterparty_breadth_text",
    "consequence_new_counterparties_text", "consequence_observability", "falsifier_status", "falsifier_span",
    "falsifier_executability", "qualification_status", "qualification_span", "qualification_substantive", "pass_a_notes",
]
PASS_B_COLUMNS = [
    "row_handle", "hypothesis_text", "recorded_activity", "recorded_active_days", "recorded_counterparty_breadth",
    "recorded_new_counterparties", "recorded_horizon_days", "evidence_labels", "alignment_activity", "alignment_active_days",
    "alignment_counterparty_breadth", "alignment_new_counterparties", "alignment_span_activity", "alignment_span_active_days",
    "alignment_span_counterparty_breadth", "alignment_span_new_counterparties", "horizon_compatibility",
    "evidence_pointer_E_SELF", "evidence_span_E_SELF", "evidence_pointer_E_MARKET", "evidence_span_E_MARKET",
    "evidence_pointer_E_COVERAGE", "evidence_span_E_COVERAGE", "evidence_pointer_E_PLACEBO", "evidence_span_E_PLACEBO",
    "placebo_handling", "pass_b_notes",
]
WALLET_RE = re.compile(r"0x[0-9a-fA-F]{20,}")
LEAK_RE = re.compile(r"(?i)(?:\bdelta\b|\baugust\b|\bjuly\b|\bsplit\b|\blog[_ -]?loss\b|\bmodel\s+(?:loss|performance|output)\b|\bF\s*=)")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def err(errors, kind, row, field, detail):
    errors.append({"type": kind, "row": row, "field": field, "detail": detail})


def load_reference(path: Path, expected: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(frame.columns) != expected:
        raise ValueError(f"reference schema mismatch: {path}")
    return frame


def check_frame(frame: pd.DataFrame, ref: pd.DataFrame, expected: list[str], allow_blank: bool, section: str):
    errors = []
    if list(frame.columns) != expected:
        return [{"type": "schema", "row": None, "field": None, "detail": f"expected exact columns {expected}"}], {"rows": len(frame)}
    if frame["row_handle"].duplicated().any():
        for i in frame.index[frame["row_handle"].duplicated()].tolist():
            err(errors, "duplicate_handle", int(i), "row_handle", clean(frame.loc[i, "row_handle"]))
    if len(frame) != len(ref):
        err(errors, "row_count", None, None, f"expected {len(ref)}, got {len(frame)}")
    if set(frame["row_handle"]) != set(ref["row_handle"]):
        err(errors, "handle_set", None, "row_handle", "submitted handles differ from locked worksheet")
    ref_map = {clean(r.row_handle): r for r in ref.itertuples(index=False)}
    for i, row in frame.iterrows():
        handle = clean(row.get("row_handle"))
        refrow = ref_map.get(handle)
        if refrow is None:
            continue
        if clean(row.get("hypothesis_text")) != clean(getattr(refrow, "hypothesis_text")):
            err(errors, "text_changed", int(i), "hypothesis_text", "displayed source text changed")
        text = clean(row.get("hypothesis_text"))
        if WALLET_RE.search(text) or LEAK_RE.search(text):
            err(errors, "blinding_leak", int(i), "hypothesis_text", "forbidden identifier/outcome term in displayed text")
    return errors, {"rows": len(frame)}


def span_check(errors, i, text, field, value, required):
    if required and value == "":
        err(errors, "missing_span", i, field, "required exact span is blank")
    elif value and value not in text:
        err(errors, "span_not_substring", i, field, "span is not an exact substring")


def validate_pass_a(frame: pd.DataFrame, ref: pd.DataFrame, allow_blank: bool):
    errors, summary = check_frame(frame, ref, PASS_A_COLUMNS, allow_blank, "pass_a")
    if list(frame.columns) != PASS_A_COLUMNS:
        return errors, summary
    allowed = {
        "proposition_boundary": {"atomic", "compound", "none", "unclear"},
        "proposition_status": {"well_formed", "ill_formed", "absent", "unclear"},
        "scope_status": {"explicit", "partial", "absent", "unclear"},
        "time_horizon_status": {"explicit", "implicit", "absent", "unclear"},
        **{f"consequence_{x}_text": {"up", "same", "down", "not_stated", "unclear"} for x in TARGETS},
        "consequence_observability": {"observable", "non_observable", "unclear"},
        "falsifier_status": {"explicit", "implicit", "absent", "unclear"},
        "falsifier_executability": {"executable", "caveat_only", "absent", "unclear"},
        "qualification_status": {"assert", "qualify", "abstain", "unclear"},
        "qualification_substantive": {"non_trivial", "trivial_or_none", "not_applicable", "unclear"},
    }
    span_rules = {
        "proposition_span": ("proposition_boundary", {"atomic", "compound"}),
        "scope_span": ("scope_status", {"explicit", "partial"}),
        "time_horizon_span": ("time_horizon_status", {"explicit", "implicit"}),
        "falsifier_span": ("falsifier_status", {"explicit", "implicit"}),
        "qualification_span": ("qualification_status", {"qualify", "abstain"}),
    }
    for i, row in frame.iterrows():
        text = clean(row.get("hypothesis_text"))
        for field, categories in allowed.items():
            value = clean(row.get(field))
            if value == "":
                if not allow_blank:
                    err(errors, "missing_annotation", int(i), field, "blank")
            elif value not in categories:
                err(errors, "invalid_label", int(i), field, value)
        if allow_blank and all(clean(row.get(x)) == "" for x in PASS_A_COLUMNS[2:]):
            continue
        for span, (status, required) in span_rules.items():
            span_check(errors, int(i), text, span, clean(row.get(span)), clean(row.get(status)) in required)
        boundary, prop = clean(row.get("proposition_boundary")), clean(row.get("proposition_status"))
        if prop == "well_formed" and boundary != "atomic":
            err(errors, "inconsistent_label", int(i), "proposition_status", "well_formed requires atomic boundary")
        if prop == "absent" and boundary not in {"none", "unclear"}:
            err(errors, "inconsistent_label", int(i), "proposition_status", "absent requires none or unclear boundary")
        exe, fs = clean(row.get("falsifier_executability")), clean(row.get("falsifier_status"))
        if exe in {"executable", "caveat_only"} and fs not in {"explicit", "implicit"}:
            err(errors, "inconsistent_label", int(i), "falsifier_executability", "executable/caveat_only requires explicit or implicit status")
        q, qs = clean(row.get("qualification_status")), clean(row.get("qualification_substantive"))
        if q == "assert" and qs == "non_trivial":
            err(errors, "inconsistent_label", int(i), "qualification_substantive", "assert cannot be a non-trivial qualification")
        if q in {"qualify", "abstain"} and qs == "not_applicable":
            err(errors, "inconsistent_label", int(i), "qualification_substantive", "qualify/abstain requires substantive judgment")
    summary["required_annotation_cells"] = len(frame) * (len(PASS_A_COLUMNS) - 2)
    return errors, summary


def validate_pass_b(frame: pd.DataFrame, ref: pd.DataFrame, allow_blank: bool):
    errors, summary = check_frame(frame, ref, PASS_B_COLUMNS, allow_blank, "pass_b")
    if list(frame.columns) != PASS_B_COLUMNS:
        return errors, summary
    align_allowed = {"entailed", "unsupported", "contradicted", "unclear"}
    horizon_allowed = {"compatible", "incompatible", "unclear"}
    ref_map = {clean(r.row_handle): r for r in ref.itertuples(index=False)}
    for i, row in frame.iterrows():
        refrow = ref_map.get(clean(row.get("row_handle")))
        if refrow is not None:
            for field in ["recorded_activity", "recorded_active_days", "recorded_counterparty_breadth", "recorded_new_counterparties", "recorded_horizon_days", "evidence_labels"]:
                if clean(row.get(field)) != clean(getattr(refrow, field)):
                    err(errors, "recorded_field_changed", int(i), field, "locked structured field changed")
        if allow_blank and all(clean(row.get(x)) == "" for x in PASS_B_COLUMNS[8:]):
            continue
        for target in TARGETS:
            value = clean(row.get(f"alignment_{target}"))
            span = clean(row.get(f"alignment_span_{target}"))
            if value == "":
                if not allow_blank: err(errors, "missing_annotation", int(i), f"alignment_{target}", "blank")
            elif value not in align_allowed:
                err(errors, "invalid_label", int(i), f"alignment_{target}", value)
            if value in {"entailed", "unsupported", "contradicted"}:
                span_check(errors, int(i), clean(row.get("hypothesis_text")), f"alignment_span_{target}", span, True)
            elif span:
                err(errors, "unexpected_span", int(i), f"alignment_span_{target}", "unclear/blank alignment cannot have span")
        hv = clean(row.get("horizon_compatibility"))
        if hv == "":
            if not allow_blank: err(errors, "missing_annotation", int(i), "horizon_compatibility", "blank")
        elif hv not in horizon_allowed:
            err(errors, "invalid_label", int(i), "horizon_compatibility", hv)
        present = {x for x in clean(row.get("evidence_labels")).split(";") if x}
        if not present.issubset(set(EVIDENCE_GROUPS)):
            err(errors, "unknown_evidence_id", int(i), "evidence_labels", ";".join(sorted(present - set(EVIDENCE_GROUPS))))
        for group in EVIDENCE_GROUPS:
            field = f"evidence_pointer_{group}"
            span_field = f"evidence_span_{group}"
            value, span = clean(row.get(field)), clean(row.get(span_field))
            if group == "E_PLACEBO":
                allowed = PLACEBO_POINTER
                requiring_span = {"negative_control_failure", "irrelevant"}
            else:
                allowed = COMMON_POINTER
                requiring_span = {"direct_descriptive", "predictive_consistent", "unsupported", "contradicted"}
            if value == "":
                if not allow_blank: err(errors, "missing_annotation", int(i), field, "blank")
            elif value not in allowed:
                err(errors, "invalid_label", int(i), field, value)
            elif group in present and value == "not_applicable":
                err(errors, "not_applicable_present_label", int(i), field, "present evidence cannot be not_applicable")
            elif group not in present and value != "not_applicable":
                err(errors, "missing_not_applicable", int(i), field, "absent evidence must be not_applicable")
            if value in requiring_span:
                span_check(errors, int(i), clean(row.get("hypothesis_text")), span_field, span, True)
            elif span:
                err(errors, "unexpected_span", int(i), span_field, "no span allowed for this evidence label")
        placebo = clean(row.get("placebo_handling"))
        allowed_placebo = {"negative_control_failure", "irrelevant", "no_placebo_evidence", "unclear"}
        if placebo == "":
            if not allow_blank: err(errors, "missing_annotation", int(i), "placebo_handling", "blank")
        elif placebo not in allowed_placebo:
            err(errors, "invalid_label", int(i), "placebo_handling", placebo)
        elif "E_PLACEBO" in present and placebo == "no_placebo_evidence":
            err(errors, "inconsistent_label", int(i), "placebo_handling", "E_PLACEBO is present")
        elif "E_PLACEBO" not in present and placebo != "no_placebo_evidence":
            err(errors, "inconsistent_label", int(i), "placebo_handling", "E_PLACEBO is absent")
    summary["required_annotation_cells"] = len(frame) * (len(PASS_B_COLUMNS) - 8)
    return errors, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--pass-a", required=True)
    parser.add_argument("--pass-b", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-blank", action="store_true")
    args = parser.parse_args()
    package = Path(args.package_dir)
    ref_a = load_reference(package / "PASS_A_TEXT_ONLY_BLIND.csv", PASS_A_COLUMNS)
    ref_b = load_reference(package / "PASS_B_STRUCTURED_REVIEW_LOCKED.csv", PASS_B_COLUMNS)
    frame_a = pd.read_csv(args.pass_a, dtype=str, keep_default_na=False)
    frame_b = pd.read_csv(args.pass_b, dtype=str, keep_default_na=False)
    errors_a, summary_a = validate_pass_a(frame_a, ref_a, args.allow_blank)
    errors_b, summary_b = validate_pass_b(frame_b, ref_b, args.allow_blank)
    errors = [{"pass": "A", **e} for e in errors_a] + [{"pass": "B", **e} for e in errors_b]
    report = {
        "created_at": utc_now(), "status": "PASS" if not errors else "FAIL", "allow_blank": bool(args.allow_blank),
        "protocol_version": "phase1_annotation_gate_v2_dev", "package_dir": str(package),
        "pass_a": {"path": str(args.pass_a), "sha256": sha256_file(Path(args.pass_a)), **summary_a},
        "pass_b": {"path": str(args.pass_b), "sha256": sha256_file(Path(args.pass_b)), **summary_b},
        "error_count": len(errors), "errors": errors[:1000], "errors_truncated": len(errors) > 1000,
        "future_outcomes_joined": False, "f_delta_joined": False, "August_test_joined": False,
    }
    out = Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "error_count": report["error_count"], "out": str(out)}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
