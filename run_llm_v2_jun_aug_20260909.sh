#!/usr/bin/env bash
set -euo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
export PYTHONUNBUFFERED=1
mkdir -p logs artifacts/llm_panel_v2/runs
SCORED=artifacts/llm_panel_v2/panel_scored_v2.csv.gz
for spec in "2022-06-01 1000 jun" "2022-07-01 1000 jul" "2022-08-01 1000 aug"; do
  set -- $spec
  SNAP=$1; LIMIT=$2; TAG=$3
  OUT=artifacts/llm_panel_v2/runs/${TAG}_gonogo_glm53_v2.csv
  echo "=== v2 $SNAP start $(date -Is) ==="
  python3 src/agent/run_agent.py \
    --snapshot "$SNAP" --limit "$LIMIT" --workers 16 \
    --model Qwen3.5-4B --max-tokens 700 \
    --panel-file "$SCORED" --out "$OUT"
  python3 src/agent/evaluate_runs.py "$OUT" --by-stratum \
    > "artifacts/llm_panel_v2/runs/${TAG}_gonogo_eval_v2.jsonl"
  echo "=== v2 $SNAP done $(date -Is) ==="
done
