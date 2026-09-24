#!/usr/bin/env python3
"""Analyze frozen Decision-State predictions without changing any prediction.

Inputs are read-only frozen artifacts:
- decision_state_prompt_cases.csv (3,000 case descriptors)
- hypothesis_panel_full.jsonl (12,000 frozen responses)
- decision_state_llm_features.csv (frozen structured LLM features)
- decision_state_meta_predictions.csv (frozen B0--B4 probabilities/log losses)
- decision_state_eval_cases.csv (evaluation-only labels)

The script only adds diagnostic tables/figures. It never refits a model,
changes a probability, selects a new case, or overwrites prediction files.
June train cases remain in the 3,000-case descriptor table, but loss deltas
are reported only for rows with already-existing out-of-sample predictions
(July development and August test). This avoids manufacturing in-sample
losses after the effectiveness gate.
"""
from __future__ import annotations
import os

import hashlib
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
RES = ROOT / "research/decision_state/results"
PLOT_DIR = RES / "plots_degradation"
TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
CLASSES = ["down", "same", "up"]
MODELS = [
    "B0_M1",
    "B1_M1_DETERMINISTIC",
    "B2_M1_SINGLE_LLM",
    "B3_M1_MULTI_LLM",
    "B4_M1_VERIFIED_LLM",
]
LLM_VARIANTS = ["full", "minus_self", "minus_market", "placebo"]
KNOWN_EVIDENCE = {"E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"}
BOOTSTRAP = 3000
SEED = 42


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_hypotheses(record: dict | None) -> list[dict]:
    if not record or not record.get("parse_valid"):
        return []
    parsed = record.get("parsed")
    if not isinstance(parsed, dict):
        return []
    hypotheses = []
    for h in parsed.get("hypotheses", [])[:3]:
        if not isinstance(h, dict):
            continue
        try:
            probability = max(float(h.get("probability", 0.0)), 0.0)
        except (TypeError, ValueError):
            continue
        consequences = h.get("consequences")
        evidence = h.get("evidence_ids", [])
        if not isinstance(consequences, dict):
            continue
        if any(consequences.get(target) not in CLASSES for target in TARGETS):
            continue
        if not isinstance(evidence, list):
            evidence = []
        hypotheses.append(
            {
                "probability": probability,
                "evidence_ids": {str(x) for x in evidence},
                "consequences": consequences,
            }
        )
    if not hypotheses:
        return []
    values = np.asarray([h["probability"] for h in hypotheses], dtype=float)
    values = np.where(np.isfinite(values) & (values >= 0), values, 0.0)
    if values.sum() <= 0:
        values = np.ones(len(hypotheses), dtype=float) / len(hypotheses)
    else:
        values = values / values.sum()
    for h, value in zip(hypotheses, values):
        h["probability"] = float(value)
    return hypotheses


def entropy(values: list[float] | np.ndarray) -> tuple[float, float]:
    p = np.asarray(values, dtype=float)
    p = p[np.isfinite(p) & (p > 0)]
    if len(p) == 0:
        return 0.0, 0.0
    raw = float(-np.sum(p * np.log(p)))
    normalized = raw / math.log(len(p)) if len(p) > 1 else 0.0
    return raw, float(normalized)


def consequence_distribution(hypotheses: list[dict], target: str) -> np.ndarray:
    if not hypotheses:
        return np.ones(3, dtype=float) / 3.0
    out = np.zeros(3, dtype=float)
    for h in hypotheses:
        out[CLASSES.index(h["consequences"][target])] += h["probability"]
    return out / out.sum() if out.sum() > 0 else np.ones(3) / 3.0


def load_panel_descriptors() -> pd.DataFrame:
    records: dict[tuple[str, str], dict] = {}
    with (RES / "hypothesis_panel_full.jsonl").open() as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                records[(record["case_id"], record["variant"])] = record

    case_rows = []
    for case_id in sorted({case_id for case_id, _ in records}):
        full_record = records.get((case_id, "full"), {})
        full = parse_hypotheses(full_record)
        parsed = full_record.get("parsed") if isinstance(full_record.get("parsed"), dict) else {}
        all_evidence = set()
        evidence_claims = 0
        evidence_counts = {evidence: 0 for evidence in KNOWN_EVIDENCE}
        for hypothesis in full:
            evidence = hypothesis["evidence_ids"]
            all_evidence.update(evidence)
            evidence_claims += len(evidence)
            for evidence_id in evidence_counts:
                evidence_counts[evidence_id] += int(evidence_id in evidence)

        probability_values = [h["probability"] for h in full]
        hypothesis_entropy, hypothesis_entropy_norm = entropy(probability_values)
        target_confidence = {}
        target_entropy = {}
        for target in TARGETS:
            q = consequence_distribution(full, target)
            target_confidence[target] = float(q.max())
            target_entropy[target] = float(-sum(float(value) * math.log(float(value)) for value in q if value > 0))

        case_rows.append(
            {
                "case_id": case_id,
                "llm_top_probability": float(max(probability_values)) if probability_values else 0.0,
                "llm_probability_margin_top_second": float(
                    sorted(probability_values, reverse=True)[0] - sorted(probability_values, reverse=True)[1]
                )
                if len(probability_values) >= 2
                else float(max(probability_values)) if probability_values else 0.0,
                "hypothesis_entropy_nats": hypothesis_entropy,
                "hypothesis_entropy_normalized": hypothesis_entropy_norm,
                "llm_mean_target_confidence": float(np.mean(list(target_confidence.values()))) if target_confidence else 0.0,
                "llm_mean_target_entropy_nats": float(np.mean(list(target_entropy.values()))) if target_entropy else 0.0,
                "hypothesis_count": len(full),
                "evidence_claim_count": evidence_claims,
                "evidence_unique_count": len(all_evidence),
                "evidence_behavioral_claim_count": evidence_counts["E_SELF"] + evidence_counts["E_MARKET"],
                "e_self_claim_count": evidence_counts["E_SELF"],
                "e_market_claim_count": evidence_counts["E_MARKET"],
                "e_coverage_claim_count": evidence_counts["E_COVERAGE"],
                "e_placebo_claim_count": evidence_counts["E_PLACEBO"],
                "has_unknown_evidence": int(bool(all_evidence - KNOWN_EVIDENCE)),
                "llm_raw_abstain_probability": float(parsed.get("abstain_probability", 0.0) or 0.0),
                "llm_full_parse_valid_raw": int(bool(full_record.get("parse_valid"))),
            }
        )

    descriptors = pd.DataFrame(case_rows)
    return descriptors


def make_family_and_repeat_features(prompt: pd.DataFrame) -> pd.DataFrame:
    out = prompt.copy()
    for column in [
        "native_event_count_30d",
        "token_event_count_30d",
        "internal_event_count_30d",
        "history_event_count_30d",
        "event_count_7d",
        "active_days_30d",
        "active_days_7d",
    ]:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)

    family_columns = {
        "native": "native_event_count_30d",
        "token": "token_event_count_30d",
        "internal": "internal_event_count_30d",
    }
    family_values = out[list(family_columns.values())].to_numpy(float)
    family_names = list(family_columns)
    dominant = []
    family_entropy = []
    for values in family_values:
        total = float(values.sum())
        shares = values / total if total > 0 else np.zeros(len(values))
        family_entropy.append(float(-sum(s * math.log(s) for s in shares if s > 0)))
        if total <= 0:
            dominant.append("unknown")
        else:
            maximum = values.max()
            winners = [name for name, value in zip(family_names, values) if value == maximum]
            dominant.append(winners[0] if len(winners) == 1 else "mixed")
    out["dominant_event_family_30d"] = dominant
    out["event_family_entropy_nats"] = family_entropy
    out["activity_log1p_event_count_7d"] = np.log1p(out["event_count_7d"])
    out["history_length_log1p_events_30d"] = np.log1p(out["history_event_count_30d"])
    out["history_active_days_30d"] = out["active_days_30d"]

    out["cutoff_date_dt"] = pd.to_datetime(out["cutoff_date"])
    out = out.sort_values(["anchor_wallet", "cutoff_date_dt", "case_id"]).reset_index(drop=True)
    out["panel_prior_case_count"] = out.groupby("anchor_wallet").cumcount()
    out["panel_repeat_wallet"] = np.where(out["panel_prior_case_count"] > 0, "repeat", "unseen")
    out["wallet_first_panel_cutoff"] = out.groupby("anchor_wallet")["cutoff_date"].transform("min")
    out = out.sort_values("case_id").reset_index(drop=True)
    return out


def add_intervention_features(frame: pd.DataFrame, llm: pd.DataFrame) -> pd.DataFrame:
    out = frame.merge(llm, on="case_id", validate="one_to_one")
    out["self_sensitivity"] = out[[f"js_{target}_self" for target in TARGETS]].mean(axis=1)
    out["market_sensitivity"] = out[[f"js_{target}_market" for target in TARGETS]].mean(axis=1)
    out["placebo_sensitivity"] = out[[f"js_{target}_placebo" for target in TARGETS]].mean(axis=1)
    out["intervention_sensitivity"] = out[["self_sensitivity", "market_sensitivity"]].mean(axis=1)
    out["intervention_sensitivity_max"] = out[["self_sensitivity", "market_sensitivity"]].max(axis=1)
    out["intervention_sensitivity_min"] = out[["self_sensitivity", "market_sensitivity"]].min(axis=1)
    out["evidence_aligned_intervention_margin"] = out["b4_relevant_minus_placebo"]
    out["evidence_alignment_rate"] = out["b4_alignment_rate"]
    out["b4_kept_mass"] = out["b4_kept_mass"]
    out["b4_gate_pass_flag"] = out["b4_gate_pass"]
    out["llm_abstention_flag"] = (out["llm_abstain"] > 0).astype(int)
    return out


def build_loss_tables(frame: pd.DataFrame, predictions: pd.DataFrame, outcomes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Existing frozen predictions are copied, not recalculated or overwritten.
    merged = frame.merge(predictions, on=["case_id", "anchor_wallet", "cutoff_date", "split", "activity_bin"], validate="one_to_one")
    merged = merged.merge(outcomes[["case_id"] + [f"y_{target}" for target in TARGETS]], on="case_id", validate="one_to_one")

    ll_columns = [f"{model}__{target}__ll" for model in MODELS for target in TARGETS]
    for column in ll_columns:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged["oos_loss_available"] = merged[ll_columns].notna().all(axis=1).astype(int)

    macro_columns = {}
    for model in MODELS:
        columns = [f"{model}__{target}__ll" for target in TARGETS]
        macro_columns[model] = f"{model}__macro_ll"
        merged[macro_columns[model]] = merged[columns].mean(axis=1)
    for model in MODELS[1:]:
        merged[f"delta_{model}_vs_B0_macro"] = merged[macro_columns[model]] - merged[macro_columns["B0_M1"]]
        merged[f"gain_{model}_vs_B0_macro"] = -merged[f"delta_{model}_vs_B0_macro"]

    merged["delta_B4_vs_B0_macro"] = merged["delta_B4_M1_VERIFIED_LLM_vs_B0_macro"]
    merged["gain_B4_vs_B0_macro"] = merged["gain_B4_M1_VERIFIED_LLM_vs_B0_macro"]
    merged["delta_B4_B0_degradation_flag"] = (merged["delta_B4_vs_B0_macro"] > 0).astype("Int64")

    long_rows = []
    for _, row in merged[merged["oos_loss_available"] == 1].iterrows():
        for target in TARGETS:
            entry = {
                "case_id": row["case_id"],
                "anchor_wallet": row["anchor_wallet"],
                "cutoff_date": row["cutoff_date"],
                "split": row["split"],
                "activity_bin": row["activity_bin"],
                "panel_repeat_wallet": row["panel_repeat_wallet"],
                "dominant_event_family_30d": row["dominant_event_family_30d"],
                "target": target,
                "y": row[f"y_{target}"],
                "self_sensitivity": row["self_sensitivity"],
                "market_sensitivity": row["market_sensitivity"],
                "placebo_sensitivity": row["placebo_sensitivity"],
                "intervention_sensitivity": row["intervention_sensitivity"],
                "evidence_aligned_intervention_margin": row["evidence_aligned_intervention_margin"],
            }
            for descriptor_column in [
                "llm_top_probability",
                "llm_probability_margin_top_second",
                "llm_abstain",
                "hypothesis_entropy_nats",
                "hypothesis_entropy_normalized",
                "llm_mean_target_confidence",
                "llm_mean_target_entropy_nats",
                "evidence_claim_count",
                "evidence_unique_count",
                "event_count_7d",
                "history_event_count_30d",
                "active_days_30d",
                "panel_prior_case_count",
            ]:
                entry[descriptor_column] = row[descriptor_column]
            for model in MODELS:
                entry[f"{model}_ll"] = row[f"{model}__{target}__ll"]
            for model in MODELS[1:]:
                entry[f"delta_{model}_vs_B0"] = entry[f"{model}_ll"] - entry["B0_M1_ll"]
                entry[f"gain_{model}_vs_B0"] = -entry[f"delta_{model}_vs_B0"]
            entry["delta_B4_vs_B0"] = entry["delta_B4_M1_VERIFIED_LLM_vs_B0"]
            entry["gain_B4_vs_B0"] = entry["gain_B4_M1_VERIFIED_LLM_vs_B0"]
            long_rows.append(entry)
    long = pd.DataFrame(long_rows)
    return merged, long


def bootstrap_mean(values: np.ndarray, n_boot: int = BOOTSTRAP) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(SEED)
    stats = np.empty(n_boot, dtype=float)
    for index in range(n_boot):
        stats[index] = values[rng.integers(0, len(values), len(values))].mean()
    return float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))


def correlation_row(values_x: pd.Series, values_y: pd.Series, feature: str, outcome: str, scope: str) -> dict:
    data = pd.DataFrame({"x": values_x, "y": values_y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 4 or data.x.nunique() < 2 or data.y.nunique() < 2:
        return {"scope": scope, "outcome": outcome, "feature": feature, "n": len(data)}
    pearson = pearsonr(data.x, data.y)
    spearman = spearmanr(data.x, data.y)
    return {
        "scope": scope,
        "outcome": outcome,
        "feature": feature,
        "n": int(len(data)),
        "pearson_r": float(pearson.statistic),
        "pearson_p": float(pearson.pvalue),
        "spearman_rho": float(spearman.statistic),
        "spearman_p": float(spearman.pvalue),
    }


def make_correlations(case_table: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    numeric_features = [
        "llm_top_probability",
        "llm_probability_margin_top_second",
        "llm_abstain",
        "llm_mean_target_confidence",
        "llm_mean_target_entropy_nats",
        "hypothesis_entropy_nats",
        "hypothesis_entropy_normalized",
        "evidence_claim_count",
        "evidence_unique_count",
        "self_sensitivity",
        "market_sensitivity",
        "placebo_sensitivity",
        "intervention_sensitivity",
        "evidence_aligned_intervention_margin",
        "event_count_7d",
        "history_event_count_30d",
        "active_days_30d",
        "panel_prior_case_count",
    ]
    rows = []
    for scope, subset in [
        ("oos_all", case_table[case_table["oos_loss_available"] == 1]),
        ("dev", case_table[(case_table["oos_loss_available"] == 1) & (case_table["split"] == "dev")]),
        ("test", case_table[(case_table["oos_loss_available"] == 1) & (case_table["split"] == "test")]),
    ]:
        for feature in numeric_features:
            if feature in subset:
                rows.append(correlation_row(subset[feature], subset["gain_B4_vs_B0_macro"], feature, "macro_gain_B4_vs_B0", scope))
    for scope, subset in [
        ("oos_all", long),
        ("dev", long[long["split"] == "dev"]),
        ("test", long[long["split"] == "test"]),
    ]:
        for target in TARGETS:
            target_subset = subset[subset["target"] == target]
            for feature in [
                "self_sensitivity",
                "market_sensitivity",
                "intervention_sensitivity",
                "evidence_aligned_intervention_margin",
                "llm_top_probability",
                "llm_probability_margin_top_second",
                "llm_abstain",
                "llm_mean_target_confidence",
                "llm_mean_target_entropy_nats",
                "hypothesis_entropy_nats",
                "hypothesis_entropy_normalized",
                "evidence_claim_count",
                "event_count_7d",
                "history_event_count_30d",
            ]:
                if feature in target_subset:
                    rows.append(
                        correlation_row(
                            target_subset[feature],
                            target_subset["gain_B4_vs_B0"],
                            feature,
                            f"{target}_gain_B4_vs_B0",
                            scope,
                        )
                    )
    return pd.DataFrame(rows)


def quantile_label(series: pd.Series, q: int = 4) -> pd.Series:
    # Rank first so discrete LLM outputs (e.g. 0.45/0.65) do not collapse
    # a nominal quartile into a one-row bin. Ties can cross bin boundaries,
    # so these are rank-quartiles, not unique-value strata.
    clean = pd.to_numeric(series, errors="coerce")
    try:
        ranks = clean.rank(method="first")
        return pd.qcut(ranks, q=q, labels=[f"Q{i}" for i in range(1, q + 1)]).astype(str)
    except ValueError:
        return pd.Series(["all"] * len(series), index=series.index)


def make_condition_summaries(case_table: pd.DataFrame, long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    macro = case_table[case_table["oos_loss_available"] == 1].copy()
    macro["unit"] = "macro"
    macro["target"] = "macro"
    macro["delta_B4_vs_B0"] = macro["delta_B4_vs_B0_macro"]
    macro["gain_B4_vs_B0"] = macro["gain_B4_vs_B0_macro"]

    long_copy = long.copy()
    long_copy["unit"] = "target"
    data = pd.concat(
        [
            macro[["case_id", "split", "activity_bin", "panel_repeat_wallet", "dominant_event_family_30d", "b4_gate_pass_flag", "llm_abstention_flag", "unit", "target", "delta_B4_vs_B0", "gain_B4_vs_B0"]],
            long_copy[["case_id", "split", "activity_bin", "panel_repeat_wallet", "dominant_event_family_30d", "unit", "target", "delta_B4_vs_B0", "gain_B4_vs_B0"]].assign(b4_gate_pass_flag=np.nan, llm_abstention_flag=np.nan),
        ],
        ignore_index=True,
    )

    condition_columns = [
        "activity_bin",
        "panel_repeat_wallet",
        "dominant_event_family_30d",
        "b4_gate_pass_flag",
        "llm_abstention_flag",
        "split",
        "target",
    ]
    rows = []
    for condition in condition_columns:
        for (level, split, unit, target), group in data.groupby([condition, "split", "unit", "target"], dropna=False):
            if condition == "split":
                # split is already a grouping dimension; avoid a redundant table.
                continue
            delta = group["delta_B4_vs_B0"].to_numpy(float)
            rows.append(
                {
                    "table": "categorical",
                    "condition": condition,
                    "level": str(level),
                    "split": split,
                    "unit": unit,
                    "target": target,
                    "n": len(group),
                    "mean_delta_B4_minus_B0": float(np.mean(delta)),
                    "median_delta_B4_minus_B0": float(np.median(delta)),
                    "degradation_rate_delta_gt_0": float(np.mean(delta > 0)),
                    "severe_degradation_rate_delta_gt_0_1": float(np.mean(delta > 0.1)),
                    "mean_gain_B4_vs_B0": float(np.mean(group["gain_B4_vs_B0"])),
                }
            )

    quantile_features = [
        "llm_top_probability",
        "hypothesis_entropy_nats",
        "intervention_sensitivity",
        "evidence_aligned_intervention_margin",
        "evidence_claim_count",
        "event_count_7d",
        "history_event_count_30d",
    ]
    for feature in quantile_features:
        macro[f"{feature}_quartile"] = quantile_label(macro[feature])
        for target in TARGETS:
            # Quantile cutpoints are computed on the full frozen OOS case table,
            # then reused for each target to keep condition definitions fixed.
            pass
        for level, group in macro.groupby(f"{feature}_quartile", dropna=False):
            delta = group["delta_B4_vs_B0"].to_numpy(float)
            rows.append(
                {
                    "table": "macro_quantile",
                    "condition": feature,
                    "level": str(level),
                    "split": "oos_all",
                    "unit": "macro",
                    "target": "macro",
                    "n": len(group),
                    "mean_delta_B4_minus_B0": float(np.mean(delta)),
                    "median_delta_B4_minus_B0": float(np.median(delta)),
                    "degradation_rate_delta_gt_0": float(np.mean(delta > 0)),
                    "severe_degradation_rate_delta_gt_0_1": float(np.mean(delta > 0.1)),
                    "mean_gain_B4_vs_B0": float(np.mean(group["gain_B4_vs_B0"])),
                }
            )
    categorical = pd.DataFrame(rows)

    target_rows = []
    for target, group in long.groupby("target"):
        for model in MODELS[1:]:
            delta = group[f"delta_{model}_vs_B0"].to_numpy(float)
            target_rows.append(
                {
                    "target": target,
                    "model": model,
                    "n": len(group),
                    "mean_delta": float(np.mean(delta)),
                    "median_delta": float(np.median(delta)),
                    "degradation_rate": float(np.mean(delta > 0)),
                    "severe_degradation_rate_gt_0_1": float(np.mean(delta > 0.1)),
                    "mean_gain": float(np.mean(-delta)),
                }
            )
    target_summary = pd.DataFrame(target_rows)
    return categorical, target_summary


def make_model_summary(case_table: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model in MODELS[1:]:
        macro_delta = case_table[f"delta_{model}_vs_B0_macro"]
        for split, subset in [("oos_all", case_table[case_table.oos_loss_available == 1]), ("dev", case_table[(case_table.oos_loss_available == 1) & (case_table.split == "dev")]), ("test", case_table[(case_table.oos_loss_available == 1) & (case_table.split == "test")])]:
            values = subset[f"delta_{model}_vs_B0_macro"].to_numpy(float)
            low, high = bootstrap_mean(values)
            rows.append(
                {
                    "unit": "macro",
                    "split": split,
                    "model": model,
                    "target": "macro",
                    "n": len(values),
                    "mean_delta_model_minus_B0": float(np.mean(values)),
                    "median_delta_model_minus_B0": float(np.median(values)),
                    "degradation_rate_delta_gt_0": float(np.mean(values > 0)),
                    "severe_degradation_rate_delta_gt_0_1": float(np.mean(values > 0.1)),
                    "mean_gain_model_vs_B0": float(np.mean(-values)),
                    "mean_delta_bootstrap_ci_low": low,
                    "mean_delta_bootstrap_ci_high": high,
                }
            )
        for target in TARGETS:
            for split, subset in [("oos_all", long[long.target == target]), ("dev", long[(long.target == target) & (long.split == "dev")]), ("test", long[(long.target == target) & (long.split == "test")])]:
                values = subset[f"delta_{model}_vs_B0"].to_numpy(float)
                low, high = bootstrap_mean(values)
                rows.append(
                    {
                        "unit": "target",
                        "split": split,
                        "model": model,
                        "target": target,
                        "n": len(values),
                        "mean_delta_model_minus_B0": float(np.mean(values)),
                        "median_delta_model_minus_B0": float(np.median(values)),
                        "degradation_rate_delta_gt_0": float(np.mean(values > 0)),
                        "severe_degradation_rate_delta_gt_0_1": float(np.mean(values > 0.1)),
                        "mean_gain_model_vs_B0": float(np.mean(-values)),
                        "mean_delta_bootstrap_ci_low": low,
                        "mean_delta_bootstrap_ci_high": high,
                    }
                )
    return pd.DataFrame(rows)


def annotate_corr(ax, x: pd.Series, y: pd.Series, prefix: str = "") -> None:
    clean = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 4 or clean.x.nunique() < 2 or clean.y.nunique() < 2:
        ax.text(0.03, 0.97, "correlation unavailable", transform=ax.transAxes, va="top", fontsize=9)
        return
    rho = spearmanr(clean.x, clean.y).statistic
    r = pearsonr(clean.x, clean.y).statistic
    ax.text(0.03, 0.97, f"n={len(clean)}\nPearson r={r:.3f}\nSpearman ρ={rho:.3f}", transform=ax.transAxes, va="top", fontsize=9, bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"})


def plot_intervention_gain(case_table: pd.DataFrame, long: pd.DataFrame) -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    test = case_table[(case_table.oos_loss_available == 1) & (case_table.split == "test")].copy()
    all_oos = case_table[case_table.oos_loss_available == 1].copy()
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True)
    panels = [
        (axes[0, 0], test, "intervention_sensitivity", "gain_B4_vs_B0_macro", "Test: raw intervention sensitivity", "B4 predictive gain (−Δ)") ,
        (axes[0, 1], test, "evidence_aligned_intervention_margin", "gain_B4_vs_B0_macro", "Test: evidence-aligned intervention margin", "B4 predictive gain (−Δ)"),
        (axes[1, 0], all_oos, "intervention_sensitivity", "gain_B4_vs_B0_macro", "Dev + test: raw intervention sensitivity", "B4 predictive gain (−Δ)"),
    ]
    for ax, data, x_col, y_col, title, ylabel in panels:
        colors = np.where(data["split"].eq("test"), "#c23b22", "#4c78a8")
        ax.scatter(data[x_col], data[y_col], s=14, alpha=0.32, c=colors, edgecolors="none")
        ax.axhline(0, color="black", linewidth=0.9, linestyle="--")
        ax.set_title(title)
        ax.set_xlabel(x_col)
        ax.set_ylabel(ylabel)
        annotate_corr(ax, data[x_col], data[y_col])
    # Target-level panel, using the same frozen target-level losses.
    ax = axes[1, 1]
    colors = {target: color for target, color in zip(TARGETS, ["#4c78a8", "#f58518", "#54a24b", "#b279a2"])}
    for target in TARGETS:
        subset = long[(long.split == "test") & (long.target == target)]
        ax.scatter(subset["intervention_sensitivity"], subset["gain_B4_vs_B0"], s=10, alpha=0.22, c=colors[target], label=target, edgecolors="none")
    ax.axhline(0, color="black", linewidth=0.9, linestyle="--")
    ax.set_title("Test: target-level intervention sensitivity")
    ax.set_xlabel("intervention_sensitivity")
    ax.set_ylabel("B4 predictive gain (−Δ)")
    ax.legend(fontsize=8, frameon=True)
    annotate_corr(ax, long.loc[long.split == "test", "intervention_sensitivity"], long.loc[long.split == "test", "gain_B4_vs_B0"])
    fig.suptitle("Frozen predictions only: intervention sensitivity vs B4 predictive gain", fontsize=14)
    fig.savefig(PLOT_DIR / "intervention_sensitivity_vs_b4_gain.png", dpi=180)
    plt.close(fig)


def plot_model_degradation(target_summary: pd.DataFrame, model_summary: pd.DataFrame) -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    test_target = target_summary.copy()
    # target_summary is OOS only; recompute test from model_summary is not target-level.
    # Build a compact test target table from model_summary rows.
    rows = []
    for _, row in model_summary[(model_summary.unit == "target") & (model_summary.split == "test")].iterrows():
        rows.append(row)
    test_target = pd.DataFrame(rows)
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    pivot = test_target.pivot(index="target", columns="model", values="mean_delta_model_minus_B0").reindex(TARGETS)
    pivot.plot(kind="bar", ax=axes[0], color=["#f58518", "#54a24b", "#b279a2", "#e45756"], width=0.78)
    axes[0].axhline(0, color="black", linewidth=0.9)
    axes[0].set_title("Test target-level degradation vs B0")
    axes[0].set_ylabel("mean Δ = loss(model) − loss(B0)")
    axes[0].tick_params(axis="x", rotation=25)
    axes[0].legend(fontsize=8)

    macro = model_summary[(model_summary.unit == "macro") & (model_summary.split == "test")].copy()
    axes[1].bar(macro["model"], macro["mean_delta_model_minus_B0"], color=["#f58518", "#54a24b", "#b279a2", "#e45756"])
    axes[1].axhline(0, color="black", linewidth=0.9)
    axes[1].set_title("Test macro degradation vs B0")
    axes[1].set_ylabel("mean Δ = loss(model) − loss(B0)")
    axes[1].tick_params(axis="x", rotation=30)
    fig.suptitle("Where B1–B4 degrade relative to the frozen M1 baseline", fontsize=14)
    fig.savefig(PLOT_DIR / "model_degradation_by_target.png", dpi=180)
    plt.close(fig)


def plot_condition_bars(condition_summary: pd.DataFrame) -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    test = condition_summary[(condition_summary.table == "categorical") & (condition_summary.split == "test") & (condition_summary.unit == "macro") & (condition_summary.target == "macro")]
    conditions = ["activity_bin", "panel_repeat_wallet", "dominant_event_family_30d"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    for ax, condition in zip(axes, conditions):
        subset = test[test.condition == condition].copy()
        ax.bar(subset.level, subset.mean_delta_B4_minus_B0, color="#e45756")
        ax.axhline(0, color="black", linewidth=0.9)
        ax.set_title(condition)
        ax.set_ylabel("mean B4 − B0 log loss")
        ax.tick_params(axis="x", rotation=30)
        for x, (_, row) in enumerate(subset.iterrows()):
            ax.text(x, row.mean_delta_B4_minus_B0, f"n={int(row.n)}", ha="center", va="bottom" if row.mean_delta_B4_minus_B0 >= 0 else "top", fontsize=8)
    fig.suptitle("Frozen test degradation by address condition", fontsize=14)
    fig.savefig(PLOT_DIR / "b4_degradation_by_condition.png", dpi=180)
    plt.close(fig)


def plot_correlation_heatmap(correlations: pd.DataFrame) -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    subset = correlations[(correlations.scope == "test") & (correlations.outcome == "macro_gain_B4_vs_B0")].copy()
    feature_order = [
        "llm_top_probability",
        "hypothesis_entropy_nats",
        "llm_abstain",
        "evidence_claim_count",
        "self_sensitivity",
        "market_sensitivity",
        "intervention_sensitivity",
        "evidence_aligned_intervention_margin",
        "event_count_7d",
        "history_event_count_30d",
        "panel_prior_case_count",
    ]
    subset = subset.set_index("feature").reindex(feature_order).reset_index()
    values = subset["spearman_rho"].to_numpy(float).reshape(-1, 1)
    fig, ax = plt.subplots(figsize=(6, 8), constrained_layout=True)
    image = ax.imshow(values, cmap="coolwarm", vmin=-1, vmax=1, aspect="auto")
    ax.set_yticks(range(len(feature_order)), feature_order)
    ax.set_xticks([0], ["test macro gain"])
    for i, value in enumerate(values[:, 0]):
        if np.isfinite(value):
            ax.text(0, i, f"{value:.3f}", ha="center", va="center", color="black", fontsize=9)
    ax.set_title("Test Spearman correlations with B4 predictive gain")
    fig.colorbar(image, ax=ax, label="Spearman ρ")
    fig.savefig(PLOT_DIR / "test_gain_correlation_heatmap.png", dpi=180)
    plt.close(fig)


def main() -> None:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    prompt = pd.read_csv(RES / "decision_state_prompt_cases.csv", low_memory=False)
    llm = pd.read_csv(RES / "decision_state_llm_features.csv", low_memory=False)
    predictions = pd.read_csv(RES / "decision_state_meta_predictions.csv", low_memory=False)
    outcomes = pd.read_csv(RES / "decision_state_eval_cases.csv", low_memory=False)

    assert len(prompt) == 3000, len(prompt)
    assert len(llm) == 3000, len(llm)
    assert len(predictions) == 3000, len(predictions)
    assert prompt["case_id"].is_unique and llm["case_id"].is_unique and predictions["case_id"].is_unique

    descriptors = load_panel_descriptors()
    assert len(descriptors) == 3000, len(descriptors)
    frame = make_family_and_repeat_features(prompt)
    frame = frame.merge(descriptors, on="case_id", validate="one_to_one")
    frame = add_intervention_features(frame, llm)
    case_table, long = build_loss_tables(frame, predictions, outcomes)

    case_table.to_csv(RES / "decision_state_case_degradation_analysis.csv", index=False)
    long.to_csv(RES / "decision_state_loss_delta_long.csv", index=False)

    model_summary = make_model_summary(case_table, long)
    model_summary.to_csv(RES / "decision_state_degradation_summary.csv", index=False)
    top_case_columns = [
        "case_id", "anchor_wallet", "cutoff_date", "split", "activity_bin",
        "panel_repeat_wallet", "dominant_event_family_30d", "event_count_7d",
        "history_event_count_30d", "llm_top_probability", "hypothesis_entropy_nats",
        "llm_abstain", "b4_gate_pass_flag", "self_sensitivity",
        "market_sensitivity", "intervention_sensitivity",
        "evidence_aligned_intervention_margin", "delta_B4_vs_B0_macro",
        "gain_B4_vs_B0_macro",
    ]
    test_cases = case_table[(case_table["split"] == "test") & (case_table["oos_loss_available"] == 1)]
    test_cases.sort_values("delta_B4_vs_B0_macro", ascending=False)[top_case_columns].head(100).to_csv(RES / "decision_state_top_100_degradation_cases.csv", index=False)
    test_cases.sort_values("delta_B4_vs_B0_macro", ascending=True)[top_case_columns].head(100).to_csv(RES / "decision_state_top_100_gain_cases.csv", index=False)
    categorical_summary, target_summary = make_condition_summaries(case_table, long)
    categorical_summary.to_csv(RES / "decision_state_degradation_by_condition.csv", index=False)
    target_summary.to_csv(RES / "decision_state_degradation_by_target.csv", index=False)
    correlations = make_correlations(case_table, long)
    correlations.to_csv(RES / "decision_state_gain_correlations.csv", index=False)

    plot_intervention_gain(case_table, long)
    plot_model_degradation(target_summary, model_summary)
    plot_condition_bars(categorical_summary)
    plot_correlation_heatmap(correlations)

    available = case_table[case_table["oos_loss_available"] == 1]
    manifest = {
        "analysis_protocol": "frozen_prediction_degradation_v1",
        "prediction_files_read_only": True,
        "prompt_cases": int(len(prompt)),
        "descriptor_cases": int(len(case_table)),
        "oos_loss_cases": int(len(available)),
        "train_cases_without_existing_oos_predictions": int((case_table["oos_loss_available"] == 0).sum()),
        "loss_rows": int(len(long)),
        "target_rows_per_oos_case": len(TARGETS),
        "prediction_sha256": sha256_file(RES / "decision_state_meta_predictions.csv"),
        "prompt_sha256": sha256_file(RES / "decision_state_prompt_cases.csv"),
        "llm_features_sha256": sha256_file(RES / "decision_state_llm_features.csv"),
        "panel_sha256": sha256_file(RES / "hypothesis_panel_full.jsonl"),
        "note": "All 3,000 frozen cases are retained in case_degradation_analysis.csv. Delta/loss analyses use only the 2,000 rows with pre-existing July/August out-of-sample predictions; June train rows are not assigned newly generated in-sample losses.",
        "plots": sorted(str(path.relative_to(RES)) for path in PLOT_DIR.glob("*.png")),
        "top_case_tables": [
            "decision_state_top_100_degradation_cases.csv",
            "decision_state_top_100_gain_cases.csv",
        ],
    }
    (RES / "decision_state_degradation_analysis_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print("\nMODEL SUMMARY: test macro")
    print(model_summary[(model_summary.unit == "macro") & (model_summary.split == "test")].to_string(index=False))
    print("\nKEY TEST CORRELATIONS")
    print(correlations[(correlations.scope == "test") & (correlations.outcome == "macro_gain_B4_vs_B0")].to_string(index=False))


if __name__ == "__main__":
    main()
