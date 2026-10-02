# Chief Scientist Merge — Phase I 横向对比（autoresearch_phase1.md §19）

- 角色: Chief Scientist（合并 + 跨方法共识组）
- 日期: 2026-09-11（本机 cloud82, 10.63.0.82）
- 冻结协议: `research/audit/temporal_protocol.yaml` v1.0（2026-09-11 冻结）+
  `research/audit/DATA_AUDIT.md`
- 统一 cutoff: **2022-09-01**；特征窗口 `[2022-06-03, 2022-09-01)`；标签窗口
  `[2022-09-01, 2022-10-01)`（fwd30_*）
- 铁律引用: 所有数字为描述性；无未来泄漏；**不声称因果/有效性/优越性/SOTA**。
- 跨方法量化数字来源: `consensus_analysis/results/*.csv|json`（本组实测，脚本
  `consensus_analysis/run_consensus.py`），组内数字来自各组 README/JSON（已逐项复核）。

## 1. 横向对比表（§19 要求字段）

| Method | Importance Definition | Future Utility（量化，样本与 cutoff） | Stability | Cost（BigQuery GiB / LLM 调用 / 时间） | Novelty | Leakage Risk | Benchmark Fit（Group F registry） |
|---|---|---|---|---|---|---|---|
| **A Behavior-First（persona）** | 动态行为画像 P_i(t)：as-of 特征聚类（full_asof/trajectory/network × K-means/GMM/HDBSCAN）；离散 persona，非标量排名 | 描述性 in-sample：persona-only R²(log1p fwd30_evt)=**0.585**（K-means K=4, n=18,519, cutoff 09-01）；features-only 0.704，persona 增量 ΔR²≈**+0.001**（无增量）；per-persona 未来活动均值 1.0–128.6 | 聚类稳定性：K-means K=4 bootstrap ARI **0.418** [0.410,0.428]；trajectory K-means ARI 0.962；相邻月 persona ARI 0.46–0.60（中等演化）；HDBSCAN noise 45–47% | BQ ≈**1.1–1.2 GiB**（分区分页上限，合计）；CPU ~10 分钟；无 LLM | 弱：as-of 行为身份框架 + 序列 embedding pilot（800 钱包, silhouette 0.232 vs 数值 0.192）；非 SOTA | 低：as-of 特征，静态先验隔离；network 覆盖 42.8%、USD 91.3%/35.8% 有选择偏差；下游效用为 in-sample 描述 | 无直接基准；§7 外部标签验证候选（P3：eth-labels/Forta/LiveGraphLab trader 标签） |
| **A-vol / A-beh（基线，§14）** | A-vol=evt_cnt_90d（量）；A-beh=行为复合分（本组按 §14 从 A as-of 特征矩阵重建：23 个 activity/counterparty/trajectory 特征百分位均值） | A-vol top-K 未来 30 天活动均值：K=10 **1779.6**、K=100 429.7、K=1000 125.1（n=18,519, lift 6.4–91× vs 全集均值 19.57）；A-beh：K=10 377.9、K=100 282.2（lift 14–19×） | A-vol Spearman(历史 evt vs fwd30 evt)=0.741；月度 top-10% 重叠 60–64%（与 B 相同现象） | 零额外成本（复用 A 数据） | 无（强制性基线，§14） | 低（as-of） | §14 基线层级必选；P4 预算化选择基线 |
| **B Predictive-Influence-First** | importance_B = 历史状态 S_i(t) 对未来行为 Y_i(t,t+30d) 的可预测性增益（端到端模型输出：活动水平 / 新边水平） | **最强 OOS 选择器**（n=18,519, holdout 09-01）：LightGBM act_level R²=**0.617**、Spearman=0.812、Recall@K(top10%)=0.653；new_level R²=0.564、Spearman=0.698、Recall@K=0.597；top-K 未来活动均值 K=10 **2072.3**（lift 106×）、K=100 458.4（23.4×）；相对基线增量：act R² +0.143（vs active_days_90d R²=0.474），new Spearman +0.036 | 持久性强：月度 top-10% 重叠 60–64%；Spearman(future activity) 0.73–0.79（4 个月）；跨 Aug→Sep regime 稳定；高度社区集中（社区 5+8 占人口 17.5%，承载预测 top-10% 的 ≈93%） | BQ ≈**0.01 GiB**（09-01 标签有界拉取，bytesBilled≈10MB）；CPU ~5 分钟；无 LLM | 中：端到端 OOS 预测增益定义，非 SOTA；扩展特征消融（轨迹/网络/USD 几乎无增量）已跑 | 低：严格时序 OOS（train 06-01 / val 07-01 / frozen test 08-01 / holdout 09-01），特征 as-of，无未来泄漏；扩展消融为 post-hoc | 无直接公共基准；P4 预算化选择器首选候选；与 Group C 共享 next-counterparty 候选池（未做 MRR，见未完成项） |
| **C Temporal-Graph-First** | 结构重要性：as-of matched-matched 时序子图（7,929 节点）上 6 项百分位复合 `structure_pct`（wdeg/PR/kcore/betweenness/bridge/recency_wdeg）；消融 `structure_novol_pct`（不含体量） | 描述性（支持集 n=7,929, cutoff 09-01）：structure_pct vs fwd30_evt ρ=**0.435**（volume_pct 0.750）；top-K 未来活动均值 K=10 **1592.9**（lift 46.7× vs 子图均值 34.08）、K=100 349.3（10.2×）；**volume 始终 > structure**（K=100: 429.7 vs 349.3）；`structure_novol_pct` K=10 更高（1794.6） | 静态 vs as-of 秩相关弱（top-100 重叠 6–9%）⇒ 全窗口先验不可替代 as-of；structure vs volume ρ=0.575；structure vs P2 影响 proxy ρ=**−0.036**（正交） | BQ ≈**0.16 GiB**（单次有界拉取 176MB）；CPU ~8 分钟（含全量 betweenness）；无 LLM | 中-弱：as-of 结构 vs 静态先验量化差异；"低量高结构"在严格阈值下几乎不存在（0–1 个）、"高量低结构"存在（248 个） | 低：as-of，静态先验仅作 leaky 基线；支持集 42.8% 限制，不外推全集 | P1 EX-Graph LP（图级外部验证，官方 split）；P4 结构基线；flow 方向化需固定语义（PR 秩相关仅 0.591） |
| **D Information-Gain / Counterfactual** | IG_i(t)=ΔNLL(钱包级 occlusion 掩蔽)，主口径 `ig_y_cp_ge10_histgbm`（未来 ≥10 个对手方）；目标相关，报告必须绑定目标 | 描述性（子集 n=2,999, cutoff 09-01）：IG 均值 ΔNLL=+0.406（中位 0.558）；top-50 IG 掩蔽 ΔNLL=+1.796 vs volume top-50 +0.988；top-K IG 钱包未来活动均值 K=10 **100.4**（lift 5.2× vs 子集均值 19.18）、K=100 72.3（3.8×）——远低于 B/A-vol；**目标关键**：y_active30 的 top-K IG 全是"可预测不活跃"钱包（fwd30_evt=0） | 同目标跨模型 Spearman 0.86–0.91；跨目标仅 0.23–0.35（目标相关）；permutation vs 中位掩蔽 ρ=0.61 | BQ ≈**0.03 GiB**（ICF v2 对照 30MB）；CPU ~5 分钟；无 LLM | 中：occlusion 钱包级 IG + 与 volume/degree/PR/ICF 正交性（ρ≈0.2–0.37，top-K Jaccard 2–7× 随机）；IG 与 volume 弱正相关（Spearman 0.306, OLS R²=0.025） | 低：as-of 特征、5 折 OOS、fwd30 仅评估；面板 i.i.d. 边界（跨钱包 IG 需事件级任务）；子集 2,999 不外推 | 无直接基准；P4 选择器候选（须目标匹配）；ICF v2 对照为 08-01 快照（cutoff 不匹配，已标注） |
| **E Qwen Behavioral Representation** | 语义行为画像：Qwen3.5-4B 结构化摘要 + Qwen3-Embedding-0.6B → PCA-64 表示 | 描述性（n=200 代表子集, cutoff 09-01）：R_qwen OOF R²(log1p fwd30)=**0.23–0.34**（Spearman 0.57–0.62, kNN 0.46–0.51）；低于纯数值 R_num 0.59–0.64；拼接 R_num+qwen **未超越**纯数值（α=1 退化, α=10 仍低） | 指令跟随 Kendall τ=**0.81**（与数值活动档一致，非 ground truth）；embedding 与数值不冗余（数值 OOF 预测 embedding 维平均 R²=−0.18） | BQ **0**；LLM **200 chat 调用**（prompt 174,399 + completion 38,840 tokens）+ **13 embedding 调用**（1024 维）；~2s/调用；GPU 复用既有服务 | 中-弱：as-of 语义表示 + 冗余度量化；严格互补性未证实（负 delta 如实报告）；非 SOTA | 低：prompt 仅 as-of 数据，fwd30 不参与生成；200/200 泄漏扫描通过；小样本（n=200）不外推 | 无直接基准；§7 外部标签验证候选；更大样本（1k–3k）验证互补性后才有选择器意义 |
| **F Benchmark / SOTA Track** | （基准层，无重要性定义）registry + 接入计划 | 外部通道：TGB `tgbl-coin-v2` MRR **0.832**（TPNet, 2026-09-11 实测活榜）；`tgbn-token` NDCG@10 0.513（NAVIS）；EX-Graph LP 官方 split（论文参照 APPNP with-X AUC 0.89±0.02, GraphSAGE wo-X 0.84）；预算化钱包选择（§8/§9）无现成公共基准 → 自建 | — | TGB 下载 1.28GB×2；EX-Graph LP 最小闭环 0.5–1 GPU-天；P3 标签为 MB 级本地 join | 中-高（自建新基准 P4）；"新基准 ≠ SOTA" | 官方协议即无泄漏；外部验证只做时点 | 本列为基准参考；推荐优先级：TGB ＞ EX-Graph LP ＞ LiveGraphLab ＞ 账户分类标签验证 ＞ 自建 P4 |

> 横线说明：**A 组未提交标量重要性排名**，`A-vol`/`A-beh` 为本组按方案 §14 基线层级从 A 的
> as-of 特征矩阵重建（脚本内列出确切 23 个特征），作为"行为/volume 类基线"参与共识分析；
> A 组官方产物是 persona 聚类（离散、描述性）。E 组只覆盖 200 钱包，不进入 top-K 共识。

## 2. 关键横向结论（Chief Scientist 摘要）

1. **预测影响（B）是未来活动/新边的最强选择器**，但**体量基线（A-vol）紧追其后**：holdout
   09-01 上 B_act 与 A_vol 的 top-K Jaccard=0.46（K=100, 63/100 重合）、秩相关 ρ=0.93。
   B 相对体量的可度量增量集中在**回归 R²**（+0.143）与 Spearman（+0.02~0.03），不是"换了一组
   完全不同的钱包"。
2. **结构（C）是第二维**：与体量 ρ=0.57、top-100 与 B 重合 35 个；`structure_novol_pct`
   不含体量后仍与活动中等相关（ρ=0.64 于 evt），但选择器效用低于 A-vol/B。
3. **信息增益（D）是独立第三维**：top-K 与 B/A/C 重合 2–4/100（≈5–7× 随机但绝对极小），
   其 top-K 钱包未来活动均值远低于 B/A-vol（K=10: 100 vs 2072/1780）——**IG 回答"谁的过去最能
   消除未来不确定性"，不回答"谁未来最活跃"**；且目标绑定（y_active30 的 top-IG 是"可预测不活跃"）。
4. **共识≠正确性（§17）**：B/A/C 的高一致集（all-3, n=7,929 支持集）K=100 有 28 个钱包
   （随机期望 0.016），其 fwd30 活动均值 916.9（lift 26.9×），但该共识主要反映**活动量驱动的
   一致选择**；D 加入后 4 方共识在 K≤100 几乎为 0（≈随机），K=250 才 7 个。见
   `consensus_analysis/README.md`。
5. **成本纪律达标**：本组新增 BigQuery = 0（标签复用 Group B 已拉取并 parity 校验的
   `wallet_asof_features_20220901`，bytesBilled≈10MB）；全组 BQ 合计 ≈1.3 GiB（A 1.1–1.2 +
   C 0.16 + B 0.01 + D 0.03），远低于 3 GiB 建议；无 LLM；CPU only。
6. **未验证项**：next-counterparty MRR（需 `nc_ranker_samples_v2` 支持集/full-vocabulary 双口径）、
   多 cutoff walk-forward（B/C/D 目前单 cutoff 09-01）、E 组更大样本互补性、C 组 flow 方向语义固定、
   TGB/EX-Graph LP 实际跑分（BENCH 组进行中）。

## 3. 样本与 cutoff 边界（所有数字必须附带）

| 数字 | 样本 | cutoff | 标签窗口 |
|---|---|---|---|
| B OOS R²/AUC、B/A-vol top-K 效用 | n=18,519（`wallet_asof_features_20220901` 全量） | 2022-09-01 | [09-01,10-01) |
| C 结构相关/效用 | n=7,929（matched-matched 时序子图，42.8% 覆盖） | 2022-09-01 | [09-01,10-01) |
| D IG 相关/效用 | n=2,999（代表性子集） | 2022-09-01 | [09-01,10-01) |
| E OOF R² | n=200（分层代表子集） | 2022-09-01 | [09-01,10-01) |
| 4 方共识（B,C,D,A） | n=1,283（B∩C∩D） | 2022-09-01 | [09-01,10-01) |
| 3 方共识（B,C,A） | n=7,929（B∩C） | 2022-09-01 | [09-01,10-01) |

> **不得外推**：C 的 7,929 / D 的 2,999 / 4 方共识的 1,283 支持集结论，不能作为全 18,519
> 或全 27,613 的结论（协议 support-restricted vs broad/full 分开报告）。

## 4. 证据核对备注（Chief Scientist 复核）

- 本组逐项复核各组 JSON/README 数字；发现 1 处内部不一致并已按**原始输出**取值：
  Group D `README.md §5.5` 写 `IG ~ log1p(volume) slope=+0.306, R²≈0.09`，但 `results/residual_20220901.json`
  （summarize.py 原始输出）为 `slope=0.0332, R²=0.025`；用 `ig_vs_baselines_20220901.csv` 重算确认
  OLS slope=0.0332、R²=0.025、Spearman(IG, log volume)=0.306。本表一律采用原始 JSON/重算值，
  并提示 Group D 后续修订 README 措辞（README 的 0.306 实际是 Spearman，R² 0.09 未复现）。
- Group B 的 `labels_20220901_bq.csv` 与 Group A `feature_matrix` 及 Group C `wallet_importance` 的
  fwd30 标签逐行 0 diff（本组复核），共识分析直接复用该标签文件，新增 BigQuery 查询 = 0。
