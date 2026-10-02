# NAACL 向 Tier2 / Tier3 方法设计（2026-09-11）

定位：不是“再算一个 PageRank/Hawkes 分数”，而是要回答一个任务内问题：

> 在一个 temporal 金融图上，当推理预算有限时，应该按什么标准把有限的
> 语言推理算子分给哪些钱包，且这个标准必须可审计、as-of 无泄漏，并对下游
> 预测/收益目标“真的有效”。

核心论文主张（一句话，novelty 候选）：
**把“影响力”定义为对邻域/市场后续活动的反事实扰动，并把该扰动与 LLM
推理增益联合成一个 budget-constrained 的 allocation 目标，而不是静态中心性。**

## Tier 2 方法：temporal counterfactual influence

### 2.1 I_cf：邻域反事实遮挡影响力（P1 的正式化 + v2 升级）
- 冻结一个便宜 temporal 排序器 f（我们已有 cheap ranker / 候选评分）。
- 对目标钱包 w，把所有以 w 为 target 的 event 行遮住（H_t \ H_w），
  重跑邻居/全部钱包的 next-counterparty 排序，测量：
  I_cf(w) = mean_{x≠w, x 的事件中有 w 参与的路线} [ RR(pred_x | H) - RR(pred_x | H \ H_w) ]
- 用 degree-biased mini-batch + 草图避免 21k 目标 × 11.8M 行的全枚举。
- 设计含义：I_cf 直接与 agent 的 RUN_COUNTERFACTUAL_MASK / REQUEST_NEIGHBOR_AGENT
  共享同一种语义（“这个节点对别的节点预测有多大贡献”），选择和推理同义。
- 与 v1 的区别：v1 是图路径遮挡代理；v2 用真实 cheap model 遮挡+重评分。

### 2.2 I_hawk：时间激发/领先影响力（P2 的正式化 + v2 升级）
- 对 directed pair (a->b)，在 as-of 窗口内估计 excitation α_ab：
  事件强度 lambda_b(t) = mu_b + Σ_{a, t_i<t} α_ab κ(t-t_i)
- I_hawk(a) = 由 a 触发的期望事件质量 / 有效分支因子；可做 time-varying。
- v2 要改成更密的聚合（更长窗口、事件质量按 USD/对手方类型加权），
  且对每个 snapshot 算成 as-of 序列，修掉 v1 只有单一 July 窗口的缺陷。

### 2.3 关键创新点（可辩护的 integration，不是单点指标）
把 I_cf、I_hawk、经济足迹（Tier1）作为**三个可分离、可消融的 allocation 轴**，
进入一个学到的 budget router，而不是把它们乘成一个标量：
- 多目标/预算条件 router：`u = ΔMRR / LLM-token` 作为主目标，
  I_cf / I_hawk / footprint 作为约束或前置 gating（例如只在 footprint 大的子集里
  还细分 I_cf 高者）。
- 每一轴单独出 budget-Pareto 曲线 + 消融（去掉任一轴，MRR/覆盖率如何变化）。

## Tier 3 方法：market-moving 的因果事件研究（单独、冻结协议）

这层不进入 allocation 的 as-of 特征（避免未来泄漏），是一个独立的
因果评估，用来回答“选出来的高影响力钱包是否真的领先市场”：

- treatment/exposure：钱包日度净流出（native + 5 个 priced token，明确口径）。
- outcome：ETH（以及未来可扩展到 5 个 token）h 期收益。
- 识别：面板 `flow_{i,t} -> ret_{t+h}`，控制市场因子/滞后、钱包固定效应；
  主力是 event study（大额异常流事件 vs 匹配控制），并报告多重检验校正
  与可交易滞后下的换手成本边界。
- 边界：这层若 CI 不为零 → 可说“观察到领先相关性/证据”，仍不等于
  “该钱包导致价格移动”；措辞用 temporal precedence，不用 causal 除非有
  更严格识别（如外生冲击/DID）。
- 先冻结协议（窗口、h、控制变量、显著性阈值）再评估，禁止事后挑窗。

## 评估协议（统一，naacl 必备）
- 一律 as-of，train Mar-Jun / tune Jul / frozen Aug；Sep 额外外检。
- 主指标：加权 MRR、Recall@K/NDCG 的 budget 曲线；ΔMRR/1000 tokens；
  选择性风险/覆盖率；router 校准与 gain 预测 R²。
- baseline：random、degree、static PageRank、volume、I_hawk 单轴、I_cf 单轴、
  learned router、oracle（明示上界）。
- 泄漏审计：每个特征 time-stamp <= 决策时点；truth rank / 未来标签不入特征。

## 当前落地进度（与本次对齐）
- Tier1 已建成冻结表 artifacts/influence_v1/wallet_influence_v1.csv。
- Tier2 现有 proxy：P1(v1) p1_wallet_icf_v2、P2(v1) wallet_trigger_proxy_v1；
  待做 v2（I_cf 遮挡重评分、I_hawk 多 snapshot）。
- Tier3 仅设计，未跑。
