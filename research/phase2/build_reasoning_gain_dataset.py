#!/usr/bin/env python3
"""Build research/phase2/reasoning_gain_dataset.parquet (P2DATA, Phase II-A).

One row per (event_id, wallet_id, cutoff_time). Sources:
  - Qwen rerun go/nogo panels (authoritative LLM arms)
  - router datasets (pre-call features only; gain labels there are legacy/buggy-era)
  - as-of wallet behavior/network, community, structure (09-only), IG (09-only)
RV follows the frozen Phase-I go/nogo protocol (see manifest).
"""
import json
import os
from pathlib import Path
import pandas as pd

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[2]))
OUT = ROOT / "research" / "phase2" / "reasoning_gain_dataset.parquet"
MANIFEST = ROOT / "research" / "phase2" / "reasoning_gain_manifest.json"

EVENT_KEY = ["snapshot_date", "target_address", "target_sequence_index"]

RUN_FILES = {
    "2022-06-01": ROOT / "artifacts/llm_panel_v2/runs/jun_gonogo_local_vllm4b_rerun_20260910.csv",
    "2022-07-01": ROOT / "artifacts/llm_panel_v2/runs/jul_gonogo_local_vllm4b_rerun_20260910.csv",
    "2022-08-01": ROOT / "artifacts/llm_panel_v2/runs/aug_gonogo_local_vllm4b_rerun_20260910.csv",
    "2022-09-01": ROOT / "artifacts/llm_panel_20220901/runs/sept_gonogo_local_vllm4b_rerun_20260910.csv",
}
ROUTER_FILES = {
    "2022-06-01": ROOT / "artifacts/llm_panel_v2/router_dataset_v2.csv",
    "2022-07-01": ROOT / "artifacts/llm_panel_v2/router_dataset_v2.csv",
    "2022-08-01": ROOT / "artifacts/llm_panel_v2/router_dataset_v2.csv",
    "2022-09-01": ROOT / "artifacts/llm_panel_20220901/sept_router_scores.csv",
}
PANEL_V2 = ROOT / "artifacts/llm_panel_v2/panel_scored_v2.csv.gz"   # jun/jul/aug (+sept rows)
PANEL_SEPT = ROOT / "artifacts/llm_panel_20220901/panel_scored_sept_v2_frozen.csv.gz"

ASOF_MONTHLY = ROOT / "research/groupA_behavior/results/data/asof_monthly_2022.parquet"
FEAT_MATRIX_09 = ROOT / "research/groupA_behavior/results/data/feature_matrix_20220901.parquet"
WALLET_IMP_09 = ROOT / "research/groupC_temporal_graph/results/data/wallet_importance_20220901.csv"
IG_09 = ROOT / "research/groupD_infogain/results/wallet_ig_20220901.csv"
COMM_DIR = ROOT / "research/community_temporal/results/data"

LAMBDA_COST = 1.0  # RV_cost = RV_MRR / (total_tokens + LAMBDA*latency_s)
DELTA_Z0, DELTA_Z1 = 0.0, 0.1

BEHAV_FEATS = ["evt_cnt_90d","evt_out_90d","evt_in_90d","evt_self_90d","evt_native_90d",
 "evt_token_90d","active_days_90d","tx_cnt_90d","active_span_days_90d","cp_distinct_90d",
 "cp_out_distinct_90d","cp_in_distinct_90d","cp_out_interact_90d","cp_in_interact_90d",
 "token_distinct_90d","cp_entropy_90d","cp_new_30d","cp_new_rate_30d","cp_both_dir_90d",
 "cp_reciprocity_90d","self_tx_rate_90d","token_event_rate_90d","token_hhi_90d",
 "events_per_active_day_90d"]
NET_FEATS = ["asof_mm_in_degree","asof_mm_out_degree","asof_mm_undir_degree",
 "asof_mm_w_in_degree","asof_mm_w_out_degree","asof_mm_pagerank","asof_mm_kcore",
 "asof_mm_clustering","asof_mm_hub_neighbors"]
FUTURE_LABELS = ["fwd30_evt_cnt","fwd30_cp_distinct","fwd30_cp_out_distinct","fwd30_new_cp"]
LEAKAGE_EXCLUDE = ["importance_proxy_p3","in_mm_subgraph","target_is_x_matched",
                   "target_exgraph_node_id"] + FUTURE_LABELS

ROUTER_PRECALL = ["cp_type_repeat","evt_cnt_90d","cp_entropy_90d","cp_new_rate_30d","pool_n",
 "cheap_top_score","cheap_margin","cheap_score_entropy","frac_bridge","frac_personal","frac_tail",
 "frac_top2000","n_bridge","n_personal","top1_is_personal","top1_is_bridge","pop_weight",
 "log_evt_cnt","log_pool_n","log_n_bridge","log_n_personal"]
ROUTER_LEGACY_GAIN = ["gain_full","gain_nocf","full_wins"]
STRUCT09_COLS = ["static_degree","static_w_degree","static_pagerank","deg_und","wdeg_und",
 "pagerank","kcore","betweenness","recency_wdeg","activity_trend","active_months",
 "persistent_edges","mutual_pairs","triangles","new_edges_recent","cross_comm_share",
 "bridge_score","hub_score","structure_novol_pct"]
COMM_COLS = ["community_id","community_size","within_comm_wdeg","cross_comm_wdeg",
 "cross_comm_share","within_comm_deg","cross_comm_deg","bridge_score","hub_score",
 "is_boundary","betweenness"]
COMM_JSON_COLS = ["comm_community_id","comm_community_size","comm_within_comm_wdeg","comm_cross_comm_wdeg",
 "comm_bridge_score","comm_hub_score","comm_is_boundary"]
IG_COLS = ["ig_occ_cp10_histgbm","ig_occ_cp10_logistic","ig_occ_act30_histgbm",
 "ig_occ_act30_logistic","ig_occ_mean","ig_perm_mean"]

def load_runs():
    parts = []
    for cutoff, path in RUN_FILES.items():
        d = pd.read_csv(path)
        d["snapshot_date"] = pd.to_datetime(d["snapshot_date"]).dt.date
        d["cutoff_time"] = d["snapshot_date"]
        d["event_id"] = (d["snapshot_date"].astype(str) + "|" + d["target_address"]
                         + "|" + d["target_sequence_index"].astype(str))
        d["wallet_id"] = d["target_address"]
        if d.duplicated(EVENT_KEY).any():
            raise RuntimeError(f"duplicate event keys in {path}")
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    assert len(df) == 4000
    return df

def load_router(runs):
    """Pre-call features from router CSVs (authoritative for these columns only)."""
    out = []
    for cutoff, path in ROUTER_FILES.items():
        r = pd.read_csv(path)
        r["snapshot_date"] = pd.to_datetime(r["snapshot_date"]).dt.date
        r = r[r["snapshot_date"] == pd.to_datetime(cutoff).date()]
        overlap_runs = set(runs.columns)
        keep = EVENT_KEY + [c for c in ROUTER_PRECALL + ROUTER_LEGACY_GAIN
                            if c in r.columns and c not in BEHAV_FEATS and c not in overlap_runs]
        out.append(r[keep])
    rt = pd.concat(out, ignore_index=True)
    n0 = len(runs)
    df = runs.merge(rt, on=EVENT_KEY, how="left")
    got = df[ROUTER_PRECALL[0]].notna().sum()
    print(f"router pre-call join: {got}/{n0}")
    if got != n0:
        raise RuntimeError("router pre-call join incomplete")
    return df

def load_panel_meta(runs):
    """cheap top-1 prediction + truth counterparty metadata from candidate panels."""
    pan = pd.read_csv(PANEL_V2, usecols=EVENT_KEY + ["candidate_address","cheap_score",
        "label","cand_source","g_rank","days_since","truth_g_rank"])
    pan["snapshot_date"] = pd.to_datetime(pan["snapshot_date"]).dt.date
    # panel_scored_v2 already contains all four cutoffs (incl. sept, per its manifest)
    # cheap top-1 (tie-break: candidate_address asc, matching cheap_tie_ranks)
    top = (pan.sort_values(EVENT_KEY + ["cheap_score","candidate_address"],
                           ascending=[True,True,True,False,True])
              .groupby(EVENT_KEY, as_index=False).tail(1)
              [EVENT_KEY + ["candidate_address","cheap_score","cand_source","days_since","g_rank"]])
    top = top.rename(columns={"candidate_address":"cheap_prediction",
                              "cheap_score":"cheap_top_score_panel",
                              "cand_source":"cheap_pred_source",
                              "days_since":"cheap_pred_days_since",
                              "g_rank":"cheap_pred_g_rank"})
    tr = pan[pan["label"] == 1].copy()
    tr = tr.rename(columns={"candidate_address":"future_target",
                            "cheap_score":"truth_cheap_score",
                            "cand_source":"truth_cand_source",
                            "days_since":"counterparty_days_since",
                            "g_rank":"counterparty_g_rank",
                            "truth_g_rank":"counterparty_truth_g_rank"})
    tr = tr[EVENT_KEY + ["future_target","truth_cheap_score","truth_cand_source",
                         "counterparty_days_since","counterparty_g_rank","counterparty_truth_g_rank"]]
    df = runs.merge(top, on=EVENT_KEY, how="left").merge(tr, on=EVENT_KEY, how="left")
    assert df["cheap_prediction"].notna().all() and df["future_target"].notna().all()
    return df

def load_asof_wallet(df):
    """As-of wallet behavior+network features; strict snapshot_date <= cutoff join."""
    am = pd.read_parquet(ASOF_MONTHLY)
    am["snapshot_date"] = pd.to_datetime(am["snapshot_date"]).dt.date
    fm = pd.read_parquet(FEAT_MATRIX_09)
    fm["snapshot_date"] = pd.to_datetime(fm["snapshot_date"]).dt.date
    asof = pd.concat([am, fm], ignore_index=True)
    # strip leakage proxy columns (fwd30_* kept explicitly as future labels below)
    drop = [c for c in ["importance_proxy_p3", "in_mm_subgraph", "target_is_x_matched"]
            if c in asof.columns]
    asof = asof.drop(columns=drop)
    keep = ["snapshot_date", "target_address"] + \
           [c for c in BEHAV_FEATS + NET_FEATS if c in asof.columns] + \
           ["target_exgraph_node_id"] + FUTURE_LABELS
    asof = asof[keep]
    before = len(df)
    df = df.merge(asof, on=["snapshot_date", "target_address"], how="left")
    got = df[BEHAV_FEATS[0]].notna().sum()
    print(f"as-of wallet join: {got}/{before}")
    return df, asof

def load_community(df):
    """Community membership per month (06..09 available; 05/06 events missing -> NaN).
    node_id == target_exgraph_node_id."""
    for cutoff in ["2022-06-01","2022-07-01","2022-08-01","2022-09-01"]:
        mon = cutoff.replace("-","")
        path = COMM_DIR / f"community_membership_{mon}.csv"
        if not path.exists():
            print("community file missing:", path)
            continue
        cm = pd.read_csv(path)
        cm = cm[["node_id"] + COMM_COLS].rename(columns={"node_id":"target_exgraph_node_id"})
        m = df["snapshot_date"].astype(str) == cutoff
        if m.sum() == 0:
            continue
        df.loc[m] = df.loc[m].merge(cm, on="target_exgraph_node_id", how="left",
                                    suffixes=("", "_comm_drop"))
        # merge may reorder; reindex to original order
        df.sort_values(["snapshot_date","target_address","target_sequence_index"], inplace=True)
        df.reset_index(drop=True, inplace=True)
        got = df.loc[m, "community_id"].notna().sum()
        print(f"community {cutoff}: {got}/{int(m.sum())}")
    return df

def load_community2(df):
    """Community membership per month (06..09 available; others -> NaN).
    Builds a single wallet-month table and merges once (clean, no index juggling)."""
    frames = []
    for cutoff in ["2022-06-01","2022-07-01","2022-08-01","2022-09-01"]:
        mon = cutoff.replace("-","")
        path = COMM_DIR / f"community_membership_{mon}.csv"
        if not path.exists():
            continue
        cm = pd.read_csv(path)
        cm = cm[["node_id"] + COMM_COLS].rename(columns={"node_id":"target_exgraph_node_id"})
        cm = cm.rename(columns={c: "comm_" + c for c in COMM_COLS})
        cm["snapshot_date"] = pd.to_datetime(cutoff).date()
        frames.append(cm)
    comm = pd.concat(frames, ignore_index=True)
    before = len(df)
    df = df.merge(comm, on=["snapshot_date","target_exgraph_node_id"], how="left")
    got = df["comm_community_id"].notna().sum()
    print(f"community join: {got}/{before}")
    return df

def load_struct09(df):
    """Wallet importance / structural features: 2022-09-01 only -> NaN elsewhere."""
    wi = pd.read_csv(WALLET_IMP_09)
    keep = ["target_address"] + [c for c in STRUCT09_COLS if c in wi.columns]
    df = df.merge(wi[keep], on="target_address", how="left")
    m09 = df["snapshot_date"].astype(str) == "2022-09-01"
    for c in STRUCT09_COLS:
        if c in df.columns:
            df.loc[~m09, c] = float("nan")
    got = df.loc[m09, "static_degree"].notna().sum()
    print(f"structure09 join: {got}/{int(m09.sum())}")
    return df

def load_ig09(df):
    """Wallet IG: 2022-09-01 subset only -> NaN elsewhere."""
    ig = pd.read_csv(IG_09)
    wide = ig.pivot_table(index="target_address", columns=["target","model"],
                          values="ig_occ", aggfunc="mean")
    wide.columns = ["ig_occ_" + t + "_" + mo for (t, mo) in wide.columns]
    wide = wide.rename(columns=lambda c: c.replace("y_",""))
    wide["ig_occ_mean"] = ig.groupby("target_address")["ig_occ"].mean()
    wide["ig_perm_mean"] = ig.groupby("target_address")["ig_perm"].mean()
    wide = wide.reset_index()
    df = df.merge(wide, on="target_address", how="left")
    m09 = df["snapshot_date"].astype(str) == "2022-09-01"
    for c in [c for c in wide.columns if c != "target_address"]:
        df.loc[~m09, c] = float("nan")
    got = df.loc[m09, "ig_occ_mean"].notna().sum()
    print(f"ig09 join: {got}/{int(m09.sum())}")
    return df

def add_rv(df):
    """RV per frozen go/nogo protocol; all parse succeeded so no operational fallback applies."""
    df["rv_mrr"] = df["full_rr"] - df["cheap_rr"]
    df["rv_nocf"] = df["nocf_rr"] - df["cheap_rr"]
    # No calibrated per-candidate probabilities in the Qwen panel (ranks only) -> RV_LL NaN.
    df["rv_ll"] = float("nan")
    df["rv_ll_available"] = False
    df["z0"] = (df["rv_mrr"] > DELTA_Z0).astype(int)
    df["z1"] = (df["rv_mrr"] > DELTA_Z1).astype(int)
    denom = df["total_tokens"] + LAMBDA_COST * df["latency_s"]
    df["rv_cost_lambda1"] = df["rv_mrr"] / denom
    df["rv_cost_tokens_only"] = df["rv_mrr"] / df["total_tokens"]
    return df

def add_core_fields(df):
    df["cheap_correct"] = (df["cheap_rank"] == 1).astype(int)
    df["fullcf_correct"] = (df["full_rank"] == 1).astype(int)  # frozen R1 metric
    # Full-CF's predicted address/score were not persisted (only its rank) -> NaN placeholders
    df["fullcf_prediction"] = float("nan")
    df["fullcf_score"] = float("nan")
    df["full_pick_matches_truth_proxy"] = (df["full_rr"] == df["cheap_rr"]).astype(int)
    df["reasoning_gain"] = df["rv_mrr"]
    df["reasoning_gain_type"] = df["stratum"]
    df["event_family"] = df["cp_type"]
    df["interaction_type"] = df["cp_type"]
    df["counterparty_novelty"] = (df["cp_type"] == "new").astype(int)
    # literal Sec.5 names (aliases to computed columns)
    df["cheap_score"] = df["cheap_top_score_panel"]
    df["counterparty_recency"] = df["counterparty_days_since"]
    df["fullcf_rank"] = df["full_rank"]
    df["wallet_activity"] = df["evt_cnt_90d"]
    df["wallet_volume"] = df["pop_weight"]
    df["degree_asof"] = df["asof_mm_undir_degree"]
    df["weighted_degree_asof"] = df["asof_mm_w_in_degree"].fillna(0) + df["asof_mm_w_out_degree"].fillna(0)
    df["weighted_degree_asof"] = df["weighted_degree_asof"].where(
        df["asof_mm_w_in_degree"].notna() | df["asof_mm_w_out_degree"].notna())
    df["pagerank_asof"] = df["asof_mm_pagerank"]
    df["kcore_asof"] = df["asof_mm_kcore"]
    # simple as-of constructed proxies (documented; no future info)
    df["behavioral_state"] = pd.qcut(df["evt_cnt_90d"].rank(method="first"), 3,
                                     labels=["low","mid","high"]).astype(str)
    med = df.groupby("snapshot_date")["cp_entropy_90d"].transform("median")
    df["behavioral_surprise"] = (df["cp_entropy_90d"] - med).abs()
    df["regime_change_score"] = float("nan")  # needs trajectory data (Group E/F, not built yet)
    df["future_spillover_new_cp_30d"] = df["fwd30_new_cp"]
    df["future_spillover_evt_cnt_30d"] = df["fwd30_evt_cnt"]
    df["future_spillover_cp_distinct_30d"] = df["fwd30_cp_distinct"]
    df["future_spillover_horizon_days"] = 30
    df["reasoning_tokens"] = df["total_tokens"]
    df["reasoning_latency"] = df["latency_s"]
    df["parse_success"] = df["full_parse_ok"]
    df["fallback_used"] = df["audit_full_internal_fallback"].fillna(0).astype(int)
    # community as JSON string
    comm_json = []
    for _, r in df.iterrows():
        if pd.isna(r.get("community_id")):
            comm_json.append("")
        else:
            comm_json.append(json.dumps({c: (None if pd.isna(r[c]) else r[c])
                                         for c in COMM_JSON_COLS}))
    df["community_features_asof"] = comm_json
    return df

def join_dynamic_influence(df):
    """Attach wallet-level dynamic influence at the event cutoff. These columns are
    derived from fwd30 future outcomes -> supervision-only, NOT pre-reasoning as-of
    features (flagged by dyn_influence_uses_future)."""
    di_path = ROOT / "research" / "phase2" / "dynamic_influence_dataset.parquet"
    if not di_path.exists():
        print("dynamic_influence_dataset.parquet missing -> dyn_influence NaN")
        df["dyn_influence_uses_future"] = True
        return df
    di = pd.read_parquet(di_path, columns=["snapshot_date","target_address",
        "I_new_hist","I_new_log","I_evt_hist","I_mean",
        "resid_I_new_hist","resid_I_new_log","resid_I_evt_hist"])
    di["snapshot_date"] = pd.to_datetime(di["snapshot_date"]).dt.date
    di = di.rename(columns={"I_new_hist":"dyn_influence_new_cp_histgbm",
                            "I_new_log":"dyn_influence_new_cp_logistic",
                            "I_evt_hist":"dyn_influence_evt_histgbm",
                            "I_mean":"dyn_influence_mean",
                            "resid_I_new_hist":"dyn_resid_new_histgbm",
                            "resid_I_new_log":"dyn_resid_new_logistic",
                            "resid_I_evt_hist":"dyn_resid_evt_histgbm"})
    drop = [c for c in ["dyn_influence_new_cp_histgbm","dyn_influence_new_cp_logistic",
                        "dyn_influence_evt_histgbm","dyn_influence_mean",
                        "dyn_resid_new_histgbm","dyn_resid_new_logistic",
                        "dyn_resid_evt_histgbm"] if c in df.columns]
    df = df.drop(columns=drop)
    before = len(df)
    df = df.merge(di, on=["snapshot_date","target_address"], how="left")
    df["dyn_influence_uses_future"] = True
    print(f"dynamic influence join: {df['dyn_influence_mean'].notna().sum()}/{before}")
    return df


def main():
    df = load_runs()
    df = load_router(df)
    df = load_panel_meta(df)
    df, asof = load_asof_wallet(df)
    df = load_community2(df)
    df = load_struct09(df)
    df = load_ig09(df)
    df = add_rv(df)
    df = add_core_fields(df)
    # dynamic influence join placeholder (filled by build_dynamic_influence_dataset.py
    # which patches this parquet's dynamic-influence columns when available)
    for c in ["dyn_influence_new_cp_histgbm","dyn_influence_new_cp_logistic",
              "dyn_influence_evt_histgbm","dyn_influence_mean",
              "dyn_resid_new_histgbm","dyn_resid_new_logistic","dyn_resid_evt_histgbm"]:
        if c not in df.columns:
            df[c] = float("nan")
    df = df.rename(columns={"cheap_top_score_panel":"cheap_pred_score"})
    df["split"] = df["snapshot_date"].map({
        pd.Timestamp("2022-06-01").date():"train_dev",
        pd.Timestamp("2022-07-01").date():"tune",
        pd.Timestamp("2022-08-01").date():"test_frozen",
        pd.Timestamp("2022-09-01").date():"holdout_sept"})
    df["model"] = "Qwen3.5-4B"
    df = df.drop(columns=[c for c in FUTURE_LABELS if c in df.columns])
    df = join_dynamic_influence(df)
    df = df.rename(columns={"gain_full":"legacy_gain_full_router",
                            "gain_nocf":"legacy_gain_nocf_router",
                            "full_wins":"legacy_full_wins_router"})
    df.to_parquet(OUT, index=False)
    print("wrote", OUT, df.shape)
    return df

if __name__ == "__main__":
    main()
