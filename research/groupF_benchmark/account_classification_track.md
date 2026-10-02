# §7 Ethereum Account-Classification 验证轨道（Group F）

- 生成日期：2026-09-11；网络抓取经代理 `http://10.63.0.72:7890`
- 目的：为"无监督行为表示 → 动态聚类/角色 → 外部标签验证"提供候选标签源；**外部标签只做验证，不做训练标签，也不把无监督角色强行重定义成标签**（方案 §7 铁律）
- 证据标签同 benchmark_registry.md：`[已实测]` `[已读源码]` `[已读论文]` `[沿用notes审计]` `[仅凭论文/描述]` `[未能验证]`
- 已先读项目 notes：`dataset-selection-recommendation.md`、`xblock-temporal-dataset-audit.md`、`dataset-audit.md`、`temporal-dataset-options.md`、`cost-and-open-data-options.md` 等，并沿用其结论

## 0. 结论先行

- **没有"官方、带时间、可复现、覆盖 exchange/mining/ICO/gambling 多类"的 Ethereum 账户分类公共基准**。最接近的是：
  1. **Etherscan 派生标签**（社区整合：Forta labelled-datasets、dawsbot/eth-labels、MyEtherWallet/ethereum-lists）—— 覆盖面广但**无时间戳、第三方、事后标签**，只能做"时点外部验证"
  2. **LiveGraphLab 节点分类标签**（日/周/月交易者启发式）—— 与行为表示最契合，但**不是真实实体角色**（exchange/mining/ICO/gambling）
  3. **EX-Graph wash-trading 标签**（1,445 个 Dune 标签）—— 内部标签，可作验证，但极少且无法映射到我们钱包（见 exgraph_benchmark_note.md）
  4. **Harvard ERC-20 2021/2022、XBlock** —— 前者是无标签原始事件（可自建标签/任务），后者已审计**不适用**
- 因此 §7 的正确定位：**外部标签验证（有效性声明）**，不是 SOTA 声明；任何"覆盖度/命中率/ARI/NMI"都要标注标签源、时点与事后性。

## 1. Etherscan 标签派生的标签清单（推荐做"实体标签 join"）

### 1.1 Forta Labelled Datasets
- paper/repo/data: `github.com/forta-network/labelled-datasets`（MIT）`[已实测]`
- 内容: Ethereum Mainnet `phishing_scams.csv`（~525KB）、`etherscan_malicious_labels.csv`（~679KB）、`malicious_smart_contracts.csv`（~163KB）；来源 Luabase `ethereum.tags`（Etherscan 标签 exploit/heist/phish-hack）`[已实测 GitHub API + README]`
- license: MIT（仓库）；上游 Etherscan 标签使用条款需另行核对 `[仅凭论文/描述]`
- 规模: 数千地址级（文件 KB-MB 级；精确条数未加载，`[未能验证]`）
- 是否已验证可跑: 否（本会话仅核到元数据/README；标签 CSV 可直接下载 join，成本极低）`[已实测元数据]`
- 与我们数据标签兼容性: 地址级可直接 join 27,613 目标，命中数可测；类别以"恶意/钓鱼/exploit"为主，**不覆盖 exchange/mining/ICO/gambling 的良性角色**
- 泄漏风险: **高**（事后标签、无时间戳；只能时点验证，禁止进入 as-of 训练/选择流程）

### 1.2 dawsbot/eth-labels
- paper/repo/data: `github.com/dawsbot/eth-labels`（MIT，296 stars；branch `v1`）`[已实测]`
- 内容: `data/csv/accounts.csv`（12.3MB）、`tokens.csv`（7.7MB）、`db.sqlite3`（42MB）—— 社区整合的地址↔标签（交易所/DeFi/桥/混币等实体）
- license: MIT `[已实测]`
- 规模: 地址级数十万行级（CSV 12MB；精确条数未加载 `[未能验证]`）
- 是否已验证可跑: 否（未下载；可直接 join，成本低）`[未能验证]`
- 与我们数据标签兼容性: **中-高**（最可能覆盖 exchange/DeFi 等实体类别）；与 27,613 目标的命中覆盖度**未实测** → 需先下载统计（任务：`join targets ∩ labels` 计数）`[未能验证覆盖度]`
- 泄漏风险: 高（事后、无时间戳；第三方维护）

### 1.3 MyEtherWallet/ethereum-lists
- paper/repo/data: `github.com/MyEtherWallet/ethereum-lists`（MIT，711 stars，branch `master`）`[已实测]`
- 内容: `src/addresses/addresses-{light,dark}list.json` 等安全/诈骗地址清单（主要是 scam/恶意清单，不是完整实体分类）
- license: MIT `[已实测]`
- 与我们数据标签兼容性: 低-中（作为"已知恶意"补充，不是角色分类）
- 泄漏风险: 高（事后标签）

### 1.4 Etherscan 官方标签
- 说明: Etherscan 提供 label cloud / API（需 API key），**无公开全量导出**；其派生态（Forta/eth-labels/ethereum-lists）都是间接整合。直接使用需注册 API key 并遵守使用条款；**本会话未申请/未验证** `[未能验证]`

## 2. 原始链上数据（可自建任务/标签，非现成基准）

### 2.1 Harvard Dataverse ERC-20 Trading 2021（10.7910/DVN/C1AR9V）/ 2022（10.7910/DVN/5P82QC）
- paper/repo/data: Dataverse 下载（CC0-1.0，已实测 license）`[已实测][沿用notes审计]`
- 内容: 逐笔 ERC-20 转账（block_id, tx_hash, time, token_address, sender, recipient, value, token 信息），按月 TSV；2022-02~07 约 6.71GB 压缩 `[沿用notes审计]`
- 规模: 月级数亿行级（2022 各月压缩 0.9-1.3GB）
- 是否已验证可跑: 未下载（notes 审计过 schema）`[沿用notes审计]`
- 与我们数据标签兼容性: **无标签**，但可与 27,613 目标 join 自建行为标签（如"与交易所/合约交互频率"）；缺点无 transaction_index/log_index，同块/同秒顺序需审计 `[沿用notes审计]`
- 泄漏风险: 中（自建标签需 as-of）

### 2.2 LiveGraphLab（Zenodo 8267012，CC BY-4.0）
- paper/repo/data: `zenodo.org/records/8267012`；代码 `github.com/livegraphlab/code`（已本地 vendor）`[已实测]`
- 内容: NFT 事件级时间图（~4.5M 节点/124M 边，至 2022-08-01）；`node-classify-data.zip`（186MB）含**节点分类标签=日/周/月交易者（启发式：按最大交易间隔）**；`link-pred-data.zip`（194MB）`[已实测 Zenodo API][已读源码]`
- license: CC BY-4.0 `[已实测]`
- 规模: 节点分类图 ~1.80M 节点 / 21.83M 边 `[已读源码]`
- 是否已验证可跑: 代码在本地 vendor（基于 Roland，torch-geometric 2.x）；**未实跑**（环境版本需移植）`[已读源码]`
- 与我们数据标签兼容性: **中**（NFT 语义与 EX-Graph 最接近；标签是行为频率型，适合验证"行为表示是否区分高频/低频交易者"，**不适合 exchange/ICO/gambling 实体语义**）
- 泄漏风险: 中-高（启发式标签用全历史计算；需 as-of 重算或用官方快照并声明）

### 2.3 EX-Graph wash-trading 标签（内部）
- paper/repo/data: EX-Graph 官方 wash-trading 图（Dune 1,445 地址；仅 3 个有 X 匹配）`[已读论文]`
- license: CC BY-NC-SA（数据）`[已读论文]`
- 与我们数据标签兼容性: **低**（wash 图无地址映射，无法 join 27,613；详见 exgraph_benchmark_note.md）
- 泄漏风险: 中-高（正例 0.05% 极不平衡）

### 2.4 XBlock（Kaggle Ethereum Partial Transaction Dataset）
- paper/repo/data: Kaggle（XBlock 发布）；本机 `data/raw/ethereum_partial_transaction_dataset.zip` 已审计 `[已实测][沿用notes审计]`
- 结论: **不适用** —— 2015-16 窗口、与 27,613 目标仅 10 行事件交集、无 hash/block/index/token、license Unknown `[已实测]`

## 3. 论文自定义评测（仅参照，不作主标签源）

- **Chen et al. 2020 (TOIT) Phishing Scams Detection in Ethereum Transaction Network**：官方数据未正式发布；社区重实现 `yuanqi7/Phishing-Detection-on-Ethereum`（无 license）；钓鱼标签 2018-2020 窗口。`[已实测 GitHub 搜索][仅凭论文]` 不推荐作主标签。
- **lincozz Ethereum-Phishing-Account-Dataset**：仓库 20KB 无数据（爬虫），无 license，需自爬 Etherscan。`[已实测]` 不推荐。
- **vagifa Ethereum Fraud Detection Dataset（Kaggle，ODbL）**：98 特征地址级表（~9.8k 行），**聚合全历史无时间** → 只能做静态地址级标签验证，泄漏风险高。`[已实测 Kaggle API]` 谨慎。
- **sergionefedov Crypto Exchange Fraud & Wash Trading（Kaggle，CC0）**：500k 交易/8k 钱包/40 token，页面称代币价格为 simulated（合成真实性未验证）→ 不推荐。`[已实测 Kaggle API][未能验证真实性]`
- **Du et al. 2024 (TIFS) Ethereum Mixing Service 去匿名**（Zenodo 10963493，CC BY-4.0）：Zenodo 上仅 PDF，无数据 → 不适用。`[已实测]`

## 4. 缺失类别与建议

- exchange / mining / ICO / gambling 等**良性角色标签**在本项目现有资源里没有可靠、带时间的公共来源：Etherscan 官方不全量开放；社区清单（eth-labels 等）最可能覆盖 exchange/DeFi，mining/ICO/gambling 覆盖度需实测。
- 落地建议：
  1. 下载 eth-labels + Forta + ethereum-lists，对 27,613 目标做一次**命中覆盖统计**（各标签类别的地址数、与目标交集数），产出 `artifacts/groupF_label_coverage.json`（Group 0 的 DATA_AUDIT 前先冻结标签源版本+sha256）；
  2. 标签只用于**时点外部验证**（报告 ARI/NMI/purity 或命中率），不进入 as-of 训练/选择；
  3. 行为聚类验证首选 LiveGraphLab trader 标签（行为语义最匹配）作为补充轴；
  4. 若需"exchange 角色"做更正式验证，再评估 Etherscan API 的合规获取（需 key + 条款核对，`[未能验证]`）。
