# Benchmark / SOTA Registry — Group F（Ethereum 动态钱包重要性 Phase I）

- 生成日期：2026-09-11（本机 cloud82，10.63.0.82）
- 依据：`research/autoresearch_phase1.md` §Group F / §6 / §7；网络抓取全部经代理 `http://10.63.0.72:7890`
- 证据状态标签（铁律）：`[已实测]`=本会话实测（本地文件/源码/API/网页）；`[已读源码]`=直接读过官方源码；`[已读论文]`=直接读过论文正文；`[沿用notes审计]`=复用本项目 notes/ 已有审计；`[仅凭论文/描述]`=仅按论文或公开描述，未独立验证；`[未能验证]`=无法验证
- 类型标记：`A=真正公共基准`（固定协议+公开 split/leaderboard，可比 SOTA）；`B=论文自定义评测`（随论文发布的评测，无公开 leaderboard）；`C=数据集/标签资源`（数据或标签，不是完整基准）

## 0. 核心结论（先看这里）

**本项目能做出可信 SOTA/基准声明的地方（按可信度排序）：**

1. **TGB `tgbl-coin-v2` / `tgbn-token`（Ethereum ERC-20 稳定币/用户-代币时间图）** —— 唯一"当前仍在运行的公开 leaderboard + 公开固定 split + 官方评测器"的 Ethereum 时间图基准；`tgbl-coin` 时间窗 2022-04-01~2022-11-01 与本项目 2022 窗口高度重叠。leaderboard 2026-09-11 实测可访问，当前榜首 tgbl-coin MRR 0.832（TPNet）。**这是最有把握的外部 SOTA 通道。**
2. **EX-Graph Ethereum Link Prediction（官方 70/10/20 时间切分 + 11 个官方基线）** —— 公开数据与 split 完整（LP 图已在本机 37.3GB pkl），可复现论文表 5（最好 APPNP AUC 0.89 with-X）。但官方 leaderboard 网站 `exgraph.deno.dev` 2026-09-11 实测 404，**当前 SOTA 只能引用论文自报值，不能宣称"击败当前 leaderboard"**；且我们的 27,613 钱包无法干净映射进 LP 图（见 exgraph_benchmark_note.md），只能做图级外部验证。
3. **账户分类/标签外部验证（§7）** —— Forta / eth-labels / Etherscan 类标签做"行为表示→外部标签"验证是可信的**有效性声明**（不是 SOTA 声明）；注意标签来自不同源、非官方 benchmark，只能做验证集，不能做"击败 SOTA"声明。
4. **预算化钱包选择（§8/§9 新任务）** —— 无任何标准公共基准，必须自建协议 + 强基线（random/degree/PageRank/k-core/volume/learned router/oracle）。可做"可复现新基准"，但**不能声称 SOTA**，只能声称"新任务上的方法比较"。

**不能做 SOTA 声明的地方：** wash-trading（无稳定公共基准；Kaggle 候选为合成/特征表数据，EX-Graph wash 图未本地验证）、X/Ethereum matching（EX-Graph 官方 matching split 文件与 LP split 完全同文件，无法复现论文表 7，见后）、行为聚类（无标准基准）。

---

## 1. EX-Graph Ethereum Link Prediction

- benchmark_name: EX-Graph Ethereum Link Prediction（官方协议）
- paper: Wang, Zhang, Liu, Lu, Luo, He, "EX-Graph: A Pioneering Dataset Bridging Ethereum and X"
- year: 2024（ICLR 2024；arXiv:2310.01015v3，2023-10 首发）
- venue: ICLR 2024（arXiv cs.SI）
- dataset: `ethereum_with_twitter_features.pkl`（DGL 同构图，官方 README 1,709,575 节点 / 13,170,869 边；本机实测一致 `[已实测]`）；边特征含 from/to/weight/block_number 声明（README），但 DGL 图内 edata 实测为空 `[已实测]`；另有 `ethereum_graph.gpickle` 大图（本机实测 1,810,641 节点 / 11,876,618 边，无 block_number 字段，weight=聚合频次）`[已实测]`
- task: 边链接预测（在 ETH 图上预测未来出现的交易边；负采样=同一地址的非存在边）
- official_split: 官方 pkl 提供 train/validation/test 边索引：正边 train 842,821 / val 111,582 / test 201,780（负边同量）；论文为按边时间戳 70/10/20 切分并取训练最大连通子图 `[已读论文][已实测 pkl]`
- metrics: AUC-ROC、Precision、Recall、F1（5 次重复平均±std）`[已读论文]`
- current_SOTA: 论文自报最好 with-X = APPNP AUC 0.89±0.02（其次 TAGCN 0.88、DAGNN 0.87）；wo-X 最好 = GraphSAGE AUC 0.84。**leaderboard 网站 2026-09-11 实测 404，未验证是否有更新的 SOTA 条目** `[已读论文][未能验证]`
- public_code: `github.com/Persdre/EX-Graph`（ethereum_link_prediction/ 下 22 个脚本 wo/with X），commit 298a525（2024-09-30）`[已实测]`
- public_leaderboard: 声明于 README/论文（exgraph.deno.dev），2026-09-11 全路径 404，**未能验证** `[未能验证]`
- data_access: Google Drive（README 链接）；LP 图已在本机 `/storage/gaoym/ethereum_with_twitter_features.pkl`（37.3GB，sha256 074bc973…已记录）`[已实测]`
- compatibility_with_our_data: **低-中**。LP 图无地址字符串（GitHub issue #3 证实社区同样发现），节点 id 命名空间与 `twitter_matching.csv` 的 27,613 映射**不能干净对齐**（v1 manifest：in-range 27,477 / 136 out-of-range；结构特征对齐仅部分精确）`[已实测]`。我们的 27,613 目标 ↔ 大图 id，不能直接映射进 LP 图参与官方 split
- leakage_risk: 中。官方协议本身按时间切分（防未来泄漏）；但 LP 图无时间戳（无 block_number/时间），第三方若自建 split 极易混入未来边；**必须使用官方 split pkl**。X 特征在官图内已含（BERT 770-d 聚合），本身是"全历史"静态特征
- reproduction_cost: 高。需 dgl 1.1.0 + torch 2.0.x（本机 exgraph-x 环境已有 torch2.0.1+cpu/dgl1.1.0，缺 sklearn/torchmetrics/pandas）；全图 1.7M 节点×200 epoch×22 个脚本（11 模型×wo/with）×5 重复；本机 GPU5（RTX4090 空闲，23GB）可用，503GB RAM 充足；预计单模型单配置数小时，全基线 1~3 GPU-天（CPU 会慢一个量级）
- novelty_potential: 中。数据集本身已发表，任务已被 11 个基线覆盖；新意只能来自"我们的表示方法在其上超过 APPNP/TAGCN/DAGNN 等"或"用我们的钱包级方法在该图上做新的子任务"
- NAACL_fit: 中。可作为外部验证（证明表示方法在标准 ETH 图上有效），但不是 NAACL 语言任务本身；对 NAACL 更相关的是"用 LLM 生成的语义表示在该图上的 AUC/F1 是否超过纯图方法"（§Group E 输出）
- 类型: A（有公开数据+固定 split+官方基线+声称的 leaderboard，但 leaderboard 当前不可访问）

## 2. EX-Graph Wash-Trading Address Detection

- benchmark_name: EX-Graph Wash-Trading Addresses Detection
- paper: 同上 EX-Graph
- year / venue: 2024 / ICLR 2024
- dataset: 官方发布 train/val/test 三个"检测图"（README：1,268,607/452,930/711,084 节点，8,276,446/1,182,349/2,364,700 边，节点含 wash_trading_label 与 4 组特征）`[已读源码][已读论文]`；标签来自 Dune 下载的 1,445 个 wash-trading 地址（其中仅 3 个有 X 匹配）`[已读论文]`
- task: 二分类（wash-trading 地址 vs 正常地址）；论文用平衡采样（全正例+等量负例）
- official_split: 官方按边时间戳 70/10/20 切分为三个独立图（train/val/test 图）；保持最大连通子图 `[已读论文]`
- metrics: AUC-ROC、Precision、Recall、F1（强调 Recall）
- current_SOTA: 论文自报最好 with-X：GATv2/ClusterGCN/DAGNN/APPNP AUC≈0.81，F1≈0.74（GATv2/ClusterGCN/DAGNN/APPNP）；wo-X：GAT/GATv2/TAGCN/ClusterGCN/DAGNN/APPNP AUC≈0.80。**leaderboard 404，未验证更新** `[已读论文][未能验证]`
- public_code: `wash_trading_addresses_detection/*.py`（20 个脚本）`[已读源码]`
- public_leaderboard: 同上 exgraph.deno.dev 404，未能验证
- data_access: Google Drive（3 个 gpickle）。本机**未下载**（此前审计记录 train≈4.46GiB、val≈1.46GiB；test 未记录）`[沿用notes审计]`
- compatibility_with_our_data: 低-中。wash 图同构化、无地址字符串（GitHub issue #3），无法把 1,445 个标签地址映射到我们的 27,613 钱包；只能作为"图级外部验证"或与我们的标签合并做交叉验证（若拿到原始标签地址清单则需向作者确认）
- leakage_risk: 中-高。平衡采样在 train/val/test 各自图内做；正例极少（0.05%），任何"全历史特征"都可能泄漏身份；官方协议按时间切分相对安全，但代码脚本文件名与 README 数据文件名不完全一致（脚本读 `G_train_dgl_twitter_updated.gpickle` 等），复现时需对齐 `[已读源码]`
- reproduction_cost: 高。需下载 ~7+GiB 图 + 同样的 dgl/torch 环境；正例极不平衡，需严格照论文平衡采样协议
- novelty_potential: 中。wash-trading 检测在 NFT/DEX 文献中常见；EX-Graph 的贡献是加 X 特征，新意有限
- NAACL_fit: 低-中。金融异常检测非 NAACL 核心；可作下游验证
- 类型: A/B 之间——有官方固定协议与数据，但无可用 leaderboard，社区使用少 → 按 B（论文自定义评测+官方数据）对待

## 3. EX-Graph X/Ethereum Matching Link Prediction

- benchmark_name: EX-Graph Matching Link Prediction（ETH 地址 ↔ X 账号）
- paper / year / venue: 同上，2024 / ICLR 2024
- dataset: `matching_link_prediction_graph.pkl`（README 2,833,659 节点 / 18,433,366 边，16-d combined features）；本机已下载 444MiB `[已实测]`
- task: 预测 ETH 地址与 X 账号之间的匹配边（论文：正例=30,667 个 OpenSea 验证匹配；负例=非存在边，1:1）
- official_split: **论文**为随机 70/10/20 切匹配边；**发布文件** = `matching_link_prediction/{positive,negative}_{train,validation,test}_edge_indices.pkl`，本机实测 **与 ethereum_link_prediction/ 同名文件 md5 完全相同（e79deceb…）**，且全部节点 id < 1,709,575（ETH 块内），**不含任何 ETH↔X 跨域边** `[已实测]`。即：发布版 matching split 文件实际上是 Ethereum LP 的 split 文件
- metrics: AUC-ROC、Precision、F1、Accuracy
- current_SOTA: 论文自报最好 DAGNN AUC 0.74、APPNP 0.73、GGNN/GCN 0.71（DeepWalk/Node2Vec ≈0.42、HIN2Vec 0.49）`[已读论文]`
- public_code: `matching_link_prediction/*.py`（含 R-GCN、HIN2Vec）`[已读源码]`
- public_leaderboard: 404，未能验证
- data_access: Google Drive（matching 图已本机 444MiB）`[已实测]`
- compatibility_with_our_data: **低**。发布 split 无跨域对，无法按官方文件复现论文表 7；matching 图内跨域边含负采样（此前审计：cross ETH-X 边 2,179,260 有向端，真实 ~27.6k 匹配不可分离）`[沿用notes审计]`
- leakage_risk: 高（若自建 split）。匹配边无时间戳（论文自己用随机切分）；用发布文件会训练在 ETH-ETH 边上，根本不是匹配任务
- reproduction_cost: 高（需先解决 split 缺陷；要么向作者要正确的 matching split，要么从 heterograph 重建）
- novelty_potential: 中-高（若我们拿到正确 crosswalk/匹配数据，做"时间感知的 X↔ETH 匹配"有空间），但当前被发布缺陷卡住
- NAACL_fit: 低-中
- 类型: **发布状态为 B 且有缺陷**（官方自认是 benchmark，但发布 split 与论文协议不一致）→ 建议在论文中标注"官方文件无法复现论文表 7"，避免被审稿人问倒

## 4. TGB tgbl-coin-v2（Ethereum ERC-20 稳定币转账，时间链接预测）

- benchmark_name: TGB tgbl-coin（v2，Temporal Graph Benchmark）
- paper: Huang et al., "Temporal Graph Benchmark for Machine Learning on Temporal Graphs", NeurIPS 2023 D&B（arXiv:2307.01026）；TGB 2.0 于 NeurIPS 2024 D&B 更新
- year / venue: 2023 / NeurIPS 2023 Datasets & Benchmarks（后续 v2 更新）
- dataset: Ethereum ERC-20 稳定币转账（5 稳定币 + 1 wrapped token，来源 Chartalist [37]）；论文统计 638,486 节点 / 22,809,486 边，时间 2022-04-01~2022-11-01（v2 修复了少量边时间乱序）`[已读论文][已实测 leaderboard/下载头]`
- task: 动态链接预测（给定地址与时间，预测下一个交互对象）
- official_split: TGB 固定时间切分（training/validation/test 由包内 evaluator 控制；streaming 评测设置，test 只更新 memory 不做反向传播）`[已读论文]`
- metrics: MRR（test/validation，越高越好）
- current_SOTA: **2026-09-11 实测 leaderboard**（tgb.complexdatalab.com/docs/leader_linkprop/，页面 dateModified 2026-01-22）：1) TPNet 0.832±0.001（2025-08-14）；2) Heuristic(LocalRecencyLocalPopularity) 0.774（2026-01-20）；3) HyperEvent 0.773±0.002；4) TNCN 0.762±0.004；5) DyGFormer 0.752±0.004；6) CTAN 0.748±0.004；7) TGN 0.586±0.037 `[已实测]`
- public_code: github.com/shenyangHuang/TGB（MIT，263 stars，pushed 2026-07-27）；官方 evaluator/negative sampler `[已实测]`
- public_leaderboard: **有，且 2026-09-11 可访问** `[已实测]`
- data_access: tgbl-coin-v2.zip = 1,284,466,067 B（1.28GB），Alliance Canada object store，2026-07-12 更新，HEAD 200 `[已实测]`
- compatibility_with_our_data: **高（时间窗）**：2022-04~11 与我们的 2022-03~09/10 高度重叠；但它是**全 Ethereum 地址**（638k 节点）而非仅我们 27,613 目标；做"仅目标钱包"版本需要从原始事件重建（Chartalist/我们的 BQ 数据），不能直接在官方 zip 上只取子集（官方已聚合）
- leakage_risk: 低-中（官方协议严格时间切分+官方 evaluator；风险在于我们自建子集时引入的聚合/去重错误）
- reproduction_cost: 中。官方包自动下载 1.28GB；TGB 依赖 torch/PyG；本机 .venv-cuda（torch 2.14+cu126）可直接装 `tgb` 包与 PyG；单模型 GPU 数小时级（TGN/DyGFormer 级别）
- novelty_potential: 高（该 leaderboard 持续有 SOTA 更新，且 Ethereum 时间图 + 语言/语义特征表示是相对空白）
- NAACL_fit: 中-高。若把 LLM/语义行为表示接入时间图方法，可写成"语言增强的时间图表示"，NAACL 可接受
- 类型: **A（真正公共基准）**

## 5. TGB tgbn-token（用户-加密货币代币交互，节点属性预测）

- benchmark_name: TGB tgbn-token
- paper / year / venue: 同上 TGB（NeurIPS 2023 D&B）
- dataset: 用户↔代币交易网络（来源 Chartalist），论文统计 61,756 节点 / 72,936,998 边（含权重=转账量，log 归一）`[已读论文]`
- task: 动态节点属性预测——预测用户未来一周与各类代币的交互频率
- official_split: TGB 固定切分（TGB 包内实现）
- metrics: NDCG@10（test/validation）
- current_SOTA: **2026-09-11 实测 leaderboard**：1) NAVIS 0.513（2025-10-20）；2) Moving Average 0.508（TGB 官方基线）；3) Persistent Forecast 0.430；4) TGNv2 0.294 `[已实测]`
- public_code / public_leaderboard / data_access: 同 TGB；tgbn-token.zip = 1,288,612,765 B（1.29GB）`[已实测]`
- compatibility_with_our_data: 中。它衡量"用户对代币类型的交互频率"，与我们的"钱包→对手方/合约"预测方向相关但粒度不同（代币类型 vs 地址）；可做方法迁移验证
- leakage_risk: 低-中（官方协议）
- reproduction_cost: 中（同 TGB；1.29GB 下载 + PyG）
- novelty_potential: 中
- NAACL_fit: 中
- 类型: **A（真正公共基准）**

## 6. Chartalist（ETH 账户型区块链标签图数据集，TGB eth 数据源）

- benchmark_name: Chartalist（Ethereum/account-based 部分）
- paper: Shamsi, Gel, Kantarcioglu, Akcora, "Chartalist: Labeled Graph Datasets for UTXO and Account-Based Blockchains", NeurIPS 2022 D&B
- year / venue: 2022 / NeurIPS 2022 Datasets & Benchmarks
- dataset: 账户型（Ethereum）ERC-20 token 交易网络与标签；TGB 的 tgbl-coin/tgbn-token 均源自此 `[已读论文]`
- task: 提供多任务数据（链接预测、节点属性、标签）；本身不是单一任务基准
- official_split: 不适用（数据源）
- metrics: 不适用
- current_SOTA: 不适用
- public_code: github.com/cakcora/chartalist（MIT，35 stars）`[已实测]`；数据站点 chartalist.org
- public_leaderboard: 无
- data_access: GitHub/站点下载；TGB 已打包其 Ethereum 子集 `[已实测]`
- compatibility_with_our_data: 中（ERC-20 语义；覆盖 2022 窗口）
- leakage_risk: 视使用方式；直接用其标签需审计标签时间/来源
- reproduction_cost: 低-中（TGB 已封装）
- novelty_potential: 低（数据源）
- NAACL_fit: 低
- 类型: C（数据/标签资源）

## 7. Harvard Dataverse ERC-20 Trading 2021 / 2022

- benchmark_name: ERC-20 Trading 2021（DOI:10.7910/DVN/C1AR9V）、ERC-20 Trading 2022（DOI:10.7910/DVN/5P82QC）
- paper: 数据集（Harvard Dataverse，M. Özyilmaz / Akcora 系列）；无单一论文
- year / venue: 2021/2022 数据集；Dataverse
- dataset: 全 ERC-20 转账逐笔表（block_id, transaction_hash, time, token_address, sender, recipient, value, token_name/symbol/decimals），按月压缩 TSV；2022-02~07 六窗口合计约 6.71GB 压缩 `[沿用notes审计][已实测 Dataverse API]`
- task: 无官方任务（自建链接预测/对手方预测/账户分类均可）
- official_split: 无
- metrics: 无官方
- current_SOTA: 无
- public_code: 无官方；社区已有使用
- public_leaderboard: 无
- data_access: 免费下载，CC0-1.0（2021 版实测 license=CC0-1.0）`[已实测]`
- compatibility_with_our_data: **高（ERC-20-only pilot）**：可直接与 27,613 地址 join；限制：无 transaction_index/log_index（同块/同秒顺序需额外审计）、不含 native ETH/NFT/internal trace `[沿用notes审计]`
- leakage_risk: 中（无严格事件排序；自建时间切分必须小心）
- reproduction_cost: 低-中（6.7GB 下载 + 行级解析）
- novelty_potential: 低-中（仅作数据源/基线）
- NAACL_fit: 低
- 类型: C（数据资源，非基准）

## 8. LiveGraphLab（NFT 时间图 + 时间链接预测/节点分类）

- benchmark_name: Live Graph Lab（Zenodo 8267012；代码 livegraphlab/code）
- paper: "Live Graph Lab: Towards Open, Dynamic and Real Transaction Graphs with NFT"（KDD 2023 系列工作；Zenodo 记录 CC BY-4.0）
- year / venue: 2023 / KDD（数据集/代码随论文发布）
- dataset: 全 NFT 交易/事件时间图（~4.5M 节点 / 124M 边，2017-07-12~2022-08-01）；另发布 link-pred 处理图（去 Null 地址后 3.13M 节点 / 23.13M 边）与 node-classify 图（~1.80M 节点 / 21.83M 边）`[已实测 Zenodo API][已读源码 README]`
- task: 时间链接预测（day/week/month 快照，Roland 框架）+ 时间节点分类（标签=日/周/月交易者启发式）+ 连续子图匹配
- official_split: 代码提供 fixed split（train_live_update_fixed_split.py 等），论文自定义切分；**无统一 leaderboard** `[已读源码]`
- metrics: 论文/代码自行定义（链接预测 MRR/AUC；节点分类 F1 等）
- current_SOTA: 无公共 leaderboard（未能验证外部 SOTA）
- public_code: github.com/livegraphlab/code（已本机 vendor/livegraphlab-code）`[已实测]`
- public_leaderboard: 无
- data_access: Zenodo（meta-data.csv.zip 5.84GB；node-classify-data.zip 186MB；link-pred-data.zip 194MB），CC BY-4.0 `[已实测]`
- compatibility_with_our_data: **高（NFT 语义与 EX-Graph 最接近）**：时间窗覆盖 2022-08-01 前，与我们的 2022 窗口重叠；节点分类标签为启发式（最大交易间隔→日/周/月交易者），适合"行为表示 vs 行为标签"外部验证，但**不是真实实体角色标签** `[已读源码]`
- leakage_risk: 中（按快照切分相对安全；但启发式标签本身用全历史计算）
- reproduction_cost: 中（5.84GB metadata 或 194MB link-pred 子集；torch-geometric 2.x/networkx 2.8 环境，与本机 .venv-cuda 版本有差距，需建独立环境或移植）
- novelty_potential: 中
- NAACL_fit: 低-中
- 类型: B（论文自定义评测 + 开放数据/代码，无 leaderboard）

## 9. TGS（Temporal Graph Foundation Models，84 个 ERC-20 token 网络）

- benchmark_name: TGS raw（Zenodo 11480106）
- paper: "Temporal Graph Foundation Models: Toward A Class of General Temporal Graph Learning"（arXiv）
- year / venue: 2024-2025 / arXiv（预印）
- dataset: 84 个选定 ERC-20 token 的逐笔交易网络（blockNumber,timestamp,tokenAddress,from,to,value,fileBlock），raw zip ~602MB，CC BY-4.0 `[沿用notes审计]`
- task: 自建（链接预测/属性预测）
- official_split: 无统一；按文件时间冻结
- metrics: 无官方
- current_SOTA: 无
- public_code: 论文代码（github.com/Graph-Machine-Learning-Group/tgs）
- public_leaderboard: 无
- data_access: Zenodo 免费，CC BY-4.0 `[沿用notes审计]`
- compatibility_with_our_data: 中（可按地址 join），但只有 84 个 token（token-selection bias），**只作开发 pilot，不能外推成完整 Ethereum 效果** `[沿用notes审计]`
- leakage_risk: 中（需自己按文件真实时间戳冻结窗口）
- reproduction_cost: 低（602MB）
- novelty_potential: 低
- NAACL_fit: 低
- 类型: C/B（数据资源+论文评测）

## 10. XBlock（Kaggle Ethereum Partial Transaction Dataset）

- benchmark_name: XBlock / Ethereum Partial Transaction Dataset（Kaggle）
- paper: Kaggle 数据集（XBlock 发布），无正式论文
- year: 最后更新 2020-03-23
- venue: Kaggle
- dataset: 三个以中心账户为条件的局部交易子图（EthereumG1/G2/G3），2015-2016；本机审计：G1 3,832 端点/225,714 边、G2 10,628/222,876、G3 26,175/679,574；与我们的 27,613 目标**仅 G3 有 10 行事件交集** `[已实测，沿用notes审计]`
- task: 局部时间链接预测
- official_split: 无（仅 edge list + addr2Idx）
- metrics: 无官方
- current_SOTA: 无
- public_code: 无
- public_leaderboard: 无
- data_access: Kaggle 下载（41.6MB 压缩），license=Unknown `[已实测]`
- compatibility_with_our_data: **极低**：时间 2015-16 与 2022 不重叠；无 hash/block/index/token；与目标地址几乎无交集 `[已实测]`
- leakage_risk: 不适用（仅可做极小单元测试）
- reproduction_cost: 低（但无价值）
- novelty_potential: 低
- NAACL_fit: 低
- 类型: C（数据资源）→ **不推荐**

## 11. vagifa Ethereum Fraud Detection Dataset（Kaggle，特征表）

- benchmark_name: Ethereum Fraud Detection Dataset（Kaggle vagifa/ethereum-frauddetection-dataset）
- paper: 数据集对应多篇 fraud 检测论文（如 Farrugia 等"Detection of illicit accounts over the Ethereum blockchain"，2018-2020 系列）；Kaggle 本身非正式引用
- year / venue: 2020 前后 / Kaggle
- dataset: 每地址一行特征表（~9.8k 行；列如 avg min between sent/received tnx、time diff、min/max/avg value、FLAG=fraud/valid 等 98 特征）；2.88MB 总大小，ODbL `[已实测 Kaggle API]`
- task: 二分类（fraud vs valid account）
- official_split: 无官方（社区常用随机 8:2）
- metrics: AUC/F1 等（各论文自定）
- current_SOTA: 各论文自报（未见统一 leaderboard）；**未能验证**统一 SOTA
- public_code: 无官方代码；多个复现 notebook
- public_leaderboard: 无
- data_access: Kaggle 下载，ODbL `[已实测]`
- compatibility_with_our_data: **低**：特征是**聚合全历史**（无逐笔时间），无法做时间切分；与我们的 27,613 目标地址的地址级 join 需先比对地址集合（未做）；**存在聚合泄漏**——特征基于全历史，测试期信息已混入
- leakage_risk: **高（无时间维度）**——只能做"地址级、非时间"的弱验证；若用其标签验证我们的表示，必须声明这是静态非时间验证
- reproduction_cost: 低
- novelty_potential: 低（被大量论文使用过）
- NAACL_fit: 低
- 类型: B（论文自定义/社区评测数据集）→ 谨慎使用（仅做静态标签验证）

## 12. sergionefedov Crypto Exchange Fraud & Wash Trading Detection（Kaggle，合成）

- benchmark_name: Crypto Exchange Fraud & Wash Trading Detection（Kaggle sergionefedov/…）
- paper: 无正式论文（Kaggle 数据集）
- year / venue: 2025 前后 / Kaggle
- dataset: 500,000 笔交易、~8,000 钱包、40 代币、~5.9% manipulative；crypto_fraud_master.csv + transactions.csv + wallets.csv + tokens.csv；158MB，CC0-1.0 `[已实测 Kaggle API]`
- task: wash trading / pump-and-dump / ramping 多分类 + 二分类（is_manipulative）
- official_split: 无
- metrics: 数据页自报 RandomForest ROC-AUC≈0.93、PR-AUC≈0.62、F1≈0.39
- current_SOTA: 无 leaderboard；自报基线即"当前" `[未能验证]`
- public_code: 无官方
- public_leaderboard: 无
- data_access: Kaggle 下载，CC0-1.0 `[已实测]`
- compatibility_with_our_data: **低**。数据页表明代币价格/钱包维度为"simulated"（模拟），真实性未确认 `[未能验证真实性]`；交易为交易所撮合日志语义，不是链上地址图，与我们 27,613 钱包无直接关系
- leakage_risk: 中（若确为合成，无真实时间语义）
- reproduction_cost: 低
- novelty_potential: 低
- NAACL_fit: 低
- 类型: C/B → **不推荐作为基准**（合成真实性未验证）

## 13. Victor & Weintraud WWW'21 DEX Wash Trading（Uniswap/IDEX/EtherDelta）

- benchmark_name: Detecting and Quantifying Wash Trading on DEX（Zenodo 4540223）
- paper: Victor & Weintraud, "Detecting and Quantifying Wash Trading on Decentralized Cryptocurrency Exchanges", WWW'21
- year / venue: 2021 / WWW
- dataset: EtherDelta/IDEX 订单/成交级数据（EtherDeltaTrades.csv 1.05GB、IDEXTrades.csv 2.1GB、价格与 token decimals），CC BY-4.0 `[已实测 Zenodo API]`
- task: DEX wash-trading 检测（订单自成交/环形交易）
- official_split: 无统一；论文自定义
- metrics: 论文自定义（检测出的 wash 交易占比等）
- current_SOTA: 无 leaderboard；**未能验证**后续对比
- public_code: github.com/friedhelmvictor/lob-dex-wash-trading-paper
- public_leaderboard: 无
- data_access: Zenodo 免费，CC BY-4.0 `[已实测]`
- compatibility_with_our_data: **低-中**。时间是 2019-2020（DEX 早期），与我们 2022 不重叠；是订单/成交语义非链上地址图；wash 标签可作方法概念参考，但不能与我们 27,613 钱包做地址级 join
- leakage_risk: 中（非时间切分设计）
- reproduction_cost: 中（~3GB）
- novelty_potential: 中-低
- NAACL_fit: 低
- 类型: B（论文自定义评测）→ 仅作方法学参考

## 14. Elliptic / Elliptic2（Bitcoin 非法交易检测——相邻链，非 Ethereum）

- benchmark_name: Elliptic2（Elliptic Bitcoin 数据集 2）
- paper: "The Shape of Money Laundering: Subgraph Representation Learning on the Blockchain with the Elliptic2 Dataset"（arXiv:2404.19109）
- year / venue: 2024 / arXiv（Elliptic1 为 IEEE DSAA 2019）
- dataset: Bitcoin 交易图（~122k 节点 / ~234k 边，233k labeled），时间 2008-2021
- task: 非法交易子图分类（illicit/legal/unknown）
- official_split: 有公开 split（官方训练/测试）
- metrics: 官方评测（macro-F1/PR-AUC 等，随版本更新）
- current_SOTA: 有官方 leaderboard/评测器（**本次未实查，未能验证**具体当前数值）`[未能验证]`
- public_code: github.com/elliptic-co（官方 code）`[仅凭论文/描述]`
- public_leaderboard: 官方评测系统存在，**本次未实查** `[未能验证]`
- data_access: 需向 Elliptic 申请（academic 协议）`[仅凭论文/描述]`
- compatibility_with_our_data: **极低**（Bitcoin 非 Ethereum；与我们地址无交集）。仅作方法学/任务设计参照（时间切分+子图表示）
- leakage_risk: 低（官方协议严格）
- reproduction_cost: 高（需申请访问）
- novelty_potential: 低（与本项目数据无关）
- NAACL_fit: 低
- 类型: A（真正公共基准，但链不同）→ 仅参照，不接入

## 15. Forta Labelled Datasets（Ethereum phishing/恶意/受害标签清单）

- benchmark_name: Forta Labelled Datasets（forta-network/labelled-datasets）
- paper: 无正式论文（社区维护）
- year / venue: 持续更新（GitHub，MIT）
- dataset: Ethereum Mainnet `phishing_scams.csv`（~525KB）、`etherscan_malicious_labels.csv`（~679KB）、`malicious_smart_contracts.csv`（~163KB）；来自 Luabase `ethereum.tags`（Etherscan 标签 exploit/heist/phish-hack）`[已实测 GitHub API + README]`
- task: 标签资源（phishing/恶意地址清单）
- official_split: 无
- metrics: 无
- current_SOTA: 无
- public_code: github.com/forta-network/labelled-datasets（MIT）`[已实测]`
- public_leaderboard: 无
- data_access: GitHub 直接下载，MIT `[已实测]`
- compatibility_with_our_data: **中**（可直接 join 我们的 27,613 目标地址，统计命中数；标签是 Etherscan 派生的第三方标签，非官方 ground truth；需自行审计标签时间/来源）
- leakage_risk: **中-高**：标签是"事后"积累的（2020 年代收集），**不能**用于 2022 年窗口的 as-of 训练/评估，只能作为"现在时点的外部验证标签"并明确声明
- reproduction_cost: 低（MB 级）
- novelty_potential: 低
- NAACL_fit: 低
- 类型: C（标签资源）→ 推荐作为 §7 外部验证标签之一

## 16. dawsbot/eth-labels + MyEtherWallet/ethereum-lists（社区地址标签）

- benchmark_name: eth-labels（dawsbot，MIT，296 stars）；ethereum-lists（MyEtherWallet，MIT，711 stars）
- paper: 无（社区维护）
- year / venue: 持续更新 / GitHub
- dataset: 社区地址↔标签清单（eth-labels：accounts.csv 12.3MB / tokens.csv 7.7MB / db.sqlite3 42MB；ethereum-lists：src/addresses/addresses-{light,dark}list.json 等安全清单）`[已实测 GitHub API]`
- task: 标签资源（交易所/DeFi/桥/混币器/钓鱼等实体标签）
- official_split / metrics / current_SOTA / public_code / public_leaderboard: 不适用
- data_access: GitHub，MIT `[已实测]`
- compatibility_with_our_data: **中**：可与 27,613 目标 join 得到实体标签（exchange/mining/ICO/gambling 等类别覆盖度需实测统计，本会话未下载统计→`[未能验证]`覆盖度）
- leakage_risk: 中-高（第三方标签无时间戳；同样只能做"时点外部验证"）
- reproduction_cost: 低
- novelty_potential: 低
- NAACL_fit: 低
- 类型: C（标签资源）

## 17. Chen et al. 2020 (TOIT) Ethereum Phishing 数据集（原始论文评测）

- benchmark_name: Phishing Scams Detection in Ethereum Transaction Network（Chen et al., TOIT 2020）
- paper: Chen, Peng, Liu, Li, Xie, Zheng, "Phishing Scams Detection in Ethereum Transaction Network", ACM TOIT 21(1), 2020
- year / venue: 2020 / ACM Transactions on Internet Technology
- dataset: Etherscan 钓鱼标签地址（论文约 2,973 phishing + 4,000 正常）+ 交易子图；**官方数据未正式发布**（无官方下载链接）；社区重实现：yuanqi7/Phishing-Detection-on-Ethereum（34 stars，无 license）等 `[已实测 GitHub 搜索][仅凭论文]`
- task: 钓鱼账户分类（图+特征方法）
- official_split: 论文自定（train/test 无公开固定 split）
- metrics: AUC/Precision/Recall/F1
- current_SOTA: 各后续论文自报（2021-2024 一系列钓鱼检测论文），**无统一 leaderboard，未能验证**
- public_code: 仅社区重实现（license 不明）`[已实测]`
- public_leaderboard: 无
- data_access: 需自行爬 Etherscan 或使用社区数据；license 不明 `[未能验证]`
- compatibility_with_our_data: 低-中（2018-2020 数据窗口，与 2022 不重叠；钓鱼标签可作外部验证但地址交集需实测）
- leakage_risk: 高（第三方数据时间/来源不明）
- reproduction_cost: 中-高（爬取/Etherscan API）
- novelty_potential: 低
- NAACL_fit: 低
- 类型: B（论文自定义评测，无官方数据）→ 仅参照，不作为主基准

## 18. Lincozz Ethereum-Phishing-Account-Dataset（爬虫项目，无数据）

- benchmark_name: Ethereum Phishing Account Transaction Network Dataset（lincozz）
- paper: 无正式论文（GitHub 项目）
- year / venue: 2026-05 更新 / GitHub
- dataset: 7,057 个种子钓鱼地址 + BFS 2-hop 交易网络；**仓库仅 20KB（无数据，只有爬虫）**，需自行用 Etherscan API 爬取 `[已实测 GitHub API]`
- task: 钓鱼网络/分类
- official_split / metrics / current_SOTA / public_leaderboard: 无
- data_access: 无 license；数据需自爬 `[未能验证]`
- compatibility_with_our_data: 低
- leakage_risk: 高（自爬无时间协议）
- reproduction_cost: 高（Etherscan API 限流）
- novelty_potential: 低
- NAACL_fit: 低
- 类型: C（工具）→ 不推荐

## 19. 预算化节点/图子集选择（Budgeted node selection / active learning / IM）

- benchmark_name: 无标准 Ethereum 公共基准（搜索确认）
- 说明: 现有方法学基准（如 Cora/Citeseer/PubMed/ogbn-arxiv 上的 active learning、NetHEPT/Wiki-Vote 等影响最大化 IM 基准）都是非 Ethereum 引用图/社交图；**未发现 Ethereum 地址图上的预算化钱包选择公共基准** `[仅凭论文/描述，搜索确认]`
- task: 预算化节点选择（预算 K 内选择钱包最大化未来下游效用）
- official_split / metrics / current_SOTA / public_code / public_leaderboard / data_access: 不适用
- compatibility_with_our_data: 不适用（需自建，见 benchmark_plan.md §8/§9 新任务协议）
- leakage_risk: 不适用（自建协议必须 as-of）
- reproduction_cost: 自建成本（中等，基线 cheap）
- novelty_potential: **高**（若做成严谨 as-of 新基准+强基线，可作为论文原创贡献；但"新基准"≠SOTA）
- NAACL_fit: 中-高（与预算化推理分配叙事一致）
- 类型: 无现有基准 → 自建新任务

## 20. Ethereum 行为聚类（Behavioral clustering）

- benchmark_name: 无标准公共基准
- 说明: 搜索到的都是论文自定义聚类（Ethereum 地址聚类/角色发现），无公开标签+指标+split 的统一基准 `[仅凭论文/描述]`
- task: 行为聚类/角色发现
- 兼容路径: 用 §7 的外部标签（Forta/eth-labels/LiveGraphLab trader 标签/EX-Graph wash 标签）对"无监督行为表示聚类"做外部验证（ARI/NMI/purity），不重新定义标签去贴合聚类 `[沿用方案§7]`
- leakage_risk: 中-高（外部标签为事后标签）
- novelty_potential: 中
- NAACL_fit: 中
- 类型: 无现有基准 → 外部标签验证

---

## 汇总表

| # | 候选基准 | 类型 | 推荐 | 一句话理由 |
|---|---|---|---|---|
| 1 | EX-Graph Ethereum LP | A | ✅ 接入（图级外部验证） | 官方 split+11 基线可复现；leaderboard 404→只能比论文自报 |
| 2 | EX-Graph Wash-trading 检测 | B/A | ⚠️ 可选（图级） | 标签/图未本地验证，正例极少；需先下载+映射 |
| 3 | EX-Graph Matching LP | B(缺陷) | ❌ 暂不接入 | 官方 split 文件=LP split（md5 相同），无法复现论文表 7 |
| 4 | TGB tgbl-coin-v2 | A | ✅✅ 首选外部 SOTA | 活 leaderboard（2026-09-11 实测），ERC-20 稳定币 2022 窗口重叠 |
| 5 | TGB tgbn-token | A | ✅ 第二外部 SOTA | 活 leaderboard，用户-代币交互 NDCG |
| 6 | Chartalist | C | ⚠️ 数据源 | TGB eth 数据源；本身无任务基准 |
| 7 | Harvard ERC-20 2021/2022 | C | ✅ ERC-20 pilot | CC0、2022 窗口、可 join 27,613；缺严格事件顺序 |
| 8 | LiveGraphLab | B | ✅ NFT 语义外部验证 | 与 EX-Graph NFT 语义最接近；无 leaderboard |
| 9 | TGS | C/B | ⚠️ 仅 dev pilot | 84 token、token-selection bias |
| 10 | XBlock | C | ❌ | 2015-16、几乎无地址交集、license Unknown |
| 11 | vagifa Fraud（Kaggle 特征表） | B | ⚠️ 仅静态标签验证 | 聚合全历史特征、无时间切分→泄漏风险高 |
| 12 | sergionefedov Wash Trading（Kaggle） | B/C | ❌ | 合成真实性未验证；非链上地址语义 |
| 13 | Victor & Weintraud DEX wash | B | ⚠️ 方法学参考 | 2019-20 DEX 订单语义，窗口不重叠 |
| 14 | Elliptic/Elliptic2 | A(异链) | ❌ 仅参照 | Bitcoin 非 Ethereum；需申请 |
| 15 | Forta Labelled Datasets | C | ✅ 账户分类外部标签 | MIT、直接 join；标签为事后→仅时点验证 |
| 16 | eth-labels / ethereum-lists | C | ✅ 外部标签补充 | MIT；覆盖度需实测 |
| 17 | Chen 2020 phishing | B | ⚠️ 仅参照 | 官方数据未发布；社区数据 license 不明 |
| 18 | Lincozz phishing 爬虫 | C | ❌ | 仓库无数据，需自爬，无 license |
| 19 | 预算化节点选择 | 无 | ✅ 自建新基准 | 无现有基准；as-of 协议+强基线 |
| 20 | 行为聚类 | 无 | ✅ 外部标签验证 | 无标准基准；用 §7 标签做 ARI/NMI |

**推荐接入优先级：TGB tgbl-coin-v2 / tgbn-token（活 leaderboard）＞ EX-Graph LP（官方协议外部验证）＞ LiveGraphLab（NFT 语义）＞ 账户分类外部标签验证（§7）＞ 自建预算化钱包选择基准（§8/§9）。**
