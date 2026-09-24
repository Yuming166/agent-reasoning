#!/usr/bin/env python3
"""Deterministic artifact-first falsification audit for frozen Decision-State outputs.

This audit is deliberately separate from the frozen evaluation and from the
Astra6 runtime. It reads existing artifacts only; it does not refit models,
regenerate LLM responses, select cases by outcome, reopen August, or overwrite
any source result.  Its outputs are a new, append-only runtime directory.
"""
from __future__ import annotations
import os

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
RES = ROOT / "research/decision_state/results"
TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
SPLITS = ["dev", "test"]
MODELS = [
    "B0_M1",
    "B1_M1_DETERMINISTIC",
    "B2_M1_SINGLE_LLM",
    "B3_M1_MULTI_LLM",
    "B4_M1_VERIFIED_LLM",
]
VARIANTS = ["full", "minus_self", "minus_market", "placebo"]
MAIN_MEASURES = [
    "intervention_sensitivity",
    "self_sensitivity",
    "market_sensitivity",
    "placebo_sensitivity",
    "intervention_sensitivity_max",
    "intervention_sensitivity_min",
    "evidence_aligned_intervention_margin",
    "evidence_alignment_rate",
]
SEED = 20260920


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_dump(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def finite_xy(df: pd.DataFrame, x: str, y: str) -> pd.DataFrame:
    if x not in df.columns or y not in df.columns:
        return df.iloc[0:0].copy()
    out = df.copy()
    out[x] = numeric(out[x])
    out[y] = numeric(out[y])
    return out.loc[out[x].notna() & out[y].notna()].copy()


def corr_pair(x: Iterable[float], y: Iterable[float]) -> dict[str, float | int | None]:
    xa = np.asarray(list(x), dtype=float)
    ya = np.asarray(list(y), dtype=float)
    valid = np.isfinite(xa) & np.isfinite(ya)
    xa, ya = xa[valid], ya[valid]
    out: dict[str, float | int | None] = {"n": int(len(xa))}
    if len(xa) < 3 or np.ptp(xa) == 0 or np.ptp(ya) == 0:
        out.update({"pearson_r": None, "pearson_p": None, "spearman_rho": None, "spearman_p": None})
        return out
    pr = pearsonr(xa, ya)
    sr = spearmanr(xa, ya)
    out.update({
        "pearson_r": float(pr.statistic),
        "pearson_p": float(pr.pvalue),
        "spearman_rho": float(sr.statistic),
        "spearman_p": float(sr.pvalue),
    })
    return out


def residualize(values: np.ndarray, groups: pd.Series) -> np.ndarray:
    """Remove a fixed effect for groups, retaining an intercept."""
    values = np.asarray(values, dtype=float)
    g = groups.astype(str).fillna("<NA>")
    design = pd.get_dummies(g, drop_first=False, dtype=float).to_numpy()
    design = np.column_stack([np.ones(len(values)), design[:, 1:]])
    beta, *_ = np.linalg.lstsq(design, values, rcond=None)
    return values - design @ beta


def correlation_row(
    df: pd.DataFrame,
    x: str,
    y: str,
    scope: str,
    adjustment: str = "none",
    cluster_note: str = "",
) -> dict:
    sub = finite_xy(df, x, y)
    row = {"scope": scope, "adjustment": adjustment, "x": x, "y": y, "cluster_note": cluster_note}
    if adjustment == "activity_bin" and len(sub):
        rx = residualize(sub[x].to_numpy(float), sub["activity_bin"])
        ry = residualize(sub[y].to_numpy(float), sub["activity_bin"])
        stats = corr_pair(rx, ry)
        row.update(stats)
        row["mean_x"] = float(sub[x].mean())
        row["mean_y"] = float(sub[y].mean())
        row["median_x"] = float(sub[x].median())
        row["median_y"] = float(sub[y].median())
        row["n_wallets"] = int(sub["anchor_wallet"].nunique())
        return row
    stats = corr_pair(sub[x], sub[y])
    row.update(stats)
    row["mean_x"] = float(sub[x].mean()) if len(sub) else None
    row["mean_y"] = float(sub[y].mean()) if len(sub) else None
    row["median_x"] = float(sub[x].median()) if len(sub) else None
    row["median_y"] = float(sub[y].median()) if len(sub) else None
    row["n_wallets"] = int(sub["anchor_wallet"].nunique()) if "anchor_wallet" in sub else None
    return row


def add_deltas(case: pd.DataFrame) -> pd.DataFrame:
    out = case.copy()
    for model in MODELS:
        ll_cols = [f"{model}__{target}__ll" for target in TARGETS]
        out[f"{model}__macro_ll"] = out[ll_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    out["delta_B4_vs_B0_macro_audit"] = out["B4_M1_VERIFIED_LLM__macro_ll"] - out["B0_M1__macro_ll"]
    out["gain_B4_vs_B0_macro_audit"] = -out["delta_B4_vs_B0_macro_audit"]
    out["b4_gain_flag_audit"] = (out["delta_B4_vs_B0_macro_audit"] < 0).astype(int)
    for target in TARGETS:
        out[f"delta_B4_vs_B0__{target}"] = (
            pd.to_numeric(out[f"B4_M1_VERIFIED_LLM__{target}__ll"], errors="coerce")
            - pd.to_numeric(out[f"B0_M1__{target}__ll"], errors="coerce")
        )
    return out


def make_quartiles(series: pd.Series, prefix: str) -> pd.Series:
    x = numeric(series)
    try:
        q = pd.qcut(x, q=4, duplicates="drop")
        labels = {code: f"{prefix}_Q{code + 1}" for code in range(len(q.cat.categories))}
        return q.cat.codes.map(labels).astype("string")
    except ValueError:
        return pd.Series(pd.NA, index=series.index, dtype="string")


def bootstrap_cluster_corr(
    df: pd.DataFrame,
    x: str,
    y: str,
    n_boot: int,
    seed: int,
    scope: str,
) -> dict:
    sub = finite_xy(df, x, y)
    groups = []
    for _, group in sub.groupby("anchor_wallet", sort=True):
        groups.append(group[[x, y]].to_numpy(float))
    point = corr_pair(sub[x], sub[y])
    row = {
        "scope": scope,
        "x": x,
        "y": y,
        "n_rows": int(len(sub)),
        "n_wallets": int(len(groups)),
        "point_pearson_r": point.get("pearson_r"),
        "point_spearman_rho": point.get("spearman_rho"),
        "bootstrap_reps": int(n_boot),
        "seed": int(seed),
    }
    if len(groups) < 3:
        row.update({"pearson_ci_low": None, "pearson_ci_high": None, "spearman_ci_low": None, "spearman_ci_high": None})
        return row
    rng = np.random.default_rng(seed)
    prs: list[float] = []
    srs: list[float] = []
    for _ in range(n_boot):
        picks = rng.integers(0, len(groups), size=len(groups))
        arrays = [groups[i] for i in picks]
        sample = np.concatenate(arrays, axis=0)
        c = corr_pair(sample[:, 0], sample[:, 1])
        if c["pearson_r"] is not None:
            prs.append(float(c["pearson_r"]))
        if c["spearman_rho"] is not None:
            srs.append(float(c["spearman_rho"]))
    row.update({
        "pearson_ci_low": float(np.quantile(prs, 0.025)) if prs else None,
        "pearson_ci_high": float(np.quantile(prs, 0.975)) if prs else None,
        "spearman_ci_low": float(np.quantile(srs, 0.025)) if srs else None,
        "spearman_ci_high": float(np.quantile(srs, 0.975)) if srs else None,
    })
    return row


def wallet_collapsed_corr(df: pd.DataFrame, x: str, y: str, scope: str) -> dict:
    sub = finite_xy(df, x, y)
    collapsed = sub.groupby("anchor_wallet", as_index=False)[[x, y]].mean()
    stats = corr_pair(collapsed[x], collapsed[y])
    return {
        "scope": scope,
        "x": x,
        "y": y,
        "n_rows": int(len(sub)),
        "n_wallets": int(len(collapsed)),
        "pearson_r": stats.get("pearson_r"),
        "pearson_p": stats.get("pearson_p"),
        "spearman_rho": stats.get("spearman_rho"),
        "spearman_p": stats.get("spearman_p"),
    }


def summarize_strata(df: pd.DataFrame, dimension: str, col: str) -> pd.DataFrame:
    rows = []
    for value, group in df.groupby(col, dropna=False, sort=True):
        value = "<NA>" if pd.isna(value) else str(value)
        valid = finite_xy(group, "intervention_sensitivity", "delta_B4_vs_B0_macro_audit")
        c = corr_pair(valid["intervention_sensitivity"], valid["delta_B4_vs_B0_macro_audit"])
        rows.append({
            "dimension": dimension,
            "stratum": value,
            "n_rows": int(len(group)),
            "n_wallets": int(group["anchor_wallet"].nunique()),
            "mean_intervention_sensitivity": float(numeric(group["intervention_sensitivity"]).mean()),
            "median_intervention_sensitivity": float(numeric(group["intervention_sensitivity"]).median()),
            "mean_delta_B4_vs_B0_macro": float(numeric(group["delta_B4_vs_B0_macro_audit"]).mean()),
            "median_delta_B4_vs_B0_macro": float(numeric(group["delta_B4_vs_B0_macro_audit"]).median()),
            "b4_gain_rate": float(numeric(group["b4_gain_flag_audit"]).mean()),
            "pearson_r_F_delta": c.get("pearson_r"),
            "spearman_rho_F_delta": c.get("spearman_rho"),
        })
    return pd.DataFrame(rows)


def model_summary(df: pd.DataFrame, scope: str, dimension: str = "all", stratum: str = "all") -> pd.DataFrame:
    rows = []
    for model in MODELS:
        col = f"{model}__macro_ll"
        sub = df.loc[numeric(df[col]).notna()].copy()
        b0 = numeric(sub["B0_M1__macro_ll"])
        ll = numeric(sub[col])
        delta = ll - b0
        rows.append({
            "scope": scope,
            "dimension": dimension,
            "stratum": stratum,
            "model": model,
            "n_rows": int(len(sub)),
            "n_wallets": int(sub["anchor_wallet"].nunique()),
            "mean_macro_log_loss": float(ll.mean()) if len(ll) else None,
            "median_macro_log_loss": float(ll.median()) if len(ll) else None,
            "mean_delta_vs_B0": float(delta.mean()) if len(delta) else None,
            "median_delta_vs_B0": float(delta.median()) if len(delta) else None,
            "gain_rate_vs_B0": float((delta < 0).mean()) if len(delta) else None,
        })
    return pd.DataFrame(rows)


def parse_variant_audit(panel_path: Path) -> pd.DataFrame:
    rows = []
    with panel_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            variant = str(record.get("variant", "<missing>"))
            parsed = record.get("parsed") if isinstance(record.get("parsed"), dict) else {}
            hypotheses = parsed.get("hypotheses", []) if isinstance(parsed.get("hypotheses"), list) else []
            valid_h = [h for h in hypotheses if isinstance(h, dict)]
            texts = [str(h.get("text", "")) for h in valid_h]
            consequence_valid = 0
            for h in valid_h:
                cons = h.get("consequences")
                if isinstance(cons, dict) and all(cons.get(t) in {"up", "same", "down"} for t in TARGETS):
                    consequence_valid += 1
            rows.append({
                "case_id": record.get("case_id"),
                "variant": variant,
                "parse_valid": int(bool(record.get("parse_valid"))),
                "http_status": record.get("http_status"),
                "model_requested": record.get("model_requested"),
                "model_returned": record.get("model_returned"),
                "n_hypotheses": int(len(valid_h)),
                "n_consequence_valid": int(consequence_valid),
                "text_chars": int(sum(len(text) for text in texts)),
                "nonempty_text_hypotheses": int(sum(bool(text.strip()) for text in texts)),
                "evidence_ids": int(sum(len(h.get("evidence_ids", [])) for h in valid_h if isinstance(h.get("evidence_ids", []), list))),
            })
    raw = pd.DataFrame(rows)
    if raw.empty:
        return raw
    summary = raw.groupby("variant", as_index=False).agg(
        records=("case_id", "size"),
        unique_cases=("case_id", "nunique"),
        parse_valid_rate=("parse_valid", "mean"),
        mean_hypotheses=("n_hypotheses", "mean"),
        mean_consequence_valid=("n_consequence_valid", "mean"),
        mean_text_chars=("text_chars", "mean"),
        nonempty_text_rate=("nonempty_text_hypotheses", lambda x: float((x > 0).mean())),
        model_returned_nunique=("model_returned", "nunique"),
    )
    return summary


def write_report(out: Path, manifest: dict, overall: pd.DataFrame, cluster: pd.DataFrame, strata: pd.DataFrame, models: pd.DataFrame, variants: pd.DataFrame) -> None:
    def row_filter(frame, **kwargs):
        out = frame
        for k, v in kwargs.items():
            out = out[out[k] == v]
        return out

    main = row_filter(overall, scope="oos", adjustment="none", x="intervention_sensitivity", y="delta_B4_vs_B0_macro_audit")
    test = row_filter(overall, scope="test", adjustment="none", x="intervention_sensitivity", y="delta_B4_vs_B0_macro_audit")
    dev = row_filter(overall, scope="dev", adjustment="none", x="intervention_sensitivity", y="delta_B4_vs_B0_macro_audit")
    matched = row_filter(overall, scope="oos", adjustment="activity_bin", x="intervention_sensitivity", y="delta_B4_vs_B0_macro_audit")
    cl = cluster[(cluster["scope"] == "oos") & (cluster["x"] == "intervention_sensitivity") & (cluster["y"] == "delta_B4_vs_B0_macro_audit") & (cluster["cluster_note"] == "cluster_bootstrap")]

    def fmt(frame, col, digits=4):
        if frame.empty or pd.isna(frame.iloc[0].get(col)):
            return "NA"
        return f"{float(frame.iloc[0][col]):.{digits}f}"

    lines = [
        "# Decision-State frozen artifact-first falsification audit",
        "",
        f"- Run time: `{manifest['created_at']}`",
        f"- Mode: `{manifest['mode']}`",
        f"- Source rows: `{manifest['source_rows']}`; OOS rows used: `{manifest['oos_rows']}` (dev `{manifest['dev_rows']}`, test `{manifest['test_rows']}`)",
        f"- Wallets in OOS: `{manifest['oos_wallets']}`",
        f"- Bootstrap: wallet-clustered, `{manifest['cluster_bootstrap_reps']}` replicates, seed `{manifest['seed']}`",
        "",
        "## Scope and immutability",
        "",
        "This is a deterministic audit of already-frozen artifacts. It does not generate new LLM outputs, fit a new predictor, change a probability, select cases by outcome, or reopen the August frozen test. The official Astra6 cycle and claim/experiment ledgers are untouched.",
        "",
        "## Main F–Delta audit",
        "",
        "`F` is the existing intervention-response magnitude (`intervention_sensitivity`), not semantic validity or faithfulness. `Delta` is frozen B4 macro log-loss minus frozen B0/M1 macro log-loss; negative means B4 improved.",
        "",
        f"- OOS pooled Pearson(F, Delta): `{fmt(main, 'pearson_r')}`; Spearman: `{fmt(main, 'spearman_rho')}`; n=`{int(main.iloc[0]['n']) if not main.empty else 'NA'}`.",
        f"- July development Pearson: `{fmt(dev, 'pearson_r')}`; August frozen test Pearson: `{fmt(test, 'pearson_r')}`.",
        f"- Activity-bin residualized OOS Pearson: `{fmt(matched, 'pearson_r')}`; this removes only fixed activity-bin means and is not a causal adjustment.",
    ]
    if not cl.empty:
        lines.append(f"- Wallet-cluster bootstrap Pearson 95% CI: `[{fmt(cl, 'pearson_ci_low')}, {fmt(cl, 'pearson_ci_high')}]`; wallet-collapsed estimates are in `cluster_correlations.csv`.")
    lines += [
        "",
        "A correlation near zero, or a confidence interval crossing zero, is a falsification of a simple monotone F-to-effectiveness story in this artifact set; it is not evidence that true belief, intent, or semantic validity is absent.",
        "",
        "## Decomposition and controls",
        "",
        "The CSV outputs report intervention type (self/market/placebo), each consequence dimension, split, activity strata, repeat-wallet status, dominant event family, event-history quartiles, and wallet-clustered estimates. They are descriptive audits over the frozen OOS rows, not post-hoc model tuning.",
        "",
        "## Representation boundary",
        "",
        "The panel contains narrative hypothesis text, but the frozen B2/B3/B4 evaluation lineage converts hypotheses into closed consequence distributions and intervention features. This artifact set does not contain a text-only/text-free matched downstream ablation or embeddings. Therefore it cannot attribute any observed B2/B3/B4 behavior to narrative text itself; B1 and B0 are text-free comparator baselines, not a controlled text ablation.",
        "",
        "## Current deterministic conclusion",
        "",
        "The next defensible action is a falsification/reliability gate, not a large new LLM experiment. If semantic human audit is later considered, its sampling and rubric must be locked before inspecting F, Delta, success/failure, or August outcomes. Any Luna Max interpretation of this directory remains `OFF_CHARTER_EXPLORATORY_FALLBACK` and cannot be promoted to the official claim ledger or experiment registry.",
        "",
        "## Files",
        "",
        "- `audit_manifest.json`: input fingerprints and protocol metadata.",
        "- `overall_correlations.csv`: raw and activity-bin-adjusted correlations.",
        "- `cluster_correlations.csv`: wallet-cluster bootstrap and wallet-collapsed correlations.",
        "- `dimension_correlations.csv`: consequence-dimension level associations.",
        "- `strata_summary.csv`: descriptive stratified audit.",
        "- `model_strata_summary.csv`: frozen model loss summaries by scope/stratum.",
        "- `variant_summary.csv`: frozen panel variant parse/text presence audit.",
    ]
    (out / "AUDIT_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--cluster-bootstrap", type=int, default=1000)
    args = parser.parse_args()

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out_dir) if args.out_dir else ROOT / "research_os/runtime" / f"lunamax_artifact_audit_{run_id}"
    out.mkdir(parents=True, exist_ok=False)

    input_paths = {
        "case_degradation": RES / "decision_state_case_degradation_analysis.csv",
        "loss_delta_long": RES / "decision_state_loss_delta_long.csv",
        "prompt_cases": RES / "decision_state_prompt_cases.csv",
        "llm_features": RES / "decision_state_llm_features.csv",
        "hypothesis_panel": RES / "hypothesis_panel_full.jsonl",
        "protocol": ROOT / "research/decision_state/protocol/DECISION_STATE_PROTOCOL_V1.md",
        "evaluation_code": ROOT / "research/decision_state/src/evaluate_decision_state.py",
    }
    for path in input_paths.values():
        if not path.exists():
            raise FileNotFoundError(path)

    case = pd.read_csv(input_paths["case_degradation"], low_memory=False)
    case = add_deltas(case)
    if "oos_loss_available" in case.columns:
        oos = case.loc[pd.to_numeric(case["oos_loss_available"], errors="coerce").eq(1)].copy()
    else:
        oos = case.loc[case["B4_M1_VERIFIED_LLM__macro_ll"].notna() & case["B0_M1__macro_ll"].notna()].copy()
    oos["activity_bin"] = oos["activity_bin"].astype(str)
    oos["split"] = oos["split"].astype(str)
    oos["panel_repeat_wallet"] = oos["panel_repeat_wallet"].astype(str)
    oos["dominant_event_family_30d"] = oos["dominant_event_family_30d"].astype(str)
    oos["event_count_7d_quartile"] = make_quartiles(oos["event_count_7d"], "event_count_7d")
    oos["history_event_count_30d_quartile"] = make_quartiles(oos["history_event_count_30d"], "history_event_count_30d")

    # Overall correlations: raw pooled, split-aware, and fixed activity-bin residualized.
    overall_rows = []
    delta_y = "delta_B4_vs_B0_macro_audit"
    for scope, frame in [("oos", oos), ("dev", oos[oos["split"] == "dev"]), ("test", oos[oos["split"] == "test"])]:
        for measure in MAIN_MEASURES:
            overall_rows.append(correlation_row(frame, measure, delta_y, scope, "none"))
            if scope == "oos":
                overall_rows.append(correlation_row(frame, measure, delta_y, scope, "activity_bin"))
            overall_rows.append(correlation_row(frame, measure, "gain_B4_vs_B0_macro_audit", scope, "none"))
        for target in TARGETS:
            for kind in ("self", "market", "placebo"):
                overall_rows.append(correlation_row(frame, f"js_{target}_{kind}", f"delta_B4_vs_B0__{target}", scope, "none"))
    overall = pd.DataFrame(overall_rows)
    overall.to_csv(out / "overall_correlations.csv", index=False)

    cluster_rows = []
    for scope, frame in [("oos", oos), ("dev", oos[oos["split"] == "dev"]), ("test", oos[oos["split"] == "test"])]:
        for measure in MAIN_MEASURES:
            cluster_rows.append(bootstrap_cluster_corr(frame, measure, delta_y, args.cluster_bootstrap, SEED, scope))
            cluster_rows[-1]["cluster_note"] = "cluster_bootstrap"
            cluster_rows.append(wallet_collapsed_corr(frame, measure, delta_y, scope))
            cluster_rows[-1]["cluster_note"] = "wallet_collapsed"
    cluster = pd.DataFrame(cluster_rows)
    cluster.to_csv(out / "cluster_correlations.csv", index=False)

    dimension_rows = []
    for scope, frame in [("oos", oos), ("dev", oos[oos["split"] == "dev"]), ("test", oos[oos["split"] == "test"])]:
        for target in TARGETS:
            for x in ["intervention_sensitivity", "self_sensitivity", "market_sensitivity", "placebo_sensitivity"]:
                y = f"delta_B4_vs_B0__{target}"
                row = correlation_row(frame, x, y, scope, "none")
                row["target"] = target
                dimension_rows.append(row)
            for kind in ("self", "market", "placebo"):
                row = correlation_row(frame, f"js_{target}_{kind}", f"delta_B4_vs_B0__{target}", scope, "none")
                row["target"] = target
                dimension_rows.append(row)
    dimension = pd.DataFrame(dimension_rows)
    dimension.to_csv(out / "dimension_correlations.csv", index=False)

    strata_parts = []
    for dimension_name, column in [
        ("split", "split"),
        ("activity_bin", "activity_bin"),
        ("panel_repeat_wallet", "panel_repeat_wallet"),
        ("dominant_event_family_30d", "dominant_event_family_30d"),
        ("event_count_7d_quartile", "event_count_7d_quartile"),
        ("history_event_count_30d_quartile", "history_event_count_30d_quartile"),
    ]:
        strata_parts.append(summarize_strata(oos, dimension_name, column))
    strata = pd.concat(strata_parts, ignore_index=True)
    strata.to_csv(out / "strata_summary.csv", index=False)

    model_parts = [model_summary(oos, "oos")]
    for split in SPLITS:
        frame = oos[oos["split"] == split]
        model_parts.append(model_summary(frame, split))
    for dimension_name, column in [
        ("activity_bin", "activity_bin"),
        ("panel_repeat_wallet", "panel_repeat_wallet"),
        ("dominant_event_family_30d", "dominant_event_family_30d"),
        ("event_count_7d_quartile", "event_count_7d_quartile"),
        ("history_event_count_30d_quartile", "history_event_count_30d_quartile"),
    ]:
        for value, frame in oos.groupby(column, dropna=False, sort=True):
            model_parts.append(model_summary(frame, "oos", dimension_name, "<NA>" if pd.isna(value) else str(value)))
    model_strata = pd.concat(model_parts, ignore_index=True)
    model_strata.to_csv(out / "model_strata_summary.csv", index=False)

    variant_summary = parse_variant_audit(input_paths["hypothesis_panel"])
    variant_summary.to_csv(out / "variant_summary.csv", index=False)

    manifest = {
        "created_at": utc_now(),
        "run_id": run_id,
        "mode": "DETERMINISTIC_ARTIFACT_FIRST_AUDIT",
        "status": "COMPLETE",
        "source_rows": int(len(case)),
        "oos_rows": int(len(oos)),
        "dev_rows": int((oos["split"] == "dev").sum()),
        "test_rows": int((oos["split"] == "test").sum()),
        "oos_wallets": int(oos["anchor_wallet"].nunique()),
        "cluster_bootstrap_reps": int(args.cluster_bootstrap),
        "seed": int(SEED),
        "delta_definition": "B4_M1_VERIFIED_LLM macro log loss minus B0_M1 macro log loss; negative means B4 gain",
        "f_definition": "existing intervention_sensitivity; no semantic-validity inference",
        "official_astra_cycle_untouched": True,
        "claim_ledger_touched": False,
        "experiment_registry_touched": False,
        "new_llm_outputs": False,
        "august_frozen_test_retuned": False,
        "input_sha256": {name: sha256_file(path) for name, path in input_paths.items()},
        "output_files": sorted(p.name for p in out.iterdir() if p.is_file()),
    }
    json_dump(out / "audit_manifest.json", manifest)
    write_report(out, manifest, overall, cluster, strata, model_strata, variant_summary)
    manifest["output_files"] = sorted(p.name for p in out.iterdir() if p.is_file())
    json_dump(out / "audit_manifest.json", manifest)
    print(json.dumps({"out_dir": str(out), **{k: manifest[k] for k in ("source_rows", "oos_rows", "dev_rows", "test_rows", "oos_wallets")}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
