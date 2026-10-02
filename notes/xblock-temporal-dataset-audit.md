# XBlock/Kaggle Ethereum Partial Transaction Dataset 审计

更新时间：2026-09-07

## 判断

如果用户所说的 `Temporal Ethereum Transactions` 指的是 Kaggle 上 XBlock 发布的 **Ethereum Partial Transaction Dataset**，那么它有 temporal 字段，但不适合作为本项目主数据源，也不适合与 EX-Graph 的 27,613 个 mapped addresses 做有效 join。

## 数据内容

Kaggle API 当前元数据显示：

- 最后更新：2020-03-23；
- 压缩下载包约 41.6 MB，解压声明大小约 120.9 MB；
- 许可证字段为 `Unknown`；
- 数据来自 Etherscan API；
- 包含 `EthereumG1`、`EthereumG2`、`EthereumG3` 三个以中心账户/K-in/K-out 为条件的局部交易网络。

README 中的 temporal edge list 每行只有：

```text
from_node_num,to_node_num,value,timestamp
```

另有 `addr2Idx.txt` 将数字节点 ID映射回 Ethereum address；预排序 pickle 的字段是：

```text
From, To, Value, TimeStamp
```

因此它可以用于测试“按时间排序的局部边预测”代码，但没有 transaction hash、block number、transaction index、token contract 或 token standard，无法作为完整事件级链上数据。

## 本地审计结果

| 子图 | endpoint nodes | edge rows | 时间范围（UTC） | 与当前 27,613 target addresses 的重叠 | 触及 target 的边 |
|---|---:|---:|---|---:|---:|
| EthereumG1 | 3,832 | 225,714 | 2015-08-07 至 2016-03-29 | 1 个地址映射，但 0 行事件 | 0 |
| EthereumG2 | 10,628 | 222,876 | 2015-07-30 至 2016-08-01 | 1 个地址映射，但 0 行事件 | 0 |
| EthereumG3 | 26,175 | 679,574 | 2015-07-30 至 2016-07-16 | 1 个地址映射 | 10 行（出站 2、入站 8） |

也就是说，虽然 G3 的局部网络有约 2.6 万个 endpoint nodes，但这不是 EX-Graph 的 2.6 万个 mapped addresses；与当前 EX-Graph mapping 实际只有 10 条事件交集。G1/G2 中碰巧存在一个相同地址，但该地址没有出现在对应 edge list 的有效端点事件中。

## 为什么不适合作为本项目数据源

1. 时间范围是 2015--2016，与 Crypto Influencer 数据的 2021--2023 时间范围不重叠；
2. 是中心账户附近的局部子图，不是全 Ethereum temporal transaction table；
3. 当前 EX-Graph target 地址几乎没有有效事件覆盖；
4. 缺少 hash/block/index，无法严格恢复同一区块或同一秒内的顺序；
5. Kaggle 许可证为 Unknown，不宜称为许可证清晰的 open dataset；
6. 没有 token/contract/event type，不能区分 native ETH、ERC-20、NFT 或合约交互。

## 可以怎么用

仅建议用于：

- 检查 temporal link prediction 代码是否能处理逐行 timestamp；
- 做极小规模单元测试；
- 对比旧论文的局部时序图设置。

不建议用于：

- EX-Graph mapped-address 的行为预测；
- Crypto Influencer 推文与交易 join；
- 交易对象预测的正式实验；
- 论文主数据集。

## 文件

原始下载包：

```text
data/raw/ethereum_partial_transaction_dataset.zip
```

可复现审计脚本：

```text
src/audit_xblock_temporal_dataset.py
```

审计结果：

```text
artifacts/ethereum_partial_transaction_audit.json
```
