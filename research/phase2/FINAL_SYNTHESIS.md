# Phase II-A Chief Scientist Synthesis

- **项目**：EX-Graph — Reasoning-Worthiness Discovery
- **完成日期**：2026-09-12
- **结论状态**：Phase II-A 交付完成；**不通过正式 Phase II-B（K-step）进入门槛**，保留受限 follow-up/validation 路线。
- **核心实验 ID**：`DATA_RG_001`、`DATA_DI_001`、`SEL_BENCH_001`、`SEL_STATS_001`、`ROBUST_GLM_001`、`AUDIT_ADV_001`、`FIG_PHASE2_001`
- **最终分析脚本**：`research/phase2/run_selector_benchmark.py`
- **最终脚本 SHA-256**：`9a854002f01f68ac2b8a06340be25f3b90a31b13bcd0f6aaf3bebb6a49d4fb1a`

## 1. Executive decision

本阶段得到一个**真实但尚未达到完整强主张标准**的现象：

> 在 Qwen3.5-4B 的 frozen cheap-rank evaluation oracle 下，Full-CF 相对 Cheap 的增量预测效用（`RV = full_rr - cheap_rr`）具有明显异质性；使用 cutoff 前的数值/时序图特征训练的选择器，在固定选择事件数 `K=100` 时，August 测试和 September holdout 均优于随机选择，并在 August 显著优于 volume 选择。但 September 相对 volume 的差异置信区间跨过 0，且 GLM→Qwen 的 September 反向模型迁移接近随机。因此，当前证据支持“推理价值可被部分预测、并可在部分时间窗口节省推理预算”，不支持“跨基线、跨模型、跨时间完全稳健的 superiority”，也不支持正式启动 K-step。

最简单、最诚实的论文方向是：**leakage-aware pre-reasoning prediction of reasoning gain under a fixed event-count budget**。dynamic predictive influence 作为候选机制没有胜出，不应成为主叙事。

## 2. Data, temporal protocol, and final-run boundary

### 2.1 Inputs

- `reasoning_gain_dataset.parquet`：4,000 个事件，June/July/August/September 各 1,000 个；`DATA_RG_001`。
- `dynamic_influence_dataset.parquet`：97,305 个 wallet-cutoff 行；`DATA_DI_001`。其中 future spillover 只作为 influence 的监督标签，不进入事件选择器输入。
- June 异常终裁沿用 `PHASE1_RESULT_AUDIT.md`：训练证据使用授权本地 Qwen rerun；GLM June 异常文件隔离；2 个 June step-3 candidate fallback 已审计并携带在 manifest 中。
- `RV` 是 frozen Qwen panel 中 `full_rr - cheap_rr`，是增量预测效用，不是因果效应、市场影响或 wallet influence causality。

### 2.2 Frozen chronology

| 角色 | cutoff | 用途 |
|---|---|---|
| Train/dev | 2022-06-01 | 训练 pre-reasoning predictor |
| Tune | 2022-07-01 | 只调 hybrid 组件权重，主预算 `K=100` |
| Test | 2022-08-01 | 冻结测试 |
| Holdout | 2022-09-01 | 独立 holdout；不使用 August refit 或 September tuning |

- 预算网格：`K ∈ {10, 25, 50, 100, 250, 500, 1000}`。
- 统计：wallet-cluster paired percentile bootstrap，`B=2000`。
- 主要报告点：`K=100`；事件选择数固定，实际 Full-CF tokens/latency 随被选事件变化并被单独记录。因此“matched budget”首先指 matched event-count allocation，token/latency efficiency 是实测的次级成本轴。

### 2.3 Final legal feature contract

最终结果对应脚本 SHA-256 `9a854002...` 的 rerun。最终 selector 不是从 joined panel 的所有 numeric columns 自动取特征，而是显式使用 70 个经审计的 as-of/pre-call 数值特征的 union（behavior、as-of graph/community、novelty、cheap uncertainty、router pre-call）。以下字段类别被排除：

- future spillover/influence labels、`RV`/`z0`/`z1`；
- truth-side metadata、full/no-CF evaluation ranks、parse/fallback/evaluation fields；
- LLM usage/cost fields（如 `llm_calls`、prompt/completion tokens、latency）；
- full-window static graph prior 不作为 primary learned feature。

`AUDIT_ADV_001` 的 `forbidden_primary_feature_scan` 为 `PASS`。中间草稿曾使用过过宽的 joined numeric 列表；该草稿不进入最终结果，最终表格和图均由上述显式 feature contract 的 rerun 生成。

## 3. Answers to the ten required questions

### 1. Is reasoning gain heterogeneous?

**是，且异质性很大。** 4,000 事件总体 `RV` mean 为 `0.1186`、median 为 `0`；按 stratum 的 mean 为：

| stratum | n | RV mean | RV median | `z0` rate | `z1` rate |
|---|---:|---:|---:|---:|---:|
| `new_popular` | 1,000 | 0.0428 | 0.0000 | 0.392 | 0.266 |
| `new_tail` | 1,000 | 0.0059 | -0.1896 | 0.351 | 0.262 |
| `repeat_easy` | 1,000 | 0.0976 | 0.0000 | 0.446 | 0.385 |
| `repeat_hard` | 1,000 | 0.3283 | 0.2778 | 0.703 | 0.608 |

月度 mean 为 June `0.1682`、July `0.1136`、August `0.1099`、September `0.0828`；median 四个月均为 `0`。这支持“昂贵推理不是均匀有用”的描述性结论，但不应外推为稳定的任务级收益或因果效应。

### 2. Can reasoning-worthiness be predicted before reasoning?

**部分可以。** 最终 July-frozen hybrid 在 `K=100` 选择的事件平均 RV 为 July `0.5160`、August `0.4833`、September `0.2963`；它在 August/September 都高于对应的 random expected `0.1099`/`0.0828`。但 September 的预测质量下降，且 direct `reasoning_value` predictor 在 September 不再胜过 volume。

因此准确表述是：**pre-reasoning selector 有可重复的 above-random signal，但还不是对所有强 naive baseline 都稳定胜出的 selector。**

### 3. Which feature family matters most?

方法层面的证据显示，**直接预测 RV 的组件最重要**：July 调出的 hybrid 权重为：

```text
rv_pred=0.50, behavior_pred=0.25, uncertainty_pred=0.25,
di_pred=0.00, novelty_pred=0.00
```

dynamic-influence 和 novelty 在 July simplex tuning 中均获得 0 权重。这里的权重是组件级选择结果，不是 feature-level causal importance；不能据此声称某个单独钱包特征造成了收益。当前最简单的可复现方法是 HistGradientBoostingRegressor + 显式 as-of/pre-call 特征契约 + July 冻结权重。

### 4. Does dynamic influence beat static importance?

**没有得到支持。** `dynamic_influence` 在 August/September 的 K=100 incremental MRR 分别为 `0.0041`/`0.0081`，低于 volume 的 `0.0123`/`0.0184`，也低于最终 hybrid 的 `0.0483`/`0.0296`。full-window static degree/PageRank 只保留为 context-only/leaky prior，不是合法 primary as-of selector；因此不能把本实验写成“dynamic influence beats static importance”。

同时，`dynamic_influence_dataset.parquet` 中确实存在低量/高 influence wallet quadrant，但最终 selector 没有稳定优先覆盖它；该 quadrant 结果只可作为 supervision audit，不能包装成已验证发现。

### 5. Does selective reasoning beat random at equal budget?

**对最终 hybrid，August 和 September 都是肯定的。** `K=100` 的 incremental MRR：

| split | hybrid | random | hybrid - random | 95% CI |
|---|---:|---:|---:|---:|
| August test | 0.04833 | 0.01099 | 0.03734 | [0.02611, 0.04895] |
| September holdout | 0.02963 | 0.00828 | 0.02134 | [0.01184, 0.03179] |
| Aug+Sep joint | — | — | 0.02934 | [0.02232, 0.03717] |

这些是 `SEL_STATS_001` 的 wallet-cluster paired bootstrap 结果；K=100 primary family 的 Holm-adjusted p 为 `0.01499`（显著行）。

### 6. Does it survive temporal holdout?

**对 random： survives；对 volume：只部分 survives。**

- August：hybrid - volume `+0.03602`，95% CI `[0.02253, 0.04902]`，不含 0。
- September：hybrid - volume `+0.01122`，95% CI `[-0.00363, 0.02548]`，跨过 0，bootstrap p=`0.14093`。
- August+September joint：hybrid - volume `+0.02362`，95% CI `[0.01423, 0.03409]`。

所以不能写“在独立 September holdout 上稳定击败 volume”；只能写“在 September 点估计上高于 volume，但不确定性仍允许无差异”。

### 7. Does it survive cross-model testing?

**部分支持，未通过双向 holdout 稳健性门槛。** 使用已有有效 GLM v2 panels，June GLM 被审计排除：

- Qwen/GLM RV Spearman：July `0.8113`（n=936）、August `0.7929`（n=999）、September `0.8068`（n=1,000）；sign/label agreement 约 `0.890`、`0.890`、`0.897`。
- Qwen-trained hybrid → GLM labels，在 K=100 的 GLM incremental MRR：July `0.0634`、August `0.0711`、September `0.0447`；同月 random expected 为 `0.0217`、`0.0224`、`0.0170`。这是支持性 transfer evidence，但没有独立 bootstrap CI。
- GLM-trained RV predictor → Qwen labels：August K=100 `0.0491`，但 September 只有 `0.00837`，几乎等于 Qwen random expected `0.00828`。

因此可写“panel agreement 和单向 transfer 为正”，不可写“model-independent generalization”或“zero-shot generalization”。

### 8. Does it justify K-step?

**不 justify 正式 K-step。** 主要原因不是没有 signal，而是最严格的门槛没有全部通过：September 对 volume 的 CI 跨 0，GLM→Qwen September 反向迁移接近 random，dynamic influence 没有贡献，低量高 influence 审计未形成稳定支持。应先做新时间窗口/新样本的预注册 validation，而不是扩大 K-step 调用规模。

### 9. What is the simplest publishable method?

推荐方法：

1. 以 frozen cheap ranker 为 cheap arm；
2. 用 `RV = full_rr - cheap_rr` 构造监督；
3. 只用显式审计的 cutoff 前数值/时序图特征；
4. June+July 训练，July 只调一次 `K=100` hybrid 权重，随后冻结到 August/September；
5. 每 cutoff 选固定 K 个事件做 Full-CF，其余走 Cheap；
6. 报告 incremental MRR、utility、实测 tokens/latency、NDCG，以及 wallet-cluster bootstrap CI；
7. 把 dynamic influence 作为 negative/ablation arm，而非机制主张。

如果论文更强调可解释性，使用 direct `reasoning_value` predictor 作为 secondary/simple baseline；如果要复现本阶段 September 的最好点估计，使用 July-frozen hybrid，但不得把它包装成独立的 model family breakthrough。

### 10. What should be the primary NAACL/WWW claim?

建议的窄主张：

> **昂贵的 counterfactual reasoning 在 Ethereum wallet-events 上并非均匀有用；一个只使用 cutoff 前信息的 selector 可以在固定事件数预算下识别更高预期 reasoning gain 的事件，并在 August 测试与 September holdout 上稳定超过随机分配。对 volume baseline 的优势在 August 明确、在 September 仍不确定；跨模型证据为部分支持。**

NAACL 方向更自然，因为贡献是 inference-time reasoning allocation；WWW 方向只有在后续把动态 influence 机制重新设计并获得更强多 cutoff 证据后再考虑。不得使用 causal effect、influence causality、zero-shot、SOTA、model-independent superiority 等表述。

## 4. K=100 benchmark snapshot

以下数值来自 `SEL_BENCH_001`；`incremental_mrr` 是每个 cutoff 全部事件上的增量 MRR，`utility_mrr = cheap_mrr + incremental_mrr`。`oracle` 只作 future-RV upper bound，`all_full` 是非 matched-K 的全成本参考。

| split | selector | incremental MRR | utility MRR | selected RV mean | NDCG@K | measured tokens | latency (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| July tune | hybrid | 0.05160 | 0.37882 | 0.51596 | 0.54270 | 975,950 | 1,199.5 |
| July tune | reasoning_value | 0.05077 | 0.37799 | 0.50769 | 0.53998 | 948,595 | 1,197.2 |
| July tune | random | 0.01136 | 0.33858 | 0.11358 | 0.24557 | 886,677 | 1,236.4 |
| July tune | volume | 0.00988 | 0.33711 | 0.09884 | 0.26384 | 1,011,800 | 1,203.9 |
| August test | hybrid | 0.04833 | 0.37788 | 0.48332 | 0.51108 | 991,099 | 1,206.6 |
| August test | reasoning_value | 0.04862 | 0.37817 | 0.48619 | 0.52376 | 938,939 | 1,224.5 |
| August test | random | 0.01099 | 0.34054 | 0.10991 | 0.21358 | 878,246 | 1,227.1 |
| August test | volume | 0.01231 | 0.34186 | 0.12314 | 0.26343 | 1,020,025 | 1,205.3 |
| August test | dynamic influence | 0.00406 | 0.33361 | 0.04060 | 0.15781 | 1,051,720 | 1,286.7 |
| September holdout | hybrid | 0.02963 | 0.38490 | 0.29629 | 0.38365 | 997,697 | 1,226.7 |
| September holdout | reasoning_value | 0.01677 | 0.37204 | 0.16766 | 0.29006 | 964,134 | 1,243.6 |
| September holdout | random | 0.00828 | 0.36356 | 0.08285 | 0.27202 | 865,665 | 1,213.5 |
| September holdout | volume | 0.01840 | 0.37368 | 0.18404 | 0.32210 | 1,004,234 | 1,197.6 |
| September holdout | dynamic influence | 0.00813 | 0.36341 | 0.08134 | 0.19936 | 1,058,939 | 1,301.5 |

补充参考：`all_full` 在 August 的 incremental MRR 为 `0.10991`、实测 tokens `8,782,460`；September 为 `0.08285`、`8,656,648` tokens。它不是 K=100 matched-budget comparator。

## 5. Statistical interpretation and multiplicity

- Bootstrap dependency unit 是 wallet；August 有 841 个 wallet clusters，September 有 824 个，Aug+Sep joint 有 1,593 个；每个比较 `B=2000`。
- `SEL_STATS_001` 输出了 315 条比较（3 learned selectors × controls × K × evaluation summaries）。最终报告的 primary family 是 K=100 hybrid 对五个 control、三个 evaluation summaries；该 family 内使用 Holm correction。
- 全部 registered exploratory comparisons 的 Holm 值更保守，不作为 headline significance gate。表中只报告 point estimate、95% CI、p-value 与 primary-family correction；不把单个 p-value 当作普遍 superiority。
- direct `reasoning_value` 的 August 对 random/volume CI 为正，但 September 对 random 和 volume 的 CI 均跨 0；这正是选择 hybrid 作为当前 primary implementation、同时拒绝完整 Phase II-B 进入的原因之一。

## 6. Adversarial audit summary

`AUDIT_ADV_001`：

- primary forbidden-feature scan：`PASS`；最终显式 feature manifest 不含 post-call LLM/evaluation/truth/cost fields。
- static full-window prior：`CONTEXT_ONLY_LEAKY_PRIOR`；只作上下文，不作 primary selector。
- hybrid score vs as-of wallet volume Spearman：August `0.3335`、September `0.3409`；不是 volume 的同义排序。
- volume-residualized selected RV：August `0.3073`、September `0.1227`；这是 train-only OLS residual 的审计证据，不是因果效果。
- low-volume/high-influence selected share：August `0.020`、September `0.020`；对应 quadrant recall 分别约 `0.0426`、`0.0741`。该审计不支持“selector 稳定发现低量高影响钱包”。
- wallet reuse across the 4,000 events：重复 wallet 占比 `0.2049`（622 个重复 wallet）；wallet/address identity 未作为 model feature。
- label-permutation placebo NDCG@100：August `0.2301`、September `0.1336`；作为 negative control，不能与真实 selector 的 NDCG 直接解释成因果检验。

## 7. Required deliverables and evidence

| deliverable | path | evidence |
|---|---|---|
| Phase-I audit + June decision | `research/phase2/PHASE1_RESULT_AUDIT.md` | June authorized-Qwen/fallback decision is explicit |
| reasoning gain data | `research/phase2/reasoning_gain_dataset.parquet` + manifest | `DATA_RG_001`, n=4,000 |
| dynamic influence data | `research/phase2/dynamic_influence_dataset.parquet` + manifest | `DATA_DI_001`, n=97,305 |
| selector benchmark | `research/phase2/selector_benchmark.csv` | `SEL_BENCH_001`, 378 rows |
| selector model contract | `research/phase2/selector_results/selector_model_manifest.json` | 70 primary candidates; frozen dates; weights |
| statistical tests | `research/phase2/selector_results/bootstrap_comparisons.csv` | `SEL_STATS_001`, 315 rows, B=2,000 |
| cross-model control | `research/phase2/selector_results/cross_model_robustness.csv` | `ROBUST_GLM_001`, 128 rows; June GLM excluded |
| adversarial audit | `research/phase2/selector_results/adversarial_audit.csv/.json` | `AUDIT_ADV_001`, 55 rows; forbidden scan PASS |
| figures | `research/phase2/figures/*.pdf` | six files, `FIG_PHASE2_001` |
| reproducibility manifests | `research/phase2/selector_results/run_manifest.json`, `phase2_selector_summary.json`, `figure_manifest.json` | no external API/LLM calls; input and output provenance |

## 8. Negative and unsupported claims to preserve

The following are explicitly **not** conclusions of Phase II-A:

- dynamic influence beats static importance;
- low-volume/high-influence wallets are reliably found by the learned selector;
- hybrid is an independent winner over direct RV prediction in all windows;
- the result is causal, model-independent, zero-shot, or SOTA;
- the September holdout proves superiority over volume;
- the sampled-pool next-counterparty MRR result from `nc_v1` is full-candidate performance;
- any GLM June anomalous panel is valid training evidence;
- `all_full` is a matched K=100 budget comparator.

## 9. Final scientific verdict

**Phase II-A succeeds as a bounded discovery and failure-aware handoff, not as a full confirmation of the broad success statement in plan §25.** The strongest surviving hypothesis is:

> Reasoning gain is heterogeneous, and a leakage-aware pre-reasoning selector can provide reliable above-random allocation of expensive reasoning at a fixed event-count budget. The effect is strongest in August, remains positive against random in September, but requires a new pre-registered validation before claiming robust superiority over strong naive allocation or across model families.

That is the result to hand to the next research cycle.
