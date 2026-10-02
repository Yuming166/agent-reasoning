PROJECT: EX-Graph Ethereum on-chain behavioral inference, NAACL-oriented autoresearch.
DATE: 2026-09-20T10:15:12Z
CHARTER_SHA256: 87150bad66f72a995d5f928ef87ec0b53c10ba1c4cc6bae0e51b40fa822972dd

NON-NEGOTIABLE BOUNDARIES:
- Astra6 is the only cognitive model; no fallback.
- Address-level actor proxy, not verified owner psychology or true belief.
- Existing August frozen tests cannot be retuned.
- No large new LLM experiment before initial falsification/literature gate.
- Natural language must be a scientific object, not merely a reporting layer.
- Discovery results are not confirmatory.

INITIAL BRANCHES:
- A: Evidence-Validity Gap
- B: Behavioral Equifinality
- C: Falsifiable Behavioral Hypothesis Induction
- D: Behavioral Hypothesis Revision
- E: Predictability x Interpretability
- F: Identifiability-Aware Selective Inference

FROZEN PROJECT HISTORY — PHASE I:
# PHASE1_SUMMARY.md — Phase-I 十五项 Scope 逐项状态（FINAL 组，2026-09-11）

- 生成: `research/final_handoff/`（FINAL 组，cloud82 10.63.0.82）
- 依据: `research/autoresearch_phase1.md` §4（Scope）+ §13/§14/§15/§16 + §25（Stop Conditions）
- 冻结协议: `research/audit/temporal_protocol.yaml` v1.0 + `research/audit/DATA_AUDIT.md`
- 状态图例: ✅ 完成 / 🟡 完成但有边界 / ❌ 未完成+原因
- 铁律: 无未来泄漏；holdout 只评估一次；不声称因果/有效性/优越性/SOTA；支持集受限与全集分开报告。

## 总览表（§4 十五项）

| # | Scope 项 | 状态 | 关键产物 | 关键数字 |
|---|---|---|---|---|
| 1 | 数据与泄漏审计 | ✅ | `audit/DATA_AUDIT.md`、`audit/temporal_protocol.yaml` v1.0、`audit/bq_metadata_2026-09-11.json` | dev/holdout 分区不重叠；11.63M dev 行/1.43M holdout 行；4 项冻结口径；7 项无法独立验证已显式声明 |
| 2 | 时序状态构造 | ✅ | Group B `wallet_asof_features_20220901`（18,519）、`labels_20220901_bq.csv`、序列组合视图 | 90 天 as-of 特征 `[2022-06-03, 09-01)`；fwd30 标签 `[09-01,10-01)`；标签 0-diff parity（B↔A↔C，CHIEF 复核） |
| 3 | 行为表示 | 🟡 | Group A `feature_matrix_20220901.parquet`（62 列）、`asof_monthly_2022.parquet` | 23 个行为特征 A_beh 复合；persona-only R²(log1p fwd30_evt)=0.585、增量 ΔR²≈+0.001（无增量）→ 描述性 |
| 4 | 动态行为画像/persona | 🟡 | Group A `persona_assignments_20220901.csv`、`cluster_profiles_20220901.csv`、`evaluation_20220901.json` | K-means K=4 bootstrap ARI 0.418 [0.410,0.428]；trajectory ARI 0.962；相邻月 ARI 0.46–0.60；HDBSCAN noise 45–47% → 无标量排名，不进正式选择器 |
| 5 | 动态社区 | 🟡 | COMM `community_membership_2022*.csv`、`community_importance_20220901.csv`、`community_evolution_summary.json` | 09-01 387 社区；top-100 中 88% bridge-only；月度 membership switch（mapped-only）0.30–0.40；掩蔽为面板 i.i.d. → 描述性 |
| 6 | 竞争重要性定义 | ✅ | CHIEF `COMPARISON.md` + `method_recommendation.md` | 5 类定义全部实现并横向对比（B 预测影响/C 结构/D 信息/A 行为/E Qwen）；B 最强 OOS 选择器 |
| 7 | 预测影响实验 | ✅ | Group B `holdout09_predictions.csv`、`predictive_results_20220901.json`、`predictive_extended09_ablation.json` | LightGBM act_level OOS R²=0.617、Spearman=0.812、Recall@top10%=0.653；new_level R²=0.564、Spearman=0.698；扩展消融轨迹/网络/USD 几乎无增量（post-hoc） |
| 8 | 信息增益/反事实 | 🟡 | Group D `wallet_ig_20220901.csv`、`SUMMARY.json`、`wallet_masking_20220901.json`、`community_masking_20220901.json` | 子集 n=2,999；wallet-masking IG(y_cp_ge10) 均值 0.406（ΔNLL）、全掩蔽 AUC→0.50；**IG 与活动/结构 top-K 近正交**；y_active30 top-IG=可预测不活跃（语义，非 bug） |
| 9 | 基准发现与对齐 | ✅ | Group F `benchmark_registry.md`、`exgraph_benchmark_note.md`、`account_classification_track.md` | TGB tgbl-coin-v2、EX-Graph LP、LiveGraphLab、自建 P4 对齐表；27,613 钱包无法干净映射进 EX-Graph LP 图 |
| 10 | 标准基准评估 | 🟡 | BENCH `BENCH_REPORT.md` + 各结果 json | TGB: 活榜 TPNet 0.832（引用）、MLP test MRR **0.7841**（实测）、EdgeBank 0.3590；EX-Graph LP heuristics test AUC 0.634–0.775；**GNN 级基线未跑**（dgl/PyG 重依赖） |
| 11 | 新基准设计 | ✅ | SELECT `README.md`、`manifest.json`、BENCH 报告 §6 | 预算化钱包选择 P4：U(K)/U(K)/K/Recall@K + 支持集纪律 + K 前沿；自建新任务 ≠ SOTA |
| 12 | 预算化选择评估 | ✅ | SELECT `selection_results_20220901.json`、`budget_frontier.csv`、`robustness_0801.json` | 25 选择器 × 7 K；B_act K=10 U/K=2,072（fwd30_evt）≈随机期望 19.57 的 106×；全层级基线同表；08-01 walk-forward 描述性对照 |
| 13 | 跨方法稳健性 | 🟡 | CHIEF `consensus_analysis/results/*`（rank_correlation、pairwise_jaccard、uniqueness、future_utility、consensus_frequency） | B_act↔A_vol ρ=0.930、top-100 Jaccard 0.46；B_act↔C_struct ρ=0.536；D 唯一性最高（top-100 0.94）；B∩C∩A K=100 n=28（随机期望 0.016）；**多 cutoff walk-forward 未跑（单点 09-01）** |
| 14 | 最终选择/排名 | ✅ | `final_handoff/final_ranking_20220901.csv`、`final_topk_lists_20220901.csv/.json`、`final_evaluation_20220901.json` | 主=B_act、次=C_struct、基线=A-vol/随机、共识=B∩C∩A；单次冻结评估：B_act K=10 U/K=2,072.3、K=100=458.4、Recall@K(新对手方) K=1000=0.094 |
| 15 | Phase-II 交接 | ✅ | `final_handoff/PHASE2_HANDOFF.md` | 动态 I_i(t) 按 cutoff 交付物、数据契约、LLM 端点、外部基准钩子、排除范畴、8 项开放项 |

## 逐项细节与证据（仅摘录关键 claim 边界）

### 1 数据与泄漏审计 — ✅
- dev 最大分区 20220831 < holdout 最小分区 20220901（已实测）；schema 差异（trace_address 类型）
  已冻结为走组合视图/显式 CAST；静态图/未来价格/未来推文不得进入 as-of 特征；
  P3 同快照排名仅演示。7 项无法验证（外部源表完备性、twitter_matching 来源、sentiment 派生等）已显式声明。

### 2 时序状态构造 — ✅
- 09-01 as-of 快照 18,519 钱包（27,613 目标中有 90 天事件的活跃子集）；fwd30 标签三列
  （evt_cnt/cp_distinct/new_cp）由 Group B 有界拉取（bytesBilled≈10MB），与 A/C 内嵌标签 0-diff。

### 3 行为表示 — 🟡 完成但有边界
- 62 列 as-of 数值特征（活动/对手方/轨迹/USD/静态结构）。序列 embedding 仅 800 钱包 pilot
  （silhouette 0.232 vs 数值 0.192）——小样本，不外推。

### 4 动态行为画像 — 🟡
- persona 是离散画像，无标量排名；对连续特征预测无增量（ΔR²≈+0.001）；
  网络覆盖 42.8%、USD 覆盖 91.3%/35.8% 存在选择偏差 → 只做描述性/解释层。

### 5 动态社区 — 🟡
- 09-01 387 社区、top-100 88% bridge-only、HHI 0.2442；月度节点集漂移大（新节点 7–10%/月）；
  switch rate 需区分集合漂移 vs 归属变化（COMM 已用 Hungarian 匹配改进）；
  community-masking 为面板 i.i.d.，跨钱包影响未覆盖。

### 6 竞争重要性定义 — ✅
- A(行为)/B(预测影响)/C(结构)/D(信息增益)/E(Qwen 语义) 五类实现；CHIEF 横向对比表完成；
  E 组仅 n=200，不进 top-K 共识。

### 7 预测影响实验 — ✅
- 严格时序 OOS：train 06-01 / val 07-01 / frozen-test 08-01 / holdout 09-01；
  LightGBM act_level 为最强选择器；扩展消融（轨迹/网络/USD）为 post-hoc，无增量如实报告。

### 8 信息增益/反事实 — 🟡
- 2,999 子集上 wallet-masking 与 feature-masking IG 已跑（面板 i.i.d. 设定）；
  低量高信息子组（n=15，IG +1.61 / volume $2）需 walk-forward 复核；
  反事实解释限于"遮蔽该钱包状态后预测性能变化"，非跨钱包传播因果。

### 9 基准发现与对齐 — ✅
- registry 覆盖 TGB(tgbl-coin-v2/tgbn-token)/EX-Graph LP/LiveGraphLab/P3 标签；
  对齐结论：27,613 目标 ↔ EX-Graph LP 图无干净映射，外部通道只能图级/全图验证。

### 10 标准基准评估 — 🟡 完成但有边界
- TGB/EX-Graph LP 最小闭环已实测（见 PHASE2 §6 表）；GNN 级模型未跑（环境重依赖），
  论文表 5 数字仅引用非实测；EX-Graph leaderboard 404 无法提交。

### 11 新基准设计 — ✅
- P4 预算化钱包选择（as-of 选择 → 冻结 top-K → fwd30 效用）已成型：指标、支持集纪律、
  K 前沿、oracle/随机参考均已定义并产出 09-01 结果。

### 12 预算化选择评估 — ✅
- 25 选择器 × 7 K 全层级基线（§14 要求项全部覆盖：random/size/structural/behavioral/
  temporal/predictive/information + hybrid）；`budget_frontier.csv` 231 行原生 + 322 行受限；
  08-01 描述性稳健对照已跑（`robustness_0801.json`）。

### 13 跨方法稳健性 — 🟡 完成但有边界
- 秩相关/重叠/唯一性/共识频率/未来效用已全部量化（CHIEF §2、§3）；
  **未完成**：多 cutoff walk-forward（B/C/D 现为单 cutoff 09-01）→ 已移交 Phase-II 开放项 #1；
  事件级 next-counterparty MRR 未做 → 开放项 #2。

### 14 最终选择/排名 — ✅
- 按 CHIEF 推荐：主=B_act、次=C_struct、强制基线 A-vol/随机、共识组合 B∩C∩A；
  产出见 §"总览表"第 14 行与 `final_evaluation_20220901.json`（verification.parity_ok=true，
  与 SELECT/CHIEF 冻结数字逐项一致）；五维向量支持集边界在 CSV 中以 NaN + 标志列标注。

### 15 Phase-II 交接 — ✅
- PHASE2_HANDOFF.md 完整回答"固定预算下把昂贵推理花在哪些钱包上"：按 B_act top-K 分配、
  结构/信息侧单独记账、数据契约/LLM 端点/外部基准钩子/排除范畴/8 项开放项齐备。

## Stop Conditions 对照（§25）

| 条件 | 状态 |
|---|---|
| 1 时间协议审计 | ✅ v1.0 冻结 |
| 2 泄漏审计通过 | ✅ |
| 3 多种重要性定义已测 | ✅ 5 类 |
| 4 强基线已评估 | ✅ §14 全层级 |
| 5 至少一次严格 OOS 评估 | ✅ 09-01 冻结 holdout 单次 + 08-01 描述性 |
| 6 基准兼容性已评估 | 🟡 TGB/EX-Graph LP 实测；GNN 级未跑 |
| 7 动态 persona 分析充分 | 🟡 描述性充分，选择增量≈0 |
| 8 重要钱包排名可复现 | ✅ build_final.py 确定性复现，与冻结数字 parity |
| 9 K 预算曲线 | ✅ |
| 10 最终选择策略冻结 | ✅（09-01；多 cutoff 策略移交 Phase-II） |
| 11 Phase-II 交接完成 | ✅ |

> 结论：Phase-I 在 2022-09-01 单点冻结评估上完成全部 15 项（其中 4 项带边界、0 项阻塞）；
> 未将代理成本/图中心性/预测 R² 重贴为因果/优越性/SOTA；高阶级递归范畴未触碰。


FROZEN PROJECT HISTORY — PHASE II-A:
# Phase II-A → Next-cycle Decision Handoff

- **Date**：2026-09-12
- **Phase**：II-A Reasoning-Worthiness
- **Handoff status**：交付完成；**正式 Phase II-B = NO-GO**
- **Allowed continuation**：受限 validation/follow-up；不得直接扩大为 K-step
- **Final script SHA-256**：`9a854002f01f68ac2b8a06340be25f3b90a31b13bcd0f6aaf3bebb6a49d4fb1a`

## 1. One-line handoff

保留“昂贵推理的价值具有事件异质性，cutoff 前 selector 能在固定事件数预算下稳定超过 random”的窄结论；暂不把它升级为“超过所有强 naive baseline、跨模型稳健、可直接进入 K-step”的宽结论。

## 2. Gate decision

| Phase II-B criterion | 判定 | 证据/边界 |
|---|---|---|
| RV heterogeneous | **PASS** | 4,000 事件；stratum mean `0.0059`–`0.3283`；median overall `0` |
| Pre-reasoning selector > random | **PASS（hybrid）** | K=100；Aug +0.03734 CI `[0.02611,0.04895]`；Sep +0.02134 CI `[0.01184,0.03179]` |
| > strong naive baselines | **PARTIAL** | Aug > volume CI 不含 0；Sep > volume CI `[-0.00363,0.02548]` 跨 0 |
| August frozen test | **PASS** | hybrid incremental MRR `0.04833` vs random `0.01099`、volume `0.01231` |
| September independent holdout | **PARTIAL** | hybrid > random；对 volume 只有正点估计，未达 CI 门槛 |
| Volume confound audit | **PARTIAL/PASS AS AUDIT** | hybrid score-volume ρ `0.3335`/`0.3409`；residual selected gain 为正；不能做因果解释 |
| Leakage audit | **PASS** | explicit feature contract；forbidden primary scan PASS；static full-window prior 隔离 |
| Matched event-count and measured cost | **PASS** | K 网格固定；tokens/latency 逐 selector 实测；token 不假设完全相等 |
| Reproducibility | **PASS** | registry、脚本 hash、run/model/figure manifests、CSV/Parquet/PDF 完整 |
| Qwen↔GLM panel agreement | **PARTIAL** | RV Spearman `0.793`–`0.811`；agreement 约 `0.890`–`0.897` |
| Bidirectional model transfer | **FAIL AS FULL GATE** | GLM→Qwen September K=100 `0.00837`，近 Qwen random `0.00828` |
| Dynamic influence mechanism | **FAIL/NEGATIVE** | DI selector Aug/Sep `0.00406`/`0.00813`，未胜出；tuned weight = 0 |
| Low-volume/high-influence discovery | **FAIL AS CLAIM** | learned selector selected share 约 2%，无稳定覆盖证据 |
| Paper-level broad claim | **NO-GO** | 只能支持窄 claim，不支持 Phase §25 全句 |

### Final decision

**NO-GO for formal Phase II-B.** 当前阶段最接近 plan §22-C（reasoning gain works but influence does not），但还需把 September 对 volume 的不确定性和反向跨模型失败作为明确 limitation，而不是把 August 的强结果外推成完整成功。

## 3. Frozen method to carry forward

### Primary implementation for validation

- `HistGradientBoostingRegressor`，seed `42`。
- Input：70 个显式 audited as-of/pre-call numeric candidates；不含 future spillover、RV labels、truth/evaluation ranks、LLM usage/cost、full-window static prior。
- Train：June 1, 2022；July 1, 2022 只做权重调参。
- Frozen hybrid weights：

```yaml
rv_pred: 0.50
di_pred: 0.00
behavior_pred: 0.25
uncertainty_pred: 0.25
novelty_pred: 0.00
```

- Test：August 1, 2022；holdout：September 1, 2022；不做 August/September refit。
- Primary allocation：每 cutoff `K=100`；完整网格保留 `10/25/50/100/250/500/1000`。
- Cheap arm：事件不入选时保持 frozen Cheap；选中事件应用已有 Qwen Full-CF panel gain。
- `dynamic_influence`、`volume`、`random`、`activity`、static prior 等继续作为 registered controls/ablations。

### Methodological caution

- “equal budget” headline 使用 fixed selected-event count；actual selected Full-CF tokens/latency 作为 secondary cost axis。
- `oracle` 只允许作为 future-RV upper bound。
- `all_full` 是 full-cost reference，不是 K=100 matched-budget comparator。
- RV、dynamic influence、volume residual 均为预测/审计量，不是因果量。

## 4. Artifact handoff

| ID | Path | Status | Handoff use |
|---|---|---|---|
| `DATA_RG_001` | `reasoning_gain_dataset.parquet` + `reasoning_gain_manifest.json` | COMPLETE | frozen Qwen RV labels/features |
| `DATA_DI_001` | `dynamic_influence_dataset.parquet` + `dynamic_influence_manifest.json` | COMPLETE | influence control/negative result |
| `SEL_BENCH_001` | `selector_benchmark.csv` + `selector_results/selector_benchmark_long.csv` | COMPLETE | benchmark source table, 378 rows |
| `SEL_STATS_001` | `selector_results/bootstrap_comparisons.csv` | COMPLETE | wallet-cluster CI, 315 rows, B=2,000 |
| `ROBUST_GLM_001` | `selector_results/cross_model_robustness.csv` + manifest | COMPLETE/PARTIAL | valid GLM v2 control; June excluded |
| `AUDIT_ADV_001` | `selector_results/adversarial_audit.csv/.json` | COMPLETE | leakage/volume/placebo/quadrant audit |
| `FIG_PHASE2_001` | `figures/*.pdf` + `figure_manifest.json` | COMPLETE | six paper figures |
| — | `selector_results/run_manifest.json` | COMPLETE | no external API/LLM calls; input hashes |
| — | `selector_results/selector_model_manifest.json` | COMPLETE | frozen feature groups and weights |
| — | `selector_results/phase2_selector_summary.json` | COMPLETE | machine-readable K=100 summary |

## 5. Reproduction command

From `/storage/gaoym/ex-graph-microtransaction-analysis`:

```bash
.venv-cuda/bin/python research/phase2/run_selector_benchmark.py \
  > research/phase2/run_logs/selector_benchmark_20260912.log 2>&1
```

Expected terminal summary:

```text
loading inputs
rows 4000 DI rows 97305
scores built; hybrid weights {'rv_pred': 0.5, 'di_pred': 0.0, 'behavior_pred': 0.25, 'uncertainty_pred': 0.25, 'novelty_pred': 0.0}
benchmark rows 378
strata rows 56
bootstrap rows 315
cross-model rows 128
audit rows 55
complete
```

This command is deterministic CPU analysis and makes no LLM request. The current registry records the same script hash prefix for `SEL_BENCH_001`, `SEL_STATS_001`, `ROBUST_GLM_001`, `AUDIT_ADV_001`, and `FIG_PHASE2_001`.

## 6. Constraints for the next cycle

1. Do not call `http://10.63.0.72:8317/v1`; do not probe or reuse Codex/Claude service endpoints or credentials.
2. Any new research LLM call must remain on the authorized local services: Qwen chat `http://127.0.0.1:31518/v1` and embedding `http://127.0.0.1:31522`.
3. Never send raw transaction/event-level data to an external API. External-facing summaries, if ever needed, must be as-of aggregates only.
4. Do not modify `artifacts/`, frozen panels, or `src/` as part of the next validation unless explicitly re-scoped.
5. Preserve June decision: authorized Qwen rerun is training evidence with audited fallback label; GLM June anomaly remains quarantined.
6. September remains holdout. Any new weighting, feature selection, or threshold tuning must use a newly declared development split and be marked post-hoc if applied to current outputs.
7. Never report `nc_v1` sampled-pool MRR `0.896` as broad/full-candidate performance.
8. Do not occupy GPU4/6; current handoff requires no GPU.

## 7. Recommended restricted follow-up (not Phase II-B)

Before any K-step expansion, run a new registered validation with the following gates:

### Must-have

- at least one genuinely new temporal window or larger event panel;
- same pre-registered feature contract and no tuning on the final holdout;
- explicit direct-RV vs hybrid ablation;
- exact comparison against random, volume, activity, and a predeclared static/as-of graph baseline;
- wallet-cluster CI and a clearly declared primary comparison family;
- bidirectional model transfer with a fresh independent holdout, including CIs where feasible;
- a token-budget sensitivity analysis in addition to fixed-K analysis.

### Stop conditions

- if hybrid/direct-RV advantage disappears against volume on the new holdout, stop the K-step proposal;
- if GLM→Qwen-like reverse transfer remains near random, keep the claim model-specific/partial;
- if dynamic influence again receives zero weight and fails baseline comparisons, remove it from the main method rather than tuning it post-hoc;
- if low-volume/high-influence coverage remains unstable, drop that subclaim.

### Explicitly prohibited next claims

- causal influence or causal reasoning effect;
- dynamic influence beats static importance;
- model-independent or zero-shot generalization;
- SOTA or universal budget optimality;
- September proof of superiority over volume;
- hybrid as an independent winner without direct-RV ablation.

## 8. Chief scientist handoff sentence

> **Proceed only with a constrained replication/validation of pre-reasoning reasoning-gain selection; do not start formal K-step.**


FROZEN PROJECT HISTORY — OW-010B:
# OW-010B Decision

**Date:** 2026-09-18 UTC  
**Experiment:** OW-010B — Blind Incremental Temporal-Structural Signal Test  
**Decision:** `NO_GO_OPENWORLD_STRUCTURAL_SIGNAL`

## Decision basis

The frozen August test supports an M1-over-M0 predictive gain but not the preregistered structural-support criterion:

- Ridge M1-over-M0: `11.660%`, absolute paired 95% CI `[0.085655, 0.095335]`.
- Ridge M2_CORE-over-M1: `0.1338%`, absolute paired 95% CI `[0.000316, 0.001559]`, below the frozen `2%` gate.
- HGB M2_CORE-over-M1: `-0.0301%`, CI `[-0.001043, 0.000621]`.
- Negative controls did not reproduce the intended gains.
- Activity/degree audits do not eliminate the possibility that M1/M2 variables are scale and autoregression proxies.
- The test contains one frozen held-out cutoff and is dominated by repeated wallets.

## Operational disposition

- **Do not open OW-010C.** No external-label evaluation is authorized by this result.
- **Do not build a Temporal GNN.** The simple structural block did not pass the frozen gate.
- **Do not start latent-strategy/LLM inference.**
- **Do not retune the target, thresholds, feature block, model grid, cutoffs, or decision rule using the August result.**
- Preserve the M1 result as a bounded/provisional recent-dynamics forecasting finding.
- Classify M2 structural evidence as insufficient and exploratory.
- If the research continues, create a new preregistered amendment before any new result is inspected; it should separate recent activity/autoregression from temporal organization and address structural/activity collinearity.

## Status labels

```text
M1 recent-dynamics signal: PROVISIONAL_PREDICTIVE_FINDING
M2 structural signal: NO_GO_UNDER_FROZEN_GATE
OW-010C: CLOSED
Temporal GNN: NOT_JUSTIFIED
Wash-label access: FALSE
```

Astra6 used the compatible operational phrase `NO_GO_TO_OW010C under the frozen rule; MODIFY_BEFORE_EXTERNAL_VALIDATION` for a possible future redesign. The formal OW-010B decision field remains exactly:

```text
NO_GO_OPENWORLD_STRUCTURAL_SIGNAL
```


FROZEN PROJECT HISTORY — DECISION-STATE V1:
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


APPEND-ONLY NEGATIVE MEMORY:
# Negative Results (append-only)

## 2026-09-19 — Decision-State V1

- B4 intervention-verified LLM features worsened August frozen test macro log loss versus M1: 0.840193 vs 0.810633.
- Evidence intervention responsiveness passed on July development, but did not imply prospective validity.
- Do not claim true belief recovery, causal provenance, persistent latent state, or Level-2 relational expectation.

## 2026-09-18 — OW-010B

- M1 recent-dynamics gain was provisional and structurally confounded/possibly autoregressive.
- M2_CORE-over-M1 failed the preregistered cross-model 2% structural gate; do not build Temporal GNN or open OW-010C.

## 2026-09-12 — Phase II-A

- Selective reasoning value was heterogeneous and beat random in a narrow setting, but September versus volume and bidirectional transfer were incomplete; formal Phase II-B/K-step was NO-GO.

New entries must be appended; prior entries must never be rewritten or deleted.


NEW DETERMINISTIC PRIORITY AUDIT SUMMARY:
{
  "source": "/storage/gaoym/ex-graph-microtransaction-analysis/research/decision_state/results/decision_state_case_degradation_analysis.csv",
  "source_sha256": "b0ffa7075fc86586e617e2e99234418c25f11d714ca849baad6c04dc90a1e486",
  "n_all_source_rows": 3000,
  "n_oos_rows": 2000,
  "splits": {
    "dev": 1000,
    "test": 1000
  },
  "F_definition": "existing frozen intervention_sensitivity = average of self/market JS distances over four consequence dimensions",
  "Delta_definition": "existing frozen B4_M1_VERIFIED_LLM macro log-loss minus B0_M1 macro log-loss",
  "F_vs_Delta_pearson": -0.033421075141118355,
  "F_vs_validity_proxy_spearman": 0.019366415512223897,
  "F_vs_Delta_spearman": -0.019366415512223897,
  "partial_pearson_F_vs_Delta_controls": -0.03831504464680598,
  "controls_numeric": [
    "history_length_log1p_events_30d",
    "history_event_count_30d",
    "event_count_7d",
    "llm_top_probability",
    "llm_abstain",
    "hypothesis_entropy_nats",
    "panel_repeat_wallet"
  ],
  "controls_categorical": [
    "split",
    "activity_bin",
    "dominant_event_family_30d"
  ],
  "mean_Delta_B4_minus_B0": 0.023495422489501656,
  "median_Delta_B4_minus_B0": -0.01128167920794115,
  "B4_gain_rate": 0.5365,
  "B4_failure_rate": 0.4635,
  "high_F_failure_n": 50,
  "low_F_success_n": 50,
  "discovery_only": true,
  "no_new_llm_calls": true,
  "future_outcomes_used_only_from_frozen_evaluation_artifact": true,
  "status": "DISCOVERY_AUDIT_COMPLETE"
}

NEW PRIORITY AUDIT REPORT:
# Decision-State case-level Evidence–Validity discovery audit

This is a deterministic, discovery-only audit of frozen OOS predictions. It is not a confirmatory result and does not modify the V1 protocol or test set.

- OOS rows: **2000** ({'dev': 1000, 'test': 1000})
- F = frozen intervention sensitivity; Delta = B4 macro log-loss minus B0 macro log-loss.
- Pearson(F, Delta): **-0.0334**
- Spearman(F, validity proxy -Delta): **0.0194**
- Partial Pearson(F, Delta | predeclared controls): **-0.0383**
- Mean Delta: **0.023495**; median Delta: **-0.011282**
- B4 gain rate (Delta < 0): **0.536**; failure rate (Delta > 0): **0.464**

## Outputs

- `priority_case_level.csv`: case-level F/Delta and frozen descriptors.
- `priority_by_F_quintile.csv`: discovery strata by intervention sensitivity.
- `high_F_failure_cases.csv`: high-sensitivity cases where B4 degraded.
- `low_F_success_cases.csv`: low-sensitivity cases where B4 improved.

## Boundary

This audit cannot establish causality, true belief, owner psychology, generalization beyond the frozen panel, or a final paper claim. Any follow-up requires Astra6 adversarial review and a new preregistered protocol/untouched holdout.
