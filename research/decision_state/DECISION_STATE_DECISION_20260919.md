# Decision-State V1 Scientific Decision

**Decision date: 2026-09-19**
**Decision: NO-GO for Level-1 effectiveness claim**

## 1. Decision question

是否可以根据冻结的 June/July/August 实验声称：

> intervention-verified, address-level behavioral hypotheses add predictive value beyond the M1 recent-dynamics baseline?

## 2. Gate ledger

| Gate | Predeclared requirement | Observed result | Status |
|---|---|---|---|
| G1 primary effectiveness | B4 test macro log loss < B0；paired CI for B0-B4 entirely > 0 | B0=0.810633；B4=0.840193；estimate=-0.029560；95% CI=[-0.056690,-0.003166] | **FAIL** |
| G2 intervention value | B4 < B2，或无 predictive deterioration 的预注册 reliability-only 条件 | B2=0.811696；B4=0.840193；B2-B4 CI=[-0.054696,-0.003118] | **FAIL** |
| G3 evidence responsiveness | July 至少 E_SELF/E_MARKET 两组 relevant > placebo 且 paired CI > 0 | E_SELF 与 E_MARKET 均通过 | PASS |
| G4 data boundary | 无 future leakage、outcome-conditioned sampling、test-time response selection | input audit PASS；固定样本/variant manifest 完整 | PASS（边界审计） |
| G5 robustness reporting | active 与 low-activity 分层报告 | 两层均报告；B4 均高于 B0 | 已报告，未形成通过 |

## 3. Final scientific decision

```text
LEVEL_1_EFFECTIVENESS = NO-GO
LEVEL_2_RELATIONAL_EXPECTATION = DEFERRED
```

### 允许写入论文/记录的表述

> In the frozen June–August 2022 evaluation, structured LLM hypothesis features and intervention-derived features were operationally valid and showed evidence responsiveness on development data, but they did not improve—and in the verified B4 condition worsened—out-of-sample 7-day address-behavior prediction over the M1 recent-dynamics baseline.

中文：

> 在冻结的 2022 年 6–8 月时间切分中，结构化 LLM hypothesis 与 intervention 特征在操作层面有效，并在 development 上表现出 evidence responsiveness；但在 frozen test 上，它们没有超过 M1 recent-dynamics baseline，经过 intervention verification 的 B4 反而使 7-day address-behavior prediction 变差。

### 不允许写入论文/记录的表述

- “我们识别了 wallet owner 的真实情感/信念”；
- “我们识别了真实 transaction intent”；
- “intervention response 证明了 causal provenance”；
- “persistent latent decision state 已被验证”；
- “Level-2 Theory-of-Mind/relational expectation 已被支持”；
- “LLM behavioral reasoning 在金融链上任务上普遍无效”。

## 4. Freeze consequences

1. 不修改 August prompt、threshold、consequence schema、feature family 或 meta-head hyperparameters 以追求过门。
2. 不把 August 结果用于选择新的 prompt 或报告最优变体。
3. 不启动 Level 2 relational expectation。
4. 保留本轮所有 raw panel、features、predictions、bootstrap 和审计报告，作为一个完整的 negative effectiveness result。
5. 如果继续，必须新建 V2 protocol，并使用新的 untouched temporal holdout；本轮 August 只能作为历史测试结果，不能变成新的 development split。

## 5. Reusable research lesson

本实验把“模型能生成听起来合理的行为解释”与“这些解释能在未来行为上得到验证”分开了：

- parser/endpoint：通过；
- intervention responsiveness：通过；
- future predictive effectiveness：失败；
- generalization：未测试，不能声称。

这正是本项目的实验效果门应当捕获的失败模式。
