#!/usr/bin/env python3
"""Rank a bounded follow-up list from fully adjudicated ENS↔X candidates.

Offline only. The frozen probability-sample summary is reported separately for
population-estimate availability; it is not a census prerequisite for ranking.
Only individually `account_confirms` rows with review provenance are eligible.
Rankings use measured in-window authored-post yield, interactions to other
confirmed IDs, and 2026 chain activity; they are a shortlist, not collection
authorization. No HTTP, RPC, or BigQuery access is performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REVIEW_REQUIRED = {
    "address", "x_user_id", "manual_verdict", "reviewer", "reviewed_at_utc",
    "evidence_seen_at_utc", "x_profile_evidence_url",
    "evidence_quote_or_capture_id", "evidence_verified_x_user_id", "review_notes",
}
REVIEW_STRATUM_COLUMNS = {"review_stratum", "sampling_stratum"}
EXPECTED_REVIEW_SAMPLE_ROWS = 60
EXPECTED_CANDIDATE_FRAME_ROWS = 231
EXPECTED_VERDICTS = {"account_confirms", "ens_only", "conflict", "unverifiable"}

METRIC_REQUIRED = {
    "address", "x_user_id", "window_start_utc", "window_end_utc",
    "authored_posts_in_window", "unique_confirmed_interaction_neighbors_in_window",
    "active_months_2026", "chain_events_2026",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_workbook_validation(validation: dict, workbook_path: Path) -> None:
    """Require the current full-frame validator to attest this exact workbook."""
    if validation.get("mode") != "offline_full_frame_review_workbook_validation_v1":
        raise ValueError("review validation report has an unexpected mode")
    if validation.get("row_count") != EXPECTED_CANDIDATE_FRAME_ROWS:
        raise ValueError("review validation report does not attest the 231-row frame")
    if validation.get("validation_errors") != []:
        raise ValueError("review validation report contains errors or is malformed")
    if not isinstance(validation.get("workbook_manifest_sha256"), str) or len(validation["workbook_manifest_sha256"]) != 64:
        raise ValueError("review validation report lacks a verified workbook manifest hash")
    if validation.get("workbook_sha256") != sha256(workbook_path):
        raise ValueError("review validation report does not match the reviewed-candidates file")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"empty CSV: {path}")
        return list(reader)


def parse_utc(value: str, label: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise ValueError(f"{label}: invalid ISO-8601 timestamp") from e
    if dt.tzinfo is None:
        raise ValueError(f"{label}: timestamp must include timezone")
    return dt.astimezone(timezone.utc)


def as_nonnegative_int(value: str, label: str) -> int:
    try:
        n = int(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"{label}: expected integer") from e
    if n < 0:
        raise ValueError(f"{label}: must be nonnegative")
    return n


def build_shortlist(review_rows: list[dict[str, str]], metrics_rows: list[dict[str, str]],
                    review_summary: dict, seed_x_user_ids: set[str],
                    window_start: str, window_end: str, limit: int) -> tuple[list[dict], dict]:
    # The 60-row probability sample estimates linkage quality in the 231-row
    # frame; it is not a census prerequisite for ranking individually adjudicated
    # rows. Keep estimate availability explicit, but gate each candidate on its
    # own account-side evidence and matching fixed-window metrics below.
    # Never trust a bare `review_complete` flag or a non-empty estimates object.
    # The upstream summarizer is expected to emit a verified frozen-manifest
    # result for exactly the 60-row probability sample and 231-row candidate
    # frame, with all four mutually exclusive verdict estimates. Ranking
    # individually confirmed rows remains possible when this population gate
    # is unavailable; only the population-estimate status is affected.
    probability_sample_complete = (
        review_summary.get("review_complete") is True
        and review_summary.get("review_rows") == EXPECTED_REVIEW_SAMPLE_ROWS
        and review_summary.get("frozen_manifest_sha256_verified") is True
        and not review_summary.get("validation_errors")
    )
    population = review_summary.get("population_estimates")
    categories = population.get("categories") if isinstance(population, dict) else None
    category_rates_valid = isinstance(categories, dict) and EXPECTED_VERDICTS.issubset(categories)
    if category_rates_valid:
        rates = []
        for verdict in EXPECTED_VERDICTS:
            entry = categories.get(verdict)
            rate = entry.get("estimated_population_rate") if isinstance(entry, dict) else None
            if not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 1:
                category_rates_valid = False
                break
            rates.append(float(rate))
        category_rates_valid = category_rates_valid and math.isclose(sum(rates), 1.0, rel_tol=1e-6, abs_tol=1e-6)
    population_estimate_available = (
        probability_sample_complete
        and isinstance(population, dict)
        and population.get("population_N") == EXPECTED_CANDIDATE_FRAME_ROWS
        and category_rates_valid
    )
    expected_start = parse_utc(window_start, "window_start")
    expected_end = parse_utc(window_end, "window_end")
    if expected_end <= expected_start:
        raise ValueError("window_end must be after window_start")
    if limit <= 0:
        raise ValueError("limit must be positive")

    if review_rows:
        missing = REVIEW_REQUIRED - set(review_rows[0])
        if missing:
            raise ValueError(f"review CSV missing columns: {sorted(missing)}")
        if not REVIEW_STRATUM_COLUMNS.intersection(review_rows[0]):
            raise ValueError(
                "review CSV must include review_stratum or sampling_stratum "
                "(the current 231-row v2 workbook uses sampling_stratum)"
            )
    if metrics_rows and not METRIC_REQUIRED.issubset(metrics_rows[0]):
        raise ValueError(f"metrics CSV missing columns: {sorted(METRIC_REQUIRED - set(metrics_rows[0]))}")

    confirmed: dict[tuple[str, str], dict[str, str]] = {}
    excluded = {
        "pending_or_nonconfirming": 0,
        "incomplete_evidence": 0,
        "evidence_x_user_id_mismatch": 0,
        "duplicate_pair": 0,
    }
    seen_account_pair: set[tuple[str, str]] = set()
    for r in review_rows:
        if r.get("manual_verdict", "").strip() != "account_confirms":
            excluded["pending_or_nonconfirming"] += 1
            continue
        address, uid = r.get("address", "").strip().lower(), r.get("x_user_id", "").strip()
        evidence_uid = r.get("evidence_verified_x_user_id", "").strip()
        evidence_ok = all(r.get(k, "").strip() for k in (
            "reviewer", "reviewed_at_utc", "evidence_seen_at_utc",
            "x_profile_evidence_url", "evidence_quote_or_capture_id", "review_notes"))
        try:
            stable_id = uid.isdigit() and int(uid) > 0
            parse_utc(r.get("reviewed_at_utc", ""), "reviewed_at_utc")
            parse_utc(r.get("evidence_seen_at_utc", ""), "evidence_seen_at_utc")
        except ValueError:
            stable_id = False
        if not (address.startswith("0x") and len(address) == 42 and stable_id and evidence_ok):
            excluded["incomplete_evidence"] += 1
            continue
        if evidence_uid != uid:
            excluded["evidence_x_user_id_mismatch"] += 1
            continue
        key = (address, uid)
        if key in seen_account_pair:
            excluded["duplicate_pair"] += 1
            continue
        seen_account_pair.add(key)
        confirmed[key] = r

    metric_by_pair: dict[tuple[str, str], dict[str, int]] = {}
    for r in metrics_rows:
        address, uid = r.get("address", "").strip().lower(), r.get("x_user_id", "").strip()
        key = (address, uid)
        if key not in confirmed:
            continue
        start = parse_utc(r.get("window_start_utc", ""), "metrics.window_start_utc")
        end = parse_utc(r.get("window_end_utc", ""), "metrics.window_end_utc")
        if start != expected_start or end != expected_end:
            raise ValueError(f"timeline metrics use a different window for {address}/{uid}")
        if key in metric_by_pair:
            raise ValueError(f"duplicate timeline metric row for {address}/{uid}")
        metric_by_pair[key] = {
            "authored_posts_in_window": as_nonnegative_int(r["authored_posts_in_window"], "authored_posts_in_window"),
            "unique_confirmed_interaction_neighbors_in_window": as_nonnegative_int(r["unique_confirmed_interaction_neighbors_in_window"], "unique_confirmed_interaction_neighbors_in_window"),
            "active_months_2026": as_nonnegative_int(r["active_months_2026"], "active_months_2026"),
            "chain_events_2026": as_nonnegative_int(r["chain_events_2026"], "chain_events_2026"),
        }

    scored = []
    missing_metrics = 0
    # Exclude IDs already in the seed and deduplicate multi-wallet users:
    # one stable X ID contributes at most one new timeline author. Select the
    # representative wallet only after joining metrics, rather than using the
    # review-frame's legacy events_2026 proxy (which could choose a wallet with
    # no fixed-window metrics and silently discard a fully measured sibling).
    confirmed_by_user: dict[str, list[tuple[tuple[str, str], dict[str, str], dict[str, int]]]] = {}
    unique_new_ids = {uid for _, uid in confirmed if uid not in seed_x_user_ids}
    for key, review in confirmed.items():
        uid = key[1]
        if uid in seed_x_user_ids:
            continue
        metric_row = metric_by_pair.get(key)
        if metric_row is not None:
            confirmed_by_user.setdefault(uid, []).append((key, review, metric_row))
    missing_metrics = sum(uid not in confirmed_by_user for uid in unique_new_ids)
    for uid, candidates in confirmed_by_user.items():
        # Text and interaction observations are attached to a stable X ID and
        # therefore must agree across wallet rows. A disagreement signals a
        # bad join/coverage artifact; do not cherry-pick the larger value.
        text_social = {
            (m["authored_posts_in_window"], m["unique_confirmed_interaction_neighbors_in_window"])
            for _, _, m in candidates
        }
        if len(text_social) != 1:
            raise ValueError(f"conflicting fixed-window X metrics across wallets for x_user_id={uid}")
        # These are wallet-level tie-break features. Prefer the most active
        # measured wallet; break ties deterministically by lowercase address.
        key, review, m = min(
            candidates,
            key=lambda item: (-item[2]["active_months_2026"],
                              -item[2]["chain_events_2026"], item[0][0]),
        )
        if m["authored_posts_in_window"] == 0 and m["unique_confirmed_interaction_neighbors_in_window"] == 0:
            continue
        scored.append({
            "address": key[0], "x_user_id": key[1],
            "review_stratum": review.get("review_stratum", "").strip()
            or review.get("sampling_stratum", "").strip(),
            "authored_posts_in_window": m["authored_posts_in_window"],
            "unique_confirmed_interaction_neighbors_in_window": m["unique_confirmed_interaction_neighbors_in_window"],
            "active_months_2026": m["active_months_2026"],
            "chain_events_2026": m["chain_events_2026"],
            "reviewer": review["reviewer"],
            "reviewed_at_utc": review["reviewed_at_utc"],
            "evidence_url": review["x_profile_evidence_url"],
            "score_basis": "measured_window_text_and_confirmed_id_interactions; chain activity tie-break",
            "collection_authorized": "false",
        })

    # Transparent, normalized equal-weight score for the two research outcomes.
    # Chain activity only breaks ties; no lifetime tweet counter is used.
    max_posts = max((r["authored_posts_in_window"] for r in scored), default=0)
    max_neighbors = max((r["unique_confirmed_interaction_neighbors_in_window"] for r in scored), default=0)
    for r in scored:
        text_norm = r["authored_posts_in_window"] / max_posts if max_posts else 0.0
        graph_norm = r["unique_confirmed_interaction_neighbors_in_window"] / max_neighbors if max_neighbors else 0.0
        r["text_coverage_component"] = round(text_norm, 6)
        r["connectivity_component"] = round(graph_norm, 6)
        r["selection_score_equal_weight"] = round((text_norm + graph_norm) / 2, 6)
    scored.sort(key=lambda r: (
        -r["selection_score_equal_weight"],
        -r["active_months_2026"], -r["chain_events_2026"], r["x_user_id"], r["address"],
    ))
    for rank, r in enumerate(scored, 1):
        r["rank"] = rank
        r["shortlist_selected"] = rank <= limit
    summary = {
        "mode": "offline_shortlist_only_no_collection_authorization",
        "window_start_utc": expected_start.isoformat().replace("+00:00", "Z"),
        "window_end_utc": expected_end.isoformat().replace("+00:00", "Z"),
        "probability_sample_review_rows": int(review_summary.get("review_rows", 0) or 0),
        "probability_sample_complete": probability_sample_complete,
        "population_estimate_available": population_estimate_available,
        "population_estimate_status": (
            "available_for_231_candidate_frame" if population_estimate_available
            else "unavailable_until_frozen_probability_sample_is_fully_adjudicated"
        ),
        "individually_confirmed_pairs": len(confirmed),
        "seed_x_user_ids_excluded": len(seed_x_user_ids),
        "eligible_unique_new_x_ids": len(unique_new_ids),
        "eligible_with_measured_window_metrics": len(scored),
        "missing_metrics_for_confirmed_pairs": missing_metrics,
        "shortlist_limit": limit,
        "shortlist_rows": min(limit, len(scored)),
        "excluded_review_rows": excluded,
        "score": "0.5 * normalized authored posts + 0.5 * normalized unique confirmed-ID interaction neighbors; chain months/events tie-break only",
        "limitations": [
            "Shortlist is not a crosswalk promotion or a collection authorization.",
            "Only individually account_confirms rows are eligible; pending/ENS-only/conflict/unverifiable rows are excluded.",
            "The account-side evidence must explicitly record the stable X ID checked, and it must equal the frozen row X ID.",
            "Text and interactions must be measured in exactly the frozen UTC window; profile lifetime counters are not used.",
            "Connectivity metric counts neighbors already confirmed in the supplied reviewed mapping; it is not graph completeness.",
            "The frozen stratified sample estimates linkage quality for the 231-pair frame; it is not required to rank independently adjudicated rows.",
            "Population-level weighted estimates remain unavailable until the frozen probability sample is fully adjudicated.",
            "The weighted review estimate describes the 231-pair candidate frame only and does not validate event-time as-of status.",
        ],
    }
    return scored[:limit], summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reviewed-candidates", type=Path, required=True)
    ap.add_argument(
        "--review-validation-json", type=Path, required=True,
        help="successful output of validate_ens_x_full_frame_review_workbook.py for this exact CSV",
    )
    ap.add_argument("--review-summary", type=Path, required=True)
    ap.add_argument("--seed-crosswalk", type=Path, required=True, help="confirmed seed CSV with x_user_id")
    ap.add_argument("--timeline-metrics", type=Path, required=True)
    ap.add_argument("--window-start-utc", required=True)
    ap.add_argument("--window-end-utc", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()
    seed_rows = read_csv(args.seed_crosswalk)
    if not seed_rows or "x_user_id" not in seed_rows[0]:
        raise ValueError("seed crosswalk must contain x_user_id")
    seed_ids = {r.get("x_user_id", "").strip() for r in seed_rows if r.get("x_user_id", "").strip().isdigit()}
    review_validation = json.loads(args.review_validation_json.read_text(encoding="utf-8"))
    verify_workbook_validation(review_validation, args.reviewed_candidates)
    rows, summary = build_shortlist(
        read_csv(args.reviewed_candidates), read_csv(args.timeline_metrics),
        json.loads(args.review_summary.read_text(encoding="utf-8")), seed_ids,
        args.window_start_utc, args.window_end_utc, args.limit,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["rank", "address", "x_user_id", "shortlist_selected"], extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    summary.update({
        "reviewed_candidates_sha256": sha256(args.reviewed_candidates),
        "review_validation_json_sha256": sha256(args.review_validation_json),
        "review_validation_verified": True,
        "review_summary_sha256": sha256(args.review_summary),
        "seed_crosswalk_sha256": sha256(args.seed_crosswalk),
        "timeline_metrics_sha256": sha256(args.timeline_metrics),
        "shortlist_sha256": sha256(args.out),
        "shortlist_path": str(args.out),
    })
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
