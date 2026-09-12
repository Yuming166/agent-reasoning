#!/usr/bin/env bash
# COMM group - reproducible pipeline (CPU only, no GPU, no LLM, no new packages).
# 1) bounded BigQuery pull (partition-filtered, maximum_bytes_billed=2GiB)
# 2) build per-cutoff as-of graphs + fixed communities + roles
# 3) formal community evolution (Hungarian matching, importance, regime, figures)
# 4) Group C exact reproduction + protocol decomposition
# 5) emit per-snapshot community_evolution_*.json
set -euo pipefail
cd "$(dirname "$0")/../.."
source .venv-cuda/bin/activate
python -u research/community_temporal/src/pull_edges.py
python -u research/community_temporal/src/build_graphs.py
python -u research/community_temporal/src/community_evolution.py
python -u research/community_temporal/src/groupC_comparison.py
python -u research/community_temporal/src/emit_per_snapshot.py
echo "[COMM] pipeline complete"
