"""COMM group - paths, cutoffs, windows, caps.

Frozen protocol: research/audit/temporal_protocol.yaml v1.0.
Every as-of graph at cutoff t uses lookback [t-90d, t) strictly before t.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
HERE = ROOT / "research" / "community_temporal"
DATA = HERE / "results" / "data"
JSON = HERE / "results" / "json"
FIG = HERE / "results" / "figures"

# Per-cutoff as-of windows [start, cutoff) = 90 days each (verified calendar math)
CUTOFFS = {
    "2022-06-01": "2022-03-03T00:00:00",
    "2022-07-01": "2022-04-02T00:00:00",
    "2022-08-01": "2022-05-03T00:00:00",
    "2022-09-01": "2022-06-03T00:00:00",
}
# Calendar-month slices (inside the 09-01 90d window) for Group C comparison
MONTHS = ["2022-06", "2022-07", "2022-08"]

# Community detection: fixed algorithm + parameters (documented in COMMUNITIES.md)
COMMUNITY_METHOD = "networkx.greedy_modularity_communities"   # Louvain-style
COMMUNITY_WEIGHT = "weight"
MIN_MATCH_JACCARD = 0.05      # mapped community pairs must overlap >= this on common nodes
MATCH_ALGORITHM = "hungarian_max_sum_jaccard"

# Group A / B / C / D reusable outputs (read-only)
GROUP_A_MONTHLY = ROOT / "research" / "groupA_behavior" / "results" / "data" / "asof_monthly_2022.parquet"
GROUP_C_IMPORTANCE = ROOT / "research" / "groupC_temporal_graph" / "results" / "data" / "wallet_importance_20220901.csv"
GROUP_C_EDGES = ROOT / "research" / "groupC_temporal_graph" / "results" / "data" / "edges_asof_20220901.csv"
GROUP_B_PREDS = ROOT / "research" / "groupB_predictive" / "results" / "holdout09_predictions.csv"
GROUP_D_IG = ROOT / "research" / "groupD_infogain" / "results" / "wallet_ig_20220901.csv"
