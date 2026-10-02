# EX-Graph Ethereum Graph 数据审计笔记

## 2026-09-07：资料核查

官方仓库的 README 将 Ethereum Graph 描述为 2,610,465 个节点、29,585,858 条边，边字段为 `from_address`、`to_address`、`weight`、`block_number`。论文正文把这部分表述为 29,585,858 条 transaction records，并称每笔 Ethereum transaction 携带时间信息；附录同时说明数据从 2022-03-01 到 2022-08-31 过滤，并使用本地 Geth/EVM 解析 block 的 transactions 数组。

但是，官方 `ethereum_graph.gpickle` 文件的前 64 字节已经显示它是 pickle protocol 5 的 `networkx.classes.digraph.DiGraph`，而不是 `MultiDiGraph`。这产生一个必须验证的结构性限制：`DiGraph` 对同一有序地址对 `(from, to)` 只能保存一条边。即使作者的原始交易记录是逐笔解析的，发布的图文件也不能以平行边的形式无损保留同一地址对的多笔交易。

## 审计目标（已完成）

1. `weight` 是转账金额、交易次数、聚合金额，还是其他字段；
2. `block_number` 是一个代表值、最后一笔交易的区块，还是列表/数组；
3. 实际 graph count 是否与 README 的 2,610,465 / 29,585,858 一致；
4. edge attribute 是否包含 README 所列全部字段；
5. 是否能在发布文件内恢复 `(from, to, block_number, transaction_hash/index)` 级事件序列。

审计结果已写入 `artifacts/ethereum_graph_audit.json`。结论应区分：

- **可以确认**：对象类型是否支持平行边、发布文件中实际保存的字段类型；
- **不能仅凭图确认**：同一地址对的历史交易次数、交易哈希、同一区块内交易顺序；
- **后续建模建议**：若缺少逐笔事件，使用图做静态关系/影响力候选筛选；预测行为时用交易事件表作为时间序列输入，严格按时间切分，避免未来信息泄漏。

## 2026-09-07：官方链接文件的本地二进制结果

已从 README 的 Ethereum Graph Google Drive 链接下载 `ethereum_graph.gpickle`，文件大小为 11,616,467,480 bytes；pickle 可在 `networkx==3.6.1`、`numpy==2.5.3` 环境中成功加载。审计结果保存在 `artifacts/ethereum_graph_audit.json`。

实际结果：

- 类型：`networkx.classes.digraph.DiGraph`；`directed=True`、`multigraph=False`；
- 节点/边：`1,810,641 / 11,876,618`，与 README 表格中的 `2,610,465 / 29,585,858` 不一致；
- edge keys：只有 `weight`，所有边都有；`block_number` 缺失率为 100%；
- `weight`：整数，min=1、median=1、max=17,173、mean=1.3475589599665494、sum=16,004,443；
- 1,079,058 条边的 weight > 1，说明同一有向地址对存在频次型聚合；
- 因为是 `DiGraph`，同一有向地址对不能有平行边。

**数据使用结论：** 当前下载文件不是逐笔交易表。它是静态的、按 `(source, target)` 聚合的加权有向图；`weight` 很可能表示交易次数/边 multiplicity，而不是交易金额，但官方 README 没有明确写出构造语义，所以论文中应写成“基于二进制审计推断的计数型权重”，并保留这一不确定性。由于没有 block/timestamp/tx hash/transaction index，无法从该文件恢复顺序、同一地址对的逐笔时间线，也不能做严格的 next-transaction prediction。

**版本一致性风险：** README 的 schema 与其 Google Drive 当前返回的对象不一致，且 Google Drive 响应的 `Last-Modified` 为 `Sat, 19 Aug 2023 07:50:22 GMT`，仓库快照 commit 为 `298a52564f5d7f8e30f7f8e6919ae1b3168db481`（2024-09-30）。在正式研究中应固定数据文件 SHA-256、下载日期、节点/边数和 edge-key 集合，并把 README/Drive mismatch 作为数据审计结果。
