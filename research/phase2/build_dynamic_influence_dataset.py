#!/usr/bin/env python3
import os
"""Build research/phase2/dynamic_influence_dataset.parquet (P2DATA, Phase II-A).

Wallet-level dynamic predictive influence (plan Sec.8, non-causal):
    I_i^h(t) = U(Y[t:t+h] | C_t, X_i) - U(Y[t:t+h] | C_t),  h = 30d
Utility U = -logloss (binary new-cp) or -SE (regression evt count).
Rolling origin: for cutoff t, non-LLM models are trained only on cutoffs < t.
Volume-adjusted residual (Sec.9): residual = I - E[I | log1p(evt_cnt_90d)] (pooled OLS).
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[2]))
OUT = ROOT / "research" / "phase2" / "dynamic_influence_dataset.parquet"
MANIFEST = ROOT / "research" / "phase2" / "dynamic_influence_manifest.json"

ASOF_MONTHLY = ROOT / "research/groupA_behavior/results/data/asof_monthly_2022.parquet"
FEAT_MATRIX_09 = ROOT / "research/groupA_behavior/results/data/feature_matrix_20220901.parquet"

H = 30
SEED = 42
CUTOFFS = ["2022-05-01","2022-06-01","2022-07-01","2022-08-01","2022-09-01"]

BEHAV_FEATS = ["evt_cnt_90d","evt_out_90d","evt_in_90d","evt_self_90d","evt_native_90d",
 "evt_token_90d","active_days_90d","tx_cnt_90d","active_span_days_90d","cp_distinct_90d",
 "cp_out_distinct_90d","cp_in_distinct_90d","cp_out_interact_90d","cp_in_interact_90d",
 "token_distinct_90d","cp_entropy_90d","cp_new_30d","cp_new_rate_30d","cp_both_dir_90d",
 "cp_reciprocity_90d","self_tx_rate_90d","token_event_rate_90d","token_hhi_90d",
 "events_per_active_day_90d"]
NET_FEATS = ["asof_mm_in_degree","asof_mm_out_degree","asof_mm_undir_degree",
 "asof_mm_w_in_degree","asof_mm_w_out_degree","asof_mm_pagerank","asof_mm_kcore",
 "asof_mm_clustering","asof_mm_hub_neighbors"]
FEATURES = BEHAV_FEATS + NET_FEATS
ID_COLS = ["target_address","target_exgraph_node_id","target_is_x_matched"]

def load():
    am = pd.read_parquet(ASOF_MONTHLY)
    am["snapshot_date"] = pd.to_datetime(am["snapshot_date"]).dt.date
    fm = pd.read_parquet(FEAT_MATRIX_09)
    fm["snapshot_date"] = pd.to_datetime(fm["snapshot_date"]).dt.date
    df = pd.concat([am, fm], ignore_index=True)
    df = df.drop(columns=["importance_proxy_p3"])
    if "in_mm_subgraph" in df.columns:
        df = df.drop(columns=["in_mm_subgraph"])
    df["y_new_cp"] = (df["fwd30_new_cp"] > 0).astype(int)
    df["y_evt"] = df["fwd30_evt_cnt"]
    df["log_vol"] = np.log1p(df["evt_cnt_90d"])
    return df

def clip_p(p):
    return np.clip(p, 1e-9, 1 - 1e-9)

def logloss(y, p):
    p = clip_p(p)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))

def base_rates(df, cutoff):
    m = df["snapshot_date"].astype(str) == cutoff
    y = df.loc[m, "y_new_cp"].to_numpy(float)
    r = y.mean()
    base_ll = -(r * np.log(clip_p(r)) + (1 - r) * np.log(clip_p(1 - r)))
    yv = df.loc[m, "y_evt"].to_numpy(float)
    mu = yv.mean()
    base_mse = float(np.mean((yv - mu) ** 2))
    return base_ll, base_mse, len(y)

def main():
    df = load()
    X_cols = [c for c in FEATURES if c in df.columns]
    for c in FEATURES:
        if c not in df.columns:
            df[c] = float("nan")
    print("feature count:", len(X_cols), "rows:", len(df))
    print(df.groupby(df["snapshot_date"].astype(str))["y_new_cp"].agg(["size","mean"]).round(3).to_string())

    records = []
    per_cutoff = {}
    for ci, cutoff in enumerate(CUTOFFS):
        tr = df[df["snapshot_date"].astype(str) < cutoff]
        te = df[df["snapshot_date"].astype(str) == cutoff]
        base_ll, base_mse, n_te = base_rates(df, cutoff)
        per_cutoff[cutoff] = {"base_ll_new_cp": base_ll, "base_mse_evt": base_mse,
                              "n_test": n_te, "n_train": int(len(tr))}
        if len(tr) < 2000 or len(te) == 0:
            print(f"{cutoff}: no prior data -> influence NaN ({len(tr)} train, {len(te)} test)")
            te2 = te.copy()
            for c in ["p_new_hist","p_new_log","pred_evt_hist","base_ll_new_cp",
                      "ll_new_hist","ll_new_log","I_new_hist","I_new_log",
                      "base_mse_evt","se_evt_hist","I_evt_hist","I_mean"]:
                te2[c] = float("nan")
            records.append(te2)
            continue
        use = [c for c in X_cols if tr[c].notna().any()]
        Xtr = tr[use].to_numpy(float)
        Xte = te[use].to_numpy(float)
        ytr = tr["y_new_cp"].to_numpy()
        yte = te["y_new_cp"].to_numpy()
        yev_tr = tr["y_evt"].to_numpy()
        yev_te = te["y_evt"].to_numpy()

        hgb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1,
              min_samples_leaf=20, l2_regularization=1.0, random_state=SEED)
        hgb.fit(Xtr, ytr)
        p_hist = hgb.predict_proba(Xte)[:, 1]

        lr = Pipeline([("imp", SimpleImputer(strategy="median")),
                       ("scl", StandardScaler()),
                       ("lr", LogisticRegression(max_iter=2000, C=1.0, random_state=SEED))])
        lr.fit(Xtr, ytr)
        p_log = lr.predict_proba(Xte)[:, 1]

        hgr = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.1,
              min_samples_leaf=20, l2_regularization=1.0, random_state=SEED)
        hgr.fit(Xtr, yev_tr)
        pred_evt = hgr.predict(Xte)

        te2 = te.copy()
        te2["p_new_hist"] = p_hist
        te2["p_new_log"] = p_log
        te2["pred_evt_hist"] = pred_evt
        te2["base_ll_new_cp"] = base_ll
        te2["ll_new_hist"] = logloss(yte, p_hist)
        te2["ll_new_log"] = logloss(yte, p_log)
        te2["I_new_hist"] = base_ll - te2["ll_new_hist"]
        te2["I_new_log"] = base_ll - te2["ll_new_log"]
        te2["base_mse_evt"] = base_mse
        te2["se_evt_hist"] = (yte - pred_evt) ** 2
        te2["I_evt_hist"] = base_mse - te2["se_evt_hist"]
        te2["I_mean"] = te2[["I_new_hist","I_new_log","I_evt_hist"]].mean(axis=1)
        te2["train_cutoffs"] = " < " + cutoff
        te2["train_n"] = int(len(tr))
        print(f"{cutoff}: trained on {len(tr)}, predicted {len(te)}; "
              f"mean I_new_hist={te2['I_new_hist'].mean():.4f}, "
              f"mean I_new_log={te2['I_new_log'].mean():.4f}, "
              f"mean I_evt_hist={te2['I_evt_hist'].mean():.4f}")
        records.append(te2)

    out = pd.concat(records, ignore_index=True)
    out = out.sort_values(["snapshot_date","target_address"]).reset_index(drop=True)
    print("\ntotal rows:", len(out), "per cutoff:", out.groupby(out['snapshot_date'].astype(str)).size().to_dict())

    # Volume-adjusted residual (pooled OLS on log_vol)
    def resid(col):
        m = out[col].notna()
        x = out.loc[m, "log_vol"].to_numpy(float)
        y = out.loc[m, col].to_numpy(float)
        if len(x) < 100:
            return pd.Series(np.nan, index=out.index)
        b, a = np.polyfit(x, y, 1)
        pred = a + b * x
        r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
        res = pd.Series(np.nan, index=out.index)
        res[m] = y - pred
        print(f"resid {col}: OLS a={a:.4f} b={b:.4f} R2={r2:.4f} n={len(x)}")
        return res

    out["resid_I_new_hist"] = resid("I_new_hist")
    out["resid_I_new_log"] = resid("I_new_log")
    out["resid_I_evt_hist"] = resid("I_evt_hist")
    out["resid_I_mean"] = resid("I_mean")

    out = out.drop(columns=[c for c in ["in_mm_subgraph"] if c in out.columns])
    out.to_parquet(OUT, index=False)
    print("wrote", OUT, out.shape)
    return out

if __name__ == "__main__":
    main()
