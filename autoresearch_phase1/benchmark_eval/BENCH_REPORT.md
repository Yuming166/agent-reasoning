# BENCH 报告：标准基准评估组（Phase-I §6）

- 生成日期：2026-09-11（本机 cloud82, 10.63.0.82）
- 工作目录：`/storage/gaoym/ex-graph-microtransaction-analysis`
- 冻结协议：`research/audit/temporal_protocol.yaml` v1.0 + `research/audit/DATA_AUDIT.md`（已读；本组仅做**外部验证**，不改协议/不动其他组文件）
- 职责边界：基准评估是外部验证，不是钱包重要性定义；不宣称 SOTA；只报告实测数字并与官方基线/论文自报值对比（差异如实说明）

## 0. 完成状态总览

| 项 | 状态 | 结果（已实测） |
|---|---|---|
| A1. EX-Graph LP 官方快照核实（路径/大小/hash/split） | ✅ 完成 | pkl 37,329,036,840 B；1,709,575 节点 / 13,170,869 边；sha256 与记录一致 |
| A2. EX-Graph LP 官方协议启发式基线（CN/AA/RA/Jaccard/PA，官方 split pkl） | ✅ 完成 | test AUC 0.634-0.775（见 §1.4） |
| A3. 27,613 钱包无法干净映射进 LP 图（图级验证边界） | ✅ 明确 | 见 §1.5 |
| B1. TGB tgbl-coin-v2 下载（代理 HEAD 验证 + 下载） | ✅ 完成 | 1,284,466,067 B，HTTP 200 |
| B2. `py-tgb` 2.3.0 安装（唯一新装包；无 torch_geometric） | ✅ 完成 | 仅新增 args/clint/py-tgb |
| B3. EdgeBank 官方启发式（unlimited / fixed_time_window） | ✅ 完成 | test MRR 0.3590 / 0.5796（见 §2.2） |
| B4. torch-only MLP 边打分基线（官方 split/evaluator/负采样） | ✅ 完成 | test MRR 0.7841（见 §2.3） |
| B5. TGB 活榜单复核 | ✅ 完成 | 2026-09-11 实测：TPNet 0.832±0.001 榜首；Heuristic 0.774 |

未完成项：EX-Graph 官方 GNN 基线（GCN/GAT/APPNP 等 11 模型）与 TGB 的 TGN/DyGFormer 级模型——需 dgl/PyG 重依赖，超出"最小可验证执行"边界（见 §3）。

## 1. A. EX-Graph Ethereum Link Prediction（图级外部验证）

### 1.1 官方快照核实（证据）
- LP 图 pkl：`/storage/gaoym/ethereum_with_twitter_features.pkl`
  - 大小 `37,329,036,840` B（34.765 GiB）—— 与 Group F 报告一致（实测 `stat`）
  - sha256 `074bc973e025e85fd57106cd4ef7f83d5432ce5f8ef1c64690c2bbfd587b42cd` —— 本次重算与 `notes/ethereum-with-twitter-features-local-extraction.md` 记录一致（实测）
  - 加载（.venv-35gb，dgl 2.1.0）：`1,709,575` 节点 / `13,170,869` 边（实测，53.6s）；与 README 声称一致
  - 边数组抽取到 `data/exgraph_lp_edges.npz`（43,030,163 B）；去重后唯一边 `13,153,096`（存在 17,773 条平行边）
- 官方 split pkl（vendor/EX-Graph-repo/ethereum_link_prediction/，实测加载）：
  - positive/negative train `(2, 842,821)`；val `(2, 111,582)`；test `(2, 201,780)`，int64
- 官方代码/论文：11 个模型脚本（DeepWalk/Node2Vec/GCN/GAT/GATv2/GraphSAGE/TAGCN/ClusterGCN/DAGNN/APPNP/GGNN × wo/with）；论文 Table 5 自报 AUC（本次从 LaTeX 源 `data/metadata/paper/src/sec-statistics-experiments.tex` 提取，见 `paper_table5_auc.json`）
- 论文协议（已读论文/README）：按边时间戳 70/10/20 切分，去掉 val/test 边后取训练最大连通子图；负边=同一地址出发的非存在边；5 次重复

### 1.2 训练拓扑与非泄漏
- 官方发布图 = 训练子图（val/test 正边已删除）——证据（本次实测 audit）：
  - positive_train 100% 在图内（842,821/842,821）
  - positive_val 仅 25/111,582、positive_test 仅 53/201,780 以同向边出现在图中
  - 反向（v,u）出现：val 2,280、test 4,223（≈2%，为训练期内相反方向独立交易，非泄漏）
  - 负边与图几乎不重叠：neg_train 1 条、neg_val 0、neg_test 0
- 启发式基线使用"官方图 − 官方 positive val/test 边"作为训练拓扑（13,153,018 边，仅再移除 78 条），与论文"训练子图"语义一致；无未来泄漏
- 注意：官方图 `edata` 为空（README 声称边含 from/to/weight/block_number，发布物不含），与 Group F `exgraph_benchmark_note.md` 一致 → 无法做按时间戳的自切分复现，只能用官方 pkl

### 1.3 基线选择说明
- 目标"最小可验证执行"：优先启发式（官方 split pkl + 官方图拓扑），不装 dgl/PyG 重依赖（.venv-cuda 无 dgl；exgraph-x 为 CPU 且缺 sklearn；全图 GNN 训练超出本次最小闭环）。Node2Vec 在 1.7M 节点上需数十亿步游走，未列入
- 方向敏感性：另跑有向（out-neighbor）CN 对照

### 1.4 结果（已实测，官方 split，AUC-ROC / AP）
| 方法 | val AUC | val AP | test AUC | test AP | test 支持率(score>0) |
|---|---:|---:|---:|---:|---:|
| Common Neighbors（无向） | 0.6581 | 0.6534 | 0.6354 | 0.6306 | 0.175 |
| Adamic-Adar（无向） | 0.6586 | 0.6590 | 0.6358 | 0.6358 | 0.175 |
| Resource Allocation（无向） | 0.6583 | 0.6578 | 0.6356 | 0.6348 | 0.175 |
| Jaccard（无向） | 0.6567 | 0.6442 | 0.6344 | 0.6241 | 0.175 |
| Preferential Attachment | 0.8037 | 0.8005 | 0.7754 | 0.7622 | 1.000 |
| CN（有向 out-neighbor，敏感性） | 0.5801 | 0.5773 | 0.5695 | 0.5666 | 0.084 |

- 论文表 5 自报 AUC 参照（wo-X / with-X）：DeepWalk 0.72/0.74；Node2Vec 0.72/0.74；GCN 0.76/0.81；GAT 0.77/0.81；GATv2 0.77/0.79；GraphSAGE 0.84/0.86；TAGCN 0.81/0.88；ClusterGCN 0.82/0.86；DAGNN 0.79/0.87；APPNP 0.82/0.89；GGNN 0.82/0.84（均为论文自报，非本次实测）
- 解读（如实）：启发式基线 test AUC 0.63-0.78，低于论文 GNN 自报的 with-X 0.84-0.89，与 wo-X GNN 0.72-0.84 部分接近（PA 0.7754 高于 DeepWalk/Node2Vec 0.72、接近 GCN 0.76）；CN 类仅 17.5% 测试对可算分（图稀疏）。**不是 SOTA/优越性声明**，仅作为官方协议下可复现的图级参考

### 1.5 27,613 钱包 ↔ LP 图映射边界（明确声明）
- 27,613 目标是 `ethereum_graph.gpickle`（大图）节点 id 空间；LP 图是另一套 0..1,709,574 编号
- LP 图发布物不含地址字符串，`twitter_matching.csv` 中 27,477/27,613 的 id 数值落在范围内，但命名空间未验证（仅 5,725/27,477 结构特征精确匹配）——Group F `exgraph_benchmark_note.md` 已实测，社区 issue #3 亦报告该缺口
- 因此 EX-Graph LP 只能做**图级外部验证**（官方图 + 官方 split），不能宣称"在 EX-Graph 上评估了我们的 27,613 钱包"
- 本组不依赖也不改动 Group A 的映射产物

## 2. B. TGB tgbl-coin-v2（外部活榜单，尽力而为）

### 2.1 下载与安装（证据）
- HEAD 验证：`https://object-arbutus.cloud.computecanada.ca/tgb/tgbl-coin-v2.zip` → HTTP 200, Content-Length `1,284,466,067`（代理 `http://10.63.0.72:7890`）
- 下载（实测）：`data/tgbl-coin-v2.zip` = `1,284,466,067` B，sha256 `64887fa5548cea21d57a5d6e7d4acba28673ccf9017f8db30156d9dad5a1e100`；耗时 69.7s（≈17.5 MB/s）；zip 内含 `tgbl-coin_edgelist_v2.csv`（2.46GB）、val/test 负样本 pkl（818/820MB）
- 安装（唯一允许新装包）：`.venv-cuda` 内 `pip install py-tgb` → `py-tgb 2.3.0`（新增 `args`、`clint` 两个小包；**未安装 torch_geometric**；PyPI 的 `tgb` 1.2.0 是无关的 Telegram 包，未使用）
- 数据放置：`<site-packages>/tgb/datasets/tgbl_coin/`（官方 loader 自动识别 v2 文件名，跳过重复下载）
- 官方协议：时间切分（train 70% / val 15% / test 15%），streaming 评测（test 只更新 memory，不反向传播）；官方 evaluator（MRR，one-vs-many）+ 官方负采样（hist_rnd，每正边 ~20 负）
- 榜单复核（2026-09-11 经代理实测 `tgb.complexdatalab.com/docs/leader_linkprop/`）：TGbl-coin-v2 榜首 TPNet 0.832±0.001；Heuristic(LocalRecencyLocalPopularity) 0.774；HyperEvent 0.773±0.002；TNCN 0.762±0.004；DyGFormer 0.752±0.004；CTAN 0.748±0.004；TGN 0.586±0.037

### 2.2 EdgeBank（官方启发式基线，numpy-only，移植官方 `examples/linkproppred/tgbl-coin/edgebank.py`，去掉未使用的 torch_geometric import）
- 协议：memory 初始化为 train 边；val 评估（streaming 更新）；test 评估（memory 继续含 val）；官方负采样 + 官方 MRR；BATCH=200；seed=1
- 结果（已实测）：

| 模式 | val MRR | test MRR |
|---|---:|---:|
| EdgeBank unlimited | 0.3154 | 0.3590 |
| EdgeBank fixed_time_window (ratio=0.15) | 0.4915 | 0.5796 |

- 对比：榜单 `Heuristic(LocalRecencyLocalPopularity)` 0.774 是 TGB 2.0 更强的连续打分启发式（未随开源仓库发布实现），不是二值记忆 EdgeBank；EdgeBank 二值记忆 recall 受限于"测试正边是否曾在 train/已见历史中重复"（实测 train 唯一对 2,983,977；val 正边对中 50.4%、test 中 42.3% 曾在 train 出现）→ 本数字低于 0.774 属预期且如实报告

### 2.3 torch-only MLP 边打分基线（自实现，无 torch_geometric）
- 特征（leak-free streaming，全部来自 timestamp < t 的已观测历史）：pair_count_prev、pair_last_gap、has_pair、src_total_prev、src_last_gap、dst_total_prev、dst_last_gap（7 维，log1p/标准化）
- 训练：train split 按时间序流式构建特征（严格过去信息）；随机采样 2M 正边 + 每正边 1 个均匀随机负 dst（特征从同一 streaming state 真实计算；eval 负样本为官方 hist_rnd）；2 层 MLP（hidden 256，dropout 0.1），8 epochs，Adam lr=1e-3，BCE；GPU6（RTX4090）
- 评测：官方 val/test 负采样 + 官方 MRR；memory 初始化为 train（test 再预载 val），streaming 更新；无反向传播
- 结果（已实测，seed=1）：

| split | MRR | 训练子集 | 总耗时 |
|---|---:|---|---:|
| val | 0.7611 | 2M 正边 | 1,051 s |
| test | 0.7841 | 2M 正边 | 1,097 s |

- 对比榜单（2026-09-11 实测）：test MRR 0.7841 高于 Heuristic 0.774、HyperEvent 0.773、DyGFormer 0.752、CTAN 0.748、TGN 0.586；低于 TPNet 0.832±0.001。**报告为"简单 MLP 基线在官方协议下的实测值"，不构成 SOTA/优越性声明**；方法本质是学习式的 recency/popularity 打分，榜单方法含更强的时序表示
- 可复现性：模型权重 `tgb_mlp_test.pt`/`tgb_mlp_val.pt` + 标准化参数 `tgb_mlp_train_scaler.npz` 已存

### 2.4 数据/协议边界
- tgbl-coin-v2 是全 Ethereum 地址（638,486 节点）ERC-20 稳定币转账时间图（2022-04-01~2022-11-01），与我们的 2022 窗口重叠，但不是"仅 27,613 目标钱包"的评测；官方已聚合，无法在官方 zip 上取子集 → 仅作图级/全图外部验证
- 数据许可 CC BY-NC：可作研究评测；不得并入对外发布的数据包

## 3. 未完成项与限制
1. EX-Graph 官方 11 模型 GNN 基线（GCN/GAT/GraphSAGE/DAGNN/APPNP 等）：需 dgl 1.1.0 + torch-geometric 环境（exgraph-x 为 CPU 且缺 sklearn；.venv-cuda 无 dgl；本组不装重依赖）→ 未跑；论文表 5 数字仅为参照，非本组实测
2. TGB TGN/DyGFormer 级模型：需 PyG/更大算力，超出最小闭环 → 未跑
3. EX-Graph leaderboard（exgraph.deno.dev）当前 404，无法提交/对比活榜单（Group F 已实测；本组沿用）
4. `Heuristic(LocalRecencyLocalPopularity)` 0.774 的确切实现未在开源仓库 → 未复现，仅引用榜单值
5. （已消除）EdgeBank fixed_time_window 结果已写入

## 4. 产出文件清单（research/benchmark_eval/）
| 文件 | 内容 |
|---|---|
| `BENCH_REPORT.md` | 本报告 |
| `exgraph_lp_heuristics_results.json` | EX-Graph 启发式 AUC/AP/支持率 + split-vs-graph audit |
| `exgraph_lp_cn_directed_{val,test}.json` | 有向 CN 敏感性 |
| `paper_table5_auc.json` | 论文表 5 AUC 自报值（从 LaTeX 提取） |
| `extract_exgraph_lp_edges.py` / `data/exgraph_lp_edges.npz` | LP 图边抽取脚本/产物 |
| `data/exgraph_lp_pkl_sha256.txt` | LP 图 pkl sha256（本次重算） |
| `exgraph_lp_heuristics.py` / `exgraph_lp_cn_directed_sensitivity.py` | 评分脚本 |
| `data/tgbl-coin-v2.zip`（1.28GB，sha256 已记） | TGB 数据集压缩包 |
| `tgb_edgebank.py` / `tgb_edgebank_predictor_official.py` / `tgb_edgebank_{unlimited,fixed_time_window}_results.json` | EdgeBank 基线 |
| `tgb_mlp.py` / `tgb_mlp_{val,test}_results.json` / `tgb_mlp_{val,test}.pt` / `tgb_mlp_train_scaler.npz` | MLP 基线 |
| （外部数据副本）`<site-packages>/tgb/datasets/tgbl_coin/*` | TGB 解压数据（csv + ns pkl） |

## 5. 证据纪律
- 所有数字标注来源（本次实测 / 论文自报 / 榜单引用 / 未能验证）
- 命令与耗时：见各脚本输出与上表；下载/流量：1.28GB zip（HEAD 验证后一次下载，无重复传输）
- 未改动其他组文件；全部产出写入 research/benchmark_eval/
