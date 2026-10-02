#!/usr/bin/env bash
set -euo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
export PYTHONUNBUFFERED=1
mkdir -p logs artifacts/llm_panel_v1/runs
echo "=== July router/prompt-set run start $(date -Is) ==="
python3 src/agent/run_agent.py \
  --snapshot 2022-07-01 --limit 960 --workers 16 \
  --model Qwen3.5-4B --max-tokens 700 \
  --out artifacts/llm_panel_v1/runs/jul_gonogo_glm53_v1.csv
echo "=== August FROZEN go/no-go start $(date -Is) ==="
python3 src/agent/run_agent.py \
  --snapshot 2022-08-01 --limit 1000 --workers 16 \
  --model Qwen3.5-4B --max-tokens 700 \
  --out artifacts/llm_panel_v1/runs/aug_gonogo_glm53_v1.csv
echo "=== evaluation $(date -Is) ==="
python3 src/agent/evaluate_runs.py artifacts/llm_panel_v1/runs/jul_gonogo_glm53_v1.csv --by-stratum \
  > artifacts/llm_panel_v1/runs/jul_gonogo_eval.jsonl
python3 src/agent/evaluate_runs.py artifacts/llm_panel_v1/runs/aug_gonogo_glm53_v1.csv --by-stratum \
  > artifacts/llm_panel_v1/runs/aug_gonogo_eval.jsonl
echo "=== DONE $(date -Is) ==="
