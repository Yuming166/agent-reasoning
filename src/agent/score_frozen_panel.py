#!/usr/bin/env python3
"""Score a temporal-holdout panel with the frozen June cheap ranker."""
import argparse
import glob
import os
import pickle
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from agent.data import EVENT_KEY, FEATURE_COLS, META_COLS, add_features, join_meta  # noqa: E402


def load_panel(panel_dir):
    ev = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(panel_dir, "events", "*.csv.gz")))],
                   ignore_index=True)
    ca = pd.concat([pd.read_csv(f) for f in
                    sorted(glob.glob(os.path.join(panel_dir, "candidates", "*.csv.gz")))],
                   ignore_index=True)
    ev["block_timestamp"] = pd.to_datetime(ev["block_timestamp"], utc=True)
    return ev, ca


def per_event_mrr(df, score_col):
    df = df.sort_values(EVENT_KEY + [score_col],
                        ascending=[True, True, True, False]).copy()
    df["rank"] = df.groupby(EVENT_KEY).cumcount() + 1
    pos = df[df.label == 1].copy()
    rr = 1.0 / pos["rank"]
    return {
        "n_events": int(len(pos)),
        "MRR_unweighted": float(rr.mean()),
        "MRR_popweighted": float((rr * pos.pop_weight).sum() / pos.pop_weight.sum()),
        "R@1": float((pos["rank"] <= 1).mean()),
        "R@5": float((pos["rank"] <= 5).mean()),
        "R@10": float((pos["rank"] <= 10).mean()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel-dir", default="artifacts/llm_panel_20220901")
    ap.add_argument("--model", default="artifacts/llm_panel_v1/cheap_ranker_jun_frozen.pkl")
    ap.add_argument("--out", default="artifacts/llm_panel_20220901/panel_scored_sept_frozen.csv.gz")
    ap.add_argument("--metrics-out", default="artifacts/llm_panel_20220901/cheap_ranker_sept_metrics.json")
    args = ap.parse_args()

    ev, ca = load_panel(args.panel_dir)
    d = add_features(join_meta(ev, ca))
    with open(args.model, "rb") as f:
        bundle = pickle.load(f)
    model = bundle["model"]
    model_features = bundle.get("features", FEATURE_COLS)
    if model_features != FEATURE_COLS:
        raise ValueError(f"frozen feature mismatch: {model_features} vs {FEATURE_COLS}")
    d["cheap_score"] = model.predict_proba(d[FEATURE_COLS].to_numpy())[:, 1]

    metrics = per_event_mrr(d, "cheap_score")
    # Same-pool reference: only pre-snapshot global inbound popularity.
    d["pop_score"] = -d.g_rank
    metrics["globalpop"] = per_event_mrr(d, "pop_score")
    by_stratum = {}
    for st, g in d.groupby("stratum"):
        by_stratum[st] = per_event_mrr(g, "cheap_score")
    result = {"frozen_model": args.model, "n_candidates": int(len(d)),
              "overall": metrics, "by_stratum": by_stratum}
    import json
    with open(args.metrics_out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))

    keep = EVENT_KEY + ["candidate_address", "label", "cand_source",
                        "g_rank", "g_cnt", "personal_cnt", "days_since",
                        "bridge_paths", "bridge_signal", "cheap_score",
                        "stratum", "activity", "pop_weight", "cp_type",
                        "counterparty_address", "truth_g_rank",
                        "evt_cnt_90d", "cp_entropy_90d", "cp_new_rate_30d"]
    d[keep].to_csv(args.out, index=False, compression="gzip")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
