# EX-Graph 专项基准说明（Group F）

- 生成日期：2026-09-11（本机 cloud82, 10.63.0.82）
- 对象：`vendor/EX-Graph-repo`（上游 Persdre/EX-Graph，commit `298a52564f5d7f8e30f7f8e6919ae1b3168db481`，2024-09-30）
- 网络：外部抓取均经代理 `http://10.63.0.72:7890`
- 证据标签：`[已实测]` `[已读源码]` `[已读论文]` `[沿用notes审计]` `[仅凭论文]` `[未能验证]`

## 1. 官方提供的任务与基线（已读源码核对）

仓库三任务目录与 README/论文声明一致 `[已读源码][已读论文]`：

| 任务 | 目录 | 基线（wo/with X 两套，除 matching 外） |
|---|---|---|
| Ethereum Link Prediction | `ethereum_link_prediction/` | DeepWalk, Node2Vec, GCN, GAT, GATv2, GraphSAGE, TAGCN, ClusterGCN, DAGNN, APPNP, GGNN（22 个脚本） |
| Wash-trading Detection | `wash_trading_addresses_detection/` | 同上 11 模型（20 个脚本） |
| Matching Link Prediction | `matching_link_prediction/` | DeepWalk, Node2Vec, GCN, GAT, GATv2, GraphSAGE, TAGCN, ClusterGCN, DAGNN, APPNP, GGNN, R-GCN, HIN2Vec（共 13 个模型） |

**已实测确认的事实（重要）：**
1. `ethereum_link_prediction/` 与 `matching_link_prediction/` 的 6 个 split pkl **md5 完全相同**（如 positive_train 均为 `e79deceb0b89c421723dd670b08be7e8`、negative_test 均 `1fb0dfa1a9543549f6635e8af2f5cb17`）；且 matching split 的所有节点 id 都在 [0, 1,709,574]（ETH 块内），**不含任何 ETH↔X 跨域对**。→ 官方发布的"matching link prediction"split 文件实际上是 Ethereum LP 的 split 文件，**无法按发布文件复现论文表 7** `[已实测]`
2. Ethereum LP split pkl 规模（已加载）：pos/neg train 各 842,821 对；val 各 111,582；test 各 201,780 `[已实测]`
3. `ethereum_with_twitter_features.pkl`（LP 图，37.3GB）本机已加载审计：DGL 同构图，1,709,575 节点 / 13,170,869 边，ndata 含 ethereum_features(8-d)、combined/twitter features 等 24 个字段；**edata 为空**（README 声明边含 from/to/weight/block_number，但发布 DGL 图内无 edata）`[已实测]`
4. 脚本环境需求：dgl==1.1.0、torch==2.0.0+cu117、torch-geometric 2.3.0 等（environment.yml）。本机 `exgraph-x` conda env 已有 dgl 1.1.0+torch 2.0.1+cpu，但缺 sklearn/torchmetrics/pandas `[已实测]`

## 2. 官方 split（论文协议）

- **Ethereum LP**：论文按**边时间戳** 70/10/20 切分，去掉 val/test 边后取训练最大连通子图；确保 val/test 边两端都在训练图中；负边=同一地址出发的非存在边。发布 split pkl 即官方固定切分 `[已读论文][已实测]`
- **Wash-trading**：整图按边时间戳 70/10/20 切为 train/val/test 三个图，训练取最大连通子图；正例=全部 wash-trading 地址，负例=等量随机正常地址（平衡采样）；5 次重复 `[已读论文]`
- **Matching**：论文为**随机** 70/10/20 切匹配边（匹配边无时间戳）；发布文件与论文协议不符（见上）`[已读论文][已实测]`

## 3. Leaderboard 现状（2026-09-11 经代理实查）

- README/论文声明 leaderboard 网址 `https://exgraph.deno.dev/`（README）与 `https://exgraph.deno.dev`（论文）
- 2026-09-11 经代理 `http://10.63.0.72:7890` 实测：`/`、`/leaderboard`、`/api/leaderboard`、`/api/results`、`/api/upload`、`/results`、`/about`、`/dataset`、`/index.html`、`/home`、`/upload` 全部返回 **HTTP 404**（server: deno/gcp-us-west4）`[已实测]`
- 结论：**官方 leaderboard 当前不可访问（404）**。任何"当前 EX-Graph SOTA"只能引用论文自报值（2023-10/ICLR2024），**不能宣称击败了当前 leaderboard**。**未能验证**是否有更新的 SOTA 条目 `[未能验证]`
- GitHub 端：仓库 22 stars/2 forks，open issue #3 即为"LP 图缺地址映射 / wash 图无法映射 / X 图无节点特征"的社区澄清请求，进一步佐证跨文件映射问题是已知缺陷 `[已实测]`

## 4. 与我们数据的兼容性（重点）

我们的数据契约：27,613 个 EX-Graph 映射地址（`twitter_matching.csv` 去重）+ BigQuery 时间物化（native/token/internal，2022-03-01~2022-09-01，约 11.63M 行）+ 2022-09/10 holdout。

| 维度 | 官方发布（LP/大图） | 我们的数据 | 兼容性判断 |
|---|---|---|---|
| 节点数 | 大图 `ethereum_graph.gpickle` 本机实测 1,810,641；LP 图 1,709,575 | 27,613 目标（含在 1,810,641 内） | 目标集合 ⊂ 大图，但 LP 图命名空间**未验证**对齐 |
| 边数 | 大图实测 11,876,618（README 声称 2,610,465 节点/29,585,858 边，**与实测不符**）；LP 图 13,170,869 | 11.63M 时间事件（native+token+internal） | 大图是聚合图（DiGraph 无双平行边），非逐笔事件流 |
| block_number | 大图/README 声明有 `block_number`，**但发布 gpickle 内 0 条边带该字段**（11876618 条全部缺失）`[已实测]` | 我们保留 block_timestamp/block_number/transaction_index | 官方聚合图无时间戳→不能做时间切分复现（只能用它做静态特征） |
| 时间 | 无（聚合静态） | 2022-03~09 逐事件 | 官方 LP split 是按时间切的，但发布物**不含时间**，只能按官方 pkl 用 |
| 地址字符串 | LP 图无地址字符串；大图有（node 属性） | 有地址 ↔ exgraph_node_id | 27,613 目标↔大图 id 有映射；↔LP 图 id 需解决（未发布） |
| 特征 | LP 图含 8-d 结构 + 770-d X + 24-d combined | 我们用 BigQuery as-of 特征 + X 静态特征 | 可对齐做图级外部验证；钱包级需先解决命名空间 |

**结论：**
1. 我们的 27,613 目标是 `ethereum_graph.gpickle`（大图）的节点 id 空间；LP 图（`ethereum_with_twitter_features.pkl`）是另一套 0..1,709,574 编号，且**发布物不含地址字符串**、社区已报告该缺口（issue #3）。本地 v1 紧凑抽取尝试以 `twitter_matching.csv` 的 id 直接索引 LP 图特征，仅"数值在范围内"（27,477/27,613），且结构特征对齐仅部分精确（total_degree 精确 5,725/27,477 等）→ **不能把 27,613 钱包的"身份"干净映射进官方 LP 基准** `[已实测]`
2. 因此 EX-Graph LP 只能作为**图级外部验证**（我们的表示方法在该官方图+官方 split 上跑，和论文基线比 AUC/F1），不能宣称"我们在 EX-Graph 上评估了我们的 27,613 钱包"。
3. 若想钱包级接入，需先取得作者提供的地址↔LP-node 映射（issue #3 的诉求）或从大图地址重建 LP 子图并**验证 id 对齐**；在此之前只能做图级。

## 5. 复现成本与算力（实测推算）

- 数据已在本地：LP 图 37.3GB（`/storage/gaoym/ethereum_with_twitter_features.pkl`）、大图 11.6GB、matching 图 444MB；**wash train/val/test 图未下载**（约 4.46+1.46+?GiB）`[已实测][沿用notes审计]`
- 环境：官方要求 dgl 1.1.0 + torch 2.0.0+cu117 + torch-geometric 2.3.0。本机 `exgraph-x` 有 dgl 1.1.0 + torch 2.0.1+cpu（缺 sklearn/torchmetrics/pandas）；`.venv-cuda`（torch 2.14+cu126）无 dgl 且与 dgl 1.1.0 不兼容 → 需：(a) 给 exgraph-x 补 sklearn/torchmetrics/pandas，或 (b) 用 PyG 移植 11 个基线（推荐，PyG 兼容 torch 2.14）
- 算力：本机 GPU5（RTX4090，23GB，空闲）可用；503GB RAM 充足。全图 1.7M 节点 / 13.17M 边、hidden 128、200 epoch、early stopping、5 重复：每模型每配置约 1-数小时（GPU），全 22 个脚本（11 模型×wo/with）估计 1-3 GPU-天；CPU 会慢一个量级 `[已实测机器资源]`
- 建议最小闭环：先复现 4-5 个关键基线（GCN/GAT/GraphSAGE/DAGNN/APPNP）wo/with X，对照论文表 5（APPNP with-X AUC 0.89 为参照），确认环境与协议正确后再扩展到全 11 模型

## 6. 建议

1. **EX-Graph LP**：接入为"外部标准图验证"（图级），用官方 split pkl + 官方脚本/PyG 移植，对照论文表 5。
2. **EX-Graph Matching**：先不要碰（发布 split 有缺陷）；若作者补发正确 matching split 再考虑。
3. **EX-Graph Wash-trading**：仅当需要"加 X 特征的洗盘检测"图级验证时再下载 ~7+GiB；注意脚本文件名与 README 数据名不一致（`G_train_dgl_twitter_updated.gpickle` 等）需对齐。
4. **leaderboard**：提交前必须再查 `exgraph.deno.dev` 是否恢复；不可访问时只引用论文自报值并注明日期。
