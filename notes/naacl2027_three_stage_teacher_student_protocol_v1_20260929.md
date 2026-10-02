# NAACL 2027 三层预测与教师-学生协议 v1

日期：2026-09-29
状态：研究协议已冻结为设计稿；教师伪标签训练、holdout、最终排序尚未运行。

## 1. 任务分层

对每个实例 `(wallet w, cutoff t)` 定义 `H_t` 为严格早于 `t` 的链上事件历史。

1. **活动预测**：`A=1` iff `[t,t+7d)` 内存在钱包主动发出的、目标地址非空的 `external_tx`。主口径为 attempted；`receipt_status=1` 为 success-only 稳健性口径。报告 AUROC、AUPRC、Brier、校准、coverage-risk；不能把真实 A 提供给后续模块。
2. **候选召回**：若 `A=1`，`y` 是未来窗口按 canonical `(block_number, transaction_index, event_index/trace, hash)` 顺序的第一笔外发 external transaction recipient。检索器只能使用 `H_t` 构造 `C_t`；真实 `y` 不得注入候选池。报告 Recall@5/50/500/2000、候选实际数量、历史支持上界和 out-of-support 率。
3. **Top-5 排序**：仅对 `C_t` 内地址评分并输出最多 5 个。报告 conditional Hit@1/5、MRR/NDCG（仅在 y∈C_t 时）以及 end-to-end Hit@5（全部 active case 分母）。召回率不能表述为最终预测准确率。

活动预测与候选召回必须分别报告；inactive 实例不进入地址召回分母，但其活动预测结果仍须保留。

## 2. 数据切分与信息边界

- 开发阶段：March-June 2022 作为训练，July 2022 作为 dev，August 2022 仅作已探索诊断；不能称独立测试。
- 正式版本：按 wallet 隔离，并选择更晚时间窗口的 holdout。钱包选择规则只能看 holdout cutoff 前数据；方法、预算、超参冻结后 holdout 只评估一次。
- 所有历史边、typed interaction key、节点统计、图嵌入和 ANN 索引都必须按 cutoff 重建或严格截断。
- 当前 compact/export 缺失时，不能声称保留了不可审计的 canonical 顺序；优先使用 offline parquet 的 block/transaction/event/trace 字段。

## 3. 教师-学生伪标签协议

### 教师（训练期辅助标签）

教师可以看到 `(H_t, A, y)`，但它的作用是选择**事后相容的线索**，不是发现因果原因。先由程序从 `H_t` 枚举候选解释，再让教师选择/排序：

- `repeat_recency`：钱包近期重复交互或 recency 路径；
- `typed_graph_path`：真实存在的时间/类型感知共享对象路径；
- `asset_or_protocol_exposure`：只能引用实际出现的 token contract/protocol metadata；
- `activity_shift`：近期活动强度或方向/事件类型变化；
- `other_unknown`：无足够证据时必须允许 UNKNOWN/拒答。

结构化输出：

```json
{
  "labels": ["repeat_recency", "typed_graph_path"],
  "evidence_event_ids": ["..."],
  "executable_rules": [{"operator":"recent_repeat", "args":{}}],
  "path_ids": ["..."],
  "confidence": 0.0,
  "abstain": false,
  "unknown_reason": null
}
```

executor 独立检查：事件是否 `< t`、事件 ID 是否真实、路径是否存在、规则能否在 `H_t` 执行；任何不合格证据导致该伪标签丢弃或降级为 UNKNOWN。没有交易对手时禁止编造对手方。该伪标签不替代真实 `A/y`。

### 学生

开发、holdout 和部署时只输入 `H_t`。输出：

```json
{
  "activity_probability": 0.0,
  "factor_weights": {"repeat_recency": 0.0, "typed_graph_path": 0.0,
                      "asset_or_protocol_exposure": 0.0, "activity_shift": 0.0},
  "candidate_budget": {"own": 0, "graph": 0, "popular": 0},
  "ranked_top5": [{"address":"...", "score":0.0,
                    "evidence_event_ids":["..."]}]
}
```

伪标签仅作为辅助目标，例如对有效 teacher label 使用 masked multi-label BCE / soft-label KL；主目标仍是真实活动 BCE、候选内 pairwise/listwise ranking loss 和 end-to-end 召回约束。建议：

`L = L_activity + λ_rank L_rank + λ_budget L_budget + μ L_teacher`

其中 `μ` 通过 dev 调整且不能让教师伪标签取代真实未来目标。

## 4. 候选与 out-of-support

- `y∉C_t` 明确记为 retrieval failure；不得重排或注入 `y`。
- `y` 不在 cutoff 前全局地址池时，记为 global out-of-support；另报 wallet-self-history seen/unseen 和 event-family/type seen/unseen。
- `UNKNOWN` 是合法输出，不计为正确解释；分析时单独报告 abstention、伪标签保留率和覆盖率。
- 无历史事件的钱包只能输出活动先验/空候选，不得生成虚构证据。

## 5. 必须对照

1. teacher-free；
2. shuffled teacher labels；
3. no typed graph path；
4. fixed budget；
5. learned factor gate；
6. direct-LLM（只作为对照，不作为主要可执行检索器）；
7. 时间反事实：删除/移动历史事件后按 executor 重新判定应变/保持/撤回；
8. 证据删除一致性：删除被引用事件后陈述、规则和候选依据必须按预注册规则变化或撤回。

## 6. 当前实际运行的最小 pilot

旧的 `artifacts/hetero_temporal_retrieval_pilot_v1_20260929/` **已标记 INVALID**：它用未来 `active=True` 筛选图节点，导致未来选择泄漏，不能引用其召回数字。当前修正版使用新的不可覆盖目录 `artifacts/hetero_temporal_retrieval_pilot_v3_20260929/`，实现一个不含 LLM 的 typed temporal retrieval：

`wallet -> (counterparty, event_family, token_contract) -> peer -> peer recent outgoing external recipient`

使用 cutoff 前事件、hub cap=200、peer cap=200、peer recent recipient cap=100、90 天时间衰减。它是候选覆盖诊断，不是排序器，不是独立测试。修正版的图构建使用 cutoff 前事件中所有可见钱包；active case 只在候选生成后用于评估。

## 7. 当前未运行

教师伪标签、学生训练、行为因子门控、ANN/LightGCN/BPR、正式 wallet-isolated later holdout 和最终 Top-5 排序均尚未运行。
