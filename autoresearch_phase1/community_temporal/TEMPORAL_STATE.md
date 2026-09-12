# TEMPORAL_STATE.md — Phase-I 时序状态构造汇总（§2 状态构造审计）

> 角色：COMM（时序状态构造与动态社区形式化组）
> 依据：`research/autoresearch_phase1.md` §2 / §12 / §13；冻结协议
> `research/audit/temporal_protocol.yaml` v1.0 与 `research/audit/DATA_AUDIT.md`（Group 0）
> 机器：cloud82（10.63.0.82）。本文件只做**一致性核验与口径汇总**，不做有效性/因果声明。
> 结构化清单：`temporal_state_manifest.json`（含表 FQN、SQL、脚本、SHA-256）。

---

## 1. 统一对象定义

```
S_i(t) = 截止 t 之前（严格 < t）可观测到的钱包 i 的全部链上信息
Z_i(t) = 由 S_i(t) 构造的 as-of 特征向量（90 天 lookback [t-90d, t)，无未来）
P_i(t) = 动态画像/社区标签：Group A 为 persona（聚类），COMM 为交易社区（模块度）
Y_i(t) = [t, t+30d) 标签窗口（仅用于标签/下游评估，不进特征）
```

四个组的 S_i(t)→Z_i(t)→P_i(t) 构造均以 `wallet_asof_features_*`（紧凑聚合表）或
`target_event_sequences_*`（序列视图）为源，全部满足“特征严格 < cutoff、标签 [t, t+30d)”。

---

## 2. 各组构造口径（逐组）

### Group A — Behavior-First
- S 源：`wallet_asof_features_20220901`（09-01，18,519 行）+ `wallet_asof_features_v1`（05-08 月度，78,786 行）。
- Z：57 列（activity / capital / counterparty / trajectory 全覆盖；USD 91.3% native / 35.8% token USD；
  as-of matched-matched 网络 42.8% = 7,929/18,519）。
- P：full_asof K-means(K=4) 主表示（bootstrap ARI 0.418），另有 GMM/HDBSCAN/轨迹/网络变体。
- 窗口：09-01 特征 `[2022-06-03, 2022-09-01)`；月度快照各自 `[t-90d, t)`；标签均 `[t, t+30d)`。

### Group B — Predictive-Influence-First
- S 源：Group A 月度 parquet（06/07/08 训练/验证/冻结测试）+ `wallet_asof_features_20220901`（09 holdout）；
  09 标签为独立有界 BQ 拉取（与 Group A parquet 逐行 parity = 0 diff）。
- Z：冻结 OOS 只用 24 个 base as-of 特征；轨迹/网络/USD 仅在 `run_extended09.py` 事后消融（已标注）。
- 切分：train 06-01 < val 07-01 < frozen test 08-01 < final holdout 09-01（协议 §4 时序切分）。
- P：不产 persona，消费 Group A persona 做社区集中度（top-2 persona 承载预测 top-10% ≈93%）。

### Group C — Temporal-Graph-First
- S 源：`target_event_sequences_20220301_20220901`（primary 事件，matched-matched、counterparty_present、非自交易）。
- G≤t：09-01 窗口 `[2022-06-03, 2022-09-01)` 建 7,929 节点 / 13,281 无向边 / 事件权重 105,592；
  月度切片 Jun/Jul/Aug。
- Z：27 个结构/时间/社区特征；社区 = greedy modularity（Louvain 式），387 社区，boundary 799（10.1%）。
- 备注：Group C 的月度 switch rate（58.0%/56.3%）是日历月切片 + 无阈值贪婪匹配 + **覆盖式权重**
  的粗略口径（见 §4 与 COMMUNITIES.md）。

### Group D — Information-Gain
- S 源：Group A `feature_matrix_20220901.parquet`（无新 BQ）；外部对照 `p1_wallet_icf_v2`（08-01 快照）。
- Z：52 个 as-of 特征（含网络/轨迹/USD）；static prior 仅作基线。
- 目标：`y_cp_ge10`（fwd30_cp_distinct≥10，正样本率 0.413）、`y_active30`。
- IG：5 折 wallet 级 CV + 中位数掩蔽 ΔNLL（out-of-sample）；子集 n=2,999（分层抽样 seed=20220901）。
- 备注：单 cutoff 快照内 wallet 级切分，不跨窗口混合 → **不是** walk-forward OOS 裁决（已标注）。

---

## 3. 一致性结论（与冻结协议对照）

| 检查项 | A | B | C | D | 结论 |
|---|---:|---:|---:|---:|---|
| cutoff 语义（严格 < t） | ✓ | ✓ | ✓ | ✓ | 一致 |
| lookback [t-90d, t) | ✓ | ✓ | ✓ | ✓ | 一致（06/07/08/09 日历逐日核验=90 天） |
| 标签 [t, t+30d) | ✓ | ✓ | ✓ | ✓ | 一致 |
| 匹配-匹配边过滤（primary / counterparty_present / 非自交易） | ✓ | n/a | ✓ | n/a | A 与 C 过滤条件完全相同 |
| 静态先验隔离（leaky，不进 as-of 特征） | ✓ | ✓ | ✓ | ✓ | 一致 |
| 社交/X 特征 | 未用 | 未用 | 未用 | 未用 | 一致（无可信 crosswalk） |
| P3 演示标签排除 | ✓ | ✓ | n/a | ✓ | 一致 |
| 切分协议 | 描述性 | 严格时序 | 描述性 | 单快照 wallet-CV（标注） | B 是唯一 walk-forward OOS |

### 关键一致性/不一致点
1. **A 与 C 的边构造一致**：同一来源表、同一过滤、同一窗口；A 按 `(u,v,direction)` 聚合，
   C 再按 month 分组。COMM 实测：09-01 图节点/边/社区/事件权重与 Group C 全同（parity 见 manifest）。
2. **A 与 B/D 的特征窗口一致**：09-01 均为 `[2022-06-03, 2022-09-01)`；B 的 06/07/08 快照用各自
   90 天窗口（来自 v1 表），与协议 walk_forward cutoffs 对齐。
3. **特征集差异（已标注、非冲突）**：B 冻结用 24 特征；D 用 52 特征（含网络/轨迹/USD）；
   A 用 57 列（含 USD 覆盖率限制）。这是各组的**重要性定义差异**，不是泄漏。
4. **`wallet_asof_features_20220901` 目标池**来自 Mar-Oct 组合视图 distinct target（低危：每行
   必须有 `[06-03,09-01)` 内 ≥1 事件，故“仅因未来活动入选”不可能出现；协议建议后续快照目标池改 `< cutoff`）。
5. **Group C 月度 switch rate 是粗略口径**：日历月（1 个月窗口）切片 + 覆盖式权重 + 无阈值贪婪匹配；
   与 COMM 正式 per-cutoff 口径差异显著（见 COMMUNITIES.md §5）。

---

## 4. 可复现清单（摘要；完整含 hash 见 `temporal_state_manifest.json`）

| 对象 | FQN / 路径 |
|---|---|
| 目标地址映射 | `ictdata-507912.exgraph.target_addresses`（27,613） |
| 事件表（dev） | `external_transactions/token_transfers/internal_traces_20220301_20220901`（2.88M/4.28M/4.48M） |
| 事件表（holdout） | 同上 `_20220901_20221001`（0.33M/0.50M/0.57M） |
| 序列视图 | `target_event_sequences_20220301_20220901`（11,836,196）/ holdout 视图（1,428,845） |
| as-of 特征 | `wallet_asof_features_v1`（78,786，快照 05-08）/ `wallet_asof_features_20220901`（18,519） |
| 选择/评估 | `wallet_importance_ranking_v1`、`router_dataset_v1`、`selection_eval_v1`、`nc_ranker_samples_v2` 等 |
| Group A SQL | `research/groupA_behavior/sql/{asof_features_20220901,asof_features_monthly,network_edges_asof}.sql` |
| Group B 脚本 | `research/groupB_predictive/{run_predictive.py,fetch_labels.py,run_extended09.py}` |
| Group C SQL | `research/groupC_temporal_graph/sql/edges_asof.sql` |
| Group D 脚本 | `research/groupD_infogain/src/{build_dataset,run_wallet_masking,run_community_masking,run_residual}.py` |
| COMM SQL | `research/community_temporal/sql/edges_asof_day.sql`（单次有界拉取 billed ≈0.41 GiB） |
| 冻结协议 | `research/audit/temporal_protocol.yaml`（sha256 `07126f9e…7227a`） |

> 元数据快照 `research/audit/bq_metadata_2026-09-11.json`、构建 job 证据与本地文件 hash 均见
> `research/audit/DATA_AUDIT.md` 与 `research/audit/bq_metadata_2026-09-11.json`。
