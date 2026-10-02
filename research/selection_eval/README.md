# Group SELECT — Budgeted Wallet Selection：预算化钱包选择的冻结评估框架与 09-01 首次结果

> 状态：**评估框架已搭建 + cutoff=2022-09-01 首次结果已产出**（2026-09-11，cloud82，10.63.0.82）。
> 依据冻结协议 `research/audit/temporal_protocol.yaml` v1.0 与 `research/audit/DATA_AUDIT.md`（Group 0）；
> 对应方案 `research/autoresearch_phase1.md` §8（Dynamic Influential Wallet Discovery）、
> §9（Budgeted Wallet Selection，高优先级）、§13（评估协议）、§14（基线层级）、§16（K 敏感度）。
> 所有数字均为**描述性**、单次冻结 holdout 证据；**不声称因果、不声称有效性/优越性、不声称 SOTA**
> （铁律）。

---

## 0. 一句话总结（claim boundary）

在 cutoff=2022-09-01、只用严格早于 cutoff 的 90 天历史状态（以及各 Group 已冻结的 09-01 产物）
做 top-K 钱包选择，再在冻结的未来窗 `[2022-09-01, 2022-10-01)` 上评估的设定下：

- **预测类选择器（Group B frozen predictions）在"每钱包未来效用 U(K)/K"上领先全支持基线**：
  K=10 时 `predictive_act`/`predictive_new`/`hybrid_pred_vol` 的 U/K（= 未来 30 天新对手方
  均值）为 **457 / 457 / 466**，约为随机期望（7.2）的 **64 倍**；K=100 时约为 160–169（随机 7.2）；
- **体量/结构基线也很强**：K=10 时 `eth_flow` U/K=346、`volume`=304、`degree`=285、
  `betweenness`=378（结构支持集内）；与预测选择器同属一个量级，不能宣称"预测显著碾压基线"；
- **IG 选择器语义与效用需区分**：`ig_cp`（对"未来 cp≥10"的遮蔽信息增益）K=10 U/K=42.7、
  K=1000 Recall@K=0.471（IG 2,999 支持集内）；`ig_active`（对未来活跃）选出的是模型最"确信不活跃"
  的钱包，top-10 未来效用为 0 —— 这是未取绝对值的遮蔽 IG 在负例上的语义，**不是选择器 bug**；
- **支持集边界主导可比性**：结构 7,929（正样本覆盖 0.565）与 IG 2,999（覆盖 0.161）均为受限子集，
  全支持与受限支持分开报告，**不做支持外推**；
- 这些数字只回答"哪类历史信号选出的钱包，其未来窗口效用更高"这一**选择层**问题；
  选择层效用 ≠ 端任务预测优越性、≠ 因果影响力（协议 §5 reporting_rules）。

---

## 1. 任务定义（Budgeted Wallet Selection）

在 cutoff t（本次 t=2022-09-01）：

1. 给定 `G_≤t`（仅含严格早于 t 的信息）与钱包全量 N=27,613 目标地址
   （as-of 表 `wallet_asof_features_20220901` 覆盖其中 18,519 个有 90 天事件的活跃钱包）；
2. 用选择器（selector）为每个钱包打分，取 **top-K**（`K∈{10,25,50,100,250,500,1000}`）冻结；
3. 未来窗 `[t, t+30d)` 隐藏，评估时只计算被选集合的未来效用；
4. 输出 **U(K)**（未来效用总和/均值）、**U(K)/K**（每选中钱包的效用）、**Recall@K** 与
   预算质量前沿（U vs K、U/K vs K），并做 §14 全层级基线对比与支持集受限对比。

**无泄漏契约**：选择分数只用 `< t` 的信息；未来标签只用于评估；静态全窗先验（
`static_degree`/`static_pagerank`）标记为 LEAKY 基线单独报告；K 不在最终测试期调参
（协议 §4、§5、§16）。


## 2. 数据契约与支持集（09-01，全部复用、不重算、不查 BigQuery）

| 支持集 | 钱包数 | 来源文件 | 正样本数(new_cp>0) | 正样本覆盖 | 选择器 |
|---|---:|---|---:|---:|---|
| full（全支持） | 18,519 | Group B `labels_20220901_bq.csv`（= 冻结表 `wallet_asof_features_20220901` 09-01 分区，经 Group B 拉取） | 10,585 | 1.000 | random / volume / eth_flow / activity / behavioral / predictive_* / hybrid_pred_vol |
| usd（USD 体量） | 16,910 | Group A `usd_capital_20220901.csv`（至少一个 USD 计价列非空；93 个钱包无任何 USD 计价不在支持集） | 10,336 | 0.976 | volume_usd |
| structural（结构） | 7,929 | Group C `wallet_importance_20220901.csv`（matched-matched as-of 子图） | 5,977 | 0.565 | degree / weighted_degree / pagerank / kcore / betweenness / bridge_score / static_*(LEAKY) |
| ig（信息增益） | 2,999 | Group D `wallet_ig_20220901.csv`（`ig_occ` 按 target×model 取 histgbm 的测试折值；与 `ig_vs_baselines_20220901.csv` 一致） | 1,707 | 0.161 | ig_cp / ig_active / hybrid_pred_ig |

- 标签列：`fwd30_evt_cnt / fwd30_cp_distinct / fwd30_new_cp`（`[09-01,10-01)`），
  与 Group 0 审计口径一致（18,519 行；14,170 有未来事件；10,585 有未来新对手方）。
- 交叉校验：Group B labels 与 Group A feature matrix 内嵌标签、Group C wallet_importance 内嵌标签
  逐钱包完全一致（max abs diff = 0）。
- **没有发起任何 BigQuery 查询**：标签/特征全部来自本机已冻结的 Group 产物
  （Group B 已在 09-11 用 `src/bq_run.py`+分区过滤拉取过 labels）。

## 3. 选择器清单（09-01，分数列 = 打分依据，越高越好）

| key | 层级（§14） | 支持集 | 分数定义 | 来源 |
|---|---|---:|---|---|
| random | Random | full | 均匀随机，固定 seed=20220901（单次抽样；期望值另作 `random_expected`=K×均值） | 本组 |
| volume | Size | full | `evt_cnt_90d`（90 天主事件数） | Group A 特征矩阵 |
| volume_usd | Size | usd | `native_usd+token_usd_priced`（as-of USD 体量，余额型非流量） | Group A |
| eth_flow | Size | full | `evt_native_90d`（原生 ETH 事件数，流量代理） | Group A 特征矩阵 |
| activity | Temporal | full | `active_days_90d`（活跃天数广度；粗分数，顶部 tie=22 钱包，见 §9） | Group A 特征矩阵 |
| recency | Temporal | full | `90 - last_event_recency_days`（越近越高） | Group A 特征矩阵 |
| persistence | Temporal | full | `active_span_days_90d`（活跃跨度；顶部 tie=1,690，粗分数） | Group A 特征矩阵 |
| behavioral | Behavioral | full | Group A `full_asof__kmeans` persona 内 `evt_cnt_90d` 百分位（每簇取"体量代表"） | Group A persona |
| behavioral_act | Behavioral | full | 同上但按 `active_days_90d` 百分位 | Group A persona |
| predictive_act | Predictive | full | Group B 冻结 LightGBM 水平预测 `pred_act_level_LightGBM`（未来活跃水平） | Group B holdout09 |
| predictive_new | Predictive | full | `pred_new_level_LightGBM`（未来新对手方水平） | Group B holdout09 |
| hybrid_pred_vol | Hybrid | full | percentile-rank 均值（predictive_act + volume） | 本组组合 |
| degree | Structural | structural | as-of 无向度 `deg_und` | Group C |
| weighted_degree | Structural | structural | as-of 加权无向度 `wdeg_und` | Group C |
| pagerank | Structural | structural | as-of PageRank | Group C |
| kcore | Structural | structural | as-of k-core 数（仅 5 个取值，tie=187，见 §9） | Group C |
| betweenness | Structural（扩展） | structural | as-of 介数 | Group C |
| bridge_score | Structural（扩展） | structural | Group C 社区桥分数 | Group C |
| static_degree / static_pagerank | Structural static prior | structural | 全窗静态先验（**LEAKY**，仅基线层，不作结论） | Group C |
| ig_cp | Information | ig | 对 `y_cp_ge10`（fwd30_cp≥10）的 HistGBM 遮蔽信息增益 `ig_occ` | Group D wallet_ig |
| ig_active | Information | ig | 对 `y_active30`（fwd30_evt>0）的 HistGBM 遮蔽 IG | Group D wallet_ig |
| hybrid_pred_ig | Hybrid | ig | percentile-rank 均值（predictive_act + ig_cp） | 本组组合 |

## 4. 评估协议与指标

对每个选择器 s 与其支持集 S（n=|S|）、top-K 集合 T_K：

- `U_evt/cp/new_sum(K)` = Σ_{i∈T_K} fwd30_{evt_cnt,cp_distinct,new_cp}_i（未来效用总和）
- `U_evt/cp/new_mean(K)` = U_sum(K)/K —— **即 U(K)/K**（每选中钱包的期望未来效用）
- `Recall@K` = |{i∈T_K: fwd30_new_cp>0}| / |{i∈S: fwd30_new_cp>0}|（支持集内正样本召回）
- `mass_share` = U_sum(K) / Σ_{i∈S} label_i（支持集内未来事件质量覆盖份额）
- `positive_support_coverage` = 支持集内正样本数 / 全域正样本数（支持集纪律指标）
- 参考上界：`oracle_*` = 按未来标签取 top-K（post-hoc，只作前沿上限参照，**不是选择器**）；
  `random_expected` = K × 支持集标签均值（解析期望）。

**支持集纪律**：主表按各选择器原生支持集报告；可比性用两个受限共池（structural_restricted
7,929、ig_restricted 2,999）把所有有分的选择器**在同一池内**重排再比；任何指标都标注分母所在
支持集，**不做支持外推**。

## 5. K 前沿关键数字（cutoff=2022-09-01，原生支持集）

### 5.1 U(K)/K = 每选中钱包的未来 30 天新对手方均值（fwd30_new_cp mean）

| selector | K=10 | K=50 | K=100 | K=250 | K=1000 | 支持集 |
|---|---:|---:|---:|---:|---:|---|
| random（单次抽样） | 9.4 | 14.4 | 11.4 | 8.8 | 8.6 | full |
| random_expected（解析期望） | 7.2 | 7.2 | 7.2 | 7.2 | 7.2 | full |
| volume | 303.7 | 190.2 | 142.9 | 96.8 | 48.9 | full |
| eth_flow | 345.8 | 190.8 | 139.6 | 94.9 | 48.4 | full |
| activity | 127.9 | 165.5 | 121.8 | 87.1 | 48.1 | full |
| behavioral | 144.5 | 36.6 | 22.5 | 20.9 | 17.4 | full |
| predictive_act | 456.9 | 219.2 | 159.9 | 105.7 | 52.2 | full |
| predictive_new | 457.1 | 232.7 | 168.6 | 107.8 | 52.1 | full |
| hybrid_pred_vol | 466.3 | 222.4 | 162.6 | 105.0 | 52.4 | full |
| degree | 284.8 | 135.7 | 115.3 | 84.5 | 41.9 | structural |
| weighted_degree | 193.8 | 64.2 | 57.6 | 43.4 | 28.9 | structural |
| pagerank | 200.5 | 118.5 | 88.4 | 66.0 | 37.0 | structural |
| kcore | 74.4 | 54.2 | 67.3 | 61.7 | 40.0 | structural |
| betweenness | 378.4 | — | 112.1 | — | 41.2 | structural |
| ig_cp | 42.7 | 19.1 | 24.4 | 22.0 | 16.7 | ig |
| ig_active | 0.0 | 0.0 | 0.0 | 0.0 | 5.7 | ig |
| hybrid_pred_ig | 59.1 | 58.9 | 40.7 | 34.0 | 17.7 | ig |
| oracle_new（post-hoc 参考） | 728.4 | — | — | — | — | full |

### 5.2 U(K) 总和（fwd30_new_cp sum，全支持集内）

| selector | K=10 | K=100 | K=1000 |
|---|---:|---:|---:|
| random | 94 | 1,136 | 8,550 |
| predictive_act | 4,569 | 15,994 | 52,150 |
| predictive_new | 4,571 | 16,855 | 52,083 |
| hybrid_pred_vol | 4,663 | 16,260 | 52,353 |
| volume | 3,037 | 14,293 | 48,855 |
| eth_flow | 3,458 | 13,957 | 48,360 |

（全支持集 fwd30_new_cp 总和 = 132,763；K=1000 时 predictive_act 捕获 ~39.3% 的新对手方质量，
volume ~36.8%，见 budget_frontier.csv `mass_share_fwd30_new_cp`。）

### 5.3 Recall@K（正样本 = fwd30_new_cp>0，分母为各自支持集）

| selector | K=100 | K=1000 | 支持集（正样本数） |
|---|---:|---:|---|
| predictive_act | 0.0094 | 0.0937 | full (10,585) |
| volume | 0.0094 | 0.0905 | full (10,585) |
| degree | 0.0167 | 0.1620 | structural (5,977) |
| ig_cp | 0.0551 | 0.4710 | ig (1,707) |
| hybrid_pred_ig | 0.0586 | 0.5226 | ig (1,707) |
| ig_active | 0.0000 | 0.1611 | ig (1,707) |

> 注意：Recall@K 的分母随支持集不同（10,585 / 5,977 / 1,707），**跨支持集不可直接比大小**；
> ig 支持集只占全域 16.2% 且只含 1,707 个正样本，K=1000 时已覆盖其 1/3 钱包，Recall 自然高。

## 6. 选择器对比摘要（描述性，单次 holdout）

1. **全支持集（18,519）内，预测选择器领先体量与活动，但幅度随 K 收缩**：
   K=10 时 predictive_act/predictive_new/hybrid_pred_vol 的 U/K（new_cp）≈ 457–466，
   是 volume（304）的 ~1.5 倍、activity（128）的 ~3.6 倍、random 期望的 ~64 倍；
   K=1000 时三者 ≈ 52，volume ≈ 49，差距收窄到 ~7%。`predictive_new` 与 `predictive_act`
   表现接近（Spearman 高、top-K 重叠 0.74@K=100 / 0.83@K=1000）。
2. **hybrid_pred_vol 在 K=10 略优于单独预测/单独体量（466 vs 457/304），但差异远小于单次
   holdout 的抽样噪声**，只作描述性记录，不作优越性声明。
3. **结构支持集（7,929）内，as-of degree / betweenness / bridge_score 是强基线**：
   K=10 时 betweenness U/K=378、degree=285，接近全支持 predictive 的水平——但注意它们只在
   结构子图（正样本覆盖 0.565，均值 new_cp 12.96 vs 全域 7.17，天然高效用子集）内可评，
   跨支持集不能直接比。
4. **IG 选择器：`ig_cp` 有用但量级低于体量/预测**；`ig_active` 选出"模型最确信不活跃"的钱包
   （top-10 未来效用=0；K=1000 也仅 5.7）。语义：Group D 的 `ig_occ` 是**未取绝对值**的遮蔽
   信息增益；对未来活跃目标，极值主要来自负例钱包（其自身特征是模型判"不活跃"的原因，遮蔽后
   模型翻转为活跃），因此不能把 ig_active 当作"未来活跃钱包"选择器使用。
5. **behavioral（簇内体量代表）K=10 高（144.5）但迅速衰减**：它按 persona 覆盖 10 个簇，top-10
   恰好含各簇最大钱包（含全局巨头）；K≥50 后每簇代表性挤占效用，与 volume 的差距拉大。作为
   "多样化的体量基线"理解更合适。
6. **volume_usd（USD 余额型体量）显著弱于 evt 体量**（K=10 U/K=13.3 vs volume 303.7）：
   USD 余额抓的是"持有量"而非"交易活动"，与未来事件效用的关联弱；这与 Group C 的
   "体量≠结构、余额≠流量"边界一致。

## 7. 支持集边界与受限对比

- **full 18,519**：正样本覆盖 1.000；均值 new_cp 7.17。
- **usd 16,910**：覆盖 0.976；均值 new_cp 7.57（略偏高，因缺 USD 计价的多为极低活动钱包）。
- **structural 7,929**：覆盖 0.565；均值 new_cp 12.96 —— **显著更高效用的子集**（matched-matched
  子图偏好有交互的钱包）。
- **ig 2,999**：覆盖 0.161；均值 new_cp 6.99（与全域接近，随机子集）。
- **受限共池对比（同一池内重排，解决支持集不可比）**：
  - `structural_restricted`（7,929）：K=10 时 betweenness 378 / degree 285 / volume 304 /
    predictive_act 457（预测选择器在全池仍领先）；K=1000 时 volume 49.3 / predictive_act 52.1 /
    degree 41.9，预测与体量收敛。
  - `ig_restricted`（2,999）：K=1000 时 hybrid_pred_ig U/K=17.7、ig_cp 16.7、volume 17.2、
    activity 17.3（池内收敛；结构类仅 1,283 个钱包有分，单独标注 n_support）。
  - 结论：**预测/体量两类选择器在受限池内也稳定地处于第一梯队；IG 单独不敌体量，但
    hybrid_pred_ig 在 IG 池内与体量打平**。以上均为单次 holdout 描述性结果。

## 8. 08-01 稳健性检查（描述性，walk-forward 证据）

用 Group A `asof_monthly_2022.parquet` 的 2022-08-01 快照（19,062 钱包，自带 fwd30 标签）
对可在本机计算的 4 个选择器（volume / eth_flow / activity / persistence）重跑前沿
（结果 `results/robustness_0801.json`）：

| selector | 08-01 U/K@K=100 (new_cp) | 08-01 vs 09-01 top-100 Jaccard |
|---|---:|---:|
| volume | 120.0 | 0.538 |
| eth_flow | 128.6 | 0.613 |
| activity | 111.8 | 0.527 |
| persistence | 26.7 | 0.163 |

- 08-01 的量级与 09-01 一致（volume@K=100：09-01 为 142.9，08-01 为 120.0），
  选择集月度重叠 0.53–0.61，方向稳定；persistence 重叠低（0.16），因其分数粗（tie=1,690）。
- **边界**：08-01 只是描述性稳健性佐证；冻结的最终 holdout 仍是 09-01（只评估一次）；
  08-01 无 Group B 预测分数/结构分数/IG 分，故该检查仅覆盖体量/活动类选择器。

## 9. Failure modes（本框架已知失效模式）

1. **粗分数 tie**：`kcore` 仅 5 个取值（max tie=187）、`activity` 顶部 tie=22、
   `persistence` max tie=1,690 —— top-K 在 tie 组内由地址字典序确定性打断，集合是"其中一个
   合法断点"，需结合 tie 诊断解读（`selection_results_20220901.json` → `selectors.*.tie_diagnostics`）。
2. **支持集差异**：结构/IG 是天然高/低效用子集，原生口径跨集对比会误导；必须用受限共池对比。
3. **IG 语义陷阱**：未取绝对值的遮蔽 IG 在负例上极值含义相反（ig_active 案例），
   使用前必须核对 p_full/p_mask 方向。
4. **单次 holdout 无显著性**：所有"领先"都是点估计；没有 seed 平均、没有 bootstrap、
   没有跨窗统计检验 —— 任何"显著/优越"表述都不被支持。
5. **随机基线单次抽样**：random 用固定 seed 一次抽样；同时报告了解析期望 `random_expected`
   作参考，K=1000 时单次抽样与期望差 ~19%（8.6 vs 7.2）。
6. **余额≠流量、计数≠金额**：volume_usd 是 as-of 余额型体量；eth_flow/volume 是事件计数，
   均非美元金额流；不能据此宣称"资本流向"。
7. **选择层≠预测层**：本框架只测"选出的钱包未来效用高不高"，不测端任务（如 next-counterparty
   ranker）的收益；selection-layer 结果不得包装成端任务预测优越性。

## 10. Compute cost

- 全流程本地 CPU 完成：`run_eval.py` ~42s、`robustness_0801.py` ~3s、`make_figures.py` ~2s；
  峰值内存 <2GB（pandas DataFrames）。
- **BigQuery 查询数 = 0**（本次会话未访问 BigQuery；labels 由 Group B 于 09-11 以
  `src/bq_run.py`+分区过滤+bytes 上限拉取，本组只读其落盘结果）。
- 不使用 LLM、不安装新包（仅 pandas/numpy/scikit-learn/matplotlib/pyarrow，均已存在）。

## 11. Novelty（范围声明，不做"没有人做过"式主张）

- **基准形式化**：把"预算化钱包选择"落成可复现的冻结评估协议 —— 一个 cutoff、严格 as-of 打分、
  冻结 top-K、未来窗评估、U(K)/U(K)/K/Recall@K + 全层级基线 + 预算质量前沿；
- **支持集纪律**：full / usd / structural / ig 四类支持集 + 受限共池对比同时报告，避免
  "支持外推"；这是本项目数据契约下的必要新增（Group 0 协议 §5 reporting_rules）；
- **复用冻结产物**：random/volume/activity（Group A）、predictive（Group B frozen predictions）、
  结构（Group C as-of）、IG（Group D）均**未重算**，选择器定义与分数列一一可追溯
  （见 `results/manifest.json`）；
- 本阶段是**基准/证据层**，不是新方法；创新主张留给后续 hybrid/IG 消融与跨窗 walk-forward
  （见 §13 未完成项）。

## 12. 文件清单

```
research/selection_eval/
├── README.md                          # 本文件
├── src/
│   ├── load_data.py                   # 只读加载 + 支持集装配 + 交叉校验
│   ├── selector_defs.py               # 选择器注册表（key/tier/support/score/note）
│   ├── evaluate.py                    # U(K)/U(K)/K/Recall@K/mass/支持集指标
│   ├── run_eval.py                    # 主入口 → results/*.json/csv + manifest
│   ├── make_figures.py                # 前沿/Recall/受限对比/重叠图
│   └── robustness_0801.py             # 08-01 描述性稳健性检查
└── results/
    ├── selection_results_20220901.json # 结构化结果（frontier/restricted/oracle/overlap/支持集/tie 诊断）
    ├── budget_frontier.csv             # 全部选择器 × K 的长表（含受限池）
    ├── manifest.json                   # 选择器支持集与来源 + 泄漏边界
    ├── robustness_0801.json            # 08-01 描述性检查
    └── figures/
        ├── frontier_new_cp.png / frontier_evt_cnt.png / frontier_cp_distinct.png
        ├── frontier_new_mass.png / recall_new_pos_full.png / restricted_comparison.png
        ├── overlap_top100.png / overlap_top1000.png / robustness_0801.png
```

## 13. 未完成项（边界与后续）

1. **跨窗 walk-forward 完整版**：方案 §13 要求多 cutoff；目前仅 09-01 主评 + 08-01 描述性佐证，
   05/06/07 cutoff 的完整选择器（含 predictive/结构/IG）尚未跑（结构/IG 仅有 09-01 产物）。
2. **随机基线的 seed 平均 / 显著性**：当前为固定 seed 单次抽样 + 解析期望；未做 seed 平均、
   bootstrap 或配对检验，不支撑"显著领先"表述。
3. **IG 双向语义与 hybrid 消融**：ig_active 的负例语义已文档化但未做"带符号 IG"变体；
   hybrid_pred_ig 只试了 rank-均值一种组合。
4. **§15 消融**（no-volume / no-network / no-temporal 等）与 §10 影响残差（低量高影响钱包）
   未在本组做，属 Group D/综合组范畴。
5. **K 灵敏度图**：已出 U vs K 与 U/K vs K；§16 要求的 overlap/稳定性随 K 曲线已含
   overlap_top100/1000 两档，未出全 K 网格（数据已在 JSON 中可随时画）。
6. **端任务衔接**：选择层效用未与 Phase-II 推理分配（router/LLM panel）联调；
   "选出的钱包对端任务有多大增益"需要 Group E/F 联合实验。
