#!/usr/bin/env bash
set -euo pipefail
ROOT=/storage/gaoym/ex-graph-microtransaction-analysis
PYTHON="$ROOT/.venv-cuda/bin/python"
export ASTRA_ONLY=1
export ASTRA_ALLOW_FALLBACK=0
export CODEX_LLM_DISABLED=1
export LUNAMAX_DISABLED=1
unset OPENAI_API_KEY OPENAI_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_BASE_URL CODEX_MODEL CODEX_PROVIDER LLM_BASE_URL LLM_MODEL || true
exec "$PYTHON" "$ROOT/research_os/runtime/resume_cycle_hard_deadline.py"
