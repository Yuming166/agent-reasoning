# 方案 B 结果：扩展 dev（150 新案例）+ 选择器 v2

执行日期：2026-10-02（后台管道）。协议：`notes/expanded_dev_protocol_20261002.md`（冻结于任何新 dev 指标计算之前）。
产出根目录：`artifacts/expanded_dev_B_20261002/`。

## 0. 执行摘要（先说结论）

1. **训练集隔离成立**：新 150 案例全部 split='dev'，训练集字节级不变；重训 gate
   max_rank_diff=0（修复脚本 RNG 顺序 bug 后通过，见 §6）。
2. **主方法在新 dev 上方向反转**：chain_all R@50 = 0.7313 vs legacy_motif 0.7080
   （旧 52 上为 0.5962 vs 0.6538）。配对差 +0.0233，CI [−0.0103, +0.0594]——跨零，
   不构成显著超越；但这否定了"chain_all 系统性弱于 legacy_motif"的旧结论：
   两段合并不支持任一方向的稳定排序。
3. **选择器 v2 预注册判据不成立**：R@50 配对差 −0.0103，CI [−0.0258, 0.0]
   （下界 < 0）。机制上结构性注定：21/129 active 案例 target 不在主池，且这 21 个
   target 在 cutoff 前与钱包**零互动**（不在实验池），任何历史证据席位原理上救不回。
   席位只产生挤出（saved=0, displaced=2）。
4. **新 dev 上无任何变体达到显著正差**。legacy_cert_fusion 与 legacy_all_mlp 并列
   最高（0.7390），但对 direct_global_legacy 的 CI 均跨零
   （fusion: +0.0078 [0, +0.0181]——CI 下界恰为 0，按 >0 判据不算显著）。
5. 诚实结论：方案 B 把 CI 从 ±0.10+ 收窄到 ±0.03-0.06，足以**证伪**"chain_all 超过
   最强基线"的主张（对该数据口径），同时把 52 案例时代的负方向翻转为方向不定。

## 1. 七项 gate（协议 §7）

| # | gate | 结果 |
|---|---|---|
| 1 | 抽样确定性（重跑逐位一致） | ✅ 编排器重跑 step2，audit 数值逐位同（secs 443.9 vs 521.0 为计时不影响产物） |
| 2 | target 语义 52/52 对拍 | ✅ attempted 口径（预验证，52/52；success_only 仅 51/52） |
| 3 | 历史边界 + proofs | ✅ `max(ts) < 2022-07-01`；79,672 proofs，invalid=0 |
| 4 | 主池三源并集、无 target 注入 | ✅ no-injection 断言通过（全部候选 pre-cutoff 可见） |
| 5 | 重训 gate max_rank_diff=0 | ✅（首轮 320 系 gate 脚本自身 RNG bug，非管道漂移；见 §6） |
| 6 | 选择器 gate k=0 == raw R@50 | ✅ 0.731266149870801 双侧逐位相等 |
| 7 | 分母完整性 | ✅ 每变体 rank 行覆盖全部 129 active |

## 2. 新 150 dev：构建与结构

- 抽样框：2022-06 qualifying outgoing ≥10 笔，6,900 候选（排除 2300 案例钱包后 6,144），
  4 层配额 [37,38,38,37]，sha1 确定性排序。
- 150 案例 → **129 active**（86.0%；旧 52 shard 为 34.7% active——抽样框按 6 月活跃度
  分层，7 月初留存率随之上升，符合预期）。108 supported（池支持率 83.7%，旧 52 为 76.9%）。
- 主池均值 4,145 候选/案例；实验池（∪L1 入边）均值 4,248（+103/案例）。
- 泄漏披露（不排除）：0/150 与旧 train 钱包重叠；51/150 出现在旧 train 对手方宇宙
  （EOA 生态常态，协议 §1 声明）。

## 3. 主表：新 129 active，seed 平均（ALL-active 分母）

R@50（降序）：

| 变体 | R@50 | R@5 |
|---|---|---|
| legacy_all_mlp | 0.7390 | 0.4341 |
| legacy_cert_fusion | 0.7390 | 0.4574 |
| chain_all | 0.7313 | 0.4393 |
| minus_burst / minus_failure / minus_role | 0.7313 | 0.4419-0.4470 |
| direct_global_legacy | 0.7313 | 0.4548 |
| direct_global_chain | 0.7287 | 0.4548 |
| legacy_cert_frozen | 0.7261 | 0.4677 |
| legacy_motif | 0.7080 | 0.4341 |
| direct_global | 0.7028 | 0.4264 |
| invalid_control | 0.7028 | 0.4264 |
| certificate_only | 0.6434 | 0.3669 |
| own_frequency | 0.6434 | 0.3566 |
| graphmixer | 0.5788 | 0.3385 |

（全表：`artifacts/expanded_dev_B_20261002/metrics/metrics_by_variant.csv`）

### 配对 bootstrap（wallet cluster，2000 reps，rng 20261002）

预注册三组对比（R@50）：

| 对比 | diff | CI |
|---|---|---|
| chain_all vs direct_global_legacy | 0.0000 | [−0.0155, +0.0181] |
| chain_all vs legacy_motif | **+0.0233** | [−0.0103, +0.0594] |
| legacy_cert_fusion vs direct_global_legacy | +0.0078 | [0.0000, +0.0181] |

全部 22 变体 × 3 对比组：`metrics/paired_bootstrap.csv`。含跨零的如实报告——
没有任何对比组 CI 下界 > 0（legacy_cert_fusion 下界恰触 0，按判据不计显著）。

## 4. 选择器 v2：预注册判据不成立（负结果，如实报告）

- 主分析 k=5 vs k=0：R@50 **−0.0103，CI [−0.0258, 0.0]**；R@5 差恰为 0
  （席位不进 top-5 的机制设计兑现）。
- k 扫描：k=1/2/3/5 → R@50 = 0.7287 / 0.7261 / 0.7235 / 0.7209，单调下降——每个席位
  都是纯挤出。
- saved=0，displaced=2（`selector_v2_fixed/per_case_k5.csv`）。
- 证据表 14,939 行（`selector_v2_fixed/evidence_table.csv`）；资格集均值 115.8 候选/案例。

### 结构性解释（为什么 v2 在新 dev 上注定无效）

supported_main == supported_l1 == 108：**L1 扩池捞回 0 个新 target**。21 个 unsupported
案例的 target 在 cutoff 前与钱包零互动（既不在主池也不在实验池），属于"as-of 不可命名"
对手方——这不是选择器公式的问题，是问题本身的可观测性边界。席位只能重排历史证据
候选，救不回从未出现过的 target。

在 52 旧案例上 v1 曾有 1 个 saved（净正 0.609→0.628）；新 150 上 saved=0。两段合并看，
"证据席位"策略的净收益上限 = 案例库中"target 有历史互动但主池漏检"的比例——该比例
在 6 月高活跃抽样框下趋近于零（主池三源并集 + 高活跃度已把这类案例捞干）。

### 执行偏差记录（协议 §8 要求）

step5 首跑把实验池当成主池做资格过滤（`qualified_mean=0`，席位恒空，k>0 只把名单从
50 缩到 50−k，−0.0103 纯机械伪影）。修复版 `planB_step5b_selector_v2_fixed.py`
（资格=不在三源并集，输出 `selector_v2_fixed/`）与首跑数值逐位一致——因为
saved 结构性为 0，席位地址永远不是 target，两版对 target 命中的影响等价。
首跑产物保留在 `selector_v2/` 作偏差记录。

## 5. 合并视角（secondary；协议 §5：不做跨段配对差）

| 变体 | 新129 | 旧52 | 合并181 |
|---|---|---|---|
| chain_all | 0.7313 | 0.8397* | 0.7624 |
| legacy_motif | 0.7080 | 0.8782* | 0.7569 |

\* 旧 52 与 §0 摘要里 0.5962/0.6538 的差异：本表旧 52 为"逐案例 seed 平均后取均值"
（案例级），metrics.json 的 0.5962/0.6538 为池级并集口径——同一冻结 rank，聚合方式不同。
合并 181 上 pooled diff = +0.0055（描述性数字，无配对意义）。

## 6. 执行事故与修复记录（透明披露）

1. **Step2 label 修复**（管道启动前）：首跑 label 用了仅到 6 月的事件表 → active=0；
   改 7-8 月独立加载（label-only，不进历史索引）后 active=129。
2. **Step5 资格过滤 bug**：见 §4。修复后数值不变（结构性原因），偏差已记录。
3. **Step6 重训 gate 两次失败**（重要教训）：
   - 首跑 `KeyError: 'valid'`：collate 依赖 prepare() 添加的键，脚本漏调 prepare——
     对照原训练脚本 `train_certificate_v2.py:179` 修复。
   - 二跑 max_rank_diff=320：**RNG 顺序 bug**——原训练是 `torch.manual_seed(seed)`
     在 `Scorer(variant)` 之前（初始化消耗 torch RNG），gate 脚本顺序反了，
     epoch-1 loss 5.559（冻结）vs 6.151（复刻）为诊断线索。修复后 max_rank_diff=0。
   - 教训：**复刻训练循环时，seed 设置必须逐行对照原脚本的位置，而不只是值。**
     失败 gate 结果归档于 `retrain_gate/gate.rng-order-bug.json`。
4. **Step7 性能**：逐候选全表扫描 8.5M 行不可行，改预分组字典（与 step5b 同模式）。

## 7. 与 52 案例结论的合并解读

- 52 案例（2026-10-02 早前）：chain_all 0.609 vs legacy_motif 0.647（差 −0.038，
  CI 跨零但方向为负）→ 当时结论"主方法未超过最强基线"。
- 新 150：差 +0.0233 [−0.0103, +0.0594]（方向为正，跨零）。
- **两段同协议、同冻结模型、同指标口径**；方向翻转说明 52 案例上的负方向是
  小样本噪声，不是 chain_all 的系统性缺陷。同理，新 150 上的正方向也不构成
  超越证据。诚实的现状：**chain_all ≈ direct_global_legacy ≈ legacy_motif
  （在 CI 精度内不可区分），证书修正不带来 R@50 净损失也不带来净增益。**
- 选择器 v2 的失败是可观测性边界（§4），不是公式调参问题——v2 修正了 v1 的
  recency-压倒-笔数弱点（Step7 机制对照见 §8），但候选池里已无它可救的案例。

## 8. Step7：旧 52 机制对照（v1 vs v2 强度排名）

51 案例（52 active 中 1 例证据表为空）、1,850 个 L1 资格候选：v2 相对 v1 改动 959 个
排名，最大跃升 169 位。预注册动机案例 0xeabb（2 笔入边 + 72 天旧 donor）确认被 v2
修正：强度 0.0997 → 0.2429（笔数通道 + 回路通道 n_out_back=2 共同贡献），在候选内
排名 5 → 5（该案例新近对手恰好也强，名次未变，但公式不再系统性惩罚旧多笔 donor）。
产物：`selector_v2/old52_mechanism_check.json`、`old52_v1_vs_v2_ranks.csv`。
本节为机制对照，非主要证据——v2 在新 150 上已按 §4 判据判负。

## 9. 下一步建议

1. **停止在"席位/扩池"方向上加方法**：新 dev 证明 unsupported 案例是 as-of 不可命名的，
   选择器没有可救的案例。证据可信度路线的可覆盖面上限已探明。
2. chain_all 与免证基线在两段 dev 上均不可区分——论文主张应转向：
   **证书机制以零精度损失换可验证性/审计性**（每个 rank 有 proofs 支撑），
   而非"更准"。这仍是一个可辩护的贡献，且 V3 formal（AUROC 0.4125）支持
   证书不可伪造的前提。
3. 若追求 R@50 提升，剩余空间在 unsupported 21 案例——需要 as-of 可见的先验
   （合约语义/地址类型），与"部分可观测条件下的联合决策"框架互补。
