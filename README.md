# EX-Graph 微观交易行为分析

这个目录用于核查 EX-Graph 的 Ethereum Graph 是否保留单笔交易，评估其是否适合做带时间顺序的账户级交易分析，并为后续接入 Crypto Influencer 推文数据、反事实节点筛选和交易对象预测准备数据审计脚本。

## 当前进展

- 已建立独立项目目录：`/storage/gaoym/ex-graph-microtransaction-analysis`
- 已固定 EX-Graph 官方仓库快照：`vendor/EX-Graph-repo`
- 已保存 EX-Graph 论文 arXiv source：`data/metadata/paper/src`
- 已下载官方链接当前返回的 `ethereum_graph.gpickle`（11,616,467,480 bytes）：`data/raw/ethereum_graph.gpickle`
- 已完成本地 pickle/NetworkX 审计：`artifacts/ethereum_graph_audit.json`、`artifacts/weight_distribution.json`
- 已完成时间交易数据集候选调研：`notes/temporal-dataset-options.md`
- 已完成第二轮数据集决策（补充 Google Cloud、AWS Public Blockchain、Harvard ERC-20 Trading）：`notes/dataset-selection-recommendation.md`
- 已保存外部数据集当前版本/文件大小/代表性 S3 分区清单：`data/metadata/temporal_dataset_catalog.json`
- 已补充 BigQuery 费用、Sandbox 限制与开放数据候选：`notes/cost-and-open-data-options.md`
- 已添加 Google 数据源的 target-address overlap count-only 验证查询：`src/sql/validate_exgraph_address_coverage_bigquery.sql`
- 已在 BigQuery 项目 `ictdata-507912` 中物化六个月逐事件表（不下载源表到跳板机）：`exgraph.external_transactions_20220301_20220901`、`exgraph.token_transfers_20220301_20220901`、`exgraph.internal_traces_20220301_20220901`
- 已建立 EX-Graph 官方匹配维表和有方向的事件序列表：`exgraph.exgraph_x_matches_v1`、`exgraph.target_event_sequences_20220301_20220901`；SQL 与执行清单见 `src/sql/create_exgraph_sequence_tables_ictdata.sql`、`artifacts/google_sequence_tables_2022-03_2022-09.json`
- 已下载并审计可能对应的 XBlock/Kaggle `Ethereum Partial Transaction Dataset`：`notes/xblock-temporal-dataset-audit.md`、`artifacts/ethereum_partial_transaction_audit.json`
- 已下载并审计 Crypto Influencer Mendeley v5 的 schema/时间范围；原始文件位于 `data/raw/crypto_influencer_v5/`
- 官方 README 标注该图为 `networkx.DiGraph`，有 2,610,465 个节点、29,585,858 条边，边字段为 `from_address, to_address, weight, block_number`。

## 已确认结论（2026-09-07）

我下载并成功加载了官方 README 所链接的 Google Drive 文件。当前二进制文件实际是 `networkx.classes.digraph.DiGraph`，不是 `MultiDiGraph`；实际有 1,810,641 个节点、11,876,618 条边，所有 11,876,618 条边都有且只有一个 `weight` 字段，**没有任何边包含 `block_number`**。`weight` 全部是整数，范围为 1--17,173，中位数为 1；所有 edge 的 `weight` 总和为 16,004,443，其中 1,079,058 条边的 weight 大于 1。

因此，针对“weight 是逐笔还是聚合”的问题，结论是：**发布的这个文件是按有向地址对聚合后的静态加权图，不是逐笔交易事件流。** 同一 `(from, to)` 地址对最多一条边；整数 `weight` 的形状与“该地址对在数据窗口内发生过多少次交易”的 multiplicity/count 高度一致。README 没有给出 weight 的构造代码，所以这里把“计数型聚合”标为基于二进制证据的结论，而不是声称有官方字段说明。

另外，当前 Google Drive 二进制与仓库 README 的表格不一致：README 写的是 2,610,465 节点、29,585,858 边，并列出 `block_number`；实际下载文件是 1,810,641 节点、11,876,618 边且无 `block_number`。这可能是文件被替换、版本落后/不同，或 README 与 Drive 没同步。后续论文/实验中必须把下载文件 hash、节点边计数和字段审计写进 manifest，不能只引用 README 表格。

这意味着：当前文件无法恢复交易发生的先后顺序，也无法按 block 或交易哈希做时间切分。它仍适合做静态关系、频次/强度和候选影响节点筛选；如果要预测“下一笔交易对象”或做反事实时间推演，需要另找逐笔交易表（至少包含 `tx_hash, from, to, block_number/timestamp`，最好还有 transaction index/value/token contract）。

## 运行审计

建议先安装轻量依赖（不会下载模型）：

```bash
cd /storage/gaoym/ex-graph-microtransaction-analysis
python -m venv .venv
. .venv/bin/activate
pip install networkx
python src/audit_ethereum_graph.py \
  --graph data/raw/ethereum_graph.gpickle \
  --output artifacts/ethereum_graph_audit.json
```

审计脚本会报告：

- 图类型、是否 directed/multigraph；
- 节点/边数量与官方 README 对照；
- 边字段、字段类型和样例；
- `block_number` 的范围、缺失和唯一值情况；
- `weight` 的类型、范围和缺失情况；
- 对重复地址对的可表示性结论。

## 数据来源与版本记录

- EX-Graph 官方仓库：`vendor/EX-Graph-repo`
- EX-Graph Ethereum Graph Google Drive file id：`1VWUGTUniv7-uDISXvJcMLE4OMCtQFPn6`
- 论文 source：`data/metadata/paper/src`
- 二进制数据文件大小和下载 URL 的确认信息：`data/metadata/ethereum_graph_download_metadata.txt`
- 二进制 SHA-256：`data/metadata/ethereum_graph_sha256.txt`
- 可复现实验 manifest：`data/metadata/source_manifest.json`
- 去重后的 27,613 个 target 地址：`data/metadata/target_addresses.csv`

## 当前数据集选择建议

- 完整 Ethereum 行为：优先 Google Cloud Blockchain Analytics；
- 无 GCP 时的公共本地备选：AWS Public Blockchain Data；
- 最快可运行的 ERC-20 pilot：Harvard Dataverse ERC-20 Trading 2022；
- 若将研究限定为 NFT：Live Graph Lab。

推荐第一年窗口：`[2021-08-01 00:00:00 UTC, 2022-08-01 00:00:00 UTC)`。交易表应保留 `event_type`，并分别处理 external transaction、token transfer、internal trace 和 log/event，不能把它们无标注地 union 成一类交易。

## 研究边界

本项目先做数据可用性/时间顺序审计，不把图结构本身包装成“已能预测交易”或“已证明影响者导致交易”。后续若接入推文和反事实推演，应明确区分：

1. 图数据能否重建事件时间线；
2. 交易对象预测的训练/验证是否严格按时间切分；
3. 反事实结果是模型模拟还是因果效果；
4. 节点影响力筛选是否使用了未来信息。
## EX-Graph match and directional event sequences (2026-09-07)

已根据官方 `twitter_matching.csv` 建立：

- `ictdata-507912.exgraph.exgraph_x_matches_v1`：27,613 个官方 EX-Graph 匹配地址，附带来源 commit、文件 hash 和版本信息；不包含原始 Twitter/X handle。
- `ictdata-507912.exgraph.target_event_sequences_20220301_20220901`：11,836,196 条有方向事件角色记录。一个事件的两个不同匹配端点会生成 outgoing/incoming 两条记录；self-transaction 只生成一条 self 记录。
- `external_tx` 与 `token_transfer` 标记为 `sequence_role=primary`；`internal_trace` 标记为 `sequence_role=auxiliary`。
- 无目的地址的合约创建/相关记录保留在表中，`counterparty_present=false`；建立 next-counterparty 标签时应过滤这些记录。

详细 schema、查询成本、行数校验和序号唯一性检查见 `notes/google-event-preparation.md` 与 `artifacts/google_sequence_tables_2022-03_2022-09.json`。

## Google temporal event preparation (2026-09-07)

The first six-month pilot is stored in BigQuery rather than on the jump host:

- `ictdata-507912.exgraph.external_transactions_20220301_20220901`: 2,877,009 rows, partitioned by `DATE(block_timestamp)` and clustered by endpoints.
- `ictdata-507912.exgraph.token_transfers_20220301_20220901`: 4,275,544 rows, partitioned by `DATE(block_timestamp)` and clustered by endpoints and token contract.
- `ictdata-507912.exgraph.internal_traces_20220301_20220901`: 4,478,515 rows, partitioned by `DATE(block_timestamp)` and clustered by endpoints.

All three tables retain counterparties for any event touching a mapped address. Native transactions, token transfers, and internal traces remain separate event families. See `notes/google-event-preparation.md`, `artifacts/google_event_prep_2022-03_2022-09.json`, and `artifacts/google_trace_prep_2022-03_2022-09.json`.

## 重要节点选择机制验证（2026-09-10）

已完成 Stage 1 的重要节点/事件选择验证，主结果目录为
`artifacts/llm_panel_v2/node_selection_v2_final_audited_20260910/`，完整报告见
`notes/node-selection-go-no-go-20260910.md`。

- 协议：2022-06 train、2022-07 validation/tuning、2022-08 frozen test、2022-09 额外时间外检验；每月 1,000 个分层事件。
- 四个月均使用授权 `Qwen3.5-4B` vLLM 配置；full/no-CF parse rate 均为 100%，候选 truth support 均为 100%。
- 50% 预算的加权 MRR：learned `0.4606`，最佳非学习 baseline（degree）`0.4205`，paired bootstrap 差值 `+0.0401`，95% CI `[+0.0209,+0.0607]`。
- learned 在 5 个预算点中 4 个超过最佳非学习 baseline；5% 点与 volume 基本持平但略低 `0.0001`。
- 结论：`GO_STAGE_2_RECURSIVE_REASONING`。该结论仅支持“选择值得分配 deliberation 预算的事件/节点”，不证明因果影响力或 X 到链上行为的因果关系。
- 冻结输入：`frozen_test_selector_input.csv`（只含调用前特征/分数）；下一阶段候选节点：`frozen_test_important_nodes_b50.csv`；结果审计单独保存在 `frozen_test_outcomes_for_audit.csv`。

评估脚本：`src/agent/evaluate_node_selection.py`。不要将 August 的 `gain_full`、truth rank、oracle 选择结果带入递归推理阶段。

## LLM 服务配置与使用限制

默认使用 `Qwen3.5-4B`，Base URL 为 `http://10.63.0.82:31518/v1`；客户端自动追加 `/chat/completions`。如需替换，可在有权使用的计算资源上自行通过 vLLM 部署模型，或使用自费购买、授权用于本项目的 API 服务。

切换服务时，通过 `LLM_BASE_URL` 或 `chat(..., base_url=...)` 设置 Base URL（不含 `/chat/completions`），同步更新运行脚本的 `--model` 或 `chat(..., model=...)`。鉴权凭据仅通过 `LLM_BEARER` 提供，不得写入代码、文档或版本库。

Qwen/vLLM 的 JSON 任务默认不发送可选的 `reasoning_effort` 字段：部分服务会把 `reasoning_effort=low` 当作隐藏思考预算，在冻结的 `max_tokens=700` 下耗尽输出而不返回 JSON。若确实需要显式控制该字段，可设置 `LLM_REASONING_EFFORT`；设置为空值（`LLM_REASONING_EFFORT=`）表示省略。

禁止使用 `http://10.63.0.72:8317/v1`，客户端保留对该主机和端口的拦截。不得借用其他用户的推理服务或 Codex、Claude Code 的服务地址及凭据；默认服务不可用时，请按上述方式配置替代服务。
