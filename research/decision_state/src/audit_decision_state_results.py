#!/usr/bin/env python3
"""Post-freeze audit for the Decision-State V1 effectiveness gate.

This script does not tune prompts, thresholds, feature sets, or model
hyperparameters. It only audits the already-frozen panel and evaluator
artifacts, computes the preregistered intervention summaries, and writes
stratified/paired diagnostics for the final scientific decision.
"""
from __future__ import annotations
import os

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, f1_score, log_loss

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[3]))
RES = ROOT / "research/decision_state/results"
TARGETS = ["activity", "active_days", "counterparty_breadth", "new_counterparties"]
CLASSES = ["down", "same", "up"]
VARIANTS = ["full", "minus_self", "minus_market", "placebo"]
KNOWN_EVIDENCE = {"E_SELF", "E_MARKET", "E_COVERAGE", "E_PLACEBO"}
BOOTSTRAP = 5000
SEED = 42


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize(values) -> np.ndarray:
    p = np.asarray(values, dtype=float)
    p = np.where(np.isfinite(p) & (p >= 0), p, 0.0)
    total = float(p.sum())
    return p / total if total > 0 else np.ones(len(p), dtype=float) / len(p)


def parse_hypotheses(record: dict | None) -> list[dict]:
    if not record or not record.get("parse_valid"):
        return []
    parsed = record.get("parsed")
    if not isinstance(parsed, dict):
        return []
    valid = []
    for h in parsed.get("hypotheses", [])[:3]:
        if not isinstance(h, dict):
            continue
        try:
            probability = max(0.0, float(h.get("probability", 0.0)))
        except (TypeError, ValueError):
            continue
        consequences = h.get("consequences")
        evidence_ids = h.get("evidence_ids", [])
        if not isinstance(consequences, dict):
            continue
        if any(consequences.get(target) not in CLASSES for target in TARGETS):
            continue
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        valid.append(
            {
                "id": str(h.get("id", "")),
                "probability": probability,
                "consequences": consequences,
                "evidence_ids": {str(x) for x in evidence_ids},
            }
        )
    if not valid:
        return []
    probabilities = normalize([h["probability"] for h in valid])
    for h, probability in zip(valid, probabilities):
        h["probability"] = float(probability)
    return valid


def consequence_distribution(hypotheses: list[dict], target: str) -> np.ndarray:
    if not hypotheses:
        return np.ones(3, dtype=float) / 3.0
    distribution = np.zeros(3, dtype=float)
    for h in hypotheses:
        distribution[CLASSES.index(h["consequences"][target])] += h["probability"]
    return normalize(distribution)


def js_distance(p, q) -> float:
    p = normalize(p)
    q = normalize(q)
    midpoint = (p + q) / 2.0

    def kl(a, b):
        total = 0.0
        for ai, bi in zip(a, b):
            if ai > 0:
                total += float(ai * np.log2(ai / max(float(bi), 1e-12)))
        return total

    return 0.5 * kl(p, midpoint) + 0.5 * kl(q, midpoint)


def bootstrap_ci(values: np.ndarray, statistic: str = "mean") -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(SEED)
    # Match the evaluator's address-bootstrap draw order exactly so the
    # primary CI is reproducible from decision_state_bootstrap.csv.
    stats = np.empty(BOOTSTRAP, dtype=float)
    for i in range(BOOTSTRAP):
        sample = values[rng.integers(0, len(values), len(values))]
        stats[i] = np.median(sample) if statistic == "median" else np.mean(sample)
    return float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))


def intervention_table(records: dict[tuple[str, str], dict]) -> pd.DataFrame:
    case_ids = sorted({case_id for case_id, _ in records})
    rows = []
    for case_id in case_ids:
        raw_full = records.get((case_id, "full"), {})
        full = parse_hypotheses(raw_full)
        variants = {variant: parse_hypotheses(records.get((case_id, variant))) for variant in VARIANTS}
        row = {
            "case_id": case_id,
            "full_parse_valid": int(bool(raw_full.get("parse_valid"))),
            "full_valid_hypotheses": len(full),
            "full_raw_hypotheses": len((raw_full.get("parsed") or {}).get("hypotheses", []))
            if isinstance(raw_full.get("parsed"), dict)
            else 0,
            "full_abstain_probability": float((raw_full.get("parsed") or {}).get("abstain_probability", 0.0))
            if isinstance(raw_full.get("parsed"), dict)
            else 0.0,
        }
        all_evidence = set()
        for h in full:
            all_evidence.update(h["evidence_ids"])
        row["full_has_e_self"] = int(any("E_SELF" in h["evidence_ids"] for h in full))
        row["full_has_e_market"] = int(any("E_MARKET" in h["evidence_ids"] for h in full))
        row["full_has_e_coverage"] = int(any("E_COVERAGE" in h["evidence_ids"] for h in full))
        row["full_has_e_placebo"] = int(any("E_PLACEBO" in h["evidence_ids"] for h in full))
        row["full_unknown_evidence_ids"] = int(len(all_evidence - KNOWN_EVIDENCE))

        for target in TARGETS:
            full_q = consequence_distribution(full, target)
            row[f"r_self_{target}"] = js_distance(
                full_q, consequence_distribution(variants["minus_self"], target)
            )
            row[f"r_market_{target}"] = js_distance(
                full_q, consequence_distribution(variants["minus_market"], target)
            )
            row[f"r_placebo_{target}"] = js_distance(
                full_q, consequence_distribution(variants["placebo"], target)
            )

        for group, prefix in [("E_SELF", "self"), ("E_MARKET", "market")]:
            claimed = [h for h in full if group in h["evidence_ids"]]
            row[f"{prefix}_claimed_hypotheses"] = len(claimed)
            # The response is the same evidence-group perturbation for the
            # address; only cases that make that claim enter this summary.
            if claimed:
                row[f"relevant_{prefix}"] = float(
                    np.mean([row[f"r_{prefix}_{target}"] for target in TARGETS])
                )
                row[f"placebo_{prefix}"] = float(
                    np.mean([row[f"r_placebo_{target}"] for target in TARGETS])
                )
                row[f"diff_{prefix}"] = row[f"relevant_{prefix}"] - row[f"placebo_{prefix}"]
            else:
                row[f"relevant_{prefix}"] = np.nan
                row[f"placebo_{prefix}"] = np.nan
                row[f"diff_{prefix}"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def intervention_summary(interventions: pd.DataFrame, split: str, scope: str) -> list[dict]:
    if scope == "all":
        subset = interventions[interventions["split"] == split]
    else:
        subset = interventions[(interventions["split"] == split) & (interventions["activity_stratum"] == scope)]
    rows = []
    for prefix, evidence in [("self", "E_SELF"), ("market", "E_MARKET")]:
        claimed = subset[subset[f"{prefix}_claimed_hypotheses"] > 0]
        diff = claimed[f"diff_{prefix}"].dropna().to_numpy(float)
        relevant = claimed[f"relevant_{prefix}"].dropna().to_numpy(float)
        placebo = claimed[f"placebo_{prefix}"].dropna().to_numpy(float)
        if len(diff):
            mean_ci = bootstrap_ci(diff, "mean")
            median_ci = bootstrap_ci(diff, "median")
            rows.append(
                {
                    "split": split,
                    "scope": scope,
                    "evidence_group": evidence,
                    "n_all": int(len(subset)),
                    "n_claimed": int(len(diff)),
                    "claim_rate": float(len(diff) / len(subset)) if len(subset) else 0.0,
                    "median_relevant_response": float(np.median(relevant)),
                    "median_placebo_response": float(np.median(placebo)),
                    "median_diff": float(np.median(diff)),
                    "median_diff_ci_low": median_ci[0],
                    "median_diff_ci_high": median_ci[1],
                    "mean_diff": float(np.mean(diff)),
                    "mean_diff_ci_low": mean_ci[0],
                    "mean_diff_ci_high": mean_ci[1],
                    "positive_diff_rate": float(np.mean(diff > 0)),
                    "gate_pass": bool(
                        np.median(relevant) > np.median(placebo) and mean_ci[0] > 0
                    ),
                }
            )
        else:
            rows.append(
                {
                    "split": split,
                    "scope": scope,
                    "evidence_group": evidence,
                    "n_all": int(len(subset)),
                    "n_claimed": 0,
                    "claim_rate": 0.0,
                    "gate_pass": False,
                }
            )
    return rows


def metric_rows(predictions: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.merge(outcomes, on="case_id", validate="one_to_one")
    frame["activity_stratum"] = np.where(
        frame["activity_bin"].isin(["1-2", "3-9"]), "low_activity", "active"
    )
    frame["stratum"] = frame["activity_stratum"]
    rows = []
    for split in ["dev", "test"]:
        split_frame = frame[frame["split"] == split]
        scoped = [("all", split_frame)]
        scoped.extend((name, split_frame[split_frame["activity_stratum"] == name]) for name in ["low_activity", "active"])
        scoped.extend((f"bin_{b}", split_frame[split_frame["activity_bin"] == b]) for b in ["1-2", "3-9", "10-19", "20+"])
        for scope, subset in scoped:
            for model in ["B0_M1", "B1_M1_DETERMINISTIC", "B2_M1_SINGLE_LLM", "B3_M1_MULTI_LLM", "B4_M1_VERIFIED_LLM"]:
                for target in TARGETS:
                    probability_columns = [f"{model}__{target}__p_{c}" for c in CLASSES]
                    if not all(column in subset for column in probability_columns):
                        continue
                    p = subset[probability_columns].to_numpy(float)
                    y = np.array([CLASSES.index(value) for value in subset[f"y_{target}"]])
                    one_hot = np.eye(3)[y]
                    predicted = np.argmax(p, axis=1)
                    rows.append(
                        {
                            "split": split,
                            "scope": scope,
                            "model": model,
                            "target": target,
                            "n": int(len(subset)),
                            "log_loss": float(log_loss(y, p, labels=[0, 1, 2])),
                            "brier": float(np.mean(np.sum((p - one_hot) ** 2, axis=1))),
                            "balanced_accuracy": float(
                                balanced_accuracy_score(y, predicted)
                            ),
                            "macro_f1": float(
                                f1_score(
                                    [CLASSES[i] for i in y],
                                    [CLASSES[i] for i in predicted],
                                    labels=CLASSES,
                                    average="macro",
                                    zero_division=0,
                                )
                            ),
                        }
                    )
    return pd.DataFrame(rows)


def paired_bootstrap_rows(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    comparisons = [
        ("B0_M1", "B4_M1_VERIFIED_LLM"),
        ("B2_M1_SINGLE_LLM", "B4_M1_VERIFIED_LLM"),
        ("B0_M1", "B3_M1_MULTI_LLM"),
    ]
    test = predictions[predictions["split"] == "test"].copy()
    for model_a, model_b in comparisons:
        for target in TARGETS + ["macro"]:
            if target == "macro":
                a_columns = [f"{model_a}__{t}__ll" for t in TARGETS]
                b_columns = [f"{model_b}__{t}__ll" for t in TARGETS]
                a = test[a_columns].mean(axis=1).to_numpy(float)
                b = test[b_columns].mean(axis=1).to_numpy(float)
            else:
                a = test[f"{model_a}__{target}__ll"].to_numpy(float)
                b = test[f"{model_b}__{target}__ll"].to_numpy(float)
            diff = a - b  # positive means model A has lower loss than model B
            low, high = bootstrap_ci(diff, "mean")
            rows.append(
                {
                    "split": "test",
                    "comparison": f"{model_a}_vs_{model_b}",
                    "target": target,
                    "n": int(len(diff)),
                    "estimate_a_minus_b": float(np.mean(diff)),
                    "ci_low": low,
                    "ci_high": high,
                    "fraction_a_lower_loss": float(np.mean(diff > 0)),
                    "better_positive": True,
                    "pass_if_ci_low_gt_zero": bool(low > 0),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    records = {}
    with (RES / "hypothesis_panel_full.jsonl").open() as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                records[(record["case_id"], record["variant"])] = record

    interventions = intervention_table(records)
    prompt = pd.read_csv(
        RES / "decision_state_prompt_cases.csv",
        usecols=["case_id", "split", "activity_bin", "cutoff_date"],
    )
    interventions = prompt.merge(interventions, on="case_id", validate="one_to_one")
    interventions["activity_stratum"] = np.where(
        interventions["activity_bin"].isin(["1-2", "3-9"]), "low_activity", "active"
    )
    interventions.to_csv(RES / "decision_state_intervention_case_metrics.csv", index=False)

    summary_rows = []
    for split in ["dev", "test"]:
        for scope in ["all", "low_activity", "active"]:
            summary_rows.extend(intervention_summary(interventions, split, scope))
    intervention_summary_frame = pd.DataFrame(summary_rows)
    intervention_summary_frame.to_csv(RES / "decision_state_intervention_summary.csv", index=False)

    predictions = pd.read_csv(RES / "decision_state_meta_predictions.csv", low_memory=False)
    outcomes = pd.read_csv(
        RES / "decision_state_eval_cases.csv",
        usecols=["case_id"] + [f"y_{target}" for target in TARGETS],
    )
    metrics = metric_rows(predictions, outcomes)
    metrics.to_csv(RES / "decision_state_stratum_metrics.csv", index=False)
    paired = paired_bootstrap_rows(predictions)
    paired.to_csv(RES / "decision_state_per_target_bootstrap.csv", index=False)

    llm_features = pd.read_csv(RES / "decision_state_llm_features.csv", low_memory=False)
    llm_features = llm_features.merge(prompt, on="case_id", validate="one_to_one")
    llm_features["activity_stratum"] = np.where(
        llm_features["activity_bin"].isin(["1-2", "3-9"]), "low_activity", "active"
    )
    gate_rows = []
    for split in ["train", "dev", "test"]:
        for scope, subset in [("all", llm_features[llm_features.split == split])]:
            gate_rows.append(
                {
                    "split": split,
                    "scope": scope,
                    "n": int(len(subset)),
                    "b4_gate_pass_rate": float(subset["b4_gate_pass"].mean()),
                    "b4_abstention_rate": float(1.0 - subset["b4_gate_pass"].mean()),
                    "mean_alignment_rate": float(subset["b4_alignment_rate"].mean()),
                    "mean_relevant_minus_placebo": float(subset["b4_relevant_minus_placebo"].mean()),
                }
            )
        for scope in ["low_activity", "active"]:
            subset = llm_features[(llm_features.split == split) & (llm_features.activity_stratum == scope)]
            gate_rows.append(
                {
                    "split": split,
                    "scope": scope,
                    "n": int(len(subset)),
                    "b4_gate_pass_rate": float(subset["b4_gate_pass"].mean()),
                    "b4_abstention_rate": float(1.0 - subset["b4_gate_pass"].mean()),
                    "mean_alignment_rate": float(subset["b4_alignment_rate"].mean()),
                    "mean_relevant_minus_placebo": float(subset["b4_relevant_minus_placebo"].mean()),
                }
            )
    pd.DataFrame(gate_rows).to_csv(RES / "decision_state_gate_signal_summary.csv", index=False)

    # Panel/schema quality audit. This is operational validity, not an
    # effectiveness claim.
    full_records = [records[(case_id, "full")] for case_id in sorted({key[0] for key in records})]
    variant_counts = {
        variant: sum(1 for case_id in {key[0] for key in records} if records.get((case_id, variant), {}).get("parse_valid"))
        for variant in VARIANTS
    }
    full_hyp = interventions["full_valid_hypotheses"]
    quality = {
        "panel_records": int(len(records)),
        "panel_cases": int(len(full_records)),
        "parse_valid_by_variant": variant_counts,
        "parse_valid_rate_by_variant": {k: v / len(full_records) for k, v in variant_counts.items()},
        "full_valid_hypothesis_count": {str(k): int(v) for k, v in full_hyp.value_counts().sort_index().items()},
        "full_exact_three_rate": float((full_hyp == 3).mean()),
        "full_abstain_probability_mean": float(interventions["full_abstain_probability"].mean()),
        "full_abstain_probability_nonzero_rate": float((interventions["full_abstain_probability"] > 0).mean()),
        "full_claim_e_self_rate": float(interventions["full_has_e_self"].mean()),
        "full_claim_e_market_rate": float(interventions["full_has_e_market"].mean()),
        "full_claim_e_coverage_rate": float(interventions["full_has_e_coverage"].mean()),
        "full_claim_e_placebo_rate": float(interventions["full_has_e_placebo"].mean()),
        "full_unknown_evidence_case_rate": float((interventions["full_unknown_evidence_ids"] > 0).mean()),
        "full_e_placebo_case_rate": float((interventions["full_has_e_placebo"] > 0).mean()),
        "panel_sha256": sha256_file(RES / "hypothesis_panel_full.jsonl"),
    }
    (RES / "decision_state_result_quality.json").write_text(
        json.dumps(quality, indent=2, ensure_ascii=False) + "\n"
    )

    # Machine-readable gate summary. The evaluator's macro bootstrap remains
    # the primary estimand; this file only makes all gates explicit.
    primary = paired[(paired.comparison == "B0_M1_vs_B4_M1_VERIFIED_LLM") & (paired.target == "macro")].iloc[0]
    secondary = paired[(paired.comparison == "B2_M1_SINGLE_LLM_vs_B4_M1_VERIFIED_LLM") & (paired.target == "macro")].iloc[0]
    dev_intervention = intervention_summary_frame[
        (intervention_summary_frame.split == "dev") & (intervention_summary_frame.scope == "all")
    ]
    intervention_pass_groups = int(dev_intervention["gate_pass"].sum())
    input_audit = json.loads((RES / "decision_state_input_audit.json").read_text())
    gate_summary = {
        "primary_gate": {
            "estimate_b0_minus_b4": float(primary.estimate_a_minus_b),
            "ci_low": float(primary.ci_low),
            "ci_high": float(primary.ci_high),
            "pass": bool(primary.pass_if_ci_low_gt_zero),
        },
        "secondary_b4_vs_b2": {
            "estimate_b2_minus_b4": float(secondary.estimate_a_minus_b),
            "ci_low": float(secondary.ci_low),
            "ci_high": float(secondary.ci_high),
            "pass_by_predictive_log_loss": bool(secondary.pass_if_ci_low_gt_zero),
        },
        "development_intervention_gate": {
            "groups_passing": intervention_pass_groups,
            "required_groups": 2,
            "pass": bool(intervention_pass_groups >= 2),
        },
        "input_leakage_audit": input_audit,
        "overall_effectiveness_pass": bool(
            primary.pass_if_ci_low_gt_zero and secondary.pass_if_ci_low_gt_zero and intervention_pass_groups >= 2
        ),
        "decision": "PASS" if primary.pass_if_ci_low_gt_zero and secondary.pass_if_ci_low_gt_zero and intervention_pass_groups >= 2 else "NO-GO",
    }
    (RES / "decision_state_gate_summary.json").write_text(
        json.dumps(gate_summary, indent=2, ensure_ascii=False, default=lambda x: bool(x)) + "\n"
    )

    print(json.dumps(gate_summary, indent=2, ensure_ascii=False, default=lambda x: bool(x)))
    print("\nINTERVENTION SUMMARY (dev/all)")
    print(dev_intervention.to_string(index=False))
    print("\nPRIMARY/SECONDARY BOOTSTRAP")
    print(paired[paired.target == "macro"].to_string(index=False))


if __name__ == "__main__":
    main()
