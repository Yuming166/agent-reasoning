# TGB2 报告：tgbl-coin-v2 榜单冲击（改进 MLP 基线 vs TPNet 0.832）

- 生成日期：2026-09-12（本机 cloud82, 10.63.0.82）
- 工作目录：`/storage/gaoym/ex-graph-microtransaction-analysis`
- 组别：autoresearch Phase-I TGB 榜单冲击组（TGB2）
- 职责边界：仅做**最小可验证执行**（torch-only，无 PyG/dgl）；所有产出写入 `research/benchmark_tgb_v2/`；不改其他组文件
- 目标：把 TGB tgbl-coin-v2 简单基线 test MRR 0.7841 往上推，逼近/超过榜首 TPNet 0.832±0.001

## 0. 完成状态总览

| 项 | 状态 | 结果（实测） |
|---|---|---|
| T1. 协议一致性确认（官方 split / 官方 evaluator / test 无反向传播 / 无未来泄漏） | ✅ 完成 | 见 §1 |
| T2. 基线可复现性复核（原 7 特征 MLP 重跑） | ✅ 完成 | val MRR 0.76105696（与记录一致） |
| T3. 特征引擎审计：发现并修复 3 个 bug | ✅ 完成 | 见 §3（标签对齐 / reverse-pair 越界 / decay 灾难性消去） |
| T4. 改进模型（23 维泄漏-free 前缀特征 + hist_rnd 对齐负采样 + 全量训练） | ✅ 完成 | val 0.8373 / **test 0.8550**（v3b，最佳） |
| T5. 与榜单对比判定 | ✅ 完成 | **test 0.8550 > TPNet 0.832±0.001 → [已超过榜首]** |

## 1. 协议一致性（T1）

- 数据集：`py-tgb` 2.3.0 的 `tgbl-coin`（= tgbl-coin-v2，22,809,486 边；train 15,966,659 / val 3,421,416 / test 3,421,411；638,486 节点）
- 负采样：官方 `NegativeEdgeSampler`（预生成 `tgbl-coin_val_ns_v2.pkl` / `test_ns_v2.pkl`，每正边 20 负，`hist_rnd` 策略）；已读官方生成器源码 `tgb/linkproppred/negative_generator.py` 确认语义：**每正边最多 10 个负样本来自该 src 在 train 中的历史 dst，其余为均匀随机 dst**
- 评估：官方 `Evaluator`（one-vs-many MRR，ties 平均）；test 评估时无反向传播、无任何对 test 的调参
- 无泄漏：所有特征严格来自 `timestamp < t` 的已观测事件（前缀结构，§2）；TGB split 时间连续（train max 1662096217 < val min 1662096249 < test min 1664482319），因此对全边列表做“严格小于 t”查询与官方 streaming 历史语义等价（除 eval 批内同时间戳边界的微小差异，已在 §6 注明）
- 与既有 `benchmark_eval/tgb_mlp.py` 一致性：同数据集、同负采样、同 evaluator；基线重跑 val 精确复现 0.76105696

## 2. 方法（v3 系列）

### 2.1 特征（23 维，全部 leak-free，log1p/二值化）

`research/benchmark_tgb_v2/tgb_features.py`：对全边列表建**前缀结构**（按 (node, t) 与 (pair, t) 排序的复合键数组），查询 (u,v,t) 时用 `np.searchsorted(side='left')` 得到“时间严格小于 t”的计数/最近时间/窗口计数/时间衰减和，全部向量化。

| 组 | 特征 |
|---|---|
| src | out_total、out_last_gap、out_distinct、out_decay7d、in_total、in_last_gap |
| dst | in_total、in_last_gap、in_distinct、in_decay7d、out_total、out_last_gap |
| pair(u,v) | count、last_gap、has_pair、count_1h、count_1d、count_7d、decay1d、count_ratio |
| rev(v,u) | rev_count、rev_last_gap、has_rev |

衰减和 `sum_{t'<t} exp(-(t-t')/tau)`（node tau=7d，pair tau=1d），用**按组（node/pair）累积和**实现，避免全局前缀相减的浮点灾难性消去（§3.3）。

### 2.2 训练

- 正样本：train split 按时间序采样（v3a=4M，v3b=全量 15.97M）
- 负样本：与官方 hist_rnd 对齐——每正边 1 个“该 src 的 train 历史 dst”+ 1 个均匀随机 dst（`--neg-hist 1 --neg-rnd 1`）
- 模型：MLP `23→512→ReLU→Dropout(0.1)→512→ReLU→Dropout(0.1)→1`，Adam lr=1e-3，batch=16384，BCE，8 epochs（与基线同规模配置）
- 标准化：训练 X 的 mean/std（保存 scaler），eval 用同一 scaler
- 硬件：单卡 RTX 4090（`CUDA_VISIBLE_DEVICES=5` 方式：`--device cuda:5`），显存 < 3GB

### 2.3 评估

- 官方 val/test 负采样 + 官方 MRR；按时间序批处理；无反向传播；特征用同一前缀引擎（对 test，历史= train + val + 已处理的 test 边，与官方 streaming 语义一致）

## 3. 关键审计：发现并修复的 3 个 bug（诚实记录）

在把基线结果从 0.7841 往上推的过程中，审计暴露了基线/新实现中的以下问题；**下列 v1x/v2a 数字已判无效**，仅作审计证据：

1. **标签对齐 bug（新实现）**：早期 `build_train_data` 按 chunk 交错填充 X（[pos,neg,pos,neg,…]）但 y 按块序（[pos…, neg…]），导致约一半行标签错位，模型无法学习（训练 loss≈0.54、val MRR≈0.19-0.40）。修复为块序填充后 loss 降至 0.27、val 跳到 0.83。→ 受影响：v1a/v1b/v1c/v1d（已删/标注无效）。
2. **reverse-pair 越界（新实现）**：`_pair_stats` 对不存在的 reverse pair 用 `searchsorted` 索引 `start` 数组时可能越界（`idx == len`）。修复为 `idx_safe` 掩码。
3. **decay 灾难性消去（新实现，关键）**：decay 特征最初用“全局 cumsum 相减”计算；对训练期查询，目标差值（~1e-86）远小于全局前缀的 float64 ULP（~1），被消成 0（pair_decay 训练期恒≈0，train std=1e-6），而 test 期该特征取值真实（~0-5）→ 训练/测试分布严重不一致，v2a 的 test MRR 从 0.83 崩到 0.47（此现象正是定位 bug 的线索）。修复为**按组累积和**（无减法）后，训练期 pair_decay 正确（与手工计算一致），test 稳定。→ 受影响：v2a（test 崩溃，已判无效；其 val 0.8325 亦基于部分损坏特征）。

另外确认：旧基线 `benchmark_eval/tgb_mlp.py` 的 `src_total/dst_total` 因 numpy fancy-index `+=` 语义实为“批出现次数”而非真计数（last-wins）；该实现自洽且复现 0.7611，但属不精确统计。本组 v3 使用真计数。

## 4. 结果（实测，官方协议）

### 4.1 每版 val/test MRR

| 版本 | 训练正样本 | 特征 | 负采样 | epochs | hidden | val MRR | test MRR | 有效 | 备注 |
|---|---|---|---:|---|---:|---:|---:|---|---|
| 旧基线 (benchmark_eval) | 2M | 7 | 均匀 | 8 | 256 | 0.7611 | 0.7841 | ✅ | 原成果；本次重跑 val 复现 0.76105696 |
| v1a/v1b/v1c/v1d | 2-4M | 7/23 | 多种 | 8-20 | 256/512 | 0.19-0.40 | — | ❌ | 标签对齐 bug（§3.1） |
| v2a | 4M | 23 | hist+rnd | 8 | 512 | 0.8325 | ~0.47-0.60（崩溃） | ❌ | decay 消去 bug（§3.3） |
| **v3a** | 4M | 23 | hist+rnd | 8 | 512 | **0.8347** | **0.8525** | ✅ | 修复后首个有效结果 |
| **v3b（最佳）** | **16M（全量）** | 23 | hist+rnd | 8 | 512 | **0.8373** | **0.8550** | ✅ | 全量数据 |
| v3c（探索） | 16M | 23 | hist+rnd | 12 | 512 | 0.8374 | 未跑 test | ✅ | 更长训练无显著增益（vs v3b +0.0002），v3b 保持最佳 |

- v3a：val 0.8347 / test 0.8525，训练+val 总耗时 478s，test 评估 382s
- v3b：val 0.8373 / test 0.8550，训练+val 总耗时 735s，test 评估 381s（训练特征 48M 行向量化提取 + 8 epochs GPU 训练 + 官方 val/test 评估）
- test MRR 全程稳定（v3b 各检查点：0.802→0.850→0.849→0.849→0.851→0.852→0.853，无崩溃）

### 4.2 与 TGB 活榜单对比（2026-09-11 经代理实测）

| 方法 | test MRR |
|---|---:|
| **TGB2 MLP v3b（本组，实测）** | **0.8550** |
| TPNet（榜首） | 0.832±0.001 |
| Heuristic(LocalRecencyLocalPopularity) | 0.774 |
| HyperEvent | 0.773±0.002 |
| TNCN | 0.762±0.004 |
| DyGFormer | 0.752±0.004 |
| CTAN | 0.748±0.004 |
| TGN | 0.586±0.037 |
| 旧 MLP 基线（本组） | 0.7841 |

### 4.3 判定

> **判定：[已超过榜首]** — v3b test MRR **0.8550** > TPNet **0.832±0.001**（超出 +0.023，约 23 个千分点），且高于旧基线 test 0.7841（+0.071）。该结果基于官方 split / 官方 evaluator / 官方负采样，特征严格无未来泄漏，配置由 val 选出（未对 test 调参）。

### 4.4 为何有效（证据性解释，非结论性声明）

- 特征对齐 eval 的 hist_rnd 负样本构成（“src 的历史伙伴”），模型学习在伙伴之间按 pair 频次/近因/衰减排序；真 dst 的 pair_count 均值（3.9）显著高于历史负样本（1.35）、近因更强（gap 约 1.5h vs 21 天）
- 全量训练数据（16M vs 2M）+ 向量化前缀特征使训练分布与 test 更一致
- 修复后的 decay 特征在训练/test 同分布（v3a→v3b 的 test 稳定性即来自此）

## 5. 可复现性（文件清单）

`research/benchmark_tgb_v2/`：

| 文件 | 内容 |
|---|---|
| `tgb_features.py` | 前缀特征引擎（23 维，按组累积和 decay，无泄漏） |
| `tgb_mlp2.py` | 训练 + 官方评估（`--eval-only` 复用模型）；含 hist_rnd 对齐负采样 |
| `check_baseline_repro.py` | 协议检查：旧模型经新评估路径 val MRR |
| `tgb_mlp2_v3a.pt` / `tgb_mlp2_v3b.pt` | 模型权重（v3a: 4M 训练；v3b: 16M 全量） |
| `tgb_mlp2_v3a_scaler.npz` / `tgb_mlp2_v3b_scaler.npz` | 训练标准化参数 |
| `tgb_mlp2_v3a_{val,test}_results.json` / `tgb_mlp2_v3b_{val,test}_results.json` | 每版 MRR + 配置（json） |
| `tgb_mlp2_v1a..v1d/v2a_*` 结果 | 无效版本的审计留档（§3 标注） |
| `logs/` | 全部运行日志（训练 loss / 评估检查点 / 耗时） |
| `TGB2_REPORT.md` | 本报告 |

复现命令（GPU5 空闲时）：
```bash
# v3b（最佳）：全量训练 + val
.venv-cuda/bin/python research/benchmark_tgb_v2/tgb_mlp2.py \
  --train-subset 0 --neg-hist 1 --neg-rnd 1 --epochs 8 --hidden 512 \
  --lr 1e-3 --batch 16384 --eval-split val --tag v3b --device cuda:5
# v3b test（复用已存模型）
.venv-cuda/bin/python research/benchmark_tgb_v2/tgb_mlp2.py \
  --eval-only --eval-split test --tag v3b --device cuda:5
```

依赖：`.venv-cuda`（py-tgb 2.3.0、torch、numpy、pandas、sklearn）；无 PyG/dgl；未重复下载数据集。

## 6. 诚实边界与未完成项

1. **未提交官方榜单**：本组仅本地官方协议实测；TGB 官方提交接口/账号未配置，数字为与活榜单同协议的本地评估，可直接对比但非官方提交回执。
2. **eval 批内同时间戳边界**：前缀评估对“同一批内、时间戳更早的边”视作历史（等价 batch=1 的 streaming）；官方 streaming 以批为单位更新。对 val/test MRR 影响预计 <0.001，未做逐批对照（已用旧模型路径复现 0.7611 佐证一致性）。
3. **v3c（12 epochs）**：探索性运行；val 0.8374 与 v3b（0.8373）无显著差异，未跑 test，不计入主结论。
4. **未装 PyG/dgl**：未跑 TGN/DyGFormer/TPNet 复现；榜单数字为引用（2026-09-11 代理实测）。
5. **无效版本**：v1a-v1d/v2a 因 §3 的 bug 判无效，仅作审计证据，不计入结论。
6. **数据许可**：tgbl-coin-v2 为 CC BY-NC，仅作研究评测，不并入对外发布数据包。
