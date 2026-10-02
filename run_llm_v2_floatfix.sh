#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
mkdir -p logs artifacts/llm_panel_v2/runs artifacts/llm_panel_20220901/runs
run_month() {
  SNAP=$1; TAG=$2; PANEL=$3; OUT=$4
  echo "=== floatfix $SNAP start $(date -Is) ==="
  python3 src/agent/run_agent.py \
    --snapshot "$SNAP" --limit 1000 --workers 16 \
    --model glm-5.3 --max-tokens 700 \
    --panel-file "$PANEL" --out "$OUT"
  python3 - <<PY
import pandas as pd
p="$OUT"; d=pd.read_csv(p)
assert len(d)==1000, len(d)
assert d[['cheap_rr','full_rr','nocf_rr']].dtypes.astype(str).tolist() == ['float64','float64','float64'], d.dtypes
assert not d.full_rr.astype(str).isin(['True','False']).any()
print('validated', p, len(d), 'parse=', round(d.full_parse_ok.mean(),3), round(d.nocf_parse_ok.mean(),3))
PY
  python3 src/agent/evaluate_runs.py "$OUT" --by-stratum \
    > "$(dirname "$OUT")/${TAG}_gonogo_eval_floatfix.jsonl"
  echo "=== floatfix $SNAP done $(date -Is) ==="
}
run_month 2022-06-01 jun \
  artifacts/llm_panel_v2/panel_scored_v2.csv.gz \
  artifacts/llm_panel_v2/runs/jun_gonogo_glm53_v2_floatfix.csv
run_month 2022-07-01 jul \
  artifacts/llm_panel_v2/panel_scored_v2.csv.gz \
  artifacts/llm_panel_v2/runs/jul_gonogo_glm53_v2_floatfix.csv
run_month 2022-08-01 aug \
  artifacts/llm_panel_v2/panel_scored_v2.csv.gz \
  artifacts/llm_panel_v2/runs/aug_gonogo_glm53_v2_floatfix.csv
run_month 2022-09-01 sept \
  artifacts/llm_panel_20220901/panel_scored_sept_v2_frozen.csv.gz \
  artifacts/llm_panel_20220901/runs/sept_gonogo_glm53_v2_floatfix.csv
echo "=== all floatfix months done $(date -Is) ==="
