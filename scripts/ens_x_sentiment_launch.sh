#!/usr/bin/env bash
set -u
cd /storage/gaoym/ex-graph-microtransaction-analysis || exit 2
out=artifacts/ens_x_crosswalk/overnight_ai_dataset_20260926
rm -f "$out/sentiment_exit_code"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) started pid=$$" > "$out/sentiment_status.txt"
.venv-cuda/bin/python -u scripts/ens_x_overnight_sentiment.py >> "$out/sentiment.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$out/sentiment_exit_code"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) finished exit_code=$rc" >> "$out/sentiment_status.txt"
exit "$rc"
