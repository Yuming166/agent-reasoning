# 影响力三档：落地现状与边界（2026-09-10）

## Tier 1 参与规模/体量 —— 已落地（as-of、防泄漏）

产物：`artifacts/influence_v1/wallet_influence_v1.csv`（冻结，每 snapshot 每钱包一行）。

列（均严格用 snapshot 前 90 天，`[snap-90d, snap)`）：
- 规模/体量：`native_usd`、`token_usd_priced`、`total_usd`、`market_share_usd`；
- 活动口径（复用 wallet_asof_features）：`evt_cnt_90d`、`evt_out_90d`、`evt_native_90d`、
  `evt_token_90d`、`active_days_90d`、`tx_cnt_90d`、`cp_distinct_90d`、`cp_out_distinct_90d`、`token_distinct_90d`；
- token USD 覆盖率（笔数）：`token_rows`、`token_rows_priced`、`token_usd_coverage`。

USD 口径：
- native：ETH 转账 value(wei)/1e18 × ETH 日线。
- token：仅 WETH/USDC/USDT/DAI/APE 五个，`quantity/10^decimals × 日线 price`；
  NFT 与长尾 token 不计价。

market_share 分母 = 同一 snapshot 全部映射钱包的 `total_usd` 合计（零流出地址自然贡献 0）。

### 各 snapshot 汇总
| snap | 钱包数(有事件) | total USD | token 行价格覆盖率 |
|---|---|---|---|
| 2022-06-01 | 20341 | 2.94B | 9.5% |
| 2022-07-01 | 19734 | 1.98B | 10.0% |
| 2022-08-01 | 19062 | 1.12B | 10.9% |
| 2022-09-01 | 18519 | 0.66B | 12.7% |

## Tier 2 结构/传播影响 —— 已引入，标注为 proxy

- P1 `icf_score_p1` / `bridges_events`：来自 `p1_wallet_icf_v2`（按 snapshot，as-of 可用）。
- P2 `trigger_score_p2` / `trigger_pairs` / `trigger_total_vol`：来自 `wallet_trigger_proxy_v1`，
  只按地址、单一窗口（Jul 附近），**不是 snapshot 序列**，只能当时间领先相关 proxy。

二者都不是因果影响力，不进入任何“市场导向”结论。

## Tier 3 市场导向/因果影响 —— 仅设计，未执行

需单独做 event-study：
- 处理变量：目标钱包日度净流出/净流入（可用 native_usd 与 5 个 priced token 近似，明确口径）。
- 结果变量：价格收益（暂时只用 ETH；若做 token 则需 token 价格，已限制为 5 个）。
- 设计：`flow_{i,t} -> ret_{t+h}` 面板回归 / 事件研究，控制市场因子，多假设校正，
  并在可交易时滞与换手成本下报告；先冻结协议再评估，避免事后挑窗。
- 边界：P1/P2/体量都不等于市场导向，禁止据此宣称“影响市场走向”。

## 已明确不做/未覆盖

- NFT（OpenSea storefront、ENS）与长尾 token 无 USD 价。
- token 行价格覆盖 ~9-13%，是“笔数覆盖率”，不是“金额覆盖率”。
- P2 非 snapshot 序列。
- Tier 3 尚未跑。

## 2026-09-11 增量：Tier2 P2 v2 + 分层结论

- 已建成 `artifacts/influence_v1/p2_trigger_proxy_v2.csv`（14,970 行，4 snapshot，
  as-of 90d，daily lag-1 Hawkes 相关，bytesBilled 1.39GB）。
- post-hoc 用冻结 Aug 1000 events 审计：
  - trigger_score_p2_v2 与 gain_full 的 Spearman = -0.047，与 learned = -0.055；
  - 50/50 融合只在 5% 预算 +0.0107，其余预算为负。
- 结论（重要）：**Tier2 影响力不是“节点该不该花 deliberation 预算”的信号**，
  它的正确位置是“该钱包对该市场重不重要”的投资 cohort 层（与 Tier1/Tier3 同层）。
  因此论文应做成两层 selection：
  Layer A = budgeted deliberation router（预测增益，learned，已 GO）；
  Layer B = influence-aware investment cohort（footprint + I_cf + I_hawk + Tier3 因果）。
- 下一步：P1 v2（真实 cheap-model 遮挡重评分 I_cf）落在 Layer B，单独评估，
  不再塞进 Layer A 的 ΔMRR router。

## 2026-09-11 增量2：P1 v2-alpha + 稳健结论

- 已建成 `artifacts/influence_v1/p1_icf_v2alpha_candidate_occlusion.csv`
  （leave-one-out candidate occlusion，真实 cheap-model 重评分，3,407 钱包）。
- 冻结 Aug 审计：I_cf v2alpha 与 gain_full 的 Spearman = -0.020，与 learned = -0.089；
  50/50 融合几乎不改变 learned 曲线（±0.005 内）。
- 三个 Tier2 变体（P1-graph、P1-candidate-occlusion、P2-Hawkes）一致表明：
  **Tier2 影响力与“deliberation 增益”正交**。因此 Tier2 不进入 Layer A router，
  而是 Layer B 市场影响力 cohort 的组成成分，需和 Tier3 的市场结果一起评估。
