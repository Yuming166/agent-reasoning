# 时间交易数据集选择：EX-Graph 地址映射的可行 join 方案

更新时间：2026-09-07

## 0. 先说 join 是否可行

可行。Ethereum 地址字符串可直接规范化为小写后与逐笔交易表的 `from` / `to` 字段 join；不需要使用 EX-Graph 当前发布的聚合 `DiGraph` 重新推断地址。应使用 `vendor/EX-Graph-repo/twitter_matching.csv` 中的地址映射表作为 target-address whitelist。

当前本地文件的实际规模是：27,614 行、27,613 个唯一 `(node_id, ethereum_address)` 映射；有 1 行完全重复。这个数量比“约三万”略少，正式 manifest 应固定为 27,613 个唯一地址。

但要注意，EX-Graph mapping 的 `node_id` 是匿名的数字 X 节点 ID，文件中没有原始 X handle。Crypto Influencer v5 的主 CSV 有 16,512 条 tweet，但列为匿名/空列索引、日期、文本、互动数和情感字段，不包含 `TwitterName` 或作者 ID。伴随的旧 Excel 工作簿包含 `TwitterName`，但没有 EX-Graph `node_id` 的 crosswalk。仅用文本+日期与旧工作簿匹配，本地只解析出 116 条可唯一识别作者的记录，不能当作完整的 influencer-to-wallet crosswalk。

因此：

- **地址到交易事件的 join：可行且直接。**
- **匿名 EX-Graph X 节点到 Crypto Influencer 作者的 join：目前不完整/不可直接完成。**
- 如果目标是“52 个 influencer 的钱包交易行为”，必须另外取得 `TwitterName -> EX-Graph node_id -> Ethereum address` 的 crosswalk；否则只能研究“EX-Graph 中有 X 映射的地址群体”，不能把效果归因到具体 influencer。

## 1. 候选数据集比较

| 候选 | 交易粒度/时间字段 | 覆盖与时间 | 与 EX-Graph join | 适合度 | 主要风险 |
|---|---|---|---|---|---|
| **Google Cloud Blockchain Analytics Ethereum Mainnet** | `transactions` 逐笔；另有 `token_transfers`、`traces`、`logs`；block timestamp、block number、transaction index、hash、from/to | Ethereum 主网持续更新，适合任意 6--12 个月 | 直接按地址 join；可只筛 target addresses | **一般交易研究首选** | 需要 BigQuery/GCP 项目；查询计费；要冻结查询结果；transaction/token transfer/trace 需定义事件单位 |
| **Live Graph Lab / livegraphlab（Zenodo 8267012）** | NFT 事件级原始表：collection address、block number、from/to、token id、transaction hash、value、timestamp | 2017-07-12 至 2022-08-01；约 124M NFT 边/记录；CC BY 4.0 | 直接按地址 join | **若保持 EX-Graph 的 NFT 语义，最匹配** | 只覆盖 NFT 事件，不是全部 ETH/ERC20/contract calls；截止 2022-08-01；同一 transaction hash 可能对应多行 token transfer |
| **TGS raw / Temporal Graph Foundation Models（Zenodo 11480106）** | 每行一个 ERC20 token transaction；`blockNumber,timestamp,tokenAddress,from,to,value,fileBlock` | 多个 ERC20 token 网络；需要按文件实际 timestamp 再冻结窗口；CC BY 4.0 | 直接按地址 join | **小规模 token pilot** | 只有 84 个选定 token，token-selection bias；不是完整 Ethereum；不覆盖 NFT/ETH 全部行为 |
| **ERC-20/ERC-721 Transfer events（Zenodo 10644077）** | Transfer event 级，另有 block timestamp、address/value 文件 | block 0--14,999,999，截止 2022-06-21；CC BY 4.0 | 直接按地址 join | 可做 2021-12-21 至 2022-06-21 的 6 个月 pilot | 不覆盖 2022-06-21 之后；文件总量约 11.4GB 压缩，预处理复杂；不是普通 ETH tx |
| **ERC-1155 Transfer Events（Zenodo 14901528）** | ERC-1155 transfer event，含 tx/block/time 等 | 截止 2024-12-31；CC BY 4.0 | 直接按地址 join | 作为 NFT 补充数据 | 只覆盖 ERC-1155，不能单独代表 NFT 或 Ethereum transaction 行为 |
| **Hugging Face BlockDB Parquet** | 逐笔 external tx；`block_timestamp,block_number,tx_index,tx_hash,from_address,to_address,value_wei,...`；按月分区 | 2015-08 至 2026-06；3.57B 行 | 直接按地址 join，可按月取 | 工程上可用的本地 fallback | 单月 parquet 约 8--13GB；完整下载量很大；dataset card 没有明确开放许可证/独立 provenance，不建议直接作为论文主数据源 |
| **Ethereum Transaction Network（Zenodo 4543269）** | `edges_ts` 含 timestamp、block_num、block_ix；另有 txin/txout 和地址表 | 旧数据，约到 2020 年；CC BY 4.0 | 地址需要先经过 `addresses.dat` ID 映射 | 不建议本项目使用 | 与 2022 EX-Graph / influencer 时间不重叠 |

## 2. 推荐顺序

### 推荐 A：Live Graph Lab 做 NFT 版本的第一版

EX-Graph 论文/数据说明的 on-chain 部分本身围绕 NFT 相关交易，Live Graph Lab 的原始表字段和时间范围与此最接近，而且直接包含 `from/to/timestamp/transaction_hash/token_id/value`。建议使用：

- 6 个月：`2022-02-01 00:00:00 UTC` -- `2022-08-01 00:00:00 UTC`；或
- 1 年：`2021-08-01 00:00:00 UTC` -- `2022-08-01 00:00:00 UTC`。

如果必须和 EX-Graph 论文声称的 `2022-03-01`--`2022-08-31` 对齐，则 Live Graph Lab 只能覆盖到 `2022-08-01`，需要明确写成“六个月/截至 2022-08-01 的窗口”，不能暗称覆盖完整 8 月。

### 推荐 B：Google Cloud Blockchain Analytics 做完整 Ethereum 版本

如果研究问题是“地址的总体交易行为与交易对象”，而不仅是 NFT，应该以 Google Cloud Blockchain Analytics 为主数据源：

1. `transactions`：普通 external transaction 的 hash、from/to、value、block/time、transaction index；
2. `token_transfers`：ERC20/721/1155 等资产转移；
3. `traces`：internal call/value flow；
4. `logs`：需要自行解析的事件。

在 27,613 个目标地址上做 whitelist join，而不是扫描并保存全网结果。需要把 `transaction`、`token_transfer`、`trace` 分成不同事件表，避免把同一个链上动作重复计数。

### 推荐 C：TGS 做低成本 development pilot

如果暂时没有 BigQuery 项目，TGS 的 602MB raw zip 适合先验证：地址 join、时间切分、候选交易对象标签、推文滞后窗口、模型输入格式。但它只能支持选定 ERC20 token 网络，pilot 结果不能外推成完整 Ethereum 交易效果。

## 3. 建议的目标表结构

统一输出一张事件表，但保留事件来源和语义：

```text
event_id
source_dataset
event_type                 # external_tx / token_transfer / trace / nft_transfer
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
matched_x_node_id           # 只有映射到 EX-Graph 匿名 node_id 时填写
```

预测任务建议把 `counterparty_address` 定义为标签，并将：

- `to_address` 的合约地址；
- token transfer 的接收方；
- internal trace 的调用方/接收方；

分开建模，不要混成一个“交易对象”类别。

## 4. 关键方法学约束

- 先用 tweet time 建立 observation window，再取其后的交易窗口；不能用未来交易行为筛选 influencer/高影响地址。
- 地址恒定不等于身份恒定：EOA、合约、交易所归集地址、托管地址和多人共用地址不能直接解释为一个自然人。
- EX-Graph 的 OpenSea matching 是一个地址与 X 账号的匹配证据，不应直接等同于 influencer 的因果身份。
- 先做 descriptive/predictive pilot，再做反事实；“移除一条推文/影响节点”的结果首先是模型反事实，不是因果效果。
- 需要保存 target address list、数据集版本/查询日期、SQL、字段字典、hash 和去重规则。
