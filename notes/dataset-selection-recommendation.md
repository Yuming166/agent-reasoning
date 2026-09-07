# Temporal 交易数据集选择建议

更新时间：2026-09-07

## 结论先行

可以把 EX-Graph 与逐笔 temporal transaction 数据 join 成一个新的异构时间图，但 join 的对象应当是 **EX-Graph 的地址映射表**，而不是当前发布的 `ethereum_graph.gpickle` 边本身：

- `ethereum_graph.gpickle` 是静态 `DiGraph`，同一 `(from, to)` 只有一条边，`weight` 是聚合后的频次型权重，不能提供逐笔时间线；
- `twitter_matching.csv` 去重后得到 27,613 个唯一 Ethereum 地址及其匿名 X node id；
- 将外部数据的 `from/to` 地址统一为小写、去掉可选的 `0x` 后，直接与这 27,613 个地址做 whitelist join；
- X 的 follow graph 和 node features 作为静态关系/节点特征，逐笔链上事件作为动态边/事件流。

“地址不会变化”只说明地址这个标识符稳定，不说明它一定对应一个自然人或一个 X 账号。必须区分 EOA、合约、交易所/托管地址、多人共用地址和机器人地址；`to_address` 很多时候是合约，而不是一个人。

## 推荐排序

### A. 完整 Ethereum 行为：Google Cloud Blockchain Analytics

**作为论文主数据源的首选。** 当前官方表族至少包括 `transactions`、`token_transfers`、`traces`、`logs` 和 `blocks`。它们可以分别提供：

- 普通 external transaction：`block_timestamp`、`block_number`、`transaction_index`、`transaction_hash`、`from_address`、`to_address`、`value`；
- token transfer：token 合约、sender/receiver、`transaction_hash`、`log_index`、token id/value；
- internal value flow：`traces`；
- 未解码合约事件：`logs`。

这样可以同时保留交易发生时间、区块内顺序和事件级去重键。对本项目而言，先上传 `target_addresses.csv` 为小表，再分别抽取目标地址作为 sender/receiver 的事件。需要注意 whitelist join 不一定按比例减少 BigQuery 扫描量，执行前要 dry-run，并冻结当前表名、schema、查询文本、执行日期和导出结果 hash。

适用范围：普通 ETH、ERC-20、NFT/token transfer、internal call/value flow 的分层行为研究。

### B. 不使用 GCP：AWS Public Blockchain Data

**作为免费、可本地复现的备选。** AWS 公共 S3 上有按日期分区的 Ethereum Parquet 表，包括 `transactions`、`token_transfers`、`traces`、`logs` 和 `blocks`。真实对象路径形如：

```text
s3://aws-public-blockchain/v1.0/eth/transactions/date=2022-02-01/
```

表中包含 block timestamp、block number、transaction index、transaction hash 和 from/to 等可用于严格排序和去重的字段。当前 AWS schema 中 `token_transfers` 主要定义为 ERC-20；ERC-721/ERC-1155 需要从 `logs` 自行解析，或者用 Live Graph Lab/BigQuery 的 token transfer 表补足。AWS 文档将这套数据标为实验性数据产品，因此建议做 hash/schema 冻结并将其作为独立数据源报告，不要默认它与 Google/EX-Graph 的解析口径完全一致。

适用范围：本地开发、复现实验、完整 external transaction + ERC-20 + traces/logs 管线。

### C. 直接下载的 ERC-20 版本：Harvard Dataverse ERC-20 Trading 2015--2024

**作为最容易先跑起来的 ERC-20 pilot。** 该数据按月提供压缩 TSV，覆盖 2015 年 11 月至 2024 年 12 月；每条记录包含：

```text
block_id, transaction_hash, time, token_address,
sender, recipient, value, token_name, token_symbol, token_decimals
```

它很适合直接与 27,613 个地址 join，并研究“推文日级特征 -> 后续 ERC-20 转账/交易对象”。当前 Dataverse API 显示 2021/2022 年文件按月发布；例如：

- 6 个月窗口 `2022-02-01 <= t < 2022-08-01`：当前压缩文件合计约 6.71 GB；
- 1 年窗口 `2021-08-01 <= t < 2022-08-01`：当前压缩文件合计约 15.64 GB。

它的限制是：文档字段没有 `transaction_index` 或 `log_index`，所以同一区块/同一秒内的严格顺序和同一 transaction 内的多事件边界需要额外审计；它也只覆盖 ERC-20，不包含原生 ETH、NFT 和所有 internal calls。因而它适合做 ERC-20-only 版本或开发基线，不应被表述成完整 Ethereum 行为数据。

### D. 与 EX-Graph/NFT 语义最接近：Live Graph Lab

Live Graph Lab 的 metadata 是逐条 NFT transaction/event 表，字段包括 collection address、block number、from/to、token id、transaction hash、value 和 timestamp；代码说明其 metadata 取 Ethereum 在 2022-08-01 之前的区块，数据规模约 124 million edges。Zenodo 的 `meta-data.csv.zip` 当前约 5.84 GB，CC BY 4.0。

如果研究问题明确是“EX-Graph 中 NFT 交易的微观行为”，这是最匹配的公开候选。推荐窗口：

```text
6 个月：2022-02-01 00:00:00 UTC <= t < 2022-08-01 00:00:00 UTC
1 年：  2021-08-01 00:00:00 UTC <= t < 2022-08-01 00:00:00 UTC
```

限制：不代表普通 ETH/ERC-20/所有合约交互；同一 transaction hash 可能对应多行 NFT transfer，仍应保留 event-level 语义，不要直接当成“一行就是一笔独立用户决策”。

### E. 小规模开发集：TGS / Temporal Graph Foundation Models

TGS raw 是逐行 ERC-20 transaction 数据，当前 raw zip 约 602 MB，CC BY 4.0，适合先验证 address join、时间切分、label 构造和模型输入。但它只覆盖约 84 个选定 ERC-20 token，存在 token selection bias，不能支持完整 Ethereum 结论。

### F. 其他补充候选

- ERC-20/ERC-721 Transfer Events（Zenodo 10644077）：覆盖到 2022-06-21，地址/合约常以数值 ID 配合 lookup 表提供，适合旧窗口的 event-level pilot；处理复杂，不适合作为本项目第一主数据源。
- ERC-1155 Transfer Events（Zenodo 14901528）：可作为 ERC-1155 补充，不可单独代表完整 NFT 或 Ethereum 行为。
- Hugging Face BlockDB Parquet：字段适合 external transaction，但单月文件很大，公开许可证/provenance 需要再次核实，不建议作为论文主数据源。

## 我建议的项目落地方案

### 方案 1：论文主线（推荐）

```text
EX-Graph address mapping + X follow graph/features
                    |
                    +-- BigQuery transactions
                    +-- BigQuery token_transfers
                    +-- BigQuery traces/logs（第二阶段）
                    |
                    +-- Crypto Influencer tweets（仅在有 author crosswalk 时归因到 influencer）
```

窗口先固定为：

```text
[2021-08-01 00:00:00 UTC, 2022-08-01 00:00:00 UTC)
```

理由：恰好一年，处在 EX-Graph/Live Graph Lab 的共同历史区间，并覆盖 Crypto Influencer CSV 的有效时间范围。由于 tweet 主 CSV 只有日期而没有可靠的完整发布时间，建议按日聚合，并至少使用 1 天 lag；不要把同一天的链上交易直接当作推文之后的反应。

事件表至少保留：

```text
event_id
source_dataset
event_type                 # external_tx / token_transfer / internal_trace / log_event / nft_transfer
block_timestamp
block_number
transaction_index
log_index
transaction_hash
from_address
to_address
counterparty_address
contract_address
token_standard
token_id
value_raw
value_numeric
is_target_from
is_target_to
exgraph_node_id_from
exgraph_node_id_to
```

`external_tx`、`token_transfer`、`internal_trace` 不要直接合并成一个没有 `event_type` 的“交易”；同一 transaction 可能在多个表中出现，这是不同层次的链上语义。

### 方案 2：无云账号的首个可运行版本

先采用：

```text
Harvard ERC-20 Trading 2022-02 ... 2022-07
+ EX-Graph target_addresses.csv
+ X graph/node features
+ Crypto Influencer 日级特征
```

这个 6 个月版本能较快验证：

1. 地址覆盖率和目标地址活跃率；
2. target-to-target、target-to-unmapped、target-to-contract 的比例；
3. 推文到下一次 ERC-20 event 的滞后分布；
4. 交易对象的候选空间和长尾程度；
5. 时间切分及 next-counterparty baseline。

通过后，再切换 BigQuery/AWS 加入 native ETH、NFT、internal traces，不要一开始就把所有事件类型混在一起。

## 标签与评估建议

### 交易对象定义

不要直接将 `to_address` 全部叫作“交易对象”。建议分层：

```text
counterparty_type = {
  mapped_x_address,       # 对方也是已匹配 X 的地址
  unmapped_eoa,           # 未匹配的外部账户
  contract,               # token/NFT/DeFi/交易合约
  service_or_exchange,    # 可用辅助地址标签标注
  unknown
}
```

预测标签可以按任务拆开：

1. 下一事件的 `counterparty_type`；
2. 下一事件的具体地址（只在活跃地址/候选 top-K 上评估）；
3. 下一 token/contract；
4. 下一日或下一周的交易强度/方向。

### 时间切分

不要随机切边。推荐一年的最初版本：

```text
train: 2021-08-01 ... 2022-03-31
valid: 2022-04-01 ... 2022-05-31
test:  2022-06-01 ... 2022-07-31
```

所有节点影响力筛选、候选节点选择、地址标签统计都只能使用 train/validation 允许看到的历史；不能先用全年的交易次数选出“高影响节点”再回头评测。

## Crosswalk 和可发表性风险

当前 EX-Graph mapping 中的 X node id 是匿名数值 ID；Crypto Influencer 主 CSV 没有 author id/handle，旧伴随文件也没有完整的 `X node id -> TwitterName` crosswalk。当前只能安全地研究：

```text
X-mapped Ethereum address cohort 的交易行为
```

不能直接把每个地址的行为归因给 52 个具体 influencer。除非后续取得独立、可审计的：

```text
Twitter/X author identifier -> EX-Graph X node id -> Ethereum address
```

还要考虑 EX-Graph 是 CC BY-NC-SA 4.0，而外部链上数据的许可不同；原始 tweet 文本也有平台条款。内部研究可以先做，但对外发布派生数据前要分别核对地址映射、tweet、链上数据的许可和再分发条件。

## 最终建议

当前不要再花时间试图从 `ethereum_graph.gpickle` 恢复时间顺序。直接把它降级为：

- 静态图结构/边频次特征；
- 候选影响节点筛选的历史先验（严格按时间切分时重新计算）；
- X 地址匹配的索引。

真正的时间线使用：

1. **BigQuery Blockchain Analytics**：完整版本，论文主线；
2. **Harvard ERC-20 Trading**：6 个月 ERC-20 pilot；
3. **Live Graph Lab**：如果确定做 NFT 版本；
4. **AWS Public Blockchain Data**：无 GCP 时的本地备选。
