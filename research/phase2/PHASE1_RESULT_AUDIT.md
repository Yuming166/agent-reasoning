# PHASE1_RESULT_AUDIT.md — Phase-I 结果审计 + June 解析异常终裁（P2AUDIT）

- 角色：autoresearch Phase-II-A 的 Phase-I 结果审计组（P2AUDIT）
- 日期：2026-09-12（UTC+8；the analysis host）
- 工作目录：`PROJECT_ROOT`
- 依据：`research/phase2/autoresearch_phase2_reasoning_worthiness.md` §4（First task: Phase-I result audit）
- 冻结基线：GitHub main `1d2dfdd`（本地发布仓库 `PUBLICATION_CHECKOUT`，`git rev-parse HEAD = 1d2dfddef868914d3ec869f8948854794f26fd49`）
- 铁律（本窗口）：不使用私人中转站 `an unauthorized relay endpoint`；不调用任何 LLM；纯 CPU 只读分析；
  只写 `research/phase2/`；不改 `artifacts/`、其他组目录、`src/`。
- 机器可读清单：`research/phase2/phase1_result_registry.csv`（35 行结果 + 表头，15 字段）

---

## 0. 审计方法

1. 只读盘点 `research/` 下 14 个 Phase-I 结果单元（`audit/`、`groupA..groupF/`、
   `chief_merge/`、`selection_eval/`、`benchmark_eval/`、`community_temporal/`、
   `final_handoff/`、`walkforward/`、`benchmark_tgb_v2/`）的 README/报告/结果 json/csv；
2. 只读审计 LLM 面板证据：`artifacts/llm_panel_v1/RESULTS_LLM_v1.md`、
   `artifacts/llm_panel_v2/june_parse_audit.json`、`notes/june-parse-audit.md`、
   `notes/node-selection-go-no-go-20260910.md`、`artifacts/llm_panel_v2/runs/*_rerun_*eval.jsonl`、
   `artifacts/llm_panel_v2/node_selection_v2_final_audited_20260910/*`、`artifacts/nc_v1/RESULTS.md`、
   `artifacts/router_v1/*`；
3. 对每项结果登记一行（registry），逐项给出 `decision`；
4. 对 June 解析异常给出最终决策（§4，见下）。

> 说明：Phase-II README 将任务写作“11 组”。实际盘点为 14 个结果目录 + LLM 面板审计项
> （G0、A–F、CHIEF、SELECT、BENCH、COMM、FINAL、WALK、TGB2 共 14 单元；LLM 面板/节点选择器
> 作为 SELECT/路由证据单列 9 行）。本审计覆盖全部 14 单元 + LLM 面板，满足“11+ 组”。

## 1. decision 语义（严格按方案 §4 的 6 类）

| decision | 定义 |
|---|---|
| **KEEP_CORE** | 冻结为 Phase-II 输入：data / split / metric / baseline / leakage / statistics 全部通过审计，Phase-II 可直接依赖 |
| **KEEP_ABLATION** | 保留为必需消融/基线臂（§14 基线层级或组件消融），不作主监督 |
| **KEEP_CONTEXT** | 描述性/上下文证据：可支撑设计、叙事或外部验证，但非正式冻结输入；必须保留 claim 边界 |
| **REPRODUCE** | 相关且结构有效，但验证不足（单 cutoff / 小 n / 无 CI / post-hoc）：Phase-II 依赖前须复现补强 |
| **DROP** | 不可作为证据（无效、支持集伪影、隔离、被取代） |
| **BLOCKED** | 当前环境无法完成/验证（缺 dgl/PyG 重依赖、无官方提交渠道等） |

## 2. 分单元审计摘要

### G0 — 数据与泄漏审计（1 行）
- `G0_data_contract` → **KEEP_CORE**。DATA_AUDIT + temporal_protocol.yaml v1.0 冻结：
  dev/holdout 分区不重叠（11,631,068 / 1,402,392 行）；27,613 目标地址一一映射；
  过滤语义为“至少一端匹配”并显式声明；“双方匹配”口径单列；静态全窗口特征标记为 leaky prior。
  4 项冻结口径、7 项“无法独立验证”已显式声明。

### Group A — 行为画像（3 行）
- `persona_clustering` → **KEEP_ABLATION**。persona-only R²=0.585 但相对 features-only 增量
  ΔR²≈+0.001（无增量）；无标量排名，不作为正式选择器；作为行为层描述与基线臂保留。
- `sequence_embedding_pilot` → **KEEP_CONTEXT**。n=800 pilot，silhouette 0.232 vs 0.192，
  无 CI。
- `reusable_data_assets` → **KEEP_CORE**。特征矩阵/月度 as-of/USD/static_prior 物化，
  标签 parity 与 B/C 0-diff，是 Phase-II 特征与标签基础设施。

### Group B — 预测影响（3 行）
- `predictive_activity_level` / `predictive_new_cp` → **KEEP_CORE**。严格时序 OOS
  （train 06-01 / val 07-01 / frozen test 08-01 / holdout 09-01），holdout R²=0.617 /
  Spearman=0.812 / top-10% Recall@K=0.653；WALK 多 cutoff 配对 bootstrap 验证
  （K=100 predictive−volume +78.55 CI[49.98,114.22]，不含 0）。
- `extended_feature_ablation` → **KEEP_CONTEXT**。09-01 内切分消融为 post-hoc，
  轨迹/网络/USD 几乎无增量（R² +0.010），不作有效性声明。

### Group C — 时序图结构（3 行）
- `structural_importance` → **KEEP_ABLATION**。as-of matched-matched 子图（7,929）上
  structure_pct ρ=0.435，但 volume 始终 > structure（K=100: 429.7 vs 349.3）；
  作为结构侧次级选择器/基线保留，不宣称主导。
- `static_vs_asof` / `structure_vs_influence_orthogonality` → **KEEP_CONTEXT**。
  静态先验 top-100 重叠仅 6–9%（方法学）；结构 vs P2 影响 proxy ρ=−0.036（概念边界）。

### Group D — 信息增益（3 行）
- `wallet_masking_ig` → **KEEP_CONTEXT**。n=2,999 子集、单 cutoff、wallet-CV（已标注非
  walk-forward OOS）；y_cp_ge10 ΔNLL=0.406 支持“钱包历史降低自身未来不确定性”，
  作信息侧辅助信号。
- `ig_topK_masking` → **KEEP_CONTEXT**。top-100 IG ΔNLL 1.79 vs volume 0.99（~1.8×），描述性。
- `residual_analysis` → **REPRODUCE**。低量高影响（n=15，mean IG +1.61，mean volume $2）
  是 §9 volume-adjusted influence 的关键假说基础，但小 n 且单 cutoff；Phase-II 须在
  walk-forward / 全量 27k 上复核后再冻结。

### Group E — Qwen 语义表示（1 行）
- `qwen_representation_pilot` → **KEEP_CONTEXT**。n=200；R_qwen OOF R² 0.23–0.34 < 数值
  0.59–0.64；拼接未超越纯数值；互补性未证实（负结果如实记录）。LLM 不是最终选择器一部分。

### Group F — 基准追踪（1 行）
- `benchmark_registry` → **KEEP_CONTEXT**。TGB tgbl-coin-v2 是唯一活榜单通道
  （TPNet 0.832±0.001，2026-09-11 引用）；EX-Graph LP leaderboard 404；27,613 钱包无法
  干净映射进 LP 图 → 只作图级外部验证。

### CHIEF — 首席合并（1 行）
- `method_comparison_consensus` → **KEEP_CONTEXT**。B 主 / C 次 / D 辅助推荐；
  B_act↔A_vol ρ=0.930 说明预测分与体量高度相关（与“预测≈体量+适度增量”一致）；
  共识 B∩C∩A K=100 n=28（随机期望 0.016）。推荐本身待 WALK 验证后生效。

### SELECT — 预算化选择（2 行）
- `budgeted_selection_framework` → **KEEP_CORE**。25 选择器 × 7 K 的冻结评估框架与
  09-01 结果：predictive_act K=10 U/K(fwd30_new_cp)=457（≈随机 7.2 的 64×），
  但 volume/degree/betweenness 同量级，不能宣称碾压；选择层效用 ≠ 端任务优越性。
- `ig_active_semantics` → **KEEP_CONTEXT**。y_active30 遮蔽 IG 选出“确信不活跃”钱包
  （top-10 未来效用 0）是未取绝对值 IG 的负例语义，非 bug，需文档化。

### BENCH — 标准基准评估（3 行）
- `exgraph_lp_heuristics` → **KEEP_CONTEXT**。官方 split 启发式 test AUC 0.634–0.775
  （PA 0.7754 最高），低于论文 GNN 自报；仅图级外部验证。
- `tgb_baselines` → **KEEP_CONTEXT**。EdgeBank 0.3590/0.5796、MLP test MRR 0.7841
  （官方 split/evaluator，leak-free streaming）；外部基准钩子（本地协议口径）。
- `exgraph_gnn_baselines` → **BLOCKED**。官方 11 模型 GNN 需 dgl/PyG 重依赖，环境未装，
  未执行；论文表 5 数字仅引用。

### COMM — 动态社区（1 行）
- `dynamic_communities` → **KEEP_CONTEXT**。per-cutoff as-of 图 + Hungarian 匹配；
  归属切换率 35.7→46.5%，ARI 0.525→0.431；09-01 与 Group C 完全一致；
  支撑 H3 社区扰动/regime 变化特征。

### FINAL — 最终排名与交接（1 行）
- `final_ranking_handoff` → **KEEP_CORE**。冻结 09-01 单次评估（B_act K=10 U/K=2,072.3、
  K=100=458.4、Recall@K(new_cp) K=1000=0.094）+ Phase-II 交接契约（数据契约、LLM 端点、
  外部基准钩子、排除范畴、8 项开放项）。

### WALK — 多 cutoff walk-forward（1 行）
- `multi_cutoff_walkforward` → **KEEP_CORE**。Phase-I 最强的统计证据：dev 06/07/08
  扩张窗口 + 配对 bootstrap（B=2000），K=100 predictive−volume +78.55 CI[49.98,114.22]、
  −activity +94.45 CI[55.19,153.94]；holdout 09-01 只评估一次（K=100 预注册）；
  预算价值 dev 省 29.6% / holdout 省 13.0%。边界：cutoff 级 bootstrap n=3、Recall@K
  “所有 K 显著”未证实（4/7 显著）、仅 2022 单年窗口。

### TGB2 — tgbl-coin-v2 榜单冲击（2 行）
- `tgb_mlp_v3b` → **KEEP_CONTEXT**。test MRR **0.8550**（val 0.8373），独立复跑逐位一致；
  特征严格 < t、官方 split/evaluator/负采样。**标注：本地官方协议评估，非官方提交回执**
  （官方提交接口/账号未配置）。对外只能称“本地官方协议评估 0.8550”，不能称“官方榜单击败”。
- `tgb_official_submission` → **BLOCKED**。官方提交回执需账号/凭据，当前环境不可得。

### LLM_PANEL — LLM 面板 / 节点选择器（9 行，含 June 终裁）
- `june_training_evidence` → **KEEP_CORE**（June 终裁，见 §4）
- `corrected_v2_qwen_panels` → **KEEP_CORE**（Jun/Jul/Aug/Sep 授权 Qwen 面板，4/4 月
  d_full_cheap 为正且 CI 不含 0）
- `node_selection_v2` → **KEEP_CORE**（修正 learned 选择器：Aug 50% 预算 0.4606 vs
  degree 0.4205，Δ+0.0401 CI[0.0209,0.0607]；4/5 预算胜；Sep 外检正）
- `nc_v1_support_restricted` → **KEEP_CONTEXT**（支持集受限 +0.0083 MRR；gate AUROC 0.557 弱）
- `router_v1` / `glm_v1_august` → **KEEP_CONTEXT**（历史/weak gate；代理成本非实测 token；
  v1 GLM 经中转站、现禁用）
- `glm_june_v2_floatfix` / `glm_june_v1` → **DROP**（隔离/仅诊断，见 §4）
- `nc_v1_learned_ranker_0896` → **DROP**（支持集伪影：82.2% 正样本在 top-2000 支持外且
  sentinel g_rank=99999；禁止报为全候选预测性能）

---

## 3. registry 概览（35 行）

| decision | 行数 | 结果 |
|---|---:|---|
| KEEP_CORE | 10 | G0_data_contract; G_A reusable_data_assets; G_B predictive_activity_level; G_B predictive_new_cp; SELECT budgeted_selection_framework; FINAL final_ranking_handoff; WALK multi_cutoff_walkforward; LLM_PANEL june_training_evidence; LLM_PANEL corrected_v2_qwen_panels; LLM_PANEL node_selection_v2 |
| KEEP_ABLATION | 2 | G_A persona_clustering; G_C structural_importance |
| KEEP_CONTEXT | 17 | G_A sequence_embedding_pilot; G_B extended_feature_ablation; G_C static_vs_asof; G_C structure_vs_influence_orthogonality; G_D wallet_masking_ig; G_D ig_topK_masking; G_E qwen_representation_pilot; G_F benchmark_registry; CHIEF method_comparison_consensus; SELECT ig_active_semantics; BENCH exgraph_lp_heuristics; BENCH tgb_baselines; COMM dynamic_communities; TGB2 tgb_mlp_v3b; LLM_PANEL nc_v1_support_restricted; LLM_PANEL router_v1; LLM_PANEL glm_v1_august |
| REPRODUCE | 1 | G_D residual_analysis（低量高影响组需 walk-forward/全量复核） |
| DROP | 3 | LLM_PANEL glm_june_v2_floatfix; LLM_PANEL glm_june_v1（作为训练证据）; LLM_PANEL nc_v1_learned_ranker_0896 |
| BLOCKED | 2 | BENCH exgraph_gnn_baselines; TGB2 tgb_official_submission |

---

## 4. June 解析异常终裁（方案 §4“diagnose and, if necessary, rerun”）

### 4.1 背景与既有审计证据

- `notes/june-parse-audit.md`（2026-09-10，`june_parse_audit.json` v1.1）已完整诊断：
  GLM v2 float-fix June 的 full/no-CF parse 仅 32.2%/33.9%，636 行 zero total tokens、
  678 行 calls<4、median latency 45.1s（正常月 12–20s）；`truth_in_pool=1` 全覆盖
  ⇒ 失败签名是 June 特定运行期/服务故障，**不是候选支持问题**；且 raw 响应/逐调用错误
  未持久化，无法回溯精确 invalid-JSON/缺字段/超时计数。
- GLM June v1：99.9%/100% parse 但为 v1 面板且不可替代 v2；仅诊断。
- 方案 §1 冻结项要求“June–September corrected v2 evaluation”，并须先诊断/重跑 June 才可用
  作 router 训练证据。

### 4.2 终裁结论（Decision）

> **无需再次重跑 June。** June 训练证据采用 **授权 Qwen3.5-4B 重跑**
> `artifacts/llm_panel_v2/runs/jun_gonogo_local_vllm4b_rerun_20260910.csv`，
> 状态 **`eligible_with_audited_stage3_candidate_fallback`**，正式冻结为 Phase-II
> router/reasoning-gain 训练输入。

依据（逐项核验 june_parse_audit.json + rerun manifest + node_selection_v2 manifest）：

1. **结构合格**：1,000/1,000 full 与 no-CF parse；4 calls/event；zero-total-token=0；
   RR 列数值型；候选支持 1,000/1,000；event key 唯一；响应模型=请求模型（Qwen3.5-4B）；
   client/transport error=0。
2. **唯一异常已文档化**：2/1,000 事件在 step-3 fusion 返回 unknown candidate ID，
   系统保留有效 mask-stage/final rank，属确定性、可审计的 **stage-3 候选 fallback**；
   June/July/August 各 2 条（共 6 条）已在 node-selection manifest 中显式保留，未静默删除。
3. **已冻结使用**：node_selection_v2_final_audited_20260910 的 learned 选择器即基于该
   rerun CSV 训练（splits: train 06-01 / val 07-01 / refit 06+07 / frozen test 08-01 /
   extra test 09-01）；Aug 50% 预算 Δ+0.0401（CI 不含 0）。重跑不会改变已冻结证据。
4. **成本-收益**：重跑 1,000 事件 × 4 calls（median ~8,975 tokens/event、~11.8s/event）
   约 900 万 token 与 ~3.3h 串行墙钟（可并行），仅对 2 条 fallback 事件重跑则约 8 calls
   / ~1.8 万 token / ~30s。为不改变结论的证据重复支付不必要。

### 4.3 各版本 June 证据的处置

| 版本 | 状态 | 处置 |
|---|---|---|
| **授权 Qwen3.5-4B 重跑** | eligible_with_audited_stage3_candidate_fallback | **训练证据（冻结）** |
| GLM v2 float-fix（32.2%/33.9%） | not_eligible_parse_anomaly | **隔离，不可用作训练证据**（仅诊断） |
| GLM v2 pre-float-fix（boolean-like RR） | not_eligible_buggy_numeric_schema | **不可用**（schema bug） |
| GLM v1 | diagnostic_only_until_protocol_review | **仅诊断**，不得静默替代 v2 |

### 4.4 若未来需要“严格无 fallback”标签（条件性预案，不执行）

若论文级声明要求“1000/1000 完全 clean”标签，有界行动（不执行，仅记录）：
- 仅重跑/复核 6 条 step-3 fallback 事件（June 2 条 + July 2 条 + August 2 条），
  使用本地 Qwen `http://127.0.0.1:31518/v1`、t=0、max_tokens=700、不发 reasoning_effort；
- 规模：6 events × 4 calls ≈ 24 calls ≈ ~5.4 万 token（按 median ~8.9k/event），
  墙钟 ≈ 1–2 分钟（串行）或 <1 分钟（并行）；
- 边界：不触碰 GLM 历史文件，不写 raw 响应，结果只追加审计字段；
- 判定标准：若 6 条重跑后 step-3 仍 unknown，则维持 fallback 标签并如实写入 manifest；
  不把 fallback 包装成 clean。

---

## 5. Phase-II 冻结清单（KEEP_CORE，10 项）

| # | 冻结项 | data | split | metric | baseline | leakage | statistics |
|---|---|---|---|---|---|---|---|
| 1 | G0 数据契约 + temporal_protocol.yaml v1.0 | ✅ | ✅ | ✅ | ✅ | ✅ PASS | n/a |
| 2 | Group A 可复用数据资产（特征矩阵/月度/USD/静态先验） | ✅ | ✅ | ✅ | ✅ | ✅ PASS | parity 0-diff |
| 3 | Group B predictive_activity_level（B_act） | ✅ | ✅ 严格时序 OOS | ✅ R²/Spearman/Recall@K | ✅ | ✅ PASS | ✅ WALK CI |
| 4 | Group B predictive_new_cp（B_new） | ✅ | ✅ 同上 | ✅ | ✅ | ✅ PASS | ✅ WALK CI |
| 5 | SELECT 预算化选择框架 + 09-01 冻结结果 | ✅ | ✅ 单点冻结 | ✅ U(K)/U(K)/K/Recall@K | ✅ 全层级 | ✅ PASS | ⚠️ 单点（CI 由 WALK 提供） |
| 6 | FINAL 最终排名 + Phase-II 交接契约 | ✅ | ✅ 单次冻结评估 | ✅ | ✅ | ✅ PASS | ⚠️ 单点 |
| 7 | WALK 多 cutoff walk-forward | ✅ | ✅ 06/07/08+holdout09 | ✅ U(K)/Recall@K | ✅ | ✅ PASS | ✅ 配对 bootstrap CI |
| 8 | June 训练证据（Qwen rerun，2 fallback 文档化） | ✅ | ✅ 06-01 | ✅ MRR/gain | ✅ cheap | ✅ PASS | ✅ paired CI |
| 9 | corrected v2 Qwen 面板（Jun/Jul/Aug/Sep） | ✅ | ✅ 4 快照 | ✅ full−cheap | ✅ cheap | ✅ PASS | ✅ paired CI（4/4 正） |
| 10 | node_selection_v2 事件级 learned 选择器（冻结 pkl/输入/结果） | ✅ | ✅ train06/val07/test08/ext09 | ✅ weighted MRR | ✅ 11 基线 | ✅ PASS（feature boundary） | ✅ bootstrap CI（B=5000） |

> 注：#5/#6 的“⚠️ 单点”不阻断冻结：其统计显著性由 #7（WALK）与 #9/#10（面板 paired CI）补足；
> Phase-II 不得把 #5/#6 的单点数字当作跨 cutoff 显著结论。

## 6. REPRODUCE / DROP / BLOCKED

- **REPRODUCE（1）**：`G_D residual_analysis` —— 低量高影响钱包（n=15）是 §9/§11 关键假说
  基础，须在 walk-forward（多 cutoff、全量或更大样本、CI）复核后才可作为 Phase-II 输入。
- **DROP（3）**：GLM June v2 float-fix（parse 异常，隔离）；GLM June v1（仅诊断，不可替代）；
  nc_v1 learned ranker MRR 0.896（支持集伪影，禁止对外报告）。
- **BLOCKED（2）**：EX-Graph 官方 11 模型 GNN 基线（缺 dgl/PyG）；TGB 官方榜单提交回执
  （无账号/凭据；0.8550 只能标“本地官方协议评估”）。

## 7. 统计支持分级（CI / 多 cutoff / n）

| 级别 | 结果 | 证据 |
|---|---|---|
| **A（CI + 多 cutoff + 大 n）** | WALK predictive vs volume/activity（U(K)）；node_selection_v2 50% 预算 learned vs degree | 配对 bootstrap（B=2000/5000）、3–4 cutoff、n≥18,519/4,000 |
| **B（CI + 单点/单模型）** | Qwen 面板 full−cheap（4/4 月）；Group B 单点 OOS；SELECT 09-01 | paired CI（1000 events）；holdout n=18,519 |
| **C（描述性/无 CI）** | G_A persona、G_C 结构、G_D IG、G_E Qwen、COMM、CHIEF、BENCH、TGB2 | 单 cutoff / 小 n / 引用 |
| **D（无效/隔离）** | GLM June v2 float-fix、nc_v1 0.896、GLM June v1（作为训练证据） | 支持伪影/parse 异常/不可替代 |

## 8. 风险项与 claim 边界（Phase-II 必须遵守）

1. **TGB2 0.8550 口径**：`本地官方协议评估，非官方提交回执`。对外只能与活榜单数字
   同协议对比，不能称“官方榜单击败”；正式提交（BLOCKED）后才能升级表述。
2. **跨模型 full−nocf 差异**：GLM v2 corrected 的 full−nocf 为正（+0.044~+0.181），
   而 Qwen 面板 full−nocf 各月≈0/负（−0.004~−0.045）。因此“MASK+FUSION 超过单射 LLM”
   是模型相关结论；Phase-II 主对象 RV=U_FullCF−U_Cheap（对 cheap）在 Qwen 下 4/4 月为正，
   但不得把“full>nocf”当跨模型事实。跨模型稳健性步骤（phase2 README 步骤 10）须显式检验。
3. **June 隔离**：GLM June v2 float-fix 文件保持 quarantine；不训练、不静默替代；
   2 条 step-3 fallback 作为 manifest 中的已知异常携带。
4. **nc_v1 支持伪影**：任何 next-counterparty MRR 必须报告支持集受限与 broad/full-candidate
   双口径（sentinel g_rank=99999 纪律），禁止把 sampled-pool 0.896 当全候选性能。
5. **预测影响 ≠ 因果/市场影响**：B/C/D 与 Phase-II 的“reasoning gain”均为增量预测效用，
   不构成因果声明（方案 §6 RV 定义）。
6. **支持集边界**：结构 7,929 / IG 2,999 / USD 16,910 均为受限支持集，报告必须分开
   （协议 reporting_rules），不做支持外推。
7. **成本轴**：router_v1 的 32/96 单位是代理成本，不是实测 LLM token；Phase-II 一律用
   实测 tokens/latency（Qwen 面板已有）。
8. **LLM 端点纪律**：本窗口禁止中转站 an unauthorized relay endpoint；仅本地 Qwen chat
   `127.0.0.1:31518` 与 embedding `127.0.0.1:31522`；不发 reasoning_effort。
9. **统计措辞**：WALK “所有 K 显著”未证实（U 6/7、Recall 4/7）；对外只写“方向稳健、
   headline K=100 显著”。

---

*审计结束。所有结论基于只读文件证据；未调用 LLM，未使用中转站，未修改 artifacts/ 与其他组文件。*
