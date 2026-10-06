#!/usr/bin/env python
"""Stage D part 2: SEMANTIC_COVERAGE.json — the uniform-schema vs uniform-
semantic-coverage gap, stated per split with fillable vs non-fillable gaps.

Reads only QUALITY_AUDIT.json (already computed from the package) plus the
grounding gold composition. No chain/cloud access; fillable gaps get a scope
and budget suggestion and stay PENDING; nothing is auto-collected.
"""
import json
from pathlib import Path

OUT = Path("/storage/gaoym/ex-graph-microtransaction-analysis/artifacts/benchmark_release_candidate_v1_20261006")
DS = OUT / "VERSIONED_DATASET"


def read_jsonl(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    audit = json.load(open(OUT / "QUALITY_AUDIT.json"))
    cov = audit["coverage"]

    # grounding gold composition (train only, automatic labels)
    g = read_jsonl(DS / "grounding_gold/train.jsonl")
    header = g[0]
    rows = g[1:]
    tasks = {}
    labels = {}
    not_avail = 0
    for r in rows:
        tasks[r["task"]] = tasks.get(r["task"], 0) + 1
        labels[r["fact_label_name"]] = labels.get(r["fact_label_name"], 0) + 1
        if r.get("claim_required_status") == "not_available":
            not_avail += 1

    out = {
        "schema": "semantic_coverage_v1",
        "headline": "统一 schema 不是统一语义覆盖:同一字段在三个 split 的真实信息量完全不同。"
                    "所有缺口都按状态记录;不自动补采;未验证前所有事实标签只是 automatic labels。",
        "per_split_raw_semantics": {
            s: {
                "parent_rows": cov[s]["parent_rows"],
                "raw_external_rows": cov[s]["raw_external_rows"],
                "raw_transaction_present": cov[s]["raw_transaction_present"],
                "raw_logs_present": cov[s]["raw_logs_present"],
                "raw_logs_empty_list_not_zero_logs": cov[s]["raw_logs_empty_list"],
                "abi_decoded": cov[s]["abi_decoded"],
                "role_packet_present": cov[s].get("role_packet_present", 0),
                "receipt_status_present": cov[s].get("receipt_status_present", 0),
                "external_status_unknown": cov[s]["external_status_unknown"],
                "external_failed_true": cov[s]["external_failed_true"],
                "role_packet_fraction": round(cov[s].get("role_packet_present", 0) / cov[s]["parent_rows"], 4),
            } for s in ("train", "dev", "test")
        },
        "critical_gap": {
            "statement": "可信本钱包角色注释 (role_packet) 仅存在于 TRAIN 的本地观察子集;DEV 与 TEST 的来源 "
                         "通道没有对应角色数据 (DEV 0/13411, TEST 0/25270)。任何在 TRAIN 用角色特征的方法,在 "
                         "DEV/TEST 上这些输入退化为 unknown——这不是方法缺陷,是来源覆盖边界,必须随结果报告。",
            "role_packet_coverage": {
                "train": cov["train"].get("role_packet_present", 0),
                "dev": 0,
                "test": 0,
            },
            "zero_role_annotation_interpretation": "0 表示该 split 的本地来源没有角色包,不代表钱包间没有角色关系;"
                                                    "也不得用 TRAIN 的角色证书跨钱包复制填充。",
        },
        "grounding_gold_composition": {
            "schema": header.get("schema"), "source_version": header.get("source_version"),
            "examples": len(rows), "tasks": tasks, "fact_labels_automatic": labels,
            "claim_required_not_available_rows": not_avail,
            "human_verification": "pending (stage E); 未有人工一致率,不得称 verified",
        },
        "fillable_from_existing_offline_trusted_sources": [
            {"gap": "receipt unknown 状态 (external_status_unknown)", "how": "声明来源窗口内的离线 parquet "
             "已有 receipt_status 字段;可在下个版本把已声明来源的回执并进 canonical_observed_action.receipt",
             "scope": "仅限已声明来源 (offline_chain_events_v1_20260929_full 与 external_fresh250/canonical_ledger)",
             "status": "plan_only_pending_freeze_decision"},
            {"gap": "DEV/TEST role_packet 为空", "how": "无现有可信来源可填;需要与 TRAIN 同协议的角色标注流程 "
             "(raw transaction/log 解码 + 角色规则),属于新采集/新计算",
             "scope_budget_suggestion": "若做:先 20-wallet pilot (stage E) 估计人工成本,再决定是否扩展; "
             "机解角色需重放 raw data,预算与 TRAIN 角色包构建同量级",
             "status": "pending_not_auto_collected"},
        ],
        "not_fillable_boundary": [
            "完整 EVM 执行与当前真实 allowance:本地观察≠执行模拟,保持 unknown",
            "钱包主观意图与后续动作原因:不可观测,保持 unknown",
            "全以太坊历史可见性:legal domain 只是声明来源的 first-seen 域,不宣称完整",
            "不同 token 原始金额跨资产相加:不定义",
        ],
        "predefined_difficulty_layers": {
            "rule": "只依据历史结构、缺失与绑定规则定义;不得按方法胜负挑挑战案例",
            "layers": [
                "layer_multi_parent_binding: 陈述必要证据分布于多个父动作 (claim_required 长度>1 的 automatic 例)",
                "layer_natural_binding_change: 同 asset/candidate 在历史中 owner 变更 (GROUNDING_FACTS natural "
                "change 切片 76 例/外折口径),与 held-expression 留出分开",
                "layer_missing_semantics: raw_transaction 缺失或 raw logs 空但行为存在的父动作 (unknown 状态保持)",
                "layer_rare_roles: 稀有 role_keys 样例,全取并如实报告数量",
            ],
            "status": "definitions_frozen_here; sampling deferred to stage E blind pack",
        },
        "nlp_validity_checks_available": [
            "fact 标签模板内类别分布 (上方 fact_labels_automatic)",
            "仅陈述/无关历史诊断:v27lean claim_only_dependence (120 例, prediction_change_rate≈0.29) 为已有"
            "冻结诊断,未经人工验证,只作 automatic 证据",
            "实体一致重命名与表达留出:v27lean locator 诊断含 natural_binding_change 与 held 表达切片 "
            "(train-vs-held 措辞),为 automatic 聚合结果",
            "controlled fact edits:可离线构造确定性编辑并重算事实标签 (不沿用未来行为标签) —— 计划见 "
            "NLP_VALIDITY_PLAN_AND_AVAILABLE_RESULTS.md;本轮未运行模型,不伪造分数",
        ],
        "unknown_accounting": {
            "unknown_is_state_not_parent_id": True,
            "empty_set_metrics_undefined_not_fake_1": True,
            "not_available_counted_separately": True,
        },
    }
    p = OUT / "SEMANTIC_COVERAGE.json"
    if p.exists():
        raise SystemExit("exists")
    with open(p, "x") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("SEMANTIC_COVERAGE.json written;",
          f"role packets train={cov['train'].get('role_packet_present', 0)} dev=0 test=0;",
          f"grounding examples={len(rows)} claim_not_available={not_avail}")


if __name__ == "__main__":
    main()
