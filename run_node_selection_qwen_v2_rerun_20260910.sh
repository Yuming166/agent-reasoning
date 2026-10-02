#!/usr/bin/env bash
# Complete the same-model Qwen v2 panel needed for a clean temporal selector
# protocol.  This script uses only the project-authorized endpoint and never
# stores raw model responses.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
export LLM_BASE_URL="${LLM_BASE_URL:-http://10.63.0.82:31518/v1}"
export LLM_REASONING_EFFORT=""
MODEL_NAME="${LOCAL_VLLM_SERVING_NAME:-Qwen3.5-4B}"
WORKERS="${LLM_WORKERS:-16}"
PANEL="artifacts/llm_panel_v2/panel_scored_v2.csv.gz"

case "${LLM_BASE_URL%/}" in
  http://10.63.0.82:31518/v1|http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*|https://127.0.0.1:*|https://localhost:*|https://\[::1\]:*) ;;
  *) echo "refusing unauthorized LLM_BASE_URL" >&2; exit 2 ;;
esac

python3 - "$LLM_BASE_URL" "$MODEL_NAME" <<'PY'
import json, sys, urllib.request
base, want = sys.argv[1].rstrip('/'), sys.argv[2]
with urllib.request.urlopen(base + '/models', timeout=10) as r:
    obj = json.load(r)
ids = []
for item in obj.get('data', []) if isinstance(obj.get('data'), list) else []:
    if isinstance(item, dict) and item.get('id') is not None:
        ids.append(str(item['id']))
if isinstance(obj.get('model_ids'), list):
    ids.extend(str(x) for x in obj['model_ids'])
if want not in ids:
    raise SystemExit('authorized endpoint model mismatch: ' + repr(sorted(set(ids))))
print('authorized_model_ready', want)
PY

run_one() {
  local snap="$1" tag="$2"
  local out="artifacts/llm_panel_v2/runs/${tag}_gonogo_local_vllm4b_rerun_20260910.csv"
  local eval_out="artifacts/llm_panel_v2/runs/${tag}_gonogo_local_vllm4b_rerun_20260910_eval.jsonl"
  local manifest="artifacts/llm_panel_v2/runs/${tag}_gonogo_local_vllm4b_rerun_20260910_manifest.json"
  if [[ -e "$out" || -e "$eval_out" || -e "$manifest" ]]; then
    echo "refusing to overwrite existing output for $snap" >&2
    exit 2
  fi
  echo "=== Qwen v2 $snap start $(date -Is) ==="
  python3 src/agent/run_agent.py \
    --snapshot "$snap" --limit 1000 --workers "$WORKERS" \
    --model "$MODEL_NAME" --max-tokens 700 \
    --panel-file "$PANEL" --audit-details --out "$out"
  python3 src/agent/evaluate_runs.py "$out" --by-stratum > "$eval_out"
  python3 - "$out" "$eval_out" "$manifest" "$snap" "$MODEL_NAME" "$LLM_BASE_URL" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, ev, mf, snap, model, base = map(Path, sys.argv[1:])
def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()
base_s = str(base)
manifest = {
  'run_type': 'v2_same_model_local_vllm_rerun',
  'snapshot': str(snap), 'model_name': str(model),
  'endpoint_scope': 'authorized_shared_qwen' if base_s.rstrip('/') == 'http://10.63.0.82:31518/v1' else 'loopback_vllm',
  'base_url_is_authorized': base_s.rstrip('/') == 'http://10.63.0.82:31518/v1' or base_s.startswith(('http://127.0.0.1:', 'http://localhost:', 'http://[::1]:', 'https://127.0.0.1:', 'https://localhost:', 'https://[::1]:')),
  'protocol': {'limit': 1000, 'max_tokens': 700, 'temperature': 0.0, 'audit_details': True, 'panel': 'artifacts/llm_panel_v2/panel_scored_v2.csv.gz', 'reasoning_effort': 'omitted'},
  'output': {'path': str(out), 'sha256': digest(out), 'size_bytes': out.stat().st_size},
  'evaluation': {'path': str(ev), 'sha256': digest(ev), 'size_bytes': ev.stat().st_size},
  'raw_responses_persisted': False,
}
mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print('wrote', mf)
PY
  echo "=== Qwen v2 $snap done $(date -Is) ==="
}

run_one 2022-07-01 jul
run_one 2022-08-01 aug
echo "=== same-model Qwen v2 reruns complete $(date -Is) ==="
