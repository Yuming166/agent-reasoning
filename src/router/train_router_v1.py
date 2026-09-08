#!/usr/bin/env python3
"""P4 learned deliberation router, v1.

Train (Jun snapshot) -> tune hyperparameter grid on Jul -> frozen eval Aug.
Target y = future-30d popularity-headroom sum (event mass the cheap
popularity baseline ranks poorly, i.e. where an agent can add value).

Outputs:
  - budget-coverage curves comparing the learned router vs raw volume,
    static P3 (oracle-style same-month importance), static P1 occlusion,
    P2 trigger, and random, on the FROZEN August test snapshot;
  - ablation: router with/without P1/P2/motif features;
  - feature importances, gain-prediction calibration, manifest JSON.
All inputs are local CSV exported from ictdata-507912.exgraph.router_dataset_v1.
"""
from __future__ import annotations
import argparse, json, os
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

MOTIF = ["cp_reciprocity_90d", "self_tx_rate_90d", "token_event_rate_90d",
         "token_hhi_90d", "cp_both_dir_90d", "token_distinct_90d"]
CORE = ["evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
        "evt_native_90d", "evt_token_90d", "active_days_90d", "tx_cnt_90d",
        "active_span_days_90d", "cp_distinct_90d", "cp_out_distinct_90d",
        "cp_in_distinct_90d", "cp_out_interact_90d", "cp_in_interact_90d",
        "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d",
        "events_per_active_day_90d"]
P1 = ["icf_score_p1", "p1_bridges_events"]
P2 = ["trigger_score_p2", "trigger_strong_pairs"]
FEATURE_SETS = {
    "full": CORE + MOTIF + P1 + P2,
    "no_p1": CORE + MOTIF + P2,
    "no_p2": CORE + MOTIF + P1,
    "no_p1p2": CORE + MOTIF,
    "core_only": CORE,
}


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date.astype(str)
    return df


def fit(train: pd.DataFrame, feats: list[str], seed: int):
    m = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=1.0, random_state=seed)
    X = train[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = np.log1p(train["y_headroom_sum"].clip(lower=0))
    m.fit(X, y)
    return m


def predict(m, df, feats):
    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return m.predict(X)


def coverage_at_budgets(score: np.ndarray, value: np.ndarray,
                        budgets=(0.01, 0.05, 0.10, 0.20)) -> dict:
    n = len(score)
    order = np.argsort(-score, kind="mergesort")
    total = value.sum()
    out = {}
    for b in budgets:
        k = max(1, int(round(b * n)))
        out[f"{int(b*100)}pct"] = float(value[order[:k]].sum() / total) if total > 0 else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/tmp/router/000000000000.csv")
    ap.add_argument("--outdir", default="artifacts/router_v1")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    df = load(args.csv)
    tr = df[df.snapshot_date == "2022-06-01"].copy()
    va = df[df.snapshot_date == "2022-07-01"].copy()
    te = df[df.snapshot_date == "2022-08-01"].copy()
    yte = te["y_headroom_sum"].clip(lower=0).to_numpy()

    # ---- tune number of iterations on validation ----------------------------
    best = None
    for iters in (100, 200, 400, 800):
        for lr in (0.03, 0.05, 0.1):
            m = HistGradientBoostingRegressor(
                max_iter=iters, learning_rate=lr, max_leaf_nodes=31,
                min_samples_leaf=30, l2_regularization=1.0, random_state=7)
            m.fit(tr[FEATURE_SETS["full"]].fillna(0),
                  np.log1p(tr["y_headroom_sum"].clip(lower=0)))
            pv = predict(m, va, FEATURE_SETS["full"])
            # validation utility = headroom captured at 10% budget
            c = coverage_at_budgets(pv, va["y_headroom_sum"].clip(lower=0).to_numpy(),
                                    budgets=(0.10,))["10pct"]
            if best is None or c > best[0]:
                best = (c, iters, lr)
    _, iters, lr = best
    print("best validation config: iters", iters, "lr", lr, "val_cov10", round(best[0], 4))

    # ---- refit on train, evaluate frozen test --------------------------------
    manifest = {"tune": {"best_iters": iters, "best_lr": lr,
                         "val_headroom_cov_10pct": best[0]},
                "n_train": len(tr), "n_val": len(va), "n_test": len(te),
                "test_total_headroom": float(yte.sum())}
    curves = {}
    rng = np.random.default_rng(42)
    # learned router variants (ablation)
    for name, feats in FEATURE_SETS.items():
        m = HistGradientBoostingRegressor(
            max_iter=iters, learning_rate=lr, max_leaf_nodes=31,
            min_samples_leaf=30, l2_regularization=1.0, random_state=7)
        m.fit(tr[feats].fillna(0), np.log1p(tr["y_headroom_sum"].clip(lower=0)))
        p = predict(m, te, feats)
        curves["router_" + name] = coverage_at_budgets(p, yte)
        if name == "full":
            te_out = te[["snapshot_date", "target_address",
                         "y_fwd_out_events", "y_headroom_sum", "y_hard_events"]].copy()
            te_out["router_score"] = p
            # permutation-style importances on test via feature corruption
            base_curve = curves["router_full"]
            imports = {}
            for col in feats:
                Xc = te[feats].copy().fillna(0.0)
                Xc[col] = rng.permutation(Xc[col].to_numpy())
                pc = m.predict(Xc.replace([np.inf, -np.inf], np.nan).fillna(0))
                imports[col] = base_curve["10pct"] - coverage_at_budgets(
                    pc, yte, budgets=(0.10,))["10pct"]
            manifest["feature_importance_drop_cov10"] = dict(
                sorted(imports.items(), key=lambda kv: -kv[1]))
    # static baselines
    curves["raw_volume"] = coverage_at_budgets(
        te["evt_cnt_90d"].to_numpy(), yte)
    curves["P1_static"] = coverage_at_budgets(
        te["icf_score_p1"].to_numpy(), yte)
    curves["P2_static"] = coverage_at_budgets(
        te["trigger_score_p2"].to_numpy(), yte)
    curves["P3_oracle_same_month"] = coverage_at_budgets(
        te["y_headroom_sum"].to_numpy(), yte)  # perfect ranking upper bound
    curves["random_expected"] = {f"{int(b*100)}pct": b
                                 for b in (0.01, 0.05, 0.10, 0.20)}
    manifest["aug_frozen_budget_curves"] = curves

    # event/hard-event coverage for the full router vs main baselines
    hard = te["y_hard_events"].clip(lower=0).to_numpy()
    evv = te["y_fwd_out_events"].clip(lower=0).to_numpy()
    mfull = HistGradientBoostingRegressor(
        max_iter=iters, learning_rate=lr, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=1.0, random_state=7)
    mfull.fit(tr[FEATURE_SETS["full"]].fillna(0),
              np.log1p(tr["y_headroom_sum"].clip(lower=0)))
    ps = {"router_full": predict(mfull, te, FEATURE_SETS["full"]),
          "raw_volume": te["evt_cnt_90d"].to_numpy(),
          "P1_static": te["icf_score_p1"].to_numpy()}
    extra = {}
    for nm, sc in ps.items():
        extra[nm] = {
            "hard_event_cov": coverage_at_budgets(sc, hard),
            "event_cov": coverage_at_budgets(sc, evv)}
    manifest["aug_frozen_other_coverage"] = extra

    te_out.sort_values("router_score", ascending=False).to_csv(
        os.path.join(args.outdir, "router_aug_scores.csv"), index=False)
    with open(os.path.join(args.outdir, "router_v1_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(curves, indent=2))


if __name__ == "__main__":
    main()
