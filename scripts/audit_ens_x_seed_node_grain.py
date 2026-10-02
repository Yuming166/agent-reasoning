#!/usr/bin/env python3
"""Offline node-grain audit for the frozen ENS↔X seed crosswalk.

The legacy bidirectional_validation.csv has no ENS node column. Validation
status is joined to a frame row only when (address, handle) is unique in both
files. Ordered row position is never used to resolve duplicate identities.
This audit does not edit inputs, establish historical validity, or promote rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_BASE = Path("artifacts/ens_x_crosswalk")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"empty CSV: {path}")
        return list(reader)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm(value: str) -> str:
    return (value or "").strip().lower()


def row_identity(row: dict[str, str]) -> tuple[str, str]:
    return norm(row.get("address", "")), norm(row.get("handle", ""))


def ordered_identity_projection_sha256(rows: list[dict[str, str]]) -> str:
    payload = "\n".join("\t".join(row_identity(row)) for row in rows).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def align_validation_to_frame(
    frame: list[dict[str, str]], validation: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Attach validation fields only for unique address+handle keys.

    For duplicate keys, positional alignment is intentionally refused—even if
    ordered identity projections match—because validation lacks ENS node.
    """
    frame_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    validation_groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(frame):
        frame_groups[row_identity(row)].append(i)
    for i, row in enumerate(validation):
        validation_groups[row_identity(row)].append(i)

    aligned: list[dict[str, str]] = []
    for i, frame_row in enumerate(frame):
        key = row_identity(frame_row)
        f_positions = frame_groups[key]
        v_positions = validation_groups.get(key, [])
        if len(f_positions) == 1 and len(v_positions) == 1:
            validation_row = validation[v_positions[0]]
            aligned.append({
                **frame_row,
                **validation_row,
                "frame_row_index": str(i),
                "validation_row_index": str(v_positions[0]),
                "validation_linkage_status": "unique_address_handle_match",
            })
        else:
            if not v_positions:
                linkage = "validation_key_missing"
            elif len(f_positions) != len(v_positions):
                linkage = "duplicate_key_multiplicity_mismatch"
            else:
                linkage = "unverified_ambiguous_source_rows"
            aligned.append({
                **frame_row,
                "status": "",
                "reverse_name": "",
                "reverse_claimed": "",
                "namehash_matches_node": "",
                "addr_record_matches": "",
                "frame_row_index": str(i),
                "validation_row_index": "",
                "validation_linkage_status": linkage,
            })
    return aligned


def _candidate_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        norm(row.get("address", "")),
        norm(row.get("node", "")),
        norm(row.get("handle", "")),
        norm(row.get("transaction_hash", "")),
    )


def build_audit(
    frame: list[dict[str, str]],
    validation: list[dict[str, str]],
    sample: list[dict[str, str]],
    seed: list[dict[str, str]],
    hashes: dict[str, str] | None = None,
) -> dict:
    aligned = align_validation_to_frame(frame, validation)
    by_candidate: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in aligned:
        by_candidate[_candidate_key(row)].append(row)

    sample_by_id: dict[str, dict[str, str]] = {}
    for row in sample:
        pid = row.get("pair_id", "").strip()
        if not pid or pid in sample_by_id:
            raise ValueError(f"missing or duplicate sample pair_id: {pid!r}")
        sample_by_id[pid] = row

    pair_details: list[dict[str, str]] = []
    seed_details = []
    projection_matches = (
        len(frame) == len(validation)
        and [row_identity(row) for row in frame]
        == [row_identity(row) for row in validation]
    )
    for seed_row in seed:
        pair_ids = [x.strip() for x in seed_row.get("source_pair_ids", "").split(";") if x.strip()]
        exact_pairs = []
        for pair_id in pair_ids:
            source = sample_by_id.get(pair_id)
            if source is None:
                exact_pairs.append({"pair_id": pair_id, "resolution": "missing_sample_pair"})
                continue
            candidate_matches = by_candidate.get(_candidate_key(source), [])
            if len(candidate_matches) != 1:
                exact_pairs.append({
                    "pair_id": pair_id,
                    "resolution": "candidate_not_unique",
                    "candidate_match_count": len(candidate_matches),
                    "node": source.get("node", ""),
                    "account_verdict_in_source": source.get("verification_status", ""),
                })
                continue
            candidate = candidate_matches[0]
            linkage = candidate.get("validation_linkage_status", "")
            if linkage == "unique_address_handle_match":
                resolution = "exact_candidate_row_reconciled"
                linkage_class = "unique_key_match"
            elif projection_matches:
                resolution = "paired_row_position_unverified"
                linkage_class = "paired_row_position_unverified"
            else:
                resolution = "unverified_ambiguous_source_rows"
                linkage_class = "unverified_ambiguous_source_rows"
            pair_detail = {
                "pair_id": pair_id,
                "address": source.get("address", ""),
                "node": source.get("node", ""),
                "handle": source.get("handle", ""),
                "x_user_id": source.get("x_user_id", ""),
                "account_verdict_in_source": source.get("verification_status", ""),
                "account_evidence_note_in_source": source.get("evidence_note", ""),
                "node_level_ens_status": candidate.get("status", "") if linkage == "unique_address_handle_match" else "unverified",
                "reverse_name": candidate.get("reverse_name", "") if linkage == "unique_address_handle_match" else "",
                "reverse_claimed": candidate.get("reverse_claimed", "") if linkage == "unique_address_handle_match" else "",
                "namehash_matches_node": candidate.get("namehash_matches_node", "") if linkage == "unique_address_handle_match" else "",
                "addr_record_matches": candidate.get("addr_record_matches", "") if linkage == "unique_address_handle_match" else "",
                "frame_row_index": candidate.get("frame_row_index", ""),
                "validation_row_index": candidate.get("validation_row_index", ""),
                "validation_linkage_status": linkage,
                "linkage_class": linkage_class,
                "resolution": resolution,
            }
            pair_details.append(pair_detail)
            exact_pairs.append(pair_detail)

        resolved_pairs = [p for p in exact_pairs if p.get("resolution") == "exact_candidate_row_reconciled"]
        node_statuses = sorted({p["node_level_ens_status"] for p in resolved_pairs if p.get("node_level_ens_status")})
        summarized = sorted({x.strip() for x in seed_row.get("ens_evidence_statuses", "").split(";") if x.strip()})
        all_resolved = len(exact_pairs) == len(pair_ids) and all(
            p.get("resolution") == "exact_candidate_row_reconciled" for p in exact_pairs
        )
        seed_details.append({
            "address": seed_row.get("address", ""),
            "x_user_id": seed_row.get("x_user_id", ""),
            "handle_at_verification": seed_row.get("handle_at_verification", ""),
            "source_pair_ids": pair_ids,
            "source_pair_count": len(pair_ids),
            "account_evidence_date": seed_row.get("account_evidence_date", ""),
            "temporal_link_status": seed_row.get("temporal_link_status", ""),
            "seed_summarized_ens_statuses": summarized,
            "exact_source_node_ens_statuses": node_statuses,
            "seed_summary_matches_exact_source_nodes": all_resolved and summarized == node_statuses,
            "all_source_nodes_bidirectional_ok": all_resolved and bool(node_statuses)
                and all(s == "bidirectional_ok" for s in node_statuses),
            "account_side_source_verdicts": sorted({
                p.get("account_verdict_in_source", "") for p in exact_pairs
                if p.get("account_verdict_in_source", "")
            }),
            "source_pairs": exact_pairs,
        })

    validation_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    frame_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in validation:
        validation_groups[row_identity(row)].append(row)
    for row in frame:
        frame_groups[row_identity(row)].append(row)
    repeated_validation = [rows for rows in validation_groups.values() if len(rows) > 1]
    mixed_status_repeated = sum(len({r.get("status", "") for r in rows}) > 1 for rows in repeated_validation)
    unresolved_links = [p for p in pair_details if p["resolution"] != "exact_candidate_row_reconciled"]

    return {
        "audit": "offline_seed_node_grain_reconciliation_v2_fail_closed",
        "row_alignment": {
            "frame_rows": len(frame),
            "validation_rows": len(validation),
            "ordered_address_handle_projection_matches": projection_matches,
            "ordered_address_handle_projection_sha256_frame": ordered_identity_projection_sha256(frame),
            "ordered_address_handle_projection_sha256_validation": ordered_identity_projection_sha256(validation),
            "method": "validation status is joined only on unique (address, handle) keys; duplicate keys are not resolved by position",
            "limitation": "The validation CSV lacks ENS node. A matching ordered identity projection does not prove a node-level status for repeated keys.",
        },
        "validation_pair_key_diagnostics": {
            "unique_address_handle_keys": len(validation_groups),
            "repeated_address_handle_keys": len(repeated_validation),
            "extra_rows_in_repeated_keys": sum(len(rows) - 1 for rows in repeated_validation),
            "repeated_keys_with_mixed_status": mixed_status_repeated,
            "frame_validation_key_multiplicity_mismatches": sum(
                len(frame_groups.get(key, [])) != len(rows) for key, rows in validation_groups.items()
            ) + sum(key not in validation_groups for key in frame_groups),
        },
        "seed_counts": {
            "crosswalk_rows": len(seed),
            "unique_wallet_addresses": len({norm(r.get("address", "")) for r in seed}),
            "unique_stable_x_user_ids": len({r.get("x_user_id", "").strip() for r in seed}),
            "source_pair_rows_reconciled": len(pair_details) - len(unresolved_links),
            "source_pair_rows_node_status_unverified": len(unresolved_links),
            "source_pair_node_statuses": dict(Counter(p["node_level_ens_status"] for p in pair_details if p["node_level_ens_status"] != "unverified")),
            "seed_summary_mismatches": sum(not r["seed_summary_matches_exact_source_nodes"] for r in seed_details),
            "links_with_all_source_nodes_bidirectional_ok": sum(r["all_source_nodes_bidirectional_ok"] for r in seed_details),
        },
        "input_sha256": hashes or {},
        "seed_links": seed_details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--out", type=Path, help="Optional JSON report path; defaults to stdout")
    args = parser.parse_args()
    base = args.base
    files = {
        "frame": base / "pairs_stratified_frame.csv",
        "validation": base / "bidirectional_validation.csv",
        "sample": base / "verification_sample_v2_filled.csv",
        "seed": base / "two_graph_seed_20260925" / "crosswalk_confirmed_unique.csv",
    }
    hashes = {key: sha256(path) for key, path in files.items()}
    report = build_audit(*(read_csv(files[k]) for k in ("frame", "validation", "sample", "seed")), hashes)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
