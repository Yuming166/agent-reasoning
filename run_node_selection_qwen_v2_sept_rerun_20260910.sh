#!/usr/bin/env bash
# Same-model September extra time-out for node-selection validation.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
export LLM_BASE_URL="${LLM_BASE_URL:-http://10.63.0.82:31518/v1}"
export LLM_REASONING_EFFORT=""
MODEL_NAME="${LOCAL_VLLM_SERVING_NAME:-Qwen3.5-4B}"
WORKERS="${LLM_WORKERS:-16}"
PANEL="artifacts/llm_panel_v2/panel_scored_v2.csv.gz"
OUT="artifacts/llm_panel_20220901/runs/sept_gonogo_local_vllm4b_rerun_20260910.csv"
EVAL_OUT="artifacts/llm_panel_20220901/runs/sept_gonogo_local_vllm4b_rerun_20260910_eval.jsonl"
MANIFEST="artifacts/llm_panel_20220901/runs/sept_gonogo_local_vllm4b_rerun_20260910_manifest.json"
case "${LLM_BASE_URL%/}" in
  http://10.63.0.82:31518/v1|http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*|https://127.0.0.1:*|https://localhost:*|https://\[::1\]:*) ;;
  *) echo "refusing unauthorized LLM_BASE_URL" >&2; exit 2 ;;
esac
python3 - "$LLM_BASE_URL" "$MODEL_NAME" <<'PY'
import json, sys, urllib.request
base, want = sys.argv[1].rstrip('/'), sys.argv[2]
with urllib.request.urlopen(base + '/models', timeout=10) as r:
    obj = json.load(r)
ids = [str(x.get('id')) for x in obj.get('data', []) if isinstance(x, dict) and x.get('id') is not None] if isinstance(obj.get('data'), list) else []
if isinstance(obj.get('model_ids'), list): ids.extend(str(x) for x in obj['model_ids'])
if want not in ids: raise SystemExit('authorized endpoint model mismatch: ' + repr(sorted(set(ids))))
print('authorized_model_ready', want)
PY
if [[ -e "$OUT" || -e "$EVAL_OUT" || -e "$MANIFEST" ]]; then
  echo "refusing to overwrite existing September output" >&2; exit 2
fi
mkdir -p "$(dirname "$OUT")"
echo "=== Qwen v2 2022-09-01 start $(date -Is) ==="
python3 src/agent/run_agent.py \
  --snapshot 2022-09-01 --limit 1000 --workers "$WORKERS" \
  --model "$MODEL_NAME" --max-tokens 700 \
  --panel-file "$PANEL" --audit-details --out "$OUT"
python3 src/agent/evaluate_runs.py "$OUT" --by-stratum > "$EVAL_OUT"
python3 - "$OUT" "$EVAL_OUT" "$MANIFEST" "$MODEL_NAME" "$LLM_BASE_URL" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, ev, mf, model, base = map(Path, sys.argv[1:])
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024), b''): h.update(chunk)
 return h.hexdigest()
base_s=str(base)
obj={'run_type':'v2_same_model_local_vllm_rerun','snapshot':'2022-09-01','model_name':str(model),
 'endpoint_scope':'authorized_shared_qwen' if base_s.rstrip('/')=='http://10.63.0.82:31518/v1' else 'loopback_vllm',
 'base_url_is_authorized':base_s.rstrip('/')=='http://10.63.0.82:31518/v1' or base_s.startswith(('http://127.0.0.1:','http://localhost:','http://[::1]:','https://127.0.0.1:','https://localhost:','https://[::1]:')),
 'protocol':{'limit':1000,'max_tokens':700,'temperature':0.0,'audit_details':True,'panel':'artifacts/llm_panel_v2/panel_scored_v2.csv.gz','reasoning_effort':'omitted'},
 'output':{'path':str(out),'sha256':digest(out),'size_bytes':out.stat().st_size},'evaluation':{'path':str(ev),'sha256':digest(ev),'size_bytes':ev.stat().st_size},'raw_responses_persisted':False}
mf.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
print('wrote',mf)
PY
echo "=== Qwen v2 2022-09-01 done $(date -Is) ==="
