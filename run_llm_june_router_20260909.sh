#!/usr/bin/env bash
set -euo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
export PYTHONUNBUFFERED=1
mkdir -p logs artifacts/llm_panel_v1/runs
echo "=== June router-training run start $(date -Is) ==="
python3 src/agent/run_agent.py \
  --snapshot 2022-06-01 --limit 1000 --workers 16 \
  --model Qwen3.5-4B --max-tokens 700 \
  --out artifacts/llm_panel_v1/runs/jun_gonogo_glm53_v1.csv
echo "=== June DONE $(date -Is) ==="
