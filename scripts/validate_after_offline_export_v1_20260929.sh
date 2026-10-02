#!/usr/bin/env bash
set -uo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
out=artifacts/offline_chain_events_v1_20260929_full
while ! grep -q '^exit_code=' "$out/launcher_status.txt" 2>/dev/null; do
  sleep 30
done
rc=$(sed -n 's/^exit_code=//p' "$out/launcher_status.txt" | tail -1)
if [ "$rc" != 0 ]; then
  printf 'validation_skipped_export_exit_code=%s\n' "$rc" > "$out/validation_status.txt"
  exit 1
fi
.venv-cuda/bin/python -u scripts/validate_offline_chain_events_v1_20260929.py --mode full > "$out/validation.log" 2>&1
vrc=$?
printf 'validation_exit_code=%s\nfinished_utc=%s\n' "$vrc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$out/validation_status.txt"
exit "$vrc"
