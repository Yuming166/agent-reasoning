"""Group D (Information-Gain / Counterfactual-First) — shared config.

Anchored to the frozen temporal protocol (research/audit/temporal_protocol.yaml v1.0):
- single cutoff 2022-09-01 (dev snapshot), features strictly < cutoff, labels in
  [2022-09-01, 2022-10-01) fwd30 window.
- representative bounded subset (default 3,000 wallets) for the masking experiments;
  no all-27k sweep.
- CPU only, sklearn; no LLM; no large BigQuery pulls beyond the compact ICF v2 table.
"""
from pathlib import Path

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
GROUP = ROOT / "research" / "groupD_infogain"
SRC = GROUP / "src"
RESULTS = GROUP / "results"
LOGS = GROUP / "logs"

# Group A reusable data (read-only)
GA = ROOT / "research" / "groupA_behavior" / "results"
FEATURE_MATRIX = GA / "data" / "feature_matrix_20220901.parquet"
TRAJ_STATS = GA / "data" / "trajectory_stats_20220901.csv"
NET_FEATURES = GA / "data" / "network_features_20220901.csv"
USD_CAPITAL = GA / "data" / "usd_capital_20220901.csv"
STATIC_PRIOR = GA / "data" / "static_prior_20220901.csv"
PERSONA = GA / "persona_assignments_20220901.csv"

# Existing influence/ICF rankings for comparison (read-only)
ICF_V1 = ROOT / "artifacts" / "p1_wallet_icf_ranking.csv"
ICF_V2_LOCAL = ROOT / "artifacts" / "influence_v1" / "p1_icf_v2alpha_candidate_occlusion.csv"

# Protocol constants
CUTOFF = "2022-09-01"
LABEL_WINDOW = "[2022-09-01, 2022-10-01)"
LOOKBACK = "[2022-06-03, 2022-09-01)"

# Experiment scope
SUBSET_N = 3000          # representative bounded subset
SEED = 20220901          # reproducibility
CV_FOLDS = 5

# Targets (leak-free fwd30 labels; binary classification for NLL/AUC)
TARGETS = {
    # primary: future interaction breadth >= 10 distinct counterparties
    "y_cp_ge10": "fwd30_cp_distinct >= 10",
    # secondary: any future activity in the next 30 days
    "y_active30": "fwd30_evt_cnt > 0",
}
PRIMARY_TARGET = "y_cp_ge10"

ID_COLS = ["snapshot_date", "target_address", "target_exgraph_node_id", "target_is_x_matched"]
LABEL_COLS = ["fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_cp_out_distinct",
              "fwd30_new_cp", "importance_proxy_p3"]

# Feature blocks (by exact column names in feature_matrix_20220901.parquet)
VOLUME_BLOCK = ["evt_cnt_90d", "evt_out_90d", "evt_in_90d", "evt_self_90d",
                "evt_native_90d", "evt_token_90d", "active_days_90d", "tx_cnt_90d",
                "active_span_days_90d", "out_interact_90d", "in_interact_90d",
                "native_90d", "token_90d", "native_usd", "token_usd_priced",
                "token_rows", "token_rows_priced"]
DIVERSITY_BLOCK = ["cp_distinct_90d", "cp_out_distinct_90d", "cp_in_distinct_90d",
                   "cp_out_interact_90d", "cp_in_interact_90d", "token_distinct_90d",
                   "cp_entropy_90d", "cp_new_30d", "cp_new_rate_30d",
                   "cp_both_dir_90d", "cp_reciprocity_90d", "self_tx_rate_90d",
                   "token_event_rate_90d", "token_hhi_90d", "events_per_active_day_90d"]
TRAJ_BLOCK = ["n_events_90d_traj", "active_days_90d_traj", "active_span_days_traj",
              "first_event_offset_days", "last_event_recency_days", "mean_gap_days",
              "median_gap_days", "max_gap_days", "std_gap_days", "n_gaps_gt7d", "n_gaps"]
NETWORK_BLOCK = ["asof_mm_in_degree", "asof_mm_out_degree", "asof_mm_undir_degree",
                 "asof_mm_w_in_degree", "asof_mm_w_out_degree", "asof_mm_pagerank",
                 "asof_mm_kcore", "asof_mm_clustering", "asof_mm_hub_neighbors",
                 "in_mm_subgraph"]

FEATURE_BLOCKS = {
    "volume": VOLUME_BLOCK,
    "diversity": DIVERSITY_BLOCK,
    "trajectory": TRAJ_BLOCK,
    "network": NETWORK_BLOCK,
}

# Volume proxy for residual analysis: native_usd + token_usd_priced (as-of, leak-safe)
VOLUME_FEATURES = ["native_usd", "token_usd_priced"]

# Persona columns available for community masking
PERSONA_COLS = ["full_asof__kmeans", "full_asof__gmm", "full_asof__hdbscan",
                "trajectory__kmeans", "trajectory__gmm", "network__kmeans"]
DEFAULT_PERSONA_COL = "full_asof__kmeans"
