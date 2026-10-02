#!/usr/bin/env python3
"""Analyze the already archived FxEmbed pilot files; this script makes no requests.

Run with: python scripts/analyze_fx_pilot_archive.py
Outputs aggregate CSV/Markdown under artifacts/ens_x_crosswalk/fx_archive_analysis/.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "artifacts/ens_x_crosswalk"
RAW = ROOT / "fx_pilot_raw"
VERIFY = ROOT / "verification_sample_v2_filled.csv"
OUT = ROOT / "fx_archive_analysis"
PAGE_CAP = 8


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, 0) if row.get(field, 0) is not None else 0 for field in fields})


def as_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "null"} else None


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def timestamp(post: dict[str, Any]) -> datetime | None:
    value = post.get("created_timestamp")
    if value is not None:
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    value = post.get("created_at")
    if value:
        for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(value, fmt).astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def reposted_by_id(post: dict[str, Any]) -> str | None:
    value = post.get("reposted_by")
    return as_id(value.get("id")) if isinstance(value, dict) else None


def author_id(post: dict[str, Any]) -> str | None:
    author = post.get("author") or {}
    return as_id(author.get("id")) if isinstance(author, dict) else None


def reply_target(post: dict[str, Any], handle_to_id: dict[str, str]) -> str | None:
    reply = post.get("replying_to")
    if not reply:
        return None
    if not isinstance(reply, dict):
        return as_id(reply)
    user = reply.get("user") or {}
    target = as_id(reply.get("user_id") or reply.get("author_id"))
    if not target and isinstance(user, dict):
        target = as_id(user.get("id"))
    if not target:
        handle = (reply.get("screen_name") or reply.get("username") or "").strip().casefold()
        target = handle_to_id.get(handle)
    return target


def quote_target(post: dict[str, Any], handle_to_id: dict[str, str]) -> str | None:
    quote = post.get("quote")
    if not isinstance(quote, dict):
        return None
    author = quote.get("author") or {}
    target = as_id(author.get("id")) if isinstance(author, dict) else None
    if not target and isinstance(author, dict):
        target = handle_to_id.get((author.get("screen_name") or "").strip().casefold())
    return target


def relevant_signature(post: dict[str, Any]) -> tuple[str, ...]:
    author = post.get("author") or {}
    quote = post.get("quote") or {}
    quote_author = quote.get("author") or {} if isinstance(quote, dict) else {}
    raw_text = post.get("raw_text") or {}
    facets = raw_text.get("facets") or [] if isinstance(raw_text, dict) else []
    return (
        as_id(author.get("id")) or "",
        as_id(post.get("created_timestamp")) or str(post.get("created_at") or ""),
        str(post.get("text") or ""),
        str(raw_text.get("text") or "") if isinstance(raw_text, dict) else "",
        canonical(facets),
        canonical(post.get("replying_to")),
        as_id(quote.get("id")) if isinstance(quote, dict) else "",
        as_id(quote_author.get("id")) if isinstance(quote_author, dict) else "",
    )


def classify_versions(owner: str, versions: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    posts = [entry["x"] for entry in versions]
    relevant_fields_conflict = len({relevant_signature(post) for post in posts}) > 1
    reposter_values = {reposted_by_id(post) for post in posts}
    author_values = {author_id(post) for post in posts}
    reply_values = {bool(post.get("replying_to")) for post in posts}

    if relevant_fields_conflict:
        return "ambiguous_metadata", "content_or_target_fields_disagree_across_duplicate_rows", ["content_or_target_fields"]

    if len(reposter_values) > 1:
        nonnull_reposters = {value for value in reposter_values if value}
        if nonnull_reposters == {owner} and author_values == {owner}:
            return "ambiguous_self_retweet", "reposted_by_conflicts_with_null_and_author_equals_timeline_owner", ["reposted_by"]
        return "ambiguous_metadata", "reposted_by_disagrees_across_duplicate_rows", ["reposted_by"]

    reposter = next(iter(reposter_values))
    if reposter:
        if reposter == owner and author_values == {owner}:
            return "ambiguous_self_retweet", "reposter_and_source_author_are_same_timeline_owner", []
        return "retweet", "consistent_reposted_by_metadata", []

    if len(reply_values) > 1:
        return "ambiguous_metadata", "reply_metadata_disagrees_across_duplicate_rows", ["replying_to"]
    if next(iter(reply_values)):
        return "reply", "replying_to_present", []
    return "authored", "no_repost_or_reply_metadata", []


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def months_between(first: str, last: str) -> list[str]:
    fy, fm = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    start, end = fy * 12 + fm - 1, ly * 12 + lm - 1
    return [f"{index // 12:04d}-{index % 12 + 1:02d}" for index in range(start, end + 1)]


def text_nonempty(post: dict[str, Any]) -> bool:
    return bool((post.get("text") or "").strip())


def mention_facets(post: dict[str, Any]) -> list[dict[str, Any]]:
    raw_text = post.get("raw_text") or {}
    facets = raw_text.get("facets") or [] if isinstance(raw_text, dict) else []
    return [facet for facet in facets if isinstance(facet, dict) and facet.get("type") == "mention"]


def main() -> None:
    if not RAW.is_dir():
        raise SystemExit(f"Missing local archive: {RAW}")
    OUT.mkdir(parents=True, exist_ok=True)

    verification = read_csv(VERIFY)
    confirmed = [row for row in verification if row.get("verification_status") == "account_confirms"]
    handle_to_ids: dict[str, set[str]] = defaultdict(set)
    id_handles: dict[str, set[str]] = defaultdict(set)
    exact_handles: set[str] = set()
    for row in confirmed:
        handle = (row.get("handle") or "").strip()
        uid = as_id(row.get("x_user_id"))
        if handle and uid:
            exact_handles.add(handle)
            handle_to_ids[handle.casefold()].add(uid)
            id_handles[uid].add(handle)
    ambiguous_handles = {handle: ids for handle, ids in handle_to_ids.items() if len(ids) != 1}
    if ambiguous_handles:
        raise SystemExit(f"Ambiguous confirmed handle->X ID mapping: {ambiguous_handles}")
    handle_map = {handle: next(iter(ids)) for handle, ids in handle_to_ids.items()}
    sample_ids = set(id_handles)

    raw_entries: list[dict[str, Any]] = []
    page_files: dict[str, list[dict[str, Any]]] = defaultdict(list)
    owner_mismatches: list[tuple[str, str, str, str]] = []
    unmapped_dirs: list[str] = []

    for account_dir in sorted((path for path in RAW.iterdir() if path.is_dir()), key=lambda p: p.name.casefold()):
        alias = account_dir.name
        expected_owner = handle_map.get(alias.casefold())
        if expected_owner is None:
            unmapped_dirs.append(alias)
        status_dir = account_dir / "statuses"
        paths = sorted(status_dir.glob("p*.json"), key=lambda path: int(path.stem[1:])) if status_dir.exists() else []
        for path in paths:
            page_no = int(path.stem[1:])
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("page payload is not an object")
            except Exception as exc:
                page_files[alias].append({"page": page_no, "n": 0, "rows": [], "cursor": False,
                                          "code": None, "error": repr(exc)})
                continue
            rows = payload.get("results") or []
            if not isinstance(rows, list):
                rows = []
            code = payload.get("code")
            page_files[alias].append({
                "page": page_no, "n": len(rows), "rows": rows,
                "cursor": bool((payload.get("cursor") or {}).get("bottom")),
                "code": code, "error": payload.get("message") if code != 200 else None,
            })
            for row_index, post in enumerate(rows):
                if not isinstance(post, dict):
                    continue
                rb = post.get("reposted_by")
                rb_id = reposted_by_id(post)
                if rb:
                    reported_owner = rb_id
                else:
                    reported_owner = author_id(post)
                if expected_owner and reported_owner and reported_owner != expected_owner:
                    owner_mismatches.append((alias, str(post.get("id")), reported_owner, expected_owner))
                owner = expected_owner or reported_owner
                if not owner:
                    continue
                raw_entries.append({
                    "owner": owner,
                    "tweet_id": as_id(post.get("id")) or f"missing-id:{alias}:{page_no}:{row_index}",
                    "alias": alias,
                    "page": page_no,
                    "x": post,
                    "dt": timestamp(post),
                })

    if unmapped_dirs:
        raise SystemExit(f"Unmapped archive directories: {unmapped_dirs}")
    if owner_mismatches:
        raise SystemExit(f"Timeline-owner mismatch(es): {owner_mismatches[:8]} (n={len(owner_mismatches)})")

    # Deduplicate deterministically by sampled timeline owner and tweet ID.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in raw_entries:
        groups[(entry["owner"], entry["tweet_id"])].append(entry)
    records: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    duplicate_rows = 0
    for (owner, tweet_id), versions in sorted(groups.items()):
        duplicate_rows += len(versions) - 1
        # Prefer the payload with the most non-null fields; break ties via canonical
        # JSON, never by file-system or page iteration order.
        versions_sorted = sorted(
            versions,
            key=lambda entry: (-sum(value is not None for value in entry["x"].values()), canonical(entry["x"])),
        )
        chosen = dict(versions_sorted[0])
        typ, reason, conflict_fields = classify_versions(owner, versions)
        chosen["type"] = typ
        chosen["classification_reason"] = reason
        chosen["conflict_fields"] = conflict_fields
        chosen["aliases"] = sorted({entry["alias"] for entry in versions}, key=str.casefold)
        chosen["duplicate_versions"] = len(versions)
        # A deterministic representative is safe only when the relevant post content agrees.
        chosen["x"] = versions_sorted[0]["x"]
        records.append(chosen)
        if len(versions) > 1 and (conflict_fields or len({reposted_by_id(v["x"]) for v in versions}) > 1):
            reposter_labels = sorted({reposted_by_id(v["x"]) or "<null>" for v in versions})
            author_labels = sorted({author_id(v["x"]) or "<null>" for v in versions})
            conflict_rows.append({
                "timeline_x_user_id": owner,
                "tweet_id": tweet_id,
                "archive_handles": ";".join(chosen["aliases"]),
                "duplicate_rows": len(versions) - 1,
                "reposted_by_values": ";".join(reposter_labels),
                "author_ids": ";".join(author_labels),
                "earliest_or_available_utc": chosen["dt"].isoformat() if chosen["dt"] else "",
                "classification": typ,
                "classification_reason": reason,
                "conflict_fields": ";".join(conflict_fields),
                "text_nonempty": text_nonempty(chosen["x"]),
            })

    if not records:
        raise SystemExit("No status records found in local archive")

    # Per-alias page audit, then stable-ID aggregation. A cursor alone is not
    # considered proof of additional records; only cap + nonempty last page + cursor
    # is flagged as suspected truncation.
    record_dates: dict[str, list[datetime]] = defaultdict(list)
    records_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_owner[record["owner"]].append(record)
        if record["dt"]:
            record_dates[record["owner"]].append(record["dt"])

    alias_rows: list[dict[str, Any]] = []
    gaps_unique: set[tuple[str, str, str, float]] = set()
    uid_alias_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alias in sorted(set(page_files) | {h for uid in sample_ids for h in id_handles[uid]}, key=str.casefold):
        uid = handle_map.get(alias.casefold(), "")
        pages = sorted(page_files.get(alias, []), key=lambda page: page["page"])
        page_numbers = [page["page"] for page in pages]
        missing_page_numbers = sorted(set(range(min(page_numbers), max(page_numbers) + 1)) - set(page_numbers)) if page_numbers else []
        last = max(pages, key=lambda page: page["page"]) if pages else {"page": "", "n": 0, "cursor": False}
        cap_suspect = len(pages) >= PAGE_CAP and last["n"] > 0 and last["cursor"]
        gaps: list[float] = []
        overlaps = 0
        for left, right in zip(pages, pages[1:]):
            if right["page"] != left["page"] + 1:
                continue
            left_dates = [timestamp(post) for post in left["rows"] if isinstance(post, dict)]
            right_dates = [timestamp(post) for post in right["rows"] if isinstance(post, dict)]
            left_dates = [value for value in left_dates if value]
            right_dates = [value for value in right_dates if value]
            if left_dates and right_dates:
                gap = (min(left_dates) - max(right_dates)).total_seconds() / 86400
                gaps.append(gap)
                gaps_unique.add((uid, min(left_dates).isoformat(), max(right_dates).isoformat(), gap))
            left_ids = {as_id(post.get("id")) for post in left["rows"] if isinstance(post, dict)}
            right_ids = {as_id(post.get("id")) for post in right["rows"] if isinstance(post, dict)}
            overlaps += len((left_ids - {None}) & (right_ids - {None}))
        errors = sum(page.get("code") != 200 or page.get("error") is not None for page in pages)
        row = {
            "archive_handle_spelling": alias,
            "stable_x_user_id": uid,
            "page_files": len(pages),
            "page_numbers": ";".join(map(str, page_numbers)),
            "missing_page_numbers_within_range": ";".join(map(str, missing_page_numbers)),
            "raw_rows_across_page_files": sum(page["n"] for page in pages),
            "earliest_visible_utc": min(record_dates.get(uid, [])).isoformat() if record_dates.get(uid) else "",
            "latest_visible_utc": max(record_dates.get(uid, [])).isoformat() if record_dates.get(uid) else "",
            "empty_pages": sum(page["n"] == 0 for page in pages),
            "last_page_number": last["page"],
            "last_page_rows": last["n"],
            "last_page_has_bottom_cursor": last["cursor"],
            "suspected_truncated_at_page_cap": cap_suspect,
            "adjacent_page_duplicate_ids": overlaps,
            "positive_page_boundary_gaps_ge_30d": sum(g >= 30 for g in gaps),
            "max_positive_page_boundary_gap_days": round(max((g for g in gaps if g > 0), default=0), 2),
            "error_pages": errors,
        }
        alias_rows.append(row)
        if uid:
            uid_alias_rows[uid].append(row)

    account_rows: list[dict[str, Any]] = []
    for uid in sorted(sample_ids):
        rows = uid_alias_rows.get(uid, [])
        ids = [record["dt"] for record in records_by_owner.get(uid, []) if record["dt"]]
        suspected = [row["archive_handle_spelling"] for row in rows if row["suspected_truncated_at_page_cap"]]
        page_gaps = [row["missing_page_numbers_within_range"] for row in rows if row["missing_page_numbers_within_range"]]
        account_rows.append({
            "stable_x_user_id": uid,
            "verified_handle_spellings": ";".join(sorted(id_handles[uid], key=str.casefold)),
            "archive_handle_spellings": ";".join(row["archive_handle_spelling"] for row in rows),
            "archive_alias_count": len(rows),
            "page_file_count_across_aliases": sum(row["page_files"] for row in rows),
            "raw_rows_across_page_files": sum(row["raw_rows_across_page_files"] for row in rows),
            "unique_tweets_across_aliases": len(records_by_owner.get(uid, [])),
            "earliest_visible_utc": min(ids).isoformat() if ids else "",
            "latest_visible_utc": max(ids).isoformat() if ids else "",
            "page_number_gaps_by_alias": " | ".join(f"{row['archive_handle_spelling']}:{row['missing_page_numbers_within_range']}" for row in rows if row["missing_page_numbers_within_range"]) or "none observed",
            "suspected_truncated_aliases_at_page_cap": ";".join(suspected) or "none",
            "suspected_truncated_alias_count": len(suspected),
            "error_pages_across_aliases": sum(row["error_pages"] for row in rows),
            "max_positive_consecutive_page_boundary_gap_days": max((row["max_positive_page_boundary_gap_days"] for row in rows), default=0),
        })

    # Calendar-month counts. Empty values are explicitly zero; a zero here means
    # no record in this archive for the month, not proof the account posted nothing.
    dated = [record["dt"] for record in records if record["dt"]]
    if not dated:
        raise SystemExit("All archived status records lack parseable timestamps")
    months = months_between(month_key(min(dated)), month_key(max(dated)))
    month_counts: dict[str, Counter[str]] = defaultdict(Counter)
    total_types: Counter[str] = Counter(record["type"] for record in records)
    quote_counts: Counter[str] = Counter()
    text_counts: Counter[str] = Counter()
    mention_counts: Counter[str] = Counter()
    missing_timestamp = sum(record["dt"] is None for record in records)
    retweet_reply_overlap = 0
    for record in records:
        post, typ, dt = record["x"], record["type"], record["dt"]
        if typ == "retweet" and post.get("replying_to"):
            retweet_reply_overlap += 1
        if not dt:
            continue
        month = month_key(dt)
        month_counts[month][typ] += 1
        has_text = text_nonempty(post)
        if has_text:
            text_counts[typ] += 1
            month_counts[month][f"{typ}_text_nonempty"] += 1
        if post.get("quote") and typ in {"authored", "reply"}:
            quote_counts[typ] += 1
            month_counts[month][f"{typ}_quote_posts"] += 1
        facets = mention_facets(post)
        if typ in {"authored", "reply"}:
            mention_class = "author_text"
        elif typ == "retweet":
            mention_class = "retweet_source"
        elif typ == "ambiguous_self_retweet":
            mention_class = "ambiguous_self_source"
        else:
            mention_class = "ambiguous_metadata_source"
        month_counts[month][f"{mention_class}_mention_facets"] += len(facets)
        if facets:
            month_counts[month][f"{mention_class}_mention_posts"] += 1
        mention_counts[mention_class] += len(facets)

    content_fields = [
        "authored", "authored_text_nonempty", "authored_quote_posts",
        "reply", "reply_text_nonempty", "reply_quote_posts",
        "retweet", "retweet_text_nonempty",
        "ambiguous_self_retweet", "ambiguous_self_retweet_text_nonempty",
        "ambiguous_metadata", "ambiguous_metadata_text_nonempty",
        "author_text_mention_facets", "author_text_mention_posts",
        "retweet_source_mention_facets", "retweet_source_mention_posts",
        "ambiguous_self_source_mention_facets", "ambiguous_self_source_mention_posts",
        "ambiguous_metadata_source_mention_facets", "ambiguous_metadata_source_mention_posts",
    ]
    monthly_content = [{"month_utc": month, **{field: month_counts[month][field] for field in content_fields}} for month in months]

    # Construct a sample-induced, typed interaction graph. Quote edges are kept
    # separate; a quote's embedded source text never enters author-text counts.
    edge_events: dict[str, dict[str, set[tuple[str, str]]]] = defaultdict(lambda: defaultdict(set))
    edge_event_counts: Counter[tuple[str, str]] = Counter()
    typed_edge_months: dict[str, dict[tuple[str, str], set[str]]] = defaultdict(lambda: defaultdict(set))
    unresolved_reply_handles: Counter[str] = Counter()
    self_loops: Counter[str] = Counter()

    def add_edge(kind: str, src: str, dst: str, month: str) -> None:
        if src == dst:
            self_loops[kind] += 1
            return
        edge = (src, dst)
        edge_events[kind][month].add(edge)
        edge_event_counts[(kind, month)] += 1
        typed_edge_months[kind][edge].add(month)

    for record in records:
        post, typ, dt, src = record["x"], record["type"], record["dt"], record["owner"]
        if not dt:
            continue
        month = month_key(dt)
        if typ == "retweet":
            target = author_id(post)
            if target in sample_ids:
                add_edge("retweet", src, target, month)
        if typ == "reply":
            target = reply_target(post, handle_map)
            if target in sample_ids:
                add_edge("reply", src, target, month)
            elif (post.get("replying_to") or {}).get("screen_name"):
                unresolved_reply_handles[(post.get("replying_to") or {}).get("screen_name", "unknown")] += 1
        if typ in {"authored", "reply"}:
            target = quote_target(post, handle_map)
            if target in sample_ids:
                add_edge("quote", src, target, month)
            for facet in mention_facets(post):
                target = as_id(facet.get("id"))
                if target in sample_ids:
                    add_edge("mention", src, target, month)

    all_edges: set[tuple[str, str]] = set()
    combined_edge_months: dict[tuple[str, str], set[str]] = defaultdict(set)
    for by_edge in typed_edge_months.values():
        for edge, active_months in by_edge.items():
            all_edges.add(edge)
            combined_edge_months[edge].update(active_months)
    incident_nodes = {node for edge in all_edges for node in edge}
    out_nodes = {src for src, _ in all_edges}
    in_nodes = {dst for _, dst in all_edges}
    n_sample = len(sample_ids)
    density_full = len(all_edges) / (n_sample * (n_sample - 1)) if n_sample > 1 else 0.0
    density_active = len(all_edges) / (len(incident_nodes) * (len(incident_nodes) - 1)) if len(incident_nodes) > 1 else None
    persistent_edges = sum(len(active_months) >= 2 for active_months in combined_edge_months.values())
    edge_month_span_counts = Counter(len(active_months) for active_months in combined_edge_months.values())

    graph_monthly: list[dict[str, Any]] = []
    graph_types = ("retweet", "reply", "quote", "mention")
    for month in months:
        typed_month_edges = {kind: edge_events[kind].get(month, set()) for kind in graph_types}
        month_edges = set().union(*typed_month_edges.values())
        month_nodes = {node for edge in month_edges for node in edge}
        row: dict[str, Any] = {"month_utc": month}
        for kind in graph_types:
            row[f"{kind}_events"] = edge_event_counts[(kind, month)]
            row[f"{kind}_directed_edges"] = len(typed_month_edges[kind])
        row.update({
            "unique_multiplex_directed_edges": len(month_edges),
            "nodes_with_any_within_sample_edge": len(month_nodes),
            "density_on_sample_nodes": f"{len(month_edges)/(n_sample*(n_sample-1)):.6f}" if n_sample > 1 else "0.000000",
        })
        graph_monthly.append(row)

    write_csv(OUT / "monthly_content_counts.csv", monthly_content, ["month_utc", *content_fields])
    graph_fields = ["month_utc"] + [f"{kind}_{metric}" for kind in graph_types for metric in ("events", "directed_edges")] + [
        "unique_multiplex_directed_edges", "nodes_with_any_within_sample_edge", "density_on_sample_nodes"]
    write_csv(OUT / "monthly_sample_graph.csv", graph_monthly, graph_fields)
    write_csv(OUT / "account_page_coverage.csv", account_rows, list(account_rows[0].keys()))
    write_csv(OUT / "account_archive_alias_audit.csv", alias_rows, list(alias_rows[0].keys()))
    write_csv(OUT / "duplicate_metadata_conflicts.csv", conflict_rows, [
        "timeline_x_user_id", "tweet_id", "archive_handles", "duplicate_rows", "reposted_by_values",
        "author_ids", "earliest_or_available_utc", "classification", "classification_reason", "conflict_fields", "text_nonempty"])

    months_2026 = [month for month in months if month.startswith("2026-")]
    content_table = "\n".join(
        f"| {month} | {month_counts[month]['authored']} | {month_counts[month]['reply']} | {month_counts[month]['retweet']} | "
        f"{month_counts[month]['ambiguous_self_retweet']} | {month_counts[month]['authored_text_nonempty'] + month_counts[month]['reply_text_nonempty']} | "
        f"{month_counts[month]['retweet_text_nonempty']} | {month_counts[month]['author_text_mention_facets']} |"
        for month in months_2026
    ) or "| No observed 2026 month | 0 | 0 | 0 | 0 | 0 | 0 | 0 |"
    graph_table = "\n".join(
        f"| {row['month_utc']} | {row['unique_multiplex_directed_edges']} | {row['nodes_with_any_within_sample_edge']} | "
        f"{row['retweet_directed_edges']} | {row['reply_directed_edges']} | {row['quote_directed_edges']} | {row['mention_directed_edges']} |"
        for row in graph_monthly if row["month_utc"].startswith("2026-")
    ) or "| No observed 2026 month | 0 | 0 | 0 | 0 | 0 | 0 |"

    unique_gap_rows = list(gaps_unique)
    positive_gaps = [row[3] for row in unique_gap_rows if row[3] > 0]
    over_30 = sum(gap >= 30 for gap in positive_gaps)
    all_aliases = len({row["archive_handle_spelling"] for row in alias_rows if row["page_files"] > 0})
    cap_aliases = [row["archive_handle_spelling"] for row in alias_rows if row["suspected_truncated_at_page_cap"]]
    cap_ids = {row["stable_x_user_id"] for row in alias_rows if row["suspected_truncated_at_page_cap"]}
    page_number_gap_count = sum(bool(row["missing_page_numbers_within_range"]) for row in alias_rows)
    total_post_count = len(records)
    known_authored_replies = total_types["authored"] + total_types["reply"]
    known_author_text_nonempty = text_counts["authored"] + text_counts["reply"]
    text_coverage = 100 * known_author_text_nonempty / known_authored_replies if known_authored_replies else 0.0
    ambiguous_self = total_types["ambiguous_self_retweet"]
    ambiguous_self_nonempty = text_counts["ambiguous_self_retweet"]
    ambiguous_self_facets = mention_counts["ambiguous_self_source"]
    authored_sensitivity_high = known_authored_replies + ambiguous_self
    text_sensitivity_high = known_author_text_nonempty + ambiguous_self_nonempty

    first_visible = min(dated).date()
    last_visible = max(dated).date()
    total_authored_text_facets = mention_counts["author_text"]
    total_retweet_source_facets = mention_counts["retweet_source"]
    ambiguous_conflict_count = sum(record["type"] == "ambiguous_metadata" for record in records)
    page_error_count = sum(row["error_pages"] for row in alias_rows)
    n_reaching_cap = len(cap_ids)
    cap_names = ", ".join(sorted(cap_aliases, key=str.casefold)) or "无"
    density_active_text = f"{density_active:.4f}" if density_active is not None else "不适用（有边节点少于 2）"
    span_text = ", ".join(f"{count} 个月:{edges} 条边" for count, edges in sorted(edge_month_span_counts.items())) or "无边"
    conflicts_listing = ", ".join(f"{row['timeline_x_user_id']}:{row['tweet_id']}" for row in conflict_rows) or "无"

    report = f"""# FxEmbed 现存归档分析（仅本地文件、零新增请求）

## 数据范围与去重 / 分类口径

- 脚本仅读取 `fx_pilot_raw` 现存 JSON 与本地核验 CSV，未发起网络/API 请求。
- 原始分页记录 **{len(raw_entries):,}**；按 `(timeline 稳定 X user ID, tweet ID)` 去重后 **{total_post_count:,}**，重复行 **{duplicate_rows:,}**。核验样本为 **{len(confirmed)} 个 account_confirms pair、{len(exact_handles)} 个精确 handle 拼写、{len(handle_map)} 个大小写归一 handle、{n_sample} 个稳定 X user ID**。归档目录按拼写 **{all_aliases} 个**。所有记录的归档 owner 与核验 ID 一致；冲突 {len(owner_mismatches)}。
- 互斥分类为原创类（无转发/回复标记）、回复、转发、`ambiguous_self_retweet`、`ambiguous_metadata`。转发标记与回复同时出现时，转发优先；共有 {retweet_reply_overlap} 条。3 条（如实际不等于 3，以计算值为准）涉及“`reposted_by` 与空值冲突、且 source author/reposter 均为 timeline owner”的记录不按文件顺序裁决，单列为自转发歧义；所有重复版本的关键内容/目标字段均一致的前提下方按该规则分类。其它关键字段冲突会被标为 `ambiguous_metadata` 并排除于确定的作者文本与主图。冲突明细见 `duplicate_metadata_conflicts.csv`：{conflicts_listing}。
- **分类敏感性：**确定的原创/回复共 {known_authored_replies:,} 条，其中非空作者文本 {known_author_text_nonempty:,} 条（{text_coverage:.1f}%）。若把 {ambiguous_self:,} 条自转发歧义全部视为原创/回复一侧，则对应上界为 {authored_sensitivity_high:,} 条、非空文本 {text_sensitivity_high:,} 条；若视为转发，则转发数增加 {ambiguous_self:,}。歧义文本与 mention 不计入主口径。quote post 仍是作者发布文本，但引用对象文本不并入。

## 内容量与可用文本

| 互斥类别 | 去重记录 | 非空 `text` | 说明 |
|---|---:|---:|---|
| 原创类 | {total_types['authored']:,} | {text_counts['authored']:,} | 可作作者文本候选 |
| 回复 | {total_types['reply']:,} | {text_counts['reply']:,} | 回复文本；与原创类分开 |
| 转发 | {total_types['retweet']:,} | {text_counts['retweet']:,} | 只表示源帖 payload 可读，不是转发者创作 |
| 自转发歧义 | {ambiguous_self:,} | {ambiguous_self_nonempty:,} | 归属/类型不确定，主作者文本覆盖排除 |
| 其它元数据歧义 | {ambiguous_conflict_count:,} | {text_counts['ambiguous_metadata']:,} | 不进入确定文本/主图 |

在确定的原创/回复 {known_authored_replies:,} 条中，非空作者文本 {known_author_text_nonempty:,} 条；作者自写/回复文本含 **{total_authored_text_facets:,} 个** mention facet（出现在有 mention 的帖子中），转发源 payload 含 **{total_retweet_source_facets:,} 个** mention facet，后者不是转发者主动提及。转发源文本分析和转发者自身立场必须分开。

## 2026 UTC 日历月内容量

> 这只是归档中状态的发布月份，不是链上事件前 1–7 天预测窗。下面月份从本地归档可见时间范围连续列出；0 表示归档中该月没有记录，不证明账号当月没有发帖。

| UTC 月 | 原创类 | 回复 | 转发 | 自转发歧义 | 原创/回复非空作者文本 | 转发源非空文本 | 主动 mention facet 数 |
|---|---:|---:|---:|---:|---:|---:|---:|
{content_table}

归档可见时间为 **{first_visible} 至 {last_visible} UTC**；缺失/不可解析时间戳 {missing_timestamp} 条。完整月份表见 `monthly_content_counts.csv`；空值已写为 0。

## 样本内互动图（仅 12 个稳定 X ID，不含关注快照）

主图仅保留两端都在核验样本内的有向互动：转发者 → 源作者；回复者 → 被回复账号；引用者 → quote 源作者；原创/回复作者 → 自写文本中的 mention 目标。自环排除。转发源文本中的 mention 不算主动提及；自转发歧义不进入主图。

- 合并不同关系类型后的跨账号有向边：**{len(all_edges)}**；至少参与一条边的节点 **{len(incident_nodes)}/{n_sample}**（有出边 {len(out_nodes)}，有入边 {len(in_nodes)}）。按全部样本 ID 计算的有向密度 **{density_full:.4f}**；有边节点诱导密度 **{density_active_text}**。
- 跨月重复出现的同一有向边：**{persistent_edges}/{len(all_edges)}** 至少跨 2 个不同月份；边月跨度分布：{span_text}。主图自环候选（按关系类型）：{dict(self_loops) if self_loops else '无'}。
- 回复目标通过 handle 无法解析到样本的记录数：{sum(unresolved_reply_handles.values())}。每月表同时报告互动事件数和不同边数；无边月份显式补零。

| UTC 月 | 不同跨账号边 | 有边节点 | 转发边 | 回复边 | 引用边 | 主动提及边 |
|---|---:|---:|---:|---:|---:|---:|
{graph_table}

完整月度图表见 `monthly_sample_graph.csv`。当前 following/followers 快照未并入历史互动图。

## 最早可见日期、分页断档与截断风险

- 按稳定 X ID 汇总的账号覆盖表：`account_page_coverage.csv`；逐归档 handle 审计：`account_archive_alias_audit.csv`。页号范围内缺页的归档别名数 **{page_number_gap_count}**。
- 达到 {PAGE_CAP} 页、末页非空且仍有 bottom cursor 的归档别名涉及 **{n_reaching_cap} 个稳定 X ID**，别名数 {len(cap_aliases)}（{cap_names}）；这是**疑似触及分页上限/截断**，不是已证实漏抓。非满页但空末页不因 cursor 单独判截断。
- 可计算的连续页边界中，正向间隔 ≥30 天 **{over_30}** 个；最大正向观测间隔 **{max(positive_gaps, default=0):.1f} 天**。边界间隔仅是相邻归档页可见内容之间的时间跨度，不等于证明完整或缺失。
- 错误页总数 **{page_error_count}**。历史上 3 条 oEmbed 抽查只验证抽中的推文内容，不验证时间线完整性。

## 对链上预测任务的边界

本轮只能在本地归档粒度上报告 UTC 日历月内容量、互动边、可见起止日期和分页风险。当前本地链上表是**地址×月聚合**而非带时间戳的逐笔事件，因此无法将贴文严格截到每个预测时点之前，也无法计算交易后 1–7 天窗口的文本覆盖或历史 as-of 边。若后续取得逐笔事件，应先做时间对齐，再用作者文本/回复文本与转发源文本分开构造特征；当前样本内图结果不能替代全体社交图，也不能据此推断关注关系历史。
"""
    (OUT / "report.md").write_text(report, encoding="utf-8")

    print(f"Archived rows / unique owner+tweet / duplicate rows: {len(raw_entries)} / {len(records)} / {duplicate_rows}")
    print(f"Confirmed pairs / exact handles / normalized handles / stable IDs: {len(confirmed)} / {len(exact_handles)} / {len(handle_map)} / {n_sample}")
    print(f"Post types: {dict(total_types)}")
    print(f"Metadata conflict groups: {len(conflict_rows)}; sample graph edges/nodes/full density: {len(all_edges)}/{len(incident_nodes)}/{density_full:.6f}")
    print(f"Suspected truncation stable IDs / aliases: {n_reaching_cap} / {len(cap_aliases)}; page errors: {page_error_count}")
    print(f"Wrote local outputs under {OUT}")


if __name__ == "__main__":
    main()
