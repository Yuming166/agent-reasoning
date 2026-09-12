# Benchmark 接入计划（Group F → Group 0-6 可执行）

- 生成日期：2026-09-11；本机 cloud82，10.63.0.82
- 前置：所有最终结果以 Group 0 `DATA_AUDIT.md` + `temporal_protocol.yaml` 通过为门槛（research/README.md 规则）
- 原则：外部基准用官方协议；我们的数据一律 as-of；标签只做时点外部验证；leaderboard 提交前实时重查

## 0. 总体顺序（先做哪个）

| 阶段 | 基准 | 目的 | 依赖 |
|---|---|---|---|
| P0（第 1 周） | TGB `tgbl-coin-v2` / `tgbn-token` | 拿到活 leaderboard 的**标准外部 SOTA 通道**（唯一可提交的公共榜单） | TGB 包 + PyG |
| P1（第 2 周） | EX-Graph Ethereum LP（官方 split） | 官方协议图级外部验证 + 论文表 5 对齐 | LP 图（已在本地）+ dgl/PyG 环境 |
| P2（第 3 周） | LiveGraphLab 时间链接预测/节点分类 | NFT 语义外部验证（与 EX-Graph 最接近） | 194MB link-pred / 186MB node-classify 下载 + torch-geometric 环境 |
| P3（并行） | §7 账户分类外部标签验证（eth-labels/Forta/ethereum-lists + LiveGraphLab trader 标签） | "行为表示→外部标签"有效性声明 | 标签下载 + join 覆盖统计 |
| P4（第 4-6 周） | 自建新任务：预算化钱包选择（§8/§9） | 原创可复现新基准（非 SOTA 声明） | Group B/C/D/E 输出 + 强基线 |
| 随时 | EX-Graph wash-trading / matching | 仅在 P1 顺利且有资源时；matching 因发布 split 缺陷暂缓 | 7+GiB 下载 / 作者补发正确 split |

## 1. P0：TGB tgbl-coin-v2 / tgbn-token（首选外部 SOTA）

- 为什么：唯一当前可访问的 Ethereum 时间图公共 leaderboard（2026-09-11 实测可访问）；tgbl-coin 时间窗 2022-04-01~11-01 与我们的 2022 窗口重叠；评测器/负采样由官方控制，可比性强
- 任务/指标：tgbl-coin = 动态链接预测，MRR（test）；tgbn-token = 节点属性预测，NDCG@10
- 当前 SOTA（2026-09-11 实测）：tgbl-coin-v2 MRR 0.832（TPNet）；tgbn-token NDCG@10 0.513（NAVIS）
- 官方 split：TGB 包内固定时间切分；streaming 设置（test 只更新 memory，不反向传播）
- 算力/数据导出：
  - 下载：tgbl-coin-v2.zip 1.28GB + tgbn-token.zip 1.29GB（已实测 HEAD 200）
  - 环境：`.venv-cuda`（torch 2.14+cu126）+ `pip install tgb torch-geometric`（tgb 为 MIT）；GPU5（RTX4090 空闲）
  - 估计：官方基线（TGN/DyGFormer）单模型数小时级；首月 2-3 个基线校准即可
  - 我们数据导出量：**0**（官方 zip 已聚合；不需要从 BQ 导数据）
- 谁做：Group C（时间图方法）提供模型；Group F 维护 leaderboard 状态与提交；Group 0 确认无泄漏（官方协议即无泄漏）
- 边界：CC BY-NC（非商业）—— NAACL 研究论文可用；**不得将 TGB/Chartalist 数据并入我们对外发布的数据包**

## 2. P1：EX-Graph Ethereum Link Prediction（官方协议外部验证）

- 为什么：官方 11 基线 + 固定 split pkl + 论文表 5 参照；LP 图 37.3GB 已在本地
- 任务/指标：边链接预测；AUC-ROC/Precision/Recall/F1（5 重复平均±std）；论文参照 with-X APPNP AUC 0.89±0.02、wo-X GraphSAGE 0.84
- 官方 split：`ethereum_link_prediction/*_edge_indices.pkl`（pos/neg train 842,821；val 111,582；test 201,780）；**必须用官方 pkl，禁止自切**
- 算力/数据导出：
  - 本地已有 LP 图（37.3GB）+ split pkl（0）+ 大图（11.6GB）
  - 环境二选一：(a) `exgraph-x` env 补 sklearn/torchmetrics/pandas（dgl 1.1.0 + torch 2.0.1+cpu，CPU 慢）；(b) 用 PyG 移植 11 基线到 `.venv-cuda`（推荐，torch 2.14 兼容）
  - GPU5 可用；先复现 GCN/GAT/GraphSAGE/DAGNN/APPNP × wo/with = 10 配置校准论文表 5，再扩全 11 模型
  - 估计：GPU 1-3 GPU-天 全 22 配置；最小闭环 10 配置约 0.5-1 GPU-天
  - 我们数据导出量：**0**（官方图级基准）
- 谁做：Group C 提供模型实现；Group A 的行为表示若要在该图上评估需先解决"27,613↔LP 节点映射"（**当前无法**，见 exgraph_benchmark_note.md）；Group F 负责与论文表 5 对齐审计
- 边界：leaderboard 404，只比论文自报；提交前重查 `exgraph.deno.dev`；wash-trading 图（4.46+1.46+?GiB）如需接入先下载并核对脚本文件名

## 3. P2：LiveGraphLab（NFT 时间图外部验证）

- 为什么：NFT 事件语义与 EX-Graph 最接近；官方提供 link-pred/node-classify 处理图和代码（Roland 框架）
- 任务/指标：时间链接预测（MRR/AUC）、时间节点分类（F1 等）；day/week/month 快照
- 官方 split：代码 `train_live_update_fixed_split.py` 等提供；论文自定义切分（无统一 leaderboard → 只报告我们自己的结果与论文基线）
- 算力/数据导出：
  - 下载：link-pred-data.zip 194MB / node-classify-data.zip 186MB（Zenodo CC BY-4.0，已实测）
  - 环境：torch-geometric 2.x（本地 vendor 代码）；需移植到 `.venv-cuda` 或建独立 env
  - 我们数据导出量：0
- 谁做：Group C；节点分类标签（trader 启发式）供 Group A/E 的行为聚类外部验证
- 边界：标签为启发式（全历史计算），报告时标注；不做 SOTA 声明

## 4. P3：§7 账户分类外部标签验证（有效性声明）

- 任务：对 Group A（行为画像）与 Group E（Qwen 语义表示）的聚类/表示做外部标签验证（ARI/NMI/purity/命中率）
- 标签源（按优先级）：dawsbot/eth-labels（MIT）＞ Forta labelled-datasets（MIT）＞ MyEtherWallet/ethereum-lists（MIT）＞ LiveGraphLab trader 标签（CC BY-4.0）＞ EX-Graph wash 标签（CC BY-NC-SA，若拿到映射）
- 数据导出：全部为地址级小文件（MB 级），本地 join 即可；**不需要 BQ 查询**
- 铁律：
  - 标签只做**时点外部验证**（标签事后收集、无时间戳），不进入 as-of 训练/选择
  - 先冻结标签文件 sha256/版本 → 统计与 27,613 目标的命中覆盖 → 再评估
  - 不把无监督角色重定义成标签；标签是验证轴不是学习目标
- 谁做：Group A/E 提供表示；Group F 提供标签清单与覆盖统计；Group 0 把关时间泄漏
- 边界：任何"分类效果"都注明标签源与事后性，不称 SOTA

## 5. P4：自建新任务——预算化钱包选择（§8/§9，原创可复现基准）

- 任务定义（方案 §8/§9）：在 cutoff t 用 G_≤t 选择 K∈{10,25,50,100,250,500,1000} 个钱包，最大化未来 [t, t+Δ] 的下游预测效用；选择期与评估期严格分离
- 指标：加权 MRR、Recall@K、NDCG@K、未来链接/活动预测增益、rank correlation、utility per selected wallet、选择重叠/持久性；主指标=budget 曲线上的 ΔMRR/1000 tokens（与 Group D/E 对齐）
- split（沿用项目冻结协议）：train 2022-03~06 / tune 07 / frozen 08 / 额外外检 09（不用于调参）
- 基线（必跑，cheap）：random、volume、activity、degree、weighted degree、PageRank、k-core、behavioral score、predictive influence、IG、learned router、oracle（上界）
- 算力/数据导出：
  - 本地已产：`exgraph_structural_features.csv`、`wallet_asof_features`、`influence_v1`、`llm_panel_v2` 路由器等
  - BQ 导出量：小（as-of 特征已在表内；只需快照表聚合，控制 bytes-billed）
  - 基线成本：低（数小时）；learned router 已有 v1 复现路径
- 谁做：Group B/D/E 的方法作为候选选择器；Group C 提供时间图基线；Group F 维护协议与基线清单；Group 0 把关 as-of
- 边界：新基准 ≠ SOTA；论文表述为"新任务 + 强基线 + 我们方法的增益"，**不得称超越某公共 SOTA**

## 6. 暂缓/不接入清单（附原因）

| 候选 | 状态 | 原因 |
|---|---|---|
| EX-Graph Matching LP | 暂缓 | 发布 split=LP split（md5 相同），无法复现论文表 7；需作者补发正确 split |
| EX-Graph Wash-trading | 待定 | 需 7+GiB 下载 + 地址映射缺失 + 脚本/数据名不一致；正例 0.05% |
| XBlock | 不接入 | 2015-16、几乎无地址交集、license Unknown（已实测） |
| vagifa Fraud（Kaggle 特征表） | 仅静态验证 | 聚合全历史特征、无时间切分，泄漏风险高 |
| sergionefedov Wash Trading（Kaggle） | 不接入 | 合成真实性未验证 |
| Victor & Weintraud DEX wash | 仅方法学参考 | 2019-20 DEX 订单语义，窗口不重叠 |
| Elliptic/Elliptic2 | 仅参照 | Bitcoin 非 Ethereum；需申请访问 |
| TGS | 仅 dev pilot | 84 token、token-selection bias |

## 7. Group 分工与交付物

- Group 0：在 P0/P1 前完成 `DATA_AUDIT.md` + `temporal_protocol.yaml`；确认 TGB/EX-Graph 官方协议无泄漏；给标签覆盖统计把关
- Group A/B/C/D/E：按各自假设提供表示/选择器，交给 P0-P4 的对应评测；结果必须附 as-of 声明
- Group F（本组）：维护 `benchmark_registry.md`（本文件所在目录）状态、leaderboard 实时重查（tgbl/tgbn 每次提交前、EX-Graph 恢复检查）、发布正确的 SOTA 引用与边界
- 统一输出：每次评测产出 manifest（数据集版本、split、指标、seed、算力、bytes-billed、日期）+ 结果 jsonl，放在各 group 目录
