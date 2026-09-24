#!/usr/bin/env python3
"""Score the Phase-1 annotation gate on the fixed double-code roster.

This scorer is outcome-blind. It uses only coder sheets, the locked internal
row map, and the declared label spaces. It reports field-level exact agreement,
nominal Cohen kappa, Gwet AC1, missingness, unclear rates, and exact/token span
agreement. Whole-case bootstrap CIs are used for categorical exact agreement.
No adjudication is included in the pre-adjudication gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
SEED = 20260922
THRESHOLDS = {
    "categorical_field_exact_min": 0.70,
    "categorical_field_kappa_min": 0.40,
    "pooled_categorical_exact_min": 0.80,
    "span_exact_min": 0.80,
    "span_token_f1_min": 0.80,
    "missing_rate_max": 0.05,
    "unclear_rate_max": 0.20,
}

CATEGORICAL_FIELDS = [
    ("pass_a", "proposition_boundary", ["atomic", "compound", "none", "unclear"]),
    ("pass_a", "scope_status", ["explicit", "partial", "absent", "unclear"]),
    ("pass_a", "time_horizon_status", ["explicit", "implicit", "absent", "unclear"]),
    ("pass_a", "consequence_activity_text", ["up", "same", "down", "not_stated", "unclear"]),
    ("pass_a", "consequence_active_days_text", ["up", "same", "down", "not_stated", "unclear"]),
    ("pass_a", "consequence_counterparty_breadth_text", ["up", "same", "down", "not_stated", "unclear"]),
    ("pass_a", "consequence_new_counterparties_text", ["up", "same", "down", "not_stated", "unclear"]),
    ("pass_a", "falsifier_status", ["explicit", "implicit", "absent", "unclear"]),
    ("pass_a", "qualification_status", ["assert", "qualify", "abstain", "unclear"]),
    *( ("pass_b", f"alignment_{target}", ["entailed", "unsupported", "contradicted", "unclear"]) for target in TARGETS ),
    ("pass_b", "horizon_compatibility", ["compatible", "incompatible", "unclear"]),
    *( ("pass_b", f"evidence_pointer_{group}", ["supported", "unsupported", "unclear", "not_applicable"]) for group in EVIDENCE_GROUPS ),
]
SPAN_FIELDS = [
    ("pass_a", "proposition_span", "proposition_boundary", {"atomic", "compound"}),
    ("pass_a", "scope_span", "scope_status", {"explicit", "partial"}),
    ("pass_a", "time_horizon_span", "time_horizon_status", {"explicit", "implicit"}),
    ("pass_a", "falsifier_span", "falsifier_status", {"explicit", "implicit"}),
    ("pass_a", "qualification_span", "qualification_status", {"qualify", "abstain"}),
    *( ("pass_b", f"alignment_span_{target}", f"alignment_{target}", {"entailed", "unsupported", "contradicted"}) for target in TARGETS ),
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_span(value: str) -> str:
    return " ".join(clean(value).split()).casefold()


def token_f1(a: str, b: str) -> float | None:
    aa = normalize_span(a).split()
    bb = normalize_span(b).split()
    if not aa and not bb:
        return 1.0
    if not aa or not bb:
        return 0.0
    # Use multiset overlap so repeated words do not inflate overlap.
    from collections import Counter
    ca, cb = Counter(aa), Counter(bb)
    overlap = sum((ca & cb).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(aa)
    recall = overlap / len(bb)
    return 2 * precision * recall / (precision + recall)


def cohen_kappa(a: list[str], b: list[str], categories: list[str]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    index = {cat: i for i, cat in enumerate(categories)}
    table = np.zeros((len(categories), len(categories)), dtype=float)
    for x, y in zip(a, b):
        if x not in index or y not in index:
            return None
        table[index[x], index[y]] += 1
    po = float(np.trace(table) / n)
    row = table.sum(axis=1) / n
    col = table.sum(axis=0) / n
    pe = float(np.dot(row, col))
    if math.isclose(1.0 - pe, 0.0):
        return 1.0 if math.isclose(po, 1.0) else 0.0
    return float((po - pe) / (1.0 - pe))


def gwet_ac1(a: list[str], b: list[str], categories: list[str]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    index = {cat: i for i, cat in enumerate(categories)}
    counts = np.zeros(len(categories), dtype=float)
    agree = 0
    for x, y in zip(a, b):
        if x not in index or y not in index:
            return None
        counts[index[x]] += 1
        counts[index[y]] += 1
        agree += int(x == y)
    po = agree / n
    p = counts / (2.0 * n)
    q = len(categories)
    pe = float(np.sum(p * (1.0 - p)) / (q - 1)) if q > 1 else 0.0
    if math.isclose(1.0 - pe, 0.0):
        return 1.0 if math.isclose(po, 1.0) else 0.0
    return float((po - pe) / (1.0 - pe))


def bootstrap_case_exact(left: pd.DataFrame, right: pd.DataFrame, field: str, row_to_case: dict[str, str], reps: int) -> dict:
    rng = np.random.default_rng(SEED + sum(ord(x) for x in field))
    handles = list(left["row_handle"])
    cases = sorted({row_to_case[h] for h in handles})
    per_case = {}
    for case in cases:
        hs = [h for h in handles if row_to_case[h] == case]
        av = [clean(left.loc[left["row_handle"].isin(hs), field].iloc[i]) for i in range(len(hs))]
        bv = [clean(right.loc[right["row_handle"].isin(hs), field].iloc[i]) for i in range(len(hs))]
        per_case[case] = float(np.mean([x == y for x, y in zip(av, bv)])) if av else np.nan
    values = np.asarray([per_case[c] for c in cases], dtype=float)
    if len(values) == 0:
        return {"case_count": 0, "bootstrap_low": None, "bootstrap_high": None}
    if len(values) == 1:
        return {"case_count": 1, "bootstrap_low": float(values[0]), "bootstrap_high": float(values[0])}
    samples = rng.integers(0, len(values), size=(reps, len(values)))
    boot = values[samples].mean(axis=1)
    return {
        "case_count": int(len(values)),
        "bootstrap_low": float(np.quantile(boot, 0.025)),
        "bootstrap_high": float(np.quantile(boot, 0.975)),
    }


def field_stats(left: pd.DataFrame, right: pd.DataFrame, field: str, categories: list[str], row_to_case: dict[str, str], reps: int) -> dict:
    a = [clean(x) for x in left[field]]
    b = [clean(x) for x in right[field]]
    n = len(a)
    missing = [x == "" or y == "" for x, y in zip(a, b)]
    valid = [not x for x in missing]
    av = [x for x, ok in zip(a, valid) if ok]
    bv = [y for y, ok in zip(b, valid) if ok]
    unexpected = sorted((set(av) | set(bv)) - set(categories))
    exact_valid = float(np.mean([x == y for x, y in zip(av, bv)])) if av else None
    unclear_rate = float(np.mean([x == "unclear" for x in av + bv])) if av else None
    out = {
        "field": field,
        "n_rows": n,
        "n_valid_pairs": len(av),
        "missing_rate": float(np.mean(missing)) if n else None,
        "exact_agreement_valid": exact_valid,
        "exact_agreement_all_rows": float(np.mean([x == y for x, y in zip(a, b)])) if n else None,
        "cohen_kappa": cohen_kappa(av, bv, categories) if not unexpected else None,
        "gwet_ac1": gwet_ac1(av, bv, categories) if not unexpected else None,
        "unclear_rate_pooled_valid_assignments": unclear_rate,
        "unexpected_categories": unexpected,
    }
    out.update(bootstrap_case_exact(left, right, field, row_to_case, reps))
    return out


def span_stats(left: pd.DataFrame, right: pd.DataFrame, span: str, status: str, required_statuses: set[str]) -> dict:
    required = [(clean(x) in required_statuses) or (clean(y) in required_statuses) for x, y in zip(left[status], right[status])]
    valid = [req and clean(x) != "" and clean(y) != "" for req, x, y in zip(required, left[span], right[span])]
    missing = [req and not ok for req, ok in zip(required, valid)]
    exact = [normalize_span(x) == normalize_span(y) for x, y, ok in zip(left[span], right[span], valid) if ok]
    f1 = [token_f1(x, y) for x, y, ok in zip(left[span], right[span], valid) if ok]
    return {
        "field": span,
        "status_field": status,
        "n_required": int(sum(required)),
        "n_valid_pairs": int(sum(valid)),
        "missing_rate_required": float(np.mean(missing)) if any(required) else None,
        "exact_agreement_valid": float(np.mean(exact)) if exact else None,
        "token_f1_mean_valid": float(np.mean(f1)) if f1 else None,
        "token_f1_median_valid": float(np.median(f1)) if f1 else None,
    }


def load_and_filter(path: Path, expected_columns: list[str], roster_handles: set[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(frame.columns) != expected_columns:
        raise ValueError(f"{path}: exact schema mismatch")
    if frame["row_handle"].duplicated().any():
        raise ValueError(f"{path}: duplicate row handles")
    handles = set(frame["row_handle"])
    if not handles.issuperset(roster_handles):
        raise ValueError(f"{path}: missing handles from fixed double-code roster")
    extra = handles - roster_handles
    # Coder files may contain the full worksheet; extra single-code rows are
    # ignored only after exact schema validation.
    if extra:
        frame = frame[frame["row_handle"].isin(roster_handles)].copy()
    frame = frame.sort_values("row_handle").reset_index(drop=True)
    if set(frame["row_handle"]) != roster_handles:
        raise ValueError(f"{path}: filtered rows do not exactly cover roster")
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--pass-a-coder-a", required=True)
    parser.add_argument("--pass-a-coder-b", required=True)
    parser.add_argument("--pass-b-coder-a", required=True)
    parser.add_argument("--pass-b-coder-b", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--bootstrap-reps", type=int, default=2000)
    args = parser.parse_args()
    if args.bootstrap_reps < 1:
        raise ValueError("--bootstrap-reps must be positive")

    package = Path(args.package_dir)
    internal = json.loads((package / "internal/SAMPLE_ROW_MAP.json").read_text(encoding="utf-8"))
    row_to_case = {str(x["row_handle"]): str(x["case_id"]) for x in internal}
    roster_handles = {str(x["row_handle"]) for x in internal if bool(x["double_code_case"])}
    roster_cases = sorted({row_to_case[h] for h in roster_handles})
    if not roster_handles or len(roster_cases) != 20:
        raise ValueError(f"fixed double-code roster must contain 20 cases, got {len(roster_cases)}")

    pa_a = load_and_filter(Path(args.pass_a_coder_a), [
        "row_handle", "hypothesis_text", "proposition_boundary", "proposition_span", "scope_status", "scope_span",
        "time_horizon_status", "time_horizon_span", "consequence_activity_text", "consequence_active_days_text",
        "consequence_counterparty_breadth_text", "consequence_new_counterparties_text", "falsifier_status", "falsifier_span",
        "qualification_status", "qualification_span", "pass_a_notes",
    ], roster_handles)
    pa_b = load_and_filter(Path(args.pass_a_coder_b), list(pa_a.columns), roster_handles)
    pb_a = load_and_filter(Path(args.pass_b_coder_a), [
        "row_handle", "hypothesis_text", "recorded_activity", "recorded_active_days", "recorded_counterparty_breadth",
        "recorded_new_counterparties", "recorded_horizon_days", "evidence_labels", "alignment_activity", "alignment_active_days",
        "alignment_counterparty_breadth", "alignment_new_counterparties", "alignment_span_activity", "alignment_span_active_days",
        "alignment_span_counterparty_breadth", "alignment_span_new_counterparties", "horizon_compatibility",
        "evidence_pointer_E_SELF", "evidence_pointer_E_MARKET", "evidence_pointer_E_COVERAGE", "evidence_pointer_E_PLACEBO", "pass_b_notes",
    ], roster_handles)
    pb_b = load_and_filter(Path(args.pass_b_coder_b), list(pb_a.columns), roster_handles)

    categorical = []
    for section, field, categories in CATEGORICAL_FIELDS:
        left, right = (pa_a, pa_b) if section == "pass_a" else (pb_a, pb_b)
        stats = field_stats(left, right, field, categories, row_to_case, args.bootstrap_reps)
        stats["section"] = section
        stats["categories"] = categories
        categorical.append(stats)

    spans = []
    for section, span, status, required_statuses in SPAN_FIELDS:
        left, right = (pa_a, pa_b) if section == "pass_a" else (pb_a, pb_b)
        stats = span_stats(left, right, span, status, required_statuses)
        stats["section"] = section
        spans.append(stats)

    valid_cat = [x for x in categorical if x["n_valid_pairs"] > 0]
    valid_span = [x for x in spans if x["n_valid_pairs"] > 0]
    all_cat_assignments = sum(x["n_valid_pairs"] for x in categorical)
    pooled_exact = None
    if all_cat_assignments:
        pooled_exact = float(sum(x["exact_agreement_valid"] * x["n_valid_pairs"] for x in valid_cat) / all_cat_assignments)
    all_span_pairs = sum(x["n_valid_pairs"] for x in spans)
    pooled_span_exact = None
    pooled_span_f1 = None
    if all_span_pairs:
        pooled_span_exact = float(sum(x["exact_agreement_valid"] * x["n_valid_pairs"] for x in valid_span) / all_span_pairs)
        pooled_span_f1 = float(sum(x["token_f1_mean_valid"] * x["n_valid_pairs"] for x in valid_span) / all_span_pairs)

    not_assessable = not valid_cat and not valid_span
    failures = []
    if not_assessable:
        status = "RELIABILITY_NOT_YET_ASSESSABLE"
    else:
        for x in categorical:
            if x["n_valid_pairs"] == 0:
                failures.append({"type": "no_valid_pairs", "field": x["field"]})
                continue
            if x["missing_rate"] > THRESHOLDS["missing_rate_max"]:
                failures.append({"type": "missing_rate", "field": x["field"], "value": x["missing_rate"]})
            if x["unexpected_categories"]:
                failures.append({"type": "unexpected_categories", "field": x["field"], "value": x["unexpected_categories"]})
            if x["exact_agreement_valid"] < THRESHOLDS["categorical_field_exact_min"]:
                failures.append({"type": "field_exact", "field": x["field"], "value": x["exact_agreement_valid"]})
            if x["cohen_kappa"] is None or x["cohen_kappa"] < THRESHOLDS["categorical_field_kappa_min"]:
                failures.append({"type": "field_kappa", "field": x["field"], "value": x["cohen_kappa"]})
            if x["unclear_rate_pooled_valid_assignments"] is not None and x["unclear_rate_pooled_valid_assignments"] > THRESHOLDS["unclear_rate_max"]:
                failures.append({"type": "unclear_rate", "field": x["field"], "value": x["unclear_rate_pooled_valid_assignments"]})
        for x in spans:
            if x["n_required"] == 0:
                continue
            if x["missing_rate_required"] is None or x["missing_rate_required"] > THRESHOLDS["missing_rate_max"]:
                failures.append({"type": "span_missing_rate", "field": x["field"], "value": x["missing_rate_required"]})
            if x["exact_agreement_valid"] is None or x["exact_agreement_valid"] < THRESHOLDS["span_exact_min"]:
                failures.append({"type": "span_exact", "field": x["field"], "value": x["exact_agreement_valid"]})
            if x["token_f1_mean_valid"] is None or x["token_f1_mean_valid"] < THRESHOLDS["span_token_f1_min"]:
                failures.append({"type": "span_token_f1", "field": x["field"], "value": x["token_f1_mean_valid"]})
        if pooled_exact is None or pooled_exact < THRESHOLDS["pooled_categorical_exact_min"]:
            failures.append({"type": "pooled_categorical_exact", "value": pooled_exact})
        if pooled_span_exact is None or pooled_span_exact < THRESHOLDS["span_exact_min"]:
            failures.append({"type": "pooled_span_exact", "value": pooled_span_exact})
        if pooled_span_f1 is None or pooled_span_f1 < THRESHOLDS["span_token_f1_min"]:
            failures.append({"type": "pooled_span_token_f1", "value": pooled_span_f1})
        status = "RELIABILITY_FAIL" if failures else "RELIABILITY_PASS"

    report = {
        "created_at": utc_now(),
        "status": status,
        "package_dir": str(package),
        "bootstrap_reps": args.bootstrap_reps,
        "seed": SEED,
        "double_code_case_count": len(roster_cases),
        "double_code_row_count": len(roster_handles),
        "double_code_cases": roster_cases,
        "thresholds": THRESHOLDS,
        "pooled_categorical_exact": pooled_exact,
        "pooled_span_exact": pooled_span_exact,
        "pooled_span_token_f1": pooled_span_f1,
        "categorical": categorical,
        "spans": spans,
        "failures": failures,
        "future_outcomes_joined": False,
        "f_delta_joined": False,
        "August_test_joined": False,
        "adjudication_included": False,
    }
    out = Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(categorical + spans).to_csv(out.with_suffix(".csv"), index=False)
    print(json.dumps({"status": status, "double_code_cases": len(roster_cases), "double_code_rows": len(roster_handles), "out": str(out)}, ensure_ascii=False))
    return 0 if status in {"RELIABILITY_PASS", "RELIABILITY_NOT_YET_ASSESSABLE"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
