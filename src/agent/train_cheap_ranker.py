#!/usr/bin/env python3
"""Fit the FROZEN cheap structured ranker for the LLM go/no-go panel.

Trained on June panel candidates only (the pre-registered training month),
scored unchanged on July and August. Model = HistGradientBoostingClassifier
on legitimate pre-snapshot candidate features (no truth_g_rank, no sentinel).
Writes artifacts/llm_panel_v1/cheap_ranker_jun_frozen.pkl and a metrics JSON.
"""
import json
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.data import (EVENT_KEY, FEATURE_COLS, PANEL_DIR, SNAPSHOTS,
                        add_features, join_meta, load_panel)

MODEL_PATH = os.path.join(PANEL_DIR, "cheap_ranker_jun_frozen.pkl")


def per_event_mrr(df, score_col):
    df = df.sort_values(EVENT_KEY + [score_col], ascending=[True, True, True, False]).copy()
    df["rank"] = df.groupby(EVENT_KEY).cumcount() + 1
    pos = df[df.label == 1].copy()
    rr = 1.0 / pos["rank"]
    out = {
        "n_events": int(len(pos)),
        "MRR": float(rr.mean()),
        "R@1": float((pos["rank"] <= 1).mean()),
        "R@5": float((pos["rank"] <= 5).mean()),
        "R@10": float((pos["rank"] <= 10).mean()),
    }
    return out, pos[EVENT_KEY + ["rank"]], rr


def main():
    ev, ca = load_panel()
    d = add_features(join_meta(ev, ca))

    train = d[d.snapshot_date == "2022-06-01"]
    from sklearn.ensemble import HistGradientBoostingClassifier
    model = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.05, max_depth=6,
        l2_regularization=1.0, random_state=20260909)
    model.fit(train[FEATURE_COLS].to_numpy(), train.label.to_numpy())
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "features": FEATURE_COLS,
                     "trained_on": "2022-06-01 panel"}, f)
    print("saved", MODEL_PATH)

    d = d.copy()
    d["cheap_score"] = model.predict_proba(d[FEATURE_COLS].to_numpy())[:, 1]

    metrics = {}
    ranks = {}
    for snap in SNAPSHOTS:
        m, pos, rr = per_event_mrr(d[d.snapshot_date == snap], "cheap_score")
        # also the unlearned global-popularity reference on the same pools
        gp, _, _ = per_event_mrr(
            d[d.snapshot_date == snap].assign(pop_score=lambda x: -x.g_rank),
            "pop_score")
        m_ref = {f"globalpop_{k}": v for k, v in gp.items()}
        metrics[snap] = {**m, **m_ref}
        ranks[snap] = pos.assign(rr=rr.values)
    print(json.dumps(metrics, indent=2))
    with open(os.path.join(PANEL_DIR, "cheap_ranker_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    # save per-candidate cheap scores for the LLM stage (small)
    keep = EVENT_KEY + ["candidate_address", "label", "cand_source",
                        "g_rank", "g_cnt", "personal_cnt", "days_since",
                        "bridge_paths", "bridge_signal", "cheap_score",
                        "stratum", "activity", "pop_weight", "cp_type",
                        "counterparty_address", "truth_g_rank",
                        "evt_cnt_90d", "cp_entropy_90d", "cp_new_rate_30d"]
    out = os.path.join(PANEL_DIR, "panel_scored.csv.gz")
    d[keep].to_csv(out, index=False, compression="gzip")
    print("wrote", out)


if __name__ == "__main__":
    main()
