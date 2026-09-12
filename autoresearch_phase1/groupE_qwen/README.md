# Group E — Qwen Behavioral Representation（本地 Qwen 语义行为画像）

- 角色: Group E — Qwen Behavioral Representation
- 工作目录: `/storage/gaoym/ex-graph-microtransaction-analysis`（本机 = cloud82, 10.63.0.82）
- 冻结协议: `research/audit/temporal_protocol.yaml` v1.0（Group 0, 2026-09-11 冻结）+ `research/audit/DATA_AUDIT.md`
- 状态: **骨架跑通（描述性小样本试点）** — 未声称有效性/因果/优越性

## 1. RQ 与 Hypothesis

**RQ**：本地 Qwen 能否发现"互补于数值/图特征"的语义行为画像？

**Hypothesis**（来自 `research/autoresearch_phase1.md` Group E）：
> 本地 Qwen 能发现互补于数值图特征的语义行为身份（behavioral identities）。

**可证伪的表述**（本组按此检验）：
1. Qwen 能从 as-of 行为画像文本生成**结构化、可解析、与输入一致的**语义摘要（parse yield、指令跟随度）；
2. Qwen 摘要 embedding 对未来活动标签具有**独立的描述性预测力**（OOF R² > 0 / Spearman > 0）；
3. Qwen embedding 空间**不冗余**于数值表示（embedding 维度无法被数值特征线性预测）；
4. 组合表示（数值+Qwen / 轨迹+Qwen）在 OOF 回归上**不劣于**纯数值/纯轨迹（互补性最严格形式）。

铁律：**绝不把 "Qwen 说这个钱包重要" 当作 ground truth**。Qwen 输出只作为
表示层（representation），其价值一律用独立下游指标（fwd30 活动/边数标签的 OOF 预测力）验证。

## 2. 数据契约与无泄漏边界

- cutoff = `2022-09-01`；lookback = `[2022-06-03, 2022-09-01)`（90 天）；label = `[2022-09-01, 2022-10-01)`（fwd30）。
- 描述钱包的**所有输入**均来自 as-of（cutoff 前）本地数据：
  - `feature_matrix_20220901.parquet`（90 天聚合，不含 fwd 标签列的使用）
  - `trajectory_stats_20220901.csv`（事件时序统计）
  - `asof_monthly_2022.parquet`（2022-05-01..08-01 月度快照，仅取 as-of 列）
  - `persona_assignments_20220901.csv`（仅用于分层采样与轨迹簇）
- **排除列**：`fwd30_*`、`importance_proxy_p3`（P3 为同 snapshot fwd30 的事后演示，绝不进入 prompt 与采样）。
  脚本内置泄漏扫描（`fwd30|importance_proxy|fwd_evt|fwd_cp`），200/200 通过。
- 采样仅用 as-of 特征（`evt_cnt_90d` 三分位 × `trajectory__kmeans` 簇 × `in_mm_subgraph` 覆盖），
  **不用任何 fwd30 标签选样本**（避免样本选择泄漏）。
- 未调用 BigQuery：所有数据复用 Group A 已物化的本地 parquet/csv（零云查询、零字节计费）。

## 3. 表示方案

| 表示 | 构造 | 维度 | 说明 |
|---|---|---|---|
| 数值表示 R_num | Group A `prepare_matrix`（ACTIVITY+CAPITAL+COUNTERPARTIES+NETWORK+TRAJECTORY） | 57 | 基线 |
| 轨迹表示 R_traj | Group A TRAJECTORY 组（gap/burstiness 等） | 7 | 时序基线 |
| Qwen 语义文本 | Qwen3.5-4B chat，temperature=0、max_tokens=700、**不发 reasoning_effort** | 文本 JSON | 8 字段结构化摘要 |
| Qwen 语义 embedding R_qwen | Qwen3-Embedding-0.6B 编码**原始模型输出文本** → PCA-64 | 1024→64 | 语义向量 |
| 组合 R_num+qwen / R_traj+qwen | 标准化拼接 | 121 / 71 | 互补性检验 |

Qwen 摘要 JSON 字段：`behavior_pattern`（行为模式）、`interaction_object_types`（交互对象类型，
仅基于输入中可证实的原生/代币/集中度/中心性线索）、`state_transitions`（状态转换）、`anomalies`
（异常）、`uncertainty`（不确定性）、`regime_change`（状态切换）、`activity_regime`（活动档）、
`confidence`（置信度）。系统提示明确要求"只用输入中给出的信息、不得编造交易对手/代币名/未来结果"。

## 4. 验证协议（每个 Qwen 表示必须用独立下游指标验证）

- **下游指标**：4 个 fwd30 标签（`fwd30_evt_cnt`、`fwd30_cp_distinct`、`fwd30_cp_out_distinct`、
  `fwd30_new_cp`）的 `log1p` 上 5 折（KFold, seed=2022）**out-of-fold Ridge R² 与 Spearman ρ**。
- **同一 200 钱包、同一折**上对比全部表示；另给 `alpha=10`（n=200 下防过参数化检查）与
  Qwen embedding 的 OOF kNN(k=5) 第二描述器。
- **独立性**：Qwen 摘要生成时不接触任何 fwd30 标签；embedding 也不接触标签；标签只在验证阶段使用。
- **冗余度检验**：用数值特征 OOF 预测每个 Qwen-embedding PCA 维，R² 低 ⇒ 携带数值之外的新信息。
- **指令跟随度（非 ground truth）**：Qwen `activity_regime` 与数值活动档的序数一致性（Kendall τ）。
- 全部数字为**描述性、小样本（n=200）**，不做显著性/有效性/优越性声明。

## 5. 样本范围

- 全量 18,519 钱包（cutoff 2022-09-01，有 ≥1 个 90 天 primary 事件）。
- 代表性子集 **200 钱包**（seed=2022，23 个分层单元）：活动档 low 77 / mid 66 / high 57；
  轨迹簇 0..4 = 45/43/72/27/13；matched-matched 子图覆盖 88、非覆盖 112。
- 覆盖方案 §20 建议的"聚类 medoid、高/低影响、持续/偶发、随机对照"的可用代理
  （影响维度用 as-of 网络/活动代理；fwd 代理不参与采样）。

## 6. 成本（实测）

| 项 | 值 |
|---|---|
| Qwen3.5-4B chat 调用 | **200 次**（组内预算 ≤500 ✓），0 失败 |
| prompt tokens | 174,399 |
| completion tokens | 38,840 |
| 平均延迟 | ~2 s/调用（首 token 快，峰值并发单线程串行） |
| parse yield | **200/200 = 1.0** |
| Embedding 调用 | **13 次**（16 条/批），200×1024 维 |
| 磁盘缓存 | `results/qwen_summaries_20220901.jsonl`（断点续跑，已实现） |
| 云查询 | 0（未调用 BigQuery；复用 Group A 本地物化数据） |
| GPU | 未占用（API 调用 GPU3/GPU4 的既有服务，未起新服务） |

缓存策略：chat 与 embedding 均按 `target_address` 幂等落盘 jsonl；重跑自动跳过已完成地址。

## 7. 结果（描述性，n=200，5 折 OOF）

OOF Ridge R²（log1p(fwd30_*)）：

| 表示 | evt_cnt | cp_distinct | cp_out_distinct | new_cp |
|---|---:|---:|---:|---:|
| R_num | 0.635 | 0.636 | 0.628 | 0.594 |
| R_traj | 0.544 | 0.544 | 0.546 | 0.488 |
| R_qwen_pca | 0.228 | 0.243 | 0.295 | 0.289 |
| R_qwen_pca (α=10) | 0.312 | 0.323 | 0.341 | 0.320 |
| R_qwen_pca kNN k=5 | 0.489 | 0.490 | 0.507 | 0.459 |
| R_num+qwen (α=10) | 0.274 | 0.279 | 0.292 | 0.304 |
| R_traj+qwen (α=10) | 0.322 | 0.332 | 0.353 | 0.339 |

Spearman ρ（Ridge α=1）：R_num 0.66–0.75；R_traj 0.66–0.72；R_qwen_pca 0.57–0.62。

**解读（保持边界）**：
1. Qwen 语义 embedding **独立携带预测信号**：OOF R² 0.23–0.34、Spearman 0.57–0.62、kNN 0.46–0.51，
   显著高于 0，且**低于**纯数值表示（0.59–0.64）。
2. Qwen embedding 空间**大体不冗余**于数值：数值特征 OOF 预测 embedding PCA 维的平均 R² = **−0.18**，
   仅 3/64 维 >0.5（前几维对应总体活动量级，可被数值预测；其余维不可）。
3. **严格互补性（拼接提升）未得到证实**：n=200 下 R_num+qwen / R_traj+qwen 的 OOF R² 不高于
   纯数值/纯轨迹（α=1 时明显退化，α=10 时仍低于纯表示）。这是小样本 + 高维拼接的典型现象，
   不能据此宣称"组合更优"，也不能据此宣称"Qwen 无用"——需要更大样本或更优融合
   （embedding 降维选择、late fusion、线性探针选维）才能下结论。
4. 指令跟随度：Qwen `activity_regime` 与数值活动档 Kendall τ = **0.81**（Spearman 0.86, n=200），
   摘要与输入数字一致（抽查 5 例见 `results/evaluation_20220901.json`），但这是"一致性"检查，
   **不是 ground truth 有效性**。

## 8. Failure Modes（预期失败模式与实测）

| 模式 | 本组处置 | 实测 |
|---|---|---|
| Qwen 幻觉交易对手/代币名/未来 | 系统提示禁止 + JSON 只允许输入可证实线索 | 抽查未见编造实体名（仅模式级描述） |
| reasoning_effort 耗光 max_tokens 不给 JSON | 按 AGENTS.md **不发该字段** | 200/200 有 JSON |
| JSON 解析失败 | 先剥 code fence，再取首尾 `{...}`；失败保留 raw 并计入 parse yield | parse yield 1.0 |
| 把 Qwen 输出当 ground truth | 所有验证一律走独立 fwd30 标签 | 未违反 |
| 未来泄漏进 prompt | 只用 as-of 本地数据 + 排除 fwd 列 + 扫描 | 200/200 通过 |
| 小样本高维过参数化 | 报告 α=1 与 α=10 两档 + kNN 第二描述器 | 组合退化已如实报告 |
| 组合表示误导性提升 | 不做显著性/优越性声明，delta 仅描述 | 如实报告负 delta |

## 9. Novelty 定位（边界声明）

- 本组是**表示层试点**，不是 SOTA 声明。可写进论文的候选贡献：
  (a) 用 as-of 语义摘要 + 本地 embedding 为钱包构建**可审计、无未来泄漏的语义表示**；
  (b) 量化"语义表示与数值/轨迹表示的冗余度"（embedding 大体不可由数值预测，但拼接增益未证实）。
- **未声称**：Qwen 发现"更优"画像、因果影响、预测优越性、零样本泛化。
- 与 Group A 的关系：persona（数值聚类）与 Qwen 语义摘要互为不同表示，本组提供二者在下游标签上的
  描述性对比（R_num / R_traj / R_qwen / 组合）。

## 10. 泄漏检查清单

- [x] 采样仅用 as-of 特征（evt_cnt 三分位、轨迹簇、子图覆盖），无 fwd30 参与
- [x] prompt 仅含 as-of 本地数据，排除 `fwd30_*` / `importance_proxy_p3`，脚本扫描通过
- [x] 月度趋势仅用 2022-05-01..08-01 as-of 快照，不含 9 月/未来
- [x] 标签（fwd30）只在评估阶段使用，不进入任何生成/采样步骤
- [x] 未调用 BigQuery（无整表导出、无字节计费）
- [x] 未改 `src/` 现有文件与其他组目录（仅新增 `research/groupE_qwen/`）

## 11. 文件清单

```
research/groupE_qwen/
├── README.md                       # 本文档
├── src/
│   ├── config.py                   # 冻结路径/端点/协议常量
│   ├── sample_wallets.py           # 分层代表采样（as-of 特征）
│   ├── build_profiles.py           # 构建 as-of 行为画像文本（含泄漏扫描）
│   ├── summarize_qwen.py           # Qwen3.5-4B 结构化摘要（缓存/断点续跑）
│   ├── embed_summaries.py          # Qwen3-Embedding-0.6B 摘要 embedding（缓存）
│   └── evaluate_representations.py # 下游 OOF 验证 + 冗余度/指令跟随度
└── results/
    ├── sample_wallets_20220901.csv        # 200 钱包 + 分层标签
    ├── sample_meta_20220901.json
    ├── profiles_20220901.jsonl            # as-of 画像文本（200）
    ├── qwen_summaries_20220901.jsonl      # chat 缓存（200，parse 200）
    ├── qwen_embeddings_20220901.jsonl     # embedding 缓存（200×1024）
    ├── qwen_embeddings_20220901.npy
    ├── qwen_embedding_addresses_20220901.json
    ├── evaluation_20220901.json           # 下游数字 + 冗余度 + 指令跟随度 + 抽查
    └── call_stats_20220901.json           # 调用统计
```

## 12. 未完成项 / 后续（不属本次范围）

1. **更大样本 + 更优融合**验证严格互补性（拼接 R² 未超越纯数值）：如 1k–3k 钱包、
   embedding 维度选择（仅保留数值不可预测的维）、late fusion / 学习型门控。
2. 事件级语义上下文（top 交易对手/代币符号）作为 prompt 增强，需有界 BigQuery 查询（分区过滤 + bytes-billed 上限）。
3. 与 Group C/D 的表示交叉验证；K 敏感性（§16）由擂台层统一执行。
4. Qwen latent representation（隐藏层）不可经 OpenAI 兼容 API 获取，本组标记为"技术不可用"。
