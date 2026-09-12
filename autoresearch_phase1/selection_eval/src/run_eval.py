"""Run the budgeted wallet-selection evaluation at cutoff 2022-09-01.

Outputs (all under research/selection_eval/results/):
  - budget_frontier.csv               long-format frontier for every selector x K
  - selection_results_20220901.json   structured results (frontier, restricted,
                                      oracle reference, support boundaries, overlap)
  - manifest.json                     selector/support provenance + leakage notes
Usage: .venv-cuda/bin/python research/selection_eval/src/run_eval.py
"""
from __future__ import annotations
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as E
import load_data as L
import selector_defs as S

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")


def jaccard_topk(base: pd.DataFrame, key_a: str, key_b: str, k: int) -> float:
    a = set(S.get_topk(base, key_a, k)["target_address"])
    b = set(S.get_topk(base, key_b, k)["target_address"])
    return len(a & b) / len(a | b) if (a | b) else float("nan")


def main() -> None:
    t0 = time.time()
    raw = L.load_all()
    base, meta = L.assemble_scores(raw)
    base = S.add_random(base, seed=20220901)

    # support masks
    full_mask = base["lbl_new"].notna()
    usd_mask = base["vol_usd"].notna()
    struct_mask = base["deg_und"].notna()
    ig_mask = base["ig_cp"].notna()

    # ---- native-support frontier ----
    rows = []
    for key in S.selector_keys():
        for k in E.KS:
            rows.append(E.evaluate_selector(base, key, k, S.SELECTORS[key]["scope"]))
    rows += E.random_expected_rows(base, full_mask, "full")
    rows += E.oracle_rows(base, full_mask, "full")
    rows += E.oracle_rows(base, struct_mask, "structural")
    rows += E.oracle_rows(base, ig_mask, "ig")

    # ---- restricted-support comparisons (apples-to-apples) ----
    struct_keys = [k for k in S.selector_keys() if base[S.SELECTORS[k]["score"]].notna().sum() >= 1000]
    for k in E.KS:
        rows += E.evaluate_restricted(base, struct_keys, struct_mask, "structural_restricted", k)
        rows += E.evaluate_restricted(base, struct_keys, ig_mask, "ig_restricted", k)

    frontier = pd.DataFrame(rows)
    frontier = frontier.sort_values(["selector", "k"]).reset_index(drop=True)
    frontier.to_csv(os.path.join(RES, "budget_frontier.csv"), index=False)

    # ---- support boundaries ----
    supports = {
        "full": E.support_metrics(base, full_mask, base["lbl_new"], "full"),
        "usd": E.support_metrics(base, usd_mask, base["lbl_new"], "usd"),
        "structural": E.support_metrics(base, struct_mask, base["lbl_new"], "structural"),
        "ig": E.support_metrics(base, ig_mask, base["lbl_new"], "ig"),
    }

    # ---- top-K overlap across selectors (native supports, K=100/1000) ----
    keys = S.selector_keys()
    overlap = {}
    for k in (100, 1000):
        mat = pd.DataFrame(np.nan, index=keys, columns=keys)
        for a in keys:
            for b in keys:
                mat.loc[a, b] = jaccard_topk(base, a, b, k)
        overlap[str(k)] = {
            "keys": keys,
            "jaccard": mat.round(4).to_dict(),
        }

    # ---- JSON summary ----
    sel_summary = {}
    for key in S.selector_keys():
        spec = S.SELECTORS[key]
        n_sup = int(base[spec["score"]].notna().sum())
        sc = base.dropna(subset=[spec["score"]])[spec["score"]]
        if spec["score"] == "score_recency":
            sc = 90.0 - sc
        elif spec["score"] == "score_random":
            sc = sc
        tie = {}
        if len(sc) and sc.nunique() < len(sc):
            top_score = sc.max()
            tie = {"score_nunique": int(sc.nunique()),
                   "n_at_max_score": int((sc == top_score).sum()),
                   "max_score": float(top_score),
                   "min_score": float(sc.min())}
        sel_summary[key] = {
            "label": spec["label"], "tier": spec["tier"], "scope": spec["scope"],
            "support": spec["support"], "score_column": spec["score"],
            "n_support": n_sup, "source": spec["source"], "note": spec["note"],
            "tie_diagnostics": tie,
        }
    sel_summary["random_expected"] = {
        "label": "Random (expected)", "tier": "random", "scope": "full",
        "support": "full", "score_column": None, "n_support": 18519,
        "source": "in-house analytic expectation K*mean(label|support)",
        "note": "reference, not a realized draw",
    }
    sel_summary["oracle"] = {
        "label": "Oracle future-label reference", "tier": "oracle_posthoc",
        "support": "full/structural/ig", "n_support": 18519,
        "source": "post-hoc (uses future labels)", "note": "upper-bound reference only; NOT a selector",
    }

    result = {
        "cutoff": "2022-09-01",
        "protocol_ref": "research/audit/temporal_protocol.yaml v1.0",
        "k_values": E.KS,
        "label_columns": list(E.LABELS.values()),
        "label_window": "[2022-09-01, 2022-10-01)",
        "no_leakage_statement": (
            "selector scores use only information strictly before cutoff (as-of features, "
            "frozen Group B predictions, Group C as-of structural features, Group D as-of IG); "
            "future labels are used ONLY for evaluation. Full-window static priors are flagged "
            "LEAKY and reported separately as baseline-tier only."
        ),
        "universe": {"n": 18519, "source": "wallet_asof_features_20220901 (via groupB labels pull)"},
        "input_sources": meta,
        "selectors": sel_summary,
        "support_boundaries": supports,
        "frontier_native": frontier[frontier["scope"].isin(["full", "usd", "structural", "ig"])]
                           .to_dict(orient="records"),
        "frontier_restricted": frontier[frontier["scope"].isin(["structural_restricted", "ig_restricted"])]
                               .to_dict(orient="records"),
        "oracle_reference": frontier[frontier["selector"].str.startswith("oracle_")]
                            .to_dict(orient="records"),
        "random_expected": frontier[frontier["selector"] == "random_expected"].to_dict(orient="records"),
        "overlap_jaccard": overlap,
        "compute": {"runtime_sec": round(time.time() - t0, 2), "mode": "local CPU, no LLM, no BigQuery"},
    }
    with open(os.path.join(RES, "selection_results_20220901.json"), "w") as f:
        json.dump(result, f, indent=1, default=float)

    manifest = {
        "task": "Budgeted wallet selection at cutoff 2022-09-01 (autoresearch_phase1.md §9/§13/§14/§16)",
        "protocol_ref": "research/audit/temporal_protocol.yaml v1.0 (frozen 2026-09-11)",
        "data_audit_ref": "research/audit/DATA_AUDIT.md",
        "generated_by": "research/selection_eval/src/run_eval.py",
        "generated_at_utc": pd.Timestamp.now("UTC").isoformat(),
        "cutoff": "2022-09-01",
        "reused_inputs": {k: v["source"] for k, v in sel_summary.items()},
        "support_sets": {
            "full": 18519, "usd": supports["usd"]["n_support"],
            "structural": supports["structural"]["n_support"],
            "ig": supports["ig"]["n_support"],
        },
        "leakage_notes": {
            "no_future_leakage": "all selector scores are computable from events strictly before 2022-09-01",
            "static_prior_leaky": "static_degree/static_pagerank are full-window priors (leaky); reported as baseline tier only",
            "ig_subset": "IG selectors are restricted to the 2,999-wallet Group D subset; no extrapolation",
            "structural_subset": "structural selectors restricted to the 7,929 matched-matched subgraph; no extrapolation",
            "oracle": "oracle reference uses future labels (post-hoc); not a selector",
            "no_k_tuning": "K is NOT tuned on the final holdout; the full K frontier is reported as analysis (§16)",
        },
        "outputs": [
            "results/selection_results_20220901.json",
            "results/budget_frontier.csv",
            "results/figures/*.png",
        ],
    }
    with open(os.path.join(RES, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, default=str)

    # ---- console summary ----
    pd.set_option("display.width", 200)
    keep = ["selector", "k", "u_fwd30_evt_cnt_mean", "u_fwd30_new_cp_mean",
            "u_fwd30_new_cp_sum", "recall_new_pos", "n_support"]
    print("=== NATIVE-SUPPORT FRONTIER (head) ===")
    print(frontier[frontier["scope"].isin(["full", "usd", "structural", "ig"])][keep]
          .groupby("selector").head(1).to_string(index=False))
    print("\n=== RUNTIME (sec):", round(time.time() - t0, 2), "===")
    print("wrote results/selection_results_20220901.json, budget_frontier.csv, manifest.json")


if __name__ == "__main__":
    main()
