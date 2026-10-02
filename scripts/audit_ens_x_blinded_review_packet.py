#!/usr/bin/env python3
"""Audit a legacy or stratified ENS-X account-evidence review packet.

This audit verifies structure, pinned source/key coverage, masking of selection
and enrichment fields, and (for v3) physical separation of the reviewer
handoff from the coordinator key. It does not establish identity or prove
that a human review occurred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.build_ens_x_blinded_review_packet import (
        ARMS, COORDINATOR_DIR, KEY_FIELDS, PACKET_FIELDS, REVIEWER_DIR,
        SCHEMA, read_csv, token_for,
    )
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from build_ens_x_blinded_review_packet import (
        ARMS, COORDINATOR_DIR, KEY_FIELDS, PACKET_FIELDS, REVIEWER_DIR,
        SCHEMA, read_csv, token_for,
    )

LEGACY_SCHEMA = "ens-x-blinded-manual-review-v2"
EXPECTED_COUNTS = {
    "stratified_probability_sample_60": 60,
    "targeted_nonprobability_complement_171": 171,
}
DIRECT_ID_FIELDS = ["address", "x_user_id", "handle_at_profile_audit", "x_profile_url"]
MASKED_DIMENSIONS = {
    "sampling arm/stratum/weight", "ENS candidate name/record", "chain activity",
    "automatic string matches", "AI outputs",
}
FORBIDDEN_FIELDS = {
    "review_arm", "candidate_selection_stratum", "sampling_stratum",
    "stratum_population_N", "stratum_sample_n", "inclusion_probability",
    "design_weight", "sampling_seed", "automatic_evidence_types_not_adjudication",
    "automatic_matched_terms_not_adjudication", "candidate_events_2026",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_issued_packet(packet_dir: Path, project_root: Path) -> dict[str, Any]:
    manifest_path = packet_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []
    schema = manifest.get("schema")
    is_v3 = schema == SCHEMA
    is_legacy = schema == LEGACY_SCHEMA
    if not (is_v3 or is_legacy):
        errors.append("unsupported_packet_schema")

    source_path = project_root / manifest.get("source_workbook", "")
    if not source_path.is_file():
        errors.append("source_workbook_missing")
        source_rows: list[dict[str, str]] = []
        source_hash = None
    else:
        _, source_rows = read_csv(source_path)
        source_hash = sha256_file(source_path)
        if source_hash != manifest.get("source_workbook_sha256"):
            errors.append("source_workbook_hash_mismatch")

    expected_total = sum(EXPECTED_COUNTS.values())
    if manifest.get("rows") != expected_total:
        errors.append("manifest_row_count_mismatch")
    if manifest.get("arm_counts") != EXPECTED_COUNTS:
        errors.append("manifest_arm_counts_mismatch")
    if manifest.get("reviewer_packet_fields") != PACKET_FIELDS:
        errors.append("manifest_reviewer_fields_mismatch")

    if is_v3:
        if manifest.get("identity_blinded") is not False:
            errors.append("identity_blinding_disclosure_missing_or_false")
        if manifest.get("direct_identity_fields_shared_for_adjudication") != DIRECT_ID_FIELDS:
            errors.append("direct_identity_field_disclosure_mismatch")
        if not MASKED_DIMENSIONS.issubset(set(manifest.get("blinded_to", []))):
            errors.append("manifest_blinded_dimensions_incomplete")
        layout = manifest.get("layout", {})
        if layout != {"reviewer_handoff": REVIEWER_DIR, "coordinator_only": COORDINATOR_DIR}:
            errors.append("packet_layout_mismatch")
        reviewer_dir = packet_dir / REVIEWER_DIR
        key_rel = manifest.get("coordinator_key_path", "")
        expected_key_rel = f"{COORDINATOR_DIR}/coordinator_key.csv"
        if key_rel != expected_key_rel:
            errors.append("coordinator_key_path_mismatch")
        reviewer_files = [f"{REVIEWER_DIR}/{f}" for f in ARMS.values()]
        instructions_rel = f"{REVIEWER_DIR}/REVIEW_INSTRUCTIONS.md"
        reviewer_manifest_rel = f"{REVIEWER_DIR}/manifest.json"
        required_files = [*reviewer_files, instructions_rel, reviewer_manifest_rel, expected_key_rel]
        manager_guide_rel = "DATA_MANAGER_IMPORT_GUIDE.md"
        manager_guide = packet_dir / manager_guide_rel
        if manager_guide.is_file() or manager_guide_rel in manifest.get("files_sha256", {}):
            required_files.append(manager_guide_rel)
        if manager_guide.is_file() and manager_guide.resolve().is_relative_to(reviewer_dir.resolve()):
            errors.append("data_manager_guide_inside_reviewer_handoff")
        if (packet_dir / expected_key_rel).is_relative_to(reviewer_dir):
            errors.append("coordinator_key_inside_reviewer_handoff")
        reviewer_manifest_path = packet_dir / reviewer_manifest_rel
        if reviewer_manifest_path.is_file():
            rm = json.loads(reviewer_manifest_path.read_text(encoding="utf-8"))
            if rm.get("schema") != SCHEMA or rm.get("identity_blinded") is not False:
                errors.append("reviewer_manifest_identity_disclosure_mismatch")
            if rm.get("direct_identity_fields_shared_for_adjudication") != DIRECT_ID_FIELDS:
                errors.append("reviewer_manifest_direct_identity_field_mismatch")
            if set(rm.get("files_sha256", {})) != {*ARMS.values(), "REVIEW_INSTRUCTIONS.md"}:
                errors.append("reviewer_manifest_file_set_mismatch")
        else:
            errors.append("reviewer_manifest_missing")
        if set(manifest.get("files_sha256", {})) != set(required_files):
            errors.append("manifest_file_set_mismatch")
        paths_by_filename = {Path(rel).name: rel for rel in required_files}
        reviewer_paths = {arm: packet_dir / REVIEWER_DIR / filename for arm, filename in ARMS.items()}
        key_path = packet_dir / expected_key_rel
        for rel in required_files:
            path = packet_dir / rel
            if not path.is_file():
                errors.append(f"packet_file_missing:{rel}")
            elif sha256_file(path) != manifest.get("files_sha256", {}).get(rel):
                errors.append(f"packet_file_hash_mismatch:{rel}")
        if reviewer_dir.exists():
            actual_key = packet_dir / expected_key_rel
            if actual_key.exists() and actual_key.resolve().is_relative_to(reviewer_dir.resolve()):
                errors.append("coordinator_key_inside_reviewer_handoff")
        coordinator_key_separated = key_path.is_file() and not key_path.resolve().is_relative_to(reviewer_dir.resolve())
        coordinator_dir = packet_dir / COORDINATOR_DIR
        permissions_ok = False
        if key_path.is_file() and coordinator_dir.is_dir():
            key_mode = stat.S_IMODE(key_path.stat().st_mode)
            dir_mode = stat.S_IMODE(coordinator_dir.stat().st_mode)
            permissions_ok = (key_mode & 0o077) == 0 and (dir_mode & 0o077) == 0
            if not permissions_ok:
                errors.append("coordinator_key_permissions_too_open")
        else:
            errors.append("coordinator_key_or_private_directory_missing")
    elif is_legacy:
        reviewer_dir = packet_dir
        key_path = packet_dir / "coordinator_key.csv"
        reviewer_paths = {arm: packet_dir / filename for arm, filename in ARMS.items()}
        required_files = [*ARMS.values(), "coordinator_key.csv", "REVIEW_INSTRUCTIONS.md"]
        if set(manifest.get("files_sha256", {})) != set(required_files):
            errors.append("manifest_file_set_mismatch")
        for rel in required_files:
            path = packet_dir / rel
            if not path.is_file():
                errors.append(f"packet_file_missing:{rel}")
            elif sha256_file(path) != manifest.get("files_sha256", {}).get(rel):
                errors.append(f"packet_file_hash_mismatch:{rel}")
        hidden = set(manifest.get("hidden_from_reviewer", []))
        if not MASKED_DIMENSIONS.issubset(hidden):
            errors.append("manifest_hidden_categories_incomplete")
        warnings.append("legacy_packet_exposes_direct_identity_fields_without_explicit_identity_blinding_disclosure")
        coordinator_key_separated = False
        permissions_ok = None
    else:
        reviewer_paths = {arm: packet_dir / filename for arm, filename in ARMS.items()}
        key_path = packet_dir / "coordinator_key.csv"
        coordinator_key_separated = False
        permissions_ok = None

    source_by_pair: dict[tuple[str, str], dict[str, str]] = {}
    for row in source_rows:
        pair = (row.get("address", "").strip().lower(), row.get("x_user_id", "").strip())
        if pair in source_by_pair:
            errors.append("duplicate_source_pair")
        source_by_pair[pair] = row
    if len(source_rows) != expected_total:
        errors.append("source_workbook_row_count_mismatch")

    key_by_token: dict[str, dict[str, str]] = {}
    if key_path.is_file():
        key_fields, key_rows = read_csv(key_path)
        if key_fields != KEY_FIELDS:
            errors.append("coordinator_key_schema_mismatch")
        for key in key_rows:
            token = key.get("review_token", "")
            if not token or token in key_by_token:
                errors.append("duplicate_or_empty_review_token_in_key")
            key_by_token[token] = key
        if len(key_rows) != expected_total:
            errors.append("coordinator_key_row_count_mismatch")
        for pair, source in source_by_pair.items():
            token = token_for(source_hash or "", *pair)
            key = key_by_token.get(token)
            if key is None:
                errors.append("source_pair_missing_from_coordinator_key")
                continue
            if key.get("address", "").strip().lower() != pair[0] or key.get("x_user_id", "").strip() != pair[1]:
                errors.append("coordinator_key_identity_mismatch")
            for field in KEY_FIELDS:
                if field != "review_token" and key.get(field, "") != source.get(field, ""):
                    errors.append(f"coordinator_key_source_mismatch:{field}")
                    break

    seen_tokens: set[str] = set()
    seen_pairs: dict[str, set[tuple[str, str]]] = {arm: set() for arm in ARMS}
    arm_counts: Counter[str] = Counter()
    for arm, filename in ARMS.items():
        path = reviewer_paths[arm]
        if not path.is_file():
            continue
        fields, rows = read_csv(path)
        if fields != PACKET_FIELDS:
            errors.append(f"reviewer_schema_mismatch:{filename}")
        if set(fields) & FORBIDDEN_FIELDS:
            errors.append("reviewer_packet_leaks_blinded_fields")
        if len(rows) != EXPECTED_COUNTS[arm]:
            errors.append(f"reviewer_row_count_mismatch:{filename}")
        sequences: list[int] = []
        for row in rows:
            token = row.get("review_token", "")
            if not token or token in seen_tokens:
                errors.append("duplicate_or_empty_review_token_in_packets")
            seen_tokens.add(token)
            key = key_by_token.get(token)
            if key is None:
                errors.append("packet_token_missing_from_key")
                continue
            if key.get("review_arm") != arm:
                errors.append("packet_row_in_wrong_arm")
            pair = (row.get("address", "").strip().lower(), row.get("x_user_id", "").strip())
            seen_pairs[arm].add(pair)
            arm_counts[arm] += 1
            source = source_by_pair.get(pair)
            if source is None:
                errors.append("packet_pair_missing_from_source")
                continue
            if token_for(source_hash or "", *pair) != token:
                errors.append("packet_token_identity_mismatch")
            expected_url = source.get("x_profile_url_from_stable_id", f"https://x.com/i/user/{pair[1]}")
            if row.get("handle_at_profile_audit", "") != source.get("handle_at_profile_audit", ""):
                errors.append("packet_handle_mismatch")
            if row.get("x_profile_url", "") != expected_url:
                errors.append("packet_profile_url_mismatch")
            try:
                sequences.append(int(row.get("review_sequence", "")))
            except ValueError:
                errors.append("invalid_review_sequence")
        if sorted(sequences) != list(range(1, len(rows) + 1)):
            errors.append(f"noncontiguous_review_sequence:{filename}")
        key_arm_pairs = {
            (k.get("address", "").strip().lower(), k.get("x_user_id", "").strip())
            for k in key_by_token.values() if k.get("review_arm") == arm
        }
        if seen_pairs[arm] != key_arm_pairs:
            errors.append(f"arm_membership_mismatch:{arm}")

    if len(seen_tokens) != expected_total or len(key_by_token) != expected_total:
        errors.append("packet_key_token_cover_mismatch")
    if manifest.get("network_requests") != 0 or manifest.get("paid_queries_usd") != 0:
        errors.append("unexpected_network_or_paid_query_claim")

    return {
        "mode": f"offline_account_evidence_packet_integrity_audit_{'v3' if is_v3 else 'legacy_v2' if is_legacy else 'unknown'}",
        "packet_dir": str(packet_dir),
        "source_workbook": manifest.get("source_workbook"),
        "source_workbook_sha256_verified": bool(source_hash and source_hash == manifest.get("source_workbook_sha256")),
        "row_count": len(seen_tokens),
        "arm_counts": dict(arm_counts),
        "coordinator_key_rows": len(key_by_token),
        "manifest_file_hashes_verified": not any(e.startswith(("packet_file_hash_mismatch:", "packet_file_missing:")) for e in errors),
        "reviewer_packets_exclude_blinded_fields": not any(e == "reviewer_packet_leaks_blinded_fields" for e in errors),
        "identity_blinded": False if is_v3 or is_legacy else None,
        "direct_identity_fields_shared_for_adjudication": DIRECT_ID_FIELDS if is_v3 or is_legacy else [],
        "coordinator_key_separated_from_reviewer_handoff": coordinator_key_separated,
        "coordinator_key_private_permissions_verified": permissions_ok,
        "network_requests": 0,
        "paid_queries_usd": 0,
        "review_verdicts": "not adjudicated by this audit",
        "warnings": warnings,
        "errors": sorted(set(errors)),
        "valid": not errors,
        "interpretation": "Structural/integrity audit only. Identity fields are intentionally visible to reviewers; selection and enrichment cues are masked. This does not establish account-side ownership evidence, historical identity validity, or completed human review.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit_issued_packet(args.packet_dir.resolve(), args.project_root.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "rows": report["row_count"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
