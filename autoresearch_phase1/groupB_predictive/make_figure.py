#!/usr/bin/env python3
"""Group B — small descriptive figures (CPU, no LLM).
1. community concentration: share of model-predicted top-10% vs population share
2. calibration curve of future-active classifier on the 09-01 holdout
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
HERE = ROOT / "research" / "groupB_predictive"
OUT = HERE / "results" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

res = json.loads((HERE / "results/persistence_regime_community_20220901.json").read_text())
comm = pd.DataFrame(res["community"]["per_community"]).sort_values("mean_future_activity")

fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
x = np.arange(len(comm))
ax[0].bar(x - 0.19, comm["share_population"], width=0.38, label="population share", color="#8da0cb")
ax[0].bar(x + 0.19, comm["share_of_pred_top10pct"], width=0.38, label="share of model pred top-10%", color="#fc8d62")
ax[0].set_xticks(x); ax[0].set_xticklabels(comm["community"], fontsize=8)
ax[0].set_xlabel("Group-A persona (full_asof__kmeans)"); ax[0].set_ylabel("share")
ax[0].set_title("Predictive importance concentration by community (09-01 holdout)")
ax[0].legend(fontsize=8)
ax[0].grid(alpha=0.3)

# calibration curve for future_active (LightGBM)
hp = pd.read_csv(HERE / "results/holdout09_predictions.csv")
y = (np.expm1(hp["fwd30_evt_cnt"].to_numpy()) > 0).astype(float)
p = hp["pred_act_bin_LightGBM"].to_numpy()
bins = np.linspace(0, 1, 11)
mid, obs = [], []
for lo, hi in zip(bins[:-1], bins[1:]):
    m = (p > lo) & (p <= hi)
    if m.sum():
        mid.append(p[m].mean()); obs.append(y[m].mean())
ax[1].plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
ax[1].plot(mid, obs, "o-", color="#66c2a5")
ax[1].set_xlabel("predicted P(future active)"); ax[1].set_ylabel("observed fraction")
ax[1].set_title("Calibration: future-active, 09-01 holdout")
ax[1].legend(fontsize=8); ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT / "groupB_figures.png", dpi=130)
print("wrote", OUT / "groupB_figures.png")
