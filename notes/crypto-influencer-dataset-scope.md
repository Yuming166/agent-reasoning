# Crypto Influencer dataset scope check

The public dataset commonly described as a crypto-influencer dataset is the Mendeley package `Database of influencers' tweets in cryptocurrency (2021-2023)`, DOI `10.17632/8fbdhh72gs.4` (and later versions under the same dataset DOI). The public description says the collection covered over 50 experts / 52 influential accounts and that the 52-account tweet data spans February 2021 to June 2023; the version-4 description also calls the initial collection an eight-month collection. This is not, as stated, an unambiguous six-month panel.

Before joining it to EX-Graph, record the exact downloaded file/version and the actual `created_at` min/max. If the intended input is a six-month subset, freeze the subset boundaries in a manifest rather than relying on the package name.

## 2026-09-07：本地版本 5 审计

已下载 Mendeley dataset `8fbdhh72gs`, version 5 的 52-person CSV。文件有 16,512 行，日期范围为 2021-02-01 至 2023-06-12。主 CSV 的列为匿名/空列索引、`created_at`、互动数、文本、情感字段等，不含 `TwitterName` 或 author ID；空列索引在文件内每行唯一，更像原始行标识而非作者键。

同版本附带的旧 `tweets-data.xls`/`tweets1` 工作表包含 `TwitterName`，但没有 EX-Graph `node_id` 到 TwitterName 的映射。用 tweet 文本和日期跨文件匹配，只能唯一恢复 116 条 v5 行的作者信息，不能解决完整 crosswalk。因此在当前数据条件下，不能把 EX-Graph 中的匿名 X 节点安全地标成 52 个具体 influencer。
