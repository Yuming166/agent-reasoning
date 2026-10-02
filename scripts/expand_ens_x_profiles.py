#!/usr/bin/env python3
"""Resumable FxEmbed profile audit for the active ENS candidate pool.

Exact account-side mentions of a reverse ENS name or a full wallet address are
marked as positive *candidates*, pending human quality audit. No timeline or
chain requests are made by this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests


HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
PROXY = "http://10.63.0.72:7890"
HEADERS = {"User-Agent": "exgraph-research/0.1 (authorized academic identity audit)"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def exact_term(text: str, term: str) -> bool:
    if not term:
        return False
    return re.search(r"(?<![a-z0-9._-])" + re.escape(term.lower()) +
                     r"(?![a-z0-9._-])", text.lower()) is not None


def load_candidates(source: Path, max_profiles: int) -> list[dict]:
    valid = defaultdict(set)
    with (source / "bidirectional_validation.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["status"] == "bidirectional_ok":
                valid[(row["address"].lower(), row["handle"].lower())].add(row["reverse_name"].lower())
    grouped = {}
    with (source / "pairs_stratified_frame.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            handle_text = row["handle"]
            key = (row["address"].lower(), handle_text.lower())
            events = int(float(row["events_2026"] or "0"))
            if key not in valid or events <= 0 or not HANDLE_RE.fullmatch(handle_text):
                continue
            h = handle_text.lower()
            if h not in grouped:
                grouped[h] = {"handle": handle_text, "records": [], "max_events_2026": 0}
            grouped[h]["max_events_2026"] = max(grouped[h]["max_events_2026"], events)
            for name in valid[key]:
                evidence = (row["address"].lower(), name)
                if evidence not in {(x["address"], x["reverse_name"]) for x in grouped[h]["records"]}:
                    grouped[h]["records"].append({"address": evidence[0], "reverse_name": evidence[1],
                                                  "record_set_at": row["record_set_at"],
                                                  "events_2026": events})
    candidates = list(grouped.values())
    candidates.sort(key=lambda x: (-x["max_events_2026"], x["handle"].lower()))
    if max_profiles and len(candidates) > max_profiles:
        top_n = max_profiles // 2
        top = candidates[:top_n]
        remainder = candidates[top_n:]
        rng = random.Random(20260925)
        sampled = rng.sample(remainder, max_profiles - top_n)
        candidates = top + sorted(sampled, key=lambda x: x["handle"].lower())
        for item in top:
            item["selection_stratum"] = "top_chain_activity"
        for item in sampled:
            item["selection_stratum"] = "random_remaining_pool"
    else:
        for item in candidates:
            item["selection_stratum"] = "full_active_pool"
    return candidates


def classify(candidate: dict, response: dict) -> dict:
    data = response.get("data") or {}
    user = data.get("user") if isinstance(data, dict) else None
    result = {"handle_requested": candidate["handle"],
              "selection_stratum": candidate["selection_stratum"],
              "max_events_2026": candidate["max_events_2026"],
              "http_status": response.get("http_status"),
              "fetched_at_utc": response.get("fetched_at_utc"),
              "candidate_records": candidate["records"],
              "x_user_id": None, "screen_name": None,
              "evidence_positive_pairs": [], "classification": "unverifiable"}
    if not isinstance(user, dict) or not user.get("id"):
        result["reason"] = response.get("error") or "no_profile_user"
        return result
    result["x_user_id"] = str(user["id"])
    result["screen_name"] = user.get("screen_name")
    if (user.get("screen_name") or "").lower() != candidate["handle"].lower():
        result["reason"] = "returned_handle_mismatch"
        return result
    website = user.get("website") or {}
    if isinstance(website, dict):
        website = " ".join(str(website.get(k) or "") for k in ("url", "display_url"))
    fields = {
        "display_name": str(user.get("name") or ""),
        "bio": str(user.get("description") or ""),
        "website": str(website),
    }
    for record in candidate["records"]:
        hits = []
        for field, text in fields.items():
            if exact_term(text, record["address"]):
                hits.append({"field": field, "evidence_type": "full_wallet_address", "matched": record["address"]})
            name = record["reverse_name"]
            if name and len(name) >= 6 and exact_term(text, name):
                hits.append({"field": field, "evidence_type": "exact_reverse_ens_name", "matched": name})
        if hits:
            result["evidence_positive_pairs"].append({**record, "hits": hits})
    result["classification"] = "account_side_exact_match_candidate" if result["evidence_positive_pairs"] else "ens_only"
    result["reason"] = "snapshot_evidence_requires_manual_audit_and_as_of_join"
    return result


def fetch(session: requests.Session, candidate: dict, raw_path: Path) -> dict:
    if raw_path.is_file():
        return json.loads(raw_path.read_text(encoding="utf-8"))
    handle = candidate["handle"]
    for attempt in range(3):
        try:
            response = session.get(f"https://api.fxtwitter.com/{handle}", headers=HEADERS,
                                   proxies={"http": PROXY, "https": PROXY}, timeout=30,
                                   allow_redirects=False)
            item = {"handle": handle, "http_status": response.status_code,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat()}
            if response.status_code == 200:
                item["data"] = response.json()
            else:
                item["error"] = f"http_{response.status_code}"
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            break
        except (requests.RequestException, ValueError) as exc:
            item = {"handle": handle, "http_status": None,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "error": type(exc).__name__}
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            break
    raw_path.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")
    return item


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-profiles", type=int, default=2000)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out.resolve()
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = root / "artifacts/ens_x_crosswalk"
    manifest = out / "candidate_queue.json"
    if manifest.is_file():
        candidates = json.loads(manifest.read_text(encoding="utf-8"))
    else:
        candidates = load_candidates(source, args.max_profiles)
        manifest.write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("frozen candidate handles", len(candidates), flush=True)
    session = requests.Session()
    output = out / "profile_audit_results.jsonl"
    existing = {}
    if output.is_file():
        with output.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    existing[value["handle_requested"].lower()] = value
    consecutive_errors = 0
    with output.open("a", encoding="utf-8") as handle:
        for index, candidate in enumerate(candidates, 1):
            h = candidate["handle"].lower()
            if h in existing:
                continue
            raw_path = raw_dir / f"{h}.json"
            legacy_path = source / "fx_raw" / f"{h}.json"
            if legacy_path.is_file() and not raw_path.is_file():
                item = json.loads(legacy_path.read_text(encoding="utf-8"))
                item.setdefault("fetched_at_utc", "2026-09-24_snapshot")
                item["reused_legacy_path"] = str(legacy_path.relative_to(root))
                raw_path.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")
            else:
                item = fetch(session, candidate, raw_path)
                time.sleep(args.delay_seconds)
            result = classify(candidate, item)
            result["raw_sha256"] = sha256(raw_path)
            result["raw_file"] = str(raw_path.relative_to(root))
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
            if result["http_status"] == 200:
                consecutive_errors = 0
            else:
                consecutive_errors += 1
            if index % 50 == 0 or result["classification"] == "account_side_exact_match_candidate":
                print(index, h, result["classification"], flush=True)
            if consecutive_errors >= 20:
                raise RuntimeError("Circuit breaker: 20 consecutive non-200 profiles")
    print("profile audit complete", flush=True)


if __name__ == "__main__":
    main()
