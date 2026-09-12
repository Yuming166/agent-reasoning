"""Budget-frontier and overlap figures for budgeted wallet selection (09-01).

Reads results/budget_frontier.csv + selection_results_20220901.json produced by
run_eval.py; writes results/figures/*.png.
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

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
FIG = os.path.join(RES, "figures")

# visual grouping by tier
TIER_COLOR = {
    "random": "#9e9e9e", "size": "#1f77b4", "temporal": "#17becf",
    "behavioral": "#9467bd", "structural": "#2ca02c", "structural_static_prior": "#8c564b",
    "predictive": "#d62728", "information": "#ff7f0e", "hybrid": "#e377c2",
    "oracle_posthoc": "#000000",
}


def load():
    f = pd.read_csv(os.path.join(RES, "budget_frontier.csv"))
    return f


def _style(ax):
    ax.set_xscale("log")
    ax.grid(True, which="both", alpha=0.25)


def plot_frontier_metric(f, metric, ylab, outname, scopes=("full", "usd", "structural", "ig")):
    sub = f[f.scope.isin(scopes) & f.k.isin([10, 25, 50, 100, 250, 500, 1000])].copy()
    # drop static-prior leaky selectors and oracle from main plot (shown separately)
    sub = sub[~sub.tier.isin(["structural_static_prior", "oracle_posthoc"])]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    # left: all native scopes, one color per tier
    for key, g in sub.groupby("selector"):
        row = g.sort_values("k")
        axes[0].plot(row.k, row[metric], marker="o", ms=3,
                     color=TIER_COLOR.get(row.tier.iloc[0], "#333"),
                     label=row.label.iloc[0], lw=1.2)
    _style(axes[0]); axes[0].set_title("Native-support frontier")
    axes[0].set_xlabel("K"); axes[0].set_ylabel(ylab)
    # right: full-support selectors only (comparable pool)
    full = f[f.scope == "full"].sort_values("k")
    for key, g in full.groupby("selector"):
        if key in ("random_expected",):
            axes[1].plot(g.k, g[metric], ls="--", color=TIER_COLOR["random"], lw=1.5,
                         label="Random (expected)")
            continue
        if key == "random":
            continue
        axes[1].plot(g.k, g[metric], marker="o", ms=3, lw=1.2,
                     color=TIER_COLOR.get(g.tier.iloc[0], "#333"),
                     label=g.label.iloc[0])
    _style(axes[1]); axes[1].set_title("Full-support selectors (n=18,519)")
    axes[1].set_xlabel("K"); axes[1].set_ylabel(ylab)
    axes[0].legend(fontsize=7, loc="upper right", framealpha=0.5)
    axes[1].legend(fontsize=7, loc="upper right", framealpha=0.5)
    fig.suptitle(f"Budget-quality frontier at cutoff 2022-09-01 — {ylab}", fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, outname), dpi=150)
    plt.close(fig)


def plot_uk_over_k(f):
    """U(K)/K per selected wallet = mean label, exactly U(K)/K by definition."""
    return


def plot_recall(f):
    sub = f[f.scope == "full" & f.k.isin([10, 25, 50, 100, 250, 500, 1000])] \
        if False else f[f.scope == "full"].copy()
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for key, g in sub.groupby("selector"):
        if key in ("random_expected",):
            continue
        g = g.sort_values("k")
        ax.plot(g.k, g.recall_new_pos, marker="o", ms=3, lw=1.2,
                color=TIER_COLOR.get(g.tier.iloc[0], "#333"), label=g.label.iloc[0])
    ax.set_xscale("log"); ax.grid(True, which="both", alpha=0.25)
    ax.set_xlabel("K"); ax.set_ylabel("Recall@K (fwd new_cp>0)")
    ax.set_title("Recall@K on full-support selectors (positives = fwd30_new_cp>0)")
    ax.legend(fontsize=7, loc="upper left", framealpha=0.5)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "recall_new_pos_full.png"), dpi=150)
    plt.close(fig)


def plot_restricted_compare(f):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, scope, title in [(axes[0], "structural_restricted", "Structural support (n=7,929)"),
                             (axes[1], "ig_restricted", "IG support (n=2,999)")]:
        sub = f[f.scope == scope].copy()
        sub = sub[~sub.tier.isin(["structural_static_prior", "oracle_posthoc"])]
        for key, g in sub.groupby("selector"):
            g = g.sort_values("k")
            ax.plot(g.k, g.u_fwd30_new_cp_mean, marker="o", ms=3, lw=1.2,
                    color=TIER_COLOR.get(g.tier.iloc[0], "#333"), label=g.label.iloc[0])
        ax.set_xscale("log"); ax.grid(True, which="both", alpha=0.25)
        ax.set_xlabel("K"); ax.set_ylabel("U(K)/K = mean fwd30_new_cp")
        ax.set_title(f"Support-restricted comparison — {title}")
        ax.legend(fontsize=6, loc="upper right", framealpha=0.5)
    fig.suptitle("Apples-to-apples on common restricted pools (09-01)", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "restricted_comparison.png"), dpi=150)
    plt.close(fig)


def plot_overlap(r):
    for k in ("100", "1000"):
        ov = r["overlap_jaccard"][k]["jaccard"]
        keys = r["overlap_jaccard"][k]["keys"]
        mat = pd.DataFrame(ov).reindex(index=keys, columns=keys).astype(float)
        fig, ax = plt.subplots(figsize=(11, 9.5))
        im = ax.imshow(mat.values, cmap="YlGnBu", vmin=0, vmax=1)
        ax.set_xticks(range(len(keys))); ax.set_yticks(range(len(keys)))
        ax.set_xticklabels(keys, rotation=90, fontsize=6)
        ax.set_yticklabels(keys, fontsize=6)
        for i in range(len(keys)):
            for j in range(len(keys)):
                v = mat.values[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=4.5,
                            color="black" if v < 0.85 else "white")
        ax.set_title(f"Jaccard overlap of top-K sets across selectors (K={k})")
        fig.colorbar(im, shrink=0.7)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, f"overlap_top{k}.png"), dpi=150)
        plt.close(fig)


def main():
    os.makedirs(FIG, exist_ok=True)
    f = load()
    r = json.load(open(os.path.join(RES, "selection_results_20220901.json")))
    plot_frontier_metric(f, "u_fwd30_new_cp_mean", "mean fwd30_new_cp (U/K)", "frontier_new_cp.png")
    plot_frontier_metric(f, "u_fwd30_evt_cnt_mean", "mean fwd30_evt_cnt (U/K)", "frontier_evt_cnt.png")
    plot_frontier_metric(f, "u_fwd30_cp_distinct_mean", "mean fwd30_cp_distinct (U/K)", "frontier_cp_distinct.png")
    plot_frontier_metric(f, "mass_share_fwd30_new_cp", "mass share fwd30_new_cp", "frontier_new_mass.png")
    plot_recall(f)
    plot_restricted_compare(f)
    plot_overlap(r)
    print("figures written:", sorted(os.listdir(FIG)))


if __name__ == "__main__":
    main()
