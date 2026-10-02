# Token USD 价格覆盖（2026-09-10）

## 结论

- Kaggle API 可用（`~/.venv-kaggle/bin/kaggle` 2.2.4，`~/.kaggle/access_token`）。
- 已生成可机读 token 价格与映射，并通过 `src/price/prepare_daily_prices.py` 校验。
- 只覆盖 **WETH/USDC/USDT/DAI/APE** 五个 fungible 的 USD 日线；
  LOOKS/WOOL/STRONG/STRNGR/ASH 已有 decimals 映射但无价格；
  大量 NFT（OpenSea storefront、ENS）与长尾 token 无价格。

## 关键文件

- `data/raw/prices/prices_full.csv`：ETH + WETH + USDC + USDT + DAI + APE 日线（窗口 2022-03-01..2022-09-01）。
- `data/raw/prices/token_map.csv`：10 个 fungible 合约地址→symbol/decimals（链上 decimals() 于 block 25947946 读取）。
- `artifacts/prices_v1/price_usd_daily_v1.csv`
- `artifacts/prices_v1/token_price_map_v1.csv`
- `artifacts/prices_v1/manifest.json`
- Kaggle 源：`data/raw/kaggle/coingecko_full/`（sudalairajkumar/cryptocurrency-historical-prices-coingecko）；`data/raw/kaggle/mapping/dataset.csv`（CoinGecko coin list，地址→symbol 参考）。

## 价格覆盖（按 study 窗口 token_transfers 笔数）

BigQuery `token_transfers_20220301_20220901`（target-touching、非 removed）2022-03-01..09-01：

- total_rows = 4,275,544
- priced_rows（WETH/USDC/USDT/DAI/APE）= 238,394（约 5.6%）
- mapped_unpriced_rows（LOOKS/WOOL/STRONG/STRNGR/ASH）= 46,754（约 1.1%）
- opensea_storefront_rows（0x495f…）= 74,311
- ens_rows（0x57f1…）= 71,639

注意：上面的百分比是 **transfer 笔数占比，不是美元价值占比**。主流稳定币+WETH 按金额大概率占大头，
但需要 quantity×price/10^decimals 量化后才能给出金额覆盖率；本阶段尚未做该 join。

## 已明确不做但需后续处理

- LOOKS/WOOL/STRONG/STRNGR/ASH：有 decimals、无 Kaggle 价格 → 暂按 unvalued。
- NFT（OpenSea storefront、ENS 等）：不是 fungible，不能用 token 价格；需 collection floor/sales 数据或单列 unvalued。
- 长尾 token（top60 中除上述外的合约）：无映射、无价格 → unvalued。
