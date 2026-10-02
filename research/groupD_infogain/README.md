# Group D — Information-Gain / Counterfactual-First（预测信息增益）

> 角色: Group D（Information-Gain / Counterfactual-First）
> 方案依据: `research/autoresearch_phase1.md` §Group D、§10 Influence Residual、§13 评估协议
> 冻结协议: `research/audit/temporal_protocol.yaml` v1.0 + `research/audit/DATA_AUDIT.md`（Group 0）
> 本机: cloud82 (10.63.0.82)。状态: **首次证据已跑通（有界样本，非全 27k）**，2026-09-11。

---

## 0. 结论摘要（claim 边界先行）

- 本组产出的全部数字是 **预测信息增益（predictive information gain）**，衡量"钱包的历史信息对
  **预测该钱包自身未来** 的不确定性削减"，**不是** 因果影响、不是市场导向影响、不是跨钱包影响。
- 在 cutoff=2022-09-01、代表性子集 n=2,999 上，全上下文预测（HistGBM, 5 折 CV, 目标=未来
  ≥10 个对端 `y_cp_ge10`）AUC=0.928 / NLL=0.337；把钱包特征掩蔽为基线中位数后 AUC≈0.50 /
  NLL=0.742（ΔNLL=+0.406）。钱包级历史信息显著降低自身未来不确定性 ⇒ 假设在该任务口径下成立。
- 掩蔽 **top-K 高 IG 钱包** 的 ΔNLL(+1.79, K=100) 约为掩蔽 **top-K 高量钱包**（+0.99）的 1.8 倍
  ⇒ IG 排序选出的钱包比纯 volume 排序的信息密度更高。
- §10 残余分析: **低量高影响 / 高量低影响 两类都存在**（见 §6.4）。IG 与 volume/degree/PageRank/
  已有 ICF 排名的 Spearman 仅 0.20–0.37，top-K Jaccard 重叠远低于 1 ⇒ IG 是区别于"体量/结构中心性"
  的一维重要性信号。
- **未做**: 全 27k 钱包大规模实验、事件级（next-counterparty）跨钱包 IG、因果推断、任何 LLM、
  GPU、整表导出。这些是明确的未完成边界（见 §10）。

---

## 1. Research Question & Hypothesis

**RQ**: 在 cutoff t，钱包 i 的哪些信息 X_i(t) 显著降低"未来 Y"的不确定性，从而值得被列为"重要钱包"？

**Hypothesis（Group D）**:

> An important wallet is one whose historical presence or information substantially
> reduces uncertainty about the future.
>
> IG_i(t) = H(Y_future | C_t) − H(Y_future | C_t, X_i(t))

本组把它落实为**面板级自预测信息增益**（self-predictive information gain）:

- Y_future = 钱包在 `[t, t+30d)` 的未来活动标签（fwd30，二值化）；
- C_t = 其他钱包（模型在除 i 外的训练上下文上拟合）+ 中性基线历史；
- X_i(t) = 钱包 i 在 `[t−90d, t)` 的 as-of 特征（Group A 已产出，防泄漏审计通过）；
- IG_i(t) = H(Y_i|C_t) − H(Y_i|C_t, X_i(t))，用 5 折 CV + 输入掩蔽（occlusion）的 ΔNLL 估计。

> 面板行之间 i.i.d.，因此该口径测量"钱包自己的历史→自己的未来"，**不**覆盖"钱包 i 的历史→
> 钱包 j 的未来"（跨钱包影响）。后者是事件/候选级任务（next-counterparty occlusion），本组已有
> 对照 proxy（ICF v2alpha candidate occlusion），作为边界说明（见 §10 未完成项）。


---

## 2. 数据与口径（冻结协议锚定）

| 项 | 值 |
|---|---|
| cutoff | 2022-09-01（dev 快照 `wallet_asof_features_20220901`） |
| lookback | `[2022-06-03, 2022-09-01)`（严格 < cutoff） |
| label window | `[2022-09-01, 2022-10-01)`（fwd30，来自 Group A 防泄漏矩阵） |
| 样本 | 全量 18,519 钱包 → 代表性子集 **n=2,999**（按主目标分层抽样，seed=20220901） |
| 特征 | 52 个 as-of 特征（volume/diversity/trajectory/network 四块）；`static_prior` 仅作对照基线，**不进模型** |
| 目标 | 主: `y_cp_ge10` = fwd30_cp_distinct ≥ 10（未来互动广度，正样本率 0.413）<br>次: `y_active30` = fwd30_evt_cnt > 0（未来活跃，正样本率 0.765） |
| 预测器 | LogisticRegression(L2, 标准化) 与 HistGradientBoostingClassifier，5 折 StratifiedKFold，CPU |
| 排除 | `importance_proxy_p3`（同快照 fwd30 的 P3 演示标签）不参与训练/评估 |
| 大查询 | 仅拉取紧凑对照表 `p1_wallet_icf_v2`（snapshot 08-01，4,969 行），bytesBilled 共 ≈30MB |

**为何用单一 cutoff 的 wallet 级 CV 分割**：协议 §4 的"chronological split only"约束的是跨时间窗口
（train<val<test<holdout）不混用。本组全部实验在单一 cutoff 快照内完成：所有特征先于 cutoff、
所有标签在同一 fwd30 窗口，wallet 级 CV 不产生跨窗口/未来泄漏；holdout 窗口仅作为标签来源
（方案明确指定 Group D 首次证据用 cutoff=2022-09-01），不对方法做最终 OOS 裁决。

---

## 3. 方法：IG 定义与掩蔽变体

### 3.1 核心算法（wallet masking）

```
5 折 CV:
  对每个 wallet i（在 eval fold）:
    p_full  = P(Y_i | C_t, X_i(t))      # 模型在 train fold（其他钱包）上拟合，用 i 的真实特征
    p_mask  = P(Y_i | C_t)              # 同一模型，把 i 的特征替换为 fold-train 中位数（中性历史）
    IG_i(t) = NLL(p_mask) − NLL(p_full) # 每个样本的真实类 NLL；>0 = 历史降低不确定性
```
- 全部评估为 **out-of-sample**（i 不在训练集中），避免"模型见过 i 的标签"造成的过拟合虚高。
- 中位数掩蔽 = 把钱包替换成"代表性中性历史"，等价于在模型条件分布下近似 H(Y|C_t)。
- 补充 **permutation 掩蔽**（用另一个钱包的特征替换）做稳健性对照。

### 3.2 变体覆盖（方案 Group D 全 5 类）

| 变体 | 实现 | 脚本 |
|---|---|---|
| wallet masking | 钱包级输入掩蔽 ΔNLL（§3.1）+ top-K 子集掩蔽 ΔNLL/ΔAUC | `src/run_wallet_masking.py` |
| feature masking | 删特征块/单特征重训，5 折 CV 池化 ΔNLL/ΔAUC | `src/run_feature_masking.py` |
| community masking | persona 社区特征掩蔽 + 社区均值 IG（Group A persona 赋值） | `src/run_community_masking.py` |
| trajectory masking | 轨迹特征块整体删除（feature masking 的 trajectory 块） | `src/run_feature_masking.py` |
| influence residualization | IG 对 log(volume) 回归取残差（§10） | `src/run_residual.py` |


---

## 4. 评估协议（§13 对齐）

- **单一 cutoff**（2022-09-01，开发快照），5 折 wallet 级 CV（out-of-sample）。
- 指标: NLL（主）、AUC、Brier；钱包掩蔽补充 mean-p 漂移（单类子集 AUC 无定义时用 NLL/Brier）。
- **基线层级（§14）**: Random（随机 K，期望 Jaccard=K/N）、Size（volume K）、Structural
  （as-of degree / as-of PageRank / static-prior degree & PageRank【标注 leaky，仅对照】）、
  Predictive（已有 ICF v1/v2 排名）。
- 对比方式: IG 排序与各基线的 **top-K Jaccard 重叠**、**Spearman 秩相关**；top-K 掩蔽 ΔNLL 对比
  （IG top-K vs volume top-K）。
- **一致性**: 同目标跨模型 Spearman（HistGBM vs Logistic）与跨目标 Spearman 分开报告。
- **报告边界**: 支持集/全体、leaky 基线、cutoff 不匹配（ICF v2 只有 06/07/08 快照）均显式标注。

## 5. 首次证据结果（n=2,999, cutoff=2022-09-01）

### 5.1 wallet masking（核心）

| 模型/目标 | NLL full | NLL mask | ΔNLL | AUC full | AUC mask | IG 均值(中位) |
|---|---|---|---:|---:|---:|---:|---:|
| HistGBM / y_cp_ge10 | 0.3369 | 0.7424 | **+0.4056** | 0.9284 | 0.4998 | +0.406 (0.558) |
| Logistic / y_cp_ge10 | 0.3367 | 0.6912 | +0.3544 | 0.9305 | 0.4999 | +0.354 (0.526) |
| HistGBM / y_active30 | 0.3535 | 0.9144 | +0.5609 | 0.8885 | 0.4995 | +0.561 (0.774) |
| Logistic / y_active30 | 0.3420 | 0.6308 | +0.2889 | 0.8921 | 0.4993 | +0.289 |

- IG 分布（HistGBM/y_cp_ge10）: 25%≈0.155，中位 0.558，max 1.80，min −4.66。
  少数钱包 **IG<0**（历史反而误导预测，如"模型按历史高置信预测活跃、实际不活跃"）。
- permutation 掩蔽与中位数掩蔽 Spearman=0.61（方向一致，稳健）。

### 5.2 top-K 子集掩蔽（HistGBM / y_cp_ge10）

| 掩蔽子集 | n | ΔNLL | mean-p 漂移 | ΔAUC |
|---|---:|---:|---:|---:|
| top50 IG | 50 | **+1.796** | 0.986→0.164 | NA（单类，全 y=1） |
| top100 IG | 100 | +1.790 | 0.981→0.164 | NA（单类） |
| top500 IG | 396* | +1.627 | 0.907→0.177 | NA（单类） |
| bottom50 IG | 40* | **−2.695** | 0.520→0.339 | +0.553 |
| volume top50 | 50 | +0.988 | 0.958→0.363 | −0.677 |
| volume top100 | 100 | +0.992 | 0.943→0.354 | −0.417 |

*: n<K 为与 IG 子集在样本内并集去重后的实际钱包数（详见 JSON）。
解读: 掩蔽 **top-K IG** 钱包比掩蔽 **top-K volume** 钱包造成约 1.8 倍 ΔNLL ⇒ 高 IG 钱包的历史
信息密度高于单纯高量钱包；**bottom-K IG** 掩蔽反而降低 NLL（其历史是误导性信息）。

### 5.3 feature masking（HistGBM / y_cp_ge10；全量 18,519 稳健性见 JSON）

| 掩蔽块 | ΔNLL | ΔAUC | 说明 |
|---|---:|---:|---|
| volume | +0.0055 | −0.0013 | 体积/活动块（含冗余，边际信息小） |
| diversity（对端多样性） | **+0.0171** | −0.0065 | 信息量最大块 |
| trajectory | +0.0064 | −0.0026 | 轨迹节奏块 |
| network（as-of 度/PR） | −0.0009 | −0.0005 | 对"未来互动广度"几乎不增信息 |

- 单特征消融 top: `token_rows_priced`(+0.0108)、`last_event_recency_days`(+0.0107)、
  `max_gap_days`(+0.0090)、`cp_in_distinct_90d`(+0.0081)、`cp_reciprocity_90d`(+0.0074)、
  `asof_mm_clustering`(+0.0072)、`cp_distinct_90d`(+0.0071)。
- 特征级 IG（≤0.03）远小于钱包级 IG（top 达 1.8）⇒ 信息主要在**特征联合形态**，单特征高度冗余。


### 5.4 community masking（persona 级）

按 Group A persona 赋值（as-of 防泄漏），社区内钱包特征整体掩蔽 = 社区均值 IG：

| persona 列 | 最高 IG 社区 | n | base_rate | 社区均值 IG | 社区均值 volume |
|---|---|---:|---:|---:|---:|
| full_asof__kmeans | 5 | 139 | 0.971 | **1.019** | $292K |
| full_asof__kmeans | 8 | 384 | 0.914 | 0.899 | $143K |
| full_asof__kmeans | 9（最低） | 138 | 0.080 | 0.151 | $162 |
| network__kmeans | 1 | 75 | 0.933 | **1.032** | $351K |
| trajectory__kmeans | 1 | 621 | 0.837 | 0.800 | $193K |

解读: "高未来互动广度、高量"的行为社区是信息密度最高的钱包集合；低活跃社区的自身历史信息量低
（其未来本来就可由基线预测）。社区均值 IG 与社区掩蔽 ΔNLL 逐社区一致（内部一致性校验通过）。

### 5.5 §10 Influence Residual（IG 对 volume 残差化）

残差模型: `IG ~ log1p(volume_usd)`（OLS），slope=+0.306（正相关但不强），R²≈0.09。

| 组 | n | 均值 IG | 均值 volume | 存在性 |
|---|---:|---:|---:|---|
| **低量高影响** (vol≤Q1 & resid≥P90) | 15 | +1.613 | $2 | ✅ 存在 |
| **高量低影响** (vol≥Q3 & resid≤P10) | 87 | −1.319 | $47,807 | ✅ 存在 |
| 高中心性低影响 (as-of 度≥P90 & resid≤P10) | 6 | −1.46 | $12,410 | ✅ 存在（样本小） |
| 低中心性高影响 (as-of 度≤P10 & resid≥P90) | 62 | +1.676 | $169,285 | ✅ 存在 |

> 注意: "低量高影响"组大多为 $0 体积、低对端、未来稳定低活跃且可被历史高置信预测的钱包；
> 该组的 IG 语义是"可预测性"，**不是**市场/因果影响。§10 问的是"是否存在比体量更会说话的钱包"，
> 本组回答: 存在（预测信息维度），但必须按 §0 的 claim 边界解释。

### 5.6 与已有 ICF 排名对照

| 对照 | Spearman(IG,·) | 覆盖 |
|---|---:|---:|
| log volume | +0.306 | 2,999 |
| as-of undirected degree | +0.365 | 1,283（mm 子图内） |
| as-of PageRank | +0.246 | 1,283 |
| static-prior degree（**leaky 基线，仅对照**） | +0.196 | 2,999 |
| static-prior PageRank（leaky 基线） | +0.219 | 2,999 |
| ICF v1（本地 ranking，对照） | +0.214 | 796 |
| ICF v2（BQ 表，snapshot **08-01**，cutoff 不匹配，对照） | +0.227 | 781 |

top-K Jaccard（IG vs 基线，随机期望 K/N）:

| K | volume | as-of degree | static PR | ICF v1 | ICF v2 | 随机期望 |
|---|---:|---:|---:|---:|---:|---:|
| 50 | 0.12 | 0.04 | 0.10 | 0.12 | 0.12 | 0.017 |
| 100 | 0.20 | 0.15 | 0.16 | 0.10 | 0.09 | 0.033 |
| 250 | 0.30 | 0.29 | 0.25 | 0.22 | 0.23 | 0.083 |
| 500 | 0.44 | 0.41 | 0.33 | 0.39 | 0.40 | 0.167 |

解读: IG 排序与体量/结构/已有 ICF 排名相关性中等偏低（ρ≈0.2–0.37），top-K 重叠约 2–7 倍于随机
但远低于 1 ⇒ **IG 是独立于 volume/degree/PageRank 的一维预测重要性信号**，与方案"影响力≠交易量"一致。

### 5.7 一致性

- 同目标跨模型（HistGBM vs Logistic）: Spearman **0.86–0.91**（排序稳健）。
- 跨目标（y_cp_ge10 vs y_active30）: Spearman 0.23–0.35 ⇒ **IG 语义目标相关**，报告时必须绑定目标。
- 重训诊断: 从训练上下文移除 top-100 IG 钱包后，其他钱包的池化 ΔNLL≈−0.001（≈0）⇒ 面板行 i.i.d.，
  钱包在训练集中的"在场"对其他钱包预测无实质影响（跨钱包影响需事件/候选级任务，见 §10）。


---

## 6. 泄漏检查（checklist）

1. **特征全部严格 < cutoff**: 本组未发起新事件查询，直接复用 Group A 的 as-of 矩阵
   （`wallet_asof_features_20220901`，lookback `[2022-06-03, 2022-09-01)`，Group 0 审计通过）。
2. **标签全部 ≥ cutoff**: fwd30 标签窗口 `[2022-09-01, 2022-10-01)`，不参与特征构建。
3. **静态全窗口先验未进模型**: `static_prior_20220901.csv`（degree/PageRank 全窗口）只用于
   §10 对照与 top-K 重叠，**不是** as-of 预测特征（协议 forbidden_features）。
4. **P3 演示标签未使用**: `importance_proxy_p3`（同快照 fwd30，协议 §2.5 标注 leaky demo）排除。
5. **无价格/社交/未来特征**: 模型特征仅为 as-of 行为/轨迹/网络/美元特征；无价格、无推文。
6. **无循环**: 排序只用 `≤cutoff` 信息（特征→IG→排名）；未来标签只用于评估 IG 的 NLL/AUC，
   不参与选择（方案 §2 no-circularity）。
7. **out-of-sample 评估**: 5 折 CV，钱包 i 的 IG 均由其不在训练集内的模型预测计算。
8. **BigQuery 纪律**: 仅 3 次小查询（schema 检查 1× + 拉取 ICF v2 2×），全部 maximumBytesBilled
   上限 1GiB，实际 billed ≈30MB（<< 全组 3GiB 建议），无整表导出、无写操作。
9. **ICF v2 cutoff 不匹配已标注**: ICF v2 无 09-01 快照，用 08-01 对照并在所有表格标注。

## 7. 失败模式（expected failure modes）

| 失败模式 | 是否出现 | 说明 |
|---|---|---|
| IG 与 volume 共线（无新信息） | **否** | ρ(IG,log vol)=0.31；top-K 重叠 0.12–0.44 |
| 中位数掩蔽把所有钱包推向同一先验 → AUC≈0.5 无区分度 | 是（设计使然） | 因此主指标用 ΔNLL，单类子集 AUC 报 NA |
| 高 IG 全是最活跃/最不活跃的"极端可预测"钱包 | 部分 | top-10 IG 混合 $6K–$565K 与不同度；需目标绑定解释 |
| 掩蔽变体过强（中位数=摧毁全部信号） | 是 | 用 permutation 对照（ρ=0.61）缓解 |
| 面板 i.i.d. ⇒ 训练集移除钱包无跨钱包效应 | 是（已证实） | ΔNLL≈0；明确标注为边界，非本方法缺陷 |
| 单类子集无法算 AUC | 是 | top-IG 子集全 y=1；改用 ΔNLL/Brier/mean-p |
| 特征高度冗余 ⇒ 单特征消融增量小 | 是 | 特征块 ΔNLL≤0.03；与钱包级 ΔNLL 1.8 对比说明 |
| ICF 对照 cutoff 不匹配 | 是 | 显式标注 snapshot 08-01，仅作方向性对照 |

## 8. Compute Cost

- 全流程 **CPU only**（sklearn），无 GPU、无 LLM。
- 实测端到端 ≈5 分钟（wallet masking ~45s、feature masking ~105s、community masking ~160s、
  其余 <5s），内存 <4GB。
- BigQuery billed ≈30MB（ICF v2 对照拉取），远低于全组 3GiB 建议。
- 扩展到全量 18,519 钱包的 wallet masking 预估: occlusion 法随 N 线性，约 5–10 分钟即可；
  但按任务要求本轮**不做全 27k/全量**，仅在全量上验证了 2 个特征块（结果与子集一致）。

## 9. Novelty（边界谨慎表述）

- 无"没人做过"声明。本组定位: 在 EX-Graph 时序 Ethereum 面板上，把方案 §1 的
  IG_i(t)=H(Y|C_t)−H(Y|C_t,X_i(t)) 落成**可复现的 wallet-level occlusion ΔNLL**，并与
  volume/degree/PageRank/已有 ICF proxy 做系统对照（§10 残差 + top-K 重叠 + 一致性）。
- 首次证据的新意点（弱声明）: (a) 单 cutoff 面板级掩蔽变体矩阵完整跑通；(b) 明确发现
  "IG 与 volume/中心性/ICF 正交性"与"低量高影响/高量低影响"在预测信息维度存在；
  (c) 明确面板 i.i.d. 边界（跨钱包 IG 需事件级任务）。与 Group B（预测影响）的 learnability 增益、
  Group C（时序图）的拓扑影响保持**概念区分**，避免把 proxy 成本/图中心性重贴为 IG 提升。

## 10. 未完成项 / 边界

1. **事件级（next-counterparty）跨钱包 IG**: 在 `nc_ranker_samples_v2` 候选集上做 leave-one-out
   candidate occlusion（对照现有 `p1_icf_v2alpha_candidate_occlusion`），才是"钱包 i 影响钱包 j 未来"
   的正解；本轮仅给出面板级自预测 IG 并引用该 proxy 作对照。
2. **多 cutoff / walk-forward**: 本轮单 cutoff 09-01；§13 要求多窗口 + 冻结 top-K + 最终 holdout，
   需后续用 05/06/07/08 快照（`wallet_asof_features_v1`）扩展。
3. **K 敏感性（§16）**: 已给 top50/100/500 的掩蔽对照，但未来效用 vs K 的完整前沿未做。
4. **与 Group A/B/C/E 的横向融合（§17/§19）**: 未做；等待各组合拢后由首席科学家裁定。
5. **因果/市场影响（Tier 3）**: 明确不做（Group D 只报预测信息增益）。
6. **全 27k 实验**: 按要求不做；若后续需要，occlusion 法可线性扩展，重训法需近似（如 influence function）。

## 11. 文件与复现

- 设计文档: `README.md`（本文件）
- 入口: `./run_all.sh`（顺序执行 0→6 步并写 `logs/run_*.log`）
- 源码: `src/config.py`（口径）、`src/models.py`（模型/掩蔽）、`src/build_dataset.py`、
  `src/run_wallet_masking.py`、`src/run_feature_masking.py`、`src/run_community_masking.py`、
  `src/run_residual.py`、`src/run_ranking_compare.py`、`src/summarize.py`
- 结果: `results/`（JSON/CSV/parquet 全量见下），`results/external/p1_wallet_icf_v2_20220801.csv`
  为 ICF v2 对照拉取（snapshot 08-01）。
- 环境: `/storage/gaoym/ex-graph-microtransaction-analysis/.venv-cuda`（sklearn 1.9 / pandas 3.0）。
- 全部结果引用冻结协议 `research/audit/temporal_protocol.yaml` v1.0 方视为有效。

### results/ 文件清单

```
results/
├── dataset_manifest.json              # 样本/特征/目标口径
├── dataset_full_20220901.parquet      # 全量 18,519 钱包数据集
├── dataset_subset_20220901.parquet    # 代表性子集 2,999 钱包
├── wallet_ig_20220901.csv             # 每钱包每模型每目标: p_full/p_mask/IG_occ/IG_perm
├── wallet_masking_20220901.json       # 钱包掩蔽: 汇总 + top-K 子集 + 重训诊断
├── feature_masking_20220901.json      # 特征块/全量稳健性
├── feature_ablation_20220901.csv      # 单特征消融
├── community_masking_20220901.json    # persona 社区掩蔽
├── residual_20220901.json             # §10 残差 + 秩相关 + 分组
├── ig_vs_baselines_20220901.csv       # 每钱包 IG+基线+残差表
├── ranking_compare_20220901.json      # top-K 重叠 + 一致性 + 示例
├── SUMMARY.json                       # 汇总摘录
└── external/p1_wallet_icf_v2_20220801.csv   # ICF v2 对照（BQ 拉取, 08-01）
```
