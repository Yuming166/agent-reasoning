# 工作日记：链上重要钱包筛选与预算化路由（2026-09-08 ~ 2026-09-09）

项目目录：`/storage/gaoym/ex-graph-microtransaction-analysis`
云端：`ictdata-507912.exgraph`（BigQuery，US）；GCS bucket `ictdata-exgraph-artifacts`。
分支：`codex/wallet-selection-router`（独立分支，不改动 main）。

## 2026-09-08（晚）

1. X 社交数据审计复核：实测确认 `twitter_matching.csv` 只有 eth node_id+地址
   （8,820 个 id 超出 X 图 1,103,509 节点）；matching 图的 212 万跨边全为双向
   候选池，正负样本不可分离；X 侧 16 维特征后 8 维在 112 万节点上唯一值=1。
   结论：已发布小文件不含 eth<->x crosswalk。
2. X 关注图独立结构统计：1,103,509 节点/3,768,281 有向边，互关 102,088，
   2 个弱连通分量；产物 `artifacts/x_graph_standalone_stats.json`，
   每节点度数 npz（不入仓库）。
3. 确认 34.8 GiB `ethereum_with_twitter_features.pkl` 含 8 维 eth + 16 维 X
   聚合特征（代码 GCN(8) vs GCN(24) 实锤），但无 X node id；制定
   GCP 内网下载-抽取-落表-销毁 VM 的零跳板机流量方案与脚本
   (`src/cloud/extract_exgraph_xfeatures_gcp.py`)，起草给作者的索要邮件
   (`notes/author-request-draft.md`)。

## 2026-09-08（深夜）~ 2026-09-09：创新筛选支柱实现

- **P3 难度加权后果**：月度 as-of 特征表 `wallet_asof_features_v1`
  （5–8 月 4 快照，事件量/对手方熵/新对手方率/互惠率/HHI 等 + fwd30 标签，
  严格过去 90 天特征、未来 30 天标签）；排名表
  `wallet_importance_ranking_v1`。8 月 1% 预算覆盖 22.7% 难事件，
  优于按交易量 14.6% 与随机 1.3%。
- **P2 时序触发代理**：6 月窗口小时级 lag-1 活动相关，`wallet_trigger_proxy_v1`
  （2,038/14,189 钱包有有效分，均值 .051）；小时网格对低活跃钱包过稀疏，v2 改天级。
- **P1 反事实遮挡（信息桥）**：`p1_bridge_events_v1`（516k 桥，24.0% 的 8 月
  转出事件存在二跳解释路径）、`p1_wallet_icf_v1`。1% 预算覆盖 47.9% 桥接信息事件；
  P1 与 P3 top-1% 集合仅重合 14/144，两个重要性轴互补。
- **P4 学习型 router v1**：6 月训练、7 月调参、8 月冻结（HistGBM），
  `router_dataset_v1`（59,137 行 × 28 as-of 特征）。冻结 8 月：10% 预算捕获
  55.1% 未来 headroom（交易量 53.7%），选择效率达 oracle 的 .823，
  Spearman=.746；最强 as-of 特征为近 30 天新对手方数。单标量目标下 P1/P2
  增益小 → v2 需多目标/预算条件混合路由。

## 2026-09-09：候选评分模型 v1（next-counterparty 闭环）

- 表：`nc_events_v1`（事件级 repeat/new 标注）、`nc_edges_hist_v1`（1.16M 边）、
  `nc_global_pop_v1`、`nc_bridge_cand_v1`（64.6M 二跳非邻居候选）、
  `nc_bridge_hits_v1`、`nc_bridge_poolsize_v1`。
- 8 月 457,128 转出事件：重复 62.4%/新 37.6%。
- 结果（artifacts/nc_v1/RESULTS.md）：历史已知重复对手方上个性化时间衰减
  MRR .374 / R@10 .734；新对手方全局非邻居热度 MRR 仅 .024；二跳桥只覆盖
  5.9% 真相、固定拼接反而有害，但子池上 oracle 二选一比单纯全局 +25% MRR
  → 学习型候选排序器/逐事件评分门控是下一步。组合基线全事件 MRR .185。
- 过程中修正两个方法论问题：(i) target_sequence_index 按钱包编号，二跳排名
  必须按 (u,seq) 分区；(ii) 窗口函数与真值过滤不能放同一 CTE。

## 边界（不夸大）

- P1 v1 是图路径遮挡代理，非"训模型后真实 mask 重打分"（v2）。
- P4 v1 目标是流行度 headroom 代理，不是真实 LLM ΔMRR/token。
- 全部结论未使用 X 特征；等待 GCP 抽取后做 P6 社交消融。
- router 生产口径只能用 5/6 月训练、8 月冻结；展示性同周期排名已标注 oracle 属性。
