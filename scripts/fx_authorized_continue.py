#!/usr/bin/env python3
"""Reconcile and boundedly continue the authorized FxEmbed pilot.

The parent run is immutable. This script first re-parses all previously archived
pages with correct retweet ownership semantics, then (unless --audit-only) fetches
only additional cursor pages for the same fixed allowlist and fixed parent cutoff.
No follower/following endpoints or candidate-pool expansion are performed.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

API = "https://api.fxtwitter.com/2/profile/{user_ref}/statuses"
START_UTC = datetime(2026, 1, 1, tzinfo=timezone.utc)
USER_AGENT = "exgraph-research/0.3 (authorized bounded academic collection)"
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3
MAX_PAGES_PER_ACCOUNT = 250
MAX_TIMELINE_PAGES_TOTAL = 1200
# This is a cumulative ceiling across restarts, not a per-process retry limit.
MAX_HTTP_ATTEMPTS_TOTAL = MAX_TIMELINE_PAGES_TOTAL * MAX_RETRIES
TRANSIENT_HTTP = {429, 500, 502, 503, 504}


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        n = int(value)
        if n > 10**12:
            n //= 1000
        return datetime.fromtimestamp(n, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "account"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def logical_page_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (str(row.get("x_user_id", "")), int(row.get("page") or 0),
            "" if row.get("cursor_in") is None else str(row.get("cursor_in")))


def append_fsynced_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_parent(parent: Path) -> tuple[dict[str, Any], list[dict[str, str]], datetime]:
    manifest = read_json(parent / "run_manifest.json")
    if manifest.get("account_count") != 12:
        raise ValueError(f"unexpected parent account_count={manifest.get('account_count')}; refusing to broaden/redefine pilot")
    cutoff = parse_dt(manifest.get("target_end_exclusive_utc"))
    if cutoff is None:
        raise ValueError("parent manifest has no valid fixed target_end_exclusive_utc")
    sample = read_csv(parent / "sample_manifest.csv")
    if len(sample) != 12 or len({r.get("x_user_id") for r in sample}) != 12:
        raise ValueError("parent sample manifest is not the original fixed 12-ID sample")
    if not all(r.get("profile_id_preflight_match", "").lower() == "true" for r in sample):
        raise ValueError("parent sample lacks a passing stable-ID preflight for every account")

    # Re-validate the collection allowlist against the filled manual review sheet
    # immediately before any continuation request. A profile-ID preflight alone
    # does not establish account-side wallet/ENS confirmation.
    verification_path = parent.parent / "verification_sample_v2_filled.csv"
    if not verification_path.is_file():
        raise ValueError(f"missing account-side verification source: {verification_path}")
    verification_rows = read_csv(verification_path)
    required = {"pair_id", "handle", "verification_status", "evidence_date", "evidence_note", "x_user_id"}
    if not verification_rows or not required.issubset(verification_rows[0]):
        raise ValueError("account-side verification CSV is missing required fields or rows")
    confirmed = [r for r in verification_rows if r.get("verification_status", "").strip() == "account_confirms"]
    for acct in sample:
        uid = str(acct.get("x_user_id", "")).strip()
        handle = str(acct.get("handle", "")).strip().lstrip("@").casefold()
        pair_ids = {x.strip() for x in str(acct.get("pair_ids", "")).split("|") if x.strip()}
        if not uid.isdigit() or not pair_ids:
            raise ValueError(f"sample account has invalid stable ID or no source pair IDs: {acct.get('handle')}")
        matches = [r for r in confirmed
                   if str(r.get("x_user_id", "")).strip() == uid
                   and str(r.get("handle", "")).strip().lstrip("@").casefold() == handle
                   and str(r.get("pair_id", "")).strip() in pair_ids
                   and str(r.get("evidence_date", "")).strip()
                   and str(r.get("evidence_note", "")).strip()]
        if not matches:
            raise ValueError(
                f"sample account is not backed by account_confirms evidence for its recorded pair(s): "
                f"{acct.get('handle')} ({uid})"
            )
    # Keep the original boundary rather than moving it to the continuation time.
    return manifest, sample, cutoff


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL audit log strictly; a damaged line makes history uncertain."""
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSONL at {path}:{line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"non-object JSONL record at {path}:{line_no}")
        rows.append(row)
    return rows


def load_request_log(run_dir: Path) -> list[dict[str, Any]]:
    """Load timeline-status attempts, excluding profile lookups from legacy logs.

    Some parent-run logs wrote profile requests with an empty ``kind`` and no
    page number. Treating a missing/empty kind as a status request made those
    non-timeline calls look like malformed timeline attempts. Legacy status
    rows are still accepted when they have a page number; explicitly typed
    status rows are retained even when malformed so the budget audit fails
    closed rather than silently dropping them.
    """
    rows: list[dict[str, Any]] = []
    for path in (run_dir / "requests.jsonl", run_dir / "continuation_requests.jsonl"):
        for row in _read_jsonl_objects(path):
            kind = str(row.get("kind") or "").strip().casefold()
            if kind == "statuses" or (not kind and row.get("page") is not None):
                rows.append(row)
    return rows


def bind_legacy_request_ids(requests: list[dict[str, Any]],
                            sample: list[dict[str, str]]) -> tuple[list[dict[str, Any]], int]:
    """Resolve missing legacy status IDs only through the frozen 12-ID sample.

    Parent logs predate stable-ID fields but include the exact requested handle.
    A missing ID is backfilled only when that handle maps uniquely in the fixed
    sample; a conflicting recorded ID or unknown/ambiguous handle fails closed.
    """
    by_handle: dict[str, set[str]] = defaultdict(set)
    for acct in sample:
        handle = str(acct.get("handle", "")).strip().lstrip("@").casefold()
        uid = str(acct.get("x_user_id", "")).strip()
        if handle and uid.isdigit():
            by_handle[handle].add(uid)
    normalized: list[dict[str, Any]] = []
    backfills = 0
    for index, row in enumerate(requests, 1):
        item = dict(row)
        raw_uid = str(item.get("x_user_id", "")).strip()
        handle = str(item.get("handle", "")).strip().lstrip("@").casefold()
        candidates = by_handle.get(handle, set())
        if raw_uid:
            if not raw_uid.isdigit() or (candidates and raw_uid not in candidates):
                raise ValueError(f"request[{index}] stable ID conflicts with frozen sample for handle={handle!r}")
        else:
            if len(candidates) != 1:
                raise ValueError(f"request[{index}] missing stable ID and handle is not unique in frozen sample")
            item["x_user_id"] = next(iter(candidates))
            item["stable_id_recovered_from_frozen_handle"] = True
            backfills += 1
        normalized.append(item)
    return normalized, backfills


def load_attempt_budget(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl_objects(path)


def _attempt_key(row: dict[str, Any]) -> tuple[str, int, str]:
    uid = str(row.get("x_user_id", "")).strip()
    if not uid.isdigit():
        raise ValueError("attempt record has no valid stable x_user_id")
    try:
        page = int(row.get("page"))
    except (TypeError, ValueError) as exc:
        raise ValueError("attempt record has no valid page number") from exc
    if page < 1:
        raise ValueError("attempt record page number must be positive")
    cursor = "" if row.get("cursor_in") is None else str(row.get("cursor_in"))
    return uid, page, cursor


def audit_attempt_budget(requests: list[dict[str, Any]],
                         reservations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Conservatively union logged HTTP attempts and durable reservations.

    A reservation and request log row are deduplicated only by an identical,
    unique request_id. Unmatched reservations still consume budget; missing or
    inconsistent identity history is surfaced as an issue and must halt resume.
    """
    reservations = reservations or []
    issues: list[str] = []
    by_id: dict[str, tuple[str, tuple[str, int, str]]] = {}
    union: list[tuple[str, int, str]] = []

    def add(rows: list[dict[str, Any]], source: str) -> None:
        seen: set[str] = set()
        for index, row in enumerate(rows, 1):
            try:
                key = _attempt_key(row)
            except ValueError as exc:
                issues.append(f"{source}[{index}]: {exc}")
                continue
            rid = str(row.get("request_id", "")).strip()
            if not rid:
                issues.append(f"{source}[{index}]: missing request_id; attempt identity cannot be reconciled")
            else:
                if rid in seen:
                    issues.append(f"{source}[{index}]: duplicate request_id {rid}")
                    # Conservatively count the duplicate record as another
                    # possible attempt; the identity history is ambiguous.
                    union.append(key)
                    continue
                seen.add(rid)
                previous = by_id.get(rid)
                if previous:
                    prev_source, prev_key = previous
                    if prev_key != key:
                        issues.append(f"request_id {rid} has mismatched attempt identity in {prev_source} and {source}")
                        union.append(key)
                    continue
                by_id[rid] = (source, key)
            union.append(key)

    add(requests, "request_log")
    add(reservations, "attempt_budget")
    counts = Counter(union)
    page_overages = [
        {"x_user_id": uid, "page": page, "cursor_in": cursor, "attempts": count,
         "limit": MAX_RETRIES}
        for (uid, page, cursor), count in sorted(counts.items()) if count > MAX_RETRIES
    ]
    return {
        "known_attempt_count": len(union),
        "global_limit": MAX_HTTP_ATTEMPTS_TOTAL,
        "global_overage": len(union) > MAX_HTTP_ATTEMPTS_TOTAL,
        "per_page_overages": page_overages,
        "history_issues": issues,
        "within_budget": not issues and not page_overages and len(union) <= MAX_HTTP_ATTEMPTS_TOTAL,
    }


def load_valid_page(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("code") != 200 or not isinstance(payload.get("results"), list):
        return None
    return payload


def owner_id(status: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (timeline-owner ID, source-author ID); repost owner is not source author."""
    author = status.get("author") if isinstance(status.get("author"), dict) else {}
    reposted_by = status.get("reposted_by") if isinstance(status.get("reposted_by"), dict) else None
    source_author_id = str(author.get("id")) if author.get("id") is not None else None
    if reposted_by is not None:
        value = reposted_by.get("id")
        return (str(value) if value is not None else None, source_author_id)
    return source_author_id, source_author_id


def collect_pages(root: Path, handle: str) -> list[tuple[int, Path, dict[str, Any]]]:
    out = []
    for p in root.glob(f"raw/{safe_name(handle)}/page_*.body"):
        m = re.search(r"page_(\d+)_", p.name)
        if not m:
            continue
        payload = load_valid_page(p)
        if payload is not None:
            out.append((int(m.group(1)), p, payload))
    return sorted(out, key=lambda x: (x[0], x[1].name))


def status_times(payload: dict[str, Any]) -> list[datetime]:
    return [dt for item in payload.get("results", []) if isinstance(item, dict)
            if (dt := parse_dt(item.get("created_timestamp") or item.get("created_at"))) is not None]


def archived_timeline_integrity(pages: list[tuple[int, Path, dict[str, Any]]],
                                expected_uid: str) -> str | None:
    """Validate all archived status owners/timestamps/order before declaring a terminal boundary."""
    previous: datetime | None = None
    for _page_no, _path, payload in sorted(pages, key=lambda x: (x[0], x[1].name)):
        statuses = payload.get("results") or []
        if not statuses:
            cursor_obj = payload.get("cursor") if isinstance(payload.get("cursor"), dict) else {}
            # An empty response with a bottom cursor is an intermediate page;
            # without a cursor it is ambiguous and cannot prove exhaustion.
            if cursor_obj.get("bottom"):
                continue
            return "empty_archived_page_without_cursor"
        for status in statuses:
            if not isinstance(status, dict):
                return "invalid_archived_status"
            owner, _author = owner_id(status)
            if owner is None:
                return "missing_timeline_owner_id"
            if owner != expected_uid:
                return "timeline_owner_id_mismatch"
            dt = parse_dt(status.get("created_timestamp") or status.get("created_at"))
            if dt is None:
                return "missing_or_invalid_timestamp"
            if previous is not None and dt > previous:
                return "pagination_order_violation"
            previous = dt
    return None


def plan_account(parent: Path, continuation_dir: Path, acct: dict[str, str],
                 prior_requests: list[dict[str, Any]]) -> dict[str, Any]:
    handle, uid = acct["handle"], str(acct["x_user_id"])
    pages: list[tuple[int, Path, dict[str, Any]]] = []
    for root in (parent, continuation_dir):
        pages.extend(collect_pages(root, handle))
    pages.sort(key=lambda x: (x[0], x[1].name))
    successful_by_page: dict[int, tuple[Path, dict[str, Any]]] = {}
    for page_no, path, payload in pages:
        # Prefer the first archived success for a logical page; every HTTP
        # attempt remains separately preserved and checksummed in the request log.
        successful_by_page.setdefault(page_no, (path, payload))

    account_requests = [r for r in prior_requests
                        if r.get("handle", "").casefold() == handle.casefold()
                        and r.get("page") is not None]
    requested_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in account_requests:
        try:
            requested_by_page[int(row["page"])].append(row)
        except (TypeError, ValueError):
            continue
    logical_pages = set(successful_by_page) | set(requested_by_page)
    prior_logical_pages = len(logical_pages)

    # If the last logical page was attempted but no valid response was archived,
    # retry that exact cursor/page instead of replaying already saved pages.
    requested_page_numbers = set(requested_by_page)
    latest_requested_page = max(requested_page_numbers, default=0)
    latest_success_page = max(successful_by_page, default=0)
    if latest_requested_page > latest_success_page:
        attempts = requested_by_page[latest_requested_page]
        last_attempt = attempts[-1]
        cursor = last_attempt.get("cursor_in")
        page_key = logical_page_key({**last_attempt, "x_user_id": uid, "page": latest_requested_page})
        cumulative_attempts = sum(
            1 for row in attempts
            if logical_page_key({**row, "x_user_id": uid}) == page_key
        )
        if cumulative_attempts >= MAX_RETRIES:
            return {"handle": handle, "x_user_id": uid, "next_page": None, "cursor": cursor,
                    "prior_logical_pages": prior_logical_pages,
                    "prior_successful_pages": len(successful_by_page),
                    "cumulative_http_attempts_for_page": cumulative_attempts,
                    "status": "terminal_retry_budget_exhausted"}
        return {"handle": handle, "x_user_id": uid,
                "next_page": latest_requested_page, "cursor": cursor,
                "prior_logical_pages": prior_logical_pages,
                "prior_successful_pages": len(successful_by_page),
                "cumulative_http_attempts_for_page": cumulative_attempts,
                "status": "retry_failed_first_page" if latest_requested_page == 1 else "retry_failed_page"}

    if not successful_by_page:
        return {"handle": handle, "x_user_id": uid, "next_page": 1, "cursor": None,
                "prior_logical_pages": prior_logical_pages, "prior_successful_pages": 0,
                "status": "retry_failed_first_page"}

    page_no = latest_success_page
    last_payload = successful_by_page[page_no][1]
    results = last_payload.get("results") or []
    times = status_times(last_payload)
    cursor = (last_payload.get("cursor") or {}).get("bottom") if isinstance(last_payload.get("cursor"), dict) else None

    for status in results:
        if not isinstance(status, dict):
            continue
        owner, _ = owner_id(status)
        if owner != uid:
            return {"handle": handle, "x_user_id": uid, "next_page": None, "cursor": None,
                    "prior_logical_pages": prior_logical_pages,
                    "prior_successful_pages": len(successful_by_page),
                    "status": "identity_validation_failed"}
    # Timeline entries may be returned out of creation-time order (for example,
    # pinned/reposted material). Record that anomaly during reconciliation, but
    # continue the cursor chain; stop by time only when every returned status has
    # a parseable timestamp and the entire page is older than the target window.
    reached_boundary = bool(times and len(times) == len(results) and max(times) < START_UTC)
    # A zero-result page is not terminal when the provider still supplies a
    # bottom cursor. Continue the cursor chain within the existing hard limits.
    exhausted = not cursor
    if reached_boundary or exhausted:
        issue = archived_timeline_integrity(
            [(n, item[0], item[1]) for n, item in sorted(successful_by_page.items())], uid)
        if issue:
            return {"handle": handle, "x_user_id": uid, "next_page": None, "cursor": None,
                    "prior_logical_pages": prior_logical_pages,
                    "prior_successful_pages": len(successful_by_page),
                    "terminal_integrity_issue": issue,
                    "status": "terminal_coverage_requires_review"}
        status = "already_reached_start_boundary" if reached_boundary else "already_exhausted_no_cursor"
        return {"handle": handle, "x_user_id": uid, "next_page": None, "cursor": None,
                "prior_logical_pages": prior_logical_pages,
                "prior_successful_pages": len(successful_by_page),
                "status": status}
    return {"handle": handle, "x_user_id": uid, "next_page": page_no + 1, "cursor": str(cursor),
            "prior_logical_pages": prior_logical_pages,
            "prior_successful_pages": len(successful_by_page),
            "status": "resume_from_cursor"}


class Continuation:
    def __init__(self, output: Path, cutoff: datetime,
                 prior_requests: list[dict[str, Any]] | None = None):
        self.output = output
        self.cutoff = cutoff
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self.log = output / "continuation_requests.jsonl"
        self.budget_log = output / "attempt_budget.jsonl"
        prior_requests = prior_requests or []
        if not self.budget_log.exists():
            # One-time, conservative migration: every previously logged HTTP
            # attempt consumes budget before this process can issue a request.
            with self.budget_log.open("x", encoding="utf-8") as f:
                for index, row in enumerate(prior_requests, 1):
                    reservation = {
                        "reservation_id": f"legacy_{index:06d}",
                        "legacy_migration": True,
                        "x_user_id": str(row.get("x_user_id", "")),
                        "handle": row.get("handle"),
                        "page": int(row.get("page") or 0),
                        "cursor_in": row.get("cursor_in"),
                        "request_id": row.get("request_id"),
                    }
                    f.write(json.dumps(reservation, ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
        self.budget_rows = load_attempt_budget(self.budget_log)
        self._validate_budget_ledger(prior_requests)
        self.attempt_counts: Counter[tuple[str, int, str]] = Counter(
            logical_page_key(row) for row in self.budget_rows
        )
        self.request_count = 0
        if self.log.exists():
            for line in self.log.read_text(encoding="utf-8").splitlines():
                try:
                    request_id = json.loads(line).get("request_id", "")
                except json.JSONDecodeError:
                    continue
                match = re.fullmatch(r"cont_req_(\d+)", str(request_id))
                if match:
                    self.request_count = max(self.request_count, int(match.group(1)))
        self.last_request_at: float | None = None
        self.timeline_pages = 0

    def _validate_budget_ledger(self, prior_requests: list[dict[str, Any]]) -> None:
        audit = audit_attempt_budget(prior_requests, self.budget_rows)
        if audit["history_issues"]:
            raise ValueError(f"attempt history is incomplete/inconsistent; refusing resume: {audit['history_issues']}")
        if audit["per_page_overages"] or audit["global_overage"]:
            raise ValueError(f"attempt budget exceeded; refusing resume: {audit}")
        if self.budget_rows:
            request_ids = {str(r.get("request_id", "")).strip() for r in prior_requests}
            reserved_ids = {str(r.get("request_id", "")).strip() for r in self.budget_rows}
            unmatched = sorted(rid for rid in request_ids if rid and rid not in reserved_ids)
            if unmatched:
                raise ValueError(
                    "attempt ledger is missing reservations for logged HTTP attempts; refusing resume: "
                    f"{unmatched}"
                )

    def _reserve_attempt(self, acct: dict[str, str], page: int, cursor: str | None,
                         req_id: str) -> tuple[bool, str | None, int]:
        key = (str(acct["x_user_id"]), int(page), "" if cursor is None else str(cursor))
        prior_page_attempts = self.attempt_counts[key]
        if prior_page_attempts >= MAX_RETRIES:
            return False, "cumulative_page_attempt_budget_exhausted", prior_page_attempts
        if len(self.budget_rows) >= MAX_HTTP_ATTEMPTS_TOTAL:
            return False, "cumulative_http_attempt_budget_exhausted", prior_page_attempts
        attempt_no = prior_page_attempts + 1
        row = {
            "reservation_id": req_id,
            "reserved_at_utc": iso(datetime.now(timezone.utc)),
            "legacy_migration": False,
            "x_user_id": key[0], "handle": acct["handle"], "page": int(page),
            "cursor_in": cursor, "attempt": attempt_no, "request_id": req_id,
        }
        append_fsynced_jsonl(self.budget_log, row)
        self.budget_rows.append(row)
        self.attempt_counts[key] += 1
        return True, None, attempt_no

    def request(self, acct: dict[str, str], page: int, cursor: str | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        handle, uid = acct["handle"], str(acct["x_user_id"])
        # Use the already verified stable user ID, not a potentially changed handle.
        user_ref = f"id:{uid}"
        url = API.format(user_ref=quote(user_ref, safe=":_-"))
        params = {"cursor": cursor} if cursor else None
        last: dict[str, Any] = {}
        attempts_this_call = 0
        while attempts_this_call < MAX_RETRIES:
            if len(self.budget_rows) >= MAX_HTTP_ATTEMPTS_TOTAL:
                return None, {"handle": handle, "x_user_id": uid, "page": page,
                              "cursor_in": cursor, "error": "cumulative_http_attempt_budget_exhausted"}
            now = time.monotonic()
            if self.last_request_at is not None:
                wait = REQUEST_DELAY_SECONDS - (now - self.last_request_at)
                if wait > 0:
                    time.sleep(wait)
            self.request_count += 1
            req_id = f"cont_req_{self.request_count:05d}"
            reserved, budget_error, attempt = self._reserve_attempt(acct, page, cursor, req_id)
            if not reserved:
                return None, {"handle": handle, "x_user_id": uid, "page": page,
                              "cursor_in": cursor, "error": budget_error,
                              "cumulative_http_attempts_for_page": attempt}
            attempts_this_call += 1
            self.last_request_at = time.monotonic()
            requested_at = datetime.now(timezone.utc)
            raw_file = self.output / "raw" / safe_name(handle) / f"page_{page:04d}_{req_id}_attempt_{attempt}.body"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                response = self.session.get(url, params=params, timeout=(15, 45))
                body = response.content
                raw_file.write_bytes(body)
                try:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        payload = None
                        parse_error = "json_root_not_object"
                    else:
                        parse_error = None
                except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                    payload = None
                    parse_error = f"json_parse_error:{type(exc).__name__}"
                api_code = payload.get("code") if payload else None
                results = payload.get("results") if payload else None
                cursor_out = ((payload or {}).get("cursor") or {}).get("bottom") if isinstance((payload or {}).get("cursor"), dict) else None
                error = parse_error
                if response.status_code != 200:
                    error = error or f"http_{response.status_code}"
                elif api_code != 200:
                    error = error or f"api_code_{api_code}"
                elif not isinstance(results, list):
                    error = error or "missing_results_list"
                last = {
                    "request_id": req_id,
                    "requested_at_utc": iso(requested_at),
                    "handle": handle,
                    "x_user_id": uid,
                    "kind": "statuses",
                    "page": page,
                    "cursor_in": cursor,
                    "cursor_out": str(cursor_out) if cursor_out is not None else None,
                    "request_url_without_query": url,
                    "query_params": params or {},
                    "http_status": response.status_code,
                    "api_code": api_code,
                    "attempt": attempt,
                    "result_count": len(results) if isinstance(results, list) else None,
                    "response_bytes": len(body),
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                    "raw_file": str(raw_file.relative_to(self.output)),
                    "error": error,
                }
                with self.log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(last, ensure_ascii=False, sort_keys=True) + "\n")
                    f.flush()
                if error is None:
                    return payload, last
                if response.status_code not in TRANSIENT_HTTP or attempt >= MAX_RETRIES:
                    return None, last
            except requests.RequestException as exc:
                last = {
                    "request_id": req_id, "requested_at_utc": iso(requested_at), "handle": handle,
                    "x_user_id": uid, "kind": "statuses", "page": page, "cursor_in": cursor,
                    "cursor_out": None, "request_url_without_query": url, "query_params": params or {},
                    "http_status": None, "api_code": None, "attempt": attempt, "result_count": None,
                    "response_bytes": None, "response_sha256": None, "raw_file": None,
                    "error": f"request_exception:{type(exc).__name__}:{str(exc)[:180]}",
                }
                with self.log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(last, ensure_ascii=False, sort_keys=True) + "\n")
                    f.flush()
                if attempt >= MAX_RETRIES:
                    return None, last
            if attempt < MAX_RETRIES and attempts_this_call < MAX_RETRIES:
                time.sleep(min(2 ** (attempt - 1), 8))
        return None, last

    def collect_account(self, acct: dict[str, str], plan: dict[str, Any], global_pages_remaining: int,
                        account_pages_remaining: int) -> dict[str, Any]:
        handle, uid = acct["handle"], str(acct["x_user_id"])
        out = {"handle": handle, "x_user_id": uid, "status": plan["status"],
               "continuation_pages_attempted": 0, "continuation_valid_pages": 0,
               "continuation_statuses": 0, "continuation_owner_mismatches": 0,
               "continuation_pages_with_order_anomalies": 0,
               "stop_reason": plan["status"]}
        if plan["next_page"] is None:
            return out
        cursor = plan["cursor"]
        page = int(plan["next_page"])
        seen_cursors = {cursor} if cursor else set()
        while page <= MAX_PAGES_PER_ACCOUNT and out["continuation_pages_attempted"] < account_pages_remaining:
            if self.timeline_pages >= global_pages_remaining:
                out["stop_reason"] = "global_page_ceiling"
                break
            self.timeline_pages += 1
            out["continuation_pages_attempted"] += 1
            payload, meta = self.request(acct, page, cursor)
            if payload is None:
                out["stop_reason"] = f"timeline_request_failed:{meta.get('error')}"
                break
            out["continuation_valid_pages"] += 1
            statuses = payload.get("results") or []
            out["continuation_statuses"] += len(statuses)
            page_times: list[datetime] = []
            owner_mismatch = False
            for status in statuses:
                if not isinstance(status, dict):
                    continue
                owner, _ = owner_id(status)
                if owner is None or owner != uid:
                    out["continuation_owner_mismatches"] += 1
                    owner_mismatch = True
                dt = parse_dt(status.get("created_timestamp") or status.get("created_at"))
                if dt:
                    page_times.append(dt)
            if owner_mismatch:
                out["stop_reason"] = "timeline_owner_id_validation_failed"
                break
            if len(page_times) > 1 and any(a < b for a, b in zip(page_times, page_times[1:])):
                # Preserve the anomaly in outcomes and continue pagination; this
                # does not prove the cursor chain is exhausted at the date bound.
                out["continuation_pages_with_order_anomalies"] += 1
            if statuses and len(page_times) == len(statuses) and max(page_times) < START_UTC:
                out["stop_reason"] = "reached_start_boundary"
                break
            next_cursor = ((payload.get("cursor") or {}).get("bottom")
                           if isinstance(payload.get("cursor"), dict) else None)
            if not next_cursor:
                out["stop_reason"] = ("empty_page_without_cursor_unverified" if not statuses
                                      else "timeline_exhausted_no_next_cursor")
                break
            next_cursor = str(next_cursor)
            if next_cursor == cursor or next_cursor in seen_cursors:
                out["stop_reason"] = "cursor_repeated"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            page += 1
            out["stop_reason"] = "continuing"
        else:
            if page > MAX_PAGES_PER_ACCOUNT:
                out["stop_reason"] = "per_account_page_ceiling"
            elif out["continuation_pages_attempted"] >= account_pages_remaining:
                out["stop_reason"] = "per_account_total_page_ceiling"
        print(f"{handle}: new_pages={out['continuation_pages_attempted']} stop={out['stop_reason']}", flush=True)
        return out


def reconcile(parent: Path, continuation_dir: Path, sample: list[dict[str, str]], cutoff: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    tweets_by_id: dict[tuple[str, str], dict[str, Any]] = {}
    identity_issues: list[dict[str, Any]] = []
    all_pages = parent / "raw"
    roots = [parent, continuation_dir]
    for acct in sample:
        handle, uid = acct["handle"], str(acct["x_user_id"])
        pages: list[tuple[int, Path, dict[str, Any]]] = []
        for root in roots:
            pages.extend(collect_pages(root, handle))
        # Parent page 1 and continuation page 2+ are disjoint; on a retried page,
        # only successful payloads enter collect_pages.
        pages.sort(key=lambda x: (x[0], x[1].name))
        # Pick one successful response per logical page; duplicate successful
        # attempts are counted but only the first payload is parsed.
        by_page: dict[int, tuple[Path, dict[str, Any]]] = {}
        for pageno, path, payload in pages:
            by_page.setdefault(pageno, (path, payload))
        rec: dict[str, Any] = {
            "handle": handle, "x_user_id": uid, "activity_stratum": acct.get("activity_stratum"),
            "profile_id_preflight_match": acct.get("profile_id_preflight_match"),
            "valid_timeline_pages": len(by_page), "statuses_returned": 0,
            "timeline_owner_id_mismatches": 0, "timeline_owner_id_missing": 0,
            "source_author_differs_from_timeline_owner": 0, "missing_timestamps": 0,
            "statuses_newer_than_fixed_cutoff": 0, "statuses_before_start": 0,
            "statuses_in_window_owner_verified": 0, "unique_tweets_in_window": 0,
            "duplicate_tweet_ids": 0, "earliest_in_window_utc": None,
            "latest_in_window_utc": None, "pagination_order_nonincreasing": True,
            "reached_start_boundary": False, "timeline_exhausted_no_cursor": False,
        }
        stop_reason = "no_successful_timeline_page"
        previous_page_last_time: datetime | None = None
        for pageno, (path, payload) in sorted(by_page.items()):
            statuses = payload.get("results") or []
            rec["statuses_returned"] += len(statuses)
            times: list[datetime] = []
            for status in statuses:
                if not isinstance(status, dict):
                    continue
                owner, author_id = owner_id(status)
                is_repost = isinstance(status.get("reposted_by"), dict)
                if owner is None:
                    rec["timeline_owner_id_missing"] += 1
                    identity_issues.append({"handle": handle, "x_user_id": uid,
                                            "tweet_id": status.get("id"), "issue": "missing_timeline_owner_id",
                                            "raw_file": str(path.relative_to(parent if parent in path.parents else continuation_dir))})
                    continue
                if owner != uid:
                    rec["timeline_owner_id_mismatches"] += 1
                    identity_issues.append({"handle": handle, "x_user_id": uid,
                                            "tweet_id": status.get("id"), "observed_timeline_owner_id": owner,
                                            "issue": "timeline_owner_id_mismatch",
                                            "raw_file": str(path.relative_to(parent if parent in path.parents else continuation_dir))})
                    continue
                if author_id and author_id != uid:
                    rec["source_author_differs_from_timeline_owner"] += 1
                dt = parse_dt(status.get("created_timestamp") or status.get("created_at"))
                if dt is None:
                    rec["missing_timestamps"] += 1
                    continue
                times.append(dt)
                if dt >= cutoff:
                    rec["statuses_newer_than_fixed_cutoff"] += 1
                    continue
                if dt < START_UTC:
                    rec["statuses_before_start"] += 1
                    continue
                rec["statuses_in_window_owner_verified"] += 1
                tweet_id = str(status.get("id") or "")
                if not tweet_id:
                    rec["missing_timestamps"] += 0
                    continue
                key = (uid, tweet_id)
                if key in tweets_by_id:
                    rec["duplicate_tweet_ids"] += 1
                    continue
                tweets_by_id[key] = normalize_status(acct, status, owner, author_id, dt, path, parent, continuation_dir)
                rec["unique_tweets_in_window"] += 1
                stamp = iso(dt)
                rec["earliest_in_window_utc"] = min(filter(None, [rec["earliest_in_window_utc"], stamp])) if rec["earliest_in_window_utc"] else stamp
                rec["latest_in_window_utc"] = max(filter(None, [rec["latest_in_window_utc"], stamp])) if rec["latest_in_window_utc"] else stamp
            if len(times) > 1 and any(a < b for a, b in zip(times, times[1:])):
                rec["pagination_order_nonincreasing"] = False
            if times and previous_page_last_time is not None and times[0] > previous_page_last_time:
                rec["pagination_order_nonincreasing"] = False
            if statuses and len(times) == len(statuses) and times:
                previous_page_last_time = times[-1]
            elif statuses:
                previous_page_last_time = None
            if statuses and len(times) == len(statuses) and max(times) < START_UTC:
                rec["reached_start_boundary"] = True
                stop_reason = "reached_start_boundary"
                break
            cursor_obj = payload.get("cursor") if isinstance(payload.get("cursor"), dict) else {}
            if pageno == max(by_page):
                if not cursor_obj.get("bottom"):
                    if statuses:
                        rec["timeline_exhausted_no_cursor"] = True
                        stop_reason = "timeline_exhausted_no_cursor"
                    else:
                        stop_reason = "empty_page_without_cursor_unverified"
                else:
                    # Empty pages with a bottom cursor are intermediate or
                    # otherwise ambiguous, never proof of timeline exhaustion.
                    stop_reason = "cursor_available_but_target_boundary_not_reached"
        rec["stop_reason"] = stop_reason
        rec["pagination_to_target_boundary"] = bool(rec["reached_start_boundary"] or rec["timeline_exhausted_no_cursor"])
        rec["truncated_or_uncertain"] = not rec["pagination_to_target_boundary"]
        if rec["timeline_owner_id_mismatches"] or rec["timeline_owner_id_missing"]:
            rec["pagination_to_target_boundary"] = False
            rec["truncated_or_uncertain"] = True
            rec["stop_reason"] = "timeline_owner_validation_failed"
        if not rec["pagination_order_nonincreasing"]:
            rec["pagination_to_target_boundary"] = False
            rec["truncated_or_uncertain"] = True
            rec["stop_reason"] = "pagination_order_violation"
        if rec["missing_timestamps"]:
            rec["pagination_to_target_boundary"] = False
            rec["truncated_or_uncertain"] = True
            rec["stop_reason"] = "missing_timestamp_validation_failed"
        coverage.append(rec)
    return coverage, list(tweets_by_id.values()), {"identity_issues": identity_issues}


def normalize_status(acct: dict[str, str], status: dict[str, Any], timeline_owner: str,
                     source_author_id: str | None, created: datetime, raw_path: Path,
                     parent: Path, continuation_dir: Path) -> dict[str, Any]:
    reposted = isinstance(status.get("reposted_by"), dict)
    reply = isinstance(status.get("replying_to"), dict)
    quote = isinstance(status.get("quote"), dict)
    post_kind = ("repost" if reposted else "reply_quote" if reply and quote else
                 "reply" if reply else "quote" if quote else "original")
    author = status.get("author") if isinstance(status.get("author"), dict) else {}
    replying_to = status.get("replying_to") if isinstance(status.get("replying_to"), dict) else {}
    quoted = status.get("quote") if isinstance(status.get("quote"), dict) else {}
    quoted_author = quoted.get("author") if isinstance(quoted.get("author"), dict) else {}
    raw_relative = str(raw_path.relative_to(parent)) if parent in raw_path.parents else str(raw_path.relative_to(continuation_dir))
    return {
        "queried_user_id": str(acct["x_user_id"]),
        "queried_handle_at_collection": acct["handle"],
        "timeline_owner_id_verified": timeline_owner,
        "tweet_id": str(status.get("id") or ""),
        "created_at_utc": iso(created),
        "post_kind": post_kind,
        "is_repost": reposted,
        "is_reply": reply,
        "is_quote": quote,
        "source_author_id": source_author_id,
        "source_author_handle": author.get("screen_name"),
        # Never treat original-source retweet text as text authored by the queried account.
        "authored_text": None if reposted else status.get("text"),
        "returned_text": status.get("text"),
        "reposted_by_id": (status.get("reposted_by") or {}).get("id") if reposted else None,
        "replying_to_tweet_id": replying_to.get("id"),
        "quoted_tweet_id": quoted.get("id"),
        "quoted_author_id": quoted_author.get("id"),
        "quoted_author_handle": quoted_author.get("screen_name"),
        "raw_response_file": raw_relative,
    }


def continuation_manifest_for_run(output: Path, parent: Path,
                                  parent_manifest: dict[str, Any],
                                  sample: list[dict[str, str]], cutoff: datetime,
                                  prior_pages: int, *, persist: bool) -> dict[str, Any]:
    parent_manifest_path = parent / "run_manifest.json"
    sample_path = parent / "sample_manifest.csv"
    expected = {
        "parent_run_id": parent_manifest.get("run_id"),
        "parent_run_manifest_sha256": file_sha256(parent_manifest_path),
        "sample_manifest_sha256": file_sha256(sample_path),
        "target_start_inclusive_utc": iso(START_UTC),
        "target_end_exclusive_utc": iso(cutoff),
        "account_count": 12,
        "account_ids_sha256": hashlib.sha256(
            "\n".join(sorted(str(row["x_user_id"]) for row in sample)).encode("utf-8")
        ).hexdigest(),
    }
    path = output / "continuation_manifest.json"
    if path.exists():
        manifest = read_json(path)
        for key in ("parent_run_id", "target_start_inclusive_utc", "target_end_exclusive_utc", "account_count"):
            if manifest.get(key) != expected[key]:
                raise ValueError(f"continuation manifest mismatch for {key}; refusing to resume")
        for key in ("parent_run_manifest_sha256", "sample_manifest_sha256", "account_ids_sha256"):
            if manifest.get(key) and manifest[key] != expected[key]:
                raise ValueError(f"continuation manifest source fingerprint mismatch for {key}; refusing to resume")
        manifest.update(expected)
    else:
        manifest = {
            "run_id": output.name,
            **expected,
            "created_at_utc": iso(datetime.now(timezone.utc)),
            "authorization_basis": "User confirmed in this conversation that FxEmbed collection is authorized; no authorization document copied into this artifact.",
            "source": "FxEmbed public v2 timeline endpoint; stable X user ID path; no X API, login, or follower/following endpoint used.",
            "parent_run_is_immutable": True,
            "allowlist_inherited_unchanged": True,
            "new_account_ids_added": 0,
            "identity_semantics": "For reposts, timeline owner is reposted_by.id and source author is author.id; for non-reposts, timeline owner is author.id.",
            "content_semantics": "Retweet source text is not treated as authored_text; raw responses are retained locally.",
            "source_conditions_note": "User authorization to use FxEmbed recorded. FxEmbed API docs describe endpoints/pagination but do not themselves establish X downstream republication rights; X terms must be checked separately before public release.",
        }
    manifest.update({
        "prior_timeline_logical_pages": prior_pages,
        "global_page_limit_total_including_parent": MAX_TIMELINE_PAGES_TOTAL,
        "max_new_timeline_pages": max(0, MAX_TIMELINE_PAGES_TOTAL - prior_pages),
        "max_total_pages_per_account": MAX_PAGES_PER_ACCOUNT,
        "request_delay_seconds": REQUEST_DELAY_SECONDS,
        "max_attempts_per_logical_page_cumulative": MAX_RETRIES,
        "max_http_attempts_cumulative": MAX_HTTP_ATTEMPTS_TOTAL,
        "attempt_budget_ledger": "attempt_budget.jsonl",
    })
    if persist:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-run", type=Path, required=True)
    parser.add_argument("--audit-only", action="store_true", help="read-only reconciliation and continuation plan; writes nothing")
    parser.add_argument("--resume", action="store_true", help="make cumulatively bounded cursor requests for only the fixed 12-account sample")
    args = parser.parse_args()
    if args.audit_only == args.resume:
        parser.error("choose exactly one of --audit-only or --resume")
    parent = args.parent_run.resolve()
    parent_manifest, sample, cutoff = load_parent(parent)
    output = parent / "continuation_20260924_fixed_window"
    # Complete read-only preflight before creating a lock, plan, manifest, or
    # migrated ledger. A malformed/over-budget history must leave disk untouched.
    prior_requests_raw = load_request_log(parent) + load_request_log(output)
    prior_requests, legacy_id_backfills = bind_legacy_request_ids(prior_requests_raw, sample)
    prior_reservations = load_attempt_budget(output / "attempt_budget.jsonl")
    budget_audit = audit_attempt_budget(prior_requests, prior_reservations)
    ledger_path = output / "attempt_budget.jsonl"
    if ledger_path.exists():
        request_ids = {str(row.get("request_id", "")).strip() for row in prior_requests}
        reservation_ids = {str(row.get("request_id", "")).strip() for row in prior_reservations}
        missing_reservations = sorted(rid for rid in request_ids if rid and rid not in reservation_ids)
        if missing_reservations:
            budget_audit["history_issues"].append(
                f"attempt ledger lacks reservations for logged request_ids: {missing_reservations}"
            )
            budget_audit["within_budget"] = False
    if args.resume and not budget_audit["within_budget"]:
        raise RuntimeError(f"attempt history/budget preflight failed; no requests issued: {budget_audit}")

    # Resume calls are serialized. The flock is automatically released if the
    # process exits or is interrupted; audit-only never creates the lock file.
    lock_handle = None
    if args.resume:
        output.mkdir(parents=True, exist_ok=True)
        lock_handle = (output / ".resume.lock").open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_handle.close()
            raise RuntimeError("another continuation resume is active; refusing concurrent requests") from exc

    try:
        plans = [plan_account(parent, output, acct, prior_requests) for acct in sample]
        prior_pages = sum(p["prior_logical_pages"] for p in plans)
        manifest = continuation_manifest_for_run(
            output, parent, parent_manifest, sample, cutoff, prior_pages, persist=args.resume
        )

        if args.resume:
            plan_path = output / "continuation_plan.csv"
            with plan_path.open("w", newline="", encoding="utf-8") as f:
                fields = ["handle", "x_user_id", "activity_stratum", "status", "next_page", "cursor",
                          "prior_logical_pages", "prior_successful_pages", "cumulative_http_attempts_for_page"]
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                by_handle = {r["handle"].casefold(): r for r in sample}
                for plan in plans:
                    w.writerow({**plan, "activity_stratum": by_handle[plan["handle"].casefold()].get("activity_stratum")})

            continuation = Continuation(output, cutoff, prior_requests)
            max_new = max(0, MAX_TIMELINE_PAGES_TOTAL - prior_pages)
            outcomes: list[dict[str, Any]] = []
            try:
                for acct, plan in zip(sample, plans):
                    if plan["status"] in {"already_reached_start_boundary", "already_exhausted_no_cursor",
                                          "terminal_retry_budget_exhausted", "identity_validation_failed",
                                          "terminal_coverage_requires_review"}:
                        outcomes.append({"handle": acct["handle"], "x_user_id": acct["x_user_id"],
                                         "status": plan["status"], "continuation_pages_attempted": 0,
                                         "continuation_valid_pages": 0, "continuation_statuses": 0,
                                         "continuation_owner_mismatches": 0, "stop_reason": plan["status"]})
                        continue
                    prior_for_acct = plan["prior_logical_pages"]
                    acct_remaining = max(0, MAX_PAGES_PER_ACCOUNT - prior_for_acct)
                    outcomes.append(continuation.collect_account(acct, plan, max_new, acct_remaining))
            except KeyboardInterrupt:
                print("interrupted; raw pages, attempt reservations, request/error/cursor logs are preserved", file=sys.stderr)
            (output / "continuation_outcomes.json").write_text(json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        coverage, tweets, diagnostics = reconcile(parent, output, sample, cutoff)
        summary = {
            "parent_run_id": parent_manifest.get("run_id"),
            "target_start_inclusive_utc": iso(START_UTC),
            "target_end_exclusive_utc": iso(cutoff),
            "accounts_in_original_allowlist": len(sample),
            "new_account_ids_added": 0,
            "accounts_with_pagination_to_target_boundary": sum(bool(r["pagination_to_target_boundary"]) for r in coverage),
            "accounts_truncated_or_uncertain": sum(bool(r["truncated_or_uncertain"]) for r in coverage),
            "unique_owner_verified_tweets_in_window": len(tweets),
            "post_kind_counts": dict(sorted(Counter(t["post_kind"] for t in tweets).items())),
            "identity_issue_count": len(diagnostics["identity_issues"]),
            "continuation_http_attempts_logged": len(load_request_log(output)),
            "max_http_attempts_cumulative": MAX_HTTP_ATTEMPTS_TOTAL,
            "attempt_budget_audit": budget_audit,
            "legacy_request_ids_resolved_from_frozen_sample": legacy_id_backfills,
            "raw_parent_untouched": True,
        }
        print(json.dumps({"summary": summary, "manifest": manifest}, ensure_ascii=False, indent=2))
        if args.audit_only:
            print("PLAN", json.dumps([
                {k: p.get(k) for k in ("handle", "status", "terminal_integrity_issue", "next_page", "prior_logical_pages",
                                        "prior_successful_pages", "cumulative_http_attempts_for_page")}
                for p in plans
            ], ensure_ascii=False))
        else:
            fields = list(coverage[0]) if coverage else []
            with (output / "combined_coverage.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader(); w.writerows(coverage)
            write_jsonl(output / "combined_tweets_in_window.jsonl", tweets)
            write_jsonl(output / "identity_issues.jsonl", diagnostics["identity_issues"])
            (output / "combined_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    finally:
        if lock_handle is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
