#!/usr/bin/env python3
"""Bounded, resumable timeline pilot for profile-evidence candidates.

Raw pages and request SHA-256 hashes are archived. Reposts are treated as
observations with unknown action time, never as dated social interactions.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
from contextlib import contextmanager
import hashlib
import json
import os
import uuid
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from fx_authorized_continue import owner_id, parse_dt, normalize_status


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 24, 17, 24, 10, tzinfo=timezone.utc)
HARD_MAX_ACCOUNTS = 10
HARD_MAX_PAGES_PER_ACCOUNT = 4
HARD_MAX_HTTP_ATTEMPTS_TOTAL = 50
MIN_HTTP_INTERVAL_SECONDS = 1.0
PROXY = "http://10.63.0.72:7890"
HEADERS = {"User-Agent": "exgraph-research/0.4 (authorized bounded academic collection)",
           "Accept": "application/json"}


def atomic_write_bytes(path: Path, body: bytes) -> None:
    """Durably replace one run artifact so a process crash cannot leave a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def append_jsonl(path: Path, value: dict) -> None:
    """Atomically append a small audit row (run caps keep these ledgers bounded)."""
    previous = path.read_bytes() if path.exists() else b""
    if previous and not previous.endswith(b"\n"):
        raise ValueError(f"refusing to append to a truncated JSONL ledger: {path}")
    line = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(path, previous + line)


def validate_account_allowlist(source: Path, count_limit: int) -> tuple[list[dict], str]:
    """Load only explicitly adjudicated account-side confirmations.

    This deliberately has no candidate-pool fallback or automatic sampling.
    Required CSV columns: handle_at_profile_audit, x_user_id, verification_status,
    pair_id, evidence_date, evidence_url, evidence_note, wallet_address.
    """
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    import io
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    required = {"handle_at_profile_audit", "x_user_id", "verification_status",
                "pair_id", "evidence_date", "evidence_url", "evidence_note",
                "wallet_address"}
    if not rows or not required.issubset(rows[0].keys()):
        raise ValueError(f"allowlist must contain rows and columns: {sorted(required)}")
    if len(rows) > count_limit:
        raise ValueError(f"allowlist has {len(rows)} accounts; limit is {count_limit}")
    seen_ids, seen_handles, queue = set(), set(), []
    for row in rows:
        handle = row["handle_at_profile_audit"].strip().lstrip("@")
        uid = row["x_user_id"].strip()
        if row["verification_status"].strip() != "account_confirms":
            raise ValueError(f"allowlist row is not account_confirms: {uid or handle}")
        if not uid.isdigit() or not handle:
            raise ValueError("allowlist requires a stable numeric X ID and handle")
        if uid in seen_ids or handle.casefold() in seen_handles:
            raise ValueError("allowlist contains duplicate X IDs or handles")
        seen_ids.add(uid); seen_handles.add(handle.casefold())
        for field in ("pair_id", "evidence_date", "evidence_url", "evidence_note", "wallet_address"):
            if not row[field].strip():
                raise ValueError(f"allowlist row {uid} missing {field}")
        queue.append({**row, "handle_at_profile_audit": handle, "x_user_id": uid})
    return queue, digest


def frozen_run_manifest(queue: list[dict], allowlist_sha256: str,
                        max_pages: int, max_attempts: int) -> dict:
    return {"schema": "ens-x-confirmed-timeline-pilot-v1",
            "allowlist_sha256": allowlist_sha256,
            "accounts": queue,
            "window_start_utc": START.isoformat(),
            "window_end_exclusive_utc": END.isoformat(),
            "max_accounts": len(queue),
            "max_pages_per_account": max_pages,
            "max_http_attempts_total": max_attempts,
            "max_attempts_per_page": 2,
            "minimum_http_interval_seconds": MIN_HTTP_INTERVAL_SECONDS}


def audit_persisted_budget(out: Path, max_attempts: int) -> None:
    budget_path = out / "attempt_budget.jsonl"
    rows = []
    if budget_path.exists():
        for lineno, line in enumerate(budget_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"damaged attempt ledger line {lineno}") from exc
            if (not isinstance(row, dict) or not row.get("request_id")
                    or not str(row.get("x_user_id", "")).isdigit()
                    or not str(row.get("page", "")).isdigit() or int(row["page"]) < 1):
                raise ValueError(f"invalid attempt reservation at line {lineno}")
            rows.append(row)
    ids = [str(r["request_id"]) for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate request IDs in attempt ledger")
    if len(rows) > max_attempts:
        raise ValueError("persisted attempt ledger exceeds frozen global budget")
    page_counts = Counter((str(r["x_user_id"]), int(r["page"]),
                           "" if r.get("cursor_in") is None else str(r["cursor_in"])) for r in rows)
    if any(n > 2 for n in page_counts.values()):
        raise ValueError("persisted attempt ledger exceeds two attempts for a logical page")
    request_path = out / "requests.jsonl"
    if request_path.exists():
        for lineno, line in enumerate(request_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"damaged request log line {lineno}") from exc
            if not isinstance(row, dict) or row.get("request_id") not in set(ids):
                raise ValueError(f"request log line {lineno} has no budget reservation")


@contextmanager
def exclusive_run_lock(out: Path):
    """Prevent two collectors from racing on the same frozen run directory."""
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    lock_path = out.with_name(f".{out.name}.collector.lock")
    lock = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another collector holds run lock: {lock_path}") from exc
        yield
    finally:
        lock.close()


def prepare_run(out: Path, allowlist: Path, max_accounts: int,
                max_pages: int, max_attempts: int, resume: bool) -> list[dict]:
    """Fail closed on legacy candidate batches or any frozen-parameter drift."""
    if (max_accounts < 1 or max_pages < 1 or max_attempts < 1
            or max_accounts > HARD_MAX_ACCOUNTS
            or max_pages > HARD_MAX_PAGES_PER_ACCOUNT
            or max_attempts > HARD_MAX_HTTP_ATTEMPTS_TOTAL):
        raise ValueError("budgets must be positive and within hard caps: 10 accounts, 4 pages/account, 50 HTTP attempts")
    manifest_path = out / "run_manifest.json"
    legacy_queue = out / "pilot_queue.json"
    if legacy_queue.exists() and not manifest_path.exists():
        raise ValueError("legacy auto-candidate batch cannot be resumed; use a new output directory")
    queue, allowlist_hash = validate_account_allowlist(allowlist, max_accounts)
    expected = frozen_run_manifest(queue, allowlist_hash, max_pages, max_attempts)
    if out.exists():
        audit_persisted_budget(out, max_attempts)
    if manifest_path.exists():
        if not resume:
            raise ValueError("output already has a run manifest; pass --resume to audit exact frozen inputs")
        actual = json.loads(manifest_path.read_text(encoding="utf-8"))
        if actual != expected:
            raise ValueError("resume refused: allowlist, account IDs, window, or budget differs from frozen manifest")
    else:
        if resume:
            raise ValueError("resume refused: frozen run manifest is missing")
        out.mkdir(parents=True, exist_ok=True)
        if any(out.iterdir()):
            raise ValueError("new run output directory must be empty")
        atomic_write_bytes(manifest_path, (json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2)+"\n").encode("utf-8"))
    return queue


def reserve_http_attempt(budget_path: Path, uid: str, page: int, cursor: str | None,
                         max_attempts_total: int,
                         minimum_interval_seconds: float = 0.0) -> dict:
    """Atomically persist a budget reservation before any network call."""
    budget_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = budget_path.with_suffix(budget_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows = []
        if budget_path.exists():
            for lineno, line in enumerate(budget_path.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"damaged attempt ledger line {lineno}") from exc
                if (not isinstance(row, dict) or not row.get("request_id")
                        or not str(row.get("x_user_id", "")).isdigit()
                        or not str(row.get("page", "")).isdigit()
                        or int(row.get("page", 0)) < 1):
                    raise ValueError(f"invalid attempt reservation at line {lineno}")
                rows.append(row)
        ids = [r["request_id"] for r in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate request IDs in attempt ledger")
        if len(rows) >= max_attempts_total:
            raise RuntimeError("global HTTP attempt budget exhausted")
        if minimum_interval_seconds < 0:
            raise ValueError("minimum HTTP interval cannot be negative")
        key = (uid, int(page), "" if cursor is None else str(cursor))
        same_page = [(str(r["x_user_id"]), int(r["page"]), str(r.get("cursor_in") or ""))
                     for r in rows]
        if same_page.count(key) >= 2:
            raise RuntimeError("per-page HTTP attempt limit (2) exhausted")
        if rows and minimum_interval_seconds:
            previous = rows[-1].get("reserved_at_utc")
            if not previous:
                raise ValueError("previous reservation lacks reserved_at_utc; refusing unpaced request")
            try:
                previous_dt = datetime.fromisoformat(str(previous).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("previous reservation has invalid reserved_at_utc") from exc
            if previous_dt.tzinfo is None:
                raise ValueError("previous reservation timestamp is not timezone-aware")
            remaining = minimum_interval_seconds - (datetime.now(timezone.utc) - previous_dt).total_seconds()
            if remaining > 0:
                time.sleep(remaining)
        reservation = {"request_id": str(uuid.uuid4()), "x_user_id": uid,
                       "page": page, "cursor_in": cursor,
                       "reserved_at_utc": datetime.now(timezone.utc).isoformat()}
        append_jsonl(budget_path, reservation)
        return reservation


def request_page(session: requests.Session, handle: str, cursor: str | None,
                 page: int, raw_dir: Path, request_log: Path, uid: str,
                 budget_path: Path, max_attempts_total: int) -> tuple[dict | None, str | None]:
    url = f"https://api.fxtwitter.com/2/profile/{quote(handle, safe='@:_-')}/statuses"
    params = {"cursor": cursor} if cursor else None
    for attempt in range(1, 3):
        reservation = reserve_http_attempt(budget_path, uid, page, cursor, max_attempts_total,
                                           MIN_HTTP_INTERVAL_SECONDS)
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            resp = session.get(url, params=params, headers=HEADERS,
                               proxies={"http": PROXY, "https": PROXY},
                               timeout=(15, 45), allow_redirects=False)
            body = resp.content
            suffix = "body" if resp.status_code == 200 else f"http_{resp.status_code}.body"
            raw = raw_dir / f"page_{page:04d}_attempt_{reservation['request_id']}.{suffix}"
            atomic_write_bytes(raw, body)
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            ok = (resp.status_code == 200 and isinstance(payload, dict)
                  and payload.get("code") == 200 and isinstance(payload.get("results"), list))
            append_jsonl(request_log, {
                "request_id": reservation["request_id"], "x_user_id": uid,
                "handle": handle, "page": page, "attempt": attempt,
                "requested_at_utc": stamp, "cursor_in": cursor,
                "cursor_out": (((payload.get("cursor") or {}).get("bottom"))
                               if ok and isinstance(payload.get("cursor"), dict) else None),
                "http_status": resp.status_code,
                "api_code": payload.get("code") if isinstance(payload, dict) else None,
                "raw_file": str(raw), "raw_sha256": hashlib.sha256(body).hexdigest(),
                "result_count": len(payload["results"]) if ok else None,
                "error": None if ok else "invalid_or_error_response",
            })
            if ok:
                return payload, str(raw)
            if resp.status_code not in (429, 500, 502, 503, 504):
                return None, None
        except requests.RequestException as exc:
            append_jsonl(request_log, {"request_id": reservation["request_id"], "x_user_id": uid,
                                       "handle": handle, "page": page, "attempt": attempt,
                                       "requested_at_utc": stamp, "cursor_in": cursor,
                                       "error": type(exc).__name__})
        time.sleep(attempt * 5)
    return None, None


def archived_page(request_log: Path, raw_dir: Path, uid: str, page: int,
                  cursor_in: str | None) -> tuple[dict, str] | None:
    """Return a page only when its durable request record binds it to this cursor.

    Raw files without a matching successful request-log row are deliberately
    ignored. Multiple successful responses for the same page/cursor are
    ambiguous (for example, a crash after logging but before checkpointing),
    so fail closed rather than silently choosing one.
    """
    if not request_log.exists():
        return None
    rows = []
    for lineno, line in enumerate(request_log.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f"damaged request log line {lineno}") from exc
        if str(row.get("x_user_id", "")) != str(uid) or int(row.get("page", 0) or 0) != page:
            continue
        logged_cursor = row.get("cursor_in")
        if (None if logged_cursor in (None, "") else str(logged_cursor)) != cursor_in:
            raise RuntimeError(f"page {page} for {uid} is logged against an unexpected cursor")
        if (row.get("http_status") == 200 and row.get("api_code") == 200
                and not row.get("error") and row.get("raw_file")):
            rows.append(row)
    if not rows:
        return None
    if len(rows) != 1:
        raise RuntimeError(f"ambiguous successful archived pages for {uid} page {page}")
    row = rows[0]
    path = Path(row["raw_file"])
    if not path.is_absolute():
        path = raw_dir.parent.parent / path
    # request_page records the complete path. For old relative records, accept
    # only paths that resolve inside this run's raw directory.
    try:
        path.resolve().relative_to(raw_dir.resolve())
    except ValueError as exc:
        raise RuntimeError("archived response path escapes the account raw directory") from exc
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"logged archived response is missing: {path}") from exc
    digest = hashlib.sha256(body).hexdigest()
    if digest != row.get("raw_sha256"):
        raise RuntimeError(f"archived response hash mismatch: {path}")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise RuntimeError(f"archived response is not valid JSON: {path}") from exc
    if not isinstance(payload, dict) or payload.get("code") != 200 or not isinstance(payload.get("results"), list):
        raise RuntimeError(f"archived response has an invalid API envelope: {path}")
    cursor_out = (payload.get("cursor") or {}).get("bottom") if isinstance(payload.get("cursor"), dict) else None
    cursor_out = None if cursor_out is None else str(cursor_out)
    logged_out = row.get("cursor_out")
    logged_out = None if logged_out is None else str(logged_out)
    if cursor_out != logged_out:
        raise RuntimeError(f"archived response cursor does not match request log: {path}")
    return payload, str(path)


def collect_account(session: requests.Session, acct: dict, out: Path, max_pages: int,
                    delay: float, max_attempts_total: int = 1) -> dict:
    handle, uid = acct["handle_at_profile_audit"], acct["x_user_id"]
    raw_dir = out / "raw" / handle.lower()
    raw_dir.mkdir(parents=True, exist_ok=True)
    request_log = out / "requests.jsonl"
    cursor = None
    seen_cursors = set()
    rec = {"handle": handle, "x_user_id": uid, "pages": 0, "statuses": 0,
           "target_start_inclusive_utc": START.isoformat(),
           "target_end_exclusive_utc": END.isoformat(),
           "authored_in_window": 0, "reposts_untimed": 0,
           "owner_mismatches": 0, "missing_timestamps": 0,
           "stop_reason": "page_ceiling", "timeline_complete": False,
           "window_boundary_reached": False, "page_ceiling_reached": False,
           "coverage_status": "unknown"}
    for page in range(1, max_pages + 1):
        archived = archived_page(request_log, raw_dir, uid, page, cursor)
        payload, raw_path = archived if archived is not None else (None, None)
        if payload is None:
            payload, raw_path = request_page(session, handle, cursor, page, raw_dir, request_log,
                                             uid, out / "attempt_budget.jsonl", max_attempts_total)
            time.sleep(delay)
        rec["pages"] += 1
        if payload is None:
            rec["stop_reason"] = "request_or_payload_failed"
            break
        statuses = payload["results"]
        rec["statuses"] += len(statuses)
        page_times = []
        for status in statuses:
            if not isinstance(status, dict):
                rec["owner_mismatches"] += 1
                continue
            owner, _ = owner_id(status)
            if owner != uid:
                rec["owner_mismatches"] += 1
                continue
            created = parse_dt(status.get("created_timestamp") or status.get("created_at"))
            if created is None:
                rec["missing_timestamps"] += 1
                continue
            is_repost = isinstance(status.get("reposted_by"), dict)
            if is_repost:
                rec["reposts_untimed"] += 1
            else:
                # A repost's created_at is the source post time, not the
                # timeline owner's repost action time; never use it to stop.
                page_times.append(created)
                if START <= created < END:
                    rec["authored_in_window"] += 1
        if rec["owner_mismatches"]:
            rec["stop_reason"] = "timeline_owner_mismatch"
            rec["coverage_status"] = "unknown_owner_mismatch"
            break
        if page_times and min(page_times) < START:
            rec["window_boundary_reached"] = True
            rec["stop_reason"] = "target_window_boundary_reached"
            rec["coverage_status"] = "boundary_observed_source_completeness_unverified"
            break
        next_cursor = ((payload.get("cursor") or {}).get("bottom")
                       if isinstance(payload.get("cursor"), dict) else None)
        if not statuses or not next_cursor:
            rec["stop_reason"] = "cursor_exhausted"
            rec["coverage_status"] = "endpoint_exhausted_before_boundary"
            break
        next_cursor = str(next_cursor)
        if next_cursor == cursor or next_cursor in seen_cursors:
            rec["stop_reason"] = "cursor_repeated"
            rec["coverage_status"] = "unknown_cursor_repeated"
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    if rec["stop_reason"] == "page_ceiling":
        rec["page_ceiling_reached"] = True
        rec["coverage_status"] = "incomplete_page_ceiling_before_boundary"
    elif rec["stop_reason"] == "request_or_payload_failed":
        rec["coverage_status"] = "incomplete_request_or_payload_failure"
    return rec


def normalize_archived(out: Path, queue: list[dict]) -> dict:
    records = []
    seen = set()
    for account in queue:
        handle, uid = account["handle_at_profile_audit"], account["x_user_id"]
        acct = {"handle": handle, "x_user_id": uid}
        raw_dir = out / "raw" / handle.lower()
        for path in sorted(raw_dir.glob("page_*.body")):
            try:
                payload = json.loads(path.read_bytes())
            except (OSError, ValueError):
                continue
            if payload.get("code") != 200 or not isinstance(payload.get("results"), list):
                continue
            for status in payload["results"]:
                if not isinstance(status, dict):
                    continue
                owner, author_id = owner_id(status)
                if owner != uid:
                    continue
                created = parse_dt(status.get("created_timestamp") or status.get("created_at"))
                if not created or created >= END:
                    continue
                repost = isinstance(status.get("reposted_by"), dict)
                if not repost and created < START:
                    continue
                tweet_id = str(status.get("id") or "")
                key = (uid, tweet_id)
                if not tweet_id or key in seen:
                    continue
                seen.add(key)
                value = normalize_status(acct, status, owner, author_id, created, path, out, out)
                value["repost_action_time_known"] = not repost
                records.append(value)
    path = out / "normalized_observed_statuses.jsonl"
    normalized = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
    atomic_write_bytes(path, normalized.encode("utf-8"))
    return {"normalized_records": len(records),
            "authored_in_window": sum(not r["is_repost"] for r in records),
            "repost_observations_untimed": sum(r["is_repost"] for r in records)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist", type=Path, required=True,
                        help="CSV of individually account-side-confirmed wallet/X links")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-accounts", type=int, required=True)
    parser.add_argument("--max-pages-per-account", type=int, required=True)
    parser.add_argument("--max-http-attempts-total", type=int, required=True)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.delay_seconds < MIN_HTTP_INTERVAL_SECONDS:
        parser.error(f"--delay-seconds must be at least {MIN_HTTP_INTERVAL_SECONDS:g}")
    out = args.out.resolve()
    with exclusive_run_lock(out):
        run_pilot(args, out)


def run_pilot(args: argparse.Namespace, out: Path) -> None:
    queue = prepare_run(out, args.allowlist.resolve(), args.max_accounts,
                        args.max_pages_per_account, args.max_http_attempts_total, args.resume)
    coverage_path = out / "coverage.jsonl"
    completed = {}
    allowed_ids = {a["x_user_id"] for a in queue}
    if coverage_path.is_file():
        for lineno, line in enumerate(coverage_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"damaged coverage ledger line {lineno}") from exc
            uid = row.get("x_user_id") if isinstance(row, dict) else None
            if uid not in allowed_ids:
                raise ValueError("coverage ledger contains an ID outside frozen allowlist")
            if uid in completed:
                raise ValueError("duplicate account in coverage ledger")
            completed[uid] = row
    session = requests.Session()
    failures = 0
    for i, acct in enumerate(queue, 1):
        if acct["x_user_id"] in completed:
            continue
        rec = collect_account(session, acct, out, args.max_pages_per_account, args.delay_seconds,
                               args.max_http_attempts_total)
        append_jsonl(coverage_path, rec)
        print(i, acct["handle_at_profile_audit"], rec["pages"], rec["authored_in_window"], rec["stop_reason"], flush=True)
        failures = failures + 1 if rec["stop_reason"] == "request_or_payload_failed" else 0
        if failures >= 10:
            raise RuntimeError("Circuit breaker: ten consecutive failed accounts")
    summary = normalize_archived(out, queue)
    coverage = [json.loads(line) for line in coverage_path.read_text(encoding="utf-8").splitlines()]
    summary.update({"queue_accounts": len(queue), "covered_accounts": len(coverage),
                    "coverage_stop_reasons": dict(Counter(r["stop_reason"] for r in coverage)),
                    "fixed_window_start_utc": START.isoformat(),
                    "fixed_window_end_exclusive_utc": END.isoformat(),
                    "per_account_page_ceiling": args.max_pages_per_account,
                    "max_http_attempts_total": args.max_http_attempts_total,
                    "known_limit": "Repost action time is unavailable; page ceiling never proves full history."})
    atomic_write_bytes(out / "summary.json", (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
