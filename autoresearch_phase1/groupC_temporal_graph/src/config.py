"""Group C (Temporal-Graph-First) — paths, windows, and caps.

Frozen protocol: research/audit/temporal_protocol.yaml v1.0.
All features at cutoff t use ONLY information strictly before t.
"""
from pathlib import Path

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
RESEARCH = ROOT / "research" / "groupC_temporal_graph"
SRC = RESEARCH / "src"
RESULTS = RESEARCH / "results"
DATA = RESULTS / "data"

# Frozen split: final untouched holdout snapshot
CUTOFF = "2022-09-01"
LOOKBACK_DAYS = 90
LOOKBACK_START = "2022-06-03T00:00:00"     # snapshot - 90d, strictly before cutoff
LABEL_END = "2022-10-01"

# BigQuery
PROJECT = "ictdata-507912"
DATASET = "exgraph"
SEQUENCE_TABLE = f"`{PROJECT}.{DATASET}.target_event_sequences_20220301_20220901`"
ASOF_20220901_TABLE = f"`{PROJECT}.{DATASET}.wallet_asof_features_20220901`"
MAX_BYTES_BILLED = 3 * 1024**3  # 3 GiB hard cap per query (protocol requirement)

# External / prior artifacts (read-only)
STRUCTURAL_FEATURES_CSV = ROOT / "artifacts" / "exgraph_structural_features.csv"
P1_RANKING_CSV = ROOT / "artifacts" / "p1_wallet_icf_ranking.csv"          # Aug-panel proxy (post-hoc boundary)
P2_TRIGGER_CSV = ROOT / "artifacts" / "influence_v1" / "p2_trigger_proxy_v2.csv"

# Group A reusable outputs (read-only)
GROUP_A_FEATURE_MATRIX = ROOT / "research" / "groupA_behavior" / "results" / "data" / "feature_matrix_20220901.parquet"
GROUP_A_NETWORK_FEATURES = ROOT / "research" / "groupA_behavior" / "results" / "data" / "network_features_20220901.csv"

# Edge weight decay half-life for recency weighting (30 days)
RECENCY_TAU_DAYS = 30.0
MONTHS = ["2022-06", "2022-07", "2022-08"]
