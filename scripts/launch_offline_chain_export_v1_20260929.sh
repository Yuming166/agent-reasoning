#!/usr/bin/env bash
set -uo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
out=artifacts/offline_chain_events_v1_20260929_full
mkdir -p "$out"
export HTTPS_PROXY=http://10.63.0.72:7890
export HTTP_PROXY=http://10.63.0.72:7890
export ALL_PROXY=http://10.63.0.72:7890
printf 'started_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$out/launcher_status.txt"
.venv-cuda/bin/python -u scripts/export_offline_chain_events_v1_20260929.py --mode full --execute >> "$out/export.log" 2>&1
rc=$?
printf 'exit_code=%s\nfinished_utc=%s\n' "$rc" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$out/launcher_status.txt"
exit "$rc"
