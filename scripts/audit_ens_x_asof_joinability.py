#!/usr/bin/env python3
"""Audit transaction-hash joinability of local ENS event artifacts (offline only).

Hash overlap is only transaction membership: it does not identify individual logs,
prove extraction completeness, or recover canonical block/transaction ordering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FILES = (
    "addrchanged_latest.parquet",
    "reverse_evidence.parquet",
    "textchanged_raw.parquet",
    "textchanged_raw_v2.parquet",
    "textchanged_twitter.parquet",
    "textchanged_twitter_decoded_v2.parquet",
    "textchanged_twitter_decoded_v3.parquet",
    "candidate_revnodes.parquet",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect(path: Path) -> tuple[dict[str, Any], set[str] | None, Counter[str] | None]:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    cols = pf.schema_arrow.names
    record: dict[str, Any] = {
        "path": str(path),
        "sha256": sha256_file(path),
        "rows": pf.metadata.num_rows,
        "columns": cols,
    }
    if "transaction_hash" not in cols:
        record.update(transaction_hash_nonnull=None, transaction_hash_unique=None,
                      duplicate_hash_rows=None)
        return record, None, None

    hash_counts: Counter[str] = Counter()
    nonnull = 0
    for batch in pf.iter_batches(columns=["transaction_hash"], batch_size=65536):
        for value in batch.column(0).to_pylist():
            if value is not None:
                hash_counts[str(value).strip().lower()] += 1
                nonnull += 1
    hashes = set(hash_counts)
    record.update(transaction_hash_nonnull=nonnull,
                  transaction_hash_unique=len(hashes),
                  duplicate_hash_rows=nonnull - len(hashes))
    return record, hashes, hash_counts


def build_report(project: Path) -> dict[str, Any]:
    base = project / "artifacts/ens_x_crosswalk"
    records: dict[str, dict[str, Any]] = {}
    hash_sets: dict[str, set[str]] = {}
    hash_counts: dict[str, Counter[str]] = {}
    for name in FILES:
        path = base / name
        record, hashes, counts = inspect(path)
        records[name] = record
        if hashes is not None:
            hash_sets[name] = hashes
            assert counts is not None
            hash_counts[name] = counts

    overlaps = []
    names = sorted(hash_sets)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            shared = len(hash_sets[left] & hash_sets[right])
            shared_hashes = hash_sets[left] & hash_sets[right]
            smaller = min(len(hash_sets[left]), len(hash_sets[right]))
            shared_left_rows = sum(hash_counts[left][h] for h in shared_hashes)
            shared_right_rows = sum(hash_counts[right][h] for h in shared_hashes)
            naive_join_pairs = sum(hash_counts[left][h] * hash_counts[right][h] for h in shared_hashes)
            overlaps.append({
                "a": left,
                "b": right,
                "distinct_shared_transaction_hashes": shared,
                "shared_fraction_of_smaller_distinct_set": round(shared / smaller, 6) if smaller else None,
                "shared_hashes_multiple_rows_in_a": sum(hash_counts[left][h] > 1 for h in shared_hashes),
                "shared_hashes_multiple_rows_in_b": sum(hash_counts[right][h] > 1 for h in shared_hashes),
                "shared_rows_in_a": shared_left_rows,
                "shared_rows_in_b": shared_right_rows,
                "naive_transaction_hash_join_pairs": naive_join_pairs,
            })
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "offline_local_transaction_hash_joinability_diagnostic",
        "network_accessed": False,
        "paid_query_usd": 0,
        "files": records,
        "pairwise_hash_overlap": overlaps,
        "interpretation": [
            "Transaction-hash overlap establishes same-transaction membership only; it does not identify which log/event within a transaction corresponds across files.",
            "naive_transaction_hash_join_pairs is the row-pair count from joining only on transaction_hash; it is a potential fan-out diagnostic, not an event-match count.",
            "No local source in this inventory provides block_number or transaction_index.",
            "addrchanged_latest has no transaction_hash and is a latest-state snapshot, not an event history.",
            "These diagnostics do not establish source completeness or historical X identity validity.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ENS–X 本地 as-of 连接粒度诊断（离线）",
        "",
        f"- 生成时间（UTC）：`{report['generated_at_utc']}`",
        "- 网络请求：0；付费查询：0",
        "- 范围：本地 ENS Parquet 的 `transaction_hash` 重叠；不是事件级 as-of 验证。",
        "",
        "## 各文件哈希覆盖",
    ]
    for name, row in report["files"].items():
        if row["transaction_hash_nonnull"] is None:
            lines.append(f"- `{name}`：{row['rows']:,} 行；无 `transaction_hash` 字段。")
        else:
            lines.append(
                f"- `{name}`：{row['rows']:,} 行；非空哈希 {row['transaction_hash_nonnull']:,}；"
                f"唯一哈希 {row['transaction_hash_unique']:,}；重复哈希行 {row['duplicate_hash_rows']:,}。"
            )
    lines += ["", "## 非零跨文件交集（唯一交易哈希及潜在 fan-out）"]
    for row in report["pairwise_hash_overlap"]:
        if row["distinct_shared_transaction_hashes"]:
            lines.append(
                f"- `{row['a']}` × `{row['b']}`：{row['distinct_shared_transaction_hashes']:,}；"
                f"占较小哈希集合 {row['shared_fraction_of_smaller_distinct_set']:.1%}；"
                f"交集哈希对应两侧行数 {row['shared_rows_in_a']:,} × {row['shared_rows_in_b']:,}；"
                f"仅按哈希连接会形成 {row['naive_transaction_hash_join_pairs']:,} 个行配对"
                f"（潜在 fan-out，不是事件匹配数）。"
            )
    lines += [
        "",
        "## 解释与边界",
        "- 同一 `transaction_hash` 只能把记录连接到同一笔交易，不能区分同一交易内的多个日志。",
        "- 当前本地源缺少 `block_number` 与 `transaction_index`；`addrchanged_latest` 没有交易哈希，不能恢复地址变更历史。",
        "- 因此目前不能做规范事件级 as-of 回放；仍需来源及覆盖可证明的规范 ENS 日志，或经独立验证的重建路径。",
        "- 本报告不证明源数据完整性，也不证明钱包—X 链接在历史时点有效。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True, help="JSON report path; Markdown sibling is also written")
    args = parser.parse_args()
    report = build_report(args.project.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = args.out.with_suffix(".md")
    md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(args.out), "markdown": str(md),
                      "files": len(report["files"]),
                      "nonzero_hash_overlap_pairs": sum(x["distinct_shared_transaction_hashes"] > 0 for x in report["pairwise_hash_overlap"]),
                      "network_accessed": False, "paid_query_usd": 0}))


if __name__ == "__main__":
    main()
