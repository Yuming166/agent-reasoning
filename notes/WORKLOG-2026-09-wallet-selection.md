
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

## 2026-09-10（晚）：June v2 parse anomaly 的授权 Qwen 重跑与审计

- 运行前验证授权服务 `http://10.63.0.82:31518/v1` 的 `/models` 返回精确模型 `Qwen3.5-4B`，未使用禁止的 `10.63.0.72:8317`，也未保存 raw response。
- 发现该 Qwen/vLLM 部署若发送 `reasoning_effort=low`，会在冻结 `max_tokens=700` 内产生隐藏思考并可能不给 JSON；客户端现在对 Qwen 默认省略该可选字段，仍允许通过 `LLM_REASONING_EFFORT` 显式覆盖。prompt、candidate pool、snapshot、temperature=0、max_tokens=700 和事件选择不变。
- June-only v2 重跑完成：`1,000/1,000` 事件、每事件 4 calls；full/no-CF parse 均 `1.000`，candidate support `1,000/1,000`，重复 event key `0`，zero total tokens `0`，response model 全为 `Qwen3.5-4B`，median latency `11.782s`，full total-token median `8,975`、no-CF median `2,784`。
- per-step 审计显示 step1/2/4 全部 `ok`；step3 有 `998 ok + 2 unknown_or_invalid_candidate_id`，两条均保留有效 final rank 且等于 mask-stage rank。因而该重跑不是“完全 clean”，但可在显式记录这一小段 fallback 的前提下作为 corrected June training evidence；历史 v2 float-fix 的 `32.2%/33.9%` parse 文件仍隔离，不可拿来训练。
- 结果文件：`artifacts/llm_panel_v2/runs/jun_gonogo_local_vllm4b_rerun_20260910.csv`、对应 `*_eval.jsonl` 与 `*_manifest.json`；审计更新于 `artifacts/llm_panel_v2/june_parse_audit.json`、`notes/june-parse-audit.md`、`logs/audit_june_parse_anomaly_20260910.log`。
- 边界：该 Qwen 重跑是跨模型/运行配置的校正证据，不应被表述为 GLM 历史结果的直接复现或性能优越性；若主线要求零 fallback 的 clean label，需要单独复核那 2 个 event key 后再冻结 router dataset。
