#!/usr/bin/env bash
set -u
cd /storage/gaoym/ex-graph-microtransaction-analysis || exit 2
out=artifacts/ens_x_crosswalk/overnight_ai_dataset_20260926/candidate_timeline_evidence
mkdir -p "$out"
rm -f "$out/exit_code"
rm -f "${out%/candidate_timeline_evidence}/finalize_exit_code"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) started pid=$$" > "$out/launcher_status.txt"
.venv-cuda/bin/python -u scripts/ens_x_overnight_candidate_timelines.py >> "$out/collector.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$out/exit_code"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) collector_finished exit_code=$rc" >> "$out/launcher_status.txt"
if test "$rc" != 0; then
  exit "$rc"
fi
.venv-cuda/bin/python -u scripts/ens_x_overnight_finalize.py >> "${out%/candidate_timeline_evidence}/finalize.log" 2>&1
final_rc=$?
printf '%s\n' "$final_rc" > "${out%/candidate_timeline_evidence}/finalize_exit_code"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ) finalizer_finished exit_code=$final_rc" >> "$out/launcher_status.txt"
exit "$final_rc"
