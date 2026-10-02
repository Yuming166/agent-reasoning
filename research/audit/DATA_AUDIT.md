# DATA_AUDIT.md — Group 0 数据与泄漏审计（Phase I 前置门槛）

- 角色: Group 0 — Data & Leakage Audit
- 审计日期: 2026-09-11（UTC+8；BigQuery 时间均为 UTC）
- 审计对象: `/storage/gaoym/ex-graph-microtransaction-analysis`（本机 cloud82, 10.63.0.82）
- 依据方案: `research/autoresearch_phase1.md` §5 Group 0
- 结论: **通过（有条件）** — 数据契约与时间协议已按实况核验；发现的 1 处表 schema 不一致、
  2 处候选集/标签口径注意事项与 1 处静态特征边界必须在 `temporal_protocol.yaml` 冻结后使用。

## 1. 审计方法与证据约定

- 连接: BigQuery REST/`google-cloud-bigquery` 3.45.0（`.venv-cuda`），
  经代理 `http://10.63.0.72:7890` + ADC
  （`GOOGLE_APPLICATION_CREDENTIALS=/home/gaoym/.config/gcloud/application_default_credentials.json`），
  项目 `ictdata-507912`、数据集 `exgraph`、位置 US。
- 每个结论标注证据等级:
  - **已实测** = 本次会话内用元数据 REST API 或带 bytes-billed 上限的有界查询直接验证；
  - **元数据** = BigQuery 表/分区元数据（`INFORMATION_SCHEMA.PARTITIONS`、`get_table`）返回的
    `num_rows`/`size_bytes`/分区范围/创建时间，非全表扫描；
  - **已记录** = 项目既有 manifest/审计产物（`artifacts/`、`data/metadata/`）记录的先前实测结果，
    本次会话复核了关键 hash 或结构一致性；
  - **无法验证** = 本次会话未能独立确认（列出原因）。
- 查询纪律: 分区表一律带 `block_timestamp`/`snapshot_date`/`month` 分区谓词；
  每次查询均设 `maximumBytesBilled`（本次审计单次上限 100MB~5GB，实际单次计费以 job 输出为准），
  不整表导出。审计运行器: `research/audit/audit_query.py`（只读查询，不改任何表）。

## 2. 数据契约逐项核验（BigQuery 实况）

### 2.1 目标地址与官方匹配维表

| 表 | 行数 | 唯一 address | 唯一 node_id | 地址格式 | 证据 |
|---|---:|---:|---:|---|---|
| `target_addresses` | 27,613 | 27,613 | 27,613 | 全部 42 字符（0x+40 hex） | 已实测（job 3f17f524-7a69-4c54-bdcf-982d8501a478, bytes_billed≈21MB） |
| `exgraph_x_matches_v1` | 27,613 | 27,613 | 27,613 | 全部 42 字符 | 已实测（同 job）；创建 2026-09-07T15:22:22Z |

- 两者 address↔node_id 一一对应，无重复。`exgraph_x_matches_v1` 仅含 `ethereum_address, exgraph_node_id`
  两列（元数据），**不含** X 原始账号/推文（已记录：匹配源 `twitter_matching.csv` sha256
  `1d2e3d5a0dbf44797a2026ac9cdb23b76f20e227630c90393e80f00172c9b5ba`，27,613 行）。

### 2.2 事件表（dev 窗口 2022-03-01..2022-09-01，holdout 窗口 2022-09-01..2022-10-01）

| 表 | 行数 | 逻辑字节 | 分区 | require_partition_filter | 创建时间(UTC) |
|---|---:|---:|---|---|---|
| `external_transactions_20220301_20220901` | 2,877,009 | 729,336,363 | DAY(block_timestamp) | **true** | 2026-09-07T12:46:34 |
| `token_transfers_20220301_20220901` | 4,275,544 | 1,164,125,153 | DAY(block_timestamp) | **true** | 2026-09-07T12:46:44 |
| `internal_traces_20220301_20220901` | 4,478,515 | 1,229,594,363 | DAY(block_timestamp) | **true** | 2026-09-07T12:49:36 |
| dev 合计 | **11,631,068** | 3,123,055,879 | — | — | — |
| `external_transactions_20220901_20221001` | 333,303 | 84,253,496 | DAY(block_timestamp) | **true** | 2026-09-09T08:38:01 |
| `token_transfers_20220901_20221001` | 497,746 | 135,869,859 | DAY(block_timestamp) | **true** | 2026-09-09T08:38:08 |
| `internal_traces_20220901_20221001` | 571,343 | 157,156,119 | DAY(block_timestamp) | **true** | 2026-09-09T08:38:15 |
| holdout 合计 | **1,402,392** | 377,279,474 | — | — | — |

- 行数来源: 元数据 REST `get_table`（已实测，落盘 `research/audit/bq_metadata_2026-09-11.json`）。
- 过滤语义（已记录，SQL 见 `artifacts/google_event_prep_2022-03_2022-09.json` 内嵌 SQL）:
  `from_address` 或 `to_address` 至少一方命中 27,613 个映射地址即保留；另一方即使未映射也保留
  （`(a_from.address IS NOT NULL OR a_to.address IS NOT NULL)`）。这是"至少一端匹配"，不是"双方匹配"。
- 窗口边界（已实测，job 336cd1b0-2e3c-4468-8aa1-8f13483f0dec / c96fee82-e179-439a-9507-06782a61f06e，
  单日分区扫描）:
  - dev 首分区 2022-03-01: 三族最小 `block_timestamp` 均为 `2022-03-01 00:00:18+00`，
    末分区 2022-08-31 最大均为 `2022-08-31 23:59:35+00` ⇒ 窗口 `[2022-03-01, 2022-09-01)` 成立。
  - holdout 首分区 2022-09-01 最小 `2022-09-01 00:00:03+00`，末分区 2022-09-30 最大
    `2022-09-30 23:59:59+00` ⇒ 窗口 `[2022-09-01, 2022-10-01)` 成立。
- 分区覆盖（元数据 `INFORMATION_SCHEMA.PARTITIONS`，job edcb5284-b203-45b1-afe8-962db26455bb）:
  - dev 三表 + dev 序列表均为 184 个日分区（20220301..20220831），无缺口；
  - holdout 三表 + holdout 序列表均为 30 个日分区（20220901..20220930），无缺口；
  - dev 与 holdout 分区范围**严格不重叠**（dev 最大 20220831 < holdout 最小 20220901）。
- 抽查质量（已记录，2026-09-07 `google_event_prep_quality_*`）: 三表 transaction_hash 无空值、
  每行至少一端命中 EX-Graph；token 表 `removed=true` 为 0；trace 表保留 122,317 行带 `error`。
  dev/holdout 事件表 schema 完全一致（已实测：external/token/trace 三族 dev vs holdout 字段集相等）。

### 2.3 方向化序列表与统一视图

| 表/视图 | 行数 | 逻辑字节 | 分区 | require_partition_filter |
|---|---:|---:|---|---|
| `target_event_sequences_20220301_20220901` (表, dev) | 11,836,196 | 5,095,709,899 | DAY(block_timestamp) | **true** |
| `target_event_sequences_20220901_20221001` (表, holdout) | 1,428,845 | 615,740,888 | DAY(block_timestamp) | **true** |
| `target_event_sequences_20220301_20221001` (视图) | 逻辑 13,265,041 | 0（视图） | 无（逻辑） | 无 |
| `target_events_20220301_20220901` (视图) | 逻辑 11,631,068 | 0（视图） | 无（逻辑） | 无 |

- 语义（已记录 + 已实测）: 每个命中端点生成一条 target/counterparty 有向角色行；两端都命中且不同
  地址 ⇒ 2 行；self 交易 ⇒ 1 行；无目的地址行保留且 `counterparty_present=false`（下一对手方标签必须排除）。
  `sequence_role`: external_tx/token_transfer = primary，internal_trace = auxiliary。
- 排序（已记录）: `target_sequence_index` 按 block_timestamp, block_number, transaction_index,
  event_family_order, event_index/trace_address, direction, counterparty, transaction_hash 确定性生成；
  同一交易内跨事件族顺序只是确定性 tie-breaker，**不是** canonical EVM 事件顺序。
- 视图可查性（已实测，job e5f2f3f5-74b0-4f15-9e59-0b90e9b826e9）: 组合视图 2022-09-01 单日返回
  44,146 行（= holdout 序列表该日角色行数），`target_events` 视图 2022-08-31 单日返回 44,275 行。

### 2.4 ⚠️ 已发现的 schema 不一致（dev vs holdout 序列表）

| 列 | dev `target_event_sequences_20220301_20220901` | holdout `target_event_sequences_20220901_20221001` |
|---|---|---|
| `trace_address` | **INTEGER, mode=REPEATED**（数组，如原始 trace 路径） | **STRING**（`TO_JSON_STRING` 序列化，如 `"[0,0,0]"`） |

- 已实测（`get_table` schema mode）: dev 为 `ARRAY<INT64>`，holdout 为 `STRING`。
  dev 表构建 SQL（`create_exgraph_sequence_tables_ictdata.sql`）直接透传 trace_address 数组；
  holdout 表构建 SQL（`create_sequence_202209_table_ictdata.sql`）对 trace 族做了 `TO_JSON_STRING`。
- 影响: 直接 `UNION ALL` 两表会类型冲突；组合视图 `target_event_sequences_20220301_20221001`
  已用 `COALESCE(TO_JSON_STRING(...),'')` 统一为 STRING。**协议要求跨窗口统一用组合视图或显式 CAST**。
- 该列仅用于排序 tie-breaker 与 trace 明细，不参与特征数值；对特征一致性影响低，但必须冻结处理方式。

### 2.5 as-of 特征与标签表

| 表 | 行数 | snapshot 分布（已实测 GROUP BY） | 创建时间(UTC) |
|---|---:|---|---|
| `wallet_asof_features_v1` | 78,786 | 2022-05-01:19,649 / 06-01:20,341 / 07-01:19,734 / 08-01:19,062 | 2026-09-08T15:49:36 |
| `wallet_asof_features_20220901` | 18,519 | 仅 2022-09-01:18,519 | 2026-09-09T08:51:01 |
| `wallet_importance_ranking_v1` | 60,260 | 2022-05-01..2022-08-01（4 snapshot） | 2026-09-08T15:51:39 |
| `wallet_future_headroom_v1` | 40,036 | 06-01:14,189 / 07-01:13,243 / 08-01:12,604 | 2026-09-08T16:46:57 |
| `p1_wallet_icf_v2` | 17,433 | 06-01:6,733 / 07-01:5,731 / 08-01:4,969 | 2026-09-08T16:45:55 |
| `p2_trigger_v2` | 42,871 | 06/07/08-01（3 snapshot） | 2026-09-08T16:46:50 |
| `router_dataset_v1` | 59,137 | 06-01:20,341 / 07-01:19,734 / 08-01:19,062 | 2026-09-08T16:47:33 |
| `selection_eval_v1` | 14,386 | 仅 2022-08-01 | 2026-09-08T15:54:57 |
| `llm_panel_events_v1` / `llm_panel_events_20220901` | 3,000 / 1,000 | 06/07/08-01 / 09-01 | 2026-09-09 |

- **as-of 语义（代码审查 + 实况佐证）**: `wallet_asof_features_20220901` 构建 SQL
  （`src/sql/create_wallet_asof_features_202209_ictdata.sql`）:
  - 特征 `*_90d` 仅用 `[snapshot-90d, snapshot)` 的 primary 事件（`block_timestamp < snapshot` 严格小于）；
  - 标签 `fwd30_*` 仅用 `[snapshot, snapshot+30d)`；
  - 实测: 18,519 行全部 `evt_cnt_90d >= 1`（`zero_feat_evt=0`，min=1, max=241,523；job b9ece8a0），
    14,170 行有 fwd30 标签事件，10,585 行 `fwd30_new_cp>0`。
  - `wallet_asof_features_v1` 同构（4 个 snapshot，SQL 相同），只读 dev 序列表（无 holdout 泄漏）。
- **P3 排名表注意事项**: `wallet_importance_ranking_v1` 的 `importance_proxy_p3` 使用**同一 snapshot
  的 fwd30 标签**（未来 30 天新对手方 × 历史熵）做排名演示（`artifacts/wallet_selection_baseline_eval_2022-08.json`
  boundaries 已明示）。这是"未来标签参与演示排序"，**不是无泄漏的选择器**；生产 router 必须用更早 snapshot
  训练并在冻结 snapshot 评估（`router_dataset_v1` 已按 06 训练/07 验证/08 冻结测试构建）。
- **P1/P2 边界（已记录）**: `p1_wallet_icf_v2` 按 snapshot 生成（as-of）；`p2_trigger_v2` 42,871 行中
  36,293 行 `trigger_score_p2` 为 NULL（正滞后相关不足 24 小时的 wallet 按设计为 NULL，已实测）；
  二者均为 proxy，不是因果影响力（方案 §2）。

### 2.6 候选排序样本表 `nc_ranker_samples_v2`（支持集与 sentinel 审计）

- 行数 28,472,717；分区 3 个 snapshot（2022-06-01 / 07-01 / 08-01），约 4.55GB（元数据）。
- 构建语义（已记录，`src/pipeline/build_rankertables.py`）:
  - 每个 snapshot: 历史窗口 `[snap-90d, snap)`（strictly before），正样本 = snapshot 月内"新"出向
    primary 事件（90 天内未见过的 u→v）；负样本 = 从历史窗口全球流行度 top-2000 地址中确定性采样 49 个
    非邻居（`FARM_FINGERPRINT` 模 40）。
  - `g_rank` = 该候选在历史窗口全球入向量的 ROW_NUMBER 排名；候选不在 `gpop`（历史窗口零入向量）⇒
    `g_rank = 99999`（sentinel）。`g_cnt/personal_cnt/days_since/bridge_paths/bridge_signal` 均由
    snapshot 前事件计算 ⇒ **特征层无未来泄漏（已记录，SQL 审查）**。
- 实况（已实测，job 942d0731 / 34442906 / e5f2f3f5）:

| snapshot | 总行 | 正样本 | 负样本 | g_rank=99999 且 label=1 | g_rank=99999 且 label=0 |
|---|---:|---:|---:|---:|---:|
| 2022-06-01 | 10,113,299 | 203,133 | 9,910,166 | 110,236 | 0 |
| 2022-07-01 | 9,787,159 | 196,345 | 9,590,814 | 96,847 | 0 |
| 2022-08-01 | 8,572,259 | 171,700 | 8,400,559 | 84,989 | 0 |

- **支持集口径（重要，非泄漏但必须分开报告）**: 所有 sentinel（g_rank=99999）都落在正样本上 —— 即
  "真实下一对手方在历史窗口全球入向量支持之外"（6/7/8 月分别占正样本 54.3%/49.3%/49.5%）。
  负样本全部有真实 g_rank。另有 g_rank ∈ (99999, max]（真实排名 >99999）与 g_rank<99999 的行
  （8 月 max g_rank=212,053，已实测）。**MRR/Recall@K 必须区分 "supported-pool"（正样本在候选支持内）
  与 full-vocabulary 两种口径**；历史 `artifacts/nc_v1/RESULTS.md` 已记录 naive 0.896 MRR 系支持集
  假象，诚实 supported-pool 结果 MRR 0.448/0.456（全局/学习排序）。本审计沿用该边界。

### 2.7 本地静态/外部数据

| 数据 | 路径 | 核验结果 | 证据 |
|---|---|---|---|
| EX-Graph 静态图 | `data/raw/ethereum_graph.gpickle`（11,616,467,480 B） | sha256 **已实测** `27c86772e260291863f2d39fe475840b8ef0bcb54d198cea344f8f8f682d5db2`（与 `data/metadata/ethereum_graph_sha256.txt` 一致）；图为有向 `DiGraph`，1,810,641 节点 / 11,876,618 边，边仅 `weight`，无 `block_number`（已记录，2026-09-07 全量实载审计 `artifacts/ethereum_graph_audit.json`；文件字节一致 ⇒ 计数仍有效） | hash 本次复核；结构=已记录 |
| 社交推文 | `data/raw/crypto_influencer_v5/dataset_52-person-from-2021-02-05_2023-06-12_21-34-17-266_with_sentiment.csv` | **已实测**: 16,512 数据行（wc 62,714 行含多行字段），时间范围 2021-02-01..2023-06-12（排序后 min/max）；sha256 `3cd10be6ff4d806e889093868fd511c1f60c8f6434e4257c45e4787999b51a9e` 与记录一致；**无 author/author_id/TwitterName 列**（列: created_at, favorite_count, full_text, reply_count, retweet_count, clean_text, importance_coefficient, importance_coefficient_normalized, new_coins, scores, compound, sentiment_type） | 已实测 |
| 社交伴侣 XLS | `.../unpacked/tweets-data.xls` | 已记录: 含 TwitterName，但无 EX-Graph node_id 交叉映射；**本次未复验**（需 xlrd，未安装） | 已记录/无法验证(本次) |
| ETH 分钟价格 | `data/raw/prices/ethusd_1min_ohlc.csv`（232,156,719 B） | **已实测**: 4,768,412 分钟行，2017-08-16 16:45:00Z..2026-09-10 02:24:00Z；研究窗口 2022-02-01..2022-10-01 覆盖 348,480/348,480 分钟=100%，零 >60s 缺口，时间戳单调；sha256 `faa76408c784977b78a51ae8beb9c9bdb768ae3e95cbce3f30b7940b14418e73` 与 manifest 一致 | 已实测 |
| ETH 日线/宏价格 | `data/raw/prices/eth_1d_ohlc.csv`、`prices.csv`、`prices_full.csv`、`token_map.csv` | 日线 3,313 行（2017-08-16..2026-09-10，manifest）；token_map 5 个可计价 token（WETH/USDC/USDT/DAI/APE，decimals 取自链上），另有 LOOKS/WOOL/STRONG/STRNGR/ASH 无价格 | 元数据/已记录 |

- **社交数据泄漏标注（必须遵守）**: 推文时间覆盖 2021-02..2023-06，**跨出**研究窗口；CSV 无作者→钱包映射，
  不能把 influencer 推文当作"钱包主人的推文"或"钱包意图证据"。只能作为资产/市场级外部上下文，且**按 cutoff
  as-of 过滤（只可用 ≤ t 的推文）**。X 图（`data/raw/x_graph/twitter_graph.pkl`，1,103,509 节点/
  3,768,281 有向关注边，已记录）为匿名 X 侧图，**无 eth_node_id↔x_node_id 可信 crosswalk**（已记录，
  2026-09-08 crosswalk 审计）。
- **静态图时序边界（必须遵守）**: `ethereum_graph.gpickle` 是聚合权重静态图，边无 block_number/时间戳，
  无法恢复逐笔顺序；**不能**作为时序事件源，只能作为静态拓扑先验（`exgraph_structural_features_v1` 27,613 行
  degree/PageRank 为全窗口静态特征，是 selection prior，不是 as-of 预测特征）。
- **价格数据泄漏标注（必须遵守）**: 价格文件覆盖到 2026-09-10，远超研究窗口；任何价格特征在 cutoff t 处
  只可用 `timestamp <= t` 的价格（as-of join），否则未来价格泄漏。

## 3. 泄漏专项

### 3.1 dev/holdout 边界
- 已实测: dev 事件/序列表分区 20220301..20220831，holdout 分区 20220901..20220930，无重叠无缺口。
- 冻结切分（已记录 + 代码核验）: 开发窗口 `[2022-03-01, 2022-09-01)`；
  wallet/importance/router 表按 2022-05-01..08-01 月度 snapshot 构建；`router_dataset_v1` =
  06-01 训练 / 07-01 验证 / 08-01 冻结测试；最终未触碰 holdout = snapshot 2022-09-01 + 标签
  `[2022-09-01, 2022-10-01)`（即 holdout 事件表）。

### 3.2 重复与未来派生特征
- 事件表按 `transaction_hash` 不去重（token/trace 为 event-level，同 hash 多行是语义，非重复；已记录）。
- as-of 特征表 `*_90d` 全部严格 `[snap-90d, snap)`；标签 `fwd30_*` 严格 `[snap, snap+30d)`；
  特征与标签分列，未发现特征引用标签列（代码审查 `create_wallet_asof_features_*_ictdata.sql`）。
- **发现（低危，已记录）**: `wallet_asof_features_20220901` 的目标池 `targets` 来自 Mar-Oct 组合视图
  （含 9 月未来事件）的 distinct target。实际影响为零: 表内每行都必须有 90 天窗口特征事件
  （实测 `evt_cnt_90d>=1` 全部满足），而 90 天窗口 `[2022-06-03, 2022-09-01)` 完全在 cutoff 之前；
  因此"仅因未来活动入选"的 wallet 不可能出现。协议仍建议后续快照把目标池改为 `< cutoff`。

### 3.3 label 泄漏
- 无: 训练/验证/测试行的标签窗口均在 snapshot 之后；Aug 冻结测试标签 `[2022-08-01, 2022-09-01)`
  在 dev 内；Sep 最终 holdout 标签 `[2022-09-01, 2022-10-01)` 在 holdout 内，且 Sep 特征构建不读
  fwd 窗口。
- 注意事项: `wallet_importance_ranking_v1` 的 P3 演示排名使用同 snapshot 的 fwd30 标签（见 §2.5），
  只能作为"事后演示/ oracle 边界"，不能作为该 snapshot 的无泄漏选择器。

### 3.4 静态/未来特征
- `exgraph_structural_features_v1`（全窗口 degree/PageRank）与 `ethereum_graph.gpickle` 均为全窗口静态，
  只作先验/基线，不得作为 cutoff 处 as-of 预测特征（已记录；协议强制）。
- `nc_ranker_samples_v2` 特征全部为 snapshot 前（已记录 + 实况 sentinel 分布佐证）。

### 3.5 per-cutoff 图统计（元数据，已实测 `INFORMATION_SCHEMA.PARTITIONS`）
dev 逐月事件行数:

| 月 | external | token | trace | 序列表(角色行) |
|---|---:|---:|---:|---:|
| 2022-03 | 579,330 | 1,034,300 | 895,843 | 2,558,374 |
| 2022-04 | 560,655 | 918,296 | 871,828 | 2,389,035 |
| 2022-05 | 515,367 | 811,461 | 786,505 | 2,147,791 |
| 2022-06 | 423,718 | 499,932 | 628,820 | 1,576,649 |
| 2022-07 | 436,591 | 513,009 | 691,835 | 1,672,437 |
| 2022-08 | 361,348 | 498,546 | 603,684 | 1,491,910 |
| dev 合计 | 2,877,009 | 4,275,544 | 4,478,515 | 11,836,196 |

holdout 2022-09: external 333,303 / token 497,746 / trace 571,343 / 序列表 1,428,845。

as-of 活跃钱包数（有 ≥1 个 90 天 primary 事件）: 05-01:19,649 / 06-01:20,341 / 07-01:19,734 /
08-01:19,062 / 09-01:18,519（已实测，随行数单调递减，与方案 §20 预算漏斗一致）。

### 3.6 可复现快照
- 工作目录非 git 仓库（已实测 `git rev-parse` 失败）；可复现发布仓库
  `/home/gaoym/agent-reasoning-publish-20260907` 当前 main HEAD =
  `35f294bb7d0b223eafd2f0f1ee93f6558670a624`（已实测 2026-09-11）。
- BigQuery 对象清单 + 创建时间 + 行数: `research/audit/bq_metadata_2026-09-11.json`（本次生成）。
- 历史构建 job 证据（已记录）: external CTAS `job_wDlAf8KR5DT-AmjXucoAmbbuumc3`
  （billed 48,076,161,024 B）；sequence CTAS `job_M_9CsnopVIaacN8DAHtATutjbTDO`
  （billed 3,125,805,056 B）；mapping 上传 `job_kiIMZPtSCDU8GT6R53Ceg3fTkP_y`。
- 本地文件 hash: gpickle / influencer CSV / 1min 价格本次均已实测并与记录一致（见 §2.7）。

## 4. 无法验证 / 未覆盖项（必须在后续阶段显式声明）

1. **链上源表完备性**: `bigquery-public-data.goog_blockchain_ethereum_mainnet_us` 为数据源，未与
   外部区块浏览器独立交叉校验（无法验证；可信度依赖 Google 公共数据集）。
2. **`twitter_matching.csv` 的来源正确性**: 27,613 条匹配为官方发布文件内容，未与作者原始抓取流程
   独立复现（已记录，无法验证）。
3. **社交 CSV 的 sentiment/importance_coefficient 派生口径**: 由数据集提供，未复现（无法验证）。
4. **XLS 伴侣文件作者列**: 本次未复验（需 xlrd）；沿用 2026-09-07 记录（含 TwitterName，无 crosswalk）。
5. **静态图 weight 聚合代码**: EX-Graph 未发布 weight 构造代码，聚合语义为推断（已记录，无法验证）。
6. **图计数本次未重载**: gpickle 11.6GB 未重新 pickle 加载；因 sha256 完全一致，沿用 2026-09-07
   全量实载审计计数（已记录）。
7. **p2_trigger_v2 的 NULL 语义**: 36,293/42,871 行 `trigger_score_p2` 为 NULL（设计如此），
   下游使用必须显式处理 NULL（已实测分布，语义见 SQL）。

## 5. 审计结论

- 数据契约行数、窗口、分区、过滤语义、as-of/标签窗口、社交与价格时序、静态图边界均已按实况核验，
  与方案 §3 声称的 27,613 地址 / ~11.63M dev 行 / ~1.4M holdout 行一致。
- 需冻结的 4 项口径: (1) 序列表 trace_address 类型不一致 ⇒ 统一走组合视图或显式 CAST；
  (2) nc_ranker 支持集 vs full-vocabulary 分开报告（sentinel g_rank=99999 全在正样本）；
  (3) P3 同 snapshot fwd30 排名仅演示、非无泄漏选择器；router 用 06 训练/07 验证/08 冻结测试；
  (4) 静态图特征与未来价格/推文不得进入 as-of 预测特征。
- 时间协议以 `research/audit/temporal_protocol.yaml` 冻结；本审计通过，后续任何结果必须引用该协议。
