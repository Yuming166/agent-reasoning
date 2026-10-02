# Phase I 动态钱包重要性与影响力发现 — 研究擂台（Research Tournament）

来源：`research/autoresearch_phase1.md`（GitHub `Yuming166/agent-reasoning` main，2026-09-11 拉取）。

核心问题：Which Ethereum wallets are worth paying attention to, at what time, and why?
铁律：无未来泄漏、无循环、影响力≠交易量、预测影响≠因果、重要性可多维。

## 进度注册表

| Group | 名称 | 状态 | 输出目录 | 开始时间 |
|---|---|---|---|---|
| 0 | 数据与泄漏审计 | ✅ 通过(有条件) 2026-09-11 | research/audit/ | 2026-09-11 |
| A | Behavior-First 行为画像 | ✅ 骨架跑通 2026-09-11 | research/groupA_behavior/ | 2026-09-11 |
| F | Benchmark / SOTA 追踪 | ✅ 完成 2026-09-11 | research/groupF_benchmark/ | 2026-09-11 |
| B | Predictive-Influence-First | 运行中 | research/groupB_predictive/ | 2026-09-11 |
| C | Temporal-Graph-First | 运行中 | research/groupC_temporal_graph/ | 2026-09-11 |
| D | Information-Gain / Counterfactual | 运行中 | research/groupD_infogain/ | 2026-09-11 |
| E | Qwen Behavioral Representation | ✅ 骨架跑通 2026-09-11 | research/groupE_qwen/ | 2026-09-11 |

> 规则：任何最终结果必须引用 `research/audit/temporal_protocol.yaml`（Group 0 已冻结 v1.0）后才视为有效。
> 各 Group 独立提交 research question/hypothesis/importance definition/representation/algorithm/
> evaluation protocol/baselines/expected failure modes/compute cost/novelty 后再由首席科学家横向比较。

## 运行环境速查（2026-09-11 实测）

- 本机 = cloud82 (10.63.0.82)。项目 venv：`.venv-cuda`（torch cu126/sklearn/pandas/networkx/hdbscan/pyarrow/bigquery 3.45）。
- LLM：Qwen3.5-4B chat `http://127.0.0.1:31518/v1`（默认，base_url 不含 /chat/completions，勿发 reasoning_effort）。
- Embedding：Qwen3-Embedding-0.6B `http://127.0.0.1:31522/v1`（OpenAI 兼容 /v1/embeddings，1024 维）。
- BigQuery：`ictdata-507912.exgraph`；SQL 用 `src/bq_run.py`（自动走代理 10.63.0.72:7890 + ADC），
  查询必须分区过滤并设 bytes-billed 上限，不整表导出。
- GPU：V100 0-2 现空闲、GPU5 空闲；GPU3=embed 服务(约1.6GB)、GPU4=Qwen chat、GPU6=Hy-MT。勿占用 GPU4/6。
- Group A 已产出的可复用数据：`research/groupA_behavior/results/data/`（feature_matrix_20220901.parquet、
  trajectory_stats_20220901.csv、network_features_20220901.csv、usd_capital_20220901.csv、
  static_prior_20220901.csv、asof_monthly_2022.parquet）与 `persona_assignments_20220901.csv`。

## 第三阶段：高阶递归前的收尾任务（2026-09-11 启动）

| 组 | 任务 | 状态 | 输出目录 |
|---|---|---|---|
| CHIEF | 首席科学家合并(§19) + 跨方法共识(§17) + 方法推荐 | ✅ 完成 2026-09-11 | research/chief_merge/ |
| SELECT | 预算化钱包选择(§9) + K 敏感度(§16) + 基线层级(§14) | ✅ 完成 2026-09-11 | research/selection_eval/ |
| BENCH | 标准 Ethereum 基准评估(§6/§7)：EX-Graph LP + TGB | ✅ 完成 2026-09-11 | research/benchmark_eval/ |
| COMM | 时序状态构造(§2) + 动态社区形式化(§12) | ✅ 完成 2026-09-11 | research/community_temporal/ |
| FINAL | 最终重要钱包排名 + Phase-II 交接 | ✅ 完成 2026-09-11 | research/final_handoff/ |

> 明确排除：高阶递归推理/递归辩论/证据图/多步 LLM 推理/市场交易 agent。

## 正结果冲刺（2026-09-11 启动）：把描述性数字升级为可验证结论

| 组 | 任务 | 状态 | 输出目录 |
|---|---|---|---|
| WALK | 多 cutoff walk-forward 验证 + 显著性(CI) + 决策级预算价值 | ✅ 完成 2026-09-11：U(K) 增益跨月显著 | research/walkforward/ |
| TGB2 | TGB tgbl-coin-v2 榜单冲击（改进简单基线 vs TPNet 0.832） | ✅ 完成 2026-09-12：test MRR 0.8550（独立复跑逐位一致）| research/benchmark_tgb_v2/ |

> 纪律：只报经过多 cutoff + bootstrap CI + 最终 holdout 验证的结论；验证不过就如实标"未证实"。
