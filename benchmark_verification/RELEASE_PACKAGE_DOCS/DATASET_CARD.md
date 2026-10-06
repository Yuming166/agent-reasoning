# Dataset Card:eth-actions-benchmark v1.0.0-candidate

## 概要
- **名称**:eth-actions-benchmark;版本 1.0.0-candidate;构建日期 2026-10-06。
- **任务**:给定链上钱包在日历截止前的本地可见历史,预测未来 7 天内首笔合格外部交易的目标地址;附历史角色绑定事实诊断。
- **域**:Ethereum 主网,2022-03-01 至 2022-06-08 声明来源窗口;1000 抽样钱包、2200 查询。

## 动机与支持机构
研究用途:时序图/语言方法在真实链上行为预测的可追溯评测。无资助机构要求;构建过程见 RELEASE_PROTOCOL.md 与 SOURCE_MANIFEST.json。

## 数据组成
- 每查询:钱包匿名化 id、UTC cutoff、历史父动作引用、实体别名映射(严格历史前缀);
- 父动作行:external/token/internal 行、金额原值(不跨资产相加)、时间、canonical 顺序、回执状态、缺失与 unknown 标记、来源 ledger row ids;
- 答案(gold)隔离存放,由已声明外部来源产生;2200/2200 独立重生成一致;
- grounding gold(TRAIN only):3,755 例,三 scope 分列,**automatic labels**。

## 抽样与已知偏差
- 钱包为 2022 年活跃地址的固定抽样(上游 1000 队列),非全网随机样本;活跃查询占 52.9%;
- 三个历史队列均已探索(v19–v27 开发),不可重命名 fresh;原 400 确认队列因暴露事件整组排除(SPLIT_EXPOSURE_LEDGER.json);
- 共享物理父交易跨钱包 3,912、跨 split 1,934:单独计数,不自动视为泄漏;
- 目标集中度:热门 hub 复用会抬高表观成绩;评分输出含 target_concentration 敏感性。

## 语言/文本
- `action_views` 的 text 字段为**程序模板渲染**(确定性),非自由生成文本;structured 与 text 同语义范围。

## 敏感性与匿名
- 地址是**可链接的公开标识符**;简单 hash 不实现不可逆身份匿名。本包不含真实人身份映射;不含 X/Twitter 社交特征;
- 无个人信息字段;若下游自行链接链外身份,责任在下游。

## 许可
见 LICENSE_MATRIX.md;unknown 保持 unknown,不默认整包 MIT。

## 维护与勘误
勘误流程见 CORRECTIONS_PROCESS.md;联系渠道在正式发布时随发布渠道确定(本候选仅本地)。

## 引用约束
近邻工作与可主张差异以 RELATED_BENCHMARKS.md / CITATION_EVIDENCE.json 为准;不编造首创或录用主张。
