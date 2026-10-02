# ENS 链上 address↔X handle 交叉表试点（2026-09-24）

目标：不用任何 X/LLM API，验证"钱包地址 ↔ 社交账号"能否从链上公开证据可靠建立，
作为"用 2026 年信息重造数据"计划的第一步可行性检查。

## 方法（全部链上数据 + 本地脚本）

- 事件源：`bigquery-public-data.crypto_ethereum.logs`（已验证更新至 2026-09-24 当天）。
- 扫描 4 个 ENS Public Resolver（0x5ffc0143…、0x226159d5…、0x4976fb03…、0x231b0ee1…），
  2019-11-01 起，4 种事件：TextChanged(3参/4参)、AddrChanged、AddressChanged。
- topic0 用本地 eth_utils.keccak 计算（已装 pycryptodome/eth-utils 到 .venv-cuda）。
  注意：现行 resolver 同时发出 3 参 `TextChanged(bytes32,string,string)`
  (0xd8c9334b…) 与 4 参 (0x448bc014…) 两种；我先前凭印象给的 topic 是错的，以本地计算为准。

## 产物

- BigQuery：`ictdata-507912.exgraph.ens_resolver_events_v1`（3,710,859 行，1.34 GiB，
  按 DATE(block_timestamp) 分区、resolver/topic0 聚簇，后续查询近零成本）；
  `exgraph.ens_address_handle_latest_v1`（15,306 行 address↔handle 最新映射）。
- 本地 `artifacts/ens_x_crosswalk/`：textchanged_raw.parquet（594,682 行）、
  textchanged_twitter.parquet（57,382 行 twitter 类 key）、addrchanged_latest.parquet
  （2,715,780 节点最新地址）、address_handle_crosswalk_latest.csv、exgraph_overlap_pairs.csv。
- 成本记录：CTAS 一次性扫描 bytes_billed=3,248,972,890,112（≈2.95 TiB ≈ $18.9，
  上限 3.3 TiB）；2026 活跃度检查 56.7 GB（≈$0.35）。dry-run 先行。

## 关键数字

- TextChanged 事件 594,682；其中 twitter 类 key（com.twitter/twitter/com.x/x）57,382 条、48,088 节点。
- 解码 0 失败；规范化 handle（去 URL/@ 前缀）后 16,982 节点有有效最新 handle。
- 与最新 AddrChanged 连接 → 16,789 节点、**15,306 个唯一地址 ↔ 15,042 个 handle**（链上自我声明 + 时间戳）。
- handle 记录写入年份分布：2023:6,160 / 2024:5,975 / 2025:4,279 / 2026:375。
- **2026 年至少有 1 笔主网原生交易（from 或 to）的 ENS-tagged 地址：7,445**。
- 与 EX-Graph `twitter_matching.csv` 27,613 地址的交集只有 **157**——ENS 路线基本是
  一套新种子，不是对原映射的恢复。

## 边界（不得夸大的部分）

- ENS 文本记录是**链上自我声明**：强于昵称相似度，但不等于该人控制 X 账号；
  双向验证（账号侧提及地址/ENS）尚未做，需要 X 侧数据。
- 仅覆盖 4 个公共 resolver；自建 resolver 的文本记录未收。
- 交叉表是"最新状态"；**时间正确性（as-of join）必须用完整事件历史重建**，
  ENS 域名易手后 handle 与 address 的对应关系可能失效，后续分析需按记录时间截断。
- 未含 X 侧任何内容（推文、关注）；X 历史推文获取仍是独立的权限/预算决策点。

## 下一步候选

1. 对 7,445 个 2026 活跃地址跑现有 BigQuery 事件管线（2026 窗），估计每地址事件量与
   候选池规模 → 决定试点样本量。
2. 抽样 100 对人工核验 handle 在 X 上是否存在且与地址声明一致（只读公开页面，不用 API）。
3. 决定 X 数据获取路径：免费只读抓取 / 付费 full-archive 搜索 / 放弃文本只用关注快照。

---

## 2026-09-24 下午：双向校验 + 分层抽样 + 事件量分布（应 ChatGPT 三条要求）

### A. ENS 官方双向校验（反解 → 正解回指）

- 补扫物化 `exgraph.ens_reverse_evidence_v1`：候选地址反向节点上的 NameChanged
  （16,412 事件 / 12,789 节点）与 ReverseClaimed（17,599 事件 / 13,111 地址）。
  bytes_billed=3,192,413,749,248（≈$19.9）。本地 namehash 已用 `eth` 的已知值校验。
- 判定：reverse_claimed ∧ 反解名字的 namehash == 持有 twitter 记录的节点 ∧ 该节点
  最新 AddrChanged == 原地址，三条全过记为 bidirectional_ok。
- **计数口径（三种分母）**：16,532 个唯一 (address,node) 对（=frame 中唯一 ENS 节点数）；
  15,303 个唯一地址；15,669 个唯一 (address,handle) 对。
  - 对级：12,040 / 16,532 = 72.8% 通过；4,492 对仅正向（含冒名指向，如零地址、WETH、
    交易所热钱包被他人 ENS 指向）。
  - 地址级：12,040 个地址至少有一对通过（78.7%），3,263 个地址仅正向，368 个地址同时
    有两类对（一个名通过、另一个未通过）——对级分组在地址级**不互斥**。
  - 通过校验的对覆盖 11,664 个唯一 handle。
- 边界：reverse_claimed 用 ReverseClaimed 事件近似（topic1=claimant），未逐笔核对
  交易发送者；namehash 只做 lowercase，未做完整 UTS-46 规范化；校验基于"最新"记录，
  历史 as-of 有效性与域名易手需用事件流重建。

### B. 100 对分层核验样本（`artifacts/ens_x_crosswalk/verification_sample_v2.csv`）

- 分层维度：记录新旧（≤2023/2024/2025-2026）× 2026 活跃度（0 / 1-50 / >50 事件）
  × handle 共享性（一对多/一对一）；seed 固定可复现。
- 发现：最新 twitter 记录 100% 落在 2023 版 resolver 上，旧 resolver 只存在于历史
  事件中，故"按 resolver 分层"退化为历史记录问题，已在笔记中说明。
- 最终样本 71 个 bidirectional_ok + 29 个 forward_only（用于覆盖失败模式）。
- 工作表含待人工填写列：x_account_exists、verification_status
  （account_confirms / ens_only / unverifiable / conflict）、evidence_date、
  evidence_note；另附 x_profile_url、链上证据 tx_hash、reverse_name。
- 人工核验（打开 X 页面逐对确认）需人执行；我没有用 X 页面抓取或 API。

### C. 按任务对齐的 2026 事件量（`address_month_events_2026.parquet`）

- 每月活跃候选地址（原生交易，地址去重后）：2,611–4,027；含代币转账：2,379–5,169。
- 每地址 2026 累计事件分布高度右偏：中位数 14，p90 229，p99 2,361；
  top-10 地址（零地址、WETH、0xdead、交易所热钱包等被冒名指向者）占 98.1% 事件量，
  说明**过滤系统/合约地址是必要预处理**，双向校验正好承担这个角色。
- **时间先后检查（非完整 as-of 校验）：2026-01 至 2026-09（9 月数据截至 09-24）逐月活跃候选中
  96.4%–99.4% 的 handle 记录写入时间早于该月**。这只证明记录曾经早于交易写入；当时有效的
  地址记录、反向记录、resolver 与 handle 是否一致，需用完整事件流逐时点重建后才能称 as-of 有效。
- 修正一处自己的错误：第一次月度统计 cand 未去重（16,789 行 vs 15,306 唯一地址），
  事件量被 ENS 一名多地址膨胀数十倍；已用 DISTINCT 重跑，上面的数字以重跑为准。

### 成本累计（本次试点）

| 项 | bytes billed | 约 |
|---|---:|---:|
| ens_resolver_events_v1 CTAS | 2.95 TiB | $18.9 |
| ens_reverse_evidence_v1 CTAS | 2.90 TiB | $19.9 |
| 月度/地址事件量等查询 | ~0.16 TiB | $1.0 |
| 合计 | ~6.0 TiB | **~$40** |

物化表均已分区+聚簇，后续增量查询近零成本。所有查询先 dry-run 并设 maximum_bytes_billed。

### C2. 最终样本（仅双向校验通过地址）的 2026 事件量

- 12,040 个通过地址中 **6,885 个在 2026 年有 ≥1 条事件**（原生交易或代币转账，
  from 或 to 任一）。
- 逐月（2026-01 至 2026-09，9 月截至 09-24）：活跃地址 2,040–4,040/月；
  事件量 59,932–119,859/月（原生 27.6k–68.1k + 代币转账 32.3k–54.7k）。
- 每地址 2026 累计事件：中位 12，p90 187，p99 1,794，max 61,833；
  top-10 地址占 19.0%（冒名指向的系统地址已被校验剔除，无病态集中）。
- 产物：`artifacts/ens_x_crosswalk/final_validated_address_month_events_2026.parquet`。
- 注意：此前"候选池 top-10 占 98.1%"的数字是未过滤口径，不代表最终样本。

## 2026-09-24 追记：100 对账号侧核验完成

- 零 API（免密钥公开端点）完成：syndication 嵌入时间线 + fxtwitter 镜像，原始响应存档。
- 71 对 bidirectional_ok：12 确认 / 38 仅 ENS 侧 / 5 冲突 / 16 无法核验；**加权确认率 18.0%**，账号存在率（加权）75.8%，存在条件下确认率 23.8%。
- 29 对 forward_only 单独报告：3 对"反向未配置但账号侧确认"、15 仅 ENS 侧、7 无法核验、4 冲突。
- 计数口径更正：双向验证**对**=12,461（非 12,040；12,040 是地址级），此前 72.8% 为混用口径，已弃用。
- 详见 artifacts/ens_x_crosswalk/verification_report_20260924.md。
- 下一步决策门：是否获取 X 推文/关注数据。注意确认证据为当日快照，历史 as-of 仍需事件流重建。

## 2026-09-25 追记：FxEmbed 零付费试点

- 13 个已确认 handle：12 个时间线/following 可抓；1 个（WeWake_eth）v2 端点 500 个例失败。
- 8 页（约160条）可覆盖多数账号 2026 全年各月；高频账号（96k 推文）需深翻页，且存在纯转发 bot 型账号。
- 互动边素材充足：转发45%/回复6%/提及26%，均带时间戳 → 社交图应走互动边路线，following 仅作当前快照。
- 3 条推文经 X 官方 oembed 独立核对通过。
- 合规边界：X 条款限制批量抓取，FxEmbed 用于可行性验证；正式获取/发布方案另行核对。
- 详见 artifacts/ens_x_crosswalk/fx_pilot_report_20260925.md。
