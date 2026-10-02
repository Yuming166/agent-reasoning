#!/usr/bin/env python3
"""Run only predeclared OW-010B secondary analyses after the frozen primary.

The primary protocol is not altered. This produces the 30-day target and the
prespecified repeated/unseen-wallet audit for the same frozen August models.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

from run_ow010b import (
    BASE, DATA, RESULTS, TRAIN_CUTOFF, DEV_CUTOFF, TEST_CUTOFF,
    build_features, build_target, fit_ridge_ladder, fit_tree_ladder, load_panel, loss,
)


def main() -> None:
    panel, qa = load_panel()
    y7, y30 = build_target(panel)
    bundle, cols = build_features(panel)
    primary = panel["history_eligible"] & panel["future30_complete"] & y30.notna().all(axis=1)
    tr = panel.index[primary & (panel.cutoff_label == TRAIN_CUTOFF)]
    dv = panel.index[primary & (panel.cutoff_label == DEV_CUTOFF)]
    te = panel.index[primary & (panel.cutoff_label == TEST_CUTOFF)]
    out = []
    results = {}
    for family, fitter in [("ridge", fit_ridge_ladder), ("hist_gradient_boosting", fit_tree_ladder)]:
        for ladder in ["M0", "M1", "M2_CORE"]:
            r = fitter(ladder, bundle, y30, tr, dv, te)
            results[(family, ladder)] = r
            for split, yy, pp, idx in [("dev", r["dev_true"], r["dev_pred"], dv), ("test", r["test_true"], r["test_pred"], te)]:
                out.append({"model_family": family, "ladder": ladder, "horizon": "30d", "split": split, "n_rows": len(idx), "n_wallets": panel.loc[idx, "anchor_wallet"].nunique(), "mse": loss(yy, pp), "mae": float(np.mean(np.abs(yy - pp))), "selected_alpha": r.get("selected_alpha")})
    for family in ["ridge", "hist_gradient_boosting"]:
        for b, m, contrast in [("M0", "M1", "temporal"), ("M1", "M2_CORE", "structural"), ("M0", "M2_CORE", "total")]:
            rb, rm = results[(family, b)], results[(family, m)]
            lb, lm = loss(rb["test_true"], rb["test_pred"]), loss(rm["test_true"], rm["test_pred"])
            out.append({"model_family": family, "ladder": f"{b}_vs_{m}", "horizon": "30d", "split": "test_gain", "n_rows": len(te), "n_wallets": panel.loc[te, "anchor_wallet"].nunique(), "mse": lb-lm, "mae": (lb-lm)/lb if lb else np.nan, "selected_alpha": rb.get("selected_alpha")})
    pd.DataFrame(out).to_csv(RESULTS / "secondary_30d_metrics.csv", index=False)

    # Refit primary 7d models exactly as frozen, then report repeated/unseen August strata.
    p7 = panel["history_eligible"] & panel["future7_complete"] & y7.notna().all(axis=1)
    tr7 = panel.index[p7 & (panel.cutoff_label == TRAIN_CUTOFF)]
    dv7 = panel.index[p7 & (panel.cutoff_label == DEV_CUTOFF)]
    te7 = panel.index[p7 & (panel.cutoff_label == TEST_CUTOFF)]
    r7 = {ladder: fit_ridge_ladder(ladder, bundle, y7, tr7, dv7, te7) for ladder in ["M0", "M1", "M2_CORE"]}
    eligible_sets = {c: set(panel.loc[panel.history_eligible & (panel.cutoff_label == c), "anchor_wallet"].astype(str)) for c in [TRAIN_CUTOFF, DEV_CUTOFF]}
    repeated = eligible_sets[TRAIN_CUTOFF] | eligible_sets[DEV_CUTOFF]
    tw = panel.loc[te7, "anchor_wallet"].astype(str)
    strata = {"repeated": tw.isin(repeated).to_numpy(), "unseen": (~tw.isin(repeated)).to_numpy(), "all": np.ones(len(te7), dtype=bool)}
    rows = []
    for stratum, mask in strata.items():
        for ladder in ["M0", "M1", "M2_CORE"]:
            r = r7[ladder]
            rows.append({"stratum": stratum, "ladder": ladder, "n_rows": int(mask.sum()), "n_wallets": int(tw[mask].nunique()), "mse": loss(r["test_true"][mask], r["test_pred"][mask]), "mae": float(np.mean(np.abs(r["test_true"][mask] - r["test_pred"][mask])))})
        m0, m1, m2 = [r7[x] for x in ["M0", "M1", "M2_CORE"]]
        l0, l1, l2 = [loss(r["test_true"][mask], r["test_pred"][mask]) for r in [m0, m1, m2]]
        rows.append({"stratum": stratum, "ladder": "M1_vs_M0", "n_rows": int(mask.sum()), "n_wallets": int(tw[mask].nunique()), "mse": l0-l1, "mae": (l0-l1)/l0 if l0 else np.nan})
        rows.append({"stratum": stratum, "ladder": "M2_vs_M1", "n_rows": int(mask.sum()), "n_wallets": int(tw[mask].nunique()), "mse": l1-l2, "mae": (l1-l2)/l1 if l1 else np.nan})
        rows.append({"stratum": stratum, "ladder": "M2_vs_M0", "n_rows": int(mask.sum()), "n_wallets": int(tw[mask].nunique()), "mse": l0-l2, "mae": (l0-l2)/l0 if l0 else np.nan})
    pd.DataFrame(rows).to_csv(RESULTS / "wallet_stratum_metrics.csv", index=False)
    print(json.dumps({"status": "ok", "secondary_30d_rows": len(te), "primary_repeated": int(strata['repeated'].sum()), "primary_unseen": int(strata['unseen'].sum())}))


if __name__ == "__main__":
    main()
