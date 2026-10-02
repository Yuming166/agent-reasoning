# 工作日记：链上重要钱包筛选与预算化路由（2026-09-08 ~ 2026-09-09）

项目目录：本地 EX-Graph 研究工作区
云端：`ictdata-507912.exgraph`（BigQuery，US）；GCS bucket `ictdata-exgraph-artifacts`。
分支：`codex/wallet-selection-router`（独立分支，不改动 main）。

## 2026-09-08（晚）

1. X 社交数据审计复核：实测确认 `twitter_matching.csv` 只有 eth node_id+地址
   （8,820 个 id 超出 X 图 1,103,509 节点）；matching 图的 212 万跨边全为双向
   候选池，正负样本不可分离；X 侧 16 维特征后 8 维在 112 万节点上唯一值=1。
   结论：已发布小文件不含 eth<->x crosswalk。
2. X 关注图独立结构统计：1,103,509 节点/3,768,281 有向边，互关 102,088，
   2 个弱连通分量；产物 `artifacts/x_graph_standalone_stats.json`，
   每节点度数 npz（不入仓库）。
3. 确认 34.8 GiB `ethereum_with_twitter_features.pkl` 含 8 维 eth + 16 维 X
   聚合特征（代码 GCN(8) vs GCN(24) 实锤），但无 X node id；制定
   GCP 内网下载-抽取-落表-销毁 VM 的零跳板机流量方案与脚本
   (`src/cloud/extract_exgraph_xfeatures_gcp.py`)，起草给作者的索要邮件
   (`notes/author-request-draft.md`)。

## 2026-09-08（深夜）~ 2026-09-09：创新筛选支柱实现

- **P3 难度加权后果**：月度 as-of 特征表 `wallet_asof_features_v1`
  （5–8 月 4 快照，事件量/对手方熵/新对手方率/互惠率/HHI 等 + fwd30 标签，
  严格过去 90 天特征、未来 30 天标签）；排名表
  `wallet_importance_ranking_v1`。8 月 1% 预算覆盖 22.7% 难事件，
  优于按交易量 14.6% 与随机 1.3%。
- **P2 时序触发代理**：6 月窗口小时级 lag-1 活动相关，`wallet_trigger_proxy_v1`
  （2,038/14,189 钱包有有效分，均值 .051）；小时网格对低活跃钱包过稀疏，v2 改天级。
- **P1 反事实遮挡（信息桥）**：`p1_bridge_events_v1`（516k 桥，24.0% 的 8 月
  转出事件存在二跳解释路径）、`p1_wallet_icf_v1`。1% 预算覆盖 47.9% 桥接信息事件；
  P1 与 P3 top-1% 集合仅重合 14/144，两个重要性轴互补。
- **P4 学习型 router v1**：6 月训练、7 月调参、8 月冻结（HistGBM），
  `router_dataset_v1`（59,137 行 × 28 as-of 特征）。冻结 8 月：10% 预算捕获
  55.1% 未来 headroom（交易量 53.7%），选择效率达 oracle 的 .823，
  Spearman=.746；最强 as-of 特征为近 30 天新对手方数。单标量目标下 P1/P2
  增益小 → v2 需多目标/预算条件混合路由。

## 2026-09-09：候选评分模型 v1（next-counterparty 闭环）

- 表：`nc_events_v1`（事件级 repeat/new 标注）、`nc_edges_hist_v1`（1.16M 边）、
  `nc_global_pop_v1`、`nc_bridge_cand_v1`（64.6M 二跳非邻居候选）、
  `nc_bridge_hits_v1`、`nc_bridge_poolsize_v1`。
- 8 月 457,128 转出事件：重复 62.4%/新 37.6%。
- 结果（artifacts/nc_v1/RESULTS.md）：历史已知重复对手方上个性化时间衰减
  MRR .374 / R@10 .734；新对手方全局非邻居热度 MRR 仅 .024；二跳桥只覆盖
  5.9% 真相、固定拼接反而有害，但子池上 oracle 二选一比单纯全局 +25% MRR
  → 学习型候选排序器/逐事件评分门控是下一步。组合基线全事件 MRR .185。
- 过程中修正两个方法论问题：(i) target_sequence_index 按钱包编号，二跳排名
  必须按 (u,seq) 分区；(ii) 窗口函数与真值过滤不能放同一 CTE。

## 边界（不夸大）

- P1 v1 是图路径遮挡代理，非"训模型后真实 mask 重打分"（v2）。
- P4 v1 目标是流行度 headroom 代理，不是真实 LLM ΔMRR/token。
- 全部结论未使用 X 特征；等待 GCP 抽取后做 P6 社交消融。
- router 生产口径只能用 5/6 月训练、8 月冻结；展示性同周期排名已标注 oracle 属性。

## 2026-09-09（凌晨）：后台 tmux 完成候选排序器、事件门控与预算曲线

- 按“关掉电脑也继续跑”的要求，在服务器 tmux `exgraph_nc` 中执行
  `run_nc_background.sh`；任务已结束。Stage B 从 BigQuery
  `exgraph.nc_ranker_samples_v2` 经 GCS 导出 30 个 gzip 分片到服务器持久目录
  `artifacts/ranker_samples/`（966,215,170 字节；表 28,472,717 行），没有把
  大文件放入 Git。
- Stage B：HistGBM 候选排序器使用 6 月训练、7 月调参、6+7 月冻结到 8 月；
  特征为全局热度 rank/count、90 天个人交互次数/间隔、二跳路径数和 bridge
  权重。naive 50-candidate sampled-pool MRR 为 .896，但审计发现这是
  candidate-support 伪强：负样本只来自历史 top-2000，而 82.2% 的真值在
  top-2000 之外并带 `g_rank=99999`，模型只需识别越界正例。该结果仅保留为
  诊断，不作为论文主结果。
- 立即补做支持集受限审计：仅保留真值在历史 top-2000 内的 8 月事件
  30,610/171,700（17.8%）。在可比的约 50 行 sampled pool 中，global popularity
  MRR .448，learned ranker .456（+0.0083 绝对，+1.85% 相对），oracle
  best-of-two .505；这说明真实增益存在但很小，远未“解决”新对手方排序。
- Stage C：事件门控用 7 月 June-only ranker 的 out-of-sample 胜负训练，8 月
  使用 June+July frozen ranker，事件上下文只由负候选聚合，避免正例特征泄漏；
  没有把静态全期 EX-Graph 结构特征混入月度 as-of gate。8 月 AUROC .557、
  AUPRC .278（learned-winner base rate 23.0%）。10% deliberation 预算只取得
  +.0029 MRR，而 oracle 为 +.0528；当前事件前上下文不足以捕获 per-event
  headroom。
- 预算轴目前是固定 token-unit proxy（cheap=32、deliberation=96），不是实测
  LLM token/latency；已在 README、`artifacts/nc_v1/RESULTS.md` 和结果 JSON
  中明确标注。
- 后台产物：`artifacts/nc_v1/learned_ranker_v1.json`、`gate_budget_v1.json`、
  `supported_pool_v1.json`、两条曲线 CSV/PNG；代码
  `src/pipeline/{build_rankertables,train_candidate_ranker,gate_and_budget,evaluate_supported_pool}.py`。
- 下一步：扩展 top-2000 之外的 bridge/tail/stratified negatives，做全候选或
  分桶 recall；给 gate 增加严格 as-of 钱包/合约/token 特征；等 X 特征抽取后
  做社交消融；最后接真实 LLM 调用测 token/latency。

## 2026-09-09（昼）：真实 LLM go/no-go 第 1 步——分层配对面板构建

- 目标：在看任何 LLM 结果前，冻结“预算化反事实路由是否有效”的检验样本；3,000 个
  事件配 cheap/deliberation 同候选、同 as-of 上下文的配对设计。
- 新脚本 `src/pipeline/build_llm_panel.py`（--build/--verify/--export），在 BQ
  物化两张分区表：
  - `exgraph.llm_panel_events_v1`：6/7/8 月各 1,000 个 primary outgoing、有对手方、
    非 self 事件；8 个 cell（new_popular/new_tail × repeat_easy/repeat_hard ×
    activity high/low），每 cell 固定 125 + 确定性 FARM_FINGERPRINT topup，
    `pop_weight` 可加权重回总体；6 月训增益模型、7 月冻结 prompt/调参、8 月只测。
  - `exgraph.llm_panel_candidates_v1`：每事件 1 正例 + 最多 49 个仅来自快照前历史
    的负例（new: 2-hop bridge/top-2000/tail 各 16；repeat: 个人历史 30 + top/tail
    补齐），pool 中位 38（20–50），共 118,901 行。
- 关键防泄漏：(i) 负例与候选特征全部严格 pre-snapshot；(ii) new_tail 事件配 16 个
  真实 rank>2000 tail 负例，消除 nc_ranker_samples_v2 中 `g_rank=99999` 哨兵可识别
  正例的支持集伪强；(iii) `truth_g_rank` 标记为 analysis-only，禁止入特征/prompt。
- 验证：每快照事件唯一且 1,000；每事件恰 1 正例且等于事件对手方；8 个 cell 各 125；
  new_tail 事件均含 tail 负例。CTAS 计费各约 1.15–1.20 GB；本地导出仅 ~220KB+3.4MB
  gzip，存于 `artifacts/llm_panel_v1/`（events/candidates/manifest/PANEL_DESIGN.md），
  GCS 前缀 `gs://ictdata-exgraph-artifacts/llm_panel_v1/`。
- 修复两个实现 bug：seg_new_bridge 漏 `WHERE rn<=16` 导致 bridge 全量进入（pool
  曾达 ~700–1000）；LIMIT 不接受表达式，改为 ROW_NUMBER topup。
- 下一步（第 2 步）：最小 agent runner（OBSERVE_HISTORY / RUN_COUNTERFACTUAL_MASK /
  STOP_AND_PREDICT）对同一候选池跑 cheap vs deliberation 两臂，实测 token/latency/
  失败率/逐事件 ΔRR；先 7 月冻结 prompt，再跑 8 月，配对 bootstrap CI。

## 2026-09-09（午后）：真实 LLM go/no-go 第 2 步——反事实算子 FSM 三臂实验

- 端点：代理 OpenAI 兼容 `glm-5.3`，`reasoning_effort=low`（默认思考会耗尽 token），
  temperature 0、JSON 模式；真实记录 prompt/completion/total tokens 与延迟，不再用 proxy。
- cheap 臂：仅 6 月面板训练并冻结的 HistGBM（8 个合法 pre-snapshot 数值特征）；
  修复两个泄漏/评估 bug：(i) cand_source one-hot 等于标签（正例 source 唯一）导致 MRR=1；
  (ii) 排名在仅正例子集上计算导致恒为 rank 1。修正后 8 月 cheap MRR .485。
- 原创算子（`src/agent/serialize.py`）：full = OBSERVE_HISTORY → 独立
  RUN_COUNTERFACTUAL_MASK（屏蔽钱包自身历史，独立重排，不看第一步答案）→ UPDATE_BELIEF
  三方融合（observe/mask/cheap）→ STOP_AND_PREDICT；每步输出算子名、证据 cid、
  belief_shift、mask_sensitive。消融 nocf = 同模型同上下文一次性排序（无 mask）。
- 规模：tmux `exgraph_llm` 后台跑 7 月 960 + 8 月 1000 配对事件，16 并发；8 月中位
  full 7,152 tokens / 18.3s、nocf 2,152 tokens，解析率 100%。脚本
  `src/agent/{data,llm_client,serialize,run_agent,evaluate_runs,budget_curve}.py`，
  产物 `artifacts/llm_panel_v1/{runs,RESULTS_LLM_v1.md,AGENT_PROTOCOL_V1.md,
  aug_paired_deltas.json,budget_summary.json,aug_budget_curve.png}`。
- 冻结 8 月主结果（配对 bootstrap CI）：full−cheap +.052 [+.016,+.088]；
  full−nocf +.131 [+.114,+.148]（增量来自反事实算子而非“用了 LLM”）；一次性 nocf 反而
  −.079。分层：repeat +.150（CI>0）、new_tail −.269（CI<0，应保持 cheap）；mask 敏感时
  平均增益 +.160，不敏感 −.026。预算路由：50% 预算只路由 repeat → MRR .635，优于
  all-cheap .485 与 all-full .550；oracle 上界 .766。7 月同模式复现（full−nocf +.133）。
- 边界：仅 2022-08 一个冻结测试月；new-tail 无优势；尚无 6 月增益路由器、9 月外推、
  强非 LLM 基线/Markov、递归深度与邻居算子消融。下一步见 RESULTS_LLM_v1.md。

## 2026-09-09（傍晚）：第 3 步——6 月训练的学习型预算路由器（冻结 8 月评估）

- 补跑 6 月面板真实 LLM（tmux `exgraph_jun`，1,000 事件，full−cheap +.003、full−nocf +.101
  [.065,.105]，解析率 .999），三个月配对面板齐备：`runs/{jun,jul,aug}_gonogo_glm53_v1.csv`。
- `build_router_dataset.py`：每事件 16 个**调用前**特征（cp_type、90 天钱包统计、候选池大小、
  cheap 顶分/边际/分数熵、candidate-source 占比等）；显式审计排除 truth_g_rank、真实排名、
  mask_sensitive（后者是 FSM 内部信号，不能做外部预路由器特征）。
- `train_budget_router.py`：HistGBM 仅用 6 月实测 gain_full 训练，7 月只选超参（depth3/50 树），
  8 月冻结评估。
- 冻结 8 月预算曲线（加权 MRR）：b=.05 .536、.10 .594、.20 .676、.50 **.716**、.75 .733；
  对照 all-cheap .485、all-full .550、oracle .766、随机 .516、手工 repeat .635、通用
  uncertainty 路由 .661（b=.5）。b=.50 配对 CI：对随机 +.228 [.192,.264]、对 repeat +.081
  [.057,.104]、对 all-cheap +.231、对 all-full +.166，全部显著为正。
- 校准：路由分数十分位对实际增益单调（底位 −.76/胜率 0% → 顶位 +.66/胜率 97%），可区分
  “有害/有益”的 deliberation；7 月冻结模型同曲线（b=.5 .769），跨月迁移。b=.5 时约
  3,576 measured tokens/event vs all-full 7,152，达到 oracle 路由 MRR 的 93%。
- 产物：`artifacts/llm_panel_v1/router_dataset_v1.csv`、`router_v1/{budget_router_jun_frozen.pkl,
  budget_router_aug_eval.json,router_vs_uncertainty.json,aug_router_scores.csv,
  aug_router_budget_curve.png,RESULTS_ROUTER_v1.md}`。
- 边界：仅 8 月一个冻结测试月；增益标签来自单一 LLM glm-5.3；尚需 9 月外推、跨模型标签稳定性
  （本地 Qwen）、强非 LLM 基线（时序图嵌入/Markov）、邻居算子与递归深度消融。

## 2026-09-09（晚）：corrected v2 LLM panel 完成

- 修复 tie-aware reciprocal-rank 实现后，`glm-5.3` corrected v2 运行完成：June、July、August、September 各 1,000 个事件；Full FSM、NoCF 和 frozen cheap 三个臂均有逐事件输出。运行脚本为 `run_llm_v2_floatfix.sh`，原始本地运行日志不入 Git。
- 失败口径固定为生产回退：Full/NoCF 解析失败的事件保留，并使用 cheap reciprocal rank；没有静默删除失败样本。`artifacts/llm_panel_v2/operational_eval_floatfix.jsonl` 记录回退后的 weighted MRR 和 paired bootstrap 区间，`corrected_v2_manifest.json` 记录文件哈希、行数和解析率。
- corrected v2 的回退后 Full MRR（June/July/August/September）为 `.5088/.5029/.5605/.5499`，Cheap 为 `.3281/.2831/.2795/.3003`；Full-Cheap delta 均为正。Full-NoCF delta 也均为正，收益主要集中在 `repeat_hard`，`new_tail` 的收益较小。
- July/August/September 解析率为高/完整；June 解析率异常低（Full `.322`、NoCF `.339`），需要在 router 训练前诊断或重跑。该异常结果只作为明确 fallback 的审计证据，不应伪装成干净的 LLM 成功率。
- 旧的 `artifacts/llm_panel_v2/router_dataset_v2.csv` 是 float-RR 修复前生成的，不能使用；下一步必须从 corrected 输出重新构建 router dataset。

## 研究主线升级

研究主线从“是否调用 LLM 的事件门控”升级为“影响力感知的选择性可信递归推理”：

1. 先用严格 as-of 历史估计钱包/钱包群体的动态未来 spillover relevance，而不是把静态 PageRank 当作真实市场影响；
2. 为每个 wallet-event 分配 low/medium/high reasoning depth，在固定 token/latency 预算下选择性递归；
3. 每一步递归输出证据事件、反事实干预、belief update、置信度、约束检查和 stop/continue，而不是无限制的自由文本递归；
4. 从下一 counterparty/action 的微观预测，扩展到钱包群体的 K-step 策略，再聚合为协议流量、网络结构和其他 market-relevant 状态。

详细定义、可证伪假说、消融和执行路线见 `notes/RESEARCH_MAINLINE.md`。当前 corrected v2 只验证了 one-step counterfactual component；dynamic influence、adaptive depth、shared-state K-step rollout 和 macro aggregation 尚未完成。

## 2026-09-10（晚）：June v2 parse anomaly 的授权 Qwen 重跑与审计

- 运行前验证授权服务 `http://10.63.0.82:31518/v1` 的 `/models` 返回精确模型 `Qwen3.5-4B`，未使用禁止的 `10.63.0.72:8317`，也未保存 raw response。
- 发现该 Qwen/vLLM 部署若发送 `reasoning_effort=low`，会在冻结 `max_tokens=700` 内产生隐藏思考并可能不给 JSON；客户端现在对 Qwen 默认省略该可选字段，仍允许通过 `LLM_REASONING_EFFORT` 显式覆盖。prompt、candidate pool、snapshot、temperature=0、max_tokens=700 和事件选择不变。
- June-only v2 重跑完成：`1,000/1,000` 事件、每事件 4 calls；full/no-CF parse 均 `1.000`，candidate support `1,000/1,000`，重复 event key `0`，zero total tokens `0`，response model 全为 `Qwen3.5-4B`，median latency `11.782s`，full total-token median `8,975`、no-CF median `2,784`。
- per-step 审计显示 step1/2/4 全部 `ok`；step3 有 `998 ok + 2 unknown_or_invalid_candidate_id`，两条均保留有效 final rank 且等于 mask-stage rank。因而该重跑不是“完全 clean”，但可在显式记录这一小段 fallback 的前提下作为 corrected June training evidence；历史 v2 float-fix 的 `32.2%/33.9%` parse 文件仍隔离，不可拿来训练。
- 结果文件：`artifacts/llm_panel_v2/runs/jun_gonogo_local_vllm4b_rerun_20260910.csv`、对应 `*_eval.jsonl` 与 `*_manifest.json`；审计更新于 `artifacts/llm_panel_v2/june_parse_audit.json`、`notes/june-parse-audit.md`、`logs/audit_june_parse_anomaly_20260910.log`。
- 边界：该 Qwen 重跑是跨模型/运行配置的校正证据，不应被表述为 GLM 历史结果的直接复现或性能优越性；若主线要求零 fallback 的 clean label，需要单独复核那 2 个 event key 后再冻结 router dataset。
