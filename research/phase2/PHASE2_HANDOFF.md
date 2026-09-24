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

From `PROJECT_ROOT`:

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

1. Do not call `an unauthorized relay endpoint`; do not probe or reuse Codex/Claude service endpoints or credentials.
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
