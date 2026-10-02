#!/usr/bin/env python3
"""DISABLED legacy collector for provisional ENS/X candidates.

The former 181-ID queue is outside the approved account-side-confirmed scope.
Raw outputs are retained for audit, but this entry point must never send requests.
Use the separately gated confirmed-account pilot collector only after the frozen
human-confirmation allowlist and batch gate pass.
"""
from __future__ import annotations


import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
sys.path.insert(0, str(ROOT / 'scripts'))
from collect_ens_x_expansion_pilot import append_jsonl, collect_account, normalize_archived  # noqa: E402

SRC = ROOT / 'artifacts/ens_x_crosswalk'
FRAME = SRC / 'expansion_decision_20260925/candidate_review_full_231.csv'
PILOT = SRC / 'timeline_expansion_pilot_20260925/pilot_queue.json'
OUT = SRC / 'overnight_ai_dataset_20260926/candidate_timeline_evidence'
MAX_PAGES_PER_ACCOUNT = 8
MAX_HTTP_ATTEMPTS_TOTAL = 2000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    raise RuntimeError(
        "collection disabled: frozen queue contains provisional candidates, "
        "not account-side-confirmed mappings; no network requests were sent"
    )


def _legacy_main_for_audit_only() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with FRAME.open(encoding='utf-8-sig', newline='') as f:
        frame = list(csv.DictReader(f))
    prior = json.loads(PILOT.read_text(encoding='utf-8'))
    previous_ids = {str(r['x_user_id']) for r in prior}
    queue = [r for r in frame if r['x_user_id'] not in previous_ids]
    if len(frame) != 231 or len(prior) != 50 or len(queue) != 181:
        raise ValueError('frozen candidate/pilot queue sizes changed')
    ids = [r['x_user_id'] for r in queue]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate stable X ID in discovery queue')
    manifest = {
        'schema': 'ens-x-provisional-evidence-discovery-v1',
        'created_date': '2026-09-26',
        'frame_sha256': sha(FRAME), 'prior_pilot_queue_sha256': sha(PILOT),
        'account_count': len(queue), 'stable_x_ids': ids,
        'target_start_inclusive_utc': '2026-01-01T00:00:00Z',
        'target_end_exclusive_utc': '2026-09-24T17:24:10Z',
        'max_pages_per_account': MAX_PAGES_PER_ACCOUNT,
        'max_http_attempts_total': MAX_HTTP_ATTEMPTS_TOTAL,
        'max_attempts_per_logical_page': 2,
        'request_delay_seconds': 1.0,
        'identity_status': 'provisional_candidate_not_account_confirmed',
        'source': 'FxEmbed public timeline v2; stable ID checked on every status',
    }
    manifest_path = OUT / 'run_manifest.json'
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding='utf-8')) != manifest:
            raise ValueError('frozen discovery manifest changed on resume')
    else:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    coverage_path = OUT / 'coverage.jsonl'
    coverage = {}
    if coverage_path.exists():
        for line in coverage_path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            uid = str(row.get('x_user_id'))
            if uid in coverage or uid not in ids:
                raise ValueError('duplicate or out-of-scope coverage ledger')
            coverage[uid] = row
    session = requests.Session()
    consecutive_failures = 0
    for idx, account in enumerate(queue, 1):
        uid = account['x_user_id']
        if uid in coverage:
            continue
        rec = collect_account(session, account, OUT, MAX_PAGES_PER_ACCOUNT, 1.0,
                              MAX_HTTP_ATTEMPTS_TOTAL)
        append_jsonl(coverage_path, rec)
        coverage[uid] = rec
        consecutive_failures = consecutive_failures + 1 if rec['stop_reason'] == 'request_or_payload_failed' else 0
        print(f'{datetime.now(timezone.utc).isoformat()} accounts={len(coverage)}/181 '
              f'uid={uid} pages={rec["pages"]} authored={rec["authored_in_window"]} '
              f'stop={rec["stop_reason"]}', flush=True)
        if consecutive_failures >= 10:
            raise RuntimeError('ten consecutive account failures; stop requests')
    stats = normalize_archived(OUT, queue)
    summary = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'accounts_planned': 181, 'accounts_with_coverage_record': len(coverage),
        'prior_pilot_accounts_excluded': 50,
        'new_timeline_pages_observed': sum(int(r['pages']) for r in coverage.values()),
        'new_http_attempts': sum(1 for line in (OUT / 'attempt_budget.jsonl').open() if line.strip()),
        'stop_reasons': dict(Counter(r['stop_reason'] for r in coverage.values())),
        'normalized': stats, 'identity_status': 'provisional_candidate_not_account_confirmed',
        'timeline_source_complete_claim': False,
        'paid_query_count': 0,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
