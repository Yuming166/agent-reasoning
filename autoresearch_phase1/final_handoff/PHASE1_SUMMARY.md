# PHASE1_SUMMARY.md — Phase-I 十五项 Scope 逐项状态（FINAL 组，2026-09-11）

- 生成: `research/final_handoff/`（FINAL 组，cloud82 10.63.0.82）
- 依据: `research/autoresearch_phase1.md` §4（Scope）+ §13/§14/§15/§16 + §25（Stop Conditions）
- 冻结协议: `research/audit/temporal_protocol.yaml` v1.0 + `research/audit/DATA_AUDIT.md`
- 状态图例: ✅ 完成 / 🟡 完成但有边界 / ❌ 未完成+原因
- 铁律: 无未来泄漏；holdout 只评估一次；不声称因果/有效性/优越性/SOTA；支持集受限与全集分开报告。

## 总览表（§4 十五项）

| # | Scope 项 | 状态 | 关键产物 | 关键数字 |
|---|---|---|---|---|
| 1 | 数据与泄漏审计 | ✅ | `audit/DATA_AUDIT.md`、`audit/temporal_protocol.yaml` v1.0、`audit/bq_metadata_2026-09-11.json` | dev/holdout 分区不重叠；11.63M dev 行/1.43M holdout 行；4 项冻结口径；7 项无法独立验证已显式声明 |
| 2 | 时序状态构造 | ✅ | Group B `wallet_asof_features_20220901`（18,519）、`labels_20220901_bq.csv`、序列组合视图 | 90 天 as-of 特征 `[2022-06-03, 09-01)`；fwd30 标签 `[09-01,10-01)`；标签 0-diff parity（B↔A↔C，CHIEF 复核） |
| 3 | 行为表示 | 🟡 | Group A `feature_matrix_20220901.parquet`（62 列）、`asof_monthly_2022.parquet` | 23 个行为特征 A_beh 复合；persona-only R²(log1p fwd30_evt)=0.585、增量 ΔR²≈+0.001（无增量）→ 描述性 |
| 4 | 动态行为画像/persona | 🟡 | Group A `persona_assignments_20220901.csv`、`cluster_profiles_20220901.csv`、`evaluation_20220901.json` | K-means K=4 bootstrap ARI 0.418 [0.410,0.428]；trajectory ARI 0.962；相邻月 ARI 0.46–0.60；HDBSCAN noise 45–47% → 无标量排名，不进正式选择器 |
| 5 | 动态社区 | 🟡 | COMM `community_membership_2022*.csv`、`community_importance_20220901.csv`、`community_evolution_summary.json` | 09-01 387 社区；top-100 中 88% bridge-only；月度 membership switch（mapped-only）0.30–0.40；掩蔽为面板 i.i.d. → 描述性 |
| 6 | 竞争重要性定义 | ✅ | CHIEF `COMPARISON.md` + `method_recommendation.md` | 5 类定义全部实现并横向对比（B 预测影响/C 结构/D 信息/A 行为/E Qwen）；B 最强 OOS 选择器 |
| 7 | 预测影响实验 | ✅ | Group B `holdout09_predictions.csv`、`predictive_results_20220901.json`、`predictive_extended09_ablation.json` | LightGBM act_level OOS R²=0.617、Spearman=0.812、Recall@top10%=0.653；new_level R²=0.564、Spearman=0.698；扩展消融轨迹/网络/USD 几乎无增量（post-hoc） |
| 8 | 信息增益/反事实 | 🟡 | Group D `wallet_ig_20220901.csv`、`SUMMARY.json`、`wallet_masking_20220901.json`、`community_masking_20220901.json` | 子集 n=2,999；wallet-masking IG(y_cp_ge10) 均值 0.406（ΔNLL）、全掩蔽 AUC→0.50；**IG 与活动/结构 top-K 近正交**；y_active30 top-IG=可预测不活跃（语义，非 bug） |
| 9 | 基准发现与对齐 | ✅ | Group F `benchmark_registry.md`、`exgraph_benchmark_note.md`、`account_classification_track.md` | TGB tgbl-coin-v2、EX-Graph LP、LiveGraphLab、自建 P4 对齐表；27,613 钱包无法干净映射进 EX-Graph LP 图 |
| 10 | 标准基准评估 | 🟡 | BENCH `BENCH_REPORT.md` + 各结果 json | TGB: 活榜 TPNet 0.832（引用）、MLP test MRR **0.7841**（实测）、EdgeBank 0.3590；EX-Graph LP heuristics test AUC 0.634–0.775；**GNN 级基线未跑**（dgl/PyG 重依赖） |
| 11 | 新基准设计 | ✅ | SELECT `README.md`、`manifest.json`、BENCH 报告 §6 | 预算化钱包选择 P4：U(K)/U(K)/K/Recall@K + 支持集纪律 + K 前沿；自建新任务 ≠ SOTA |
| 12 | 预算化选择评估 | ✅ | SELECT `selection_results_20220901.json`、`budget_frontier.csv`、`robustness_0801.json` | 25 选择器 × 7 K；B_act K=10 U/K=2,072（fwd30_evt）≈随机期望 19.57 的 106×；全层级基线同表；08-01 walk-forward 描述性对照 |
| 13 | 跨方法稳健性 | 🟡 | CHIEF `consensus_analysis/results/*`（rank_correlation、pairwise_jaccard、uniqueness、future_utility、consensus_frequency） | B_act↔A_vol ρ=0.930、top-100 Jaccard 0.46；B_act↔C_struct ρ=0.536；D 唯一性最高（top-100 0.94）；B∩C∩A K=100 n=28（随机期望 0.016）；**多 cutoff walk-forward 未跑（单点 09-01）** |
| 14 | 最终选择/排名 | ✅ | `final_handoff/final_ranking_20220901.csv`、`final_topk_lists_20220901.csv/.json`、`final_evaluation_20220901.json` | 主=B_act、次=C_struct、基线=A-vol/随机、共识=B∩C∩A；单次冻结评估：B_act K=10 U/K=2,072.3、K=100=458.4、Recall@K(新对手方) K=1000=0.094 |
| 15 | Phase-II 交接 | ✅ | `final_handoff/PHASE2_HANDOFF.md` | 动态 I_i(t) 按 cutoff 交付物、数据契约、LLM 端点、外部基准钩子、排除范畴、8 项开放项 |

## 逐项细节与证据（仅摘录关键 claim 边界）

### 1 数据与泄漏审计 — ✅
- dev 最大分区 20220831 < holdout 最小分区 20220901（已实测）；schema 差异（trace_address 类型）
  已冻结为走组合视图/显式 CAST；静态图/未来价格/未来推文不得进入 as-of 特征；
  P3 同快照排名仅演示。7 项无法验证（外部源表完备性、twitter_matching 来源、sentiment 派生等）已显式声明。

### 2 时序状态构造 — ✅
- 09-01 as-of 快照 18,519 钱包（27,613 目标中有 90 天事件的活跃子集）；fwd30 标签三列
  （evt_cnt/cp_distinct/new_cp）由 Group B 有界拉取（bytesBilled≈10MB），与 A/C 内嵌标签 0-diff。

### 3 行为表示 — 🟡 完成但有边界
- 62 列 as-of 数值特征（活动/对手方/轨迹/USD/静态结构）。序列 embedding 仅 800 钱包 pilot
  （silhouette 0.232 vs 数值 0.192）——小样本，不外推。

### 4 动态行为画像 — 🟡
- persona 是离散画像，无标量排名；对连续特征预测无增量（ΔR²≈+0.001）；
  网络覆盖 42.8%、USD 覆盖 91.3%/35.8% 存在选择偏差 → 只做描述性/解释层。

### 5 动态社区 — 🟡
- 09-01 387 社区、top-100 88% bridge-only、HHI 0.2442；月度节点集漂移大（新节点 7–10%/月）；
  switch rate 需区分集合漂移 vs 归属变化（COMM 已用 Hungarian 匹配改进）；
  community-masking 为面板 i.i.d.，跨钱包影响未覆盖。

### 6 竞争重要性定义 — ✅
- A(行为)/B(预测影响)/C(结构)/D(信息增益)/E(Qwen 语义) 五类实现；CHIEF 横向对比表完成；
  E 组仅 n=200，不进 top-K 共识。

### 7 预测影响实验 — ✅
- 严格时序 OOS：train 06-01 / val 07-01 / frozen-test 08-01 / holdout 09-01；
  LightGBM act_level 为最强选择器；扩展消融（轨迹/网络/USD）为 post-hoc，无增量如实报告。

### 8 信息增益/反事实 — 🟡
- 2,999 子集上 wallet-masking 与 feature-masking IG 已跑（面板 i.i.d. 设定）；
  低量高信息子组（n=15，IG +1.61 / volume $2）需 walk-forward 复核；
  反事实解释限于"遮蔽该钱包状态后预测性能变化"，非跨钱包传播因果。

### 9 基准发现与对齐 — ✅
- registry 覆盖 TGB(tgbl-coin-v2/tgbn-token)/EX-Graph LP/LiveGraphLab/P3 标签；
  对齐结论：27,613 目标 ↔ EX-Graph LP 图无干净映射，外部通道只能图级/全图验证。

### 10 标准基准评估 — 🟡 完成但有边界
- TGB/EX-Graph LP 最小闭环已实测（见 PHASE2 §6 表）；GNN 级模型未跑（环境重依赖），
  论文表 5 数字仅引用非实测；EX-Graph leaderboard 404 无法提交。

### 11 新基准设计 — ✅
- P4 预算化钱包选择（as-of 选择 → 冻结 top-K → fwd30 效用）已成型：指标、支持集纪律、
  K 前沿、oracle/随机参考均已定义并产出 09-01 结果。

### 12 预算化选择评估 — ✅
- 25 选择器 × 7 K 全层级基线（§14 要求项全部覆盖：random/size/structural/behavioral/
  temporal/predictive/information + hybrid）；`budget_frontier.csv` 231 行原生 + 322 行受限；
  08-01 描述性稳健对照已跑（`robustness_0801.json`）。

### 13 跨方法稳健性 — 🟡 完成但有边界
- 秩相关/重叠/唯一性/共识频率/未来效用已全部量化（CHIEF §2、§3）；
  **未完成**：多 cutoff walk-forward（B/C/D 现为单 cutoff 09-01）→ 已移交 Phase-II 开放项 #1；
  事件级 next-counterparty MRR 未做 → 开放项 #2。

### 14 最终选择/排名 — ✅
- 按 CHIEF 推荐：主=B_act、次=C_struct、强制基线 A-vol/随机、共识组合 B∩C∩A；
  产出见 §"总览表"第 14 行与 `final_evaluation_20220901.json`（verification.parity_ok=true，
  与 SELECT/CHIEF 冻结数字逐项一致）；五维向量支持集边界在 CSV 中以 NaN + 标志列标注。

### 15 Phase-II 交接 — ✅
- PHASE2_HANDOFF.md 完整回答"固定预算下把昂贵推理花在哪些钱包上"：按 B_act top-K 分配、
  结构/信息侧单独记账、数据契约/LLM 端点/外部基准钩子/排除范畴/8 项开放项齐备。

## Stop Conditions 对照（§25）

| 条件 | 状态 |
|---|---|
| 1 时间协议审计 | ✅ v1.0 冻结 |
| 2 泄漏审计通过 | ✅ |
| 3 多种重要性定义已测 | ✅ 5 类 |
| 4 强基线已评估 | ✅ §14 全层级 |
| 5 至少一次严格 OOS 评估 | ✅ 09-01 冻结 holdout 单次 + 08-01 描述性 |
| 6 基准兼容性已评估 | 🟡 TGB/EX-Graph LP 实测；GNN 级未跑 |
| 7 动态 persona 分析充分 | 🟡 描述性充分，选择增量≈0 |
| 8 重要钱包排名可复现 | ✅ build_final.py 确定性复现，与冻结数字 parity |
| 9 K 预算曲线 | ✅ |
| 10 最终选择策略冻结 | ✅（09-01；多 cutoff 策略移交 Phase-II） |
| 11 Phase-II 交接完成 | ✅ |

> 结论：Phase-I 在 2022-09-01 单点冻结评估上完成全部 15 项（其中 4 项带边界、0 项阻塞）；
> 未将代理成本/图中心性/预测 R² 重贴为因果/优越性/SOTA；高阶级递归范畴未触碰。
