#!/usr/bin/env python3
"""Offline integrity/coverage audit for archived timeline pilot data.

Only successful request-log rows whose archived body, SHA-256, API envelope,
result count, and cursor transition reconcile are eligible for coverage claims.
This script never changes collection data or performs network requests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fx_authorized_continue import owner_id, parse_dt  # noqa: E402

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 24, 17, 24, 10, tzinfo=timezone.utc)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"invalid JSONL at {path}:{n}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"non-object JSONL row at {path}:{n}")
        rows.append(row)
    return rows


def norm_cursor(value):
    return None if value in (None, "") else str(value)


def audit(root: Path) -> dict:
    coverage_path, request_path = root / "coverage.jsonl", root / "requests.jsonl"
    coverage, requests = read_jsonl(coverage_path), read_jsonl(request_path)
    by_handle: dict[str, list[dict]] = defaultdict(list)
    for request in requests:
        handle = str(request.get("handle") or "").strip().lstrip("@").casefold()
        by_handle[handle].append(request)

    seen_uids, seen_handles, accounts, all_issues = set(), set(), [], []
    covered_handles = {str(c.get("handle") or "").strip().lstrip("@").casefold() for c in coverage}
    unmatched_requests = [r for r in requests
                          if str(r.get("handle") or "").strip().lstrip("@").casefold() not in covered_handles]
    total_bound_attempts = total_successes = 0
    for cov in coverage:
        uid = str(cov.get("x_user_id") or "")
        handle = str(cov.get("handle") or "").strip().lstrip("@")
        key = handle.casefold()
        issues = []
        if not uid.isdigit():
            issues.append("coverage_missing_stable_numeric_x_user_id")
        if uid in seen_uids:
            issues.append("duplicate_x_user_id_in_coverage")
        if not key or key in seen_handles:
            issues.append("missing_or_duplicate_handle_in_coverage")
        seen_uids.add(uid); seen_handles.add(key)
        req_rows = by_handle.get(key, [])
        total_bound_attempts += len(req_rows)
        valid_by_page: dict[int, list[dict]] = defaultdict(list)
        account_issues = []
        for req in req_rows:
            try:
                page = int(req.get("page"))
            except (TypeError, ValueError):
                account_issues.append("request_page_invalid")
                continue
            if page < 1:
                account_issues.append("request_page_invalid")
                continue
            is_success = (req.get("http_status") == 200 and req.get("api_code") == 200
                          and not req.get("error"))
            if not is_success:
                continue
            raw_value = req.get("raw_file")
            if not raw_value:
                account_issues.append(f"page_{page}_successful_request_missing_raw_path")
                continue
            raw_path = Path(str(raw_value))
            if not raw_path.is_absolute():
                raw_path = root / raw_path
            try:
                raw_path = raw_path.resolve()
                raw_path.relative_to(root.resolve())
            except (OSError, ValueError):
                account_issues.append(f"page_{page}_raw_path_outside_pilot_root")
                continue
            try:
                body = raw_path.read_bytes()
            except OSError:
                account_issues.append(f"page_{page}_raw_file_missing")
                continue
            digest = hashlib.sha256(body).hexdigest()
            if digest != req.get("raw_sha256"):
                account_issues.append(f"page_{page}_raw_sha256_mismatch")
                continue
            try:
                payload = json.loads(body)
            except ValueError:
                account_issues.append(f"page_{page}_raw_json_invalid")
                continue
            if not isinstance(payload, dict) or payload.get("code") != 200 or not isinstance(payload.get("results"), list):
                account_issues.append(f"page_{page}_raw_api_envelope_invalid")
                continue
            if req.get("result_count") != len(payload["results"]):
                account_issues.append(f"page_{page}_result_count_mismatch")
                continue
            cursor_out = norm_cursor((payload.get("cursor") or {}).get("bottom")
                                     if isinstance(payload.get("cursor"), dict) else None)
            valid_by_page[page].append({"request": req, "payload": payload,
                                        "cursor_in": norm_cursor(req.get("cursor_in")),
                                        "cursor_out": cursor_out,
                                        "raw_file": str(raw_path), "raw_sha256": digest})
        valid_pages = {}
        for page, candidates in valid_by_page.items():
            if len(candidates) != 1:
                account_issues.append(f"page_{page}_ambiguous_successful_responses")
                continue
            valid_pages[page] = candidates[0]
        ordered_pages = sorted(valid_pages)
        for previous, current in zip(ordered_pages, ordered_pages[1:]):
            if current == previous + 1:
                if valid_pages[current]["cursor_in"] != valid_pages[previous]["cursor_out"]:
                    account_issues.append(f"cursor_chain_mismatch_page_{current}")
            else:
                account_issues.append(f"page_sequence_gap_{previous}_to_{current}")
        total_successes += len(valid_pages)
        timestamps = []
        boundary = False
        authored_window = repost_observations = owner_mismatches = missing_ts = 0
        authored_ids, repost_ids = set(), set()
        missing_status_ids = 0
        for page in ordered_pages:
            for status in valid_pages[page]["payload"]["results"]:
                if not isinstance(status, dict):
                    owner_mismatches += 1
                    continue
                owner, _ = owner_id(status)
                if owner != uid:
                    owner_mismatches += 1
                    continue
                ts = parse_dt(status.get("created_timestamp") or status.get("created_at"))
                if ts is None:
                    missing_ts += 1
                    continue
                status_id = str(status.get("id") or "")
                if not status_id:
                    missing_status_ids += 1
                if isinstance(status.get("reposted_by"), dict):
                    repost_observations += 1
                    if status_id:
                        repost_ids.add(status_id)
                    continue
                timestamps.append(ts)
                if START <= ts < END:
                    authored_window += 1
                    if status_id:
                        authored_ids.add(status_id)
                if ts < START:
                    boundary = True
        if owner_mismatches:
            account_issues.append("owner_mismatch_in_validated_pages")
        legacy_stop = cov.get("stop_reason", "unknown")
        if boundary:
            corrected = "boundary_observed_source_completeness_unverified"
        elif legacy_stop == "cursor_exhausted":
            corrected = "endpoint_exhausted_before_boundary"
        elif legacy_stop == "page_ceiling":
            corrected = "incomplete_page_ceiling_before_boundary"
        elif legacy_stop in ("request_or_payload_failed", "timeline_owner_mismatch", "cursor_repeated"):
            corrected = "incomplete_or_unknown_" + str(legacy_stop)
        else:
            corrected = "unknown"
        # Any provenance/cursor defect invalidates a positive boundary claim.
        if account_issues and boundary:
            corrected = "integrity_issue_boundary_not_accepted"
        acct = {
            "handle": handle, "x_user_id": uid,
            "legacy_stop_reason": legacy_stop,
            "legacy_timeline_complete": cov.get("timeline_complete"),
            "request_attempt_count": len(req_rows),
            "successful_request_count": sum(1 for r in req_rows if r.get("http_status") == 200 and r.get("api_code") == 200 and not r.get("error")),
            "validated_page_count": len(valid_pages),
            "validated_pages": [{"page": n, "cursor_in": valid_pages[n]["cursor_in"],
                                  "cursor_out": valid_pages[n]["cursor_out"],
                                  "raw_file": valid_pages[n]["raw_file"],
                                  "raw_sha256": valid_pages[n]["raw_sha256"]} for n in ordered_pages],
            "corrected_coverage_status": corrected,
            "target_boundary_observed_in_validated_pages": boundary and not account_issues,
            "authored_in_window_observations": authored_window,
            "unique_authored_in_window_status_ids": len(authored_ids),
            "repost_observations_untimed": repost_observations,
            "unique_repost_source_status_ids": len(repost_ids),
            "owner_statuses_missing_id": missing_status_ids,
            "owner_mismatches": owner_mismatches,
            "missing_timestamps": missing_ts,
            "oldest_valid_owner_authored_timestamp": min(timestamps).isoformat() if timestamps else None,
            "newest_valid_owner_authored_timestamp": max(timestamps).isoformat() if timestamps else None,
            "integrity_issues": sorted(set(issues + account_issues)),
        }
        accounts.append(acct)
        all_issues.extend(f"{handle}:{issue}" for issue in acct["integrity_issues"])

    status_counts = Counter(a["corrected_coverage_status"] for a in accounts)
    return {
        "audit_mode": "offline_only_raw_files_unchanged",
        "target_start_inclusive_utc": START.isoformat(),
        "target_end_exclusive_utc": END.isoformat(),
        "coverage_file": str(coverage_path), "coverage_sha256": sha256(coverage_path),
        "request_log": str(request_path), "request_log_sha256": sha256(request_path),
        "account_count": len(accounts),
        "request_attempt_count_bound_to_coverage_handles": total_bound_attempts,
        "request_attempt_count_unmatched_to_coverage": len(unmatched_requests),
        "request_success_count_bound_to_coverage_handles": sum(
            r.get("http_status") == 200 and r.get("api_code") == 200 and not r.get("error")
            for r in requests if str(r.get("handle") or "").strip().lstrip("@").casefold() in covered_handles),
        "request_error_count_bound_to_coverage_handles": sum(
            not (r.get("http_status") == 200 and r.get("api_code") == 200 and not r.get("error"))
            for r in requests if str(r.get("handle") or "").strip().lstrip("@").casefold() in covered_handles),
        "validated_successful_page_count": total_successes,
        "integrity_issue_count": len(all_issues) + len(unmatched_requests),
        "integrity_issues": all_issues + ["unmatched_request_handle:" + str(r.get("handle")) for r in unmatched_requests],
        "legacy_timeline_complete_true_count": sum(bool(a["legacy_timeline_complete"]) for a in accounts),
        "corrected_boundary_observed_count": sum(a["target_boundary_observed_in_validated_pages"] for a in accounts),
        "corrected_status_counts": dict(status_counts),
        "total_authored_in_window_observations": sum(a["authored_in_window_observations"] for a in accounts),
        "total_unique_authored_in_window_status_ids": sum(a["unique_authored_in_window_status_ids"] for a in accounts),
        "total_repost_observations_untimed": sum(a["repost_observations_untimed"] for a in accounts),
        "total_unique_repost_source_status_ids": sum(a["unique_repost_source_status_ids"] for a in accounts),
        "identity_scope": "Request handles are joined to the stable IDs recorded in coverage.jsonl; this audit does not prove wallet-to-account ownership or account-side confirmation.",
        "accounts": accounts,
        "interpretation": "Request-log-bound successful pages only. Cursor exhaustion is endpoint exhaustion, not proof of complete historical coverage. Repost source timestamps are not timeline-owner action times. Even a validated owner-authored pre-window status does not prove source archive completeness.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.pilot_dir.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "accounts"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
