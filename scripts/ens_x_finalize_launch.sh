#!/usr/bin/env bash
set -u
cd /storage/gaoym/ex-graph-microtransaction-analysis || exit 2
base=artifacts/ens_x_crosswalk/overnight_ai_dataset_20260926
collector="$base/candidate_timeline_evidence/exit_code"
rm -f "$base/finalize_exit_code"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) waiting_for_collector pid=$$" > "$base/finalize_status.txt"
for ((i=0; i<720; i++)); do
  if test -f "$collector"; then
    break
  fi
  sleep 30
done
if ! test -f "$collector"; then
  printf '%s\n' 'timeout_waiting_for_collector' >> "$base/finalize_status.txt"
  printf '%s\n' 124 > "$base/finalize_exit_code"
  exit 124
fi
if test "$(cat "$collector")" != 0; then
  printf '%s\n' 'collector_failed; finalizer_not_run' >> "$base/finalize_status.txt"
  printf '%s\n' 125 > "$base/finalize_exit_code"
  exit 125
fi
.venv-cuda/bin/python -u scripts/ens_x_overnight_finalize.py >> "$base/finalize.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$base/finalize_exit_code"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) finalizer_finished exit_code=$rc" >> "$base/finalize_status.txt"
exit "$rc"
