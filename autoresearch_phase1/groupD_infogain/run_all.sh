#!/usr/bin/env bash
# Group D — Information-Gain / Counterfactual-First: full reproducible run.
# CPU-only, sklearn; cutoff 2022-09-01; bounded subset (default 3,000 wallets).
set -euo pipefail
cd "$(dirname "$0")"
PY=/storage/gaoym/ex-graph-microtransaction-analysis/.venv-cuda/bin/python
LOG=logs/run_$(date +%Y%m%d_%H%M%S).log
{
  echo "=== Group D run @ $(date -Is) ==="
  echo "--- 0. build dataset (from Group A as-of assets) ---"
  $PY src/build_dataset.py
  echo "--- 1. wallet masking (per-wallet predictive IG, 5-fold CV occlusion) ---"
  $PY src/run_wallet_masking.py
  echo "--- 2. feature/trajectory masking ---"
  $PY src/run_feature_masking.py
  echo "--- 3. community (persona) masking ---"
  $PY src/run_community_masking.py
  echo "--- 4. influence residual analysis (Section 10) ---"
  $PY src/run_residual.py
  echo "--- 5. ranking comparison ---"
  $PY src/run_ranking_compare.py
  echo "--- 6. summary digest ---"
  $PY src/summarize.py
  echo "=== Group D run finished @ $(date -Is) ==="
} 2>&1 | tee "$LOG"
echo "[run_all] log -> $LOG"
