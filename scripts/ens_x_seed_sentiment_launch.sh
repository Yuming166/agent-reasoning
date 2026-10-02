#!/usr/bin/env bash
set +e
cd /storage/gaoym/ex-graph-microtransaction-analysis || exit 1
out=artifacts/ens_x_crosswalk/paper_dataset_tiered_20260926
printf 'started_utc=%s\n' "$(date -u +%FT%TZ)" > "$out/seed_sentiment_status.txt"
.venv-cuda/bin/python scripts/ens_x_seed_sentiment.py > "$out/seed_sentiment.log" 2>&1
code=$?
printf '%s\n' "$code" > "$out/seed_sentiment_exit_code"
printf 'finished_utc=%s\nexit_code=%s\n' "$(date -u +%FT%TZ)" "$code" >> "$out/seed_sentiment_status.txt"
exit "$code"
