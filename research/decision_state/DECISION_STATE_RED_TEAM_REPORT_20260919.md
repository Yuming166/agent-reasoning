# Decision-State V1 Red-Team Report

**日期：2026-09-19**
**对象：`DECISION_STATE_PROTOCOL_V1` 的冻结 effectiveness evaluation**

## 1. Red-team 总结

本次 red-team 没有发现足以推翻数据边界的 future leakage 证据，但发现了一个更重要的科学边界：

> 模型确实对 evidence intervention 有响应，但这些响应没有转化为 August future-behavior predictive gain；B4 反而显著劣于 M1。

因此不能用“intervention response 很强”替代“future validation 通过”。

## 2. 逐项审查

### 2.1 Future leakage

已执行输入审计：

```text
prompt_rows = 3000
eval_rows = 3000
forbidden_prompt_columns = []
case_id_unique = true
status = PASS
```

Prompt cases 与 evaluation-only outcomes 分开保存。Future outcome 字段没有进入 prompt 表；LLM panel 在 future outcomes join 之前完成冻结。当前证据支持“未发现输入列级 future leakage”。这不是对源数据所有潜在语义错误的绝对证明，因此报告中仍只使用 leakage-safe boundary claim。

### 2.2 Outcome-conditioned sampling

固定每个 cutoff 1,000 个地址，四个 prior-30-day activity bins 各 250 个，由 address/cutoff hash 选择。case manifest 没有使用 future label 选择样本。该设计避免了“先看未来，再选容易预测的地址”。

### 2.3 Test-time response selection

四种 variant 均完整保留：

```text
full         3000
minus_self   3000
minus_market 3000
placebo      3000
```

LLM panel manifest 记录 12,000/12,000 HTTP 200、12,000/12,000 parse-valid、0 errors。没有在 August 看到 outcome 后丢弃 response 或替换 response。Operational success 不是 effectiveness success，但这里没有看到 post-outcome response filtering。

### 2.4 Parser success 是否被错误包装成科学成功

没有。所有 variant 均 parse-valid，但 parser success 只支持：

- endpoint 可用；
- 返回结构可解析；
- schema 通过率高。

它不支持：

- hypothesis 是正确的；
- probability 已校准；
- evidence provenance 是真实的；
- future behavior 被改善预测。

正式 test 中 B4 macro log loss 为 0.840193，而 B0 为 0.810633，正好说明这一区分不能省略。

### 2.5 Intervention 是否可能只是 prompt sensitivity

可能，而且当前结果只能安全地称为 **evidence-responsiveness**：

- July `E_SELF` 的 relevant response median 0.221949，placebo median 0.058082；
- July `E_MARKET` 的 relevant response median 0.130945，placebo median 0.058082；
- 两组 paired mean-difference CI 都严格高于 0。

但是，删除 evidence 会同时改变模型看到的上下文、可生成的 hypotheses 和语言叙事。JS response 没有完成 causal identification。协议也明确把它定义为 intervention-responsiveness test，而不是真实 belief 的因果识别。

### 2.6 Provenance contamination

Full hypotheses 中：

- 100.0% case 声称使用 `E_SELF`；
- 97.6% case 声称使用 `E_MARKET`；
- 8.87% case 至少有 hypothesis 声称使用 `E_PLACEBO`；
- 0 case 出现未知 evidence ID。

`E_PLACEBO` 被纳入 hypothesis evidence，说明模型会把非行为 reporting sentence 也吸收到 behavioral narrative 中。当前 B4 gate 会拒绝没有 relevant `E_SELF/E_MARKET` response 的 hypothesis，但这不能消除模型本身的 provenance hallucination；它只限制哪些 hypothesis 可进入 B4 consequence mixture。

### 2.7 Hypothesis diversity 是否等于有效 competing explanations

不等于。Full prompt 99.9667% case 有三条有效 hypothesis，但三条 hypothesis 的数量和结构化差异不证明它们是有区分力的 competing explanations。当前实验没有把自然语言 text 传给 downstream head，因此结果主要测试 consequence vectors、probabilities 和 intervention features，而不是语言解释质量。

### 2.8 “Persistent state” 是否被真正验证

没有完全验证。每个 cutoff 都对同一个 address-level unit 产生一组当期 hypothesis，但本轮主指标是单个 cutoff 到未来 7 天 consequence 的预测；没有单独定义和评估：

- hypothesis identity/state 在相邻 cutoff 之间是否持续；
- 状态转换是否可重复；
- 同一 address 的 state trajectory 是否优于独立重推理。

因此结果不能写成“persistent latent state 已被证明”，最多只能写成“per-cutoff structured behavioral hypotheses 的 future consequence test 失败”。

### 2.9 Meta-head 是否偷看了 test

冻结 amendment 明确规定：

- June fit；
- July development check；
- August 前用 June+July refit；
- August 不参与 feature、threshold、prompt 或 hyperparameter selection。

Evaluator 使用固定的 HistGradientBoosting 参数，输入只含 as-of M1 与 LLM-derived structured features。结合输入审计，当前没有发现 test outcome 被用于训练或选择。

### 2.10 单一模型、单一窗口的外推风险

本轮只测试：

- Qwen3.5-4B 一个模型；
- 2022-06 至 2022-08 一个历史窗口；
- 四类地址行为 consequence；
- 7-day horizon。

所以 NO-GO 是对 V1 scientific claim 的否定，不是对所有 LLM、所有市场窗口或所有 latent-state tasks 的普遍否定。

## 3. 结果是否可能被活动度分层掩盖

没有。August test macro log loss：

| Stratum | B0 | B4 | B4 - B0 |
|---|---:|---:|---:|
| low_activity | 0.690096 | 0.714577 | +0.024481 |
| active | 0.931170 | 0.965809 | +0.034639 |

B4 在两个聚合 stratum 都变差。因此不能通过只报告某一个活动度区间来挽救主张。

## 4. Red-team verdict

### 已通过的边界检查

- input column leakage audit：PASS；
- case uniqueness：PASS；
- fixed sample counts and activity bins：PASS；
- four intervention variants complete：PASS；
- parser/HTTP operational yield：PASS；
- July intervention responsiveness：PASS。

### 未通过的科学检查

- B4 vs B0 primary predictive gate：FAIL；
- B4 vs B2 intervention-value gate：FAIL；
- low/activity strata incremental gain：FAIL。

**Red-team verdict：NO-GO。**

任何后续工作都必须把本轮 August 结果视为 frozen test result，不得把它回收为 prompt/threshold tuning data。
