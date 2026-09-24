# Decision-State V1：B0–B4 Degradation Analysis

**日期：2026-09-19**
**原则：只读冻结 predictions；不重新训练、不改概率、不重选 case**

## 1. 分析边界

本分析读取以下冻结产物：

- `decision_state_prompt_cases.csv`：3,000 cases；
- `hypothesis_panel_full.jsonl`：12,000 条冻结 LLM response；
- `decision_state_llm_features.csv`：冻结的结构化 LLM/intervention features；
- `decision_state_meta_predictions.csv`：冻结的 B0–B4 probabilities 与 per-target log loss；
- `decision_state_eval_cases.csv`：evaluation-only outcomes。

3,000 个 case 全部保留在：

```text
results/decision_state_case_degradation_analysis.csv
```

但现有冻结 prediction 文件只对 July development 和 August test 提供 out-of-sample prediction；June train 的 1,000 行没有 frozen prediction。为了遵守“不改任何 prediction”，本分析没有额外生成 June in-sample prediction。

因此：

```text
全部 case descriptor：3,000
有效 OOS loss delta：2,000
loss delta long rows：8,000 = 2,000 × 4 targets
```

所有相关性和 degradation 统计都明确区分 `dev`、`test` 和 `oos_all=dev+test`。

## 2. 定义

对每一个已有 OOS prediction 的 case，定义四个 target 的 log loss：

\[
\ell(B_k,Y_i)=-\log p_{B_k}(Y_i)
\]

B4 相对 B0 的 per-case macro degradation：

\[
\Delta_i
=
\frac{1}{4}\sum_t \ell(B4_{i,t},Y_{i,t})
-
\frac{1}{4}\sum_t \ell(B0_{i,t},Y_{i,t})
\]

- \(\Delta_i>0\)：B4 degradation；
- \(\Delta_i<0\)：B4 相对 B0 有 gain；
- `B4 predictive gain = -Δ`，正值表示 B4 更好。

Intervention sensitivity 定义为：

\[
S_i=
\frac{1}{2}
\left[
\frac{1}{4}\sum_t R_{self,i,t}
+
\frac{1}{4}\sum_t R_{market,i,t}
\right]
\]

其中每个 \(R\) 是 full 与对应 intervention consequence distribution 的 JS distance。

另报告 evidence-aligned margin：

```text
b4_relevant_minus_placebo
```

它是模型声称相关的 evidence response 与 placebo response 的差值。

## 3. B1–B4 在什么情况下 degradation

### 3.1 August test macro 结果

| Model | Mean Δ vs B0 | Median Δ | Degradation rate Δ>0 | Severe rate Δ>0.1 |
|---|---:|---:|---:|---:|
| B1 deterministic | +0.008218 | -0.000251 | 46.1% | 16.9% |
| B2 single LLM | +0.001063 | +0.001272 | 51.8% | 10.9% |
| B3 multi-hypothesis | +0.003137 | -0.007031 | 47.8% | 24.5% |
| **B4 verified LLM** | **+0.029560** | **-0.006318** | **48.4%** | **33.3%** |

B4 的一个重要特征是：**median Δ 略小于 0，但 mean Δ 明显大于 0。**

这说明 B4 不是“所有 case 都小幅变差”，而是：

> 一部分普通 case 的变化接近 0 或略有 gain，但少数 catastrophic degradation case 产生了很大的正向 log-loss tail，最终把 macro mean 推坏。

August test 的 Δ 分位数：

```text
min       = -2.362806
p01       = -1.268394
p05       = -0.632406
p25       = -0.146262
median    = -0.006318
p75       =  0.184797
p95       =  0.778142
p99       =  1.353646
max       =  1.901705
```

最大的 10% degradation cases 贡献了全部正向 Δ 总量的约 **56.9%**；最大的 5% 贡献约 **36.0%**；最大的 1% 贡献约 **10.2%**。因此主门失败主要由 **tail-risk / overconfident wrong consequences** 驱动，而不是简单的全体平均小幅退化。

### 3.2 按 prediction target

August test 上 B4 相对 B0 的平均 per-target Δ：

| Target | Mean Δ(B4−B0) | Degradation rate | Severe rate Δ>0.1 |
|---|---:|---:|---:|
| activity | **+0.042426** | 48.5% | 32.9% |
| active days | **+0.027778** | 48.7% | 33.2% |
| counterparty breadth | **+0.031579** | 50.5% | 33.1% |
| new counterparties | **+0.016458** | 49.4% | 30.5% |

四个 target 的 mean Δ 全部为正；activity 的 degradation 最大，new counterparties 相对最小。

### 3.3 按 activity bin

| Activity bin | n | Mean Δ(B4−B0) | Severe rate |
|---|---:|---:|---:|
| 1–2 | 250 | +0.033609 | 24.8% |
| 3–9 | 250 | +0.015355 | 32.8% |
| 10–19 | 250 | +0.017615 | 33.6% |
| 20+ | 250 | **+0.051663** | **42.0%** |

最高 activity bin 的 B4 degradation 最明显，尤其是严重 degradation 比例达到 42.0%。不过低活跃 bin 也没有获得正向总体收益。

### 3.4 Repeat vs unseen wallet

这里的 repeat 定义为：该 address 在冻结 3,000-case panel 中已经在更早 cutoff 出现过；不是外部全量数据集意义上的“已知 owner”。

| Panel status | n | Mean Δ | Degradation rate | Severe rate |
|---|---:|---:|---:|---:|
| unseen | 902 | +0.023920 | 48.0% | 33.1% |
| repeat | 98 | **+0.081478** | 52.0% | 34.7% |

Repeat wallet 的平均 degradation 更大，但样本只有 98 个；这更像一个值得后续验证的 failure signal，不能单独视为稳定的 subgroup claim。

### 3.5 Dominant event family

Dominant event family 根据 cutoff 前 30-day native/token/internal event counts 定义，完全不使用 future outcome。

| Dominant family | n | Mean Δ | Degradation rate | Severe rate |
|---|---:|---:|---:|---:|
| mixed | 388 | +0.014787 | 47.7% | 28.4% |
| internal | 251 | +0.033797 | 50.6% | 38.2% |
| token | 361 | **+0.042493** | 47.6% | 35.2% |

Token-dominant 和 internal-dominant addresses 的 B4 degradation 都高于 mixed addresses。

### 3.6 B4 intervention gate 的 abstention 状态

这里区分两种 abstention：

1. LLM JSON 中的 `abstain_probability`；
2. B4 intervention gate 最终没有保留任何 hypothesis 的 gate abstention。

August test：

| State | n | Mean Δ | Median Δ | Severe rate |
|---|---:|---:|---:|---:|
| B4 gate pass | 903 | +0.018537 | -0.004567 | 33.2% |
| B4 gate abstain/fail | 97 | **+0.132185** | -0.008895 | 34.0% |

gate abstention 组的 mean degradation 更大，但 median 仍接近 0，说明它同样被少数 catastrophic cases 拉高。

原始 LLM `abstain_probability>0` 只有 5/1,000 test cases，样本太少，不能据此做稳定 subgroup 结论。

## 4. Confidence、entropy、evidence count 与 predictive gain

以下均使用 August test 的 1,000 个已有 OOS predictions。`gain=-Δ`，正值越大代表 B4 越好。

| Feature | Pearson r | Spearman ρ | Spearman p |
|---|---:|---:|---:|
| top hypothesis probability | -0.0117 | -0.0317 | 0.317 |
| top-vs-second probability margin | -0.0103 | -0.0314 | 0.322 |
| raw abstention probability | -0.0347 | +0.0251 | 0.428 |
| mean target confidence | -0.0063 | -0.0416 | 0.189 |
| mean target entropy | -0.0014 | +0.0351 | 0.267 |
| hypothesis entropy | +0.0109 | +0.0253 | 0.424 |
| evidence claim count | -0.0080 | -0.0327 | 0.302 |
| unique evidence count | -0.0008 | -0.0006 | 0.985 |
| event count 7d | -0.0362 | +0.0116 | 0.714 |
| history event count 30d | -0.0244 | -0.0210 | 0.507 |

总体上：

- LLM 越 confident，并没有更可能产生 B4 gain；
- hypothesis entropy 与 gain 没有稳定关系；
- evidence count 与 gain 没有稳定关系；
- activity/history length 与 gain 也没有稳定的单调关系。

这不支持“只要 confidence 高一些”或“hypothesis 更集中一些”，就能识别出更可靠的 future behavioral hypothesis。

## 5. 核心图：Intervention Sensitivity vs B4 Predictive Gain

图文件：

```text
results/plots_degradation/intervention_sensitivity_vs_b4_gain.png
```

August test macro-level 结果：

| X feature | Pearson r | Spearman ρ |
|---|---:|---:|
| raw intervention sensitivity | **+0.0549** | **-0.0240** |
| evidence-aligned intervention margin | +0.1055 | +0.0316 |
| self sensitivity | +0.0297 | -0.0208 |
| market sensitivity | +0.0452 | -0.0052 |

图中最重要的是：

> intervention sensitivity 的点云没有形成可见的单调上升关系；Pearson 和 Spearman 都接近 0。

`evidence_aligned_intervention_margin` 的 Pearson +0.1055 主要不是稳定的 rank-order relationship，因为 Spearman 只有 +0.0316。它更像少数 outlier 对线性相关造成的影响，不足以说明“响应越强，hypothesis 越可预测”。

### 唯一值得单独记录的弱信号

`placebo_sensitivity` 与 B4 gain 有一个很弱的负相关：

```text
Pearson r = -0.0974, p = 0.0020
Spearman ρ = -0.0911, p = 0.0039
```

这更接近：**模型对 placebo sentence 也越敏感时，B4 越可能变差**。它不能证明 causal provenance，但与 provenance contamination 的 red-team 观察方向一致。由于本分析包含多个 exploratory comparisons，这个弱信号不能单独升级为 confirmatory claim。

## 6. Interpretation

本轮最清楚的 negative finding 不是简单的：

> LLM did not beat the baseline.

而是：

> **The model reacts to the evidence it cites, but the magnitude of evidence sensitivity does not identify hypotheses that are more predictive of future behavior.**

更具体地说：

1. `E_SELF` / `E_MARKET` intervention response 在 development 上确实高于 placebo；
2. 但 test 上，`self_sensitivity`、`market_sensitivity` 和 aggregate `intervention_sensitivity` 与 B4 predictive gain 的 Spearman correlation 都接近 0；
3. confidence、hypothesis entropy、evidence count、activity 和 history length 同样不能解释哪些 case 会 gain；
4. B4 的总体失败由一批严重 log-loss tail failures 推动，尤其集中在高 activity、repeat wallet、token/internal dominant 等条件；
5. 因此 **evidence responsiveness ≠ evidence validity ≠ future predictive usefulness**。

这给出的论文级表述可以是：

> Intervention tests detected that the LLM changed its structured hypotheses when cited evidence was removed, but intervention magnitude did not identify hypotheses with superior future-behavior validity. The model was evidence-responsive without being behaviorally predictive.

## 7. 不应过度解释的地方

- June train 的 1,000 rows 没有现成 OOS B0–B4 predictions，因此没有被事后补生成 in-sample loss；
- repeat/unseen 只表示 frozen panel 内的 prior appearance，不代表全量 Ethereum history 的 wallet familiarity；
- top probability 是 hypothesis probability proxy，不是 calibrated confidence；
- correlation 是 post-hoc diagnostic，不是 causal effect；
- 当前分析没有改变任何预测，也没有使用新的训练、阈值或 prompt selection。

## 8. 产物

分析脚本：

```text
research/decision_state/src/analyze_decision_state_degradation.py
```

核心表：

```text
results/decision_state_case_degradation_analysis.csv
results/decision_state_loss_delta_long.csv
results/decision_state_degradation_summary.csv
results/decision_state_degradation_by_condition.csv
results/decision_state_degradation_by_target.csv
results/decision_state_gain_correlations.csv
results/decision_state_top_100_degradation_cases.csv
results/decision_state_top_100_gain_cases.csv
results/decision_state_degradation_analysis_manifest.json
```

图：

```text
results/plots_degradation/intervention_sensitivity_vs_b4_gain.png
results/plots_degradation/model_degradation_by_target.png
results/plots_degradation/b4_degradation_by_condition.png
results/plots_degradation/test_gain_correlation_heatmap.png
```

冻结 prediction 文件 SHA-256 在分析 manifest 中记录，分析脚本运行过程中只读这些文件，没有覆盖或重写 prediction。
