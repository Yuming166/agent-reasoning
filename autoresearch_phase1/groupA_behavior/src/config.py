"""Group A (Behavior-First) — path/config constants.

All feature construction is anchored to a single fixed cutoff so that no
future information leaks into S_i(t) -> Z_i(t) -> P_i(t). The as-of lookback
window and the future label window are defined once here.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Primary cutoff. 2022-09-01 matches the pre-built as-of table
# `wallet_asof_features_20220901` (18,519 wallets). All features use
# [LOOKBACK_START, CUTOFF) strictly; labels use [CUTOFF, LABEL_END).
# ---------------------------------------------------------------------------
CUTOFF = "2022-09-01"
LOOKBACK_DAYS = 90
LABEL_DAYS = 30
# exact window used by the pre-built as-of table (snapshot - 90 days)
LOOKBACK_START = "2022-06-03T00:00:00"   # TIMESTAMP(DATETIME_SUB(2022-09-01, INTERVAL 90 DAY))
LABEL_END = "2022-10-01"

# Monthly snapshots for temporal-persistence analysis (from wallet_asof_features_v1)
MONTHLY_SNAPSHOTS = ["2022-05-01", "2022-06-01", "2022-07-01", "2022-08-01"]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
RESEARCH = ROOT / "research" / "groupA_behavior"
SRC = RESEARCH / "src"
RESULTS = RESEARCH / "results"
SQL = RESEARCH / "sql"

# Local artifacts used (existing project artifacts, read-only)
ARTIFACTS = ROOT / "artifacts"
STRUCTURAL_FEATURES_CSV = ARTIFACTS / "exgraph_structural_features.csv"
USD_OUTFLOW_CSV = ARTIFACTS / "prices_v1" / "wallet_usd_outflow_v1.csv"
IMPORTANCE_RANKING_CSV = ARTIFACTS / "wallet_importance_ranking_v1.csv"

# BigQuery
PROJECT = "ictdata-507912"
DATASET = "exgraph"
SEQUENCE_TABLE = f"`{PROJECT}.{DATASET}.target_event_sequences_20220301_20220901`"
ASOF_20220901_TABLE = f"`{PROJECT}.{DATASET}.wallet_asof_features_20220901`"
ASOF_MONTHLY_TABLE = f"`{PROJECT}.{DATASET}.wallet_asof_features_v1`"
MAX_BYTES_BILLED = 3 * 1024**3  # 3 GiB hard cap per query; bounded by design

# ---------------------------------------------------------------------------
# Sample scope for the preliminary run
# ---------------------------------------------------------------------------
# The primary bounded sample is the full as-of table at the cutoff
# (18,519 wallets, 1 partition). This is a compact aggregated table, not a
# full event export. Sequence-level pilots use a smaller subsample.
EMBED_PILOT_N = 800     # wallets sampled for the sequence-embedding pilot
EMBED_SEED = 2022
