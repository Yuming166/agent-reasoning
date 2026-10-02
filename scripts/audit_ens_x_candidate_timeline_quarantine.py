#!/usr/bin/env python3
"""Offline integrity and scope-quarantine audit for the stopped provisional-ID batch."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RUN = ROOT / 'artifacts/ens_x_crosswalk/overnight_ai_dataset_20260926/candidate_timeline_evidence'
OUT = RUN / 'scope_quarantine_audit.json'


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    coverage = read_jsonl(RUN / 'coverage.jsonl')
    reservations = read_jsonl(RUN / 'attempt_budget.jsonl')
    requests = read_jsonl(RUN / 'requests.jsonl')
    reserved_ids = [r['request_id'] for r in reservations]
    request_ids = [r['request_id'] for r in requests]
    reservation_set, request_set = set(reserved_ids), set(request_ids)
    bad_raw = []
    for row in requests:
        p = Path(row['raw_file'])
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            bad_raw.append({'request_id': row['request_id'], 'reason': 'missing_raw_file'})
        elif digest(p) != row['raw_sha256']:
            bad_raw.append({'request_id': row['request_id'], 'reason': 'raw_sha256_mismatch'})
    inventory = []
    for p in sorted(RUN.rglob('*')):
        if not p.is_file() or p.name.endswith('.lock') or p == OUT:
            continue
        inventory.append({'path': str(p.relative_to(RUN)), 'bytes': p.stat().st_size, 'sha256': digest(p)})
    total_pages = sum(int(r.get('pages', 0)) for r in coverage)
    total_statuses = sum(int(r.get('statuses', 0)) for r in coverage)
    summary = {
        'schema': 'ens-x-stopped-provisional-timeline-scope-audit-v1',
        'audited_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope_status': 'quarantined_out_of_scope_not_eligible_for_confirmed_crosswalk_or_linked_graph_analysis',
        'reason': 'The 181-ID queue consists of provisional candidates without completed account-side human confirmation.',
        'collection_status': 'stopped; do not resume this manifest',
        'target_window_utc': {'start_inclusive': '2026-01-01T00:00:00Z', 'end_exclusive': '2026-09-24T17:24:10Z'},
        'accounts_with_coverage_records': len(coverage),
        'planned_accounts': 181,
        'observed_pages': total_pages,
        'observed_statuses': total_statuses,
        'authored_in_window_observations': sum(int(r.get('authored_in_window', 0)) for r in coverage),
        'untimed_repost_observations': sum(int(r.get('reposts_untimed', 0)) for r in coverage),
        'coverage_stop_reasons': dict(Counter(str(r.get('stop_reason', '')) for r in coverage)),
        'attempt_reservations': len(reservations),
        'request_log_rows': len(requests),
        'reserved_without_request_log': sorted(reservation_set - request_set),
        'request_without_reservation': sorted(request_set - reservation_set),
        'duplicate_reservation_ids': sorted(k for k, v in Counter(reserved_ids).items() if v > 1),
        'duplicate_request_ids': sorted(k for k, v in Counter(request_ids).items() if v > 1),
        'raw_response_integrity_errors': bad_raw,
        'file_inventory': inventory,
        'limitations': [
            'An attempt reservation without a corresponding request log cannot prove whether bytes reached the provider.',
            'The manifest and all raw responses are retained only for provenance; they are not authorized account-to-wallet evidence.',
            'Observed timeline coverage is not evidence that a wallet belongs to the X account.',
        ],
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    notice = RUN / 'SCOPE_QUARANTINE.md'
    notice.write_text('''# Scope quarantine: provisional candidate timeline batch\n\nThis batch is retained for audit only. Its frozen queue contains provisional ENS/X candidates that had not completed account-side human confirmation. It must not be resumed, used to promote wallet/X links, or joined into confirmed wallet ownership / linked-graph analyses. The candidate collector entrypoint is now disabled.\n\nSee `scope_quarantine_audit.json` for the SHA-256 inventory, response-to-request audit, coverage counts, and any unresolved attempt reservation.\n''', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'file_inventory'}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
