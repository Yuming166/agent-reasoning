# Group C — Temporal-Graph-First：演化交易网络中的结构重要性（Phase I 骨架）

> 状态：**流水线骨架已跑通，cutoff=2022-09-01 首次证据已产出**（2026-09-11，cloud82，
> 10.63.0.82）。本组结果必须引用冻结协议 `research/audit/temporal_protocol.yaml` v1.0 与
> `research/audit/DATA_AUDIT.md`（Group 0）；所有数字标注样本范围与 cutoff，**只作描述性证据，
> 不声称因果、不声称预测优越性、不声称 SOTA**。

---

## 1. Research Question 与 Hypothesis

**Phase I 总体问题**：Which Ethereum wallets are worth paying attention to, at what time, and why?

**Group C 子问题**：
> 在 cutoff t 的演化交易网络中，"结构重要性"（structural importance）如何定义、如何无泄漏地计算，
> 它能否描述性地预测钱包未来的网络行为（活动量 / 边数），以及它是否区别于"交易量大小"与
> "预测影响力"两类概念？

**Group C 假说（来自方案 §Group C）**：
> H_C：重要钱包 = 演化交易网络中的结构重要节点（hub / bridge / 高时间中心性节点），
> 而非仅仅"量大"的钱包。

**对象定义**：
- `G_≤t`：只用严格早于 cutoff t 的信息构造的时序子图（lookback `[t-90d, t)`）。
- `s_i(t)`：钱包 i 在 `G_≤t` 上的结构特征向量。
- 结构重要性 = 由 `s_i(t)` 导出的排名/分数（本组用等权百分位复合 `structure_pct` 作为汇总口径，
  另给不含体量的 `structure_novol_pct` 做消融）。

**边界声明（铁律）**：
1. **结构重要性 ≠ 预测影响力**：结构分数高不等于"对未来有预测影响"（实测与 P2 trigger proxy
   近零相关，见 §6.4）。
2. **结构重要性 ≠ 因果**：任何相关性均为描述性；无干预/识别策略，不产生因果声明。
3. **静态全窗口先验是 leaky prior**：`artifacts/exgraph_structural_features.csv`（全窗口聚合
   degree/weighted degree/PageRank）**不得**作为 cutoff 处 as-of 预测特征，只作为外部先验/基线
   （协议 `feature_availability.static_graph_prior_only`）。

---

## 2. 结构重要性定义与指标清单

全部指标在 as-of matched-matched 时序子图上计算（定义见 §3），只使用 `< 2022-09-01` 的信息。

| 类别 | 指标 | 计算方式 | 说明 |
|---|---|---|---|
| 体量/局部结构 | `deg_in/out/und` | networkx DiGraph in/out degree；无向图 degree | 不同对手方数量 |
| | `wdeg_in/out/und` | 事件计数加权 | 与 Group A `asof_mm_w_*` 同语义 |
| 全局结构 | `pagerank` | `nx.pagerank(alpha=0.85, weight)` | 有向角色图 |
| | `kcore` | `nx.core_number(undirected)` | 核数 |
| | `clustering` | `nx.clustering` | 局部聚集系数 |
| | `betweenness` | `nx.betweenness_centrality(und, normalized=True)`（全量，m=13,281 小图） | 中介/经纪 |
| 时间中心性 | `recency_wdeg` | Σ_月 weight × exp(-age_days/30)（月衰减，锚定 cutoff） | 近期权重 |
| | `activity_trend` | 月权重线性斜率 / (总权重+1) | 加速/衰减 |
| | `active_months` | 活跃月份数（Jun/Jul/Aug） | 持久性 |
| | `persistent_edges` | 出现在 ≥2 个月的边数 | 边持久性 |
| | `new_edges_recent` | 8 月新出现（前两月无）的边数 | 新鲜激活 |
| 时间 motif（轻量代理） | `mutual_pairs` | 双向 (u→v ∧ v→u) 对数 | 互惠对 |
| | `triangles` | `nx.triangles(und)` | 三角参与 |
| 社区 bridge | `community_id/size` | `greedy_modularity_communities(und, weight)`（Louvain 式） | 社区 |
| | `within_comm_wdeg` / `cross_comm_wdeg` | 同/跨社区加权度 | hub/bridge 材料 |
| | `cross_comm_share` | 跨社区权重占比 | 边界钱包 |
| | `bridge_score` | betweenness × (1 + 跨社区边数) | 经纪×跨界复合 |
| | `hub_score` | 社区内加权度 / (社区大小-1) | 社区内 hub |
| | `is_boundary` | `cross_comm_share ≥ 0.5` | 边界标记 |
| 复合 | `structure_pct` | 6 项百分位均值：log1p(wdeg_und, pagerank, kcore, betweenness, bridge_score, recency_wdeg) | 汇总口径 |
| | `structure_novol_pct` | 3 项百分位均值：pagerank, betweenness, bridge_score | **不含体量**的消融口径 |

**有向边语义（重要，已按 DDL 核实）**：`target_event_sequences_*` 中 `direction` 是 target 角色
（`outgoing`=from_address 是 target；`incoming`=to_address 是 target）。matched-matched 交互在表中
产生两条角色行（两端各一条）。本组主图沿用 Group A 约定：每条角色行生成一条 target→counterparty
有向边，因此**每次双向匹配交互在图中表现为一对镜像边**；每个端点的 in/out 计数 = 该钱包作为
target-发送方/target-接收方的交互次数（端点级计数正确）。方向化 flow 图（sender→receiver、权重减半）
仅作稳健性校验（`flow_pagerank_robustness`），不替换主特征。


---

## 3. 图构造：静态 vs 滚动窗口 vs 时序（temporal）

### 3.1 数据契约（冻结协议 §1-3）

| 项 | 值 |
|---|---|
| 主 cutoff | `2022-09-01`（最终未触碰 holdout 快照，只评估一次） |
| 特征 lookback | `[2022-06-03 00:00, 2022-09-01 00:00)` UTC（= snapshot-90d，严格早于 cutoff，与 `wallet_asof_features_20220901` 语义一致） |
| 标签窗口 | `[2022-09-01, 2022-10-01)`（仅描述性评估用 `fwd30_*`） |
| 事件来源 | `target_event_sequences_20220301_20220901`（dev 序列表，184 日分区无缺口） |
| 事件过滤 | `sequence_role='primary'`（external_tx + token_transfer）、`counterparty_present`、`NOT self_transaction`、两端 node_id 非空（matched-matched） |
| BigQuery 纪律 | 分区谓词 `block_timestamp ∈ [2022-06-03, 2022-09-01)`；`maximum_bytes_billed=3GiB`；单次实际计费 176,160,768 B（见 §9）；不整表导出 |

### 3.2 三类图对比

| 图 | 构造 | 时间语义 | 在本组中的角色 |
|---|---|---|---|
| **静态 EX-Graph 全图** | `data/raw/ethereum_graph.gpickle` / `exgraph_structural_features.csv`（1.81M 节点、11.9M 边，全窗口聚合，无时间戳） | 全窗口（含未来），**leaky** | 只作外部先验/基线，绝不并入 as-of 特征 |
| **滚动窗口 as-of 图（主）** | 90 天 lookback 内 matched-matched 有向边（事件计数加权） | `[t-90d, t)` 聚合，严格 as-of | 全部结构特征的主图 |
| **时序（temporal）图** | 同一有界拉取按自然月切 3 个快照（2022-06/07/08） | 月级演化 | 时间中心性/趋势/持久性/motif、月度社区演化 |

### 3.3 覆盖边界（支持集）

- as-of 表：18,519 个钱包（有 ≥1 个 90 天 primary 事件）。
- matched-matched 时序子图：**7,929 个节点（全部 ∈ 18,519）**，覆盖 42.8%。
- 未命中子图的钱包无 matched-matched 结构特征（其对手方未映射到 EX-Graph），在结构分析中
  按"支持集受限"口径单独报告；**绝不把支持集内的相关性强加到全集**（对应协议
  "support-restricted vs broad/full-candidate 分开报告"）。

---

## 4. 评估设计（全部描述性）

流程（冻结协议 §13 的"过去→状态→社区→重要性→选 K→冻结→观察未来→评估"的 Phase-I 描述版）：
1. cutoff 处只用 `< t` 信息计算 `s_i(t)`；
2. 按结构分数对支持集钱包排序；
3. 用未来窗口 `[t, t+30d)` 的 `fwd30_*` 标签**描述性评估**排序质量（不是时间外推的预测验证）。

评估项：
- **结构 vs 静态先验**：Spearman 秩相关 + top-K 重叠（说明 leaky 全窗口先验与 as-of 结构差异）。
- **结构 vs 交易量**：`volume = evt_cnt_90d`（钱包自身 90 天 primary 事件数）；复合结构分数与
  体量分数的秩相关、体积×结构分位联合表、低量高结构/高量低结构钱包计数与示例。
- **结构 vs 预测影响 proxy**：P2 trigger proxy（`p2_trigger_proxy_v2`，snapshot=2022-09-01，
  as-of；NULL 语义按审计处理）；P1 ICF 排名（Aug panel）为**事后补充边界**。
- **结构对 fwd30 的描述性预测力**：各结构特征与 `fwd30_evt_cnt / fwd30_cp_distinct / fwd30_new_cp`
  的 Spearman 秩相关；结构分位十等分组未来行为；top-K ∈ {10,25,50,100,250,500,1000} 选择后的
  未来活动/边数均值（与 volume 基线、静态 PageRank 基线对比）。
- **§12 动态社区**：as-of 社区结构（hub/bridge/boundary 的构成）+ 月度社区成员演化（后验描述性）。

**Baselines（方案 §14）**：random（隐含在全量均值中）、volume/activity（`evt_cnt_90d`）、
静态结构基线（`static_pagerank`/`static_w_degree`，leaky 仅基线）。本组不做 predictive/information
类基线（Group B/D 负责）。


---

## 5. 首次证据（cutoff=2022-09-01，支持集 n=7,929/18,519）

> 所有数字为描述性；详细表见 `results/evidence_summary.json`、`results/data/decile_analysis.csv`、
> `results/data/wallet_importance_20220901.csv`。

### 5.1 图规模（单次有界拉取，36,990 边行）

| 项 | 值 |
|---|---|
| as-of 子图节点 | 7,929（全部 ∈ 18,519 钱包样本） |
| 有向角色边 | 26,562（13,281 无向交互对） |
| 月度快照 | 2022-06: 4,607 节点/10,454 边；07: 4,578/10,528；08: 4,239/9,894 |
| betweenness | 全量计算（m=13,281，无采样） |

### 5.2 静态全窗口先验 vs as-of 结构（leaky prior 差异大）

| 配对 | Spearman 秩相关 |
|---|---|
| static_w_degree vs asof wdeg_und | **0.196** |
| static_degree vs asof deg_und | 0.376 |
| static_pagerank vs asof pagerank | 0.273 |
| top-100 重叠（w_degree / pagerank） | 6.4% / 8.7% |

> 解读：全窗口静态先验与 90 天 as-of 结构秩相关弱、top-100 重叠极低 —— 全窗口聚合的
> "历史总重要"**不能**替代 cutoff 处 as-of 结构（也印证协议禁止把它当 as-of 特征）。

### 5.3 结构重要性 vs 交易量（§10 显式检验"低量高结构"是否存在）

- `structure_pct` vs `evt_cnt_90d` 秩相关 = 0.575；不含体量口径 `structure_novol_pct` = 0.642。
- **低量高结构钱包在严格阈值下几乎不存在**：`struct≥p90 ∧ vol≤p50`：全复合 0 个、非体量复合 1 个；
  `p80/p30`、`p75/p25` 扫掠同样 ≤1 个。
- **高量低结构钱包存在**：`vol≥p90 ∧ struct≤p50`：248 个（非体量复合 229 个）。
- 体积×结构三分位联合表（非体量复合）：struct_hi 行 = {vol_lo:186, vol_mid:717, vol_hi:1740}，
  struct_lo 行 = {vol_lo:1529, vol_mid:822, vol_hi:292} —— 结构重要性与体量强正向共变，
  但非完全重合（高量低结构 ≠ 0）。

> 结论（描述性）：在该 matched-matched 子图中，"低量高结构"不是显著群体；"高量低结构"存在。
> 这正对应方案 §10 的告诫："Do not assume these groups exist"。

### 5.4 结构重要性 vs 预测影响力 proxy（二者正交）

| 配对 | Spearman |
|---|---|
| structure_pct vs P2 trigger score（n=1,113 有值，09-01 as-of） | **-0.036** |
| evt_cnt_90d vs P2 | -0.074 |
| wdeg_und vs P2 | -0.013 |
| structure_pct vs P1 ICF（Aug panel，事后边界，n=4,481） | 0.375 |

> 解读：as-of 结构分数与 P2 触发型影响 proxy 近零相关 —— 结构重要性**不等于**预测影响力
> （呼应协议 `P1/P2/P3 are proxies, not causal influence`；也呼应 Group B 的"two-layer separation"）。

### 5.5 结构特征对 fwd30 未来行为的描述性预测力

Spearman（支持集 n=7,929，对 `fwd30_evt_cnt`）：

| 特征 | ρ |
|---|---|
| volume_pct（evt_cnt_90d） | **0.750** |
| deg_und / mutual_pairs | 0.496 / 0.496 |
| bridge_score / betweenness | 0.489 / 0.487 |
| structure_novol_pct | 0.488 |
| kcore / structure_pct / pagerank | 0.458 / 0.435 / 0.390 |

- 全量 n=18,519 上 `evt_cnt_90d` 对 fwd30 的 ρ=0.74-0.75（活动/边数）、0.656（新对手方）。
- 十等分组（structure_pct）：最低组 fwd30_evt 均值 15.8 / 中位 8，最高组 123.0 / 64 —— 单调上升，
  顶部组≈全量均值（34.1）的 3.6 倍（描述性）。
- **top-K 选择（描述性，K=10..1000）**：structure 组 fwd30_evt 均值始终低于 volume 组
  （K=10: 1592.9 vs 1779.6；K=100: 349.3 vs 429.7；K=1000: 108.0 vs 126.1），但高于静态 PageRank
  组（K=100: 349.3 vs 293.1；K=1000: 108.0 vs 95.7）。

> 结论（描述性）：结构指标对"未来活动/边数"有中等正向区分度（ρ≈0.39-0.50），**弱于纯体量基线
> （ρ≈0.75）**，但强于 leaky 静态 PageRank 基线。这是 in-sample 描述，**不是**时间外推预测优越性。

### 5.6 §12 动态社区（as-of + 月度演化，后验描述性）

- as-of Louvain（greedy modularity）得 **387 个社区**，前两大社区 2,450/2,085 节点；boundary 钱包
  （跨社区占比 ≥0.5）799 个（10.1%）。
- 结构 top-100 钱包：**88% 是"纯 bridge"**（bridge≥p90 且非 hub≥p90）、12% 双高、0% 纯 hub ——
  本网络的结构重要性呈"经纪/跨界"形态而非"社区内 hub"形态。
- boundary 钱包 fwd30_evt 均值 38.0 vs 非 boundary 33.65（差异小，描述性）。
- 月度社区成员演化：Jun→Jul switch rate 58.0%、Jul→Aug 56.3%（greedy 最佳 Jaccard 匹配；
  月图节点集不同，数字含集合漂移成分，仅作粗略描述）。

---

## 6. Expected Failure Modes（预期失败模式）

1. **体量混淆**：结构复合含 wdeg/recency，与自身活动量机械相关；已用 `structure_novol_pct` 消融，
   但 pagerank/betweenness 本身仍随度增长，无法完全去体量。
2. **覆盖 42.8%**：matched-matched 子图只覆盖样本钱包的 42.8%；未命中钱包（对手方未映射）结构
   不可知，任何全集外推都有选择偏差。
3. **角色边语义**：主图为 target↔counterparty 角色边（每交互一对镜像边）；flow 方向化后
   PageRank 秩相关仅 0.591 —— 方向约定会影响排名，需在正式版固定并报告敏感性。
4. **月度社区高 switch rate**：月图节点集逐月变化 + 小社区噪声，switch rate 不能直接读作
   "社区归属漂移"。
5. **P2 覆盖**：09-01 快照仅 3,076 行（支持集内 1,113 有值），NULL 语义（滞后不足 24h）限制
   影响 proxy 对比的解释力；P1 是 Aug panel，属事后边界。
6. **描述性评估不外推**：所有 fwd30 指标是 in-sample 描述；没有做 walk-forward 冻结选择
   （那是 Phase-II/正式评估）。
7. **静态先验 leaky**：static_* 只作基线对比，若被误用为 as-of 特征即泄漏（协议禁止）。
8. **长尾**：wdeg/volume 高度右偏（max evt_cnt 241,523 vs 中位 37），百分位复合缓解但未完全消除。

---

## 7. Compute Cost

- **CPU only**，未使用 GPU；无 LLM。
- BigQuery：**单次有界拉取，实际 billed = 176,160,768 B（≈0.16 GiB）**，远低于协议建议的全组
  ≤3 GiB；分区谓词 + `maximum_bytes_billed=3GiB` 双重防护，不整表导出。
- 本地：networkx 建图 + 全量 betweenness ~6.5 分钟；评估/社区/流方向稳健性 <1 分钟；总计约 8 分钟。

---

## 8. Novelty（弱声明，Phase-I 边界）

- 本组为 Phase-I 探索：不声称新方法/SOTA。可支撑的差异化点（待正式版验证）：
  1. **as-of 时序结构 vs 全窗口静态先验的量化差异**（top-100 重叠仅 6-9%），对"用 EX-Graph 静态
     特征做选择先验"的实践有直接警示；
  2. 在 matched-matched 时序子图上显式检验"低量高结构/高量低结构"分布（低量高结构≈空），
     与方案 §10 的预注册问题对齐；
  3. 结构重要性 vs P2 影响 proxy 近零相关，支持"结构 ≠ 预测影响"的两层分离叙事（与 Group B 交叉）。
- §12 动态社区为探索性描述，社区 switch rate 口径粗糙，正式版需固定社区匹配与阈值。

---

## 9. 复现与文件清单

```bash
cd /storage/gaoym/ex-graph-microtransaction-analysis
bash research/groupC_temporal_graph/run_all.sh        # [1/2] build + [2/2] evaluate
```

| 文件 | 内容 |
|---|---|
| `sql/edges_asof.sql` | 有界 as-of 边抽取（分区过滤，按月分组） |
| `src/config.py` | cutoff/window/BQ 上限/路径 |
| `src/bq_client.py` | 代理+ADC 有界查询（只读） |
| `src/build_temporal_features.py` | 建图 + 全部结构/时间/社区特征（networkx CPU） |
| `src/evaluate_importance.py` | 描述性评估（先验对比/体量/影响 proxy/fwd30/社区） |
| `results/data/edges_asof_20220901.csv` | 36,990 边行 (u,v,direction,month,weight) |
| `results/data/structural_features_20220901.csv` | 7,929 节点 × 27 结构/时间/社区特征 |
| `results/data/wallet_importance_20220901.csv` | 钱包级合并表（结构+体量+fwd30+proxy+先验） |
| `results/data/decile_analysis.csv` | 结构十等分组未来行为 |
| `results/data/monthly_graph_stats.json` / `community_summary.json` / `build_manifest.json` | 图规模/社区/构建清单 |
| `results/evidence_summary.json` | 全部关键数字 |

**样本/cutoff 边界**：特征窗口 `[2022-06-03, 2022-09-01)`；cutoff=2022-09-01（最终 holdout 快照）；
标签窗口 `[2022-09-01, 2022-10-01)`；支持集 7,929/18,519；静态先验只作外部基线。

---

## 10. 未完成项 / 后续（Phase-I 内或 Phase-II）

1. **月度滚动 walk-forward**（方案要求的 walk_forward cutoffs 05/06/07/08）——当前只做了 09-01
   主 cutoff；`sql/edges_asof.sql` 可改窗口复用（低成本）。
2. **正式 top-K 冻结选择评估**（K∈{10..1000}，MRR/Recall@K/NDCG）——本组只做描述性均值对比；
   与 Group B/D 的选择器对比留给全组擂台。
3. **flow 方向化主图**：固定方向语义后的正式特征（当前为稳健性校验，秩相关 0.591 提示需审计）。
4. **社区演化正式口径**：固定社区匹配算法/阈值与"集合漂移 vs 归属变化"分离。
5. **与 Group B（预测影响）/D（信息增益）交叉对比**：结构、影响、信息三口径在相同钱包集上的
   两两相关与 top-K 重叠（当前只有 P1/P2 代理的初步对比）。
6. **更细时间粒度**（周级而不是月级）的 temporal motif。
