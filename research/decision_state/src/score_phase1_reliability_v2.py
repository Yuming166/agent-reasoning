#!/usr/bin/env python3
"""Score Gate 1A for the repaired Phase-1 V2 package.

Primary unit is the case (three rows per case). Row-level estimates are shown,
and whole-case bootstrap intervals are primary uncertainty diagnostics. Kappa
with a zero chance-correction denominator is explicitly NOT_ESTIMABLE.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
SEED = 20260921
THRESHOLDS = {
    "categorical_field_exact_min": 0.70,
    "categorical_field_kappa_min": 0.40,
    "span_exact_min": 0.80,
    "span_token_f1_min": 0.80,
    "missing_rate_max": 0.05,
    "unclear_rate_max": 0.20,
}
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
CATEGORICAL_FIELDS = [
    ("pass_a", "proposition_boundary", ["atomic", "compound", "none", "unclear"]),
    ("pass_a", "proposition_status", ["well_formed", "ill_formed", "absent", "unclear"]),
    ("pass_a", "scope_status", ["explicit", "partial", "absent", "unclear"]),
    ("pass_a", "time_horizon_status", ["explicit", "implicit", "absent", "unclear"]),
    *( ("pass_a", f"consequence_{target}_text", ["up", "same", "down", "not_stated", "unclear"]) for target in TARGETS ),
    ("pass_a", "consequence_observability", ["observable", "non_observable", "unclear"]),
    ("pass_a", "falsifier_status", ["explicit", "implicit", "absent", "unclear"]),
    ("pass_a", "falsifier_executability", ["executable", "caveat_only", "absent", "unclear"]),
    ("pass_a", "qualification_status", ["assert", "qualify", "abstain", "unclear"]),
    ("pass_a", "qualification_substantive", ["non_trivial", "trivial_or_none", "not_applicable", "unclear"]),
    *( ("pass_b", f"alignment_{target}", ["entailed", "unsupported", "contradicted", "unclear"]) for target in TARGETS ),
    ("pass_b", "horizon_compatibility", ["compatible", "incompatible", "unclear"]),
    *( ("pass_b", f"evidence_pointer_{group}", ["direct_descriptive", "predictive_consistent", "unsupported", "contradicted", "unclear", "not_applicable"]) for group in EVIDENCE_GROUPS if group != "E_PLACEBO" ),
    ("pass_b", "evidence_pointer_E_PLACEBO", ["negative_control_failure", "irrelevant", "unclear", "not_applicable"]),
    ("pass_b", "placebo_handling", ["negative_control_failure", "irrelevant", "no_placebo_evidence", "unclear"]),
]
SPAN_FIELDS = [
    ("pass_a", "proposition_span", "proposition_boundary", {"atomic", "compound"}),
    ("pass_a", "scope_span", "scope_status", {"explicit", "partial"}),
    ("pass_a", "time_horizon_span", "time_horizon_status", {"explicit", "implicit"}),
    ("pass_a", "falsifier_span", "falsifier_status", {"explicit", "implicit"}),
    ("pass_a", "qualification_span", "qualification_status", {"qualify", "abstain"}),
    *( ("pass_b", f"alignment_span_{target}", f"alignment_{target}", {"entailed", "unsupported", "contradicted"}) for target in TARGETS ),
    *( ("pass_b", f"evidence_span_{group}", f"evidence_pointer_{group}", {"direct_descriptive", "predictive_consistent", "unsupported", "contradicted"}) for group in ["E_SELF", "E_MARKET", "E_COVERAGE"] ),
    ("pass_b", "evidence_span_E_PLACEBO", "evidence_pointer_E_PLACEBO", {"negative_control_failure", "irrelevant"}),
]


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(v):
    if pd.isna(v): return ""
    return str(v).strip()


def norm(v): return " ".join(clean(v).split()).casefold()


def token_f1(a, b):
    aa, bb = norm(a).split(), norm(b).split()
    if not aa and not bb: return 1.0
    if not aa or not bb: return 0.0
    ca, cb = Counter(aa), Counter(bb)
    overlap = sum((ca & cb).values())
    if overlap == 0: return 0.0
    p, r = overlap / len(aa), overlap / len(bb)
    return 2 * p * r / (p + r)


def kappa(a, b, categories):
    if not a: return "NOT_ESTIMABLE"
    idx = {x: i for i, x in enumerate(categories)}
    if any(x not in idx or y not in idx for x, y in zip(a, b)): return "NOT_ESTIMABLE"
    table = np.zeros((len(categories), len(categories)), dtype=float)
    for x, y in zip(a, b): table[idx[x], idx[y]] += 1
    po = float(np.trace(table) / len(a))
    pe = float(np.dot(table.sum(1) / len(a), table.sum(0) / len(a)))
    if math.isclose(1.0 - pe, 0.0): return "NOT_ESTIMABLE"
    return float((po - pe) / (1.0 - pe))


def ac1(a, b, categories):
    if not a: return "NOT_ESTIMABLE"
    idx = {x: i for i, x in enumerate(categories)}
    if any(x not in idx or y not in idx for x, y in zip(a, b)): return "NOT_ESTIMABLE"
    counts = np.zeros(len(categories), dtype=float)
    agree = 0
    for x, y in zip(a, b):
        counts[idx[x]] += 1; counts[idx[y]] += 1; agree += int(x == y)
    po = agree / len(a)
    p = counts / (2 * len(a))
    pe = float(np.sum(p * (1 - p)) / (len(categories) - 1)) if len(categories) > 1 else 0.0
    if math.isclose(1.0 - pe, 0.0): return "NOT_ESTIMABLE"
    return float((po - pe) / (1 - pe))


def bootstrap_case_exact(left, right, field, row_to_case, reps):
    cases = sorted({row_to_case[h] for h in left["row_handle"]})
    if not cases: return {"case_bootstrap_reps": 0, "case_bootstrap_ci95": None}
    case_rows = {case: [] for case in cases}
    for i, h in enumerate(left["row_handle"]): case_rows[row_to_case[h]].append(i)
    rng = np.random.default_rng(SEED)
    values = []
    for _ in range(reps):
        sampled = rng.choice(cases, size=len(cases), replace=True)
        pairs = [i for case in sampled for i in case_rows[case]]
        if not pairs: continue
        values.append(float(np.mean([clean(left.iloc[i][field]) == clean(right.iloc[i][field]) for i in pairs])))
    return {"case_bootstrap_reps": len(values), "case_bootstrap_ci95": [float(np.quantile(values, .025)), float(np.quantile(values, .975))] if values else None}


def field_stats(left, right, field, categories, row_to_case, reps):
    a, b = [clean(x) for x in left[field]], [clean(x) for x in right[field]]
    valid = [(x != "" and y != "") for x, y in zip(a, b)]
    av, bv = [x for x, ok in zip(a, valid) if ok], [y for y, ok in zip(b, valid) if ok]
    unexpected = sorted((set(av) | set(bv)) - set(categories))
    out = {
        "field": field, "n_rows": len(a), "n_valid_pairs": len(av),
        "missing_rate": float(np.mean([not x for x in valid])) if valid else None,
        "exact_agreement_valid": float(np.mean([x == y for x, y in zip(av, bv)])) if av else None,
        "exact_agreement_all_rows": float(np.mean([x == y for x, y in zip(a, b)])) if a else None,
        "cohen_kappa": kappa(av, bv, categories) if not unexpected else "NOT_ESTIMABLE",
        "gwet_ac1": ac1(av, bv, categories) if not unexpected else "NOT_ESTIMABLE",
        "unclear_rate_pooled_valid_assignments": float(np.mean([x == "unclear" for x in av + bv])) if av else None,
        "unexpected_categories": unexpected,
    }
    out.update(bootstrap_case_exact(left, right, field, row_to_case, reps))
    return out


def span_stats(left, right, span, status, required_statuses):
    required = [(clean(x) in required_statuses) or (clean(y) in required_statuses) for x, y in zip(left[status], right[status])]
    valid = [req and clean(x) != "" and clean(y) != "" for req, x, y in zip(required, left[span], right[span])]
    exact = [norm(x) == norm(y) for x, y, ok in zip(left[span], right[span], valid) if ok]
    f1 = [token_f1(x, y) for x, y, ok in zip(left[span], right[span], valid) if ok]
    return {
        "field": span, "status_field": status, "n_required": int(sum(required)), "n_valid_pairs": int(sum(valid)),
        "missing_rate_required": float(np.mean([req and not ok for req, ok in zip(required, valid)])) if any(required) else None,
        "exact_agreement_valid": float(np.mean(exact)) if exact else None,
        "token_f1_mean_valid": float(np.mean(f1)) if f1 else None,
        "token_f1_median_valid": float(np.median(f1)) if f1 else None,
    }


def load(path: Path, expected, roster):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(frame.columns) != expected: raise ValueError(f"{path}: exact schema mismatch")
    if frame["row_handle"].duplicated().any(): raise ValueError(f"{path}: duplicate handles")
    if not roster.issubset(set(frame["row_handle"])): raise ValueError(f"{path}: missing double-code handles")
    frame = frame[frame["row_handle"].isin(roster)].sort_values("row_handle").reset_index(drop=True)
    if set(frame["row_handle"]) != roster: raise ValueError(f"{path}: roster mismatch")
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package-dir", required=True)
    ap.add_argument("--pass-a-coder-a", required=True); ap.add_argument("--pass-a-coder-b", required=True)
    ap.add_argument("--pass-b-coder-a", required=True); ap.add_argument("--pass-b-coder-b", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--bootstrap-reps", type=int, default=2000)
    args = ap.parse_args()
    package = Path(args.package_dir)
    internal = json.loads((package / "internal/SAMPLE_ROW_MAP.json").read_text())
    row_to_case = {str(x["row_handle"]): str(x["case_id"]) for x in internal}
    roster = {str(x["row_handle"]) for x in internal if bool(x["double_code_case"])}
    cases = sorted({row_to_case[h] for h in roster})
    if len(cases) != 20: raise ValueError(f"expected 20 double-code cases, found {len(cases)}")
    pa = [load(Path(p), PASS_A_COLUMNS, roster) for p in [args.pass_a_coder_a, args.pass_a_coder_b]]
    pb = [load(Path(p), PASS_B_COLUMNS, roster) for p in [args.pass_b_coder_a, args.pass_b_coder_b]]
    categorical = []
    for section, field, categories in CATEGORICAL_FIELDS:
        left, right = pa if section == "pass_a" else pb
        x = field_stats(left, right, field, categories, row_to_case, args.bootstrap_reps); x.update({"section": section, "categories": categories}); categorical.append(x)
    spans = []
    for section, span, status, required in SPAN_FIELDS:
        left, right = pa if section == "pass_a" else pb
        x = span_stats(left, right, span, status, required); x.update({"section": section}); spans.append(x)
    valid_cat = [x for x in categorical if x["n_valid_pairs"]]
    valid_span = [x for x in spans if x["n_valid_pairs"]]
    failures = []
    if not valid_cat and not valid_span:
        status = "RELIABILITY_NOT_YET_ASSESSABLE"
    else:
        for x in categorical:
            if x["n_valid_pairs"] == 0: failures.append({"type": "no_valid_pairs", "field": x["field"]}); continue
            if x["missing_rate"] > THRESHOLDS["missing_rate_max"]: failures.append({"type": "missing_rate", "field": x["field"], "value": x["missing_rate"]})
            if x["unexpected_categories"]: failures.append({"type": "unexpected_categories", "field": x["field"], "value": x["unexpected_categories"]})
            if x["exact_agreement_valid"] < THRESHOLDS["categorical_field_exact_min"]: failures.append({"type": "field_exact", "field": x["field"], "value": x["exact_agreement_valid"]})
            if x["cohen_kappa"] == "NOT_ESTIMABLE" or x["cohen_kappa"] < THRESHOLDS["categorical_field_kappa_min"]: failures.append({"type": "field_kappa", "field": x["field"], "value": x["cohen_kappa"]})
            if x["unclear_rate_pooled_valid_assignments"] is not None and x["unclear_rate_pooled_valid_assignments"] > THRESHOLDS["unclear_rate_max"]: failures.append({"type": "unclear_rate", "field": x["field"], "value": x["unclear_rate_pooled_valid_assignments"]})
        for x in spans:
            if x["n_required"] and (x["missing_rate_required"] is None or x["missing_rate_required"] > THRESHOLDS["missing_rate_max"]): failures.append({"type": "span_missing_rate", "field": x["field"], "value": x["missing_rate_required"]})
            if x["n_required"] and (x["exact_agreement_valid"] is None or x["exact_agreement_valid"] < THRESHOLDS["span_exact_min"]): failures.append({"type": "span_exact", "field": x["field"], "value": x["exact_agreement_valid"]})
            if x["n_required"] and (x["token_f1_mean_valid"] is None or x["token_f1_mean_valid"] < THRESHOLDS["span_token_f1_min"]): failures.append({"type": "span_token_f1", "field": x["field"], "value": x["token_f1_mean_valid"]})
        status = "RELIABILITY_FAIL" if failures else "RELIABILITY_PASS"
    report = {
        "created_at": utc_now(), "status": status, "protocol_version": "phase1_annotation_gate_v2_dev",
        "package_dir": str(package), "bootstrap_reps": args.bootstrap_reps, "seed": SEED,
        "double_code_case_count": len(cases), "double_code_row_count": len(roster), "double_code_cases": cases,
        "primary_uncertainty_unit": "case", "row_level_agreement_descriptive_only": True,
        "undefined_kappa_policy": "NOT_ESTIMABLE", "thresholds": THRESHOLDS,
        "categorical": categorical, "spans": spans, "failures": failures,
        "future_outcomes_joined": False, "f_delta_joined": False, "August_test_joined": False, "adjudication_included": False,
    }
    out = Path(args.out); out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    pd.DataFrame(categorical + spans).to_csv(out.with_suffix(".csv"), index=False)
    print(json.dumps({"status": status, "double_code_cases": len(cases), "double_code_rows": len(roster), "out": str(out)}, ensure_ascii=False))
    return 0 if status in {"RELIABILITY_PASS", "RELIABILITY_NOT_YET_ASSESSABLE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
