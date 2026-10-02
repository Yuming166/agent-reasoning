# research/final_handoff/ — FINAL 组交付（Phase-I 最终整合，2026-09-11）

本目录是 autoresearch_phase1.md Phase-I 的最终整合产物，全部只写本目录、只读复用
Group 0/A/B/C/D/E/F + CHIEF/SELECT/BENCH/COMM 的冻结产物。

## 文件清单

| 文件 | 内容 |
|---|---|
| `final_topk_lists_20220901.csv` | 长表：主/次级/基线/共识 13 种方法 × K∈{10,25,50,100,250,500,1000} 的 top-K 钱包（含 score/rank/支持集/fwd30 标签） |
| `final_topk_lists_20220901.json` | 结构化 top-K（方法→K→[{target_address,score,rank}]）+ 方法定义 + 共识定义 |
| `final_ranking_20220901.csv` | 18,519 钱包 × 五维重要性向量 I_i(t) + 各方法排名 + 共识投票 + 支持集标志 + fwd30 标签 |
| `final_evaluation_20220901.json` | 单次冻结评估：U(K)、U(K)/K、Recall@K、mass share、支持集边界、oracle/随机参考、与冻结数字的 parity 验证 |
| `PHASE2_HANDOFF.md` | Phase-I→II 交接：推荐方法与边界、动态 I_i(t) 按 cutoff 交付物、数据契约、LLM 端点、外部基准钩子、排除范畴、开放项 |
| `PHASE1_SUMMARY.md` | 方案 §4 十五项 Scope 逐项状态（✅/🟡/❌ + 产物 + 关键数字）+ §25 Stop Conditions 对照 |
| `src/build_final.py` | 可复现脚本（CPU only、无 LLM、无 BigQuery）；运行：`.venv-cuda/bin/python research/final_handoff/src/build_final.py` |

## 核心结论（cutoff=2022-09-01，单次冻结 holdout，n=18,519）

- 主选择器 = Group B 预测影响（`pred_act_level_LightGBM`）：K=10 U/K=2,072.3（fwd30 事件均值，
  全集均值 19.57 → lift 106×）；K=100 = 458.4；Recall@K(新对手方, K=1000)=0.094。
- 次级 = Group C 结构重要性（`structure_pct`，支持集 7,929，不外推）；强制基线 A-vol/随机同表。
- 共识组合 B∩C∩A（K=100 n=28，随机期望 0.016）：稳健子集，但共识≠正确性。
- 全部数字与 `selection_eval/results/selection_results_20220901.json` 和
  `chief_merge/consensus_analysis/results/consensus_summary.json` 逐项 parity（脚本验证 0 差异）。
- 铁律遵守：无未来泄漏；holdout 只评估一次；K 不在 holdout 上调参；不声称因果/有效性/优越性/SOTA。
