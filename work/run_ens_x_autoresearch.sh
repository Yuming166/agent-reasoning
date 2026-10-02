#!/usr/bin/env bash
set -euo pipefail

project_dir=/storage/gaoym/ex-graph-microtransaction-analysis
prompt_file="$project_dir/notes/autoresearch-overnight-prompt.md"
run_dir="$project_dir/artifacts/ens_x_crosswalk/overnight_autoresearch_20260925"

mkdir -p "$run_dir"
printf 'started_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$run_dir/launcher_status.txt"
printf 'launcher_pid=%s\n' "$$" >> "$run_dir/launcher_status.txt"
printf 'prompt=%s\n' "$prompt_file" >> "$run_dir/launcher_status.txt"
cd "$project_dir"

set +e
timeout --signal=TERM --kill-after=60s 6h /usr/local/bin/codex exec --approve-for-me --cd "$project_dir" --skip-git-repo-check - < "$prompt_file" >> "$run_dir/codex.log" 2>&1
exit_code=$?
set -e
printf 'finished_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$run_dir/launcher_status.txt"
printf 'exit_code=%s\n' "$exit_code" >> "$run_dir/launcher_status.txt"
exit "$exit_code"
