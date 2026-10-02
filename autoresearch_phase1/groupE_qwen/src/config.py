"""Group E (Qwen Behavioral Representation) — frozen paths and constants.

All artifacts are anchored to the single frozen cutoff 2022-09-01
(Group 0 temporal_protocol.yaml v1.0). Features used to describe a wallet in
the Qwen prompt use ONLY information strictly before the cutoff (90-day
lookback [2022-06-03, 2022-09-01) plus as-of monthly snapshots May-Aug 2022).
Future labels (fwd30_*) are used ONLY in the downstream validation step and
are NEVER included in the prompt text nor in sample selection.

Claim boundary: everything in this group is a descriptive, small-sample pilot.
No causal / effectiveness / superiority claim is made.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen data contract (Group 0)
# ---------------------------------------------------------------------------
CUTOFF = "2022-09-01"
LOOKBACK_START = "2022-06-03T00:00:00"
LABEL_END = "2022-10-01"
PROTOCOL_REF = "research/audit/temporal_protocol.yaml (v1.0, frozen 2026-09-11)"
DATA_AUDIT_REF = "research/audit/DATA_AUDIT.md"

# ---------------------------------------------------------------------------
# Local reusable artifacts (read-only; produced by Group A / Group 0)
# ---------------------------------------------------------------------------
ROOT = Path("/storage/gaoym/ex-graph-microtransaction-analysis")
RESEARCH = ROOT / "research"
GROUP_A_RESULTS = RESEARCH / "groupA_behavior" / "results"
FEATURE_MATRIX = GROUP_A_RESULTS / "data" / "feature_matrix_20220901.parquet"
TRAJ_STATS = GROUP_A_RESULTS / "data" / "trajectory_stats_20220901.csv"
MONTHLY = GROUP_A_RESULTS / "data" / "asof_monthly_2022.parquet"
PERSONA = GROUP_A_RESULTS / "persona_assignments_20220901.csv"

# ---------------------------------------------------------------------------
# Group E paths
# ---------------------------------------------------------------------------
GROUP_E = RESEARCH / "groupE_qwen"
SRC = GROUP_E / "src"
RESULTS = GROUP_E / "results"

SAMPLE_CSV = RESULTS / "sample_wallets_20220901.csv"
PROFILES_JSONL = RESULTS / "profiles_20220901.jsonl"
SUMMARIES_JSONL = RESULTS / "qwen_summaries_20220901.jsonl"
EMBEDDINGS_JSONL = RESULTS / "qwen_embeddings_20220901.jsonl"
EMBEDDINGS_NPY = RESULTS / "qwen_embeddings_20220901.npy"
EVAL_JSON = RESULTS / "evaluation_20220901.json"
STATS_JSON = RESULTS / "call_stats_20220901.json"

# ---------------------------------------------------------------------------
# LLM endpoints (authorized; verified reachable 2026-09-11)
# ---------------------------------------------------------------------------
CHAT_BASE = "http://127.0.0.1:31518/v1"
CHAT_MODEL = "Qwen3.5-4B"
EMBED_BASE = "http://127.0.0.1:31522/v1"
EMBED_MODEL = "Qwen3-Embedding-0.6B"
EMBED_DIM = 1024

# Frozen prompt / generation protocol
TEMPERATURE = 0.0
MAX_TOKENS = 700           # frozen 700-token cap (matches README convention)
SEND_REASONING_EFFORT = False   # AGENTS.md / README: omit for this Qwen/vLLM
MAX_RETRIES = 3
TIMEOUT_S = 300

# ---------------------------------------------------------------------------
# Sample design
# ---------------------------------------------------------------------------
SAMPLE_N = 200             # bounded representative subset target
SAMPLE_SEED = 2022
STRAT_FEATURES = ["evt_cnt_90d"]          # activity tier (as-of only)
STRAT_TRAJ_CLUSTER = "trajectory__kmeans"  # persona column (as-of only)

# ---------------------------------------------------------------------------
# Downstream validation
# ---------------------------------------------------------------------------
LABELS = ["fwd30_evt_cnt", "fwd30_cp_distinct", "fwd30_cp_out_distinct", "fwd30_new_cp"]
N_FOLDS = 5
RIDGE_ALPHA = 1.0
PCA_DIM = 64
VAL_SEED = 2022
