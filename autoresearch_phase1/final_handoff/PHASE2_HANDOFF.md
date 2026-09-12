# PHASE2_HANDOFF.md — Phase-I → Phase-II 交接（FINAL 组，2026-09-11）

- 生成: `research/final_handoff/src/build_final.py`（FINAL 组，cloud82 10.63.0.82）
- 冻结协议: `research/audit/temporal_protocol.yaml` v1.0（2026-09-11 冻结）+ `research/audit/DATA_AUDIT.md`
- 主方案: `research/autoresearch_phase1.md`（§23 H Phase-II handoff / §28 / §29）
- 本文件回答: **给定固定推理预算，Phase II 应把昂贵的可信推理花在哪些钱包上、何时、为什么？**
- 边界铁律: 选择层证据 ≠ 因果/有效性/优越性；不触碰最终 holdout；K 不在 holdout 上调参。

## 1. 一句话交接

在 cutoff=2022-09-01、只用严格早于 cutoff 的 as-of 信息、fwd30 只用于一次评估的冻结设定下，
**主选择器 = Group B 预测影响（未来活动水平，`pred_act_level_LightGBM`）**，次级 = Group C 结构
重要性（`structure_pct`），强制并跑基线 A-vol/随机，共识组合 B∩C∩A 作为"三法一致"稳健子集；
Phase II 推理预算应按 B_act 的 top-K（K∈{10,25,50,100,250,500,1000}）分配，
并对结构侧（C）与信息侧（D，正交维度）单独记账，不做支持集外推。

## 2. 推荐方法、边界与量化结果（cutoff=2022-09-01，n=18,519）

| 角色 | 方法 | 分数 | 支持集 | 单次冻结评估关键数字（fwd30，[09-01,10-01)） |
|---|---|---|---|---|
| 主选择器 | B_act（预测影响·活动水平） | `pred_act_level_LightGBM`（06/07/08 训练/调/冻结测试，09-01 应用） | full 18,519 | OOS R²=0.617、Spearman=0.812、Recall@top10%=0.653；U/K K=10: 2,072.3（lift 106×）、K=100: 458.4、K=1000: 130.7（fwd30_evt 均值；全集均值 19.57） |
| 次级选择器 | C_struct（结构重要性） | `structure_pct`（wdeg/PR/kcore/betweenness/bridge/recency_wdeg 百分位复合） | structural 7,929（42.8%） | 子图内 U/K K=10: 1,592.9（lift 46.7× vs 子图均值 34.08）；**vol 恒 > struct**；与 B 秩相关 ρ=0.536 |
| 强制基线 | A-vol（体量） | `evt_cnt_90d` | full 18,519 | U/K K=10: 1,779.6、K=100: 429.7；与 B_act 秩相关 0.930、top-100 Jaccard 0.46（63/100 重合）→ B 的增量在回归 R²（+0.143）而非"换了完全不同的钱包" |
| 强制基线 | 随机 | seed=20220901 单次 + 解析期望 | full 18,519 | 解析期望 U/K=19.57（fwd30_evt）；单次抽样见 frontier |
| 辅助 | B_new（未来新对手方水平） | `pred_new_level_LightGBM` | full 18,519 | OOS R²=0.564、Spearman=0.698；U/K K=10: 2,043.0 |
| 辅助 | A_beh（行为复合） | 23 个 as-of 行为特征百分位均值 | full 18,519 | 与 B_act 秩相关 0.965（几乎同序）；persona 聚类仅描述性 |
| 正交维度 | D_ig_cp（信息增益） | `ig_occ`（histgbm, y_cp_ge10） | ig 2,999（16.1% 正样本覆盖） | K=10 U/K=100.4、K=1000 Recall@K=0.471（IG 支持集内）；与 B/C/A top-K 几乎不相交（K=10 为 0）→ **回答"谁的过去最能消除未来不确定性"，不回答"谁未来最活跃"** |
| 共识子集 | B∩C∩A（三法全一致） | B_act∩C_struct∩A_vol top-K 交集 | 7,929 | K=100 n=28（随机期望 0.016，≈1,760×），共识钱包 fwd30_evt 均值 916.9（lift 26.9×）；K=10 n=1（0xcda72070…，fwd30 evt 14,179）；**共识≠正确性（§17）** |

边界（必须随数字一起引用）:
- 结构 7,929 / IG 2,999 / 4 方共识 1,283 支持集结论**不得外推**到全 18,519 或全 27,613；
  支持集受限与全集口径分开报告。
- B_act 与 A_vol 排序几乎=体量排序（ρ=0.93），不得包装成"发现全新的重要钱包"；
  诚实表述为"预测影响在体量基线上提供回归 R²/Spearman 增量"。
- 静态全窗先验（static_degree/static_pagerank）是 LEAKY 基线，**不得**用作 as-of 预测特征。
- IG 的 y_active30 目标选出的是模型最"确信不活跃"的钱包（top-K 未来效用为 0），
  这是未取绝对值的遮蔽 IG 在负例上的语义，不是 bug。

## 3. 动态重要性向量 I_i(t) 与按 cutoff 交付物（Phase-II 必读）

Phase-I 只在**最终 holdout 09-01** 上完成一次冻结评估。方案 §13 要求的"多 cutoff walk-forward"
**尚未运行**（CHIEF §5 已明示），这是 Phase-II 的首要任务。I_i(t) 的构造与交付物如下：

### 3.1 I_i(t) 五维向量（09-01 已产出，见 `final_ranking_20220901.csv`）

```
I_i(t) = [ I_behavior(t), I_network(t), I_predictive(t), I_information(t), I_temporal(t) ]
```

| 维度 | 分数列（final_ranking 中） | 来源（只读输入） | 支持集 | 缺失语义 |
|---|---|---|---|---|
| I_behavior | `I_behavior`（=A_beh，23 个 as-of 行为特征百分位均值） | groupA feature_matrix | full 18,519 | NaN=无 |
| I_network | `I_network`（=structure_pct）; 消融 `I_network_novol` | groupC wallet_importance | structural 7,929 | **NaN=未命中子图（不做外推）** |
| I_predictive | `I_predictive`（=pred_act_level_LightGBM）; `I_predictive_new` | groupB holdout09_predictions | full 18,519 | NaN=无 |
| I_information | `I_information`（=ig_occ, histgbm, y_cp_ge10）; `I_information_active` | groupD wallet_ig | ig 2,999 | **NaN=不在 D 子集（不做外推）** |
| I_temporal | `I_temporal`（=recency+accel(cp_new_rate_30d)+persistence(active_span_days_90d) 百分位均值；原始分量见 score_recency/cp_new_rate_30d/active_span_days_90d） | groupA feature_matrix | full 18,519 | NaN=无 |

支持集纪律: 各维缺失维度=NaN，**不做外推**；报告必须同时给支持集受限与全集两个口径
（协议 §5 reporting_rules）。

### 3.2 按 cutoff 的动态交付物（Phase-II 模板，09-01 已按此产出）

对每个 cutoff t（已有快照 05/06/07/08/09；新 cutoff 需重新跑）：

1. as-of 特征 `wallet_asof_features_*`（`[t-90d, t)` 主事件族）→
2. 在 `[t-90d, t)` 重建 as-of 时序子图（结构）与 IG 面板（D 子集）→
3. 冻结 B 模型（train 用更早快照 strictly < t；t=09-01 已冻结）→ 输出
   `final_topk_lists_{t}.csv/.json`（K∈{10,25,50,100,250,500,1000}）、
   `final_ranking_{t}.csv`（五维 + 各方法排名 + 共识投票 + 支持集标志）、
   `final_evaluation_{t}.json`（U(K)、U(K)/K、Recall@K、仅一次评估）。
4. 评估标签一律 `[t, t+30d)`（fwd30_*），标签源 = `wallet_asof_features_*` 内嵌或 BQ 有界拉取。

> Phase-II 不得因更早/更晚 cutoffs 的分数好坏而回到 09-01 重选 K/重选模型（协议 §4：no tuning on the final holdout）。

## 4. 数据契约（Phase-II 引用清单，全部已冻结/已审计）

| 对象 | 契约 | 证据 |
|---|---|---|
| 目标地址 | `ictdata-507912.exgraph.target_addresses`（27,613 行）; X 匹配 `exgraph_x_matches_v1`（地址+node_id only） | temporal_protocol.yaml §6 |
| dev 事件 | `external_transactions_20220301_20220901`(2,877,009) / `token_transfers_20220301_20220901`(4,275,544) / `internal_traces_20220301_20220901`(4,478,515) | 同上 |
| holdout 事件 | 对应 `_20220901_20221001` 三表（333,303 / 497,746 / 571,343） | 同上 |
| 序列表 | `target_event_sequences_20220301_20220901`(11,836,196) / `_20220901_20221001`(1,428,845) / **组合视图** `target_event_sequences_20220301_20221001`（跨窗必须走视图或显式 CAST，trace_address dev=REPEATED INT / holdout=STRING） | DATA_AUDIT §2.4 |
| as-of 特征 | `wallet_asof_features_v1`(78,786; 快照 05/06/07/08) + `wallet_asof_features_20220901`(18,519; 09-01) | 同上 |
| 标签 | 主事件族 `[t,t+30d)`；排除 `counterparty_present=false` 与自交易；**labels_20220901_bq.csv 与 A/C 内嵌标签逐行 0 diff（CHIEF 复核）** | temporal_protocol.yaml §2/§5 |
| 候选排序 | `nc_ranker_samples_v2`(28,472,717; 快照 06/07/08; sentinel `g_rank=99999` 在正样本) → 支持集 vs full-vocabulary **分开报告** | temporal_protocol.yaml §6 |
| SQL/脚本 | `src/sql/create_*_ictdata.sql`（权威 DDL）; `src/bq_run.py`（代理 10.63.0.72:7890 + ADC，**必须分区过滤 + bytes-billed 上限，禁止整表导出**）; 只读审计脚本 `research/audit/audit_query.py` | temporal_protocol.yaml §7 |
| hash | gpickle sha256 `27c86772…d5db2`; twitter csv `3cd10be6…1a9e`; 1min 价格 `faa76408…e73`; EX-Graph LP pkl `074bc973…42cd`（BENCH 重算一致） | DATA_AUDIT §2.7 / BENCH_REPORT §1.1 |
| BigQuery 预算 | Phase-I 全组合计 ≈1.3 GiB（A 1.1–1.2 + C 0.16 + B 0.01 + D 0.03）; Phase-II 每次 cutoff 拉取须设字节上限并记录 job_id/bytes billed | COMPARISON §2.5 |

## 5. LLM 端点（Phase-II 若做推理/表示，仅限以下本地端点）

- Qwen chat: `http://127.0.0.1:31518/v1`（Qwen3.5-4B；base_url 不含 /chat/completions；
  **勿发 reasoning_effort**）
- Embedding: `http://127.0.0.1:31522/v1`（Qwen3-Embedding-0.6B；OpenAI 兼容 /v1/embeddings，1024 维）
- Phase-I 使用边界: 仅 Group E 200 钱包描述性试点（R_qwen OOF R² 0.23–0.34 < 数值 0.59–0.64；
  拼接未超越纯数值）。**LLM 不是最终选择器的一部分**；把代理成本/图中心性/预测 R² 重贴为
  "因果影响/推理收益"一律禁止。E 组大样本互补性验证为开放项。
- GPU 纪律: 勿占用 GPU4(Qwen chat)/GPU6(Hy-MT)；GPU3=embed 服务；GPU0-2、GPU5 可用。

## 6. 外部基准钩子（引用 BENCH 结果，BENCH_REPORT.md 2026-09-11）

| 通道 | 状态 | 数字（实测，除非注明） | Phase-II 用法 |
|---|---|---|---|
| TGB `tgbl-coin-v2` | ✅ 下载+EdgeBank+MLP | 活榜 TPNet test MRR 0.832±0.001（2026-09-11 实测）；Heuristic 0.774；本组 MLP(7-feature, leak-free streaming) test MRR **0.7841**（高于 Heuristic/DyGFormer 0.752，低于 TPNet）；EdgeBank unlimited test MRR 0.3590 | 全图 638,486 节点外部验证；官方 zip 无法取 27,613 钱包子集；CC BY-NC，**不得并入对外发布数据包** |
| EX-Graph LP 官方 split | ✅ 启发式基线 | 官方 pkl 1,709,575 节点/13,170,869 边；heuristics test AUC 0.634–0.775（PA 0.7754 最高）；论文表 5 自报 APPNP with-X AUC 0.89±0.02、GraphSAGE wo-X 0.84（**非本组实测**）；有向 CN 敏感性 AUC 0.5801 | 27,613 目标无法干净映射进 LP 图（图级验证边界，BENCH §1.5）；官方 GNN 基线（dgl/PyG）**未跑** |
| EX-Graph leaderboard | ⚠️ 404 | exgraph.deno.dev 当前 404（Group F 实测） | 无法提交/对比活榜单 |
| 新基准（§8/§9 预算化钱包选择） | ✅ 自建 P4 | 本 handoff 的 U(K)/U(K)/K/Recall@K 即新任务口径 | **新任务 ≠ SOTA**；发布叙事 = 新任务 + 强基线 + 选择器增量 |

## 7. 明确排除的高阶递归范畴（Phase-II 不得把以下当 Phase-I 已验证）

- 高阶递归推理 / 递归辩论 / 递归证据图
- 多步 LLM 推理 rollout / 对全部钱包的昂贵 LLM 推理
- 最终市场交易 agent
- 未经有效因果识别策略的"因果影响力"声明
- 把 P1/P2 proxy（ICF/trigger）当作"推理价值"证据（CHIEF §3.3 明确排除）

以上范畴属于 Phase-II 的研究对象，但**不得**引用 Phase-I 数字作为其有效性的证据。

## 8. 遗留开放项清单（Phase-II 优先级）

1. **多 cutoff walk-forward（最高优先）**：05/06/07/08 快照各训练一次、滚动评估 06→09；
   当前仅 09-01 单点冻结评估。方法与边界见 §3.2。
2. **next-counterparty MRR（事件级）**：用 `nc_ranker_samples_v2` 支持集 vs full-vocabulary
   双口径（sentinel 纪律）；当前只有选择层，未做事件级 MRR。
3. **C 组 flow 方向语义固定**：flow 方向化后 PR 秩相关仅 0.591，须在正式版固定并报敏感性。
4. **D 组 IG 符号/绝对值语义**：y_active30 的遮蔽 IG 在负例上的语义（top-K 未来效用 0）需文档化；
   低量高信息钱包（n=15 子组，均值 IG +1.61、均值 volume $2）需在 walk-forward 复核。
5. **E 组更大样本互补性**：200→1k–3k 验证 Qwen 语义表示是否与数值互补；当前无选择器意义。
6. **社区口径**：switch rate 需区分"集合漂移 vs 归属变化"（COMM 已用 Hungarian 匹配，
   mapped-only 0.30–0.40/月）；掩蔽为面板 i.i.d.，跨钱包影响未覆盖。
7. **TGB/EX-Graph GNN 基线**：TGN/DyGFormer 级与 EX-Graph 官方 11 模型需 dgl/PyG 重依赖，
   Phase-I 未跑（超出最小闭环）。
8. **动态 I_i(t) 生产化**：把 build_final.py 参数化为任意 cutoff t（当前硬编码 09-01）。

## 9. 交付物索引（research/final_handoff/）

- `final_topk_lists_20220901.csv/.json` — 主/次级/基线/共识 top-K（K∈{10..1000}）
- `final_ranking_20220901.csv` — 18,519 钱包五维向量 + 各方法排名 + 共识投票 + 支持集标志
- `final_evaluation_20220901.json` — 单次冻结评估 U(K)/U(K)/K/Recall@K + 参考 + 验证
- `PHASE1_SUMMARY.md` — 方案 §4 十五项 Scope 状态表
- `src/build_final.py` — 可复现脚本（CPU only，只读复用冻结产物）
