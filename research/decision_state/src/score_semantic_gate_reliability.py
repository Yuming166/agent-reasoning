#!/usr/bin/env python3
"""Score pre-adjudication reliability for Semantic Gate V2.1.

This scorer is deliberately outcome-blind.  It reads only the two coders'
annotation sheets, restricts scoring to the locked 20-case double-code roster,
and reports exact agreement, nominal Cohen kappa, and q-specific Gwet AC1.
Confidence intervals resample whole cases, never individual rows.

The scorer does not join future outcomes, F, Delta, split/date, wallet
identity, model losses, or August labels.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
EVIDENCE_GROUPS = ["E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"]
SEED = 20260920

LABELS = {
    "pass_a_commitment": ["explicit", "hedged", "generic", "none", "unclear"],
    "pass_a_operationality": ["operational", "non_operational", "unclear"],
    "alignment": ["entailed", "unsupported", "contradicted", "unclear"],
    "horizon": ["compatible", "incompatible", "unclear"],
    "evidence_relevance": ["relevant", "irrelevant", "unclear", "not_applicable"],
}

PASS_A_FIELDS = [
    ("pass_a_commitment", "pass_a_commitment"),
    ("pass_a_operationality", "pass_a_operationality"),
]
PASS_B_FIELDS = [
    *( (f"alignment_{target}", "alignment") for target in TARGETS ),
    ("horizon_compatibility", "horizon"),
    *( (f"evidence_relevance_{group}", "evidence_relevance") for group in EVIDENCE_GROUPS ),
]

THRESHOLDS = {
    "pooled_exact_min": 0.80,
    "pooled_kappa_min": 0.60,
    "dimension_exact_min": 0.70,
    "dimension_kappa_min": 0.40,
    "missing_rate_max": 0.05,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def category_spec(label_family: str) -> tuple[list[str], int]:
    categories = LABELS[label_family]
    return categories, len(categories)


def pair_stats(
    left: pd.Series,
    right: pd.Series,
    *,
    label_family: str | None = None,
) -> dict:
    """Compute pairwise nominal agreement on complete annotation pairs.

    Missing cells are excluded from kappa/AC1 and reported separately.  Gwet
    AC1 uses the nominal multi-category chance term

        P_e = sum_c p_c (1 - p_c) / (q - 1),

    where p_c is the pooled proportion of *all rater assignments* in category
    c and q is the declared number of categories for this field family.
    """
    a = left.map(clean).to_numpy(dtype=object)
    b = right.map(clean).to_numpy(dtype=object)
    if len(a) != len(b):
        raise ValueError(f"paired series have different lengths: {len(a)} != {len(b)}")

    both_missing = (a == "") & (b == "")
    one_missing = ((a == "") ^ (b == ""))
    valid = ~((a == "") | (b == ""))
    n_valid = int(valid.sum())
    n_total = int(len(a))
    exact_total = float((a == b).mean()) if n_total else None
    exact_valid = float((a[valid] == b[valid]).mean()) if n_valid else None

    if label_family is not None:
        declared_categories, q = category_spec(label_family)
    else:
        declared_categories = sorted(set(a[valid]) | set(b[valid])) if n_valid else []
        q = len(declared_categories)

    unexpected_categories: list[str] = []
    if n_valid:
        av = a[valid]
        bv = b[valid]
        observed_categories = sorted(set(av) | set(bv))
        unexpected_categories = sorted(set(observed_categories) - set(declared_categories)) if label_family is not None else []
        po = float((av == bv).mean())
        pa = {cat: float((av == cat).mean()) for cat in declared_categories}
        pb = {cat: float((bv == cat).mean()) for cat in declared_categories}
        # Keep unexpected categories visible rather than silently folding them
        # into a declared label.  Human validation should reject these, but a
        # scorer must remain fail-closed if called directly.
        for cat in unexpected_categories:
            pa[cat] = float((av == cat).mean())
            pb[cat] = float((bv == cat).mean())
        pooled_prob = {cat: (pa[cat] + pb[cat]) / 2.0 for cat in pa}
        pe = float(sum(pa[cat] * pb[cat] for cat in pa))
        if label_family is None:
            # A heterogeneous pooled diagnostic (e.g. commitment plus
            # operationality) has no single declared category universe.
            # Keep exact agreement/kappa for traceability, but do not report
            # an AC1 value that could be mistaken for a q-specific estimate.
            ac1_pe = None
        elif q > 1:
            ac1_pe = float(sum(p * (1.0 - p) for p in pooled_prob.values()) / (q - 1))
        else:
            ac1_pe = None
        kappa = None if abs(1.0 - pe) < 1e-12 else float((po - pe) / (1.0 - pe))
        ac1 = None if ac1_pe is None or abs(1.0 - ac1_pe) < 1e-12 else float((po - ac1_pe) / (1.0 - ac1_pe))
        # Category diagnostics count the two raters' assignments, not rows
        # where either rater happened to use the category.
        counts = Counter(av.tolist()) + Counter(bv.tolist())
        categories = {cat: int(counts.get(cat, 0)) for cat in (declared_categories or sorted(counts))}
        for cat in sorted(set(counts) - set(categories)):
            categories[cat] = int(counts[cat])
    else:
        pe = None
        ac1_pe = None
        kappa = None
        ac1 = None
        categories = {cat: 0 for cat in declared_categories}

    return {
        "n_total": n_total,
        "n_valid_both": n_valid,
        "both_missing": int(both_missing.sum()),
        "one_sided_missing": int(one_missing.sum()),
        "missing_rate_any": float((both_missing | one_missing).mean()) if n_total else None,
        "exact_agreement_all_rows": exact_total,
        "exact_agreement_valid_pairs": exact_valid,
        "cohen_kappa": kappa,
        "gwet_ac1": ac1,
        "gwet_ac1_chance_agreement": ac1_pe,
        "label_family": label_family,
        "declared_category_count": int(q) if q else 0,
        "unexpected_categories": unexpected_categories,
        "categories": categories,
    }


def _bootstrap_stats(
    stacked: pd.DataFrame,
    *,
    label_family: str | None,
    row_to_case: dict[str, str],
    reps: int,
) -> dict:
    """Bootstrap complete rows by sampling the fixed double-coded cases."""
    work = stacked.copy()
    work["case_id"] = work["row_handle"].map(row_to_case)
    work = work[work["case_id"].notna()].copy()
    cases = sorted(work["case_id"].unique())
    empty = {
        "bootstrap_cases": len(cases),
        "reps": reps,
        "seed": SEED,
        "exact_ci_low": None,
        "exact_ci_high": None,
        "kappa_ci_low": None,
        "kappa_ci_high": None,
        "ac1_ci_low": None,
        "ac1_ci_high": None,
    }
    if len(cases) < 2:
        return empty

    by_case = {case: frame for case, frame in work.groupby("case_id", sort=True)}
    rng = np.random.default_rng(SEED)
    exacts: list[float] = []
    kappas: list[float] = []
    ac1s: list[float] = []
    for _ in range(reps):
        sampled = rng.choice(cases, size=len(cases), replace=True)
        draw = pd.concat([by_case[case] for case in sampled], ignore_index=True)
        stats = pair_stats(draw["left"], draw["right"], label_family=label_family)
        if stats["exact_agreement_valid_pairs"] is not None:
            exacts.append(float(stats["exact_agreement_valid_pairs"]))
        if stats["cohen_kappa"] is not None:
            kappas.append(float(stats["cohen_kappa"]))
        if stats["gwet_ac1"] is not None:
            ac1s.append(float(stats["gwet_ac1"]))

    def quantile(values: list[float], q: float) -> float | None:
        return float(np.quantile(values, q)) if values else None

    return {
        "bootstrap_cases": len(cases),
        "reps": reps,
        "seed": SEED,
        "exact_ci_low": quantile(exacts, 0.025),
        "exact_ci_high": quantile(exacts, 0.975),
        "kappa_ci_low": quantile(kappas, 0.025),
        "kappa_ci_high": quantile(kappas, 0.975),
        "ac1_ci_low": quantile(ac1s, 0.025),
        "ac1_ci_high": quantile(ac1s, 0.975),
    }


def paired_frame(left: pd.DataFrame, right: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    """Return exact row-handle pairs; callers already enforce the roster."""
    left_part = left[["row_handle"] + fields]
    right_part = right[["row_handle"] + fields]
    merged = left_part.merge(right_part, on="row_handle", suffixes=("_left", "_right"), how="outer", validate="one_to_one")
    if len(merged) != len(left_part) or len(merged) != len(right_part):
        raise ValueError("coder row handles do not form the same fixed roster")
    return merged


def score_fields(
    left: pd.DataFrame,
    right: pd.DataFrame,
    fields: list[tuple[str, str]],
    row_to_case: dict[str, str],
    reps: int,
    section: str,
) -> list[dict]:
    names = [field for field, _ in fields]
    merged = paired_frame(left, right, names)
    rows = []
    for field, label_family in fields:
        stacked = pd.DataFrame({
            "row_handle": merged["row_handle"],
            "left": merged[f"{field}_left"],
            "right": merged[f"{field}_right"],
        })
        stats = pair_stats(stacked["left"], stacked["right"], label_family=label_family)
        boot = _bootstrap_stats(stacked, label_family=label_family, row_to_case=row_to_case, reps=reps)
        rows.append({"section": section, "field": field, "metric_scope": "dimension", **stats, **boot})
    return rows


def pooled_stats(
    left: pd.DataFrame,
    right: pd.DataFrame,
    fields: list[tuple[str, str]],
    row_to_case: dict[str, str],
    reps: int,
    name: str,
    label_family: str | None,
    metric_scope: str = "pooled",
) -> dict:
    """Pool fields with the same declared label family only."""
    rows = []
    for field, field_family in fields:
        if label_family is not None and field_family != label_family:
            raise ValueError(f"cannot pool {field_family} with {label_family}: category spaces differ")
        merged = paired_frame(left, right, [field])
        rows.append(pd.DataFrame({
            "row_handle": merged["row_handle"],
            "left": merged[f"{field}_left"],
            "right": merged[f"{field}_right"],
        }))
    stacked = pd.concat(rows, ignore_index=True)
    stats = pair_stats(stacked["left"], stacked["right"], label_family=label_family)
    boot = _bootstrap_stats(stacked, label_family=label_family, row_to_case=row_to_case, reps=reps)
    return {
        "section": name,
        "field": "__pooled__",
        "metric_scope": metric_scope,
        **stats,
        **boot,
    }


def load_roster(package: Path, internal_map: list[dict]) -> tuple[set[str], dict[str, str], dict]:
    roster_path = package / "DOUBLE_CODE_ROW_HANDLES.csv"
    roster = pd.read_csv(roster_path, dtype=str, keep_default_na=False)
    if list(roster.columns) != ["row_handle"]:
        raise ValueError("DOUBLE_CODE_ROW_HANDLES.csv must contain exactly row_handle")
    handles = [clean(value) for value in roster["row_handle"]]
    if not handles or any(not handle for handle in handles) or len(handles) != len(set(handles)):
        raise ValueError("double-code roster contains blank or duplicate row handles")

    internal = {str(item["row_handle"]): item for item in internal_map}
    unknown = sorted(set(handles) - set(internal))
    if unknown:
        raise ValueError(f"double-code roster contains unknown row handles: {unknown[:3]}")
    row_to_case = {handle: str(internal[handle]["case_id"]) for handle in handles}
    cases = sorted(set(row_to_case.values()))
    expected_cases = 20
    expected_rows = 60
    if len(cases) != expected_cases or len(handles) != expected_rows:
        raise ValueError(
            f"locked double-code roster mismatch: rows={len(handles)} cases={len(cases)} "
            f"expected rows={expected_rows}, cases={expected_cases}"
        )
    return set(handles), row_to_case, {
        "path": str(roster_path),
        "row_count": len(handles),
        "case_count": len(cases),
        "case_ids": cases,
    }


def load_coder(path: str, *, label: str, all_handles: set[str], roster_handles: set[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "row_handle" not in frame.columns:
        raise ValueError(f"{label} is missing row_handle")
    if frame["row_handle"].duplicated().any():
        raise ValueError(f"{label} contains duplicate row_handle values")
    actual = set(frame["row_handle"].map(clean))
    allowed = all_handles | roster_handles
    unexpected = sorted(actual - allowed)
    if unexpected:
        raise ValueError(f"{label} contains unexpected row handles: {unexpected[:3]}")
    missing_roster = sorted(roster_handles - actual)
    if missing_roster:
        raise ValueError(f"{label} is missing double-code row handles: {missing_roster[:3]}")
    # Templates contain all 300 rows; accepting a roster-only export keeps the
    # scorer useful after a human submits only the double-coded worksheet.
    return frame[frame["row_handle"].isin(roster_handles)].copy().reset_index(drop=True)


def gate_status(table: pd.DataFrame) -> tuple[str, dict]:
    required = table.copy()
    if required.empty:
        return "RELIABILITY_NOT_YET_ASSESSABLE", {"reason": "no scored dimensions"}
    if (required["n_valid_both"] == 0).any():
        return "RELIABILITY_NOT_YET_ASSESSABLE", {
            "reason": "at least one required dimension has no complete coder pairs",
            "fields_without_complete_pairs": required.loc[required["n_valid_both"] == 0, "field"].tolist(),
        }

    missing_failures = required[required["missing_rate_any"] > THRESHOLDS["missing_rate_max"]]
    label_failures = required[required["unexpected_categories"].map(bool)]
    pooled = required[required["metric_scope"] == "pooled"]
    dimensions = required[required["metric_scope"] == "dimension"]
    pooled_failures = pooled[
        (pooled["exact_agreement_valid_pairs"] < THRESHOLDS["pooled_exact_min"])
        | pooled["cohen_kappa"].isna()
        | (pooled["cohen_kappa"] < THRESHOLDS["pooled_kappa_min"])
    ]
    dimension_failures = dimensions[
        (dimensions["exact_agreement_valid_pairs"] < THRESHOLDS["dimension_exact_min"])
        | dimensions["cohen_kappa"].isna()
        | (dimensions["cohen_kappa"] < THRESHOLDS["dimension_kappa_min"])
    ]
    checks = {
        "missingness_pass": bool(missing_failures.empty),
        "label_space_pass": bool(label_failures.empty),
        "pooled_pass": bool(pooled_failures.empty),
        "dimension_pass": bool(dimension_failures.empty),
        "missingness_failures": missing_failures[["section", "field", "missing_rate_any"]].to_dict(orient="records"),
        "label_space_failures": label_failures[["section", "field", "unexpected_categories"]].to_dict(orient="records"),
        "pooled_failures": pooled_failures[["section", "field", "exact_agreement_valid_pairs", "cohen_kappa"]].to_dict(orient="records"),
        "dimension_failures": dimension_failures[["section", "field", "exact_agreement_valid_pairs", "cohen_kappa"]].to_dict(orient="records"),
    }
    return ("RELIABILITY_PASS" if checks["missingness_pass"] and checks["label_space_pass"] and checks["pooled_pass"] and checks["dimension_pass"] else "RELIABILITY_FAIL"), checks


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
    internal_map = json.loads((package / "internal/SAMPLE_ROW_MAP.json").read_text(encoding="utf-8"))
    all_handles = {str(item["row_handle"]) for item in internal_map}
    roster_handles, row_to_case, roster_meta = load_roster(package, internal_map)

    pa_a = load_coder(args.pass_a_coder_a, label="pass_a_coder_a", all_handles=all_handles, roster_handles=roster_handles)
    pa_b = load_coder(args.pass_a_coder_b, label="pass_a_coder_b", all_handles=all_handles, roster_handles=roster_handles)
    pb_a = load_coder(args.pass_b_coder_a, label="pass_b_coder_a", all_handles=all_handles, roster_handles=roster_handles)
    pb_b = load_coder(args.pass_b_coder_b, label="pass_b_coder_b", all_handles=all_handles, roster_handles=roster_handles)

    if not all(set(frame["row_handle"]) == roster_handles for frame in (pa_a, pa_b, pb_a, pb_b)):
        raise ValueError("filtered coder frames do not cover exactly the locked double-code roster")

    rows = score_fields(pa_a, pa_b, PASS_A_FIELDS, row_to_case, args.bootstrap_reps, "pass_a")
    rows += score_fields(pb_a, pb_b, PASS_B_FIELDS, row_to_case, args.bootstrap_reps, "pass_b")
    rows += [pooled_stats(
        pa_a,
        pa_b,
        PASS_A_FIELDS,
        row_to_case,
        args.bootstrap_reps,
        "pass_a_pooled",
        None,
        "pooled_mixed_diagnostic",
    )]
    rows += [pooled_stats(
        pb_a,
        pb_b,
        [(f"alignment_{target}", "alignment") for target in TARGETS],
        row_to_case,
        args.bootstrap_reps,
        "pass_b_alignment_pooled",
        "alignment",
    )]
    rows += [pooled_stats(
        pb_a,
        pb_b,
        [(f"evidence_relevance_{group}", "evidence_relevance") for group in EVIDENCE_GROUPS],
        row_to_case,
        args.bootstrap_reps,
        "pass_b_evidence_relevance_pooled",
        "evidence_relevance",
    )]
    table = pd.DataFrame(rows)
    status, checks = gate_status(table)

    out_json = Path(args.out)
    out_csv = out_json.with_suffix(".csv")
    table.to_csv(out_csv, index=False)
    report = {
        "created_at": utc_now(),
        "status": status,
        "package_dir": str(package),
        "bootstrap_reps": args.bootstrap_reps,
        "seed": SEED,
        "double_code_roster": roster_meta,
        "scored_rows_per_field": len(roster_handles),
        "future_outcomes_joined": False,
        "f_delta_joined": False,
        "thresholds": THRESHOLDS,
        "gate_checks": checks,
        "summaries": table.to_dict(orient="records"),
        "pooled_summaries": table[table["metric_scope"].isin(["pooled", "pooled_mixed_diagnostic"])].to_dict(orient="records"),
        "csv_path": str(out_csv),
    }
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "bootstrap_cases": roster_meta["case_count"], "out": str(out_json), "csv": str(out_csv)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
