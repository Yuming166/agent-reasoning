#!/usr/bin/env python3
"""Turn a completed FxEmbed profile audit into a reviewable candidate crosswalk."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    source = root / "artifacts/ens_x_crosswalk"
    run = source / "profile_expansion_20260925"
    rows = [json.loads(line) for line in (run / "profile_audit_results.jsonl").read_text(encoding="utf-8").splitlines()]
    queue = json.loads((run / "candidate_queue.json").read_text(encoding="utf-8"))
    if len(rows) != len(queue) or len(rows) != 2000:
        raise RuntimeError(f"Incomplete frozen audit: {len(rows)} results, {len(queue)} queued")
    if len({row["handle_requested"].lower() for row in rows}) != len(rows):
        raise RuntimeError("Duplicate audited handles")
    result = []
    for row in rows:
        if row["classification"] != "account_side_exact_match_candidate":
            continue
        for pair in row["evidence_positive_pairs"]:
            hits = pair["hits"]
            result.append({
                "address": pair["address"].lower(),
                "x_user_id": str(row["x_user_id"]),
                "handle_at_profile_audit": row["screen_name"],
                "reverse_ens_name": pair["reverse_name"],
                "ens_record_set_at": pair["record_set_at"],
                "events_2026": pair["events_2026"],
                "selection_stratum": row["selection_stratum"],
                "evidence_fields": ";".join(sorted({hit["field"] for hit in hits})),
                "evidence_types": ";".join(sorted({hit["evidence_type"] for hit in hits})),
                "matched_terms": ";".join(sorted({hit["matched"] for hit in hits})),
                "profile_audit_at_utc": row["fetched_at_utc"],
                "profile_raw_file": row["raw_file"],
                "profile_raw_sha256": row["raw_sha256"],
                "review_status": "automatic_exact_match_requires_manual_audit",
                "historical_link_status": "snapshot_only_as_of_not_validated",
            })
    result.sort(key=lambda r: (r["x_user_id"], r["address"]))
    if len({(r["address"], r["x_user_id"]) for r in result}) != len(result):
        raise RuntimeError("Duplicate candidate wallet-X pairs")
    output = run / "account_side_exact_match_candidates.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_queue_handles": len(queue),
        "audited_handles": len(rows),
        "http_status": dict(Counter(str(r["http_status"]) for r in rows)),
        "classification": dict(Counter(r["classification"] for r in rows)),
        "by_selection_stratum": {stratum: dict(Counter(r["classification"] for r in rows
                                                   if r["selection_stratum"] == stratum))
                                 for stratum in sorted({r["selection_stratum"] for r in rows})},
        "candidate_wallet_x_pairs": len(result),
        "candidate_wallets": len({r["address"] for r in result}),
        "candidate_stable_x_user_ids": len({r["x_user_id"] for r in result}),
        "evidence_fields": dict(Counter(hit["field"] for r in rows
                                        for pair in r["evidence_positive_pairs"]
                                        for hit in pair["hits"])),
        "evidence_types": dict(Counter(hit["evidence_type"] for r in rows
                                         for pair in r["evidence_positive_pairs"]
                                         for hit in pair["hits"])),
        "limits": [
            "Automatic exact matches are candidates pending manual quality review.",
            "Account-side profile evidence is a current snapshot, not a historical as-of identity link.",
            "The 2000 handles are a mix of top-chain-activity and randomly sampled remaining active candidates; no population extrapolation is implied.",
            "HTTP 404 / unavailable profiles have unknown account-side evidence, not negative evidence.",
            "No timeline, following graph, or expanded chain graph is included in this profile audit.",
        ],
    }
    (run / "profile_audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
