# Phase II-A — Reasoning-Worthiness Discovery（推理价值发现）

- **完成日期**：2026-09-12
- **核心对象**：`RV(e,t) = U_FullCF(e,t) − U_Cheap(e,t)`；RV 是增量预测效用，不是因果效应。
- **冻结协议**：June 训练 / July 调参 / August 冻结测试 / September 独立 holdout；`K ∈ {10,25,50,100,250,500,1000}`。
- **最终脚本**：`run_selector_benchmark.py`，SHA-256 `9a854002f01f68ac2b8a06340be25f3b90a31b13bcd0f6aaf3bebb6a49d4fb1a`。
- **基础设施纪律**：本阶段 selector/统计/绘图为本地 CPU、无 LLM 新调用；不使用私人中转站；研究 LLM 面板沿用已审计的本地 Qwen3.5-4B 与已有 GLM v2 只读对照。

## 进度注册表（Phase II-A）

| 步骤 | 任务 | 状态 | 输出/证据 |
|---|---|---|---|
| 0 | 冻结 Phase-I commit | ✅ COMPLETE | Phase-I main `1d2dfdd` |
| 1 | Phase-I 结果审计（14 单元 + 面板证据） | ✅ COMPLETE | `PHASE1_RESULT_AUDIT.md`、`phase1_result_registry.csv` |
| 2 | June 异常诊断与终裁 | ✅ COMPLETE | 授权 Qwen rerun 作为训练证据；GLM June 隔离；2 条 audited fallback |
| 3 | `reasoning_gain_dataset.parquet` | ✅ COMPLETE | `DATA_RG_001`，4,000 events + manifest |
| 4 | `dynamic_influence_dataset.parquet` | ✅ COMPLETE | `DATA_DI_001`，97,305 wallet-cutoff rows + manifest |
| 5-9 | 选择器基线/擂台/冻结/评估 | ✅ COMPLETE | `SEL_BENCH_001`，378 rows；最终显式 feature contract |
| 10 | 跨模型稳健性（已有 GLM v2 vs Qwen） | ⚠️ PARTIAL | `ROBUST_GLM_001`，128 rows；双向 holdout gate 未通过 |
| 11 | 对抗性泄漏/体量审计 | ✅ COMPLETE | `AUDIT_ADV_001`，55 rows；forbidden scan PASS |
| 12 | 论文级图 | ✅ COMPLETE | `FIG_PHASE2_001`，`figures/` 六个 PDF |
| 13-14 | 首席科学家综合 + II-B 决策 | ✅ COMPLETE / NO-GO | `FINAL_SYNTHESIS.md`、`PHASE2_HANDOFF.md` |

## Final decision

**Phase II-A 交付完成；正式 Phase II-B（K-step）暂不进入。**

保留的窄结论是：

> Qwen Full-CF 相对 frozen Cheap 的 reasoning gain 具有明显事件异质性；cutoff 前 selector 在固定事件数 `K=100` 下，August test 和 September holdout 均优于 random。对 volume 的优势在 August 显著，但 September 置信区间跨 0；GLM→Qwen 的 September transfer 接近 random。因此当前支持“above-random reasoning allocation”，不支持完整的跨强基线/跨模型 superiority。

最接近方案 §22-C：reasoning gain 有效、dynamic influence 未胜出；下一步只能是受限的新窗口/新样本 validation，不是直接扩大 K-step。

## 关键 K=100 结果

| split | hybrid incremental MRR | random | volume | dynamic influence | 95% CI 重点 |
|---|---:|---:|---:|---:|---|
| August test | 0.04833 | 0.01099 | 0.01231 | 0.00406 | hybrid-random `[0.02611,0.04895]`；hybrid-volume `[0.02253,0.04902]` |
| September holdout | 0.02963 | 0.00828 | 0.01840 | 0.00813 | hybrid-random `[0.01184,0.03179]`；hybrid-volume `[-0.00363,0.02548]` |
| Aug+Sep joint | — | — | — | — | hybrid-volume `[0.01423,0.03409]` |

Final July-frozen hybrid weights：`rv_pred=0.50`、`behavior_pred=0.25`、`uncertainty_pred=0.25`、`di_pred=0`、`novelty_pred=0`。dynamic influence 未获 tuned weight，不能包装为机制胜者。

## 结果与限制

- RV overall mean `0.1186`、median `0`；stratum mean：`new_tail 0.0059`、`new_popular 0.0428`、`repeat_easy 0.0976`、`repeat_hard 0.3283`。
- Qwen/GLM RV Spearman：July/August/September `0.8113/0.7929/0.8068`；这是 panel agreement，不是 model-independent proof。
- Qwen-trained hybrid → GLM 在 K=100 三个月均为正；GLM-trained → Qwen 的 September incremental MRR `0.00837`，接近 Qwen random `0.00828`，所以跨模型仅 partial。
- primary feature contract 为 70 个显式 as-of/pre-call 数值候选；排除 future labels、LLM/evaluation/truth/cost fields 和 full-window static prior。`AUDIT_ADV_001` forbidden scan = PASS。
- low-volume/high-influence quadrant 仅作监督审计；learned selector 未稳定覆盖，不得写成已验证发现。
- `all_full` 是 full-cost reference，不是 K=100 matched-budget comparator；`oracle` 只作 future-RV upper bound。

## 交接入口

1. 先读 `FINAL_SYNTHESIS.md`：十个必答问题、benchmark、bootstrap、跨模型和 audit 的完整结论。
2. 再读 `PHASE2_HANDOFF.md`：NO-GO gate、冻结方法、复现命令、受限 follow-up 和 stop conditions。
3. 机器可读结果：
   - `selector_results/phase2_selector_summary.json`
   - `selector_results/run_manifest.json`
   - `selector_results/selector_model_manifest.json`
   - `selector_results/cross_model_manifest.json`
   - `selector_results/figure_manifest.json`
4. 结果表均带 `experiment_id`；registry：`EXPERIMENT_REGISTRY.yaml`。

## 复现命令

```bash
.venv-cuda/bin/python research/phase2/run_selector_benchmark.py \
  > research/phase2/run_logs/selector_benchmark_20260912.log 2>&1
```

预期末尾：`benchmark rows 378`、`strata rows 56`、`bootstrap rows 315`、`cross-model rows 128`、`audit rows 55`、`complete`。

## 约束提醒

- 禁止 `an unauthorized relay endpoint`；不得探测或复用 Codex/Claude 服务地址及凭据。
- 研究 LLM 只允许授权本地 Qwen chat `http://127.0.0.1:31518/v1`、embedding `http://127.0.0.1:31522`；本阶段 selector rerun 没有新 LLM 调用。
- 不发送原始交易数据/事件级数据到外部 API。
- 只写 `research/phase2/`；不修改 `artifacts/`、已冻结面板、`src/`。
- 不占用 GPU4/6。
