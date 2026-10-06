# License Matrix(逐文件,unknown 保持 unknown)

| 层 | 内容 | 许可 | 依据/备注 |
|---|---|---|---|
| 链上原始事实(地址、交易、日志、金额、时间) | Ethereum 主网公开数据(经声明来源转存) | 上游条款:BigQuery public-data crypto_ethereum 数据集条款(公开可得、按"原样") | 链上事实本身无版权主体;转存服务条款适用于其分发物;未验证条款全文前标 **unknown-pending-review** |
| offline_chain_events_v1_20260929_full | 本项目自建的离线事件表(源自上表) | 未单独设许可;随包分发时建议 CC0(事实数据)——**pending 人工决定** | 构建脚本记录于仓库;不含第三方衍生内容 |
| external_fresh250/canonical_ledger.parquet | 自建 | 同上 pending | |
| EX-Graph 衍生物 | **本包不包含** | 作者仓库 CC BY-NC-SA(仅当未来引入时适用) | RELATED_BENCHMARKS.md;不得整包改 MIT |
| 本包 schema/代码(评测器、构建脚本) | 项目原创 | **pending 人工决定**(候选:MIT/Apache-2.0/CC-BY-4.0);在决定前按"保留所有权利"处理 | 不默认开源 |
| 文档(本目录) | 项目原创 | 同上 pending | |
| grounding gold | automatic labels,项目生成 | 随整包;pending | 人工验证前不宣称 verified |
| Python 依赖 | pandas/pyarrow/numpy 等 | 各自的 OSI 许可(BSD/Apache) | 运行环境记录见 REPRODUCTION_RECEIPT.json |

**规则**:在逐项许可确认前,本包不声明任何 SPDX 整包标识;"unknown" 是显式状态,不是疏漏。
