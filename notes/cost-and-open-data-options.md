# Google BigQuery 成本与开放数据备选

更新时间：2026-09-07

## BigQuery 是否收费

BigQuery Public Dataset 的数据存储由 Google 承担，使用者主要为自己运行的 query 付费。当前官方价格页给出的 on-demand 规则是每个 billing account 每月前 1 TiB query processing free，超出部分按当前价格计费；正式使用前应以控制台和价格页为准。

BigQuery Sandbox 可以不绑定信用卡/结算账号查询公共数据，但有 1 TiB/月免费处理、10 GiB lifetime storage、默认 60 天表过期等限制，并不适合无限量保存完整抽取结果。

查询扫描量和跳板机流量是两件事：扫描在 Google 侧进行，跳板机通常只提交 SQL 和接收结果。应使用 dry-run、maximum bytes billed、目标表和 Cloud Storage export，避免将宽表查询结果直接输出到跳板机。

## 严格开放/免费候选

1. Harvard Dataverse ERC-20 Trading 2015--2024：当前 Dataverse API 版本标记为 CC0-1.0；按月 TSV，字段含 block_id、transaction_hash、time、token_address、sender、recipient、value。2022-02--07 当前压缩文件约 6.71 GB；2021-08--2022-07 约 15.64 GB。只覆盖 ERC-20，没有 transaction_index/log_index。
2. Live Graph Lab：Zenodo 开放 temporal blockchain graph；metadata 压缩包约 5.8 GB，NFT event 语义，代码说明覆盖 2022-08-01 之前的区块，字段含 block/from/to/token/tx hash/value/timestamp。
3. TGS：Zenodo 开放，84 个 ERC-20 token networks，raw zip 约 602 MB；只作为开发 pilot。
4. ERC-20/ERC-721 Transfer Events：Zenodo 开放，覆盖到 2022-06-21；event 文件使用数值 ID 和 lookup，约 11.4 GB，适合旧窗口补充。
5. ERC-1155 Transfer Events：Zenodo 开放，覆盖 2015--2024，事件按时间顺序并含 transaction_index/log_index；只作为 ERC-1155 补充。

## 公共但不应直接等同于开放许可证

AWS Public Blockchain Data 免费公开 S3，按日期提供 Parquet 的 Ethereum blocks/transactions/logs/token_transfers/traces。它很适合完整行为的免费访问和本地/远程查询，但数据使用许可应按 AWS registry 指向的条款单独核对；其文档还注明数据为 experimental。不要因为“无需 AWS 账号”就把它当成与 CC0/CC BY 完全相同的再分发许可。

## 推荐

- 有 GCP：先用 BigQuery Sandbox 做 schema、COUNT、活跃率和 bytes dry-run；如果抽取结果可控，主线继续用 BigQuery。
- 不想付费且先做 ERC-20：Harvard 2022-02--07 六个月 pilot。
- 不想付费且研究 NFT：Live Graph Lab 2022-02--07 六个月 pilot。
- 要 native ETH + traces/logs：AWS Public Blockchain Data，尽量在远端 Athena/云端处理，只下载目标地址过滤后的结果。

严格意义上，目前没有找到一个同时满足“完整 Ethereum native ETH + ERC-20 + ERC-721/1155 + traces/logs、逐事件精确排序、单一开放许可证、可直接下载”的单一数据集。完整方案需要组合多个开放数据源，或使用 BigQuery/AWS 自行抽取。
