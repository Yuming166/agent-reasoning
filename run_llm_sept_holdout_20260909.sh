#!/usr/bin/env bash
set -euo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
export PYTHONUNBUFFERED=1
mkdir -p logs artifacts/llm_panel_20220901/runs
OUT=artifacts/llm_panel_20220901/runs/sept_gonogo_glm53_v2.csv
echo "=== September FROZEN temporal holdout start $(date -Is) ==="
python3 src/agent/run_agent.py \
  --snapshot 2022-09-01 --limit 1000 --workers 16 \
  --model Qwen3.5-4B --max-tokens 700 \
  --panel-file artifacts/llm_panel_20220901/panel_scored_sept_frozen.csv.gz \
  --out "$OUT"
echo "=== September run DONE $(date -Is) ==="
python3 src/agent/evaluate_runs.py "$OUT" --by-stratum \
  > artifacts/llm_panel_20220901/runs/sept_gonogo_eval.jsonl
echo "=== September evaluation DONE $(date -Is) ==="
python3 src/agent/evaluate_frozen_router_holdout.py \
  --scored artifacts/llm_panel_20220901/panel_scored_sept_frozen.csv.gz \
  --runs "$OUT" \
  --router artifacts/llm_panel_v1/router_v1/budget_router_jun_frozen.pkl \
  --out-json artifacts/llm_panel_20220901/router_v1_sept_eval.json \
  --out-scores artifacts/llm_panel_20220901/sept_router_scores.csv \
  > artifacts/llm_panel_20220901/router_v1_sept_eval.log
echo "=== Router evaluation DONE $(date -Is) ==="
