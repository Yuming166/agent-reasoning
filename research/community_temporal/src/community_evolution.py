"""COMM group - fixed community matching, switch-rate formalization, importance.

Reads results/data/monthly_communities.csv (per-snapshot membership + roles).
Fixed protocol:
  * communities: networkx greedy_modularity_communities (Louvain-style), weight
  * matching:    Hungarian max-weight bipartite matching on common-node Jaccard,
                 minimum Jaccard 0.05 for a mapped pair (bijective, global opt)
  * drift vs membership change are reported separately.
Group C's rough greedy switch rate is reproduced for comparison.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

import config

CUTOFFS = ["2022-06-01", "2022-07-01", "2022-08-01", "2022-09-01"]
MONTHS = ["2022-06", "2022-07", "2022-08"]
PAIRS_CUTOFF = list(zip(CUTOFFS[:-1], CUTOFFS[1:]))
PAIRS_MONTH = list(zip(MONTHS[:-1], MONTHS[1:]))


def comm_sets(df: pd.DataFrame) -> dict[int, set]:
    out: dict[int, set] = {}
    for ci, nodes in df.groupby("community_id")["node_id"]:
        out[int(ci)] = set(nodes.tolist())
    return out


def jaccard(a: set, b: set) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def greedy_match(prev_sets: dict, cur_sets: dict) -> dict[int, int | None]:
    """Group C rough matching: each cur comm -> best prev comm by Jaccard (>=0.05)."""
    mapping: dict[int, int | None] = {}
    for cci, cset in cur_sets.items():
        best, best_j = None, -1.0
        for pci, pset in prev_sets.items():
            j = jaccard(cset, pset)
            if j > best_j:
                best, best_j = pci, j
        mapping[cci] = best if best_j >= config.MIN_MATCH_JACCARD else None
    return mapping


def greedy_no_threshold_match(prev_sets: dict, cur_sets: dict) -> dict[int, int | None]:
    """Group C exact rough matching: every cur comm -> best prev comm by
    Jaccard, no minimum-overlap threshold (spurious pairs allowed)."""
    mapping: dict[int, int | None] = {}
    for cci, cset in cur_sets.items():
        best, best_j = None, -1.0
        for pci, pset in prev_sets.items():
            j = jaccard(cset, pset)
            if j > best_j:
                best, best_j = pci, j
        mapping[cci] = best
    return mapping


def hungarian_match(prev_sets: dict, cur_sets: dict) -> dict[int, int | None]:
    """Bijective global-optimum matching maximizing total common-node Jaccard."""
    pkeys = sorted(prev_sets)
    ckeys = sorted(cur_sets)
    n, m = len(pkeys), len(ckeys)
    if n == 0 or m == 0:
        return {c: None for c in ckeys}
    J = np.zeros((n, m))
    for i, p in enumerate(pkeys):
        for j, c in enumerate(ckeys):
            J[i, j] = jaccard(prev_sets[p], cur_sets[c])
    rows, cols = linear_sum_assignment(-J)
    mapping: dict[int, int | None] = {c: None for c in ckeys}
    for i, j in zip(rows, cols):
        if J[i, j] >= config.MIN_MATCH_JACCARD:
            mapping[ckeys[j]] = pkeys[i]
    return mapping


def pair_metrics(prev_df: pd.DataFrame, cur_df: pd.DataFrame,
                 method: str) -> dict:
    prev_nodes = set(prev_df["node_id"])
    cur_nodes = set(cur_df["node_id"])
    common = prev_nodes & cur_nodes
    prev_c = prev_df.set_index("node_id")["community_id"].to_dict()
    cur_c = cur_df.set_index("node_id")["community_id"].to_dict()
    prev_sets = comm_sets(prev_df)
    cur_sets = comm_sets(cur_df)
    if method == "greedy_best_jaccard":
        mapping = greedy_match(prev_sets, cur_sets)
    elif method == "greedy_no_threshold":
        mapping = greedy_no_threshold_match(prev_sets, cur_sets)
    else:
        mapping = hungarian_match(prev_sets, cur_sets)

    switched = sum(1 for n in common if mapping.get(cur_c[n], None) != prev_c[n])
    switch_rate = switched / len(common) if common else None
    # decomposition: nodes inside mapped (persistent) cur communities vs
    # nodes that entered an unmapped (new/unrelated) cur community
    mapped_cur = {cci for cci, pci in mapping.items() if pci is not None}
    common_in_mapped = [n for n in common if cur_c[n] in mapped_cur]
    switched_mapped = sum(1 for n in common_in_mapped
                          if mapping.get(cur_c[n], None) != prev_c[n])
    switch_mapped_only = (switched_mapped / len(common_in_mapped)
                          if common_in_mapped else None)
    new_comm_enter_share = (1.0 - len(common_in_mapped) / len(common)
                            if common else None)

    labels_prev = [prev_c[n] for n in sorted(common)]
    labels_cur = [mapping.get(cur_c[n], -1) for n in sorted(common)]
    labels_cur_raw = [cur_c[n] for n in sorted(common)]
    ari = float(adjusted_rand_score(labels_prev, labels_cur_raw)) if len(common) > 1 else None
    nmi = float(normalized_mutual_info_score(labels_prev, labels_cur_raw)) if len(common) > 1 else None

    # mapped-pair Jaccard (stability of matched communities on common nodes)
    pair_j = []
    for cci, pci in mapping.items():
        if pci is None:
            continue
        cset = {n for n in cur_sets[cci] if n in common}
        pset = {n for n in prev_sets[pci] if n in common}
        pair_j.append(jaccard(cset, pset))
    mean_mapped_jaccard = float(np.mean(pair_j)) if pair_j else None
    n_unmapped_cur = sum(1 for v in mapping.values() if v is None)
    return {
        "n_prev": len(prev_nodes), "n_cur": len(cur_nodes),
        "n_common": len(common),
        "node_set_jaccard": round(jaccard(prev_nodes, cur_nodes), 4),
        "n_new_nodes": len(cur_nodes - prev_nodes),
        "n_gone_nodes": len(prev_nodes - cur_nodes),
        "new_node_share": round(len(cur_nodes - prev_nodes) / len(cur_nodes), 4),
        "matching": method,
        "n_cur_communities": len(cur_sets),
        "n_prev_communities": len(prev_sets),
        "n_unmapped_cur_communities": n_unmapped_cur,
        "membership_switch_rate_common": round(switch_rate, 4) if switch_rate is not None else None,
        "switch_rate_mapped_only": (round(switch_mapped_only, 4)
                                    if switch_mapped_only is not None else None),
        "new_community_enter_share": (round(new_comm_enter_share, 4)
                                      if new_comm_enter_share is not None else None),
        "mean_mapped_community_jaccard": (round(mean_mapped_jaccard, 4)
                                          if mean_mapped_jaccard is not None else None),
        "ari_common": round(ari, 4) if ari is not None else None,
        "nmi_common": round(nmi, 4) if nmi is not None else None,
    }


def assign_role(row, hub_thr, bridge_thr):
    """Role classes: hub (hub_score>=p90, not bridge), bridge (bridge>=p90,
    not hub), both, neither. Boundary is a separate flag (cross_share>=0.5)."""
    is_hub = row["hub_score"] >= hub_thr
    is_br = row["bridge_score"] >= bridge_thr
    if is_hub and is_br:
        return "both"
    if is_hub:
        return "hub"
    if is_br:
        return "bridge"
    return "neither"


def role_analysis(allm: pd.DataFrame) -> dict:
    out = {}
    for snap in sorted(allm["snapshot"].unique()):
        if snap not in CUTOFFS:
            continue  # calendar months have no betweenness -> no bridge_score
        d = allm[allm["snapshot"] == snap].copy()
        hub_thr = d["hub_score"].quantile(0.90)
        br_thr = d["bridge_score"].quantile(0.90)
        d["role_class"] = d.apply(lambda r: assign_role(r, hub_thr, br_thr), axis=1)
        cnt = d["role_class"].value_counts().to_dict()
        boundary = int(d["is_boundary"].sum())
        out[snap] = {
            "role_class_counts": {k: int(cnt.get(k, 0)) for k in
                                  ["hub", "bridge", "both", "neither"]},
            "n_boundary": boundary,
            "boundary_share": round(boundary / len(d), 4),
            "hub_threshold_p90": round(float(hub_thr), 4),
            "bridge_threshold_p90": round(float(br_thr), 4),
        }
    return out


def role_transitions(allm: pd.DataFrame, pairs) -> dict:
    """Role-class transition rates on common nodes across consecutive cutoffs."""
    out = {}
    role_prev = {}
    for prev, cur in pairs:
        dp = allm[allm["snapshot"] == prev]
        dc = allm[allm["snapshot"] == cur]
        common = set(dp["node_id"]) & set(dc["node_id"])
        rp = dp.set_index("node_id")
        rc = dc.set_index("node_id")
        hub_p, br_p = dp["hub_score"].quantile(0.90), dp["bridge_score"].quantile(0.90)
        hub_c, br_c = dc["hub_score"].quantile(0.90), dc["bridge_score"].quantile(0.90)
        trans = {}
        for n in common:
            r1 = assign_role(rp.loc[n], hub_p, br_p)
            r2 = assign_role(rc.loc[n], hub_c, br_c)
            trans.setdefault((r1, r2), 0)
            trans[(r1, r2)] += 1
        total = len(common)
        mat = {f"{a}->{b}": round(v / total, 4) for (a, b), v in sorted(trans.items())}
        out[f"{prev}|{cur}"] = {
            "n_common": total,
            "transition_rate_matrix": mat,
            "role_changed_share": round(
                sum(v for (a, b), v in trans.items() if a != b) / total, 4),
        }
    return out


def community_importance(allm: pd.DataFrame) -> dict:
    """Community x importance on 09-01 snapshot:
    Group B predictive top-10% (pred_act_level), Group D wallet IG, Group C
    structure/fwd30. Concentration reported subgraph-restricted (7,929)."""
    snap = "2022-09-01"
    d = allm[allm["snapshot"] == snap].copy()
    # address <-> node_id map (Group C wallet importance covers the 7,929 subgraph)
    amap = (pd.read_csv(config.GROUP_C_IMPORTANCE,
                       usecols=["target_address", "target_exgraph_node_id"])
            .drop_duplicates("target_exgraph_node_id"))
    d = d.merge(amap, left_on="node_id", right_on="target_exgraph_node_id",
                how="left", validate="one_to_one")
    # Group B predictions (target_address)
    b = pd.read_csv(config.GROUP_B_PREDS)
    d = d.merge(b, on="target_address", how="left", validate="one_to_one")
    # Group D wallet IG: headline variant = histgbm / y_cp_ge10, mean over folds
    ig = pd.read_csv(config.GROUP_D_IG)
    ig = (ig[(ig["model"] == "histgbm") & (ig["target"] == "y_cp_ge10")]
          .groupby("target_exgraph_node_id", as_index=False)["ig_occ"].mean())
    d = d.merge(ig, left_on="node_id", right_on="target_exgraph_node_id",
                how="left", validate="one_to_one")
    # Group C wallet importance (target_exgraph_node_id)
    c = pd.read_csv(config.GROUP_C_IMPORTANCE)
    d = d.merge(c[["target_exgraph_node_id", "structure_pct", "fwd30_evt_cnt"]],
                left_on="node_id", right_on="target_exgraph_node_id",
                how="left", suffixes=("", "_c"), validate="one_to_one")

    n_sub = len(d)
    # predicted top-10% among subgraph members (Group B definition)
    k10 = max(1, int(round(n_sub * 0.10)))
    pred_rank = d["pred_act_level_LightGBM"].rank(ascending=False, method="first")
    d["is_pred_top10pct"] = pred_rank <= k10

    rows = []
    for ci, g in d.groupby("community_id"):
        rows.append({
            "community_id": int(ci),
            "n": int(len(g)),
            "share_pop_subgraph": round(len(g) / n_sub, 5),
            "n_pred_top10pct": int(g["is_pred_top10pct"].sum()),
            "share_of_pred_top10pct_total": round(
                float(g["is_pred_top10pct"].sum()) / k10, 5),
            "pred_top10pct_density": round(
                float(g["is_pred_top10pct"].mean()), 5) if len(g) else None,
            "mean_ig_occ": round(float(g["ig_occ"].mean()), 5)
            if g["ig_occ"].notna().any() else None,
            "median_ig_occ": round(float(g["ig_occ"].median()), 5)
            if g["ig_occ"].notna().any() else None,
            "n_ig_covered": int(g["ig_occ"].notna().sum()),
            "mean_structure_pct": round(float(g["structure_pct"].mean()), 4),
            "mean_fwd30_evt": round(float(g["fwd30_evt_cnt"].mean()), 3),
        })
    comm_imp = pd.DataFrame(rows).sort_values("n", ascending=False)

    # concentration on absolute counts (same definition as Group B: share of
    # the total predicted top-10% pool, K=10% of subgraph members)
    by_abs = comm_imp.sort_values("n_pred_top10pct", ascending=False)
    top2_share = float(by_abs.head(2)["share_of_pred_top10pct_total"].sum())
    top5_share = float(by_abs.head(5)["share_of_pred_top10pct_total"].sum())
    top10_share = float(by_abs.head(10)["share_of_pred_top10pct_total"].sum())
    hhi_pred = float((comm_imp["share_of_pred_top10pct_total"] ** 2).sum())
    corr = comm_imp[["n", "mean_ig_occ"]].dropna()
    sp = corr["n"].corr(corr["mean_ig_occ"], method="spearman")

    comm_imp.to_csv(config.DATA / "community_importance_20220901.csv", index=False)
    return {
        "snapshot": snap,
        "n_subgraph_members": int(n_sub),
        "k_top10pct_subgraph": k10,
        "pred_metric": "pred_act_level_LightGBM (Group B holdout09)",
        "ig_metric": "ig_occ (Group D wallet masking, y_cp_ge10, histgbm, mean over folds)",
        "top2_community_share_of_pred_top10pct": round(top2_share, 4),
        "top5_community_share_of_pred_top10pct": round(top5_share, 4),
        "top10_community_share_of_pred_top10pct": round(top10_share, 4),
        "hhi_pred_top10pct_across_communities": round(hhi_pred, 4),
        "spearman_comm_size_vs_mean_ig": round(float(sp), 4) if not math.isnan(sp) else None,
        "n_communities": int(len(comm_imp)),
        "mean_ig_overall": round(float(d["ig_occ"].mean()), 5),
        "n_ig_covered_subgraph": int(d["ig_occ"].notna().sum()),
        "note": ("concentration restricted to matched-matched subgraph (7,929); "
                 "Group B's 93% used Group A personas over all 18,519 wallets"),
    }


def regime_dependence(allm: pd.DataFrame) -> dict:
    """Per-snapshot community concentration of FUTURE activity top-10% using
    fwd30 labels from Group A monthly (06/07/08) and Group C importance (09)."""
    month = pd.read_parquet(config.GROUP_A_MONTHLY)
    month["snapshot_date"] = month["snapshot_date"].astype(str)
    imp09 = pd.read_csv(config.GROUP_C_IMPORTANCE)
    out = {}
    for snap in CUTOFFS:
        d = allm[allm["snapshot"] == snap].copy()
        if snap == "2022-09-01":
            lab = imp09[["target_exgraph_node_id", "fwd30_evt_cnt"]]
            d = d.merge(lab, left_on="node_id",
                        right_on="target_exgraph_node_id", how="left")
            ycol = "fwd30_evt_cnt"
        else:
            lab = month[month["snapshot_date"] == snap][
                ["target_exgraph_node_id", "fwd30_evt_cnt"]]
            d = d.merge(lab, left_on="node_id",
                        right_on="target_exgraph_node_id", how="left")
            ycol = "fwd30_evt_cnt"
        d = d[d[ycol].notna()].copy()
        k10 = max(1, int(round(len(d) * 0.10)))
        rank = d[ycol].rank(ascending=False, method="first")
        d["is_top10pct"] = rank <= k10
        g = d.groupby("community_id").agg(
            n=("node_id", "size"), n_top=("is_top10pct", "sum")).reset_index()
        g["share_pop"] = g["n"] / len(d)
        g["share_top"] = g["n_top"] / k10
        top2 = float(g.sort_values("share_top", ascending=False).head(2)["share_top"].sum())
        hhi = float((g["share_top"] ** 2).sum())
        out[snap] = {
            "n_with_fwd30_label": int(len(d)),
            "k_top10pct": k10,
            "top2_community_share_of_future_top10pct": round(top2, 4),
            "hhi_future_top10pct_across_communities": round(hhi, 4),
        }
    return out


def make_figures(allm: pd.DataFrame, ev: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    config.FIG.mkdir(parents=True, exist_ok=True)

    # 1) community size distribution per snapshot (rank-size)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, snap in zip(axes.ravel(), CUTOFFS):
        sizes = (allm[allm["snapshot"] == snap]
                 .groupby("community_id").size().sort_values(ascending=False))
        ax.loglog(np.arange(1, len(sizes) + 1), sizes.values, "o-", ms=3, lw=1)
        ax.set_title(f"cutoff {snap}  n_comm={len(sizes)}")
        ax.set_xlabel("community rank"); ax.set_ylabel("size")
    fig.suptitle("Community size (rank-size, log-log) per cutoff", fontsize=13)
    fig.tight_layout(); fig.savefig(config.FIG / "community_size_rank.png", dpi=130)
    plt.close(fig)

    # 2) set drift + membership switch decomposition
    labels = []
    formal = []
    set_j = []
    for pair in PAIRS_CUTOFF:
        k = f"{pair[0]}|{pair[1]}"
        labels.append(f"{pair[0][5:]}\u2192{pair[1][5:]}")
        formal.append(ev["pair_metrics_hungarian"][k]["membership_switch_rate_common"])
        set_j.append(ev["pair_metrics_hungarian"][k]["node_set_jaccard"])
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - 0.18, formal, 0.36, label="membership switch (common nodes, Hungarian)")
    ax.bar(x + 0.18, set_j, 0.36, label="node-set Jaccard (drift, 1 - drift = change)")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("rate"); ax.set_ylim(0, 1)
    ax.legend(); ax.set_title("Set drift vs membership switch (per-cutoff as-of graphs)")
    fig.tight_layout(); fig.savefig(config.FIG / "switch_drift_decomposition.png", dpi=130)
    plt.close(fig)

    # 3) calendar-month comparison Group C exact reproduction vs formal
    #    (same Group C edges file, window [2022-06-03, 2022-09-01))
    gc = json.load(open(config.JSON / "groupC_monthly_comparison.json"))
    labels = [f"{p[0][-2:]}\u2192{p[1][-2:]}" for p in PAIRS_MONTH]
    rough = [gc[f"{p[0]}|{p[1]}"]["groupC_exact_overwrite_greedy_nothr"]
             ["membership_switch_rate_common"] for p in PAIRS_MONTH]
    formal_m = [gc[f"{p[0]}|{p[1]}"]["formal_hungarian_summed"]
                ["membership_switch_rate_common"] for p in PAIRS_MONTH]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - 0.18, rough, 0.36, label="Group C exact (overwrite weights, greedy no-thr)")
    ax.bar(x + 0.18, formal_m, 0.36, label="formal (summed weights, Hungarian max-Jaccard)")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("switch rate"); ax.set_ylim(0, 1)
    ax.legend(); ax.set_title("Calendar-month switch rate: Group C exact vs formal")
    fig.tight_layout(); fig.savefig(config.FIG / "monthly_switch_groupC_vs_formal.png", dpi=130)
    plt.close(fig)

    # 4) community x importance (09-01): share_pop vs share_pred_top10pct
    ci = pd.read_csv(config.DATA / "community_importance_20220901.csv")
    top = ci.sort_values("n_pred_top10pct", ascending=False).head(15)
    x = np.arange(len(top))
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(x - 0.18, top["share_pop_subgraph"], 0.36, label="share of subgraph population")
    ax.bar(x + 0.18, top["share_of_pred_top10pct_total"], 0.36,
           label="share of predicted top-10% pool (Group B)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"C{int(c)}" for c in top["community_id"]], rotation=45)
    ax.set_ylabel("share"); ax.legend()
    ax.set_title("09-01 communities: population vs predicted-importance share (top-15)")
    fig.tight_layout(); fig.savefig(config.FIG / "community_importance_20220901.png", dpi=130)
    plt.close(fig)

    # 5) regime: future top-10% concentration per snapshot
    reg = ev["regime"]
    labels = [s[5:] for s in CUTOFFS]
    vals = [reg[s]["top2_community_share_of_future_top10pct"] for s in CUTOFFS]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(labels, vals, "o-", lw=2)
    ax.set_ylabel("top-2 community share of future-activity top-10%")
    ax.set_title("Community concentration of future activity per cutoff (regime)")
    ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(config.FIG / "community_regime_concentration.png", dpi=130)
    plt.close(fig)
    print("[figs] saved 5 figures", flush=True)


def main() -> None:
    config.DATA.mkdir(parents=True, exist_ok=True)
    config.JSON.mkdir(parents=True, exist_ok=True)
    allm = pd.read_csv(config.DATA / "monthly_communities.csv")
    print(f"[load] monthly_communities {allm.shape}", flush=True)

    ev: dict = {}
    ev["pair_metrics_hungarian"] = {}
    ev["pair_metrics_greedy"] = {}
    for prev, cur in PAIRS_CUTOFF + PAIRS_MONTH:
        dp = allm[allm["snapshot"] == prev]
        dc = allm[allm["snapshot"] == cur]
        hm = pair_metrics(dp, dc, "hungarian_max_sum_jaccard")
        gm = pair_metrics(dp, dc, "greedy_best_jaccard")
        ev["pair_metrics_hungarian"][f"{prev}|{cur}"] = hm
        ev["pair_metrics_greedy"][f"{prev}|{cur}"] = gm
        print(f"[pair] {prev}|{cur} n_common={hm['n_common']} "
              f"set_j={hm['node_set_jaccard']} "
              f"switch_hungarian={hm['membership_switch_rate_common']} "
              f"switch_greedy={gm['membership_switch_rate_common']}", flush=True)

    ev["role_analysis"] = role_analysis(allm)
    ev["role_transitions_cutoff"] = role_transitions(allm, PAIRS_CUTOFF)
    ev["community_importance_20220901"] = community_importance(allm)
    ev["regime"] = regime_dependence(allm)

    with open(config.JSON / "community_evolution_summary.json", "w") as f:
        json.dump(ev, f, indent=2, ensure_ascii=False)

    make_figures(allm, ev)
    print("[done] community_evolution_summary.json + figures", flush=True)


if __name__ == "__main__":
    main()
