#!/usr/bin/env bash
# Group B — Predictive-Influence-First: full pipeline (CPU only, no LLM).
# 1) bounded BQ label pull (≈10MB) -> 2) frozen temporal OOS experiment
# -> 3) exploratory 09-01 extended ablation -> 4) persistence/regime/community
# -> 5) descriptive figure
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="$ROOT/.venv-cuda/bin/python"
cd "$ROOT"
"$PY" research/groupB_predictive/fetch_labels.py
"$PY" research/groupB_predictive/run_predictive.py
"$PY" research/groupB_predictive/run_extended09.py
"$PY" research/groupB_predictive/persistence_analysis.py
"$PY" research/groupB_predictive/make_figure.py
echo "Group B pipeline done."
