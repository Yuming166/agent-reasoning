# Group B — Predictive-Influence-First：钱包重要性的预测影响定义与首次 OOS 证据

> 状态：**设计文档 + 首次严格 OOS 证据已完成**（2026-09-11，cloud82）。
> 依据冻结协议 `research/audit/temporal_protocol.yaml`（Group 0, v1.0）与
> `research/audit/DATA_AUDIT.md`。所有数字均为描述性/初步，标注样本范围与 cutoff；
> **不声称因果、不声称有效性优越性、不声称 SOTA**（铁律）。

---

## 0. 一句话总结（claim boundary）

在 cutoff=2022-09-01、只用 <=cutoff 的 90 天历史状态、模型只在 2022-06-01 快照上训练
（严格时序 OOS：train 06-01 / val 07-01 / frozen test 08-01 / final holdout 09-01）的设定下：

- **未来 30 天活动水平（log1p(fwd30_evt_cnt)）可被显著预测**：holdout09 上 LightGBM
  R²=0.617、Spearman=0.812、top-10% 检索 Recall@K=0.653；
- **未来 30 天新对手方/新边形成（log1p(fwd30_new_cp)）可被显著预测**：holdout09 上
  R²=0.564、Spearman=0.698、Recall@K=0.597；
- **多特征模型超过单特征 persistence 基线，但增量中等**：活动水平 R² 相对最优基线
  （active_days_90d，R²=0.474）+0.143；新边 R² 相对 cp_distinct_90d（R²≈-2.0 的
  persistence 直用）提升明显，但 Spearman 只 +0.036、Recall@K +0.025；
- **扩展特征组（轨迹/网络/USD）几乎不增加预测力**（09-01 内切分消融：R² +0.010、
  AUC +0.004），与既有证据"activity 特征已强、footprint/influence 几乎无增量"一致；
- **预测影响是持久的（月度 top-10% 重叠 ≈60-64%）、跨 Aug→Sep regime 稳定、且高度
  集中在少数社区**（社区 5+8 占人口 17.5%，却承载模型预测 top-10% 的 ≈93%）。

这些数字只回答"历史状态对未来的**描述性**预测增益"；**预测影响 ≠ 因果影响**（见 §14）。

---

## 1. Research Question

**主问题（Phase I）**：Which Ethereum wallets are worth paying attention to, at what time, and why?

**Group B 子问题**：钱包 i 在 cutoff t 的**历史状态** S_i(t)（只含 <=t 的信息）能否显著
改善对**未来生态行为** Y_i(t, t+30d) 的预测？若能，改善多少、是否持久、是否因 regime /
community 而异？

## 2. Hypothesis

> **H_B：钱包重要性的最佳定义是"其历史状态对未来生态行为的可预测性增益"。**
> 即：i 重要 ⇔ 把 S_i(t) 加入预测器后，未来行为 Y_i(t,t+30d) 的不确定性下降最多。

可证伪版本：若最优多特征预测器相对"历史活跃度/对手方数/度"等朴素基线的增益≈0，
则该定义在选定目标上不提供额外排序能力（失败模式见 §10）。

## 3. Importance Definition（本组操作化）

对目标 Y（未来 30 天行为）定义**预测重要性分数**：

```
importance_B(i, t) = score( Y_i(t,t+30d) | S_i(t) )   # 模型输出（分类概率或回归水平）
                     - score( Y_i(t,t+30d) | naive(i,t) )  # 相对基线增益（组级比较）
```

- 本组**不做逐钱包因果识别**：score 是描述性预测（条件期望/概率），不是反事实干预。
- 与 Group C（结构中心性）、Group D（信息增益/遮蔽）的区别：B 用**端到端预测增益**
  直接衡量"历史状态对未来行为的可预测性"，不假定图结构或因果机制。

## 4. 目标选择（Target Selection）

候选目标（方案 §Group B Possible targets）：未来活动水平 / 未来边数 / 下一交互对象 /
未来社区演化 / 聚合生态活动 / 未来交易方向 / 未来流量类别。

本组**首次证据实现 2 个目标**（在 5 个快照上都有冻结标签、成本低、口径干净）：

| 目标 | 标签 | 类型 | 语义 |
|---|---|---|---|
| T1 未来活动水平 | `fwd30_evt_cnt`（log1p 变换） | 回归 + 伴随二分类（>0） | [t, t+30d) 内该钱包 primary 事件数（external_tx + token_transfer） |
| T2 未来边数/新交互对象 | `fwd30_new_cp`（log1p 变换） | 回归 + 伴随二分类（>0） | [t, t+30d) 内新出现对手方数（90 天窗口内未见过） |

**未实现（留给后续/其他组）**：
- **下一交互对象（next counterparty）**：本质是检索/排序任务（MRR/Recall@K），
  需要 `nc_ranker_samples_v2` 的候选池语义（sentinel g_rank=99999，支持集 vs full
  vocabulary 必须分开报告）。本组把 MRR 定义在"top-10% 未来活动检索"上（§6），
  下一对手方的 MRR 实验与 Group C/D 共享候选池。
- 未来社区演化 / 聚合生态活动 / 流量类别：需要额外标签工程，不在本次范围。

## 5. 预测器（Predictors）

| 模型 | 用途 | 说明 |
|---|---|---|
| Logistic / Ridge（线性） | 分类 / 回归 | StandardScaler + L2；作为线性基线 |
| HistGradientBoosting (sklearn) | 分类 / 回归 | 300 iters、lr=0.05、max_leaf_nodes=31 |
| LightGBM | 分类 / 回归 | 300 iters、lr=0.05、num_leaves=31、CPU、early stopping on val(07-01) |

- 特征：24 个 base as-of 特征（90 天 lookback `[t-90d, t)`，全为 primary 事件聚合：
  activity / capital / counterparty / diversity / reciprocity / entropy 等，见
  `run_predictive.py::BASE_FEATURES`）。
- 09-01 扩展特征（轨迹/网络/USD）仅在**探索性消融**中启用（`run_extended09.py`），
  不进入冻结时序结果。

## 6. 评估指标（Metrics）

| 指标 | 目标 | 定义/说明 |
|---|---|---|
| AUC / PR-AUC | 二分类 | 未来活跃 / 未来新边 二分类 |
| Log-loss (NLL) | 二分类 | 概率校准敏感 |
| Brier | 二分类 | 均方概率误差 |
| ECE（10 bin） | 二分类 | 校准误差 |
| RMSE / MAE / R² | 回归 | log1p 水平 |
| Spearman ρ | 回归 | 排序一致性 |
| Recall@K / MRR | 排序（检索） | 见下 |

**检索指标定义（本组）**：在 holdout 钱包集上按预测值降序排序，真实 top-K（K=10%）
钱包出现在前 K 的比例 = Recall@K；MRR = 真实 top-K 各钱包排序位置的倒数均值。
MRR 数值很小（≈0.004）是定义使然（对 ~1852 个真实 top 项取均值），**Recall@K 才是
可解释的排序指标**；若要做"下一对手方"MRR，需切换候选池语义（§4）。

## 7. Baselines（基线）

| 基线 | 说明 | 状态 |
|---|---|---|
| persistence：预测=历史值 | `log1p(evt_cnt_90d)` / `log1p(active_days_90d)` / `log1p(cp_distinct_90d)` | 回归 + 排序 |
| 单特征 univariate Logistic | 仅用 1 个历史特征（在 06-01 训练） | 二分类 |
| 静态全窗口 PageRank | `static_prior_20220901.csv`（全窗口静态先验） | **仅 holdout09 基线**，按协议不得作为 as-of 特征 |

## 8. 数据与时间协议（无未来泄漏）

- 窗口：dev 事件 2022-03-01..2022-09-01，holdout 事件 2022-09-01..2022-10-01（半开区间）。
- 快照：train=2022-06-01（20,341），val=2022-07-01（19,734），frozen test=2022-08-01
  （19,062），final untouched holdout=2022-09-01（18,519）；2022-05-01（19,649）保留未用。
- 特征：只读 `wallet_asof_features_v1`（05-08）与 `wallet_asof_features_20220901`（09）
  的 `*_90d` 特征（严格 < snapshot），静态先验/未来信息一律不进入特征。
- 标签：`fwd30_*` = `[t, t+30d)`；09-01 标签从 BigQuery 有界拉取
  （`fetch_labels.py`，bytesBilled=10MB），与 Group A 本地 parquet 逐行 parity 校验 = 0 diff。
- 切分：只有时序切分（train < val < frozen test < holdout），无随机切分（协议 §4）。
- 09-01 扩展特征消融是**唯一**非时序切分实验，使用确定性 address-hash 钱包切分
  （train/val/test=11111/3696/3712），**明确标记为探索性/事后分析，不是冻结 OOS 结果**。

---

## 9. 首次证据（First Evidence，严格 OOS）

样本：train=2022-06-01（20,341 钱包）、val=07-01（19,734）、frozen test=08-01（19,062）、
final holdout=09-01（18,519）。特征 24 个 base as-of（90d lookback < cutoff）；
标签 [cutoff, cutoff+30d)。模型仅在 06-01 训练，07-01 早停/选阈值，08-01 冻结测试，
09-01 最终 holdout（模型从未见过）。

### 9.1 主结果（LightGBM，CPU）

| 目标 | 指标 | frozen test 08-01 | holdout 09-01 |
|---|---|---|---|
| 未来活动水平 (log1p) | R² | 0.602 | **0.617** |
|  | Spearman ρ | 0.784 | **0.812** |
|  | Recall@10% | 0.614 | **0.653** |
| 未来新边 (log1p) | R² | 0.556 | **0.564** |
|  | Spearman ρ | 0.702 | 0.698 |
|  | Recall@10% | 0.595 | **0.597** |
| 未来活跃 (>0) | AUC | 0.882 | **0.891** |
|  | PR-AUC | 0.959 | **0.966** |
|  | Brier | 0.122 | 0.119 |
|  | Log-loss | 0.374 | 0.363 |
|  | ECE | 0.057 | 0.073 |
| 未来新边 (>0) | AUC | 0.849 | 0.848 |
|  | PR-AUC | 0.894 | 0.889 |
|  | Brier | 0.156 | 0.157 |
|  | Log-loss | 0.473 | 0.475 |
|  | ECE | 0.016 | 0.015 |

### 9.2 基线对比（holdout09）

| 基线 | 活动 R² | 活动 ρ | 活动 R@K | 新边 ρ | 新边 R@K | 活跃 AUC | 新边 AUC |
|---|---:|---:|---:|---:|---:|---:|---:|
| evt_cnt_90d (persistence) | -0.834 | 0.741 | 0.604 | 0.656 | 0.539 | 0.850 | 0.824 |
| active_days_90d | 0.474 | 0.790 | 0.620 | 0.669 | 0.552 | 0.876 | 0.832 |
| cp_distinct_90d | 0.087 | 0.765 | 0.626 | 0.662 | 0.572 | 0.858 | 0.826 |
| 静态全窗口 PageRank（仅基线） | -1.758 | 0.475 | 0.369 | 0.389 | 0.336 | — | — |
| **LightGBM（本组）** | **0.617** | **0.812** | **0.653** | **0.698** | **0.597** | **0.891** | **0.848** |

**解读**：
- 历史状态对未来活动/新边的预测力**强且显著**（AUC≈0.85-0.89；log 水平 R²≈0.56-0.62）。
- 相对最优单特征基线：活动 R² +0.143、Recall@K +0.027；新边 Spearman +0.036、
  Recall@K +0.025；二分类 AUC +0.015~0.016、Brier -0.007~-0.009。
- **增量中等**：历史活跃度本身已解释大部分可预测性；多特征模型带来的是"更优的排序/
  校准"，不是数量级改进。静态 PageRank 作为 as-of 预测器很差（R²<0）。

### 9.3 扩展特征消融（09-01 内确定性钱包切分，**探索性/事后**，非冻结结果）

| 特征集 | 活跃 AUC | 新边 AUC | 活动 R² | 新边 R² |
|---|---:|---:|---:|---:|
| base | 0.890 | 0.842 | 0.695 | 0.550 |
| base+traj | 0.892 | 0.845 | 0.703 | 0.555 |
| base+net | 0.890 | 0.843 | 0.694 | 0.548 |
| base+usd | 0.890 | 0.845 | 0.695 | 0.555 |
| all | 0.894 | 0.845 | 0.705 | 0.558 |

轨迹/网络/USD 扩展特征组增量 ≤ +0.010 R² / +0.004 AUC：**在 09-01 单快照上几乎无增量**。
（该结论只覆盖 09-01 快照的扩展特征；不排除更长历史/不同特征工程有增量。）

### 9.4 持久性 / regime / community 检查

**持久性（跨 05→09 相邻快照，公共钱包集）**：

| 相邻对 | n 公共 | 未来活动 ρ | 历史活动 ρ | top-10% 未来活动 Jaccard |
|---|---:|---:|---:|---:|
| 05→06 | 19,571 | 0.791 | 0.969 | 0.616 |
| 06→07 | 19,376 | 0.775 | 0.953 | 0.639 |
| 07→08 | 18,627 | 0.729 | 0.934 | 0.600 |
| 08→09 | 17,787 | 0.788 | 0.924 | 0.628 |

→ "重要（高未来活动）钱包"月度排序 ρ≈0.73-0.79，top-10% 重叠 60-64%：**持久但每月
约 36-40% 轮换**；历史活跃度本身更稳定（ρ 0.92-0.97）。

**Regime 特定性**：
- Aug（dev 内冻结测试）→ Sep（最终 holdout）：活动 R² 0.602→0.617、AUC 0.882→0.891，
  新边 AUC 0.849→0.848。**OOS 性能稳定（略升），未出现 regime 崩塌**（但仅覆盖 2 个
  相邻月份，不能外推更远 regime）。
- Aug→Sep 实际 top-10% 轮换：Sep 的 top-10% 中 **37.2% 不在 Aug top-10%**（Jaccard 0.628）。

**Community 特定性**（Group A `full_asof__kmeans` 10 社区，09-01）：

| 社区 | 人口占比 | 平均未来活动 | 平均未来新边 | 模型预测 top-10% 占比 | 未来活跃 AUC |
|---|---:|---:|---:|---:|---:|
| 5 | 4.8% | 128.6 | 49.5 | **40.9%** | 0.834 |
| 8 | 12.7% | 43.5 | 17.0 | **52.3%** | **0.946** |
| 7 | 16.0% | 23.1 | 7.7 | 6.6% | 0.876 |
| 6 | 5.0% | 15.4 | 1.7 | 0.2% | 0.918 |
| 1 | 7.8% | 10.2 | 3.6 | 0.0% | 0.837 |
| 4 | 18.4% | 9.2 | 3.3 | 0.0% | 0.763 |

→ **预测影响高度社区集中**：社区 5+8 仅占人口 17.5%，却承载模型预测 top-10% 的 ≈93%；
各社区可预测性差异大（未来活跃 AUC 0.76-0.95），社区 8 最可预测、社区 4 最不可预测。
（注：persona 是 Group A 在 09-01 快照上的聚类，社区标签本身依赖 <=09-01 特征。）

## 10. Expected Failure Modes（预期失败模式）

1. **预测力主要来自"历史活跃度"本身**：本组证据已确认增量中等（§9.2），若论文叙事把
   多特征模型说成"超越活跃度"会被审稿人击穿——应表述为"在活跃度基线上提供稳定但中等的
   排序/校准增益"。
2. **regime 漂移**：仅 2 个月 OOS，若后续月份市场/网络结构变化（如 2022 年底波动），
   R²/AUC 可能下降；需 walk-forward 扩展。
3. **候选池/下一对手方 MRR 陷阱**：若切换到 next-counterparty，必须区分支持集
   （nc_ranker_samples_v2 g_rank=99999 sentinel）与 full vocabulary，否则重演
   "August MRR 0.896"式虚假增益（memory Task 6 教训）。
4. **社区标签循环性**：persona 由 <=09-01 特征聚类，若用社区做预测特征需 as-of 版本；
   当前只用社区做**描述性分层报告**，未作为特征。
5. **标签口径**：fwd30 标签只含 primary 事件族（external_tx + token_transfer），
   trace 仅辅助，不能宣称"全生态活动"。
6. **样本范围**：18.5k 钱包、单月 holdout、单一目标窗口（30d）——所有数字只在此范围
   有效，不得推广到 27,613 全地址或更长窗口。

## 11. Compute Cost

- 全程 CPU（LightGBM/HistGBM/sklearn，`.venv-cuda`），未用 GPU。
- BigQuery：`fetch_labels.py` 单次有界拉取 bytesBilled=10MB；本组**未查询任何原始事件表**。
  总 BQ 计费 << 3GiB（Group B 全组上限），实际 ≈10MB。
- 单次主实验约 10s、扩展消融约 9s、持久性/社区约 2-3s（8 核 CPU）。

## 12. Novelty（相对既有工作，仅按本方案范围陈述）

- 本组不声称"没有人做过"。相对本项目已有积累（memory：Stage-1 learned node selector、
  P1/P2 influence proxies、`wallet_importance_ranking_v1` 的 P3 同快照演示排序）的新点：
  1. **重要性定义改为"端到端 OOS 预测增益"**，并用**冻结时序协议**（train 06/val 07/
     frozen 08/holdout 09）跑出可复现数字，替代"同快照 fwd30 排名演示"（P3 泄漏口径，
     协议 §3.3 已标注不得作为无泄漏选择器）。
  2. **显式回答"预测影响是否持久/regime 特定/community 特定"**（§9.4），给出量化边界
     （top-10% 月度轮换 36-40%、社区集中 ≈93%）。
  3. 与既有 P1/P2 代理（ICF / trigger proxy，与 reasoning gain 近似正交）分离：
     本组只报**行为预测**，不把预测增益包装成市场影响力（memory：
     "P1/P2 不能预测 LLM deliberation 增益"）。
- 与 Group C/D 的分工：C 做结构中心性、D 做信息增益/遮蔽，本组做端到端预测增益；
  三者可横向比较（research/README.md 擂台规则）。

## 13. 泄漏检查（Leakage Checks）

- **特征无未来**：全部 24 个 base 特征为 `*_90d`（`[t-90d, t)`，strictly before），
  由 Group 0 冻结 SQL 构建；静态全窗口 PageRank 仅作基线、未进入特征（协议 §3.4）。
- **标签有未来但只用于评估**：fwd30 标签窗口 `[t, t+30d)`；模型训练/早停只用 train/val
  快照（其标签窗口在各自快照之后、与特征无重叠）；frozen test 与 final holdout 的标签
  从未参与拟合或超参选择。
- **时序切分**：train < val < frozen test < holdout，无随机切分；05-01 快照保留未用。
- **09-01 标签 parity**：BigQuery 拉取 vs Group A 本地 parquet 逐行 0 diff
  （`fetch_labels.py` 输出）。
- **P3 演示列排除**：`importance_proxy_p3`（同快照 fwd30 泄漏口径）在特征矩阵中显式
  剔除，绝不作特征。
- **唯一非时序实验**（扩展特征消融）已明确标注 exploratory/post-hoc（§9.3）。

## 14. 预测影响 ≠ 因果（明确声明）

本组所有结果都是**描述性预测**：`P(Y_future | S_history)` 的 OOS 条件预测质量。
这**不等于**：
- 该钱包"导致"了未来生态行为（无干预/工具变量/反事实识别）；
- 屏蔽该钱包会改变未来（那是 Group D 的遮蔽实验，需要 counterfactual masking）；
- 该钱包有市场影响力（那是 Tier3 市场验证，memory 已记录 top-100 事件研究的 Sep OOS
  方向反转，不能把预测增益当 alpha）。

凡引用本组数字，必须同时引用本声明与样本范围（18,519 钱包 / 2022-09-01 / 30d 标签）。

## 15. 复现（Reproducibility）

环境：`.venv-cuda`（pandas 3.0.5 / sklearn 1.9.0 / lightgbm 4.7.0 / scipy 1.18.1，
纯 CPU）。BigQuery 经代理 `http://10.63.0.72:7890` + ADC，有界查询。

```
# 1) 拉取 09-01 未来标签（BQ，bytesBilled≈10MB）并做本地 parity 校验
.venv-cuda/bin/python research/groupB_predictive/fetch_labels.py

# 2) 主实验（冻结时序 OOS）：train 06 / val 07 / frozen 08 / holdout 09
.venv-cuda/bin/python research/groupB_predictive/run_predictive.py

# 3) 探索性：09-01 扩展特征消融（非时序，明确 post-hoc）
.venv-cuda/bin/python research/groupB_predictive/run_extended09.py

# 4) 持久性 / regime / community 检查
.venv-cuda/bin/python research/groupB_predictive/persistence_analysis.py

# 5) 描述性图（社区集中度 + 校准曲线）
.venv-cuda/bin/python research/groupB_predictive/make_figure.py
```

输入（只读复用 Group A 产物）：`research/groupA_behavior/results/data/`
`feature_matrix_20220901.parquet`、`asof_monthly_2022.parquet`、`static_prior_20220901.csv`、
`results/persona_assignments_20220901.csv`。
输出：`results/predictive_results_20220901.json`、`results/holdout09_predictions.csv`、
`results/predictive_extended09_ablation.json`、`results/persistence_regime_community_20220901.json`、
`results/data/labels_20220901_bq.csv`、`results/figures/groupB_figures.png`。

## 16. 文件清单

| 文件 | 说明 |
|---|---|
| `README.md` | 本设计文档 + 首次证据 |
| `fetch_labels.py` | BQ 有界拉取 09-01 标签 + parity 校验 |
| `run_predictive.py` | 主实验：冻结时序 OOS，4 目标 × 3 模型 + 基线 |
| `run_extended09.py` | 探索性：09-01 扩展特征消融（post-hoc） |
| `persistence_analysis.py` | 持久性 / regime / community 检查 |
| `make_figure.py` | 描述性图 |
| `sql/pull_labels_20220901.sql` | 有界标签查询（分区过滤） |
| `src/bq_client.py` | BQ 客户端（代理 + ADC + bytes 上限） |
| `results/*.json|csv|png` | 全部结果与图 |

## 17. 未完成项

1. **下一交互对象（next-counterparty）MRR**：需接入 `nc_ranker_samples_v2` 候选池语义
   （支持集 vs full-vocabulary 分开报告），本组仅定义了 top-10% 检索 MRR。
2. **walk-forward 扩展**：05-01 快照保留未用；后续可在 06 训练基础上做 07/08/09 滚动
   再训练，检验长 horizon 稳定性。
3. **更长窗口/更远 regime**：当前仅 30d 标签、2 个月 OOS；可扩展到 60/90d 标签与
   2022-10 之后（需新事件表，受 Group 0 数据窗口限制）。
4. **与 Group C/D 的横向比较**：同一 holdout 上的结构中心性排名 vs 预测增益排名。
5. **社区 as-of 特征**：若要把 persona 作为预测特征，需重建 <=cutoff 的 as-of 聚类，
   避免循环；当前只做描述性分层。
