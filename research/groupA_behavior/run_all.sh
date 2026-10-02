#!/usr/bin/env bash
# Group A behavior-first pipeline: S_i(t) -> Z_i(t) -> P_i(t) + evaluation.
# CPU only; BigQuery queries are bounded (partition-filtered, bytes-billed cap).
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv-cuda/bin/python
echo "== [1/5] build as-of feature matrix (BigQuery bounded pulls) =="
$PY research/groupA_behavior/src/build_features.py
echo "== [2/5] pull monthly as-of snapshots (temporal persistence) =="
$PY research/groupA_behavior/src/pull_monthly.py
echo "== [3/5] cluster personas (K-means/GMM/HDBSCAN) =="
$PY research/groupA_behavior/src/cluster_personas.py
echo "== [4/5] evaluate stability/bootstrap/persistence/downstream utility =="
$PY research/groupA_behavior/src/evaluate_personas.py
echo "== [5/5] sequence-embedding pilot (800 wallets) =="
$PY research/groupA_behavior/src/embed_sequence_pilot.py
echo "== done =="
