# 方案 B 预注册协议：扩展 dev（150 新案例）+ 统一选择器 v2

冻结时间：2026-10-02（用户外出，后台执行）。**本文件在任何新 dev 指标计算之前落盘。**
后续所有脚本必须引用本协议；偏离需要在新文件中显式声明为偏差。

## 0. 动机

52 个 active dev 案例上，主方法 chain_all 未超过最强基线（R@50: 0.609 vs legacy_motif 0.647），
配对差 CI 宽（±0.10+）。统一选择器（k=5 证据席位）首次净正（R@50 0.609→0.628，零挤出），
但只有 1 个 saved 案例，证据不足。方案 B：新增 150 个 dev 案例（训练集不变），
把配对差 CI 收窄到能支撑或证伪"净覆盖增量"主张的水平，并预注册选择器 v2
（修正 v1 的 recency-压倒-笔数弱点）。

## 1. 训练集隔离声明（核心决策）

- 原 2300 案例：2150 train 分布在 2022-04-01..2022-06-15 七个 cutoff shard；150 dev 在
  2022-06-01/2022-07-01（52 active 在 07-01）。
- **新 150 案例全部 split='dev'，不进任何训练/归一化拟合。**
- 训练集字节级不变 ⇒ 冻结模型（`artifacts/cert_v2_featfix_20261002T000000Z/models/`）
  就是"重训后的模型"，直接在新 dev 上打分是合法评估，不构成泄漏。
- **重训 gate**（防管道漂移，非必要重训）：重训 chain_all seed0 于与原训练完全相同的
  2150 train 案例集，其在旧 52 active 上的 rank 必须与冻结 rank 完全一致（max_rank_diff=0）。
  通过 ⇒ 冻结打分管道无漂移。
- 归一化：复用冻结 `normalization.json`（训练集不变 ⇒ stats 不变，禁止重拟合）。
- 泄漏披露（非排除）：记录每个新 dev 钱包与旧 2150 train 钱包及其对手方宇宙的地址重叠率。
  EOA 生态互相交易是常态，原 2300 案例内部同样如此；排除会造成选择偏差。
  泄漏的唯一定义是"案例进入训练"——本协议保证不发生。

## 2. 抽样框与分层（先冻结，后抽样）

- 事件源：`artifacts/offline_chain_events_v1_20260929_full/`（6 个月全面板，本地，无 BigQuery 消费）。
- qualifying 口径（与全项目一致）：`event_family=='external_tx' & direction=='outgoing' &
  counterparty_address 非空 & != 0x0000...0000`，地址统一小写。
- 抽样框：2022-06（06-01..06-30 UTC）qualifying outgoing 笔数 ≥ 10 的行主体钱包。
  该口径下 6,900 个新候选（9,777 为全 family 宽口径；选严格口径避免 token 互动主导）。
- 排除：2300 案例全部钱包（含旧 dev 150、旧 train、旧 target 地址不排除——target 可以
  是任何人）。
- 分层：按 6 月笔数 4 桶：Q1 [10,20)，Q2 [20,50)，Q3 [50,150)，Q4 [150,∞)。
  配额 [37, 38, 38, 37] = 150。桶内按 sha1(wallet) 十六进制升序取前 N（确定性；
  sha1 排序在分桶控制活跃度后消除"笔数选择偏差"）。
- 无钱包被重复抽（唯一）。

## 3. 案例语义（与旧 2300 逐位一致；已对拍）

- cutoff = 2022-07-01（UTC），split = 'dev'，case_id = `devx_2022-07-01_<wallet>`。
- active：[07-01, 07-07) UTC 窗口内存在 ≥1 笔 qualifying outgoing external。
- target：窗口内**首笔**（block_number, transaction_index, event_index, transaction_hash
  排序）qualifying outgoing external 的 counterparty_address（attempted 口径，不筛
  receipt_status——52 个旧 active 案例对拍 52/52；success_only 仅 51/52）。
- 不活跃案例保留在 shard（active=0），不进指标分母。

## 4. 候选池（两层，声明用途）

- **主池 = 三源并集**（与旧 2300 完全同构）：
  `sorted(set(motif_pool) | set(graphmixer_pool) | set(typed_tgn_pool))`，
  三源分别由 `motif_gated_retriever.build_pool`、`graphmixer_train.case_pool`、
  `typed_tgn.make_pool` 在各自 as-of 索引上生成（POOL_OWN=500, POOL_GLOBAL=2000,
  POOL_RECENT=2000, POOL_DIFF=500）。禁止 target 注入。
- **实验池 = 主池 ∪ Layer-1 入边**（仅用于 §6 选择器 v2）：as-of 截止前给案例钱包转过账的
  地址（事件表 `target_address==w & direction=='incoming'` 行的 counterparty_address），
  排除 self 与空串。52 案例实验已验证该扩池对冻结分数零位移（saved=0, displaced=0）。
- 主指标（§5 表）全部基于主池；实验池结果单独成表，不与旧 2300 直接混排。

## 5. 特征、模型与指标

- 特征：B/C/E（History.proofs + features，proofs 全部 `certificate_v2.verify` 通过）、
  X（legacy pair_features 20 维）、gm（candidate_matrix 5 维）、seq（64×6 钱包级，
  复刻 graphmixer_train.build_wallet_sequences：FAM_VOCAB/ADDR_BUCKETS=32768/
  TOK_BUCKETS=4096/log1p×100 编码，仅 outgoing）、ctx（wallet_context 6 维）、
  cand_bucket（sha1 % 32768）。历史 = canonical_ledger（< cutoff），
  断言 `max(ts) < cutoff_ts` 且 epoch 秒级。
- 打分：冻结 22 变体 × seeds{0,1,2} + own_frequency（seed0，B[:,1]），全部变体、
  全部新 active 案例。rank≤0（不在池）计 0，分母 = 全部新 active。
- 主表指标：R@5 / R@50 / R@100 / MRR@5（ALL-active 分母），逐 seed + seed 平均。
- 配对 bootstrap（主推断）：wallet 为 cluster，2000 replicates，rng seed 20261002，
  seed 平均后逐案例配对。对比组：
  - 每变体 vs `direct_global_legacy`（最强免证基线）
  - 每变体 vs `chain_all`（当前主方法）
  - `chain_all` vs `legacy_motif`（最强基线，R@50 0.647）
  报告全部 CI（含跨零），不做选择性引用。
- 新 dev 150 案例的 active 数预期 ~130-150；ALL-active R@50 配对差 CI 预期 ±0.05-0.08
  （钱包 cluster 相关性可再收窄；±0.03 需 ~900 案例，如实报告不承诺）。
- 合并视角（secondary）：新 150（新 rank）+ 旧 52 active（原 run 冻结 rank，主池协议）
  合并报告，标注两段来源，不做跨段配对差。

## 6. 选择器 v2（预注册新方法；公式先验冻结，不在新 dev 调参）

v1 弱点（52 案例审计）：`strength = log1p(n_in)·exp(−days/30) − 0.5·hub` 中 recency
作为唯一乘性通道，使"2 笔 + 72 天旧"（0xeabb 案例，强度 0.0997）输给"1 笔 + 新近"。

v2 公式（方向对称，加性双通道，全部系数先验冻结）：

```
strength_v2 = 1.0 * log1p(n_in)  * exp(−days_in/30)      # 钱包 ← 候选 通道（笔数主导）
            + 0.5 * exp(−days_in/30)                     # 新近加成通道（封顶 0.5）
            + 1.0 * log1p(n_out_back) * exp(−days_out/30) # 钱包 → 候选 回路通道
            − 0.5 * hub(candidate)                        # 候选为 hub（全局出度 > 109，
                                                          #  52 案例冻结的 99 分位）时罚
```

- 资格：实验池中**由 L1 入边新增**的候选（不在三源并集），n_in ≥ 1。
- 证据三状态的操作化（诚实边界）：事件表为全面板行主体抽取，候选↔钱包子空间完全可观测
  ⇒ 状态 ∈ {observed-supported (n_in≥1), unobserved}；候选自身全局历史视为未完整观察
  （表不含一般地址完整历史，0.4% 覆盖，见 donor 审计 20261002）。refuted 状态留待
  合约语义工作，本协议不操作化。
- 席位机制（与 v1 相同）：k 个证据席位追加在名次 (51−k)..50 尾部，**绝不进入 top-5**；
  其余 50−k 席位按冻结 chain_all 分数。k=0 为基线复现。
- **主分析 k=5**（与 52 案例实验同一先验）；k∈{0,1,2,3} 报告为敏感性，不作主要证据。
- 成功判据（预注册）：新 150 active 上，v2@k=5 相对 chain_all@k=0 的 R@50 配对差
  CI 下界 > 0，且 R@5 配对差 ≥ −0.02。同时报告 saved/displaced 清单。
- 附带复算：52 旧 active 在 v2 公式下的 k 扫描（仅作机制对照，与 §5 合并视角区分）。

## 7. Gate 清单（全部必须通过，否则停止并报告）

1. 抽样确定性：重跑抽样脚本产出逐位一致的 150 钱包清单。
2. target 语义：新案例 labeler 在 52 旧 active 上复现 52/52（已预验证）。
3. 特征历史边界：`max(history ts) < 2022-07-01`，proofs 验证 invalid=0。
4. 主池规则：新案例主池 = 三源并集，无 target 注入断言（target ∈ pool 允许——它本就是
   as-of 可见性检查，不是注入）。
5. 重训 gate：chain_all seed0 重训后旧 52 rank 与冻结 rank max_diff = 0。
6. 选择器 gate：v2@k=0 必须逐位复现 chain_all 实验池 R@50。
7. 分母完整性：新 dev 每变体 rank 行数 = 新 active 案例数。

## 8. 产出

- `artifacts/expanded_dev_B_20261002/`：selection/、shards/、scores/、metrics/、
  selector_v2/、leakage_audit.json、REPORT.md
- `notes/expanded_dev_results_20261002.md`：结果 + 与 52 案例结论的合并解读

## 9. 执行日志（追加）

- 18:47 Step1 完成：frame_candidates=6144（排除后），Q1 2255/Q2 2368/Q3 1266/Q4 255，
  150 选出。泄漏审计：selected ∩ train wallets = 0/150；∩ train 对手方宇宙 = 51/150（披露不排除）。
- 18:43-18:52 Step2 首跑发现 label 用了仅到 6 月的事件表（active_new=0），修正为
  7-8 月独立加载后重跑：150 案例全部构建，129 active / 108 supported（83.7% 池支持率，
  高于旧 52 案例的 76.9%，因抽样框要求 6 月 ≥10 笔）。
- 18:52 编排器启动（会确定性重跑 step2 后接 step3-6）；step2 重跑产物应与首跑逐位一致。
- 19:12-19:24 Step3 完成：79,672 proofs 全部验证（invalid=0）；主池均值 4,145、
  实验池均值 4,248 候选/案例；supported_main=supported_l1=108。
- 19:13-19:15 Step4 完成：67 变体 × 129 active 打分 + 全对比组配对 bootstrap。
- 19:15-19:17 Step5 完成：v2@k=5 R@50 配对差 −0.0103，CI [−0.0258, 0.0]——
  预注册成功判据不成立。发现资格过滤 bug（把实验池当主池，qualified_mean=0）；
  修复版 step5b 数值逐位一致（saved 结构性为 0 所致），偏差已记录于结果文档 §4。
- 19:19 Step6 首跑 KeyError（漏 prepare）；修复后二跑 max_rank_diff=320
  （gate 脚本 RNG 顺序 bug：seed 设置须在 Scorer() 之前）；三跑 max_rank_diff=0
  PASS（19:33）。失败产物归档 retrain_gate/gate.rng-order-bug.json。
- 19:20-19:37 Step7 完成：51 案例 1,850 候选，v2 改动 959 排名；0xeabb 强度
  0.0997→0.2429 修正确认。
- 全部 gate（协议 §7）通过；结果文档 notes/expanded_dev_results_20261002.md 落盘。
