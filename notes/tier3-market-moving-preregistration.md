# Tier3 market-moving event study：预注册协议（冻结版 2026-09-11）

## 目标
回答：选层（Layer B）选出的高影响力钱包，其链上资金流是否在统计上**领先**市场收益？
只允许 temporal-precedence 措辞，不写因果，除非未来加更严识别（DID/外生冲击）。

## 数据口径（as-of）
- 暴露变量：钱包日度净流 `netflow_t = usd_in_t - usd_out_t`
  - `usd_in/out` 口径：native ETH value × 当日 ETH price；priced token（仅 5 个）
    quantity/10^decimals × 当日 token price。NFT/长尾不计价（见 Tier1 边界）。
  - 窗口 2022-03-01..2022-08-31；9 月用于 OOS。
- 结果变量：ETH 日度 log return，`r_{t+h}`，h in {1,3,7}。
- 控制：滞后 ETH return（1 阶）、日活跃钱包数（activity proxy）、星期固定效应；
  可选 Newey-West 调整自相关。

## 预注册检验（单一主检验 + 多重校正）
- 主检验：标准化的市场聚合净流 `zF_t` 对 `r_{t+1}` 的斜率 b1=0 是否被拒绝；
  控制 lag return + day-of-week。
- 报告 Newey-West t、R²、Bonferroni 校正后的拒绝阈值（h 集 {1,3,7} 视为 3 个假设）。
- 探索性（明示 post-hoc）：按 Layer B top-K 影响力子集拆分信号。

## 边界声明
- 若显著：写“观察到所选钱包的聚合净流对 ETH 短期收益有领先相关证据”，
  不写“这些钱包导致/操控市场”。
- 非显著：如实报告，不换窗口/换口径找显著；只记录为 null result。

## 当前暂不进入回归的特征（防未来泄漏）
- `importance_proxy_p3`、`fwd30_*`（未来标签）。
- 任何用未来收益选择钱包的口径。

## 首次结果（2026-09-11，全网聚合净流，未做影响子集）
- 暴露：全映射钱包日度聚合净流 zF_t（in-out，native+5 token）。
- 结果：`r_{t+1}` b=0.313,t=0.97,p=0.332；`r_{t+3}` t=0.67,p=0.501；`r_{t+7}` b=2.27,t=1.74,p=0.083。
- Bonferroni 阈值 0.0167 下全部非显著；R²≤0.029。
- 结论：**全量聚合净流不领先 ETH 短期收益**（h=7 弱正、未达到多重校正显著性）。
- 下一步：按 Layer B 高影响力子集（footprint/I_cf/I_hawk）做 as-of 选择的子集信号，
  这才是“影响力分层是否更有效”的问题，而非全量噪声池。

## 2026-09-11 后续尝试（均诚实记录）
- v2：Layer-B top-100（2022-06-01 as-of，rankavg(market_share,icf)）的 surprise 净流 → ETH excess return；
  h=1 t=0.13、h=3 t=-0.01、h=7 t=-0.06，R²≈0。仍 null。
- v3：top-100 净流截面离散度(daily IQR/MAD) → ETH Parkinson realized vol；
  log(RV_{t+h}) 的 R²≈0.11-0.14，但该 R² 主要来自 lag-RV；dispersion 系数
  h=1 t=0.82、h=3 t=-1.53、h=7 t=1.29，均不显著。
- 结论：日频、粗聚合、~85 个 OOS 日下，未发现钱包流对 ETH 收益/波动的显著领先。
  再在同一框架内换口径即属 p-hacking，停止。

## 2026-09-11 增量3：intraday event-time 事件研究（保留事件时间信息）
- 设计：top-100 影响力钱包、OOS 2022-06-01..08-31、≥$20k 大额流事件(1,097 个)；
  用 1-min ETH close 计算事件后 30/60/180/360 min 的 CAR，day-clustered bootstrap。
- 发现（24 个 forward 检验中）：
  - `native_incoming`：30m -16.4bp (CI[-26.8,-5.7], p=0.002)；60m -24.8bp (CI[-39.2,-9.6], p=0.002)。
    （含义：高footprint钱包收到大额 ETH 后，60 分钟内 ETH 下跌——疑似交易所/枢纽入金→卖压。）
  - `stable_outgoing` 30m -9.5bp (p=0.026)；其余臂/时点不显著。
- 边界：这是 temporal-precedence / 描述性发现，非因果；p≈0.002 在 24 次 Bonferroni 阈值(0.0021)
  附近，需在 9 月 OOS 上做单假设复现 + 钱包类型(exchange vs 非 exchange)标注后才是主结论。
- 下一步：预注册单检验 `native_incoming -> 60min CAR<0`，在 Sept OOS 复现；并取钱包 archetype 标注。

## 2026-09-11 增量4：Sept OOS 单假设复现——失败（如实记录）
- 预注册 H：top-100 影响力钱包 `native_incoming(>=20k USD)` -> 60min CAR < 0。
- Sept OOS n=22 events；car60m = **+13.6bp**（方向反转），one-sided p(mean>=0)=0.83。
- 结论：6-8 月那个 -24.8bp 不敢复现，大概率是时期特异/假阳性。
- 不再对阈值/时点做搜索（否则 p-hacking）。
