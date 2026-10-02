# WALK — 多 cutoff walk-forward 验证组（Phase I）

把 Group B 的单点描述性结果（06 训练 / 07 验证 / 08 冻结 / 09 holdout）升级为
**多 cutoff、带显著性、可复现**的结论。全部产物在本目录，不改动其他组文件；
BigQuery≈0（只读本地 parquet/CSV），CPU-only，无 LLM，未安装新包（`.venv-cuda`）。

## 复现

```bash
cd /storage/gaoym/ex-graph-microtransaction-analysis
.venv-cuda/bin/python research/walkforward/run_walkforward.py
```

输入（只读）:
- `research/groupA_behavior/results/data/asof_monthly_2022.parquet`（dev 05-08，78,786 行）
- `research/groupA_behavior/results/data/feature_matrix_20220901.parquet`（holdout 09，18,519 行）
- `research/groupB_predictive/results/holdout09_predictions.csv`（B 冻结预测分）
- `research/community_temporal/results/data/edges_asof_2022{06,07,08,09}01.csv`（结构选择器）

## 方法与冻结边界

- 协议: `research/audit/temporal_protocol.yaml` v1.0 + `research/audit/DATA_AUDIT.md`。
- Walk-forward（扩张窗口，仅用 cutoff 之前数据）: 06←{05}；07←{05,06}；08←{05,06,07}；
  holdout 扩展模型←{05..08}。05-01 无更早快照 ⇒ 无 predictive 分（文档化）。
- 模型: LightGBM（n_estimators=300, lr=0.05, num_leaves=31, seed=2022, early-stop 50, CPU），
  与 Group B 冻结配置一致；24 个 base 特征；回归目标 log1p(fwd30_evt_cnt)，
  分类 fwd30_evt_cnt>0；排除 importance_proxy_p3。
- 选择器: predictive（回归分为主，act_bin/new_level 为辅助）、volume（evt_cnt_90d）、
  activity（active_days_90d）、random（固定 seed）、structural（edges_asof degree/PageRank，支持集分开报）。
- 显著性: dev 上按 cutoff 配对 bootstrap（B=2000，seed 2022），差值 CI 不含 0 才算正结果。
- Holdout: 只评估一次（不调参/不调 K）；headline K=100 在 dev 上预注册。

## 文件清单

| 文件 | 说明 |
|---|---|
| `run_walkforward.py` | 全部实验脚本（可重跑，确定性 seed） |
| `WALK_REPORT.md` | 结论报告 + 逐条 [已验证]/[未证实]/[负结果] 判定 |
| `README.md` | 本文件 |
| `data/schema_check.json` | dev/holdout schema 一致性 + 09-01 标签 parity |
| `data/dev_selector_scores.parquet` | dev 每 cutoff 每 wallet 选择器分 |
| `data/holdout_selector_scores.parquet` | holdout 选择器分（B 冻结 + wf 扩展共用结构列） |
| `data/dev_metrics.parquet` | dev 每 cutoff×selector×K 的 U_total/U(K)/U(K)/K/Recall@K |
| `data/holdout_metrics.parquet` | holdout 同上（predictive_source 区分 B 冻结 / wf 扩展） |
| `data/bootstrap_ci.json` | 全部配对 bootstrap CI |
| `data/budget_saving.json` | volume K' 达到 predictive U(K) 的预算对照 |
| `results/walkforward_summary.json` | 上述全部的一体化 JSON |
| `figures/*.png` | utility frontier / Recall@K / budget saving 图 |

## 主要结论（详见 WALK_REPORT.md）

- ① predictive 的 U(K)（每钱包均值）跨 06/07/08 显著优于 volume（K=100: +78.6, 95%CI [50.0,114.2]）
  与 activity（+94.4, [55.2,153.9]）⇒ [已验证]；Recall@K 差异绝对值极小（基数高，见报告）。
- ② 方向跨 K 稳健（7/7 K 均值为正、无负向反转）[已验证-方向]；显著性覆盖 U 6/7、Recall 4/7 ⇒
  “所有 K 显著为正” [未证实]。
- ③ holdout 09-01（B 冻结分）K=100: predictive U(K)=458.4 > volume 429.7 > activity 373.3，
  与单点结论方向一致 [已验证-方向]，增量中等 [已验证-大小]。
- ④ 预算价值: 全 K 网格 K' > K（dev K=100: K'=143, 省 29.6%；holdout: K'=115, 省 13.0%），
  predictive 比 volume 预算更高效 [已验证-方向]，幅度随 K 收窄。

## 边界 / 未完成

- 只有 3 个模型可评估的 dev cutoff（06/07/08），cutoff 级 bootstrap 粒度粗；
- 单月标签（30d）、单一数据窗口（2022）；无 2022-10 之后外推；
- 结构选择器只在支持集（06:11,370 / 07:10,172 / 08:8,927 / 09:7,929）上有定义；
- 预测影响是描述性预测，不构成因果或市场影响力结论。
