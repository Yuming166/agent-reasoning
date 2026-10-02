#!/usr/bin/env python3
"""Offline verification of profile evidence leads for the frozen ENS-X 231 frame.

Reads only the frozen local candidate/review CSVs and already-captured profile
JSON. It makes no network requests and never writes adjudication fields or
changes the confirmed crosswalk. Outputs a provenance-bound lead table, not
identity decisions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone

CANDIDATE_SHA256 = "8871786e9b8897b7ba36b81c8218d862eb4248b1f43ff6cac61c48132a93c71d"
WORKBOOK_SHA256 = "b764ddafab49e1b6fe38b6f2b67ce5c4c5b65f406b607d8f50c481348cd26ec8"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def exact_term(text: str, term: str) -> bool:
    if not term:
        return False
    return re.search(r"(?<![a-z0-9._-])" + re.escape(term.lower()) +
                     r"(?![a-z0-9._-])", text.lower()) is not None


def scan(project: Path) -> tuple[list[dict[str, str]], dict]:
    base = project / "artifacts/ens_x_crosswalk"
    candidate_path = base / "expansion_decision_20260925/candidate_review_full_231.csv"
    workbook_path = base / "goal_audit_20260925/manual_review_workbook_231_v2.csv"
    candidate_rows, workbook_rows = read_csv(candidate_path), read_csv(workbook_path)
    if sha256(candidate_path) != CANDIDATE_SHA256:
        raise ValueError("frozen 231 candidate frame SHA-256 mismatch")
    if sha256(workbook_path) != WORKBOOK_SHA256:
        raise ValueError("frozen 231 review workbook SHA-256 mismatch")
    if len(candidate_rows) != 231 or len(workbook_rows) != 231:
        raise ValueError("expected exactly 231 frozen candidate and review rows")
    key = lambda r: (r["address"].strip().lower(), r["x_user_id"].strip())
    if len({key(r) for r in candidate_rows}) != 231 or len({key(r) for r in workbook_rows}) != 231:
        raise ValueError("duplicate or missing address/X-ID pair in frozen frame")
    workbook = {key(r): r for r in workbook_rows}
    if set(workbook) != {key(r) for r in candidate_rows}:
        raise ValueError("review workbook keys differ from frozen candidate frame")

    output: list[dict[str, str]] = []
    integrity = Counter()
    by_arm = Counter()
    for candidate in candidate_rows:
        pair = key(candidate)
        review = workbook[pair]
        if review.get("manual_verdict", "").strip() != "pending":
            raise ValueError(f"expected pending manual verdict for {pair}")
        raw_rel = Path(candidate["profile_raw_file"])
        raw_path = raw_rel if raw_rel.is_absolute() else project / raw_rel
        row: dict[str, str] = {
            "address": pair[0], "x_user_id": pair[1],
            "handle_at_profile_audit": candidate.get("handle_at_profile_audit", ""),
            "reverse_ens_name": candidate.get("reverse_ens_name", ""),
            "review_arm": review.get("review_arm", ""),
            "sampling_stratum": review.get("sampling_stratum", ""),
            "inclusion_probability": review.get("inclusion_probability", ""),
            "design_weight": review.get("design_weight", ""),
            "candidate_events_2026": candidate.get("events_2026", ""),
            "manual_verdict": "pending",
            "lead_status": "capture_missing_or_unreadable",
            "capture_fetched_at_utc": "", "capture_http_status": "",
            "capture_profile_url": "", "capture_x_user_id": "",
            "capture_id_matches_target": "false", "capture_sha256": "",
            "capture_hash_matches_candidate": "false",
            "wallet_address_hit_fields": "", "ens_name_hit_fields": "",
            "evidence_lead_type": "none", "tweet_count_profile_snapshot": "",
            "raw_profile_path": raw_rel.as_posix(),
            "candidate_profile_capture_sha256": candidate.get("profile_raw_sha256", ""),
            "adjudication": "not_adjudicated_manual_verdict_unchanged",
        }
        by_arm[review.get("review_arm", "")] += 1
        if not raw_path.is_file():
            integrity["capture_missing"] += 1
            output.append(row)
            continue
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            integrity["capture_unreadable"] += 1
            output.append(row)
            continue
        digest = sha256(raw_path)
        data = raw.get("data") if isinstance(raw, dict) else None
        user = data.get("user") if isinstance(data, dict) else None
        if not isinstance(user, dict):
            integrity["capture_no_user"] += 1
            output.append(row)
            continue
        row.update({
            "capture_fetched_at_utc": str(raw.get("fetched_at_utc") or ""),
            "capture_http_status": str(raw.get("http_status") or ""),
            "capture_profile_url": str(user.get("url") or ""),
            "capture_x_user_id": str(user.get("id") or ""),
            "capture_id_matches_target": str(str(user.get("id") or "") == pair[1]).lower(),
            "capture_sha256": digest,
            "capture_hash_matches_candidate": str(digest == candidate.get("profile_raw_sha256", "")).lower(),
            "tweet_count_profile_snapshot": str(user.get("tweets") or ""),
        })
        if row["capture_http_status"] != "200":
            integrity["capture_non_200"] += 1
            output.append(row)
            continue
        if row["capture_id_matches_target"] != "true":
            integrity["capture_id_mismatch"] += 1
            output.append(row)
            continue
        if row["capture_hash_matches_candidate"] != "true":
            integrity["capture_hash_mismatch"] += 1
            output.append(row)
            continue
        fields = {
            "display_name": str(user.get("name") or ""),
            "bio": str(user.get("description") or ""),
        }
        website = user.get("website") or {}
        if isinstance(website, dict):
            fields["website_url"] = str(website.get("url") or "")
            fields["website_display_url"] = str(website.get("display_url") or "")
        else:
            fields["website"] = str(website)
        address_hits = sorted(field for field, text in fields.items()
                              if exact_term(text, pair[0]))
        ens = candidate.get("reverse_ens_name", "").strip()
        ens_hits = sorted(field for field, text in fields.items()
                          if len(ens) >= 6 and exact_term(text, ens))
        row["wallet_address_hit_fields"] = ";".join(address_hits)
        row["ens_name_hit_fields"] = ";".join(ens_hits)
        if address_hits and ens_hits:
            row["evidence_lead_type"] = "profile_exact_wallet_and_ens"
        elif address_hits:
            row["evidence_lead_type"] = "profile_exact_full_wallet_address"
        elif ens_hits:
            row["evidence_lead_type"] = "profile_exact_reverse_ens_name"
        else:
            row["evidence_lead_type"] = "no_exact_term_in_captured_profile_fields"
        row["lead_status"] = "verified_capture_review_lead_only"
        integrity["verified_capture_id_and_hash"] += 1
        integrity[row["evidence_lead_type"]] += 1
        output.append(row)

    # Check the frozen sample/complement split; do not combine their estimates.
    arms = Counter(r["review_arm"] for r in output)
    if arms.get("stratified_probability_sample_60") != 60 or arms.get("targeted_nonprobability_complement_171") != 171:
        raise ValueError(f"frozen review-arm split changed: {dict(arms)}")
    lead_counts_by_arm = {}
    for arm in sorted(arms):
        selected = [r for r in output if r["review_arm"] == arm]
        lead_counts_by_arm[arm] = dict(Counter(r["evidence_lead_type"] for r in selected))
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_profile_capture_evidence_lead_screen_no_network_no_adjudication",
        "network_requests": 0, "paid_queries_usd": 0,
        "candidate_promotions": 0, "crosswalk_modified": False,
        "input_sha256": {
            "candidate_review_full_231.csv": sha256(candidate_path),
            "manual_review_workbook_231_v2.csv": sha256(workbook_path),
        },
        "rows": len(output), "review_arm_counts": dict(arms),
        "lead_counts_by_review_arm": lead_counts_by_arm,
        "integrity_and_lead_counts": dict(integrity),
        "manual_verdict_counts": dict(Counter(r["manual_verdict"] for r in output)),
        "weighted_estimate_allowed": False,
        "notes": [
            "Exact matches in captured X profile fields are leads for human adjudication, not identity verdicts.",
            "Only the 60-row frozen probability arm can support design-weighted estimation after valid manual adjudication; the 171-row targeted complement is separate.",
            "Profile tweet counts are snapshot metadata and do not establish timeline text coverage or historical completeness.",
            "No follower/following or interaction-edge data are inspected; this artifact cannot estimate cross-graph connectivity.",
            "No manual evidence URL, quote/capture adjudication, reviewer, or as-of status is added to the workbook.",
        ],
    }
    return output, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    out_dir = args.out_dir.resolve()
    rows, report = scan(project)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "profile_evidence_leads_231.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    report["output_csv_sha256"] = sha256(csv_path)
    report["output_csv"] = str(csv_path)

    # This separate triage view only sequences human review of the targeted
    # complement. It is not a probability sample or an acquisition list.
    targeted = [r for r in rows if r["review_arm"] == "targeted_nonprobability_complement_171"]
    targeted.sort(key=lambda r: (
        0 if "full_wallet_address" in r["evidence_lead_type"] else 1,
        -int(r["tweet_count_profile_snapshot"] or 0),
        -int(r["candidate_events_2026"] or 0),
        r["address"], r["x_user_id"],
    ))
    priority_rows = []
    for rank, row in enumerate(targeted, 1):
        priority_row = dict(row)
        priority_row["manual_review_priority_rank"] = str(rank)
        priority_row["priority_basis"] = "full_address_profile_hit_then_snapshot_tweet_count_then_chain_event_count"
        priority_rows.append(priority_row)
    priority_path = out_dir / "targeted_manual_review_priority_171.csv"
    if priority_rows:
        priority_fields = ["manual_review_priority_rank", "priority_basis", *list(rows[0])]
        with priority_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=priority_fields)
            writer.writeheader(); writer.writerows(priority_rows)
    report["targeted_manual_review_priority_csv"] = str(priority_path)
    report["targeted_manual_review_priority_csv_sha256"] = sha256(priority_path)
    report["priority_policy"] = "Manual-review sequencing only: exact full wallet-address profile lead first, then profile snapshot tweet count, then 2026 candidate chain event count. Not an identity decision, probability sample, graph-connectivity estimate, or authorization to fetch timelines."
    json_path = out_dir / "profile_evidence_leads_231.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path = out_dir / "profile_evidence_leads_231.md"
    counts = report["integrity_and_lead_counts"]
    lines = [
        "# Offline ENS-X profile evidence-lead screen (231 frozen candidates)", "",
        f"Generated UTC: `{report['generated_at_utc']}`", "",
        "> This is a local evidence-lead screen only. It makes no network/API requests, changes no verdict, and promotes no candidate.", "",
        "## Coverage", "",
        f"- Rows: {report['rows']}; frozen probability sample: {report['review_arm_counts'].get('stratified_probability_sample_60', 0)}; targeted non-probability complement: {report['review_arm_counts'].get('targeted_nonprobability_complement_171', 0)}.",
        f"- Verified capture ID and hash: {counts.get('verified_capture_id_and_hash', 0)}.",
        f"- Exact wallet-address leads: {counts.get('profile_exact_full_wallet_address', 0)} plus {counts.get('profile_exact_wallet_and_ens', 0)} with both terms.",
        f"- Exact ENS-name leads: {counts.get('profile_exact_reverse_ens_name', 0)} plus {counts.get('profile_exact_wallet_and_ens', 0)} with both terms.",
        f"- No exact term in captured fields: {counts.get('no_exact_term_in_captured_profile_fields', 0)}.",
        f"- Manual verdict counts: `{json.dumps(report['manual_verdict_counts'], ensure_ascii=False, sort_keys=True)}`.",
        f"- Probability-arm leads (60): `{json.dumps(report['lead_counts_by_review_arm'].get('stratified_probability_sample_60', {}), ensure_ascii=False, sort_keys=True)}`.",
        f"- Targeted complement leads (171): `{json.dumps(report['lead_counts_by_review_arm'].get('targeted_nonprobability_complement_171', {}), ensure_ascii=False, sort_keys=True)}`.",
        "- A separate 171-row human-review priority CSV is ordered by direct wallet-address profile hit, profile snapshot tweet count, then chain event count; it is not an acquisition list or identity decision.", "",
        "## Interpretation and limits", "",
    ]
    lines.extend(f"- {note}" for note in report["notes"])
    lines += ["", "## Provenance", "",
              f"- Candidate frame SHA-256: `{report['input_sha256']['candidate_review_full_231.csv']}`",
              f"- Frozen review workbook SHA-256: `{report['input_sha256']['manual_review_workbook_231_v2.csv']}`",
              f"- Lead CSV SHA-256: `{report['output_csv_sha256']}`",
              f"- Targeted review-priority CSV SHA-256: `{report['targeted_manual_review_priority_csv_sha256']}`", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "out_dir": str(out_dir),
                      "integrity_and_lead_counts": counts,
                      "network_requests": 0, "promotions": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
