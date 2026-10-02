#!/usr/bin/env bash
set -euo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
export http_proxy=http://10.63.0.72:7890
export https_proxy=http://10.63.0.72:7890
export HTTP_PROXY=http://10.63.0.72:7890
export HTTPS_PROXY=http://10.63.0.72:7890
export PYTHONUNBUFFERED=1
PY=/storage/gaoym/miniforge3/bin/python3
WORKDIR=/storage/gaoym/ex-graph-microtransaction-analysis/artifacts/ranker_samples
mkdir -p "$WORKDIR" artifacts/pipeline artifacts/nc_v1 logs

echo "[$(date -Is)] Stage B: export/download learned ranker samples and train candidate ranker"
$PY src/pipeline/train_candidate_ranker.py --workdir "$WORKDIR"

echo "[$(date -Is)] Stage C: train event-level gate and budget curve"
$PY src/pipeline/gate_and_budget.py --workdir "$WORKDIR"

echo "[$(date -Is)] DONE"
