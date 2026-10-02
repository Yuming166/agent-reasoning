#!/usr/bin/env bash
# Re-run only the quarantined June v2 panel against an explicitly local vLLM.
# This script never falls back to a remote endpoint and never overwrites output.
set -euo pipefail

cd "$(dirname "$0")"
ROOT=$PWD
export PYTHONUNBUFFERED=1

LOCAL_VLLM_MODEL=${LOCAL_VLLM_MODEL:-}
MODEL_NAME=${LOCAL_VLLM_SERVING_NAME:-Qwen3.5-4B}
VLLM_PORT=${VLLM_PORT:-18000}
VLLM_HOST=127.0.0.1
START_VLLM=${START_VLLM:-0}
OUT=${JUNE_RERUN_OUT:-artifacts/llm_panel_v2/runs/jun_gonogo_local_vllm4b_rerun_20260910.csv}
EVAL_OUT=${JUNE_RERUN_EVAL_OUT:-artifacts/llm_panel_v2/runs/jun_gonogo_local_vllm4b_rerun_20260910_eval.jsonl}
SERVER_LOG=${JUNE_RERUN_SERVER_LOG:-logs/vllm_june_rerun_20260910.log}

if [[ "$START_VLLM" == "1" ]]; then
  : "${LOCAL_VLLM_MODEL:?Set LOCAL_VLLM_MODEL to an authorized local model directory when START_VLLM=1}"
  case "$LOCAL_VLLM_MODEL" in
    /*) ;;
    *) echo "LOCAL_VLLM_MODEL must be an absolute local path" >&2; exit 2 ;;
  esac
  if [[ ! -d "$LOCAL_VLLM_MODEL" || ! -f "$LOCAL_VLLM_MODEL/config.json" ]]; then
    echo "local model directory/config.json not found: $LOCAL_VLLM_MODEL" >&2
    exit 2
  fi
  if ! find "$LOCAL_VLLM_MODEL" -maxdepth 1 -type f \( \
      -name 'model.safetensors' -o -name 'model-*.safetensors' -o \
      -name 'pytorch_model*.bin' -o -name 'pytorch_model*.safetensors' \
    \) -print -quit | grep -q .; then
    echo "no local model weight file found at top level: $LOCAL_VLLM_MODEL" >&2
    exit 2
  fi
elif [[ "$START_VLLM" != "0" ]]; then
  echo "START_VLLM must be 0 (attach) or 1 (start local vLLM)" >&2
  exit 2
fi
if [[ -e "$OUT" || -e "$EVAL_OUT" ]]; then
  echo "refusing to overwrite existing rerun artifact: $OUT or $EVAL_OUT" >&2
  exit 2
fi
mkdir -p "$(dirname "$OUT")" "$(dirname "$EVAL_OUT")" "$(dirname "$SERVER_LOG")"

VLLM_PID=""
cleanup() {
  if [[ -n "$VLLM_PID" ]] && kill -0 "$VLLM_PID" 2>/dev/null; then
    kill "$VLLM_PID" 2>/dev/null || true
    wait "$VLLM_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "$START_VLLM" == "1" ]]; then
  command -v vllm >/dev/null || { echo 'vllm CLI not found in current environment' >&2; exit 2; }
  # Optional flags are supplied explicitly by the operator, e.g.
  # VLLM_EXTRA_ARGS='--language-model-only --reasoning-parser qwen3 --trust-remote-code'.
  read -r -a EXTRA_ARGS <<< "${VLLM_EXTRA_ARGS:-}"
  echo "starting authorized local vLLM model=$MODEL_NAME host=$VLLM_HOST port=$VLLM_PORT"
  vllm serve "$LOCAL_VLLM_MODEL" \
    --host "$VLLM_HOST" --port "$VLLM_PORT" \
    --served-model-name "$MODEL_NAME" \
    --max-model-len "${VLLM_MAX_MODEL_LEN:-65536}" \
    --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.90}" \
    "${EXTRA_ARGS[@]}" >"$SERVER_LOG" 2>&1 &
  VLLM_PID=$!
  export LLM_BASE_URL="http://${VLLM_HOST}:${VLLM_PORT}/v1"
else
  : "${LLM_BASE_URL:?Set LLM_BASE_URL to the already-started authorized local vLLM /v1 endpoint, or use START_VLLM=1}"
  # Permit loopback vLLM endpoints and the one explicitly authorized shared
  # Qwen service. Do not silently accept arbitrary remote endpoints.
  case "${LLM_BASE_URL%/}" in
    http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*|https://127.0.0.1:*|https://localhost:*|https://\[::1\]:*|http://10.63.0.82:31518/v1)
      LLM_BASE_URL=${LLM_BASE_URL%/}
      export LLM_BASE_URL
      ;;
    *) echo "refusing unauthorized LLM_BASE_URL; use loopback vLLM or http://10.63.0.82:31518/v1" >&2; exit 2 ;;
  esac
fi

# Readiness check is restricted to the local endpoint selected above.
python - <<'PY'
import json, os, time, urllib.error, urllib.request
base = os.environ["LLM_BASE_URL"].rstrip("/")
want = os.environ.get("LOCAL_VLLM_SERVING_NAME", "Qwen3.5-4B")
last = None
for _ in range(120):
    try:
        with urllib.request.urlopen(base + "/models", timeout=2) as r:
            obj = json.load(r)
        ids = []
        if isinstance(obj.get("data"), list):
            ids.extend(str(x.get("id")) for x in obj["data"] if isinstance(x, dict) and x.get("id") is not None)
        # The authorized service currently exposes model_ids rather than the
        # usual OpenAI data[].id shape.
        if isinstance(obj.get("model_ids"), list):
            ids.extend(str(x) for x in obj["model_ids"])
        if want in ids:
            print("local_vllm_ready", sorted(set(ids)))
            break
        if ids:
            last = "model_mismatch:" + ",".join(sorted(set(ids)))
        else:
            last = "empty_model_list"
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        last = type(exc).__name__
    time.sleep(2)
else:
    raise SystemExit("local vLLM readiness check failed: " + str(last))
PY

export LLM_BEARER="${LLM_BEARER:-}"
# The authorized Qwen service exposes hidden reasoning when this field is set;
# under the frozen 700-token completion budget it can emit no JSON content.
# Omit the optional field for this corrected JSON-completion rerun.
export LLM_REASONING_EFFORT=""
echo "running June v2 rerun with audited per-step status; output=$OUT"
python3 src/agent/run_agent.py \
  --snapshot 2022-06-01 --limit 1000 --workers "${LLM_WORKERS:-16}" \
  --model "$MODEL_NAME" --max-tokens 700 \
  --panel-file artifacts/llm_panel_v2/panel_scored_v2.csv.gz \
  --audit-details --out "$OUT"
python3 src/agent/evaluate_runs.py "$OUT" --by-stratum > "$EVAL_OUT"

python3 - "$OUT" "$EVAL_OUT" "$LOCAL_VLLM_MODEL" "$MODEL_NAME" "$LLM_BASE_URL" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
out = Path(sys.argv[1])
ev = Path(sys.argv[2])
model_path = sys.argv[3] or None
model_name = sys.argv[4]
base = sys.argv[5]
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024), b''): h.update(chunk)
    return h.hexdigest()
manifest = {
    "run_type": "june_v2_local_vllm_rerun",
    "snapshot": "2022-06-01",
    "model_name": model_name,
    "model_path_configured": model_path,
    "endpoint_scope": "authorized_shared_qwen" if base.rstrip("/") == "http://10.63.0.82:31518/v1" else "loopback_vllm",
    "base_url_is_authorized": (
        base.rstrip("/") == "http://10.63.0.82:31518/v1"
        or base.startswith(("http://127.0.0.1:", "http://localhost:", "http://[::1]:", "https://127.0.0.1:", "https://localhost:", "https://[::1]:"))
    ),
    "protocol": {"limit": 1000, "max_tokens": 700, "temperature": 0.0, "audit_details": True, "panel": "artifacts/llm_panel_v2/panel_scored_v2.csv.gz", "reasoning_effort": "omitted"},
    "output": {"path": str(out), "sha256": digest(out), "size_bytes": out.stat().st_size},
    "evaluation": {"path": str(ev), "sha256": digest(ev), "size_bytes": ev.stat().st_size},
    "raw_responses_persisted": False,
}
path = out.with_name(out.stem + "_manifest.json")
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print("wrote", path)
PY
