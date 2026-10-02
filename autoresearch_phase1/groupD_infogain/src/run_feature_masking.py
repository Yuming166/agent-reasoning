"""Experiment 2 — feature masking / trajectory masking (feature-level predictive IG).

Variants (plan §Group D):
- block masking: drop volume / diversity / trajectory / network feature block, retrain
- single-feature ablation: drop one feature, retrain, rank by dNLL vs full model
- trajectory masking is reported as the 'trajectory' block result

Method: 5-fold CV at cutoff 2022-09-01 (same protocol as wallet masking).
Both histgbm and logistic for blocks; histgbm for single-feature ablation.
Also runs the two cheapest blocks on the FULL 18,519 population as a robustness note.

Outputs: results/feature_masking_20220901.json, results/feature_ablation_20220901.csv
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).parent))
import config as C
import models as M

OUT_JSON = C.RESULTS / "feature_masking_20220901.json"
OUT_CSV = C.RESULTS / "feature_ablation_20220901.csv"


def feature_list(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c not in
            (set(C.ID_COLS) | set(C.LABEL_COLS) | set(C.TARGETS) |
             {"volume_usd", "log_volume_usd"} | set(C.PERSONA_COLS))]


def cv_pooled(df: pd.DataFrame, feats: list, target: str, model_name: str,
              seed: int = C.SEED) -> dict:
    X = df[feats].to_numpy(dtype=float)
    y = df[target].to_numpy().astype(int)
    p = np.full(len(df), np.nan)
    skf = StratifiedKFold(n_splits=C.CV_FOLDS, shuffle=True, random_state=seed)
    for tr, te in skf.split(X, y):
        pipe = M.Pipeline(model_name, seed=seed).fit(X[tr], y[tr])
        p[te] = pipe.predict_proba1(X[te])
    ok = ~np.isnan(p)
    return {
        "n_features": int(len(feats)),
        "nll": M.nll(y[ok], p[ok]),
        "auc": M.auc(y[ok], p[ok]),
        "brier": float(np.mean((p[ok] - y[ok]) ** 2)),
    }


def main() -> None:
    t0 = time.time()
    df = pd.read_parquet(C.RESULTS / "dataset_subset_20220901.parquet")
    feats = feature_list(df)
    target = C.PRIMARY_TARGET
    result = {"cutoff": C.CUTOFF, "target": target, "subset": int(len(df)),
              "full_feature_count": len(feats)}

    # --- block masking ---
    result["blocks"] = {}
    for model_name in ["histgbm", "logistic"]:
        full = cv_pooled(df, feats, target, model_name)
        result.setdefault("full_model", {})[model_name] = full
        result["blocks"][model_name] = {"full": full}
        for bname, bcols in C.FEATURE_BLOCKS.items():
            remain = [c for c in feats if c not in set(bcols)]
            r = cv_pooled(df, remain, target, model_name)
            r["masked_block"] = bname
            r["n_masked_features"] = len(bcols)
            r["delta_nll"] = r["nll"] - full["nll"]
            r["delta_auc"] = r["auc"] - full["auc"]
            r["delta_brier"] = r["brier"] - full["brier"]
            result["blocks"][model_name][bname] = r
            print(f"[feat] {model_name} block={bname:10s} nll={r['nll']:.4f} "
                  f"(dNLL={r['delta_nll']:+.4f}) auc={r['auc']:.4f} (dAUC={r['delta_auc']:+.4f})")

    # --- single-feature ablation (histgbm) ---
    rows = []
    full_h = result["full_model"]["histgbm"]
    for c in feats:
        remain = [x for x in feats if x != c]
        r = cv_pooled(df, remain, target, "histgbm")
        rows.append({"feature": c, "nll": r["nll"], "auc": r["auc"], "brier": r["brier"],
                     "delta_nll": r["nll"] - full_h["nll"],
                     "delta_auc": r["auc"] - full_h["auc"],
                     "delta_brier": r["brier"] - full_h["brier"]})
    abl = pd.DataFrame(rows).sort_values("delta_nll", ascending=False)
    abl.to_csv(OUT_CSV, index=False)
    result["single_feature_ablation"] = {
        "top10_by_dnll": abl.head(10)[["feature", "delta_nll", "delta_auc", "delta_brier"]].to_dict("records"),
        "bottom5_by_dnll": abl.tail(5)[["feature", "delta_nll", "delta_auc", "delta_brier"]].to_dict("records"),
    }

    # --- full-population robustness for volume & trajectory blocks (histgbm) ---
    df_full = pd.read_parquet(C.RESULTS / "dataset_full_20220901.parquet")
    feats_full = feature_list(df_full)
    result["full_population_robustness"] = {"n_wallets": int(len(df_full))}
    full_f = cv_pooled(df_full, feats_full, target, "histgbm")
    result["full_population_robustness"]["full"] = full_f
    for bname in ["volume", "trajectory"]:
        remain = [c for c in feats_full if c not in set(C.FEATURE_BLOCKS[bname])]
        r = cv_pooled(df_full, remain, target, "histgbm")
        r["masked_block"] = bname
        r["delta_nll"] = r["nll"] - full_f["nll"]
        r["delta_auc"] = r["auc"] - full_f["auc"]
        result["full_population_robustness"][bname] = r
        print(f"[feat] FULL-pop {bname:10s} nll={r['nll']:.4f} (dNLL={r['delta_nll']:+.4f}) "
              f"auc={r['auc']:.4f} (dAUC={r['delta_auc']:+.4f})")

    result["elapsed_sec"] = round(time.time() - t0, 1)
    (C.RESULTS / "feature_masking_20220901.json").write_text(json.dumps(result, indent=2, default=str))
    print(f"[feat] done in {time.time()-t0:.1f}s -> {OUT_JSON}")


if __name__ == "__main__":
    main()
