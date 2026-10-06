# 方法–Benchmark 对齐表(G1.3 草稿,等作者确认)

日期:2026-10-06。本文是投稿前必须逐行确认的合同:**论文中每个方法/数字,在 benchmark 的哪个 split、哪个 track、哪个评分器下产生**。规则:不得引用本表之外的数字;不得混用 track 语义;决策 (a) 已冻结(fixed_pool 仅 train)。

---

## 1. 方法侧(论文 Method 章节)允许引用的组件

| 组件 | 冻结出处 | 可主张措辞 | 禁止措辞 |
|---|---|---|---|
| 两级结构:Locator(事实定位)→ Ranker(候选精排) | `action_evidence_rerank_v27lean_20261006/CONFIG_FROZEN.json`(seed 0,15 fits:12 ranker + 3 locator) | two-stage evidence locator and ranker | "novel architecture"(组件均为标准件:MiniLM+BiGRU+attention) |
| Locator→Ranker 接口 | CONFIG_FROZEN:`locator_to_ranker_interface` | 只传被选中的**原始父动作 ID**,不传向量/置信度("selection without leaking representations") | 不得暗示端到端联合训练 |
| 历史编码 | `v27_model.py:ParentEncoder` | 时间排序父动作序列 + BiGRU + attention 池化(sequence-based) | **不得写成图方法**(无 GNN/邻接矩阵;角色关系以文本化记录进入序列) |
| attempted 口径 | RELEASE_PROTOCOL §1 | 保留 receipt_status=0,预测"发起动作"而非"成功转账" | — |
| 三个免训练基线 | `BASELINES_RETRIEVAL.json`(frequency/recency/random-legal,seed 20261006) | training-free baselines,同一评测器 | 不得称 baseline 为"我们方法的一部分" |
| grounding 可执行语义验证 | `EXECUTABLE_SEMANTICS_VALIDATION.json` | executable semantics:controlled-language generation + round-trip parsing + dual-implementation agreement(3755/3755) | **不得写 human verification / human-audited**(N5) |

## 2. 数字侧(论文 Results 章节)允许引用的表格

**主表:retrieval 轨,全 split**(评分器 = 发布版 `benchmark_evaluator.py`,复现通过)

| 方法 | train hits5/847 | dev hits5/67 | test hits5/69 | 出处 |
|---|---|---|---|---|
| frequency baseline | 385 (.455) | 27 (.403) | 37 (.536) | BASELINES_RETRIEVAL.json |
| recency baseline | 85 (.100) | 10 (.149) | 13 (.188) | 同上 |
| random-legal baseline | 0 (E≈.09 expected) | 0 | 0 | 同上 |
| v27lean ranker (R0/role-pool) | 305 (.360) | — | — | SCORING_V27LEAN_TRAIN.json retrieval |
| v27lean program_roles | 306 (.361) | — | — | 同上 |
| v27lean learned_locator | 297 (.351) | — | — | 同上 |

**副表:fixed_pool 轨,仅 train**(决策 (a);冻结口径,与主表**不可同列比较**)

| 方法 | hits5/847 | Top5 | MRR5 | Recall50/985 |
|---|---|---|---|---|
| all_history (R0 pool rank) | 416 | .422 | .300 | 674 (.684) |
| program_roles | 416 | .422 | .299 | 674 |
| learned_locator | 406 | .412 | .294 | 674 |

**grounding 表**:fact 三分类 + 三 scope 定位;聚合诊断引用 `SCORING_V27LEAN_TRAIN_DIAGNOSTICS.json`(7/7 冻结一致);验证声明引用 EXECUTABLE_SEMANTICS_VALIDATION.json。

**错误分析**:引用 `ERROR_ANALYSIS_RETRIEVAL.json`(hits5 稀有目标 .215 → 流行目标 .488;域外失败集中于新目标 121/317 vs 14/631)。

## 3. 必须写进 Limitation 的对应约束

- 冻结方法数字 = **TRAIN-only、单 seed、开发筛查口径**(CONFIG_FROZEN authorization);不得写成 held-out test 胜利。dev/test 只有免训练基线数字。
- learned_locator 相对 all_history 的 Top5 差为 **−0.010(bootstrap95 [−0.020, −0.002])**,净命中 −10:定位器在当前筛查中**未超过**简单历史池——论文如实报告为 negative result + 机制分析,不包装为增益(N4)。
- 域间不可比:retrieval 305 与 fixed_pool 416 的差 = 133 个截止后不可见地址 fail-closed + 池外;**只能作为协议严格度演示,不能当作方法退步**。
- 钱包聚类 bootstrap 是名义区间(共享目标依赖未去除)。
- grounding 是 executable-semantics 验证,不是人工验证;逐例 pilot 未执行。
- 2022-03–06 单窗口、1000 钱包;400 队列已排除(EXPOSURE_EVENT)。

## 4. 论文标题/贡献句模板(用 FACTS 名)

> FACTS: First-Attempt Counterparty Forecasting from Sequences
> Contribution 1: a benchmark of 2,200 queries over 1,000 Ethereum wallets with attempted-semantics labels, executable-semantics grounding evidence, and a fail-closed retrieval protocol;
> Contribution 2: training-free baselines + a frozen two-stage locator–ranker method screen under preregistered dev discipline, including a negative result on learned localization.

## 5. 作者确认清单(每行回"确认"或改)

1. 主表用 retrieval 全 split + 副表 fixed_pool train-only(决策 a)——是否同意?
2. learned_locator 负结果如实入正文(不藏)——是否同意?
3. grounding 措辞 = executable semantics,**不出现 human**——是否同意?
4. 基线三行进入主表与 v27lean 并列——是否同意?
5. 方法叙述 sequence-based,不用图叙事——是否同意?
