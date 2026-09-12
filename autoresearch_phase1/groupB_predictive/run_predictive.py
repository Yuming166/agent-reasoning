#!/usr/bin/env python3
"""Group B (Predictive-Influence-First) — first OOS evidence run.

Importance definition (this group):
  wallet i is "predictively important" at cutoff t iff its <=t historical
  state S_i(t) materially improves prediction of future ecosystem behavior
  in [t, t+30d) beyond naive historical baselines.

Experiment (strict OOS / temporal):
  - train   : 2022-06-01 snapshot (wallet_asof_features_v1)
  - validate: 2022-07-01 snapshot (early stopping / threshold choice)
  - frozen  : 2022-08-01 snapshot (within-dev frozen test, never tuned on)
  - holdout : 2022-09-01 snapshot (final untouched holdout, labels from BQ)

Targets:
  T1 future activity level       y = log1p(fwd30_evt_cnt)   (+ active >0 companion)
  T2 future new-edge formation   y = log1p(fwd30_new_cp)    (+ new-edge >0 companion)

Models: Linear (Logistic/Ridge) / HistGBM / LightGBM (CPU only, no GPU).
Baselines: persistence on historical volume/activity/counterparty-degree;
at 09-01 also static-prior PageRank (baseline only, leaky prior).

All features are strictly <= cutoff. No future labels are used in training.
No causality is claimed; these are descriptive OOS predictive numbers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import (
    roc_auc_score, average_precision_score, brier_score_loss, log_loss,
    mean_squared_error, mean_absolute_error, r2_score,
)
from scipy.stats import spearmanr
from lightgbm import LGBMClassifier, LGBMRegressor

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
HERE = ROOT / "research" / "groupB_predictive"
DATA = HERE / "results" / "data"
GROUP_A = ROOT / "research" / "groupA_behavior" / "results" / "data"
OUTDIR = HERE / "results"
OUTDIR.mkdir(parents=True, exist_ok=True)

RNG = 2022
N_EARLY_STOP = 50

# ---------------------------------------------------------------------------
# Feature sets
# ---------------------------------------------------------------------------
BASE_FEATURES = [
    "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d", "evt_native_90d",
    "evt_token_90d", "active_days_90d", "tx_cnt_90d", "active_span_days_90d",
    "cp_distinct_90d", "cp_out_distinct_90d", "cp_in_distinct_90d",
    "cp_out_interact_90d", "cp_in_interact_90d", "token_distinct_90d",
    "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d", "cp_both_dir_90d",
    "cp_reciprocity_90d", "self_tx_rate_90d", "token_event_rate_90d",
    "token_hhi_90d", "events_per_active_day_90d",
]
EXTRA_09_FEATURES = [
    # trajectory
    "n_events_90d_traj", "active_days_90d_traj", "active_span_days_traj",
    "first_event_offset_days", "last_event_recency_days", "mean_gap_days",
    "median_gap_days", "max_gap_days", "std_gap_days", "n_gaps_gt7d", "n_gaps",
    "out_interact_90d", "in_interact_90d", "native_90d", "token_90d",
    # network (as-of matched-matched subgraph; 0-filled with flag outside)
    "asof_mm_in_degree", "asof_mm_out_degree", "asof_mm_undir_degree",
    "asof_mm_w_in_degree", "asof_mm_w_out_degree", "asof_mm_pagerank",
    "asof_mm_kcore", "asof_mm_clustering", "asof_mm_hub_neighbors",
    # USD capital (coverage-limited)
    "native_usd", "token_usd_priced", "token_rows", "token_rows_priced",
]
ID_COLS = ["snapshot_date", "target_address", "target_exgraph_node_id",
           "target_is_x_matched"]
LABEL_COLS = ["fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_cp_out_distinct",
              "fwd30_new_cp", "importance_proxy_p3"]  # p3 is leaky demo, never a feature


def load_data() -> dict[str, pd.DataFrame]:
    monthly = pd.read_parquet(GROUP_A / "asof_monthly_2022.parquet")
    fm = pd.read_parquet(GROUP_A / "feature_matrix_20220901.parquet")
    # 09-01 labels: use the fresh bounded BigQuery pull (verified parity 0 diff)
    lab = pd.read_csv(DATA / "labels_20220901_bq.csv")
    fm = fm.drop(columns=[c for c in LABEL_COLS if c in fm.columns])
    fm = fm.merge(lab, on="target_address", how="left")
    static = pd.read_csv(GROUP_A / "static_prior_20220901.csv")
    return {"monthly": monthly, "fm09": fm, "static09": static}


def prep(df: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    X = df[features].copy()
    # categorical flag for network subgraph membership
    if "in_mm_subgraph" in X.columns:
        X["in_mm_subgraph"] = X["in_mm_subgraph"].fillna(False).astype(int)
    # fill NaNs with column median (0 for count-like)
    X = X.fillna(X.median(numeric_only=True)).replace([np.inf, -np.inf], 0.0)
    y_act = np.log1p(df["fwd30_evt_cnt"].to_numpy(float))
    y_new = np.log1p(df["fwd30_new_cp"].to_numpy(float))
    y_act_bin = (df["fwd30_evt_cnt"].to_numpy(float) > 0).astype(int)
    y_new_bin = (df["fwd30_new_cp"].to_numpy(float) > 0).astype(int)
    return X.to_numpy(float), {
        "act_level": y_act, "new_level": y_new,
        "act_bin": y_act_bin, "new_bin": y_new_bin,
    }, list(X.columns)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def make_models(task: str):
    if task == "cls":
        return {
            "Logistic": make_pipeline(StandardScaler(),
                                      LogisticRegression(max_iter=2000, C=1.0)),
            "HistGBM": HistGradientBoostingClassifier(max_iter=300,
                                                      learning_rate=0.05,
                                                      max_leaf_nodes=31,
                                                      random_state=RNG),
            "LightGBM": LGBMClassifier(n_estimators=300, learning_rate=0.05,
                                       num_leaves=31, random_state=RNG,
                                       verbose=-1, n_jobs=4),
        }
    return {
        "Ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "HistGBM": HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                                 max_leaf_nodes=31,
                                                 random_state=RNG),
        "LightGBM": LGBMRegressor(n_estimators=300, learning_rate=0.05,
                                  num_leaves=31, random_state=RNG,
                                  verbose=-1, n_jobs=4),
    }


def fit_model(model, Xtr, ytr, Xva, yva):
    """Fit with early-stopping where supported; return fitted model."""
    if isinstance(model, (LGBMClassifier, LGBMRegressor)):
        model.fit(Xtr, ytr, eval_set=[(Xva, yva)],
                  callbacks=[__import__("lightgbm").early_stopping(N_EARLY_STOP, verbose=False)])
        return model
    model.fit(Xtr, ytr)
    return model


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def ece(y, p, n_bins=10):
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    tot = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p > lo) & (p <= hi)
        if m.sum() == 0:
            continue
        tot += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return float(tot)


def cls_metrics(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "logloss": float(log_loss(y, p)),
        "ece": ece(y, p),
    }


def reg_metrics(y, p):
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "mae": float(mean_absolute_error(y, p)),
        "r2": float(r2_score(y, p)),
        "spearman": float(spearmanr(y, p).statistic),
    }


def topk_retrieval(y, p, k_frac=0.1):
    """MRR / Recall for retrieving the true top-k_frac wallets by future value,
    ranking the holdout by predicted value p (or baseline feature)."""
    n = len(y)
    k = max(1, int(round(n * k_frac)))
    true_top = set(np.argsort(-np.asarray(y))[:k])
    order = np.argsort(-np.asarray(p))
    rec_at_k = len(true_top.intersection(set(order[:k]))) / k
    # MRR over the true top-k items: mean reciprocal position within the ranked list
    pos = {v: i + 1 for i, v in enumerate(order)}
    mrr = float(np.mean([1.0 / pos[t] for t in true_top]))
    return {"k": k, "recall_at_k": float(rec_at_k), "mrr": mrr}


# ---------------------------------------------------------------------------
# Baselines (naive / persistence / static prior)
#   * regression  : predict y = log1p(historical feature)  (persistence)
#   * classification: univariate logistic on ONE historical feature (fit on train)
#   * ranking     : top-k retrieval by historical volume / activity / degree
#     and (holdout09 only) full-window static-prior PageRank (leaky prior,
#     BASELINE ONLY per temporal_protocol.yaml feature_availability).
# ---------------------------------------------------------------------------
def run_baselines(sets, static09):
    out = {}
    for eval_name in ["test08", "holdout09"]:
        raw = sets[eval_name]["_raw"]
        Y = sets[eval_name]["Y"]
        bl_feats = ["evt_cnt_90d", "active_days_90d", "cp_distinct_90d"]
        bl = {f: np.log1p(raw[f].to_numpy(float)) for f in bl_feats}
        if eval_name == "holdout09" and static09 is not None:
            bl["static_pagerank"] = np.log1p(raw["_static_pagerank"].to_numpy(float))
        evalm = {}
        for bname, bv in bl.items():
            evalm[bname] = {"reg": {}, "cls": {}}
            for tkey in ["act_level", "new_level"]:
                y = Y[tkey]
                met = reg_metrics(y, bv)
                met.update(topk_retrieval(y, bv))
                evalm[bname]["reg"][tkey] = met
        # univariate logistic baselines (only features present in train snapshot)
        from sklearn.linear_model import LogisticRegression as _LR
        tr_raw = sets["train"]["_raw"]
        tr_Y = sets["train"]["Y"]
        for bname in bl_feats:
            xtr = np.log1p(tr_raw[bname].to_numpy(float)).reshape(-1, 1)
            xev = np.log1p(raw[bname].to_numpy(float)).reshape(-1, 1)
            for tkey in ["act_bin", "new_bin"]:
                y = Y[tkey]
                lr = _LR(max_iter=2000).fit(xtr, tr_Y[tkey])
                p = lr.predict_proba(xev)[:, 1]
                met = cls_metrics(y, p)
                met.update(topk_retrieval(y, p))
                evalm[bname]["cls"][tkey] = met
        out[eval_name] = evalm
    return out

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_split(data, label):
    """Temporal split run: train=06-01, val=07-01, test=08-01, holdout=09-01."""
    monthly = data["monthly"]
    fm09 = data["fm09"]
    static09 = data["static09"]

    snap = {str(s)[:10]: g for s, g in monthly.groupby("snapshot_date")}
    tr = snap["2022-06-01"]
    va = snap["2022-07-01"]
    te = snap["2022-08-01"]
    ho = fm09

    raw_cols = ["evt_cnt_90d", "active_days_90d", "cp_distinct_90d"]
    sets = {}
    for name, df in [("train", tr), ("val", va), ("test08", te), ("holdout09", ho)]:
        X, Y, cols = prep(df, BASE_FEATURES)
        raw = df[raw_cols].reset_index(drop=True)
        if name == "holdout09":
            pr = ho[["target_address"]].reset_index(drop=True).merge(
                static09[["target_address", "pagerank"]], on="target_address",
                how="left")["pagerank"].fillna(0.0)
            raw["_static_pagerank"] = pr
        sets[name] = {"X": X, "Y": Y, "n": len(X), "features": cols, "_raw": raw}

    results = {"split": label, "n_train": sets["train"]["n"],
               "n_val": sets["val"]["n"], "n_test08": sets["test08"]["n"],
               "n_holdout09": sets["holdout09"]["n"],
               "targets": {}, "baselines": {}, "model_deltas": {}}
    results["baselines"] = run_baselines(sets, static09)

    holdout_pred = pd.DataFrame({"target_address": ho["target_address"].reset_index(drop=True),
                                   "fwd30_evt_cnt": sets["holdout09"]["Y"]["act_level"],
                                   "fwd30_new_cp": sets["holdout09"]["Y"]["new_level"]})
    for tkey, tname in [("act_bin", "future_active"), ("new_bin", "future_new_edge"),
                        ("act_level", "future_activity_level"),
                        ("new_level", "future_new_edges_level")]:
        task = "cls" if tkey.endswith("bin") else "reg"
        targets = {k: v["Y"][tkey] for k, v in sets.items()}
        models_out = {}
        for mname, model in make_models(task).items():
            m = fit_model(model, sets["train"]["X"], targets["train"],
                          sets["val"]["X"], targets["val"])
            row = {"model": mname}
            for eval_name in ["test08", "holdout09"]:
                p = m.predict_proba(sets[eval_name]["X"])[:, 1] if task == "cls" \
                    else m.predict(sets[eval_name]["X"])
                met = cls_metrics(targets[eval_name], p) if task == "cls" \
                    else reg_metrics(targets[eval_name], p)
                met.update(topk_retrieval(targets[eval_name], p))
                row[eval_name] = met
            models_out[mname] = row
            if tkey in ("act_level", "new_level") and mname == "LightGBM":
                holdout_pred[f"pred_{tkey}_LightGBM"] = m.predict(sets["holdout09"]["X"])
            if tkey in ("act_bin", "new_bin") and mname == "LightGBM":
                holdout_pred[f"pred_{tkey}_LightGBM"] = m.predict_proba(sets["holdout09"]["X"])[:, 1]
        results["targets"][tkey] = {"name": tname, "models": models_out,
                                    "base_rate": {
                                        "test08_pos": float(targets["test08"].mean()),
                                        "holdout09_pos": float(targets["holdout09"].mean())}}
    holdout_pred.to_csv(OUTDIR / "holdout09_predictions.csv", index=False)
    return results


def main() -> None:
    data = load_data()
    res = run_split(data, "temporal_train06_val07_test08_holdout09")
    out = OUTDIR / "predictive_results_20220901.json"
    out.write_text(json.dumps(res, indent=2, default=str))
    print(f"wrote {out}")

    # --- baselines summary ---
    print("\n== BASELINES (persistence / static prior, no training) ==")
    for eval_name in ["test08", "holdout09"]:
        print(f"  -- {eval_name} --")
        for bname, bv in res["baselines"][eval_name].items():
            r = bv["reg"]["act_level"]
            rn = bv["reg"]["new_level"]
            c = bv["cls"].get("act_bin", {})
            c2 = bv["cls"].get("new_bin", {})
            cls_txt = ""
            if c:
                cls_txt = f"| act_cls auc={c['auc']:.4f} brier={c['brier']:.4f} | new_cls auc={c2['auc']:.4f} brier={c2['brier']:.4f}"
            print(f"    {bname:18s} act: r2={r['r2']:.4f} sp={r['spearman']:.4f} r@k={r['recall_at_k']:.4f} "
                  f"| new: r2={rn['r2']:.4f} sp={rn['spearman']:.4f} r@k={rn['recall_at_k']:.4f} {cls_txt}")

    # compact console summary
    for tkey, t in res["targets"].items():
        print(f"\n== {t['name']} ({tkey}) ==")
        for eval_name in ["test08", "holdout09"]:
            for mname, row in t["models"].items():
                met = row[eval_name]
                if "auc" in met:
                    print(f"  {eval_name} {mname:10s} auc={met['auc']:.4f} pr={met['pr_auc']:.4f} "
                          f"brier={met['brier']:.4f} ll={met['logloss']:.4f} ece={met['ece']:.4f} "
                          f"mrr={met['mrr']:.4f} r@k={met['recall_at_k']:.4f}")
                else:
                    print(f"  {eval_name} {mname:10s} rmse={met['rmse']:.4f} mae={met['mae']:.4f} "
                          f"r2={met['r2']:.4f} sp={met['spearman']:.4f} mrr={met['mrr']:.4f} "
                          f"r@k={met['recall_at_k']:.4f}")


if __name__ == "__main__":
    main()
