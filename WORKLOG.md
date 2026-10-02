# WORKLOG — Autoresearch Phase I（Ethereum 动态钱包重要性 / 影响力发现）

- 时间段：2026-09-11 ～ 2026-09-12
- 机器：cloud82（10.63.0.82，本机）
- 依据：`autoresearch_phase1.md`（GitHub `Yuming166/agent-reasoning` main）
- 范围：Phase-I（高阶递归之前的全部任务）；**明确排除**：递归辩论 / 递归证据图 / 多步 LLM 推理 / 市场交易 agent

## 0. 基础设施准备（2026-09-11）

- 核验基础条件：本机=cloud82；`ictdata-507912.exgraph` BigQuery 40 张表在库（dev 11.63M 事件 / holdout 1.40M / 27,613 目标地址）；Qwen3.5-4B chat 在 82:31518；GPU：3×V100 + 4×4090（Qwen 占 1 张 4090，embed 服务占 1 张）。
- 补齐两个缺口：
  1. `.venv-cuda` 安装 `google-cloud-bigquery 3.45.0`（本机外网需走代理 10.63.0.72:7890 + ADC）；
  2. 本地模型仓库 `Qwen3-Embedding-0.6B` → 在 GPU3 起 OpenAI 兼容 `/v1/embeddings` 服务（端口 31522，last-token pooling + L2 归一化，1024 维；`src/embed/serve_qwen_embedding.py`，tmux `embed-qwen`）。

## 1. 第一轮：G0 / G A / G F

| 组 | 交付 | 关键结果 |
|---|---|---|
| G0 数据与泄漏审计 | `research/audit/`：DATA_AUDIT.md + temporal_protocol.yaml v1.0（冻结）| 契约与方案 §3 一致；4 项口径必须冻结（trace_address schema 不一致、nc_ranker sentinel 陷阱、P3 仅演示、静态图不入 as-of 特征）|
| G A 行为画像 | `research/groupA_behavior/` | 18,519 钱包 persona 聚类；轨迹表示 silhouette 0.396 最高、ARI 稳定性 0.93–0.97 |
| G F Benchmark/SOTA | `research/groupF_benchmark/` | 20 候选基准带证据标签；唯一活榜单通道 = TGB tgbl-coin-v2 / tgbn-token；EX-Graph leaderboard 404 |

## 2. 第二轮：G B / G C / G D / G E

| 组 | 关键结果（cutoff=2022-09-01，30d 标签，严格 OOS） |
|---|---|
| G B 预测影响 | LightGBM holdout：未来活动 R²=0.617、AUC=0.891；相对最优基线 R² +0.143 |
| G C 时序图 | 静态全图先验 ≠ as-of 结构（秩相关 0.20–0.38）；**低量高结构≈不存在**；结构≠预测影响（ρ≈−0.04）；结构 top-100 中 88% 为 bridge |
| G D 信息增益 | 钱包掩蔽 ΔNLL +0.406；top-100 高 IG 掩蔽 ΔNLL +1.79 vs 高量 +0.99；IG 与 volume/中心性近正交（ρ 0.21–0.37）|
| G E Qwen 语义 | 200 钱包、parse 200/200；Qwen embedding OOF R² 0.23–0.34（低于数值 0.63）但不冗余；拼接未证实 |

## 3. 第三轮：CHIEF / SELECT / BENCH / COMM

| 组 | 关键结果 |
|---|---|
| CHIEF 合并+共识 | §19 对比表；B×A 秩相关 0.930；3 方共识富集 ~1760×（K=100）但由活动量驱动；D 特有唯一性 94%（真正正交维度）；方法推荐：B 主 / C 次 / D 仅描述性 |
| SELECT 预算化选择 | 21 选择器 × K∈{10..1000}；K=10 hybrid 466 > 预测 457 > eth_flow 346 > 体量 304；K=1000 收敛 ~7%；IG 语义陷阱文档化 |
| BENCH 标准基准 | EX-Graph LP 启发式 test AUC 0.634–0.775（审计发现：官方发布图=训练子图）；TGB tgbl-coin-v2 基线 MLP test MRR 0.7841 |
| COMM 时序状态+动态社区 | 四组状态构造与冻结协议一致（parity 实测）；switch rate 35.7%→46.5%；top-2 社区承载预测 top-10% 的 68.1% |

## 4. 收尾：FINAL（最终排名 + Phase-II 交接）

- `research/final_handoff/`：五维重要性向量 I_i(t)（18,519 钱包）、最终 top-K 列表、单次冻结评估、PHASE1_SUMMARY.md、PHASE2_HANDOFF.md。
- 最终：主=B_act（预测影响）、次=C_struct；top-10 U/K=2,072（相对随机 106×）；#1 钱包 `0xcda72070…`。
- Phase-I 15 项 Scope：9 项完成、6 项完成但有边界、无阻塞项。

## 5. 正结果冲刺：WALK / TGB2（2026-09-11 ~ 09-12）

| 组 | 结果 | 判定 |
|---|---|---|
| WALK 多 cutoff walk-forward | dev 06/07/08 + 09-01 holdout；predictive−volume U(K) 差 +78.6，95% CI [50.0, 114.2] 不含 0；预算节省方向一致（K=100 省 13–30%）| **[已验证]** 预测影响跨月显著优于体量/活动（U(K) 维度）|
| TGB2 榜单冲击 | tgbl-coin-v2，23 维 leak-free 前缀特征 + torch-only MLP（v3b）：val 0.8373 / **test MRR 0.8550**；独立复跑逐位一致（VERIFY_NOTE.md）| **[已验证]** 同协议本地评估超活榜榜首 TPNet 0.832±0.001（+0.023）；**非官方提交回执** |
| TGB2 审计 | 修复 3 个实现 bug（标签错位 / reverse-pair 越界 / decay 浮点灾难性消去），无效版本留档 INVALID_RUNS_NOTE.md | — |

## 6. 关键边界声明（全篇统一）

- 除 WALK/TGB2 标注 [已验证] 外，其余均为**单 cutoff（2022-09-01）描述性结果**，不声称因果/有效性/优越性；
- 支持集纪律：结构 7,929 / IG 2,999 与全支持 18,519 分开报告，不外推；
- 预测影响 = 描述性预测（P(Y_future|S_history)），不是因果影响或市场影响力；
- TGB 0.8550 为本地官方协议评估，正式"榜单击败"需经 TGB Google Form 提交 + 公开代码后由官方确认；
- 共识 ≠ 正确性；SOTA 数字均为截至 2026-09-11 的榜单引用。

## 7. 资源使用

- BigQuery：Phase-I 合计 ≈ 1.3 GiB（全部分区过滤 + bytes-billed 上限，无整表导出）；
- 网络：TGB 数据集下载 1.28 GB（单次，走代理）；
- LLM：Qwen chat 200 次 + embedding 13 次（全部落盘缓存）；
- GPU：全程未占他人 GPU；embed 服务常驻 GPU3（~2.5GB），TGB2 训练用 GPU5（<3GB）。

## 8. 文件地图

- `autoresearch_phase1/`：本目录为 Phase-I 全部产出（各组 README/报告、可复现脚本、SQL、关键结果 CSV/JSON、图）。
- `research/audit/` 冻结协议 `temporal_protocol.yaml` v1.0 —— 任何 Phase-I 结果引用该协议后才视为有效。
- 复现：各组 `run_all.sh` / `src/*.py`，环境 `.venv-cuda`（torch cu126 / sklearn / pandas / networkx / lightgbm / hdbscan / pyarrow / google-cloud-bigquery）。

## 9. 未完成项（移交 Phase-II）

1. 多 cutoff walk-forward 扩展到 5 个 cutoff（重建 03/04 特征）；2. next-counterparty 事件级 MRR（支持集 vs full-vocabulary 双口径）；3. C 组 flow 方向语义固定；4. D 组 IG 符号/低量高信息复核；5. E 组大样本互补性；6. 社区 switch 口径正式化；7. TGB/EX-Graph GNN 级基线；8. TGB 官方榜单提交。
