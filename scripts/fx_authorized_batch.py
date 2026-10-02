#!/usr/bin/env python3
"""Bounded FxEmbed timeline collection for account-side-confirmed stable X IDs.

This runner intentionally does not call follower/following endpoints. It queries
only the fixed account_confirms allowlist, verifies each handle still resolves
to its recorded stable X user ID, archives every raw response and cursor/error,
and stops at the configured UTC time window or hard page ceilings.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
ARTIFACTS = BASE / "artifacts" / "ens_x_crosswalk"
SAMPLE = ARTIFACTS / "verification_sample_v2_filled.csv"
PROFILES = ARTIFACTS / "fx_profiles_parsed.jsonl"
API = "https://api.fxtwitter.com/2/profile/{handle}/{kind}"
START_UTC = datetime(2026, 1, 1, tzinfo=timezone.utc)
PAGE_SIZE_ASSUMED = 20  # observed in the existing pilot; actual page length is logged
MAX_PAGES_PER_ACCOUNT = 250
MAX_TIMELINE_PAGES_TOTAL = 1200
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3
USER_AGENT = "exgraph-research/0.2 (authorized bounded academic collection)"


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def parse_timestamp(item: dict[str, Any]) -> datetime | None:
    value = item.get("created_timestamp")
    if value is not None:
        try:
            n = int(value)
            if n > 10**12:
                n //= 1000
            return datetime.fromtimestamp(n, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    value = item.get("created_at")
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "account"


def load_profiles() -> dict[str, str]:
    profiles: dict[str, str] = {}
    if not PROFILES.exists():
        return profiles
    for line in PROFILES.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        handle = str(rec.get("handle") or "").lstrip("@").casefold()
        user_id = str(rec.get("fx_user_id") or "")
        if handle and user_id:
            profiles[handle] = user_id
    return profiles


def load_allowlist() -> list[dict[str, Any]]:
    if not SAMPLE.exists():
        raise FileNotFoundError(f"required verification file missing: {SAMPLE}")
    df = pd.read_csv(SAMPLE, dtype={"x_user_id": "string"})
    required = {"pair_id", "handle", "x_user_id", "verification_status", "status", "activity", "events_2026"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"verification sample missing columns: {sorted(missing)}")
    selected = df[
        df["verification_status"].astype(str).eq("account_confirms")
        & df["x_user_id"].notna()
        & df["x_user_id"].astype(str).str.strip().ne("")
        & df["handle"].notna()
    ].copy()
    if selected.empty:
        raise ValueError("no account_confirms rows with stable X IDs")

    profiles = load_profiles()
    output: list[dict[str, Any]] = []
    for user_id, group in selected.groupby(selected["x_user_id"].astype(str), sort=False):
        handles = sorted({str(x).strip().lstrip("@") for x in group["handle"].dropna() if str(x).strip()})
        if len({h.casefold() for h in handles}) != 1:
            raise ValueError(f"stable user ID {user_id} maps to multiple handles in the confirmed sample: {handles}")
        handle = handles[0]
        matched_profile_id = profiles.get(handle.casefold())
        if matched_profile_id != user_id:
            raise ValueError(
                f"existing FxEmbed identity audit mismatch for @{handle}: sample={user_id}, profile={matched_profile_id!r}"
            )
        evidence = sorted(set(group["status"].dropna().astype(str)))
        pair_ids = sorted(set(group["pair_id"].dropna().astype(str)))
        raw_events = pd.to_numeric(group["events_2026"], errors="coerce").dropna()
        events = int(raw_events.max()) if not raw_events.empty else 0
        activity_values = sorted(set(group["activity"].dropna().astype(str)))
        if events >= 50:
            stratum = "high_50plus"
        elif events > 0:
            stratum = "low_1_49"
        else:
            stratum = "inactive_2026"
        output.append({
            "x_user_id": user_id,
            "handle": handle,
            "pair_ids": "|".join(pair_ids),
            "ens_link_statuses": "|".join(evidence),
            "activity_labels": "|".join(activity_values),
            "events_2026_max_across_confirmed_pairs": events,
            "activity_stratum": stratum,
            "profile_id_preflight_match": True,
        })
    output.sort(key=lambda x: (x["activity_stratum"], x["x_user_id"]))
    return output


def create_run_dir(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for i in range(100):
        candidate = root / f"fx_authorized_batch_{stamp}" if i == 0 else root / f"fx_authorized_batch_{stamp}_{i:02d}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError("could not create a unique run directory")


class Collector:
    def __init__(self, run_dir: Path, cutoff: datetime, allowlist: list[dict[str, Any]]):
        self.run_dir = run_dir
        self.cutoff = cutoff
        self.allowlist = allowlist
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self.request_log_path = run_dir / "requests.jsonl"
        self.tweets_path = run_dir / "tweets_in_window.jsonl"
        self.coverage_path = run_dir / "coverage.csv"
        self.request_count = 0
        self.timeline_page_count = 0
        self.all_rows: list[dict[str, Any]] = []
        self.last_request_at: float | None = None

    def append_jsonl(self, path: Path, row: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()

    def log_request(self, rec: dict[str, Any]) -> None:
        self.append_jsonl(self.request_log_path, rec)

    def request(self, handle: str, kind: str, page: int | None, cursor: str | None, raw_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        url = API.format(handle=quote(handle, safe="@:_-"), kind=kind)
        params = {"cursor": cursor} if cursor else None
        attempt = 0
        last_meta: dict[str, Any] = {}
        while attempt < MAX_RETRIES:
            attempt += 1
            now_mono = time.monotonic()
            if self.last_request_at is not None:
                wait = REQUEST_DELAY_SECONDS - (now_mono - self.last_request_at)
                if wait > 0:
                    time.sleep(wait)
            self.last_request_at = time.monotonic()
            self.request_count += 1
            request_id = f"req_{self.request_count:05d}"
            capture_time = datetime.now(timezone.utc)
            try:
                response = self.session.get(url, params=params, timeout=(15, 45))
                body = response.content
                page_label = f"page_{page:04d}" if page is not None else "profile"
                raw_file = raw_dir / f"{page_label}_{request_id}_attempt_{attempt}.body"
                raw_file.parent.mkdir(parents=True, exist_ok=True)
                raw_file.write_bytes(body)
                parsed: dict[str, Any] | None
                try:
                    value = response.json()
                    parsed = value if isinstance(value, dict) else None
                    json_error = None if parsed is not None else "json_root_not_object"
                except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                    parsed = None
                    json_error = f"json_parse_error:{type(exc).__name__}:{str(exc)[:180]}"
                cursor_out = ((parsed or {}).get("cursor") or {}).get("bottom") if isinstance((parsed or {}).get("cursor"), dict) else None
                api_code = (parsed or {}).get("code")
                api_results = (parsed or {}).get("results")
                error = json_error
                if response.status_code != 200:
                    error = error or f"http_{response.status_code}"
                elif api_code != 200:
                    error = error or f"api_code_{api_code}"
                elif json_error:
                    error = json_error
                last_meta = {
                    "request_id": request_id,
                    "requested_at_utc": iso(capture_time),
                    "http_status": response.status_code,
                    "api_code": api_code,
                    "attempt": attempt,
                    "page": page,
                    "cursor_in": cursor,
                    "cursor_out": str(cursor_out) if cursor_out is not None else None,
                    "result_count": len(api_results) if isinstance(api_results, list) else None,
                    "response_bytes": len(body),
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                    "raw_file": str(raw_file.relative_to(self.run_dir)),
                    "error": error,
                    "request_url_without_query": url,
                    "query_params": params or {},
                }
                self.log_request({"handle": handle, "kind": kind, **last_meta})
                if response.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                    time.sleep(min(2 ** (attempt - 1), 8))
                    continue
                if parsed is None or error:
                    return None, last_meta
                return parsed, last_meta
            except requests.RequestException as exc:
                last_meta = {
                    "request_id": request_id,
                    "requested_at_utc": iso(capture_time),
                    "http_status": None,
                    "api_code": None,
                    "attempt": attempt,
                    "page": page,
                    "cursor_in": cursor,
                    "cursor_out": None,
                    "result_count": None,
                    "response_bytes": None,
                    "response_sha256": None,
                    "raw_file": None,
                    "error": f"request_exception:{type(exc).__name__}:{str(exc)[:220]}",
                    "request_url_without_query": url,
                    "query_params": params or {},
                }
                self.log_request({"handle": handle, "kind": kind, **last_meta})
                if attempt < MAX_RETRIES:
                    time.sleep(min(2 ** (attempt - 1), 8))
        return None, last_meta

    def write_coverage(self) -> None:
        fields = [
            "x_user_id", "handle", "activity_stratum", "profile_id_match_this_run",
            "profile_http_status", "profile_error", "pages_requested", "pages_with_valid_payload",
            "statuses_returned", "statuses_in_target_window", "unique_tweet_ids_in_window",
            "duplicate_tweet_ids", "author_id_mismatches", "missing_timestamps",
            "outside_newer_than_cutoff", "before_start_boundary", "earliest_in_window_utc",
            "latest_in_window_utc", "pagination_order_nonincreasing", "last_cursor",
            "reached_start_boundary", "stop_reason", "complete_to_window_boundary", "truncated_or_uncertain",
        ]
        tmp = self.coverage_path.with_suffix(".csv.tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in self.all_rows:
                w.writerow({k: row.get(k) for k in fields})
        tmp.replace(self.coverage_path)

    def collect_account(self, acct: dict[str, Any], seen_tweet_ids: set[tuple[str, str]]) -> None:
        handle, expected_id = acct["handle"], str(acct["x_user_id"])
        raw_dir = self.run_dir / "raw" / safe_name(handle)
        rec: dict[str, Any] = {
            **acct,
            "profile_id_match_this_run": False,
            "profile_http_status": None,
            "profile_error": None,
            "pages_requested": 0,
            "pages_with_valid_payload": 0,
            "statuses_returned": 0,
            "statuses_in_target_window": 0,
            "unique_tweet_ids_in_window": 0,
            "duplicate_tweet_ids": 0,
            "author_id_mismatches": 0,
            "missing_timestamps": 0,
            "outside_newer_than_cutoff": 0,
            "before_start_boundary": 0,
            "earliest_in_window_utc": None,
            "latest_in_window_utc": None,
            "pagination_order_nonincreasing": True,
            "last_cursor": None,
            "reached_start_boundary": False,
            "stop_reason": None,
            "complete_to_window_boundary": False,
            "truncated_or_uncertain": True,
        }
        raw_profile, profile_meta = self.request(handle, "", None, None, raw_dir)
        rec["profile_http_status"] = profile_meta.get("http_status")
        if raw_profile is None:
            rec["profile_error"] = profile_meta.get("error")
            rec["stop_reason"] = "profile_request_failed"
            self.all_rows.append(rec)
            self.write_coverage()
            print(f"{handle}: PROFILE ERROR {rec['profile_error']}", flush=True)
            return
        user = raw_profile.get("user") if isinstance(raw_profile.get("user"), dict) else {}
        resolved_id = str(user.get("id") or "")
        if resolved_id != expected_id:
            rec["profile_error"] = f"stable_id_mismatch:{resolved_id or 'missing'}"
            rec["stop_reason"] = "profile_identity_mismatch"
            self.all_rows.append(rec)
            self.write_coverage()
            print(f"{handle}: PROFILE ID MISMATCH; skipped timeline", flush=True)
            return
        rec["profile_id_match_this_run"] = True

        cursor: str | None = None
        cursor_seen: set[str] = set()
        page_times: list[datetime] = []
        page_limit_hit = False
        while rec["pages_requested"] < MAX_PAGES_PER_ACCOUNT:
            if self.timeline_page_count >= MAX_TIMELINE_PAGES_TOTAL:
                rec["stop_reason"] = "global_timeline_page_ceiling"
                page_limit_hit = True
                break
            page_no = rec["pages_requested"] + 1
            payload, meta = self.request(handle, "statuses", page_no, cursor, raw_dir)
            rec["pages_requested"] += 1
            self.timeline_page_count += 1
            rec["last_cursor"] = cursor
            if payload is None:
                rec["stop_reason"] = f"timeline_request_failed:{meta.get('error')}"
                break
            results = payload.get("results")
            if not isinstance(results, list):
                rec["stop_reason"] = "results_not_list"
                break
            rec["pages_with_valid_payload"] += 1
            rec["statuses_returned"] += len(results)
            this_page_times: list[datetime] = []
            stop_for_identity = False
            for status in results:
                if not isinstance(status, dict):
                    rec["missing_timestamps"] += 1
                    continue
                author = status.get("author") if isinstance(status.get("author"), dict) else {}
                author_id = str(author.get("id") or "")
                if author_id != expected_id:
                    rec["author_id_mismatches"] += 1
                    stop_for_identity = True
                    continue
                created = parse_timestamp(status)
                if created is None:
                    rec["missing_timestamps"] += 1
                    continue
                this_page_times.append(created)
                if created >= self.cutoff:
                    rec["outside_newer_than_cutoff"] += 1
                    continue
                if created < START_UTC:
                    rec["before_start_boundary"] += 1
                    continue
                rec["statuses_in_target_window"] += 1
                tweet_id = str(status.get("id") or "")
                unique_key = (expected_id, tweet_id)
                if not tweet_id or unique_key in seen_tweet_ids:
                    rec["duplicate_tweet_ids"] += 1
                    continue
                seen_tweet_ids.add(unique_key)
                rec["unique_tweet_ids_in_window"] += 1
                stamp = iso(created)
                page_times.append(created)
                rec["earliest_in_window_utc"] = min(filter(None, [rec["earliest_in_window_utc"], stamp])) if rec["earliest_in_window_utc"] else stamp
                rec["latest_in_window_utc"] = max(filter(None, [rec["latest_in_window_utc"], stamp])) if rec["latest_in_window_utc"] else stamp
                reposted = isinstance(status.get("reposted_by"), dict)
                replied = isinstance(status.get("replying_to"), dict)
                quoted = isinstance(status.get("quote"), dict)
                kind = "repost" if reposted else "reply" if replied else "quote" if quoted else "original"
                quote = status.get("quote") if isinstance(status.get("quote"), dict) else {}
                replying_to = status.get("replying_to") if isinstance(status.get("replying_to"), dict) else {}
                normalized = {
                    "queried_user_id": expected_id,
                    "queried_handle_at_collection": handle,
                    "tweet_id": tweet_id,
                    "created_at_utc": stamp,
                    "post_kind": kind,
                    "author_id": author_id,
                    "author_handle_in_payload": author.get("screen_name"),
                    "is_repost": reposted,
                    "is_reply": replied,
                    "is_quote": quoted,
                    "authored_text": None if reposted else status.get("text"),
                    "returned_text": status.get("text"),
                    "reposted_by": status.get("reposted_by"),
                    "replying_to": replying_to,
                    "quoted_tweet_id": quote.get("id"),
                    "quoted_author_id": (quote.get("author") or {}).get("id") if isinstance(quote.get("author"), dict) else None,
                    "quoted_author_handle": (quote.get("author") or {}).get("screen_name") if isinstance(quote.get("author"), dict) else None,
                    "quoted_text": quote.get("text"),
                    "raw_status": status,
                }
                self.append_jsonl(self.tweets_path, normalized)
            if stop_for_identity:
                rec["stop_reason"] = "timeline_author_id_mismatch"
                break
            if len(this_page_times) >= 2 and any(a < b for a, b in zip(this_page_times, this_page_times[1:])):
                rec["pagination_order_nonincreasing"] = False
            if this_page_times and max(this_page_times) < START_UTC:
                rec["reached_start_boundary"] = True
                rec["stop_reason"] = "older_than_start_boundary"
                break
            cursor_obj = payload.get("cursor")
            next_cursor = cursor_obj.get("bottom") if isinstance(cursor_obj, dict) else None
            if not results or not next_cursor:
                rec["stop_reason"] = "timeline_exhausted_no_next_cursor"
                break
            next_cursor = str(next_cursor)
            if next_cursor in cursor_seen or next_cursor == cursor:
                rec["stop_reason"] = "cursor_repeated"
                break
            cursor_seen.add(next_cursor)
            cursor = next_cursor
        else:
            rec["stop_reason"] = "per_account_page_ceiling"
            page_limit_hit = True
        if rec["stop_reason"] is None:
            rec["stop_reason"] = "stopped_without_reason"
        rec["complete_to_window_boundary"] = bool(rec["reached_start_boundary"] or rec["stop_reason"] == "timeline_exhausted_no_next_cursor")
        rec["truncated_or_uncertain"] = not rec["complete_to_window_boundary"]
        if page_limit_hit:
            rec["truncated_or_uncertain"] = True
        self.all_rows.append(rec)
        self.write_coverage()
        print(
            f"{handle}: pages={rec['pages_requested']} in_window={rec['unique_tweet_ids_in_window']} "
            f"earliest={rec['earliest_in_window_utc']} stop={rec['stop_reason']}", flush=True
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true", help="validate allowlist and prior stable-ID audit without network requests")
    parser.add_argument("--root", type=Path, default=ARTIFACTS)
    args = parser.parse_args()

    allowlist = load_allowlist()
    strata = Counter(a["activity_stratum"] for a in allowlist)
    print(f"allowlist_accounts={len(allowlist)} strata={dict(sorted(strata.items()))}")
    print(f"stable_id_profile_preflight=PASS for all {len(allowlist)} accounts")
    if args.preflight_only:
        for a in allowlist:
            print(f"{a['activity_stratum']}: {a['handle']} id={a['x_user_id']} pair_ids={a['pair_ids']}")
        return 0

    # The end bound is fixed at run start to prevent future leakage even if collection takes time.
    cutoff = datetime.now(timezone.utc)
    run_dir = create_run_dir(args.root)
    manifest = {
        "run_id": run_dir.name,
        "authorization_basis": "User confirmed in this conversation that FxEmbed collection is authorized; no authorization document copied into this artifact.",
        "source": "FxEmbed public v2 timeline/profile endpoint; no X API, login, or following/follower endpoint used.",
        "endpoint_pattern": "https://api.fxtwitter.com/2/profile/{handle}/[statuses]",
        "created_at_utc": iso(datetime.now(timezone.utc)),
        "target_start_inclusive_utc": iso(START_UTC),
        "target_end_exclusive_utc": iso(cutoff),
        "end_cutoff_semantics": "exact UTC start-of-run timestamp; records at/after cutoff are excluded",
        "allowlist_source": str(SAMPLE.relative_to(BASE)),
        "stable_id_preflight_source": str(PROFILES.relative_to(BASE)),
        "account_count": len(allowlist),
        "strata_counts": dict(sorted(strata.items())),
        "max_pages_per_account": MAX_PAGES_PER_ACCOUNT,
        "max_timeline_pages_total": MAX_TIMELINE_PAGES_TOTAL,
        "request_delay_seconds": REQUEST_DELAY_SECONDS,
        "retry_limit": MAX_RETRIES,
        "page_size_observed_in_previous_pilot": PAGE_SIZE_ASSUMED,
        "collection_semantics": {
            "only_account_confirms_and_stable_x_user_id": True,
            "profile_id_must_match_before_timeline": True,
            "each_status_author_id_must_match_expected_id": True,
            "retweet_text_is_not_authored_text": True,
            "current_following_snapshot_excluded": True,
            "automatic_candidate_pool_expansion": False,
        },
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sample_fields = list(allowlist[0])
    with (run_dir / "sample_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sample_fields)
        w.writeheader()
        w.writerows(allowlist)

    print(f"run_dir={run_dir}")
    print(f"target_window=[{iso(START_UTC)}, {iso(cutoff)})")
    collector = Collector(run_dir, cutoff, allowlist)
    seen: set[tuple[str, str]] = set()
    try:
        for acct in allowlist:
            collector.collect_account(acct, seen)
            if collector.timeline_page_count >= MAX_TIMELINE_PAGES_TOTAL:
                print("global timeline page ceiling reached; no more accounts/pages will be requested", flush=True)
                break
    except KeyboardInterrupt:
        print("interrupted: raw pages and request/cursor log are preserved; coverage reflects completed accounts", file=sys.stderr)
        return 130
    finally:
        collector.write_coverage()
        summary = {
            "finished_at_utc": iso(datetime.now(timezone.utc)),
            "accounts_attempted": len(collector.all_rows),
            "timeline_pages": collector.timeline_page_count,
            "requests_total": collector.request_count,
            "tweets_in_window_unique": sum(int(r.get("unique_tweet_ids_in_window") or 0) for r in collector.all_rows),
            "accounts_complete_to_boundary": sum(bool(r.get("complete_to_window_boundary")) for r in collector.all_rows),
            "accounts_uncertain_or_truncated": sum(bool(r.get("truncated_or_uncertain")) for r in collector.all_rows),
            "coverage_file": "coverage.csv",
            "request_log": "requests.jsonl",
            "derived_tweets": "tweets_in_window.jsonl",
            "raw_responses_dir": "raw/",
        }
        (run_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RUN_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
