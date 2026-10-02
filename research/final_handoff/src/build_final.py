#!/usr/bin/env python
"""FINAL group — build final important-wallet rankings + single frozen evaluation at cutoff 2022-09-01.

Read-only inputs (frozen Group A/B/C/D + CHIEF/selection_eval artifacts). CPU only, no LLM, no BigQuery.
Writes ONLY under research/final_handoff/:
  final_ranking_20220901.csv
  final_topk_lists_20220901.csv
  final_topk_lists_20220901.json
  final_evaluation_20220901.json
Protocol: research/audit/temporal_protocol.yaml v1.0 (frozen 2026-09-11); final holdout evaluated exactly once.
"""
from __future__ import annotations
import json
import os

import numpy as np
import pandas as pd

REPO = "/storage/gaoym/ex-graph-microtransaction-analysis"
OUT = os.path.join(REPO, "research/final_handoff")
CUTOFF = "2022-09-01"
KS = [10, 25, 50, 100, 250, 500, 1000]

P = {
    "labels": os.path.join(REPO, "research/groupB_predictive/results/data/labels_20220901_bq.csv"),
    "feature_matrix": os.path.join(REPO, "research/groupA_behavior/results/data/feature_matrix_20220901.parquet"),
    "persona": os.path.join(REPO, "research/groupA_behavior/results/persona_assignments_20220901.csv"),
    "predictions": os.path.join(REPO, "research/groupB_predictive/results/holdout09_predictions.csv"),
    "structural": os.path.join(REPO, "research/groupC_temporal_graph/results/data/wallet_importance_20220901.csv"),
    "ig": os.path.join(REPO, "research/groupD_infogain/results/wallet_ig_20220901.csv"),
    "sel_results": os.path.join(REPO, "research/selection_eval/results/selection_results_20220901.json"),
    "consensus_summary": os.path.join(REPO, "research/chief_merge/consensus_analysis/results/consensus_summary.json"),
    "consensus_freq": os.path.join(REPO, "research/chief_merge/consensus_analysis/results/consensus_frequency.csv"),
}

BEH_FEATS = [
    "evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
    "evt_native_90d", "evt_token_90d", "active_days_90d", "tx_cnt_90d",
    "active_span_days_90d", "cp_distinct_90d", "cp_out_distinct_90d",
    "cp_in_distinct_90d", "cp_out_interact_90d", "cp_in_interact_90d",
    "token_distinct_90d", "cp_new_30d", "cp_new_rate_30d",
    "cp_reciprocity_90d", "token_event_rate_90d", "events_per_active_day_90d",
    "n_events_90d_traj", "active_days_90d_traj", "active_span_days_traj",
]
TEMPORAL_FEATS = ["score_recency", "cp_new_rate_30d", "active_span_days_90d"]

# ---------------------------------------------------------------------------
# 1. Load frozen inputs
# ---------------------------------------------------------------------------
def load():
    lbl = pd.read_csv(P["labels"])
    assert lbl.target_address.nunique() == len(lbl) == 18519
    lbl = lbl.rename(columns={"fwd30_evt_cnt": "lbl_evt",
                              "fwd30_cp_distinct": "lbl_cp",
                              "fwd30_new_cp": "lbl_new"})
    lbl = lbl[["target_address", "lbl_evt", "lbl_cp", "lbl_new"]]
    fm = pd.read_parquet(P["feature_matrix"])
    pr = pd.read_csv(P["predictions"])
    pa = pd.read_csv(P["persona"])
    st = pd.read_csv(P["structural"])
    ig = pd.read_csv(P["ig"])
    return lbl, fm, pr, pa, st, ig


def assemble(lbl, fm, pr, pa, st, ig):
    base = lbl.copy()
    fm_cols = (["target_address", "target_exgraph_node_id", "target_is_x_matched",
               "last_event_recency_days", "in_mm_subgraph"]
               + BEH_FEATS + ["cp_new_rate_30d", "cp_new_30d", "score_recency"])
    fm_cols = list(dict.fromkeys(c for c in fm_cols if c in fm.columns))
    base = base.merge(fm[fm_cols], on="target_address", how="left")
    base = base.merge(pr[["target_address", "pred_act_level_LightGBM",
                          "pred_new_level_LightGBM"]]
                      .rename(columns={"pred_act_level_LightGBM": "pred_act",
                                       "pred_new_level_LightGBM": "pred_new"}),
                      on="target_address", how="left")
    base = base.merge(pa[["target_address", "full_asof__kmeans", "trajectory__kmeans"]],
                      on="target_address", how="left")
    stcols = ["target_address", "target_exgraph_node_id", "structure_pct",
              "structure_novol_pct", "deg_und", "wdeg_und", "pagerank", "kcore",
              "betweenness", "bridge_score", "static_degree", "static_pagerank",
              "community_id", "community_size", "is_boundary", "activity_trend",
              "active_months"]
    st2 = st[stcols].rename(columns={"target_exgraph_node_id": "node_id_struct"})
    base = base.merge(st2, on="target_address", how="left")
    ig_cp = ig[(ig["target"] == "y_cp_ge10") & (ig["model"] == "histgbm")] \
        .set_index("target_address")["ig_occ"]
    ig_act = ig[(ig["target"] == "y_active30") & (ig["model"] == "histgbm")] \
        .set_index("target_address")["ig_occ"]
    base["ig_cp"] = base["target_address"].map(ig_cp)
    base["ig_active"] = base["target_address"].map(ig_act)
    # temporal composite: percentile-mean of recency + acceleration + persistence
    base["score_recency"] = 90.0 - base["last_event_recency_days"]
    for f in TEMPORAL_FEATS:
        base[f + "_pct"] = base[f].rank(pct=True)
    base["I_temporal"] = base[[f + "_pct" for f in TEMPORAL_FEATS]].mean(axis=1)
    # A_beh composite (chief-merge reconstruction)
    for f in BEH_FEATS:
        base[f + "_pct"] = base[f].rank(pct=True)
    base["A_beh"] = base[[f + "_pct" for f in BEH_FEATS]].mean(axis=1)
    # percentile variants for headline vector
    base["I_behavior"] = base["A_beh"]
    base["I_network"] = base["structure_pct"]
    base["I_predictive"] = base["pred_act"]
    base["I_information"] = base["ig_cp"]
    base["persona_full_asof_kmeans"] = base["full_asof__kmeans"]
    base["persona_trajectory_kmeans"] = base["trajectory__kmeans"]
    base["I_network_novol"] = base["structure_novol_pct"]
    base["I_predictive_new"] = base["pred_new"]
    base["I_information_active"] = base["ig_active"]
    # random draw (identical seed to selection_eval)
    rng = np.random.default_rng(20220901)
    base["score_random"] = rng.random(len(base))
    return base

# ---------------------------------------------------------------------------
# 2. Per-method scores, ranks and top-K sets
# ---------------------------------------------------------------------------
METHODS = {
    # key: (label, score_column, support, higher_is_better)
    "B_act":        ("Predictive influence (future activity level)", "pred_act", "full", True),
    "B_new":        ("Predictive influence (future new counterparties)", "pred_new", "full", True),
    "C_struct":     ("Structural importance (structure_pct)", "structure_pct", "structural", True),
    "C_novol":      ("Structural importance w/o volume (structure_novol_pct)", "structure_novol_pct", "structural", True),
    "A_vol":        ("Volume baseline (evt_cnt_90d)", "evt_cnt_90d", "full", True),
    "A_beh":        ("Behavioral composite baseline (A_beh)", "A_beh", "full", True),
    "D_ig_cp":      ("Information gain (ig_cp)", "ig_cp", "ig", True),
    "D_ig_act":     ("Information gain (ig_active)", "ig_active", "ig", True),
    "hybrid_pred_vol": ("Hybrid predictive+volume", "hybrid_pred_vol", "full", True),
    "temporal":     ("Temporal composite (recency+accel+persistence)", "I_temporal", "full", True),
    "random":       ("Random (seed=20220901)", "score_random", "full", True),
}
SUPPORT_SIZES = {"full": 18519, "structural": 7929, "ig": 2999}


def add_derived(base):
    base = base.copy()
    base["hybrid_pred_vol"] = (base["pred_act"].rank(pct=True)
                               + base["evt_cnt_90d"].rank(pct=True)) / 2.0
    return base


def make_ranks(base):
    """rank 1 = best within the method's own support (NaN = outside support)."""
    out = {}
    for key, (label, col, support, hib) in METHODS.items():
        df = base.dropna(subset=[col]).copy()
        df["_score"] = df[col] if hib else -df[col]
        df = df.sort_values(["_score", "target_address"], ascending=[False, True])
        df["rank"] = np.arange(1, len(df) + 1)
        out[key] = df[["target_address", col, "rank"]].rename(columns={col: "score"})
    return out


def topk(ranks, key, k):
    return ranks[key].head(k)


def consensus_topk(ranks, keys, k):
    """wallets ranked top-K by ALL given methods (n_all_methods consensus)."""
    sets = [set(ranks[m].head(k).target_address) for m in keys]
    inter = set.intersection(*sets) if sets else set()
    df = ranks[keys[0]][ranks[keys[0]]["target_address"].isin(inter)] \
        if inter else pd.DataFrame(columns=["target_address", "score", "rank"])
    return df.sort_values("rank")

# ---------------------------------------------------------------------------
# 3. Single frozen evaluation (identical formulas to selection_eval/evaluate.py)
# ---------------------------------------------------------------------------
LABEL_COLS = {"lbl_evt": "fwd30_evt_cnt", "lbl_cp": "fwd30_cp_distinct", "lbl_new": "fwd30_new_cp"}


def evaluate_method(base, ranks, key, k):
    spec = METHODS[key]
    col = spec[1]
    sup = base.dropna(subset=[col])
    sel = topk(ranks, key, k).merge(
        base[["target_address", "lbl_evt", "lbl_cp", "lbl_new"]],
        on="target_address", how="left")
    n = len(sel)
    row = {"method": key, "k": k, "support": spec[2],
           "n_support": int(len(sup)), "n_selected": n}
    for lc, ln in LABEL_COLS.items():
        tot = float(sup[lc].sum())
        s = float(sel[lc].sum())
        row[f"U_{ln}_sum"] = s
        row[f"U_{ln}_perK"] = s / n if n else float("nan")
        row[f"mass_share_{ln}"] = s / tot if tot else float("nan")
    pos_new = int((sup["lbl_new"] > 0).sum())
    pos_evt = int((sup["lbl_evt"] > 0).sum())
    row["Recall@K_new_pos"] = float((sel["lbl_new"] > 0).sum() / pos_new) if pos_new else float("nan")
    row["Recall@K_evt_pos"] = float((sel["lbl_evt"] > 0).sum() / pos_evt) if pos_evt else float("nan")
    row["support_frac"] = k / len(sup) if len(sup) else float("nan")
    return row


def evaluate_consensus(base, ranks, keys, k, support_key):
    sup = base[base["in_mm_subgraph"] == True] if support_key == "structural" else base
    sel = consensus_topk(ranks, keys, k).merge(
        base[["target_address", "lbl_evt", "lbl_cp", "lbl_new"]],
        on="target_address", how="left")
    n = len(sel)
    row = {"method": "_".join(keys), "k": k, "support": support_key,
           "n_support": int(len(sup)), "n_selected": n}
    if n == 0:
        for lc, ln in LABEL_COLS.items():
            row[f"U_{ln}_sum"] = 0.0; row[f"U_{ln}_perK"] = float("nan")
            row[f"mass_share_{ln}"] = 0.0
        row["Recall@K_new_pos"] = 0.0; row["Recall@K_evt_pos"] = 0.0
        row["support_frac"] = 0.0
        return row
    for lc, ln in LABEL_COLS.items():
        tot = float(sup[lc].sum())
        s = float(sel[lc].sum())
        row[f"U_{ln}_sum"] = s
        row[f"U_{ln}_perK"] = s / n
        row[f"mass_share_{ln}"] = s / tot if tot else float("nan")
    pos_new = int((sup["lbl_new"] > 0).sum())
    pos_evt = int((sup["lbl_evt"] > 0).sum())
    row["Recall@K_new_pos"] = float((sel["lbl_new"] > 0).sum() / pos_new) if pos_new else float("nan")
    row["Recall@K_evt_pos"] = float((sel["lbl_evt"] > 0).sum() / pos_evt) if pos_evt else float("nan")
    row["support_frac"] = n / len(sup) if len(sup) else float("nan")
    return row


def random_expected(base):
    sup = base.dropna(subset=["lbl_new"])
    mean = {lc: float(sup[lc].mean()) for lc in LABEL_COLS}
    return {k: {lc: k * m for lc, m in mean.items()} for k in KS}, mean

# ---------------------------------------------------------------------------
# 4. Verification against frozen single-evaluation artifacts
# ---------------------------------------------------------------------------
def verify(base, ranks):
    sel = json.load(open(P["sel_results"]))
    con = json.load(open(P["consensus_summary"]))
    problems = []
    # 1) selector frontier parity (selection_eval frozen single evaluation)
    frozen = {(r["selector"], r["k"]): r for r in sel["frontier_native"]}
    for key, k in [(m, k) for m in ["B_act", "B_new", "C_struct", "C_novol",
                                    "A_vol", "A_beh", "D_ig_cp", "D_ig_act",
                                    "hybrid_pred_vol", "temporal", "random"]
                   for k in KS]:
        fr = frozen.get((key, k))
        if fr is None:
            continue
        mine = evaluate_method(base, ranks, key, k)
        for f in ["u_fwd30_evt_cnt_mean", "recall_new_pos"]:
            a = fr[f]
            b = mine["U_fwd30_evt_cnt_perK"] if f.startswith("u_") else mine["Recall@K_new_pos"]
            if np.isnan(a) and np.isnan(b):
                continue
            if not np.isclose(a, b, rtol=1e-6, atol=1e-6):
                problems.append(f"selector {key} k={k} {f}: frozen={a} mine={b}")
    # 2) B_C_A consensus parity (chief_merge consensus_summary)
    bca = con["consensus_sets"]["B_C_A"]
    for k in KS:
        n_frozen = bca[str(k)].get("n_all_methods", 0) or 0
        n_mine = len(consensus_topk(ranks, ["B_act", "C_struct", "A_vol"], k))
        if n_frozen != n_mine:
            problems.append(f"consensus B_C_A k={k}: frozen={n_frozen} mine={n_mine}")
        if n_mine and bca[str(k)].get("consensus_mean_fwd30_evt") is not None:
            m = consensus_topk(ranks, ["B_act", "C_struct", "A_vol"], k)
            mean_mine = float(m.merge(base[["target_address", "lbl_evt"]], on="target_address")["lbl_evt"].mean())
            if not np.isclose(mean_mine, bca[str(k)]["consensus_mean_fwd30_evt"], rtol=1e-6, atol=1e-3):
                problems.append(f"consensus B_C_A k={k} mean: frozen={bca[str(k)]['consensus_mean_fwd30_evt']} mine={mean_mine}")
    # 3) support sizes
    for name, col in [("full", "pred_act"), ("structural", "structure_pct"), ("ig", "ig_cp")]:
        n = int(base[col].notna().sum())
        if n != SUPPORT_SIZES[name]:
            problems.append(f"support {name}: expected {SUPPORT_SIZES[name]}, got {n}")
    return problems


# ---------------------------------------------------------------------------
# 5. Build outputs
# ---------------------------------------------------------------------------
def build_ranking_csv(base, ranks):
    rcols = {m: ranks[m].set_index("target_address")["rank"]
             for m in METHODS}
    for m, s in rcols.items():
        base[f"rank_{m}"] = base["target_address"].map(s)
    # consensus votes at K=100 and K=1000
    for K in (100, 1000):
        for m in ("B_act", "C_struct", "D_ig_cp", "A_vol"):
            top = set(ranks[m].head(K).target_address)
            base[f"top{K}_{m}"] = base["target_address"].isin(top).astype(int)
            base.loc[~base["target_address"].isin(ranks[m].target_address),
                     f"top{K}_{m}"] = np.nan
        b = [f"top{K}_{m}" for m in ("B_act", "C_struct", "A_vol")]
        d = b + [f"top{K}_D_ig_cp"]
        base[f"votes_BCA_top{K}"] = base[b].sum(axis=1)
        base[f"votes_BCDA_top{K}"] = base[d].sum(axis=1)

    cols = ["target_address", "target_exgraph_node_id", "target_is_x_matched",
            "in_structural_support", "in_ig_support",
            "persona_full_asof_kmeans", "persona_trajectory_kmeans",
            "community_id", "community_size", "is_boundary",
            "I_behavior", "I_network", "I_network_novol",
            "I_predictive", "I_predictive_new",
            "I_information", "I_information_active", "I_temporal",
            "score_recency", "cp_new_rate_30d", "active_span_days_90d",
            "deg_und", "wdeg_und", "pagerank", "kcore", "betweenness", "bridge_score",
            "evt_cnt_90d",
            "rank_B_act", "rank_B_new", "rank_C_struct", "rank_C_novol",
            "rank_A_vol", "rank_A_beh", "rank_D_ig_cp", "rank_D_ig_act",
            "rank_hybrid_pred_vol", "rank_temporal", "rank_random",
            "top100_B_act", "top100_C_struct", "top100_D_ig_cp", "top100_A_vol",
            "votes_BCA_top100", "votes_BCDA_top100",
            "top1000_B_act", "top1000_C_struct", "top1000_D_ig_cp", "top1000_A_vol",
            "votes_BCA_top1000", "votes_BCDA_top1000",
            "lbl_evt", "lbl_cp", "lbl_new"]
    out = base[cols].copy()
    out = out.sort_values(["rank_B_act", "target_address"])
    out["in_structural_support"] = out["in_structural_support"].astype(int)
    out["in_ig_support"] = out["in_ig_support"].astype(int)
    out["target_is_x_matched"] = out["target_is_x_matched"].astype(int)
    out.to_csv(os.path.join(OUT, "final_ranking_20220901.csv"), index=False)
    return out


def build_topk_csv(base, ranks):
    rows = []
    methods = list(METHODS.keys()) + ["consensus_BCA", "consensus_BCDA"]
    for key in methods:
        for k in KS:
            if key == "consensus_BCA":
                df = consensus_topk(ranks, ["B_act", "C_struct", "A_vol"], k)
                support = "structural"
            elif key == "consensus_BCDA":
                df = consensus_topk(ranks, ["B_act", "C_struct", "D_ig_cp", "A_vol"], k)
                support = "ig_intersection"
            else:
                df = topk(ranks, key, k)
                support = METHODS[key][2]
            df = df.merge(base[["target_address", "target_exgraph_node_id",
                                "lbl_evt", "lbl_cp", "lbl_new"]],
                          on="target_address", how="left")
            df = df.reset_index(drop=True)
            df["method"] = key
            df["K"] = k
            df["rank"] = np.arange(1, len(df) + 1)
            df["support"] = support
            rows.append(df[["method", "K", "rank", "target_address",
                            "target_exgraph_node_id", "score", "support",
                            "lbl_evt", "lbl_cp", "lbl_new"]])
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(os.path.join(OUT, "final_topk_lists_20220901.csv"), index=False)
    return out


def build_topk_json(base, ranks):
    out = {}
    for key in list(METHODS.keys()) + ["consensus_BCA", "consensus_BCDA"]:
        out[key] = {}
        for k in KS:
            if key == "consensus_BCA":
                df = consensus_topk(ranks, ["B_act", "C_struct", "A_vol"], k)
            elif key == "consensus_BCDA":
                df = consensus_topk(ranks, ["B_act", "C_struct", "D_ig_cp", "A_vol"], k)
            else:
                df = topk(ranks, key, k)
            recs = df.reset_index(drop=True).to_dict(orient="records")
            recs = [{"target_address": r["target_address"],
                     "score": None if pd.isna(r["score"]) else float(r["score"]),
                     "rank": int(i + 1)} for i, r in enumerate(recs)]
            out[key][str(k)] = recs
    return out


def build_eval_json(base, ranks, problems):
    sel = json.load(open(P["sel_results"]))
    con = json.load(open(P["consensus_summary"]))
    eval_rows = {}
    for key in ["B_act", "B_new", "C_struct", "C_novol", "A_vol", "A_beh",
                "D_ig_cp", "D_ig_act", "hybrid_pred_vol", "temporal", "random"]:
        eval_rows[key] = {str(k): evaluate_method(base, ranks, key, k) for k in KS}
    cons = {}
    for name, keys, sup in [("B_C_A", ["B_act", "C_struct", "A_vol"], "structural"),
                            ("B_C_D_A", ["B_act", "C_struct", "D_ig_cp", "A_vol"], "ig_intersection")]:
        cons[name] = {}
        for k in KS:
            cons[name][str(k)] = evaluate_consensus(base, ranks, keys, k, sup)
    rexp, rexp_mean = random_expected(base)
    frozen_re = {r["k"]: r for r in sel["random_expected"]}
    oracle = [r for r in sel["oracle_reference"] if r["selector"] == "oracle_fwd30_new_cp"
              and r["scope"] == "full"]
    result = {
        "task": "FINAL important-wallet ranking at cutoff 2022-09-01 (autoresearch_phase1.md §13/§14/§16/§23)",
        "protocol_ref": "research/audit/temporal_protocol.yaml v1.0 (frozen 2026-09-11)",
        "data_audit_ref": "research/audit/DATA_AUDIT.md",
        "chief_recommendation": "research/chief_merge/method_recommendation.md",
        "generated_by": "research/final_handoff/src/build_final.py",
        "cutoff": CUTOFF,
        "label_window": "[2022-09-01, 2022-10-01)",
        "single_evaluation_statement": (
            "final holdout 2022-09-01 evaluated EXACTLY ONCE with frozen selector "
            "definitions from Groups B/C/D and selection_eval; K is NOT tuned on the "
            "holdout (the full K frontier is reported as §16 sensitivity analysis)."
        ),
        "no_future_leakage": (
            "all selector scores use only information strictly before 2022-09-01 "
            "(as-of features, frozen Group B OOS predictions, Group C as-of structural, "
            "Group D as-of IG); fwd30 labels used ONLY for evaluation."
        ),
        "primary_method": {"key": "B_act", "definition": "predictive influence = LightGBM OOS prediction of future activity level (pred_act_level_LightGBM)"},
        "secondary_method": {"key": "C_struct", "definition": "structural importance = as-of structure_pct composite (support 7,929; no extrapolation)"},
        "forced_baselines": ["A_vol (volume, evt_cnt_90d)", "random (seed=20220901)", "random_expected (analytic)"],
        "consensus_complement": "B∩C∩A (all-methods agreement over B_act, C_struct, A_vol; support 7,929)",
        "universe": {"n": 18519, "source": "wallet_asof_features_20220901 via groupB labels pull"},
        "support_boundaries": sel["support_boundaries"],
        "evaluation": eval_rows,
        "consensus_evaluation": cons,
        "references": {
            "random_expected_perK": rexp_mean,
            "random_expected_sums": rexp,
            "oracle_fwd30_new_cp_full": oracle,
        },
        "key_findings": {
            "B_act_vs_A_vol_rank_corr": 0.9302,
            "B_act_vs_C_struct_rank_corr": 0.5360,
            "B_act_vs_D_ig_cp_rank_corr": 0.3784,
            "B_act_vs_A_vol_top100_jaccard": 0.460,
            "D_top100_uniqueness": 0.94,
            "consensus_BCA_K100": {"n_all": 28, "mean_fwd30_evt": 916.89, "lift_vs_support": 26.90},
            "note": "consensus != correctness (§17); B≈A_vol in rank order; D is an orthogonal dimension",
        },
        "verification": {
            "parity_ok": len(problems) == 0,
            "problems": problems,
            "verified_against": [
                "research/selection_eval/results/selection_results_20220901.json",
                "research/chief_merge/consensus_analysis/results/consensus_summary.json",
            ],
        },
        "compute": {"mode": "local CPU, no LLM, no BigQuery (reuses frozen artifacts only)"},
    }
    with open(os.path.join(OUT, "final_evaluation_20220901.json"), "w") as f:
        json.dump(result, f, indent=1, default=float)
    return result

def main():
    lbl, fm, pr, pa, st, ig = load()
    base = assemble(lbl, fm, pr, pa, st, ig)
    base = add_derived(base)
    base["in_structural_support"] = base["structure_pct"].notna()
    base["in_ig_support"] = base["ig_cp"].notna()
    ranks = make_ranks(base)
    problems = verify(base, ranks)
    print("VERIFICATION problems:", problems if problems else "NONE (parity OK)")

    build_ranking_csv(base, ranks)
    build_topk_csv(base, ranks)
    topk_json = build_topk_json(base, ranks)
    with open(os.path.join(OUT, "final_topk_lists_20220901.json"), "w") as f:
        json.dump({
            "cutoff": CUTOFF,
            "protocol_ref": "research/audit/temporal_protocol.yaml v1.0",
            "methods": {k: {"label": v[0], "score_column": v[1], "support": v[2]}
                        for k, v in METHODS.items()},
            "consensus_methods": {
                "consensus_BCA": "wallets in top-K of B_act AND C_struct AND A_vol (support 7,929)",
                "consensus_BCDA": "wallets in top-K of B_act AND C_struct AND D_ig_cp AND A_vol (support 1,283 intersection)",
            },
            "topk": topk_json,
        }, f, indent=1, default=float)

    build_eval_json(base, ranks, problems)
    print("wrote: final_ranking_20220901.csv, final_topk_lists_20220901.csv/.json, final_evaluation_20220901.json")


if __name__ == "__main__":
    main()
