# COMMUNITIES.md — §12 动态社区形式化（per-cutoff as-of 交易社区）

> 角色：COMM 组。依据 `research/autoresearch_phase1.md` §12（Dynamic Communities）/ §13（评估协议）；
> 冻结协议 `research/audit/temporal_protocol.yaml` v1.0。全部构造只用严格 < cutoff 的信息；
> **不声称因果、不声称有效性/优越性**；数字均为描述性证据并标注样本与 cutoff。
> 数据：matched-matched primary 边（双方 EX-Graph 映射、counterparty_present、非自交易），
> 单次有界 BQ 拉取（billed ≈0.41 GiB，`sql/edges_asof_day.sql`）。

---

## 1. 固定协议（正式口径）

| 项 | 固定值 |
|---|---|
| 快照 | as-of 图，cutoff t ∈ {2022-06-01, 07-01, 08-01, 09-01}，lookback `[t-90d, t)` |
| 图 | 无向加权图，方向角色边按 `(u,v)` 累加权重（与 Group C 主图语义一致） |
| 社区算法 | `networkx.community.greedy_modularity_communities(weight="weight")`（Louvain 式，networkx 3.6.1），节点按 ID 排序保证可复现 |
| 跨快照匹配 | Hungarian 最大权重二部匹配（最大化公共节点 Jaccard 和），匹配对要求 `Jaccard ≥ 0.05`；双射、全局最优 |
| 漂移分解 | 集合漂移 = 节点集 Jaccard / 新节点占比；归属变化 = 公共节点上“映射后社区改变”的比例（另拆 mapped-only 与新社区进入） |
| 角色（与 Group C 定义一致） | hub = `hub_score≥p90` 且非 bridge；bridge = `bridge_score≥p90` 且非 hub；both / neither；boundary = `cross_comm_share≥0.5` |
| betweenness | 09-01 全量（与 Group C 一致）；06/07/08 采样 k=1000 seed=42（已标注近似）；日历月不计算（仅用于 switch 对比） |
| 成本 | CPU only；无 GPU、无 LLM、无新包 |

---

## 2. 月度 as-of 图规模（per-cutoff，90 天窗口）

| cutoff | 节点 | 无向边 | 事件权重 | 社区数 | modularity | boundary 数（占比） |
|---|---:|---:|---:|---:|---:|---:|
| 2022-06-01 | 11,370 | 22,451 | 153,878 | 373 | 0.5017 | 1,283（11.28%） |
| 2022-07-01 | 10,172 | 19,331 | 124,810 | 375 | 0.5119 | 1,133（11.14%） |
| 2022-08-01 | 8,927 | 15,997 | 113,188 | 409 | 0.4745 | 969（10.85%） |
| 2022-09-01 | 7,929 | 13,281 | 105,592 | 387 | 0.4577 | 799（10.08%） |

- 09-01 与 Group C 完全一致（节点/边/社区数/boundary/事件权重 105,592 = Group C 月度 28,946+39,588+37,058）。
- 节点集随 cutoff 递减（11,370→7,929），与 DATA_AUDIT 的活跃钱包数递减一致。

---

## 3. 集合漂移 vs 归属变化（正式口径）

相邻 cutoff（as-of 90 天窗口重叠 60 天）：

| 对 | 公共节点 | 节点集 Jaccard | 新节点占比(占cur) | 消失节点占比(占prev) | **归属切换率（公共节点）** | 其中 mapped-only 切换 | 进入新/未匹配社区 | 映射社区平均 Jaccard | ARI | NMI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 06-01→07-01 | 9,447 | 0.7811 | 0.071 | 0.169 | **0.3568** | 0.3047 | 0.0749 | 0.8217 | 0.5254 | 0.5149 |
| 07-01→08-01 | 8,166 | 0.7469 | 0.085 | 0.197 | **0.3998** | 0.3389 | 0.0922 | 0.7999 | 0.4848 | 0.4944 |
| 08-01→09-01 | 7,109 | 0.7294 | 0.103 | 0.204 | **0.4652** | 0.4031 | 0.1040 | 0.8354 | 0.4309 | 0.4860 |

**解读（描述性）**：
- 社区归属切换率逐月上升（35.7%→40.0%→46.5%），其中“进入未匹配/新社区”占比从 7.5% 升至 10.4%；
  ARI 同步下降（0.525→0.431）→ **越接近 Aug→Sep regime 切换，社区结构越不稳定**。
- 集合漂移与归属变化是两回事：即便节点集 Jaccard 保持 ~0.73-0.78，公共节点中仍有 36-47% 换社区。
- 已映射社区的成员 Jaccard 稳定（0.80-0.84），说明**持续性社区内部的成员构成相当稳定**，
  切换主要发生在边界/新进入的钱包上。

---

## 4. 角色分布与角色转移（与 Group C 定义一致）

| cutoff | hub | bridge | both | neither | boundary（cross_share≥0.5） |
|---|---:|---:|---:|---:|---:|
| 06-01 | 1,024 | 1,022 | 115 | 9,209 | 1,283 |
| 07-01 | 937 | 937 | 81 | 8,217 | 1,133 |
| 08-01 | 853 | 840 | 53 | 7,181 | 969 |
| 09-01 | 809 | 758 | 35 | 6,327 | 799 |

- 角色类（hub/bridge/both）约占总节点 18-20%，boundary（跨社区权重 ≥50%）约 10-11%。
- 相邻 cutoff 角色改变率：06→07 16.2%、07→08 16.5%、08→09 16.8%（common 节点上，p90 阈值）。
- 09-01 结构 top-100 中 Group C 报告 88% 为“纯 bridge”——本组角色框架在四个快照上均给出
  “bridge 型重要”（非 hub 型）的一致形态（hub/both 占比随月份略降）。

---

## 5. 与 Group C 粗略月度 switch rate（58.0%/56.3%）的差异

**Group C 数字可精确复现**：在其 edges 文件（`[2022-06-03, 2022-09-01)` 内 Jun/Jul/Aug 日历月切片）
上用其原算法（覆盖式权重 + 无阈值贪婪匹配）得到 58.02% / 56.31%，与报告一致。

同数据、同日历月上的口径分解（`results/json/groupC_monthly_comparison.json`）：

| 口径 | Jun→Jul | Jul→Aug |
|---|---:|---:|
| A. Group C 精确（覆盖式权重 + 贪婪无阈值） | **58.02%** | **56.31%** |
| B. 正式 Hungarian（同一覆盖式权重图） | 70.31% | 69.58% |
| C. 正式 Hungarian（累加式权重图） | 68.09% | 68.00% |
| D. 本组正式 per-cutoff as-of（90 天窗口） | 35.68% | 39.98% |

**差异来源（明确）**：
1. **匹配协议**（A→B，+12~13pp）：Group C 的贪婪匹配无最小重叠阈值，任何 cur 社区都映射到某个
   prev 社区（即使 Jaccard=0），把“进入全新/无关社区”误算为“未切换”，**系统性低估 switch rate**；
   正式 Hungarian + 0.05 阈值把这些计入切换。
2. **权重语义**（B→C，-2pp）：Group C 月度对比脚本用 `add_edge(weight=w)`（重复方向行**覆盖**，
   实测 6,114 对互惠 (u,v,month) 受影响）；正式口径累加（与 Group C 主图一致）。
3. **窗口类型**（C→D，-32~30pp）：Group C 是 1 个月日历切片（窗口互不重叠、节点集 Jaccard 仅
   ~0.37-0.39）；正式 per-cutoff 是 90 天 as-of 窗口（相邻窗口重叠 60 天、节点集 Jaccard ~0.73-0.78），
   因此正式归属切换率更低（35.7-46.5% vs 68-70%）。**两者回答不同问题**：日历月=月与月的结构差异；
   per-cutoff as-of=月度决策点上的状态漂移。

---

## 6. 社区 × 重要性（09-01 主 cutoff）

样本边界：交易社区覆盖 matched-matched 子图 7,929 钱包（占 18,519 的 42.8%）；重要性来自
Group B holdout09 预测（`pred_act_level_LightGBM` top-10%，K=793）与 Group D 钱包 IG
（`ig_occ`，histgbm/y_cp_ge10，5 折均值；子图内覆盖 1,283 钱包）。

| 指标 | 值 |
|---|---:|
| top-2 社区承载预测 top-10% 份额 | **68.1%** |
| top-5 社区份额 | 83.4% |
| top-10 社区份额 | 91.3% |
| 预测 top-10% 跨社区 HHI | 0.3914 |
| 含 ≥1 个预测 top-10% 成员的社区 | 45 / 387 |
| Spearman(社区大小, 社区均值 IG) | 0.2241 |
| 子图钱包均值 IG | 0.535（Group D 全子集均值 0.406） |

- **对照 Group B 的 93%**：Group B 在 Group A persona（覆盖全部 18,519 钱包）上测得 top-2 persona
  承载预测 top-10% ≈93%；交易社区（仅 7,929 子图）上 top-2 = 68%。两者都显示“预测重要钱包高度
  集中”，但**交易社区集中度低于 persona 集中度**——口径（覆盖范围+分区方式）不同，不能直接比大小。
- **社区×信息增益**：社区大小与均值 IG 弱正相关（ρ=0.22）；IG 覆盖仅在 1,283/7,929（16.2%），
  Group D 子集与交易社区子图交集有限，社区级 IG 差异需更大覆盖再下结论。

---

## 7. Regime 依赖（描述性）

按 fwd30 未来活动（`fwd30_evt_cnt`，来自 Group A 月度 + Group C 09 标签）在各 cutoff 计算
“未来活动 top-10% 的前 2 社区承载份额”：

| cutoff | 未来 top-10% 前 2 社区份额 | 跨社区 HHI |
|---|---:|---:|
| 2022-06-01 | 0.6209 | 0.3332 |
| 2022-07-01 | 0.6431 | 0.3404 |
| 2022-08-01 | 0.6125 | 0.3128 |
| 2022-09-01 | 0.6066 | 0.3039 |

- 未来活动的重要性集中度在各月稳定（~0.61-0.64），09-01 略降；
- 与此同时归属切换率从 35.7% 升到 46.5% → **集中度高且稳定，但社区成员构成在 Aug→Sep 期间加速漂移**，
  即“重要钱包仍集中在少数社区，但这些社区的成员在换血”。

---

## 8. 产出文件清单

| 文件 | 内容 |
|---|---|
| `sql/edges_asof_day.sql` | day 级有界边拉取（[2022-03-03, 2022-09-01)） |
| `src/{pull_edges,build_graphs,community_evolution,groupC_comparison,emit_per_snapshot}.py` | 全流程脚本 |
| `results/data/edges_day_20220303_20220901.csv` | 142,300 行 day 级边（billed 0.41 GiB） |
| `results/data/edges_asof_2022{0601,0701,0801,0901}.csv` | 各 cutoff 聚合边 |
| `results/data/monthly_communities.csv` | 每快照每节点：社区 + 角色特征（52,084 行） |
| `results/data/community_membership_2022*.csv` | 分快照角色明细 |
| `results/data/community_importance_20220901.csv` | 社区×重要性（Group B/D/C 交叉） |
| `results/json/community_evolution_2022*.json` | 每快照图统计 + 角色分布 |
| `results/json/community_evolution_summary.json` | switch/漂移/稳定性/重要性/regime 汇总 |
| `results/json/groupC_monthly_comparison.json` | Group C 复现 + 口径分解 |
| `results/figures/*.png` | 规模 rank、漂移分解、Group C 对比、重要性、regime 5 张图 |

---

## 9. 未完成项 / 边界

1. **betweenness 近似**：06/07/08 用采样 k=1000（seed=42），仅 09-01 全量；bridge_score 在早期快照为近似。
2. **社区×重要性覆盖**：Group D IG 只覆盖子图 1,283/7,929；社区级 IG 结论受覆盖限制。
3. **top-K 冻结选择评估**：本组只做描述性集中度；正式 MRR/Recall@K 属全组擂台（§13 正式协议）。
4. **更细粒度**：周级 as-of 图未做；方向化 flow 图主特征未替换角色边主图。
5. **persona 社区（行为社区）对比**：方案 §12 的“交易 vs 行为 vs 混合社区”三线对比只完成交易社区，
   行为社区对比（Group A persona × 交易社区交叉）未做——留给全组交叉。
