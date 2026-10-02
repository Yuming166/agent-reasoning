"""Descriptive 08-01 robustness check (as-of snapshot 2022-08-01).

Uses Group A asof_monthly_2022.parquet snapshot 2022-08-01 (19,062 wallets with
fwd30 labels). Only selectors whose scores are computable locally at 08-01 are
included (volume_evt, eth_flow, activity, recency, persistence). This is a
DESCRIPTIVE stability check (walk-forward evidence), NOT a final-holdout claim;
the frozen final holdout remains 2022-09-01 evaluated exactly once.

Writes results/robustness_0801.json and results/figures/robustness_0801.png.
"""
from __future__ import annotations
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import load_data as L
import selector_defs as S

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIG = os.path.join(RES, "figures")
KS = [10, 25, 50, 100, 250, 500, 1000]
LABELS = {"lbl_evt": "fwd30_evt_cnt", "lbl_cp": "fwd30_cp_distinct", "lbl_new": "fwd30_new_cp"}

SELECTORS_0801 = [
    ("volume", "evt_cnt_90d"),
    ("eth_flow", "evt_native_90d"),
    ("activity", "active_days_90d"),
    ("persistence", "active_span_days_90d"),
]


def build_0801():
    df = L.load_0801()
    # labels sanity
    assert df["lbl_new"].notna().all() and len(df) == 19062
    return df


def topk(df, col, k):
    d = df.dropna(subset=[col]).copy()
    d = d.sort_values([col, "target_address"], ascending=[False, True])
    return d.head(k)


def evaluate(df, col, k):
    sup = df.dropna(subset=[col])
    sel = topk(df, col, k)
    row = {"k": k, "n_support": int(len(sup))}
    for lcol, lname in LABELS.items():
        row[f"u_{lname}_sum"] = float(sel[lcol].sum())
        row[f"u_{lname}_mean"] = float(sel[lcol].sum() / len(sel))
    row["recall_new_pos"] = float((sel["lbl_new"] > 0).sum() / max((sup["lbl_new"] > 0).sum(), 1))
    return row


def jaccard(a, b):
    a = set(a); b = set(b)
    return len(a & b) / len(a | b) if (a | b) else float("nan")


def main():
    os.makedirs(FIG, exist_ok=True)
    df = build_0801()
    out = {"cutoff": "2022-08-01",
           "protocol_ref": "research/audit/temporal_protocol.yaml v1.0",
           "status": "DESCRIPTIVE robustness check (walk-forward evidence); final frozen holdout is 2022-09-01",
           "n_wallets": int(len(df)),
           "label_window": "[2022-08-01, 2022-08-31)",
           "frontier": {},
           "overlap_0801_vs_0901": {},
           }
    # 09-01 selections (native full support) for overlap
    raw = L.load_all()
    base09, _ = L.assemble_scores(raw)
    base09 = S.add_random(base09, seed=20220901)

    for key, col in SELECTORS_0801:
        out["frontier"][key] = [evaluate(df, col, k) for k in KS]
        ov = {}
        for k in KS:
            a = set(topk(df, col, k)["target_address"])
            b = set(S.get_topk(base09, key, k)["target_address"])
            ov[str(k)] = {"jaccard_0801_vs_0901": jaccard(a, b),
                          "n_0801": len(a), "n_0901": len(b)}
        out["overlap_0801_vs_0901"][key] = ov

    with open(os.path.join(RES, "robustness_0801.json"), "w") as f:
        json.dump(out, f, indent=1, default=float)

    # figure
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for key, col in SELECTORS_0801:
        fr = out["frontier"][key]
        axes[0].plot([r["k"] for r in fr], [r["u_fwd30_new_cp_mean"] for r in fr],
                     marker="o", ms=3, label=key)
        axes[1].plot([r["k"] for r in fr], [r["recall_new_pos"] for r in fr],
                     marker="o", ms=3, label=key)
    for ax, yl, t in [(axes[0], "U(K)/K = mean fwd30_new_cp", "08-01 frontier (descriptive)"),
                      (axes[1], "Recall@K (new_cp>0)", "08-01 recall")]:
        ax.set_xscale("log"); ax.grid(True, which="both", alpha=0.25)
        ax.set_xlabel("K"); ax.set_ylabel(yl); ax.set_title(t); ax.legend(fontsize=8)
    fig.suptitle("Walk-forward descriptive check at cutoff 2022-08-01 (as-of features only)", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "robustness_0801.png"), dpi=150)
    plt.close(fig)
    print("wrote results/robustness_0801.json + figures/robustness_0801.png")
    for key in out["frontier"]:
        k100 = [r for r in out["frontier"][key] if r["k"] == 100][0]
        print(f"{key:10s} K=100 U/K={k100['u_fwd30_new_cp_mean']:.2f} "
              f"recall={k100['recall_new_pos']:.4f} "
              f"ovl_0801vs0901={out['overlap_0801_vs_0901'][key]['100']['jaccard_0801_vs_0901']:.3f}")


if __name__ == "__main__":
    main()
