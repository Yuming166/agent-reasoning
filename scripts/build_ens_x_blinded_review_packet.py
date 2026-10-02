#!/usr/bin/env python3
"""Create/import a resumable offline ENS-X account-evidence review packet.

This is blinded to sampling design and enrichment/automatic cues, NOT to
identity: reviewers must see the candidate wallet and target X account to
judge account-side evidence. Coordinator-only sampling metadata is stored
separately from the reviewer handoff. No network/API calls are made.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
from collections import Counter
from pathlib import Path

REVIEWER_DIR = "reviewer_handoff"
COORDINATOR_DIR = "coordinator_only"
SCHEMA = "ens-x-stratified-account-evidence-review-v3"
ARMS = {
    "stratified_probability_sample_60": "probability_sample_for_review.csv",
    "targeted_nonprobability_complement_171": "targeted_complement_for_review.csv",
}
REVIEW_FIELDS = [
    "manual_verdict", "x_profile_evidence_url", "evidence_quote_or_capture_id",
    "evidence_verified_x_user_id", "evidence_seen_at_utc", "reviewer", "reviewed_at_utc", "review_notes",
]
PACKET_FIELDS = [
    "review_token", "review_sequence", "address", "x_user_id", "handle_at_profile_audit",
    "x_profile_url", *REVIEW_FIELDS,
]
KEY_FIELDS = [
    "review_token", "review_order", "review_arm", "address", "x_user_id",
    "candidate_selection_stratum", "sampling_stratum", "stratum_population_N",
    "stratum_sample_n", "inclusion_probability", "design_weight", "sampling_seed",
    "automatic_evidence_types_not_adjudication", "automatic_matched_terms_not_adjudication",
    "candidate_events_2026",
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            raise ValueError(f"empty CSV: {path}")
        return list(r.fieldnames), list(r)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def token_for(source_hash: str, address: str, x_user_id: str) -> str:
    material = f"ens-x-blind-review-v1\0{source_hash}\0{address.lower()}\0{x_user_id}"
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def generate(workbook: Path, out_dir: Path) -> dict:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty; refusing to overwrite: {out_dir}")
    fields, rows = read_csv(workbook)
    required = (set(KEY_FIELDS) - {"review_token"}) | {"handle_at_profile_audit", "x_profile_url_from_stable_id", "review_state"}
    missing = required - set(fields)
    if missing:
        raise ValueError(f"workbook missing fields: {sorted(missing)}")
    if len(rows) != 231:
        raise ValueError(f"expected 231 rows, got {len(rows)}")
    counts = Counter(r["review_arm"] for r in rows)
    if counts != Counter({"stratified_probability_sample_60": 60,
                          "targeted_nonprobability_complement_171": 171}):
        raise ValueError(f"unexpected review-arm partition: {dict(counts)}")
    pairs = [(r["address"].strip().lower(), r["x_user_id"].strip()) for r in rows]
    if len(set(pairs)) != 231 or any(not re.fullmatch(r"0x[0-9a-f]{40}", a) or not x.isdigit() for a, x in pairs):
        raise ValueError("invalid or duplicate address/stable-ID pair")
    if any(r.get("manual_verdict", "pending").strip() not in {"", "pending"} for r in rows):
        raise ValueError("workbook has adjudications; create a resume packet from pending rows explicitly")

    src_hash = hashlib.sha256(workbook.read_bytes()).hexdigest()
    rng = random.Random(int(src_hash[:16], 16))
    packet_rows: dict[str, list[dict[str, str]]] = {arm: [] for arm in ARMS}
    key_rows = []
    for r in rows:
        address, uid = r["address"].strip().lower(), r["x_user_id"].strip()
        token = token_for(src_hash, address, uid)
        packet_rows[r["review_arm"]].append({
            "review_token": token, "review_sequence": "", "address": address,
            "x_user_id": uid, "handle_at_profile_audit": r.get("handle_at_profile_audit", ""),
            "x_profile_url": r.get("x_profile_url_from_stable_id", f"https://x.com/i/user/{uid}"),
            **{f: r.get(f, "") or ("pending" if f == "manual_verdict" else "") for f in REVIEW_FIELDS},
        })
        key_rows.append({"review_token": token, **{k: r.get(k, "") for k in KEY_FIELDS if k != "review_token"}})
    for packet in packet_rows.values():
        rng.shuffle(packet)
        for i, row in enumerate(packet, 1):
            row["review_sequence"] = str(i)

    out_dir.mkdir(parents=True, exist_ok=True)
    reviewer_dir = out_dir / REVIEWER_DIR
    coordinator_dir = out_dir / COORDINATOR_DIR
    reviewer_dir.mkdir(mode=0o700)
    coordinator_dir.mkdir(mode=0o700)
    reviewer_dir.chmod(0o700)
    coordinator_dir.chmod(0o700)
    file_hashes: dict[str, str] = {}
    for arm, filename in ARMS.items():
        rel = f"{REVIEWER_DIR}/{filename}"
        file_hashes[rel] = write_csv(out_dir / rel, PACKET_FIELDS, packet_rows[arm])
    key_rel = f"{COORDINATOR_DIR}/coordinator_key.csv"
    file_hashes[key_rel] = write_csv(out_dir / key_rel, KEY_FIELDS, key_rows)
    (out_dir / key_rel).chmod(0o600)

    instructions = (
        "# ENS–X 账号侧证据人工复核（分层信息盲化；身份不盲）\n\n"
        "## 身份与保密边界\n"
        "本复核包**不是身份盲化**：复核者会看到目标钱包地址、稳定 X 用户 ID、handle 和 profile 链接，因为这些信息是判断账号侧声明是否对应候选钱包所必需的。"
        "包仅对抽样组别、抽样权重、ENS 候选记录、链上活动、自动匹配和 AI 输出盲化。数据管理员不得把 `coordinator_only/` 或根目录审计 manifest 发给复核者；只分发整个 `reviewer_handoff/` 文件夹。\n\n"
        "## 执行顺序与统计边界\n"
        "先完成 `probability_sample_for_review.csv`（冻结 60 条概率样本），再复核 `targeted_complement_for_review.csv`（171 条定向补充样本）。"
        "两组分别保存、分别报告；只有前者可用于本 231 条候选框的设计加权估计，不能把定向组并入加权分母。不要查看或索取 coordinator key。\n\n"
        "## 裁决规则\n"
        "逐行检查稳定 X ID 对应账号的公开资料和账号侧内容。只有 X 账号侧明确发布/展示可核对的钱包地址，或明确写出可核对的 ENS 名，才可记 `account_confirms`。"
        "若证据提及 ENS 名，请在证据摘录/备注中记录账号侧实际写出的完整名称；不能以昵称相似、ENS 侧记录或自动命中替代账号侧证据。"
        "仅 ENS 侧证据记 `ens_only`；证据不足/不可访问记 `unverifiable`；账号侧相互矛盾的证据记 `conflict`。账号存在、profile bio 中无地址/ENS 的一般介绍、关注关系或转发原帖均不自动等于确认。\n\n"
        "## 必填证据与时间\n"
        "对 `account_confirms`/`conflict` 填证据 URL、简短原文或耐久 capture ID、证据页面/内容绑定的稳定数字 X 用户 ID（必须与本行目标 ID 完全一致）、证据查看 UTC 时间、复核者和复核 UTC 时间。"
        "该 ID 必须从证据页面/内容核验，不得仅抄本行目标 ID；备注说明核验方式、被确认对象是直接地址还是 ENS 名，并记录可见的原帖/资料发布日期。"
        "这是当前账号侧证据裁决，不代表钱包—账号链接在任何历史预测时点有效；历史 as-of 必须另行重建。仅保留最小必要文本并遵守适用数据政策。\n\n"
        "复核后由数据管理员使用 `scripts/build_ens_x_blinded_review_packet.py --import-reviewed ...` 导入到新工作簿（不要覆盖源文件），再运行 `scripts/validate_ens_x_full_frame_review_workbook.py`。\n\n"
        "数据管理员的完整分阶段导入、恢复和校验命令见复核包根目录 `DATA_MANAGER_IMPORT_GUIDE.md`；该指南、`coordinator_only/` 和根目录 manifest 不得分发给复核者。\n"
    )
    instruction_path = reviewer_dir / "REVIEW_INSTRUCTIONS.md"
    instruction_path.write_text(instructions, encoding="utf-8")
    file_hashes[f"{REVIEWER_DIR}/REVIEW_INSTRUCTIONS.md"] = hashlib.sha256(instruction_path.read_bytes()).hexdigest()

    masked_dimensions = ["sampling arm/stratum/weight", "ENS candidate name/record", "chain activity",
                         "automatic string matches", "AI outputs"]
    direct_identity_fields = ["address", "x_user_id", "handle_at_profile_audit", "x_profile_url"]
    reviewer_manifest = {
        "schema": SCHEMA,
        "rows": len(rows),
        "arm_counts": dict(counts),
        "randomized_within_arm": True,
        "reviewer_packet_fields": PACKET_FIELDS,
        "identity_blinded": False,
        "direct_identity_fields_shared_for_adjudication": direct_identity_fields,
        "blinded_to": masked_dimensions,
        "files_sha256": {Path(k).name: v for k, v in file_hashes.items() if k.startswith(REVIEWER_DIR + "/")},
        "interpretation": "Review account-side public evidence only. Identity is intentionally visible; sampling design and enrichment/automated cues are hidden. The 60-row probability arm alone supports the design-weighted 231-frame estimate; report the 171-row targeted arm separately.",
    }
    reviewer_manifest_path = reviewer_dir / "manifest.json"
    reviewer_manifest_path.write_text(json.dumps(reviewer_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    file_hashes[f"{REVIEWER_DIR}/manifest.json"] = hashlib.sha256(reviewer_manifest_path.read_bytes()).hexdigest()

    manager_guide = (
        "# Coordinator-only import guide\n\n"
        "Do not distribute this file, the packet-root manifest, or `coordinator_only/` to reviewers. "
        "The immutable baseline is the `source_workbook` recorded in the adjacent packet-root `manifest.json`; "
        "use that exact file for every import, including resumes.\n\n"
        "Import each returned arm to a fresh output path with `scripts/build_ens_x_blinded_review_packet.py`, "
        "passing `--workbook <immutable-baseline>`, `--coordinator-key <packet>/coordinator_only/coordinator_key.csv`, "
        "`--manifest <packet>/manifest.json`, `--import-reviewed <one canonical arm CSV>`, and `--out-workbook <new path>`. "
        "The importer creates an adjacent `.receipt.json`; preserve it with the workbook. For a later arm, pass "
        "`--existing-workbook <prior importer output>` while keeping `--workbook` set to the original baseline. "
        "Never overwrite an output, edit an interim workbook, or import the same arm twice.\n\n"
        "Then run `scripts/validate_ens_x_full_frame_review_workbook.py` against the frozen candidate, probability sample, "
        "sampling manifest, targeted queue, and queue report used to construct the baseline workbook. Obtain these paths "
        "and the expected baseline-manifest SHA-256 from the coordinator's frozen-frame audit; do not infer or refresh "
        "them from reviewer submissions. Only the completed probability arm can support the design-weighted estimate; "
        "the targeted complement remains separate. Current account-side evidence is not historical as-of validity.\n"
    )
    manager_guide_path = out_dir / "DATA_MANAGER_IMPORT_GUIDE.md"
    manager_guide_path.write_text(manager_guide, encoding="utf-8")
    file_hashes["DATA_MANAGER_IMPORT_GUIDE.md"] = hashlib.sha256(manager_guide_path.read_bytes()).hexdigest()

    manifest = {
        **reviewer_manifest,
        "source_workbook": str(workbook),
        "source_workbook_sha256": src_hash,
        "layout": {"reviewer_handoff": REVIEWER_DIR, "coordinator_only": COORDINATOR_DIR},
        "coordinator_key_path": key_rel,
        "files_sha256": file_hashes,
        "network_requests": 0,
        "paid_queries_usd": 0,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for path in out_dir.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
        elif path.is_dir():
            path.chmod(0o700)
    out_dir.chmod(0o700)
    return manifest


def import_reviewed(
    workbook: Path, key_path: Path, manifest_path: Path, packet_paths: list[Path], out: Path,
    existing_workbook: Path | None = None,
) -> dict:
    """Import one or more arm packets, optionally resuming from a receipt-bound output.

    ``workbook`` is always the immutable baseline used to generate the packet. A
    resumed output must have the adjacent ``.receipt.json`` created here; this
    prevents silently trusting an edited interim adjudication.
    """
    if out.exists():
        raise FileExistsError(f"refusing to overwrite: {out}")
    fields, baseline_rows = read_csv(workbook)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(workbook.read_bytes()).hexdigest()
    if manifest.get("source_workbook_sha256") != source_hash:
        raise ValueError("workbook hash differs from blinded packet manifest source")
    kfields, keys = read_csv(key_path)
    key_hash = hashlib.sha256(key_path.read_bytes()).hexdigest()
    key_manifest_path = manifest.get("coordinator_key_path", "coordinator_key.csv")
    pinned_key_hash = manifest.get("files_sha256", {}).get(key_manifest_path)
    # Legacy v2 manifests stored the key under the basename in a flat folder.
    if pinned_key_hash is None and key_manifest_path == "coordinator_key.csv":
        pinned_key_hash = manifest.get("files_sha256", {}).get("coordinator_key.csv")
    if pinned_key_hash != key_hash:
        raise ValueError("coordinator key hash differs from account-evidence packet manifest")
    if not set(REVIEW_FIELDS).issubset(fields) or not {"review_token", "review_arm", "address", "x_user_id"}.issubset(kfields):
        raise ValueError("workbook/key schema mismatch")
    key_by_token = {k["review_token"]: k for k in keys}
    if len(key_by_token) != len(keys) or len(keys) != len(baseline_rows):
        raise ValueError("coordinator key must uniquely cover every workbook row")
    baseline_by_pair = {(r["address"].strip().lower(), r["x_user_id"].strip()): r for r in baseline_rows}
    if len(baseline_by_pair) != len(baseline_rows):
        raise ValueError("duplicate workbook pairs")
    for pair, row in baseline_by_pair.items():
        token = token_for(source_hash, *pair)
        key = key_by_token.get(token)
        if key is None or key.get("address", "").lower() != pair[0] or key.get("x_user_id") != pair[1]:
            raise ValueError("coordinator key does not exactly map to the source workbook")
        for f in KEY_FIELDS:
            if f != "review_token" and key.get(f, "") != row.get(f, ""):
                raise ValueError(f"coordinator key/source workbook mismatch: {f}")
    rows = [dict(r) for r in baseline_rows]
    if existing_workbook is not None:
        receipt_path = Path(str(existing_workbook) + ".receipt.json")
        if not receipt_path.is_file():
            raise ValueError("existing interim workbook has no import receipt")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        existing_hash = hashlib.sha256(existing_workbook.read_bytes()).hexdigest()
        if receipt.get("output_sha256") != existing_hash:
            raise ValueError("existing interim workbook hash differs from import receipt")
        if (receipt.get("source_workbook_sha256") != source_hash
                or receipt.get("packet_manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                or receipt.get("coordinator_key_sha256") != key_hash):
            raise ValueError("existing interim receipt is not bound to this baseline packet/key")
        prior_arms = receipt.get("imported_arms", {})
        if not isinstance(prior_arms, dict):
            raise ValueError("invalid imported_arms in interim receipt")
        _, existing_rows = read_csv(existing_workbook)
        if len(existing_rows) != len(baseline_rows) or any(list(r.keys()) != fields for r in existing_rows):
            raise ValueError("existing interim workbook schema/row count differs from baseline")
        immutable_fields = [f for f in fields if f not in set(REVIEW_FIELDS) | {"review_state"}]
        baseline_index = {(r["address"].lower(), r["x_user_id"]): r for r in baseline_rows}
        existing_index = {(r["address"].lower(), r["x_user_id"]): r for r in existing_rows}
        if set(existing_index) != set(baseline_index):
            raise ValueError("existing interim identity set differs from baseline")
        for pair, base_row in baseline_index.items():
            current = existing_index[pair]
            if any(current.get(f, "") != base_row.get(f, "") for f in immutable_fields):
                raise ValueError("existing interim immutable fields differ from baseline")
        rows = existing_rows
    else:
        prior_arms = {}
    row_by_pair = {(r["address"].strip().lower(), r["x_user_id"].strip()): r for r in rows}
    incoming = {}
    new_arms = {}
    allowed_verdicts = {"", "pending", "account_confirms", "ens_only", "conflict", "unverifiable"}
    expected_filename_to_arm = {filename: arm for arm, filename in ARMS.items()}
    for packet_path in packet_paths:
        pfields, packets = read_csv(packet_path)
        if pfields != PACKET_FIELDS:
            raise ValueError(f"review packet schema changed: {packet_path}")
        expected_arm = expected_filename_to_arm.get(packet_path.name)
        if expected_arm is None:
            raise ValueError(f"unexpected reviewer packet filename: {packet_path.name}")
        if expected_arm in prior_arms or expected_arm in new_arms:
            raise ValueError(f"review arm already imported; combine that arm into one canonical packet: {expected_arm}")
        packet_hash = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        new_arms[expected_arm] = {"filename": packet_path.name, "sha256": packet_hash, "rows": len(packets)}
        for p in packets:
            token = p.get("review_token", "")
            if token not in key_by_token or token in incoming:
                raise ValueError(f"unknown or duplicate review token: {token}")
            k = key_by_token[token]
            pair = (p.get("address", "").strip().lower(), p.get("x_user_id", "").strip())
            if pair != (k["address"].lower(), k["x_user_id"]):
                raise ValueError(f"identity fields changed for token {token}")
            if k["review_arm"] != expected_arm:
                raise ValueError(f"packet contains a row from the wrong review arm: {token}")
            target = row_by_pair[pair]
            expected_handle = target.get("handle_at_profile_audit", "")
            expected_url = target.get("x_profile_url_from_stable_id", f"https://x.com/i/user/{pair[1]}")
            if p.get("handle_at_profile_audit", "") != expected_handle or p.get("x_profile_url", "") != expected_url:
                raise ValueError(f"profile identity fields changed for token {token}")
            if p.get("manual_verdict", "").strip() not in allowed_verdicts:
                raise ValueError(f"invalid manual verdict for token {token}")
            if p.get("manual_verdict", "").strip() in {"account_confirms", "conflict"}:
                observed_id = p.get("evidence_verified_x_user_id", "").strip()
                if not observed_id.isdigit() or observed_id != pair[1]:
                    raise ValueError(f"affirmative review requires evidence_verified_x_user_id equal to target ID: {token}")
            if target.get("review_arm") != k["review_arm"]:
                raise ValueError("coordinator key arm does not match workbook")
            incoming[token] = p
    for token, p in incoming.items():
        k = key_by_token[token]
        target = row_by_pair[(k["address"].lower(), k["x_user_id"])]
        for f in REVIEW_FIELDS:
            new = p.get(f, "").strip()
            old = target.get(f, "").strip()
            if old not in {"", "pending"} and new not in {old, ""}:
                raise ValueError(f"refusing conflicting overwrite of existing adjudication: {f}/{token}")
            if new:
                target[f] = new
        verdict = target.get("manual_verdict", "pending").strip()
        target["review_state"] = "reviewed" if verdict not in {"", "pending"} else "in_progress" if any(target.get(f, "").strip() for f in REVIEW_FIELDS[1:]) else "not_started_account_side_evidence_required"
    digest = write_csv(out, fields, rows)
    receipt_path = Path(str(out) + ".receipt.json")
    all_arms = {**prior_arms, **new_arms}
    receipt = {
        "schema": "ens-x-review-import-receipt-v1",
        "source_workbook_sha256": source_hash,
        "packet_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "coordinator_key_sha256": key_hash,
        "imported_arms": all_arms,
        "output_sha256": digest,
        "network_requests": 0,
        "paid_queries_usd": 0,
    }
    with receipt_path.open("x", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"rows": len(rows), "packets_imported": len(incoming), "output": str(out), "output_sha256": digest,
            "receipt": str(receipt_path), "network_requests": 0, "paid_queries_usd": 0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--import-reviewed", nargs="+", type=Path)
    ap.add_argument("--coordinator-key", type=Path)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--out-workbook", type=Path)
    ap.add_argument("--existing-workbook", type=Path,
                    help="resume from a prior importer output; its adjacent .receipt.json is required")
    a = ap.parse_args()
    if a.import_reviewed:
        if not a.coordinator_key or not a.manifest or not a.out_workbook:
            ap.error("--import-reviewed requires --coordinator-key, --manifest, and --out-workbook")
        result = import_reviewed(a.workbook, a.coordinator_key, a.manifest, a.import_reviewed, a.out_workbook,
                                 existing_workbook=a.existing_workbook)
    else:
        if not a.out_dir:
            ap.error("generation requires --out-dir")
        result = generate(a.workbook, a.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
