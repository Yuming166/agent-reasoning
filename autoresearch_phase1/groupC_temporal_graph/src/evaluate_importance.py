"""Group C — evaluate structural importance at cutoff 2022-09-01.

Descriptive evaluation only (frozen protocol §5): we observe the future window
[2022-09-01, 2022-10-01) via fwd30 labels to DESCRIBE how well as-of structural
importance ranks predict future behavior. No causal claim; no out-of-sample
superiority claim; static full-window prior is treated as a leaky external
baseline and never as an as-of feature.

Outputs:
  results/evidence_summary.json        all headline numbers
  results/data/wallet_importance_20220901.csv   merged wallet-level table
  results/data/decile_analysis.csv              structure deciles vs future
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def rank_pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


def spearman(a, b) -> float:
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    m = a.notna() & b.notna()
    if m.sum() < 3:
        return float("nan")
    return float(stats.spearmanr(a[m], b[m]).statistic)


def topk_overlap(a: pd.Series, b: pd.Series, k: int) -> float:
    sa = set(a.dropna().nlargest(k).index)
    sb = set(b.dropna().nlargest(k).index)
    if not sa or not sb:
        return float("nan")
    return len(sa & sb) / len(sa | sb)


def load_all() -> dict:
    feats = pd.read_csv(config.DATA / "structural_features_20220901.csv")
    feats["target_exgraph_node_id"] = feats["target_exgraph_node_id"].astype("int64")

    fm = pd.read_parquet(config.GROUP_A_FEATURE_MATRIX)
    fm["target_exgraph_node_id"] = fm["target_exgraph_node_id"].astype("int64")

    static = pd.read_csv(config.STRUCTURAL_FEATURES_CSV)
    static["target_exgraph_node_id"] = static["exgraph_node_id"].astype("int64")

    p2 = pd.read_csv(config.P2_TRIGGER_CSV)
    p2 = p2[p2.snapshot_date == config.CUTOFF].copy()
    p2["target_address"] = p2["target_address"].str.lower()

    p1 = pd.read_csv(config.P1_RANKING_CSV)
    p1["target_address"] = p1["target_address"].str.lower()

    return {"feats": feats, "fm": fm, "static": static, "p2": p2, "p1": p1}


def merge_wallet_table(d: dict) -> pd.DataFrame:
    fm = d["fm"]
    feats = d["feats"]
    static = d["static"][["target_exgraph_node_id", "in_degree", "out_degree",
                          "w_in_degree", "w_out_degree", "degree", "w_degree",
                          "pagerank"]].rename(columns={
        "in_degree": "static_in_degree", "out_degree": "static_out_degree",
        "w_in_degree": "static_w_in", "w_out_degree": "static_w_out",
        "degree": "static_degree", "w_degree": "static_w_degree",
        "pagerank": "static_pagerank"})
    w = fm.merge(feats, on="target_exgraph_node_id", how="left")
    w = w.merge(static, on="target_exgraph_node_id", how="left")
    w = w.merge(d["p2"][["target_address", "trigger_score_p2_v2"]].rename(
        columns={"trigger_score_p2_v2": "p2_score"}), on="target_address", how="left")
    w = w.merge(d["p1"][["target_address", "icf_score_p1", "p1_rank"]],
                on="target_address", how="left")
    return w


def structure_score(w: pd.DataFrame) -> pd.DataFrame:
    """Composite as-of structural importance (mean of percentile ranks)."""
    cols = ["wdeg_und", "pagerank", "kcore", "betweenness", "bridge_score",
            "recency_wdeg"]
    pcts = []
    for c in cols:
        x = np.log1p(w[c].clip(lower=0))
        pcts.append(rank_pct(x).rename(f"pct_{c}"))
    pct = pd.concat(pcts, axis=1)
    w["structure_pct"] = pct.mean(axis=1)
    # non-volume structural composite: centrality/brokerage terms only (no
    # degree / k-core / recency-weight), to test structure beyond own size
    novol = []
    for c in ["pagerank", "betweenness", "bridge_score"]:
        novol.append(rank_pct(np.log1p(w[c].clip(lower=0))).rename(f"novol_{c}"))
    w["structure_novol_pct"] = pd.concat(novol, axis=1).mean(axis=1)
    w["volume_pct"] = rank_pct(w["evt_cnt_90d"])
    return w


def flow_pagerank_robustness(edges: pd.DataFrame, role_pr: pd.Series) -> dict:
    """Flow-oriented directed PageRank robustness check.

    Role rows orient as: (u,v,'outgoing') => flow u->v ; (v,u,'incoming') =>
    flow u->v as well (sender is the counterparty). Each matched-matched
    interaction yields two role rows, so flow weights are halved to recover
    true interaction counts. Result is compared with the role-graph PageRank
    used in the primary features (Group A convention).
    """
    flow = {}
    for r in edges.itertuples(index=False):
        u, v, d, m, w = int(r.u), int(r.v), r.direction, r.month, int(r.weight)
        fu, fv = (u, v) if d == "outgoing" else (v, u)
        if fu == fv:
            continue
        flow[(fu, fv)] = flow.get((fu, fv), 0) + w
    F = nx.DiGraph()
    for (fu, fv), w in flow.items():
        F.add_edge(fu, fv, weight=w / 2.0)
    pr_flow = nx.pagerank(F, alpha=0.85, weight="weight")
    idx = role_pr.dropna().index
    x = pd.Series(pr_flow, dtype=float).reindex(idx)
    rho = stats.spearmanr(role_pr.reindex(idx), x).statistic
    return {
        "flow_nodes": F.number_of_nodes(),
        "flow_directed_edges": F.number_of_edges(),
        "spearman_role_pr_vs_flow_pr": round(float(rho), 4),
    }


def monthly_communities(edges: pd.DataFrame):
    """Greedy-modularity communities per month; greedy cross-month match by
    maximum Jaccard overlap (post-hoc descriptive; features strictly < cutoff)."""
    out = {}
    for m in config.MONTHS:
        em = edges[edges.month == m]
        Gm = nx.Graph()
        for r in em.itertuples(index=False):
            if int(r.u) != int(r.v):
                Gm.add_edge(int(r.u), int(r.v), weight=int(r.weight))
        comms = list(nx.community.greedy_modularity_communities(Gm, weight="weight"))
        out[m] = {n: ci for ci, nodes in enumerate(comms) for n in nodes}
    return out


def match_communities(prev: dict, cur: dict) -> dict:
    """Map cur community ids to prev ids by max Jaccard overlap (>=0.05)."""
    prev_sets = {}
    for n, ci in prev.items():
        prev_sets.setdefault(ci, set()).add(n)
    cur_sets = {}
    for n, ci in cur.items():
        cur_sets.setdefault(ci, set()).add(n)
    mapping = {}
    for cci, cset in cur_sets.items():
        best, best_j = None, -1.0
        for pci, pset in prev_sets.items():
            j = len(cset & pset) / len(cset | pset)
            if j > best_j:
                best, best_j = pci, j
        mapping[cci] = best
    return mapping


def evaluate() -> None:
    config.RESULTS.mkdir(parents=True, exist_ok=True)
    d = load_all()
    w = merge_wallet_table(d)
    w = structure_score(w)

    sub = w[w.target_exgraph_node_id.isin(d["feats"].target_exgraph_node_id)].copy()
    sub["is_boundary"] = sub["is_boundary"].fillna(False).astype(bool)
    n_all = len(w)
    n_sub = len(sub)
    ev = {}

    # ---------------- 1. coverage ----------------
    ev["coverage"] = {
        "n_wallets_asof_table": int(n_all),
        "n_wallets_in_mm_subgraph": int(n_sub),
        "coverage_share": round(n_sub / n_all, 4),
        "n_edges_asof_directed": int(d["feats"].deg_in.sum()),
        "asof_subgraph_nodes": int(d["feats"].shape[0]),
    }

    # ---------------- 2. static leaky prior vs as-of ----------------
    rho = {}
    for sa, sb in [("static_w_degree", "wdeg_und"),
                   ("static_degree", "deg_und"),
                   ("static_pagerank", "pagerank"),
                   ("static_w_in", "wdeg_in")]:
        rho[f"{sa} vs {sb}"] = round(spearman(sub[sa], sub[sb]), 4)
    ev["static_vs_asof_spearman"] = rho
    ev["static_vs_asof_topk_overlap"] = {
        "top100_wdeg": round(topk_overlap(sub["static_w_degree"], sub["wdeg_und"], 100), 4),
        "top100_pagerank": round(topk_overlap(sub["static_pagerank"], sub["pagerank"], 100), 4),
        "top1000_wdeg": round(topk_overlap(sub["static_w_degree"], sub["wdeg_und"], 1000), 4),
        "top1000_pagerank": round(topk_overlap(sub["static_pagerank"], sub["pagerank"], 1000), 4),
    }

    # ---------------- 3. structure vs volume (size) ----------------
    lo_vol_hi_struct = sub[(sub.structure_pct >= 0.90) & (sub.volume_pct <= 0.50)]
    hi_vol_lo_struct = sub[(sub.volume_pct >= 0.90) & (sub.structure_pct <= 0.50)]
    lo_vol_hi_struct_nv = sub[(sub.structure_novol_pct >= 0.90) & (sub.volume_pct <= 0.50)]
    hi_vol_lo_struct_nv = sub[(sub.volume_pct >= 0.90) & (sub.structure_novol_pct <= 0.50)]
    # threshold sweep for the low-volume/high-structure cell
    sweep = {}
    for sv, vv in [("p90", "p50"), ("p80", "p30"), ("p75", "p25")]:
        sv_thr = {"p90": 0.90, "p80": 0.80, "p75": 0.75}[sv]
        vv_thr = {"p50": 0.50, "p30": 0.30, "p25": 0.25}[vv]
        sweep[f"struct>={sv} & vol<={vv}"] = {
            "n_all_composite": int(((sub.structure_pct >= sv_thr) & (sub.volume_pct <= vv_thr)).sum()),
            "n_novol_composite": int(((sub.structure_novol_pct >= sv_thr) & (sub.volume_pct <= vv_thr)).sum()),
        }
    cont = pd.crosstab(
        pd.qcut(sub.volume_pct, 3, labels=["vol_lo", "vol_mid", "vol_hi"]),
        pd.qcut(sub.structure_pct, 3, labels=["struct_lo", "struct_mid", "struct_hi"]),
    )
    cont_nv = pd.crosstab(
        pd.qcut(sub.volume_pct, 3, labels=["vol_lo", "vol_mid", "vol_hi"]),
        pd.qcut(sub.structure_novol_pct, 3, labels=["struct_lo", "struct_mid", "struct_hi"]),
    )
    ev["structure_vs_volume"] = {
        "spearman_struct_vs_evt_cnt": round(spearman(sub["structure_pct"], sub["evt_cnt_90d"]), 4),
        "spearman_struct_novol_vs_evt_cnt": round(spearman(sub["structure_novol_pct"], sub["evt_cnt_90d"]), 4),
        "n_low_vol_hi_struct": int(len(lo_vol_hi_struct)),
        "n_high_vol_low_struct": int(len(hi_vol_lo_struct)),
        "n_low_vol_hi_struct_novol": int(len(lo_vol_hi_struct_nv)),
        "n_high_vol_low_struct_novol": int(len(hi_vol_lo_struct_nv)),
        "threshold_sweep": sweep,
        "contingency_vol_x_struct": cont.to_dict(),
        "contingency_vol_x_struct_novol": cont_nv.to_dict(),
        "examples_low_vol_hi_struct": lo_vol_hi_struct.sort_values(
            "structure_pct", ascending=False).head(5)[
            ["target_address", "target_exgraph_node_id", "evt_cnt_90d",
             "volume_pct", "structure_pct", "fwd30_evt_cnt", "fwd30_cp_distinct"]].to_dict("records"),
        "examples_high_vol_low_struct": hi_vol_lo_struct.sort_values(
            "volume_pct", ascending=False).head(5)[
            ["target_address", "target_exgraph_node_id", "evt_cnt_90d",
             "volume_pct", "structure_pct", "fwd30_evt_cnt", "fwd30_cp_distinct"]].to_dict("records"),
    }

    # ---------------- 4. structure vs influence proxies ----------------
    p2sub = sub[sub["p2_score"].notna()]
    ev["structure_vs_influence_proxy"] = {
        "p2_n_wallets_with_score": int(len(p2sub)),
        "p2_spearman_struct_vs_p2": round(spearman(p2sub["structure_pct"], p2sub["p2_score"]), 4),
        "p2_spearman_evt_cnt_vs_p2": round(spearman(p2sub["evt_cnt_90d"], p2sub["p2_score"]), 4),
        "p2_spearman_wdeg_vs_p2": round(spearman(p2sub["wdeg_und"], p2sub["p2_score"]), 4),
        "p1_augpanel_posthoc_n": int(sub["icf_score_p1"].notna().sum()),
        "p1_augpanel_posthoc_spearman_struct_vs_icf": round(
            spearman(sub[sub.icf_score_p1.notna()]["structure_pct"],
                     sub[sub.icf_score_p1.notna()]["icf_score_p1"]), 4),
    }

    # ---------------- 5. descriptive predictive power on fwd30 ----------------
    struct_cols = ["deg_und", "wdeg_und", "pagerank", "kcore", "betweenness",
                   "recency_wdeg", "activity_trend", "active_months",
                   "persistent_edges", "mutual_pairs", "triangles",
                   "new_edges_recent", "cross_comm_share", "bridge_score",
                   "hub_score", "structure_pct", "structure_novol_pct", "volume_pct"]
    targets = ["fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_new_cp"]
    corr = {}
    for tgt in targets:
        corr[tgt] = {}
        for c in struct_cols:
            corr[tgt][c] = round(spearman(sub[c], sub[tgt]), 4)
    ev["descriptive_spearman_subgraph_n" + str(n_sub)] = corr

    # rank correlation on full wallet set for volume-only (activity baseline)
    corr_full = {}
    for tgt in targets:
        corr_full[tgt] = {
            "evt_cnt_90d": round(spearman(w["evt_cnt_90d"], w[tgt]), 4),
            "fwd30_evt_cnt_log_corr": round(spearman(w["evt_cnt_90d"], w[tgt]), 4),
        }
    ev["descriptive_spearman_full_n" + str(n_all)] = corr_full

    # ---------------- 6. decile analysis (structure score) ----------------
    sub["struct_decile"] = pd.qcut(sub["structure_pct"], 10, labels=False, duplicates="drop")
    dec = sub.groupby("struct_decile").agg(
        n=("target_address", "count"),
        median_evt_cnt_90d=("evt_cnt_90d", "median"),
        mean_fwd30_evt=("fwd30_evt_cnt", "mean"),
        median_fwd30_evt=("fwd30_evt_cnt", "median"),
        mean_fwd30_cp=("fwd30_cp_distinct", "mean"),
        median_fwd30_cp=("fwd30_cp_distinct", "median"),
        pct_fwd30_active=("fwd30_evt_cnt", lambda s: (s > 0).mean()),
    ).reset_index()
    dec.to_csv(config.DATA / "decile_analysis.csv", index=False)
    ev["decile_analysis"] = dec.to_dict("records")

    # ---------------- 7. top-K descriptive selection ----------------
    ks = [10, 25, 50, 100, 250, 500, 1000]
    topk = {}
    for k in ks:
        row = {}
        sel = sub.nlargest(k, "structure_pct")
        sel_v = sub.nlargest(k, "evt_cnt_90d")
        sel_s = sub.nlargest(k, "static_pagerank")
        row["struct_mean_fwd30_evt"] = round(sel["fwd30_evt_cnt"].mean(), 2)
        row["struct_mean_fwd30_cp"] = round(sel["fwd30_cp_distinct"].mean(), 2)
        row["vol_mean_fwd30_evt"] = round(sel_v["fwd30_evt_cnt"].mean(), 2)
        row["vol_mean_fwd30_cp"] = round(sel_v["fwd30_cp_distinct"].mean(), 2)
        row["static_pr_mean_fwd30_evt"] = round(sel_s["fwd30_evt_cnt"].mean(), 2)
        row["static_pr_mean_fwd30_cp"] = round(sel_s["fwd30_cp_distinct"].mean(), 2)
        topk[str(k)] = row
    topk["all_subgraph_mean_fwd30_evt"] = round(sub["fwd30_evt_cnt"].mean(), 2)
    topk["all_subgraph_mean_fwd30_cp"] = round(sub["fwd30_cp_distinct"].mean(), 2)
    ev["topk_descriptive_selection"] = topk

    # ---------------- 8. dynamic communities (as-of + monthly) ----------------
    top100 = sub.nlargest(100, "structure_pct")
    hub_thr = sub["hub_score"].quantile(0.90)
    bridge_thr = sub["bridge_score"].quantile(0.90)
    top100_bridge = top100["bridge_score"] >= bridge_thr
    top100_hub = top100["hub_score"] >= hub_thr
    ev["dynamic_communities"] = {
        "n_communities_asof": int(sub["community_id"].nunique()),
        "top100_share_hub_top10pct": round((top100["hub_score"] >= hub_thr).mean(), 4),
        "top100_share_bridge_top10pct": round((top100["bridge_score"] >= bridge_thr).mean(), 4),
        "top100_share_bridge_only": round((top100_bridge & ~top100_hub).mean(), 4),
        "top100_share_hub_only": round((top100_hub & ~top100_bridge).mean(), 4),
        "top100_share_both": round((top100_bridge & top100_hub).mean(), 4),
        "all_share_hub_top10pct": round((sub["hub_score"] >= hub_thr).mean(), 4),
        "all_share_bridge_top10pct": round((sub["bridge_score"] >= bridge_thr).mean(), 4),
        "n_boundary_wallets": int(sub["is_boundary"].sum()),
        "boundary_vs_hub_fwd30_evt_mean": {
            "boundary": round(sub[sub.is_boundary]["fwd30_evt_cnt"].mean(), 2),
            "non_boundary": round(sub[~sub.is_boundary]["fwd30_evt_cnt"].mean(), 2),
        },
        "top100_community_concentration_hhi": round(
            ((top100.groupby("community_id").size() / len(top100)) ** 2).sum(), 4),
    }

    # monthly community evolution (post-hoc descriptive, pre-cutoff data only)
    edges = pd.read_csv(config.DATA / "edges_asof_20220901.csv")
    mc = monthly_communities(edges)
    ev["monthly_communities"] = {}
    for prev_m, cur_m in [("2022-06", "2022-07"), ("2022-07", "2022-08")]:
        mapping = match_communities(mc[prev_m], mc[cur_m])
        switched = 0
        total = 0
        for n, cci in mc[cur_m].items():
            if n in mc[prev_m]:
                total += 1
                if mapping.get(cci, -1) != mc[prev_m][n]:
                    switched += 1
        ev["monthly_communities"][f"{prev_m}->{cur_m}"] = {
            "n_wallets_common": total,
            "switch_rate": round(switched / total, 4) if total else None,
        }

    # ---------------- flow-oriented PageRank robustness ----------------
    edges_df = pd.read_csv(config.DATA / "edges_asof_20220901.csv")
    ev["flow_pagerank_robustness"] = flow_pagerank_robustness(
        edges_df, sub.set_index("target_exgraph_node_id")["pagerank"])

    # ---------------- write outputs ----------------
    out_cols = (["target_address", "target_exgraph_node_id", "evt_cnt_90d",
                 "volume_pct", "structure_pct", "fwd30_evt_cnt",
                 "fwd30_cp_distinct", "fwd30_new_cp", "p2_score",
                 "icf_score_p1", "p1_rank"] +
                ["static_" + c for c in ["degree", "w_degree", "pagerank"]] +
                [c for c in struct_cols if c in sub.columns] +
                ["community_id", "community_size", "within_comm_wdeg",
                 "cross_comm_wdeg", "cross_comm_share", "bridge_score",
                 "hub_score", "is_boundary"])
    out_cols = list(dict.fromkeys(c for c in out_cols if c in sub.columns))
    out = sub[out_cols].copy()
    out.to_csv(config.DATA / "wallet_importance_20220901.csv", index=False)

    summary = {
        "protocol_ref": "research/audit/temporal_protocol.yaml v1.0",
        "cutoff": config.CUTOFF,
        "lookback_window": [config.LOOKBACK_START, config.CUTOFF],
        "label_window": [config.CUTOFF, config.LABEL_END],
        "claim_boundaries": {
            "structural_importance_ne_predictive_influence": True,
            "structural_importance_ne_causality": True,
            "evaluation_is_descriptive_not_out_of_sample_superiority": True,
            "static_prior_is_leaky_external_baseline_only": True,
        },
        **ev,
    }
    with open(config.RESULTS / "evidence_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print("[done] evidence_summary.json written")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("descriptive_spearman_subgraph_n7929",
                                   "descriptive_spearman_full_n18519",
                                   "decile_analysis", "topk_descriptive_selection")},
                     indent=2, default=str)[:4000])


if __name__ == "__main__":
    evaluate()
