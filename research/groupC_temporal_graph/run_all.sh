#!/usr/bin/env bash
# Group C — Temporal-Graph-First reproduction: cutoff 2022-09-01 first evidence.
# CPU only (networkx); one bounded BigQuery pull (partition-filtered, 3 GiB cap).
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv-cuda/bin/python
echo "== [1/2] build as-of temporal-graph structural features =="
$PY research/groupC_temporal_graph/src/build_temporal_features.py
echo "== [2/2] evaluate structural importance (descriptive) =="
$PY research/groupC_temporal_graph/src/evaluate_importance.py
echo "== done; see research/groupC_temporal_graph/README.md =="
