# Decision-State V1 实验结果报告

**评估日期：2026-09-19**
**实验状态：已完成冻结测试；效果门判定为 NO-GO**

## 1. 结论先行

本轮实验的目标是检验：

> 在 leakage-safe 的 M1 recent-dynamics baseline 之上，加入由 LLM 生成、并经过 evidence intervention 筛选的 address-level behavioral hypotheses，是否能提升对未来 7 天地址行为的预测。

结论是：**没有通过效果门。**

- **主门失败：** `B4_M1_VERIFIED_LLM` 的 August test macro log loss 为 **0.840193**，高于 `B0_M1` 的 **0.810633**。
- 配对 address bootstrap 的 `B0 - B4` 估计为 **-0.029560**，95% CI 为 **[-0.056690, -0.003166]**；整个区间低于 0，而不是高于 0。
- **干预响应门通过：** July development 上，`E_SELF` 和 `E_MARKET` 都满足预注册的 relevant response > placebo response 且 paired CI > 0。
- 但干预响应只说明模型对证据删除有响应，**不等于 future predictive value**；它不能挽救主预测门失败。
- 因此本轮 Level 1 不支持继续启动 Level 2 relational expectation，也不支持声称“LLM 推断的 latent state 有增量预测价值”。

## 2. 冻结协议与数据边界

| 项目 | 设置 |
|---|---|
| 单位 | 一个 Ethereum address 在一个 cutoff 的行为代理，不解释为真实 owner 的情感/信念 |
| cutoff | 2022-06-01、2022-07-01、2022-08-01 UTC |
| split | June train、July development、August frozen test |
| 每个 cutoff | 1,000 个 active observed addresses；四个 30-day activity bins 各 250 个 |
| 总 case 数 | 3,000；future outcomes 3,000/3,000 complete |
| 预测 horizon | cutoff 后 7 天 |
| consequence 维度 | activity、active days、counterparty breadth、new counterparties |
| LLM variants | full、minus_self、minus_market、placebo |
| LLM panel | 12,000 calls；12,000/12,000 HTTP 200 且 schema parse-valid |
| LLM model | Qwen3.5-4B |

Prompt/input 审计结果：

```text
prompt_rows = 3000
future/evaluation-only forbidden prompt columns = []
case_id_unique = true
status = PASS
```

样本选择由 cutoff/address hash 和预先定义的 activity bins 决定；future outcome 没有进入 prompt、sample selection 或 intervention selection。上述结果是边界审计结果，不是 effectiveness 结果。

## 3. Baseline ladder 的正式 test 结果

这里的 B1–B4 按冻结的 meta-head amendment 解释为 **M1 + augmentation**，不是用 LLM 直接替代 M1。

| 模型 | 含义 | Test macro log loss | Test macro F1 | Test balanced accuracy |
|---|---|---:|---:|---:|
| B0_M1 | M1 recent-dynamics classifier | **0.810633** | 0.612624 | 0.639346 |
| B1_M1_DETERMINISTIC | M1 + deterministic as-of proxy | 0.818851 | 0.609566 | 0.635237 |
| B2_M1_SINGLE_LLM | M1 + top single hypothesis | 0.811696 | 0.613434 | 0.640598 |
| B3_M1_MULTI_LLM | M1 + full hypothesis mixture | 0.813770 | 0.606902 | 0.634957 |
| B4_M1_VERIFIED_LLM | M1 + mixture + intervention features | **0.840193** | 0.591819 | 0.629929 |

B4 相对于 B0 的 macro log loss **增加 0.029560**；相对于 B2 增加 **0.028497**。因此 intervention features 在本冻结设置下没有带来增量预测收益，反而使 test 概率预测变差。

### 3.1 主门：B4 vs B0

预注册要求：`B0 - B4` 的 paired address bootstrap 95% CI 全部高于 0。

```text
estimate(B0 - B4) = -0.029560
95% CI              = [-0.056690, -0.003166]
pass                = false
```

主门判定：**FAIL**。

### 3.2 次门：B4 vs B2

```text
estimate(B2 - B4) = -0.028497
95% CI             = [-0.054696, -0.003118]
pass by log loss   = false
```

B4 没有满足 `B4 < B2`。由于 B4 已经发生 predictive deterioration，不能用 calibration/abstention 叙事替代预注册的 predictive requirement。

### 3.3 Per-dimension paired test bootstrap

正值表示左侧模型 log loss 更低；目标是 CI 下界大于 0。

| Comparison | Dimension | Estimate | 95% CI | 判定 |
|---|---|---:|---:|---|
| B0 - B4 | activity | -0.042426 | [-0.078049, -0.007342] | fail |
| B0 - B4 | active_days | -0.027778 | [-0.060650, 0.005229] | fail |
| B0 - B4 | counterparty_breadth | -0.031579 | [-0.067724, 0.002589] | fail |
| B0 - B4 | new_counterparties | -0.016458 | [-0.048685, 0.015007] | fail |
| B0 - B4 | macro | -0.029560 | [-0.056690, -0.003166] | **fail** |

activity dimension 的 B4 退化最明确；其余维度点估计也均不利于 B4。

## 4. July development 上的 intervention gate

该部分没有使用 August outcome 来调阈值。这里的 relevant response 是删除模型声称依赖的 evidence group 后，consequence distribution 的 JS response；placebo 是替换非行为 UTC reporting sentence 后的 response。

| Evidence group | n claimed | Median relevant response | Median placebo response | Mean relevant-minus-placebo | 95% CI of paired mean diff | 判定 |
|---|---:|---:|---:|---:|---:|---|
| E_SELF | 1,000 | 0.221949 | 0.058082 | 0.179571 | [0.167412, 0.191519] | **pass** |
| E_MARKET | 991 | 0.130945 | 0.058082 | 0.077894 | [0.068495, 0.087112] | **pass** |

所以 intervention responsiveness gate 通过了 2/2 个要求的 evidence groups。但这只证明：模型输出对输入证据扰动有可测响应；它没有证明响应是 causal，也没有证明它能正确预测未来地址行为。

## 5. Activity-stratum 结果

协议要求同时报告 low-activity 和 active stratum，避免只在高活跃地址上报告收益。

| Test stratum | B0 macro log loss | B2 macro log loss | B3 macro log loss | B4 macro log loss |
|---|---:|---:|---:|---:|
| all | 0.810633 | 0.811696 | 0.813770 | **0.840193** |
| low_activity (`1-2`,`3-9`) | 0.690096 | 0.690544 | 0.697333 | **0.714577** |
| active (`10-19`,`20+`) | 0.931170 | 0.932848 | 0.930207 | **0.965809** |

B4 在 low-activity 和 active 两个聚合 stratum 都高于 B0；没有出现“只在一个高活跃 stratum 上取得总体收益”的情况。

## 6. LLM 输出与 provenance 质量

12,000 次调用的 operational/parser 指标很好，但不能当作 scientific effectiveness：

- 四个 variant 均为 3,000/3,000 parse-valid。
- Full prompt 中 2,999/3,000 case 有 3 条有效 hypotheses；1 个 case 有 2 条。
- `abstain_probability` 平均为 0.0002，非零比例为 0.2%。
- Full hypotheses 声称使用 `E_SELF` 的 case 比例为 100%；使用 `E_MARKET` 为 97.6%。
- 8.87% case 至少有 hypothesis 声称使用 `E_PLACEBO`。这不是未知 evidence ID，但说明模型会把非行为 reporting sentence 纳入叙事，需要在后续设计中视为 provenance 风险。
- 未发现未知 evidence ID。

独立的 direct consequence distribution（不是主门的 meta-head）也没有显示可靠性：其 test log loss 明显高于 meta-head，说明不能把“模型能输出结构化 JSON”误认为“模型输出的概率就是可校准预测概率”。

## 7. 科学判定

| Gate | 结果 |
|---|---|
| B4 < B0，paired test CI 全部高于 0 | **FAIL** |
| B4 < B2 或无 predictive deterioration 的预注册 reliability-only 条件 | **FAIL** |
| July relevant intervention > placebo，至少 E_SELF/E_MARKET 两组 | **PASS** |
| 输入无 future leakage、case 唯一、prompt boundary 审计 | PASS（边界审计） |
| low/active strata 分层报告 | 已报告；两层均无 B4 增益 |

**最终决定：Level-1 effectiveness gate = NO-GO。**

该决定只适用于冻结的 V1 协议、2022 年 6–8 月窗口、当前 7-day consequence schema、Qwen3.5-4B 和当前 meta-head。它不等价于“LLM behavioral reasoning 在所有任务上都无效”，但足以否定“本轮方法已获得增量预测价值”的论文主张。

## 8. 后续边界

1. 不用 August test 结果反向调 prompt、阈值、consequence schema 或模型超参数。
2. 不启动 Level-2 relational expectation；先保留 Level-1 的 NO-GO 记录。
3. 若继续研究，应建立新的预注册协议和新的 untouched holdout；只能把本轮 August 结果作为已观测历史，不能把它当作可反复调参的 validation set。
4. 后续可以在不改动本冻结结果的前提下，用 June/July 做 failure analysis，但任何新方法比较都要有新的时间切分或新的 holdout。
5. 不把 address-level consequence prediction 写成真实 owner 的 emotion、belief、causal intent 或 Theory-of-Mind 识别。

## 9. 主要产物

- Protocol: `protocol/DECISION_STATE_PROTOCOL_V1.md`
- Meta-head amendment: `protocol/PROTOCOL_V1_AMENDMENT_META_HEADS_20260919.md`
- Frozen LLM panel: `results/hypothesis_panel_full.jsonl`
- Evaluator outputs: `results/decision_state_metrics.csv`、`results/decision_state_bootstrap.csv`、`results/decision_state_meta_predictions.csv`
- Intervention audit: `results/decision_state_intervention_summary.csv`、`results/decision_state_intervention_case_metrics.csv`
- Stratum audit: `results/decision_state_stratum_metrics.csv`
- Gate summary: `results/decision_state_gate_summary.json`
- Red-team analysis: `DECISION_STATE_RED_TEAM_REPORT_20260919.md`
- Decision record: `DECISION_STATE_DECISION_20260919.md`

Frozen panel SHA-256：

```text
047f999c1dde6b2f47d7601f3bb41fe6a457b6dbad028932e0469b95e7effe2b
```
