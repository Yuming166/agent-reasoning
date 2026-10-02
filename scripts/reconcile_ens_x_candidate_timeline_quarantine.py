#!/usr/bin/env python3
"""Read-only ledger reconciliation for a quarantined provisional X timeline batch.

Unlike the original collector audit, this tool requires a separate output path and
never modifies the source run directory. It distinguishes attempted page slots,
request rows, coverage rows, and retries so partial accounts are not hidden.
"""
from __future__ import annotations


import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SOURCE_NAMES = ("attempt_budget.jsonl", "requests.jsonl", "coverage.jsonl")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def reconcile(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    reservations = read_jsonl(run_dir / "attempt_budget.jsonl")
    requests = read_jsonl(run_dir / "requests.jsonl")
    coverage = read_jsonl(run_dir / "coverage.jsonl")

    reservation_ids = [str(row["request_id"]) for row in reservations]
    request_ids = [str(row["request_id"]) for row in requests]
    reservation_id_set, request_id_set = set(reservation_ids), set(request_ids)

    reserved_slots: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    request_slots: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in reservations:
        reserved_slots[(str(row["x_user_id"]), int(row["page"]))].append(row)
    for row in requests:
        request_slots[(str(row["x_user_id"]), int(row["page"]))].append(row)

    coverage_by_id = {str(row["x_user_id"]): row for row in coverage}
    reserved_by_id: dict[str, set[int]] = defaultdict(set)
    requested_by_id: dict[str, set[int]] = defaultdict(set)
    for uid, page in reserved_slots:
        reserved_by_id[uid].add(page)
    for uid, page in request_slots:
        requested_by_id[uid].add(page)

    raw_errors = []
    for row in requests:
        raw_path = Path(str(row["raw_file"]))
        if not raw_path.is_absolute():
            raw_path = run_dir / raw_path
        if not raw_path.is_file():
            raw_errors.append({"request_id": str(row["request_id"]), "reason": "missing_raw_file"})
        elif sha256(raw_path) != row.get("raw_sha256"):
            raw_errors.append({"request_id": str(row["request_id"]), "reason": "raw_sha256_mismatch"})

    attempts_per_slot = [len(rows) for rows in reserved_slots.values()]
    status_counts = Counter(str(row.get("http_status")) for row in requests)
    coverage_pages_sum = sum(int(row.get("pages", 0)) for row in coverage)
    reserved_account_ids = set(reserved_by_id)
    coverage_account_ids = set(coverage_by_id)
    request_account_ids = set(requested_by_id)

    return {
        "schema": "ens-x-provisional-timeline-ledger-reconciliation-v1",
        "mode": "offline_read_only",
        "scope_status": "quarantined_not_eligible_for_confirmed_crosswalk_or_linked_graph_analysis",
        "collection_status": "stopped_do_not_resume_manifest",
        "source_files": {
            name: {"sha256": sha256(run_dir / name), "bytes": (run_dir / name).stat().st_size}
            for name in SOURCE_NAMES
        },
        "ledger_counts": {
            "attempt_reservation_rows": len(reservations),
            "request_log_rows": len(requests),
            "http_status_counts": dict(status_counts),
            "accounts_with_reservations": len(reserved_account_ids),
            "accounts_with_request_rows": len(request_account_ids),
            "accounts_with_terminal_coverage_rows": len(coverage_account_ids),
            "distinct_reserved_account_page_slots": len(reserved_slots),
            "distinct_requested_account_page_slots": len(request_slots),
            "coverage_pages_sum_for_terminal_coverage_rows": coverage_pages_sum,
            "max_distinct_reserved_pages_per_account": max(map(len, reserved_by_id.values()), default=0),
            "max_reservations_per_account_page_slot": max(attempts_per_slot, default=0),
            "page_slots_over_two_reservations": sum(n > 2 for n in attempts_per_slot),
            "reserved_without_request_log_ids": sorted(reservation_id_set - request_id_set),
            "request_without_reservation_ids": sorted(request_id_set - reservation_id_set),
            "duplicate_reservation_ids": sorted(k for k, n in Counter(reservation_ids).items() if n > 1),
            "duplicate_request_ids": sorted(k for k, n in Counter(request_ids).items() if n > 1),
            "reservation_only_account_ids_without_coverage": sorted(reserved_account_ids - coverage_account_ids),
            "coverage_accounts_without_reservations": sorted(coverage_account_ids - reserved_account_ids),
            "requested_slots_without_reservation": [
                {"x_user_id": uid, "page": page}
                for uid, page in sorted(set(request_slots) - set(reserved_slots))
            ],
            "coverage_page_count_mismatches": [
                {
                    "x_user_id": uid,
                    "coverage_pages": int(coverage_by_id[uid].get("pages", 0)),
                    "distinct_reserved_pages": len(reserved_by_id.get(uid, set())),
                }
                for uid in sorted(coverage_account_ids | reserved_account_ids)
                if uid in coverage_by_id
                and int(coverage_by_id[uid].get("pages", 0)) != len(reserved_by_id.get(uid, set()))
            ],
            "raw_response_integrity_errors": raw_errors,
            "coverage_stop_reasons": dict(Counter(str(row.get("stop_reason", "")) for row in coverage)),
        },
        "interpretation": [
            "Reservation rows count attempts; distinct (x_user_id, page) pairs count page slots; coverage.pages sums only terminal coverage rows.",
            "A reservation without a request row cannot establish whether the provider received the request.",
            "An account with reservations but no coverage row is a partial run, not zero pages and not complete coverage.",
            "The batch consists of provisional candidates and cannot confirm account ownership or contribute linked-graph edges.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New report path outside --run-dir")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    output = args.output.resolve()
    if output == run_dir or run_dir in output.parents:
        parser.error("--output must be outside the source run directory; source artifacts are immutable")
    if output.exists():
        parser.error("--output already exists; choose a new append-only report path")
    report = reconcile(run_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["ledger_counts"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
