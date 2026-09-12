# Chief Scientist — 方法选择建议（给 FINAL 组，autoresearch_phase1.md §18/§19）

- 日期: 2026-09-11；冻结协议 `research/audit/temporal_protocol.yaml` v1.0 + `DATA_AUDIT.md`
- 统一 cutoff: 2022-09-01（本节建议的多 cutoff walk-forward 用 `wallet_asof_features_v1`
  的 05/06/07/08 快照 + 09-01 最终 holdout）
- 证据来源: `COMPARISON.md`、`consensus_analysis/README.md`（本组实测）
- 铁律: 任何定义升级前必须满足——特征/选择只用 ≤cutoff 信息、fwd30 标签只用于评估、
  冻结 top-K 后再观察未来、报告支持集受限口径、不声称因果/优越性/SOTA。

## 1. 建议升级到正式冻结评估的定义（FINAL 组主选）

### 1.1 首选 — Group B 预测影响（活动水平与新边水平）
- 定义: importance_B(i,t) = 模型对 `log1p(fwd30_evt_cnt)` / `log1p(fwd30_new_cp)` 的
  OOS 预测输出（逻辑回归/HistGBM/LightGBM 集成，或单 LightGBM）。
- 理由: holdout09（n=18,519）上最强的未来活动选择器（act R²=0.617、Spearman=0.812、
  Recall@K=0.653；top-10 未来活动 lift 106×）；严格时序 OOS 已就绪；稳定性最好
  （月度 top-10% 重叠 60–64%）；成本最低（BQ≈10MB，CPU 分钟级）。
- 正式评估要求:
  1. 多 cutoff walk-forward: 在 05/06/07/08 快照各训练一次（train 用更早快照，strictly
     before），滚动评估 06→09；
  2. 在最终 holdout 09-01 上**冻结一次** top-K（K∈{10,25,50,100,250,500,1000}），
     禁止用 09-01 调参/选模型；
  3. 评估 = 冻结 top-K 的 fwd30 均值/lift + Recall@K + MRR（top-10% 检索），
     并与 **A-vol（evt_cnt_90d）**、随机、A-beh 同表对比（B 相对体量的增量必须单独报）。
- 注意: B_act 与 A_vol 秩相关 0.93、top-100 Jaccard 0.46 —— 若正式版目标就是"未来活跃度"，
  B 的增量主要在回归 R²（+0.143），必须诚实报告"排序几乎=体量排序"的边界，不得包装成
  "发现新的重要钱包"。

### 1.2 次级 — Group C 结构重要性（as-of，`structure_pct` + `structure_novol_pct`）
- 理由: 独立于体量的第二维（与体量 ρ=0.57，去掉体量项后 top-10 lift 52.7× 于子图均值）；
  "结构 ≠ 预测影响"已有初步证据（vs P2 proxy ρ=−0.04）；桥/边界结构是 §12 动态社区叙事材料。
- 正式评估要求:
  1. 固定有向边语义（当前 flow 方向化后 PR 秩相关仅 0.591，须在正式版固定并报敏感性）；
  2. 多 cutoff 滚动 + 最终 holdout，与 A-vol 双基线并跑；
  3. 明确支持集 7,929（42.8%）限制：正式评估必须报"子图内 vs 全集（未命中钱包结构=未知）"
     两个口径，不得外推。
- 定位: 作为**结构侧描述/二级选择器**，不是未来活跃度的主选择器（vol 恒>struct）。

### 1.3 基线（必跑，非"方法"）
- A-vol（evt_cnt_90d）、A-beh（行为复合）、随机、B_new、C_novol、D_ig_cp（辅助）。
- 这是方案 §14 基线层级的强制项；任何正式冻结评估都必须与这些基线同表。

## 2. 建议仅保留为描述性的定义（不升级为正式选择器）

| 定义 | 状态 | 原因 |
|---|---|---|
| Group A persona 聚类（K-means/GMM/HDBSCAN） | 描述性 | 离散画像、无标量排名；persona 对连续特征的 ΔR²≈+0.001（无增量）；高 HDBSCAN noise（45–47%） |
| Group A 序列 embedding（800 钱包 pilot） | 描述性 | 小样本 pilot（silhouette 0.232 vs 0.192），需扩样后才可评估 |
| Group D IG（y_active30 目标） | 描述性 | top-K 全为"可预测不活跃"钱包（fwd30_evt=0）；作为活跃度选择器无效；只能描述信息密度 |
| Group E Qwen 语义表示 | 描述性试点 | n=200；R_qwen OOF R² 0.23–0.34 低于数值（0.59–0.64）；拼接未超越纯数值；互补性未证实 |
| Group C 动态社区 / D 社区掩蔽 | 描述性 | 社区 switch rate 口径粗糙（月度节点集漂移）；掩蔽为面板 i.i.d.，跨钱包影响未覆盖 |

> 这些定义可作为论文的"表示层/结构层"描述性贡献，但**不得**作为 Phase-II 推理分配预算的
> 正式选择依据，除非补充：(a) 更大样本；(b) 多 cutoff 冻结评估；(c) 独立有效性验证。

## 3. §18 开放轨道提案（按同一时间评估标准评审）

所有开放定义必须与 §13 一致: 特征/选择只用 ≤t → 冻结 top-K → fwd30 评估；并报告
支持集受限口径。建议按优先级：

### 3.1 高优先（数据已具备，可立即接入）
1. **Behavioral surprise（行为惊讶）** — 定义: 钱包 t 时刻行为向量相对其自身/所在 persona
   原型的偏离（如 to cluster centroid 的 as-of Mahalanobis/欧氏距离，或相对上月特征位移
   `‖Z_i(t) − Z_i(t−30d)‖`，全部 as-of）。假说: 高惊讶钱包未来行为更不确定/更易剧变。
   评估: 冻结 top-K 的 fwd30 活动/lift + 未来行为变异性（fwd30 分布方差）。可直接用 A 的
   月度 as-of 特征（`asof_monthly_2022.parquet`）。
2. **Bridge importance（桥重要性，正式化）** — C 已有 `bridge_score`/`cross_comm_share`/
   `is_boundary`（top-100 中 88% 是 bridge-only）。正式化: 固定 as-of 社区口径 + 月度社区
   匹配（区分"集合漂移 vs 归属变化"），评估 bridge top-K 的 fwd30 网络行为（新边、跨社区边）。
3. **Influence novelty（影响力新颖性）** — 定义: 预测信息增益超出"由历史体量/常规行为可预期"
   的部分。D 已有 `ig_resid_logvol`（IG 对 log1p(volume) 残差，OLS R²=0.025）。正式化:
   用多特征残差 + 时间去趋势，评估 top-K 残差钱包是否"低量高信息"且未来稳定（D §5.5 显示
   n=15 低量高影响组均值 IG +1.61、均值 volume $2，需在 walk-forward 上复核）。

### 3.2 中优先（需要事件级任务/新标签，本阶段只做设计）
4. **Propagation importance（传播重要性）** — 需要事件级 next-counterparty 评估
   （`nc_ranker_samples_v2` 支持集 vs full-vocabulary 双口径），或在 TGB 动态图基准上做
   节点删除/扰动传播实验。当前面板级 i.i.d. 无法覆盖跨钱包传播，须先建事件级评估再升级。
5. **Influence concentration（影响力集中度）** — 以社区/对手方为粒度聚合预测影响或 IG；
   需先固定社区匹配算法。

### 3.3 明确排除（Phase-II 范畴）
6. **Reasoning-worthiness（推理价值）** — 需要 Phase-II 的 deliberation 收益标签；
   P1/P2 proxy（ICF/trigger）不足以作为推理价值证据，不得升级。

> 开放轨道铁律: 不因"听起来新颖"而豁免时间评估；任何新定义与 B_act/A_vol 基线同表，
> 若增量 ≈0 则如实报告（方案 §10 "Do not assume these groups exist"）。

## 4. FINAL 组交付建议（汇总）

1. **主选择定义** = B 预测影响（活动水平），**强制并跑基线** A-vol / A-beh / 随机 / B_new；
2. **结构侧** = C `structure_pct`/`structure_novol_pct`（描述性 + 二级），**信息侧** =
   D_ig_cp（辅助，目标绑定 y_cp_ge10）；
3. 评估协议: 多 cutoff walk-forward（05/06/07/08 训练滚动，09-01 最终 holdout 冻结一次），
   K∈{10..1000}，指标 = fwd30 均值/lift、Recall@K、MRR、与基线增量、utility-per-wallet；
   报告支持集受限（7,929/2,999/1,283）与全集（18,519）两套口径；
4. 不把 proxy 成本、图中心性、预测 R² 重贴为"因果影响/市场影响力/推理收益"；
5. 发布叙事: "新任务（预算化钱包选择，as-of）+ 强基线 + 我们的选择器增量"（Group F P4），
   外部通道用 TGB tgbl-coin-v2（leaderboard 实测 MRR 0.832）与 EX-Graph LP（官方 split）；
   任何数字带样本与 cutoff。

## 5. 本建议的未验证项
- 多 cutoff walk-forward 尚未运行（B/C/D 现为单 cutoff 09-01）；本建议依赖其将来结果。
- next-counterparty MRR、事件级传播、E 组大样本互补性、TGB/EX-Graph LP 跑分未完成。
- 正式冻结评估须由 FINAL 组按上述协议执行并在独立 holdout 上复核本建议中的选择器。
