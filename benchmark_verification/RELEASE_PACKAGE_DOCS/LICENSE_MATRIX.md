# License Matrix(逐文件,unknown 保持 unknown)

| 层 | 内容 | 许可 | 依据/备注 |
|---|---|---|---|
| 链上原始事实(地址、交易、日志、金额、时间) | Ethereum 主网公开数据(经声明来源转存) | 事实数据无版权主体;本包以 **CC0 1.0** 分发(作者决定 2026-10-06);转存服务条款(BigQuery)待正式发布前复核一次 | 复核点保留:发布前对 BigQuery 条款做一次只读复核 |
| offline_chain_events_v1_20260929_full | 本项目自建的离线事件表(源自上表) | **CC0 1.0**(事实数据;作者决定 2026-10-06) | 构建脚本记录于仓库;不含第三方衍生内容 |
| external_fresh250/canonical_ledger.parquet | 自建 | **CC0 1.0**(同上) | |
| EX-Graph 衍生物 | **本包不包含** | 作者仓库 CC BY-NC-SA(仅当未来引入时适用) | RELATED_BENCHMARKS.md;不得整包改 MIT |
| 本包 schema/代码(评测器、构建脚本) | 项目原创 | **MIT** | 作者决定 2026-10-06 |
| 文档(本目录) | 项目原创 | **CC BY 4.0** | 作者决定 2026-10-06 |
| grounding gold | automatic labels,项目生成 | **CC BY 4.0**(随文档层;作者决定 2026-10-06) | 人工验证前不宣称 verified |
| Python 依赖 | pandas/pyarrow/numpy 等 | 各自的 OSI 许可(BSD/Apache) | 运行环境记录见 REPRODUCTION_RECEIPT.json |

**规则**:作者 2026-10-06 拍板:代码 **MIT**,文档与 grounding gold **CC BY 4.0**,链上事实数据 **CC0 1.0**。唯一保留复核点:BigQuery 转存条款在正式发布前做一次只读复核。
