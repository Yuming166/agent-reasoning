#!/usr/bin/env python3
import os
"""Write reasoning_gain_manifest.json + dynamic_influence_manifest.json."""
import json
from pathlib import Path
import pandas as pd, numpy as np

ROOT = Path(os.environ.get('EXGRAPH_PROJECT_ROOT', Path(__file__).resolve().parents[2]))
PH2 = ROOT / "research" / "phase2"

rg = pd.read_parquet(PH2 / "reasoning_gain_dataset.parquet")
di = pd.read_parquet(PH2 / "dynamic_influence_dataset.parquet")
rg["sd"] = rg["snapshot_date"].astype(str)
di["sd"] = di["snapshot_date"].astype(str)

def miss_rate(df, cols):
    return {c: round(float(df[c].isna().mean()), 4) for c in cols}

# ---------------- reasoning gain manifest ----------------
rg_cols = list(rg.columns)
fut_cols = [c for c in rg_cols if c.startswith(("future_spillover", "dyn_"))]
precall = ["pool_n","cheap_top_score","cheap_margin","cheap_score_entropy","frac_bridge",
 "frac_personal","frac_tail","frac_top2000","n_bridge","n_personal","top1_is_personal",
 "top1_is_bridge","pop_weight","log_evt_cnt","log_pool_n","log_n_bridge","log_n_personal",
 "cp_type_repeat"]
behav = ["evt_cnt_90d","evt_out_90d","evt_in_90d","evt_self_90d","evt_native_90d",
 "evt_token_90d","active_days_90d","tx_cnt_90d","active_span_days_90d","cp_distinct_90d",
 "cp_out_distinct_90d","cp_in_distinct_90d","cp_out_interact_90d","cp_in_interact_90d",
 "token_distinct_90d","cp_entropy_90d","cp_new_30d","cp_new_rate_30d","cp_both_dir_90d",
 "cp_reciprocity_90d","self_tx_rate_90d","token_event_rate_90d","token_hhi_90d",
 "events_per_active_day_90d"]
net = ["asof_mm_in_degree","asof_mm_out_degree","asof_mm_undir_degree","asof_mm_w_in_degree",
 "asof_mm_w_out_degree","asof_mm_pagerank","asof_mm_kcore","asof_mm_clustering",
 "asof_mm_hub_neighbors"]
struct09 = ["static_degree","static_w_degree","static_pagerank","deg_und","wdeg_und","pagerank",
 "kcore","betweenness","recency_wdeg","activity_trend","active_months","persistent_edges",
 "mutual_pairs","triangles","new_edges_recent","cross_comm_share","bridge_score","hub_score",
 "structure_novol_pct"]
comm = [c for c in rg_cols if c.startswith("comm_")]
ig = [c for c in rg_cols if c.startswith("ig_")]
legacy = ["legacy_gain_full_router","legacy_gain_nocf_router","legacy_full_wins_router"]
core = ["cheap_prediction","cheap_pred_score","cheap_rank","cheap_correct","fullcf_correct",
 "full_pick_matches_truth_proxy","full_rank","reasoning_gain","reasoning_gain_type",
 "future_target","event_family","interaction_type","wallet_activity","wallet_volume",
 "counterparty_recency","counterparty_novelty","degree_asof","weighted_degree_asof",
 "pagerank_asof","kcore_asof","behavioral_state","behavioral_surprise","regime_change_score",
 "community_features_asof","future_spillover_new_cp_30d","future_spillover_evt_cnt_30d",
 "future_spillover_cp_distinct_30d","future_spillover_horizon_days","reasoning_tokens",
 "reasoning_latency","parse_success","fallback_used"]
rv = ["rv_mrr","rv_nocf","rv_ll","rv_ll_available","z0","z1","rv_cost_lambda1","rv_cost_tokens_only"]
cost = ["total_tokens","nocf_total_tokens","latency_s","prompt_tokens","completion_tokens","llm_calls"]

by_month = rg.groupby("sd").agg(
    n=("rv_mrr","size"),
    rv_mean=("rv_mrr","mean"), rv_median=("rv_mrr","median"),
    z0_rate=("z0","mean"), z1_rate=("z1","mean")).round(4)
by_stratum = rg.groupby("stratum").agg(
    n=("rv_mrr","size"),
    rv_mean=("rv_mrr","mean"), rv_median=("rv_mrr","median"),
    z0_rate=("z0","mean"), z1_rate=("z1","mean")).round(4)

rg_manifest = {
 "artifact": "reasoning_gain_dataset.parquet",
 "version": "v1",
 "builder": "research/phase2/build_reasoning_gain_dataset.py",
 "build_date": "2026-09-12",
 "n_rows": int(len(rg)),
 "n_events": int(len(rg)),
 "months": sorted(rg["sd"].unique().tolist()),
 "split_protocol": {
   "2022-06-01": "train_dev", "2022-07-01": "tune",
   "2022-08-01": "test_frozen", "2022-09-01": "holdout_sept"},
 "join_keys": {
   "event": ["snapshot_date","target_address","target_sequence_index"],
   "wallet_asof": ["snapshot_date","target_address"],
   "community": ["snapshot_date","target_exgraph_node_id"],
   "structure09_ig09": "2022-09-01 only, key=target_address (masked to 09, no leakage)",
   "dynamic_influence": ["snapshot_date","target_address"]},
 "sources": [
   {"path": "artifacts/llm_panel_v2/runs/{jun,jul,aug}_gonogo_local_vllm4b_rerun_20260910.csv",
    "role": "authoritative LLM arms (cheap/full/nocf ranks, tokens, latency, parse, audit)", "coverage": "1000/1000 per month"},
   {"path": "artifacts/llm_panel_20220901/runs/sept_gonogo_local_vllm4b_rerun_20260910.csv",
    "role": "sept holdout LLM arms", "coverage": "1000/1000"},
   {"path": "artifacts/llm_panel_v2/router_dataset_v2.csv",
    "role": "pre-call features only (pool_n, cheap_top_score/margin/entropy, frac_*, n_bridge/personal, pop_weight, logs); gain labels there are LEGACY (pre-float-fix era) and not used as RV basis", "coverage": "3000/3000 jun-aug"},
   {"path": "artifacts/llm_panel_20220901/sept_router_scores.csv",
    "role": "pre-call features for sept (rr/token cols there are from an earlier eval; NOT used)", "coverage": "1000/1000"},
   {"path": "artifacts/llm_panel_v2/panel_scored_v2.csv.gz",
    "role": "candidate-level cheap scores: cheap top-1 prediction + truth counterparty metadata", "coverage": "4000/4000 events"},
   {"path": "research/groupA_behavior/results/data/asof_monthly_2022.parquet",
    "role": "as-of wallet behavior features, cutoffs 05-08", "coverage": "2939/3000 (97.97%)"},
   {"path": "research/groupA_behavior/results/data/feature_matrix_20220901.parquet",
    "role": "as-of wallet behavior+network features, cutoff 09", "coverage": "969/1000 (96.9%)"},
   {"path": "research/community_temporal/results/data/community_membership_202{06,07,08,09}01.csv",
    "role": "community membership/importance, matched per cutoff", "coverage": "2407/4000 (60.2%)"},
   {"path": "research/groupC_temporal_graph/results/data/wallet_importance_20220901.csv",
    "role": "structural features, 09-only", "coverage": "547/1000 sept (13.7% of all events)"},
   {"path": "research/groupD_infogain/results/wallet_ig_20220901.csv",
    "role": "wallet information gain, 09 subset only", "coverage": "175/1000 sept (4.4% of all events)"},
   {"path": "research/phase2/dynamic_influence_dataset.parquet",
    "role": "wallet dynamic influence at event cutoff (FUTURE-derived; supervision-only)", "coverage": "3908/4000 (97.7%)"}],
 "rv_definitions": {
   "rv_mrr": "full_rr - cheap_rr (frozen Phase-I go/nogo protocol). full_rr = 1/(cheap-order average-competition rank of the Full-CF predicted address); cheap_rr = 1/(cheap-order average-competition rank of the true counterparty); both in the shared frozen-cheap-rank candidate ordering",
   "rv_nocf": "nocf_rr - cheap_rr (ablation arm, same ordering)",
   "rv_ll": "NaN - no calibrated per-candidate probabilities in the Qwen panel (ranks only)",
   "rv_ll_available": False,
   "z0": "1[rv_mrr > 0.0] (pre-registered delta 0)",
   "z1": "1[rv_mrr > 0.1] (pre-registered delta +0.1)",
   "rv_cost_lambda1": "rv_mrr / (total_tokens + 1.0*latency_s)",
   "rv_cost_tokens_only": "rv_mrr / total_tokens",
   "cost_lambda": 1.0,
   "parse_success": "1000/1000 per month (full_parse_ok=1); internal fallback count = 0 -> operational gain equals raw rv_mrr here"},
 "reasoning_gain_type": "stratum (new_tail/new_popular/repeat_easy/repeat_hard)",
 "rv_summary_by_month": json.loads(by_month.to_json()),
 "rv_summary_by_stratum": json.loads(by_stratum.to_json()),
 "rv_summary_overall": {"n": int(len(rg)), "mean": round(float(rg["rv_mrr"].mean()),4),
    "median": round(float(rg["rv_mrr"].median()),4),
    "z0_rate": round(float(rg["z0"].mean()),4), "z1_rate": round(float(rg["z1"].mean()),4)},
 "column_coverage": {
   "core_llm_arms": miss_rate(rg, rv + cost),
   "precall_router": miss_rate(rg, precall),
   "behavior_asof": miss_rate(rg, behav),
   "network_asof_09only": miss_rate(rg, net),
   "structure_09only": miss_rate(rg, struct09),
   "community": miss_rate(rg, comm),
   "ig_09subset": miss_rate(rg, ig),
   "legacy_gain_router": miss_rate(rg, legacy),
   "future_derived": miss_rate(rg, fut_cols)},
 "missing_columns_report": {
   "rv_ll": "entirely NaN; no calibrated probabilities recorded in run CSVs (only ranks)",
   "regime_change_score": "entirely NaN; requires multi-period trajectory state (Group E/F feature not built yet)",
   "fullcf_prediction/fullcf_score": "not recorded in run CSVs; only the rank of the Full-CF predicted address was persisted. fullcf_correct is the frozen R1 metric (full_rank==1); full_pick_matches_truth_proxy=(full_rr==cheap_rr) is a necessary-condition proxy",
   "asof_mm_*/degree_asof/pagerank_asof/kcore_asof": "86.3% missing; network features exist only in feature_matrix_20220901 (09) and only for wallets in the monthly mm subgraph",
   "structure09/ig09": "09-only; NaN for all 05-08 cutoffs (masked to prevent leakage)",
   "community": "39.8% missing; community membership available for 06-09 and covers ~60% of event wallets",
   "legacy_*_router": "jun-aug only (sept router file lacks gain columns)"},
 "leakage_declaration": {
   "as_of_features": "all feature columns are computed strictly at/before the event cutoff; fwd30 future labels are isolated in future_spillover_* columns",
   "future_derived_columns": fut_cols,
   "dyn_influence_note": "dyn_influence_*/dyn_resid_* are derived from fwd30 outcomes -> may be used ONLY as selector supervision on train/tune cutoffs, never as test-time features",
   "structure_ig_mask": "structure09/ig09 values masked to 09-01 events to avoid cross-cutoff leakage",
   "importance_proxy_p3": "excluded from features (used by Group A only)"},
 "caveats": [
   "legacy_gain_full/nocf/wins in router CSVs come from the pre-float-fix (buggy) run era and are retained only as diagnostic columns; they are NOT the RV basis",
   "cheap_prediction is the argmax cheap_score candidate in panel_scored_v2 with candidate_address tie-break, consistent with the frozen cheap_tie_ranks ordering",
   "RV is incremental predictive utility under the frozen shared cheap-order evaluation oracle, not a causal treatment effect",
   "mask_sensitive=True for all events; belief_shift='reinforce' except 1 sept event ('flip')"]
}
(PH2 / "reasoning_gain_manifest.json").write_text(json.dumps(rg_manifest, indent=2, ensure_ascii=False))
print("wrote reasoning_gain_manifest.json")

# ---------------- dynamic influence manifest ----------------
sub = di[di["sd"] > "2022-05-01"].copy()
sub["vol_hi"] = sub["evt_cnt_90d"] > sub["evt_cnt_90d"].median()
quad = {}
for ic in ["I_new_hist","resid_I_new_hist","I_new_log","resid_I_new_log","I_evt_hist","I_mean","resid_I_mean"]:
    hi = f"{ic}_hi"
    sub[hi] = sub[ic] > sub[ic].median()
    tab = pd.crosstab(sub[hi], sub["vol_hi"]).rename(index={False:"infl_low", True:"infl_high"},
                                                     columns={False:"vol_low", True:"vol_high"})
    quad[ic] = {
        "vol_low_infl_low": int(tab.loc["infl_low","vol_low"]),
        "vol_low_infl_high": int(tab.loc["infl_high","vol_low"]),
        "vol_high_infl_low": int(tab.loc["infl_low","vol_high"]),
        "vol_high_infl_high": int(tab.loc["infl_high","vol_high"]),
        "low_vol_high_infl_share": round(float(tab.loc["infl_high","vol_low"]/len(sub)),4),
        "median": round(float(sub[ic].median()),6)}

di_manifest = {
 "artifact": "dynamic_influence_dataset.parquet",
 "version": "v1",
 "builder": "research/phase2/build_dynamic_influence_dataset.py",
 "build_date": "2026-09-12",
 "n_rows": int(len(di)),
 "unit": "wallet x cutoff",
 "cutoffs": sorted(di["sd"].unique().tolist()),
 "outcomes": {
   "y_new_cp": "fwd30_new_cp > 0 (new counterparty in next 30d; binary)",
   "y_evt": "fwd30_evt_cnt (future event count in next 30d; regression)"},
 "horizon_days": 30,
 "utility_definitions": {
   "binary": "U = -logloss(y,p); I_i = baseline_logloss(t) - conditional_logloss_i",
   "regression": "U = -squared error; I_i = baseline_MSE(t) - (y_i - yhat_i)^2"},
 "models": {
   "I_new_hist": "HistGradientBoostingClassifier(max_iter=300, lr=0.1, min_samples_leaf=20, l2=1.0, seed=42)",
   "I_new_log": "Pipeline(median imputer + StandardScaler + LogisticRegression(C=1.0, max_iter=2000, seed=42))",
   "I_evt_hist": "HistGradientBoostingRegressor(max_iter=300, lr=0.1, min_samples_leaf=20, l2=1.0, seed=42)"},
 "protocol": "rolling origin: for cutoff t, models trained ONLY on cutoffs < t; features are as-of at each row's own cutoff",
 "per_cutoff": json.loads(di.groupby("sd").agg(
     n=("y_new_cp","size"),
     new_cp_rate=("y_new_cp","mean"),
     I_mean=("I_new_hist","mean")).round(4).to_json()),
 "base_rates_note": "baseline utility U(Y|C_t) = empirical marginal at cutoff t (logloss of predicting the cutoff rate; MSE of predicting the cutoff mean)",
 "volume_adjustment": {
   "method": "resid = I - E[I | log1p(evt_cnt_90d)] via pooled OLS over cutoffs 06-09",
   "r2": {"I_new_hist": 0.0246, "I_new_log": 0.0178, "I_evt_hist": 0.0082, "I_mean": 0.0082},
   "note": "volume explains <3% of influence variance"},
 "four_quadrants_06_09": quad,
 "coverage": {
   "05-01": "influence NaN (no prior cutoff for rolling-origin training)",
   "06-09": f"{int(sub['I_new_hist'].notna().sum())} rows with influence"},
 "leakage_declaration": {
   "features": "strictly as-of at each row's cutoff",
   "labels": "fwd30 outcomes (future by construction); used to measure predictive utility, not as model input",
   "models": "trained only on cutoffs < t (no same-cutoff or future training)"},
 "caveats": [
   "I_evt_hist is in squared-error units and is scale-dominated by high-activity wallets (mean ~8.7k, std ~92k); prefer I_new_* (logloss, bounded) for reasoning-worthiness work",
   "asof_mm_* network features exist only for 09 (feature_matrix) and are NaN for 05-08; HistGBM trains on available columns per fold",
   "dynamic influence is NOT causal; it is future predictive spillover (plan Sec.8)",
   "I_new_hist max ~0.68 equals the max binary entropy at these base rates, so influence is upper-bounded by base-rate uncertainty"]
}
(PH2 / "dynamic_influence_manifest.json").write_text(json.dumps(di_manifest, indent=2, ensure_ascii=False))
print("wrote dynamic_influence_manifest.json")
