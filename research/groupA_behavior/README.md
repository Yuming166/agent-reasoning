# Group A — Behavior-First：动态钱包行为画像流水线（Phase I 骨架）

> 状态：**流水线骨架已跑通，输出初步可审计描述性数字**（2026-09-11，cloud82）。
> 所有数字均标注样本范围与 cutoff；在 Group 0 的 `DATA_AUDIT.md` + `temporal_protocol.yaml`
> 通过前，本组结果**不视为最终有效结果**（research/README.md 擂台规则）。

---

## 1. Research Question 与 Hypothesis

**核心问题（Phase I 总体）**：Which Ethereum wallets are worth paying attention to, at what time, and why?

**Group A 子问题**：钱包 i 在 cutoff t 的历史行为（S_i(t)）能否被组织成一个**动态行为画像（persona）P_i(t)**，
且该画像可作为后续"谁值得被关注"的**行为侧输入**？

**Group A 假说**：
> H_A：钱包的行为身份（behavioral identity）是未来预测有用性（predictive usefulness）的强决定因素；
> 即存在可计算、可审计、随时间演化的 P_i(t)，其聚类结构对未来行为具有描述性区分度。

**对象定义**（与 autoresearch_phase1.md 一致）：
- `S_i(t)`：cutoff t 之前可观测到的钱包 i 的全部链上信息（<= t，无未来）。
- `Z_i(t)`：由 S_i(t) 构造的行为特征向量（手工数值特征 + 轨迹摘要 + 网络特征）。
- `P_i(t)`：由 Z_i(t) 聚类得到的动态 persona 标签 / 分布。

**边界声明**：本组只报告"行为画像的结构质量（可分离性、稳定性、持久性）"与"对未来的描述性区分度"，
**不声称因果、不声称预测优越性、不声称 SOTA**。

---

## 2. 数据契约与时间边界（无未来泄漏）

主 cutoff：**2022-09-01**（与现成 as-of 表 `wallet_asof_features_20220901` 对齐）。

| 窗口 | 区间（UTC） | 用途 |
|---|---|---|
| 90 天 lookback | `[2022-06-03 00:00, 2022-09-01 00:00)` | 所有特征 Z_i(t) |
| 未来 30 天 | `[2022-09-01 00:00, 2022-10-01 00:00)` | 仅标签 / 下游效用评估（fwd30_*） |

**泄漏规则**：
- 特征只用 lookback 窗口内、且 `sequence_role='primary'`（external_tx + token_transfer，按
  `(target, block_number, transaction_index, event_index, direction)` 去重）的事件；
  与 `wallet_asof_features_20220901` 的建表语义一致。
- 未来窗口只用于标签（fwd30_evt_cnt / fwd30_cp_distinct / fwd30_new_cp）与下游描述性评估；
  **聚类输入矩阵不含任何 fwd30_* 列**。
- **静态全窗口结构特征**（`artifacts/exgraph_structural_features.csv` 的 degree/weighted degree/PageRank）
  是整窗口聚合，**不属于 as-of 特征**；已单独写成 `results/data/static_prior_20220901.csv`
  并标记为 leaky prior，**未并入 Z_i(t)**（见 memory 审计结论：全窗口静态特征是 selection prior，
  不是 as-of prediction feature）。
- **X/社交特征**（`ethereum_with_twitter_features_v1/*.parquet` 的 PCA 社交特征）因无可信
  eth↔X crosswalk 且为全图静态特征，**本组不使用**；`wallet_usd_outflow_v1.csv` 的 snapshot
  与 cutoff 对齐，作为覆盖率受限的 USD 资本特征使用（仅 91.3% 钱包有值）。

**主数据来源**：
- BigQuery（有界查询，分区过滤 + maximum_bytes_billed 上限，不整表导出）：
  `wallet_asof_features_20220901`、`wallet_asof_features_v1`、`target_event_sequences_20220301_20220901`。
- 本地产物：`prices_v1/wallet_usd_outflow_v1.csv`（USD，as-of）、`exgraph_structural_features.csv`（静态先验，隔离）。

---

## 3. 特征组（Z_i(t)）

| 特征组 | 特征 | 覆盖率（18,519 钱包） |
|---|---|---|
| **Activity 活跃** | evt_cnt_90d, evt_out/in/self_90d, active_days_90d, tx_cnt_90d, active_span_days_90d, events_per_active_day_90d | 100% |
| **Capital 资本** | evt_native/token_90d, token_distinct_90d, token_hhi_90d, token_event_rate_90d；native_usd, token_usd_priced, token_rows(_priced) | 100%（计数）；USD 91.3%（token USD 35.8%） |
| **Counterparties 对手方** | cp_distinct_90d, cp_out/in_distinct_90d, cp_out/in_interact_90d, cp_entropy_90d, cp_new_30d, cp_new_rate_30d, cp_both_dir_90d, cp_reciprocity_90d, self_tx_rate_90d | 100% |
| **Network 网络（as-of）** | asof_mm_in/out/undir_degree, asof_mm_w_in/w_out_degree, asof_mm_pagerank, asof_mm_kcore, asof_mm_clustering, asof_mm_hub_neighbors, in_mm_subgraph | **42.8%**（仅 matched-matched 子图内钱包） |
| **Trajectory 轨迹** | mean/median/max/std_gap_days, n_gaps_gt7d, n_gaps, first_event_offset_days, last_event_recency_days, burstiness（推导）, direction_balance（推导） | 100%（gap 特征 92.96%，单事件钱包置 0） |

**关键边界**：
- **Network 组**基于"双方都是 EX-Graph 匹配地址"的有向时序子图（lookback 90 天内聚合出
  31,752 条有向 (u,v,direction) 边，其中 7,929 个样本钱包命中），是严格 as-of 的时序子图，
  **不是**全窗口静态图。未命中钱包该组特征置 0 并带 `in_mm_subgraph=False` 指示列。
- **Trajectory 组**从 BigQuery 按钱包聚合（LAG 时间差、burstiness、休眠/再激活、首次/最近活动偏移），
  输出为紧凑的每钱包一行，未导出事件级数据。
- 计数/长度类特征做 `log1p`，比率/熵类特征原值，缺失按组语义填补（计数 0 / 比率中位数），
  99.5/0.5 分位 winsorize，StandardScaler。

---

## 4. 表示方案对比（Representation）

| 表示 | 定义 | 状态 |
|---|---|---|
| **手工数值特征**（主） | 全部 5 组特征的标准化矩阵（54 列，含派生 burstiness / direction_balance） | ✅ 已跑 |
| **轨迹表示** | 仅 Trajectory 组（gap/burstiness/休眠/方向平衡） | ✅ 已跑 |
| **序列 embedding** | 动作符号序列 → 本地 TF-IDF bag-of-2-gram（方向×事件族×self，6 符号） | ✅ 800 钱包 pilot |
| **K-means** | K∈{3,4,5,6,8,10}，n_init=10 | ✅ 已跑 |
| **GMM** | n_components∈{3,4,5,6,8,10}，diag 协方差 | ✅ 已跑 |
| **HDBSCAN** | min_cluster_size∈{30,60,120}，PCA-20 + euclidean | ✅ 已跑（注意 noise 率高） |
| 层级聚类 | 备选，未跑（未来工作） | ⏳ 未跑 |
| LLM / neural embedding | 属 Group E 范围（Qwen 语义表示）；本组只用确定性本地向量化 | ⏳ 不在本组范围 |

> 序列 embedding 的 pilot 是**确定性、本地、无 GPU/无 LLM** 的 TF-IDF 表示，仅用于对比"动作顺序
> 是否带来额外聚类结构"；神经/LLM embedding 留给 Group E。

---

## 5. 评估协议

所有指标为**描述性诊断**，不做有效性/优越性结论：

1. **Silhouette**：每个 模型×表示×超参 配置的平均 silhouette（HDBSCAN 仅在非 noise 点上计算，同时报告 noise 率）。
2. **Cluster stability（子采样）**：5× 80% 无放回子样本重拟合，与全量标签的 ARI。
3. **Cluster stability（扰动）**：5× 对特征加 N(0, 0.1·std) 噪声重拟合，与全量标签的 ARI。
4. **Bootstrap consistency**：10× 有放回重采样重拟合，与全量标签的 ARI（mean + 95% 区间）。
5. **Temporal persistence**：月度快照（2022-05/06/07/08 来自 `wallet_asof_features_v1` + 2022-09）上
   K-means(K=4) 公共特征子集的（a）相邻月 ARI、（b）May vs Sep 逐特征 Spearman 秩相关、
   （c）Aug→Sep persona 转移矩阵。
6. **Downstream utility（描述性）**：per-persona 未来 30 天均值（fwd30_evt_cnt / fwd30_new_cp）；
   OLS（in-sample）`log1p(fwd30_evt_cnt)` 对 persona one-hot / 连续特征 / 二者并集的 R²，报告 ΔR²。
   **注意**：这是 in-sample 描述性 R²（persona 是同一特征的离散化，ΔR² 通常很小），
   不是时间外推验证；正式有效性需要冻结协议 + 独立 holdout。

---

## 6. 初步结果（cutoff=2022-09-01，n=18,519 钱包）

> 样本范围 = `wallet_asof_features_20220901` 分区 `2022-09-01` 的全部 18,519 个钱包（紧凑聚合表，非原始事件导出）。

### 6.1 特征覆盖率
- Activity/Counterparty/计数类资本/轨迹：**100%**（gap 类 92.96%，单事件钱包置 0）。
- 网络（matched-matched 时序子图）：**42.8%**（7,929/18,519 钱包有 >=1 条匹配-匹配边）。
- USD 资本：**91.3%**（native_usd）；token USD 仅 **35.8%**（部分 token 无价格映射）。
- 静态全窗口先验：27,613 地址（其中 18,519 在样本内），**隔离不进 Z**。

### 6.2 聚类 silhouette（完整表见 `results/clustering_summary.json`）
| 表示×模型 | 配置 | silhouette |
|---|---|---|
| full_asof × K-means | K=3 | 0.257 |
| full_asof × K-means | K=4 | 0.236 |
| full_asof × K-means | K=5 | 0.193 |
| full_asof × GMM | nc=3 | 0.200 |
| full_asof × GMM | nc=4 | 0.090 |
| full_asof × HDBSCAN | mcs∈{30,60,120} | 0.113–0.168（noise≈45–47%） |
| trajectory × K-means | K=5 | **0.396** |
| trajectory × GMM | nc=5 | 0.251 |
| network × K-means（mm 子集 n=7,929） | K=5 | 0.379 |

> 解读：纯轨迹表示的可分离性最高；全特征 K-means/GMM 为中等；HDBSCAN 在 PCA-20 上
> 把约 45–47% 钱包判为 noise，说明高维混合特征的密度结构较弱。

### 6.3 稳定性 / Bootstrap（ARI vs 全量标签）
| 模型 | subsample | perturb | bootstrap(95%CI) |
|---|---:|---:|---:|
| full_asof K-means K=4 | 0.421 | 0.417 | 0.418 [0.410, 0.428] |
| full_asof GMM nc=4 | 0.277 | 0.298 | 0.281 [0.245, 0.297] |
| trajectory K-means K=5 | 0.974 | 0.927 | 0.962 [0.912, 0.986] |

### 6.4 时间持久性
- 相邻月 persona ARI（K=4，公共特征）：May→Jun 0.60，Jun→Jul 0.56，Jul→Aug 0.46，Aug→Sep 0.47。
- May vs Sep 特征秩相关（n=17,157 重叠）：token_distinct 0.74、active_days 0.71、cp_distinct 0.70、
  evt_cnt 0.68 等"量"类特征较高；比率类较低（self_tx_rate 0.17、cp_new_rate 0.12）。
- Aug→Sep 转移矩阵（行=Aug，列=Sep，概率；persona 编号在两个月间任意）：
  p3→p3 0.722 较稳定；p1→p0 0.834、p0→p2 0.808 存在明显跨月迁移；
  p2→p1 0.750。整体相邻月 ARI 约 0.47，画像中等程度随时间演化。

### 6.5 下游效用（描述性，in-sample R² on log1p(fwd30_evt_cnt)）
| 模型 | persona-only R² | features-only R² | combined R² | ΔR²(persona 增量) |
|---|---:|---:|---:|---:|
| full_asof K-means K=4 | 0.585 | 0.704 | 0.705 | +0.001 |
| full_asof GMM nc=4 | 0.486 | 0.704 | 0.705 | +0.001 |
| trajectory K-means K=5 | 0.413 | 0.704 | 0.705 | +0.000 |
| HDBSCAN（noise 剔除 n=10,109） | 0.366 | 0.739 | 0.740 | +0.001 |
| network K-means（n=7,929） | 0.209 | 0.702 | 0.702 | +0.000 |

> persona 对"未来 30 天活跃量"已有较强的单变量描述性（R²≈0.59），但相对连续特征几乎无增量
> （persona 是同一特征的离散化，预期如此）。这**不是**时间外推的预测验证。

### 6.6 序列 embedding pilot（n=800，seed=2022，cutoff 2022-09-01）
- 平均动作序列长度 ≈ 120；TF-IDF bag-of-2-gram 维度 = 20。
- silhouette（K-means K=5）：**序列 embedding 0.232 vs 手工数值（同 800 子集）0.192**。
- 解读（描述性）：在 800 钱包小样本上，动作顺序的 2-gram 表示带来的聚类结构 ≥ 聚合数值表示；
  需要更大样本确认，属 pilot 证据。

---

## 7. Expected Failure Modes（预期失败模式）

1. **长尾 / 少数巨鲸主导**：evt_cnt 均值 145、中位数 37、max 241,523，极端尾部经 log1p+winsorize 仍可能使
   聚类被超大钱包主导 → 需要分层/裁剪或稳健聚类再做最终版本。
2. **网络特征覆盖不足**：仅 42.8% 钱包在 matched-matched 时序子图内，缺失处理（置 0 + 指示列）
   会形成"是否有匹配-匹配边"的伪聚类维度；未命中钱包的网络画像不可靠。
3. **HDBSCAN 高 noise**：约 45–47% 钱包被判 noise，密度结构弱；高维欧氏距离 + PCA 压缩的取舍需审计。
4. **月度目标集漂移**：May–Sep 重叠钱包 17,157/18,519（92.6%），目标集合逐月变化，持久性数字含
   集合变化成分；应区分"目标集漂移"与"画像变化"。
5. **USD 资本覆盖残缺**：token USD 仅 35.8%，USD 特征含选择偏差（有价格映射的 token 才计入）。
6. **未来泄漏风险点**：静态全窗口结构特征、全窗口 X 特征已隔离；任何后续将 `static_prior` 并入 Z
   都会引入泄漏，禁止。
7. **特征高度共线**：活动/对手方计数强相关（rho 0.65-0.74），冗余维度影响 GMM/HDBSCAN；
   需报告相关结构与降维消融。
8. **序列 embedding 样本过小**：800 钱包 pilot 不能外推；且 6 符号表忽略金额层级与 token 身份。
9. **下游效用是 in-sample**：R² 是描述性的，不能作为"persona 提升预测"的证据。

---

## 8. Compute Cost

- **CPU only**（未使用 GPU；V100/GPU3/GPU5 均未占用）。运行时：BigQuery 拉取 ~1-2 分钟/查询，
  本地聚类+评估 ~3-4 分钟，共约 10 分钟。
- **BigQuery bytes billed（有界、分区过滤、每查询 cap=3 GiB）**：
  - `wallet_asof_features_20220901`：10 MiB（重跑缓存命中 0）
  - `trajectory_stats`：~473 MiB（18,519 行输出）
  - `network_edges_asof`：~168 MiB（31,752 行输出）
  - `asof_features_monthly`：~22 MiB（78,786 行输出）
  - 序列 embedding pilot（800 钱包）：dry-run bytesProcessed ~467 MiB
  - **合计约 1.1–1.2 GiB**；全部为紧凑聚合结果，无整表导出。
- 本地新增依赖：`hdbscan==0.8.44`、`pyarrow`（仅读取本地 parquet；.venv-cuda 已有其余依赖）。

---

## 9. Novelty（保守声明）

- **定位**：为"动态重要钱包选择"提供**行为侧（behavioral identity）候选表示**——在固定 cutoff 上
  严格 as-of 构造 S→Z→P，并把 手工数值 / 轨迹 / 序列 embedding × K-means / GMM / HDBSCAN
  的**可审计比较协议**（silhouette + 稳定性 + bootstrap + 时间持久性 + 下游描述性效用）作为可复现工件。
- **不声称**：不声称因果、不声称有效性/优越性、不声称 SOTA、不声称"行为画像 = 重要性"。
  正式竞争力结论需 Group 0 审计通过 + 与其他 Group 表示/定义横向比较 + 独立 holdout。
- **与现有工作的区分点**：本组把"动态 persona 的稳定性/持久性/下游效用"作为可审计中间产物，
  供 Phase II 预算路由与后续 importance 定义使用；novelty 判断由首席科学家横向比较后给出。

---

## 10. 复现命令

```bash
cd /storage/gaoym/ex-graph-microtransaction-analysis
# 1) S->Z：拉取 as-of 特征 + 轨迹统计 + 网络边，构建特征矩阵（BigQuery 有界查询）
.venv-cuda/bin/python research/groupA_behavior/src/build_features.py
# 2) 月度 as-of（时间持久性用）
.venv-cuda/bin/python research/groupA_behavior/src/pull_monthly.py
# 3) Z->P：K-means / GMM / HDBSCAN + silhouette
.venv-cuda/bin/python research/groupA_behavior/src/cluster_personas.py
# 4) 评估：稳定性 / bootstrap / 时间持久性 / 下游效用
.venv-cuda/bin/python research/groupA_behavior/src/evaluate_personas.py
# 5) 序列 embedding pilot（800 钱包）
.venv-cuda/bin/python research/groupA_behavior/src/embed_sequence_pilot.py
```

> 依赖说明：BigQuery 客户端需代理环境变量（脚本内已设置
> `HTTPS_PROXY=http://10.63.0.72:7890` + ADC），与 notes/embed-server-and-bigquery-client-20260911.md 一致。

---

## 11. 文件清单

```
research/groupA_behavior/
  README.md                      # 本文档（设计 + 结果 + 边界）
  src/config.py                  # cutoff / lookback / 样本范围 / 路径
  src/bq_client.py               # 有界 BigQuery 客户端（bytes-billed 上限）
  src/build_features.py          # S->Z：特征矩阵 + 覆盖率 + manifest
  src/pull_monthly.py            # 月度 as-of 拉取（持久性用）
  src/cluster_personas.py        # Z->P：K-means/GMM/HDBSCAN + silhouette
  src/evaluate_personas.py       # 稳定性/bootstrap/持久性/下游效用
  src/embed_sequence_pilot.py    # 序列 embedding pilot（800 钱包）
  sql/asof_features_20220901.sql / asof_features_monthly.sql
  sql/trajectory_stats.sql / network_edges_asof.sql
  results/manifest.json                      # 样本/cutoff/泄漏声明/覆盖率
  results/clustering_summary.json            # 全部聚类配置数字
  results/persona_assignments_20220901.csv   # 每钱包 × 每模型 persona
  results/cluster_profiles_20220901.csv      # 每 cluster 均值 + 未来标签
  results/evaluation_20220901.json           # 稳定性/bootstrap/持久性/下游效用
  results/sequence_embedding_pilot.json      # 序列 embedding 对比
  results/data/feature_matrix_20220901.parquet   # 主特征矩阵（特征+标签）
  results/data/network_features_20220901.csv     # as-of 网络特征
  results/data/trajectory_stats_20220901.csv     # 轨迹统计
  results/data/usd_capital_20220901.csv          # USD 资本（覆盖率受限）
  results/data/static_prior_20220901.csv         # 全窗口静态先验（泄漏标记，隔离）
  results/data/asof_monthly_2022.parquet         # 月度 as-of（持久性）
```

---

## 12. 未完成项（Future Work）

1. **序列 embedding 扩样**：当前仅 800 钱包 pilot；需更大有界样本 + 金额桶/代币身份符号再验证。
2. **完整 as-of 网络特征多 cutoff 化**：当前 network 组只在 2022-09-01 计算；月度网络特征（含
   持久性）未做。
3. **层级聚类 / 更稳健聚类**：未跑。
4. **Qwen 语义摘要**：属 Group E（LLM 仅极少量代表钱包），本组未调用 LLM。
5. **有效性验证**：需 Group 0 审计 + 冻结协议 + 独立 holdout（如 2022-10 窗口）后，
   才能把"persona 对未来行为的区分度"升级为有效性证据。
6. **与 Group B/C/D 的表示融合与横向比较**：交由首席科学家。
