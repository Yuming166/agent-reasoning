# EX-Graph 重要节点选择机制验证（2026-09-10）

## 结论

在当前 v2 候选池、四个月各 1,000 个分层事件面板以及统一的授权 Qwen3.5-4B/vLLM 配置下，重要节点选择器通过 Stage 1 go/no-go：

> `GO_STAGE_2_RECURSIVE_REASONING`

这里的“重要”严格表示：**值得分配完整 deliberation/后续动态推理预算的目标钱包事件**。它不表示已经证明钱包具有因果影响力，也不表示 X 活动导致了链上行为。

## 固定协议

- 选择单位：`(snapshot_date, target_address, target_sequence_index)` 目标钱包预测事件；后续同时导出事件到钱包的聚合排名。
- 时间切分：2022-06-01 train；2022-07-01 validation/tuning；2022-08-01 frozen test；2022-09-01 额外时间外检验。
- 每个月 1,000 个事件，四个 strata 各 250：`new_popular`、`new_tail`、`repeat_easy`、`repeat_hard`。
- 预算：5%、10%、20%、50%、75%；主预算为 50%。
- 选择器：仅使用调用前的 16 个特征；HistGradientBoostingRegressor 在 June 训练，在 July 调参，随后使用 June+July 重训并冻结到 August。
- 运行配置：四个月均为 `Qwen3.5-4B`，temperature=0，max_tokens=700，省略 `reasoning_effort`，每事件 full/no-CF 共 4 calls。
- 失败策略：full 输出无效时回退到 cheap RR，收益记为 0；不删除失败事件。

## 比较策略

- `random`：同事件集、同预算，多随机种子重复。
- `degree`：事件候选池中最高的 as-of `g_cnt`。
- `pagerank`：as-of 全局流行度 rank 的代理 `-log(g_rank)`；不是释放版静态 PageRank。
- `activity`：目标钱包近 90 天事件数 `evt_cnt_90d`。
- `volume`：候选池 as-of `g_cnt` 总量。
- `repeat`：是否为 repeat 事件。
- `cheap_uncertainty`：cheap candidate score 的平均 Bernoulli entropy。
- `cheap_margin` / `cheap_topscore`：cheap top-1/top-2 边际和 top score 的不确定性代理。
- `static_pagerank` / `static_degree`：释放版静态 EX-Graph 特征的敏感性分析；候选覆盖很低，因此不作为主结论依据。
- `oracle`：按真实 operational gain 排序，仅作上界，不能部署。

## 冻结 August 测试结果

加权 MRR：

| 预算 | learned | 最佳非学习 baseline | 最佳 baseline | learned - best |
|---:|---:|---:|---|---:|
| 5% | 0.3056 | 0.3058 | volume | -0.0001 |
| 10% | 0.3463 | 0.3312 | volume | +0.0151 |
| 20% | 0.4042 | 0.3781 | volume | +0.0261 |
| 50% | **0.4606** | 0.4205 | degree | **+0.0401** |
| 75% | 0.4509 | 0.4267 | degree | +0.0242 |

主预算 50% 的 paired bootstrap CI：

- learned - degree：`+0.0401`，95% CI `[+0.0209, +0.0607]`；
- learned - volume：`+0.0443`，95% CI `[+0.0252, +0.0649]`；
- learned - repeat：`+0.0518`，95% CI `[+0.0311, +0.0734]`；
- learned - cheap uncertainty：`+0.0507`，95% CI `[+0.0284, +0.0741]`；
- learned - random：`+0.1215`，95% CI `[+0.0931, +0.1495]`。

因此 learned 在 5 个预算中的 4 个超过最佳非学习 baseline；5% 是唯一没有超过 volume 的预算点。August 的全 cheap MRR 为 0.2795，全 full MRR 为 0.4060；50% learned 已达到 0.4606。

50% learned 的附加统计：

- useful-event precision（selected 后 `gain_full > 0`）：0.732；
- useful-event recall：0.762；
- 正收益 headroom 捕获：0.906；
- harm rate（selected 后 `gain_full < 0`）：0.214；
- 加权平均约 5,746 measured tokens/event，相比全 full 的约 8,782 tokens/event；
- learned score 与真实 gain 的 Spearman：0.508。

## 额外 September 外检验

September 没有用于训练或调参。learned 相对最佳非学习 baseline 的 MRR 差值为：

- 5%：`+0.0201`；
- 10%：`+0.0389`；
- 20%：`+0.0274`；
- 50%：`+0.0338`；
- 75%：`+0.0122`。

这支持时间外稳定性，但不是新的训练/调参结果。

## 审计边界

四个月均为 1,000/1,000 supported events，full/no-CF parse rate 均为 100%，重复 event key 为 0，client/transport error 为 0。逐步审计发现 June、July、August 各有 2 条 step-3 unknown/invalid candidate ID；系统保留了有效的 mask-stage/final rank，不做静默删除；September 为全 step `ok`。因此报告明确保留这 6 条 deterministic fallback，不将运行包装成完全无异常的 clean step audit。

选择器的 feature boundary 通过：没有使用 `truth_g_rank`、真实排名、`truth_in_pool`、`mask_sensitive`、parse 状态、LLM token/latency、`gain_full`、`pop_weight` 或 stratum 作为模型特征。Static PageRank/degree 仅作为敏感性 baseline，不进入 learned selector。

## 交付物

主结果目录：

```text
artifacts/llm_panel_v2/node_selection_v2_final_audited_20260910/
```

关键文件：

- `node-selection-go-no-go.md`：完整 go/no-go 报告；
- `go_no_go.json`：机器可读决策；
- `manifest.json`：运行、模型、切分、审计和 feature boundary；
- `selection_curves.csv`：所有预算和 baseline 曲线；
- `paired_bootstrap_test.csv`：August paired CI；
- `strata_test_b50.csv`：四个 strata 的 50% 结果；
- `calibration_test.csv`：learned score calibration；
- `learned_selector_frozen.pkl`：June+July 训练、冻结的选择器；
- `frozen_test_selector_input.csv`：**仅调用前输入和可部署分数**，不含收益、truth、token、latency；
- `frozen_test_outcomes_for_audit.csv`：单独隔离的结果审计文件；
- `frozen_test_important_nodes_b50.csv`：August 50% learned policy 的 event-to-wallet 聚合，可作为下一阶段递归推理的输入候选。

选择器脚本：

```text
src/agent/evaluate_node_selection.py
```

同模型面板重跑脚本：

```text
run_node_selection_qwen_v2_rerun_20260910.sh
run_node_selection_qwen_v2_sept_rerun_20260910.sh
```

## 下一步

现在可以进入递归可信推理阶段，但应把本次 `learned_selector_frozen.pkl` 和 `frozen_test_selector_input.csv` 视为冻结的 Stage-1 输入。下一阶段单独设计并评估：

```text
selected event/node
  -> dynamic depth controller
  -> OBSERVE_HISTORY
  -> higher-order / neighbor expansion
  -> counterfactual intervention
  -> continue/stop
  -> trustworthy next-counterparty prediction
```

递归阶段不能回头使用 August 的真实 gain、truth rank 或 oracle 选择结果调参。
