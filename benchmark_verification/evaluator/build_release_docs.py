#!/usr/bin/env python
"""Stage F part 1: assemble the local release package (README, dataset card,
license matrix, known limitations, AI-use disclosure, corrections process).

Everything is written into artifacts/benchmark_release_candidate_v1_20261006/
RELEASE_PACKAGE_DOCS/. Claims follow RELATED_BENCHMARKS.md/CITATION_EVIDENCE.json;
unknown licenses stay unknown; no first-of-its-kind or acceptance claims.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path("/storage/gaoym/ex-graph-microtransaction-analysis/artifacts/benchmark_release_candidate_v1_20261006")
DOCS = OUT / "RELEASE_PACKAGE_DOCS"


def w(path, text):
    p = DOCS / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "x") as f:
        f.write(text)
    print("wrote", path)


def main():
    if DOCS.exists():
        raise SystemExit("exists")

    w("README.md", """# eth-actions-benchmark v1.0.0-candidate(本地发布候选)

**状态:本地发布候选,未公开发布,人工审查未完成。** 本目录是 `VERSIONED_DATASET/` 的说明与合同;评分器见 `../SCORER_VALIDATION.json` 与代码 `research/benchmark_release_candidate_v1_20261006/`。

## 任务
查询 q = (wallet, UTC cutoff)。给定严格 `timestamp < cutoff` 的历史(父动作行、角色证据、unknown 标记),预测 `[cutoff, cutoff+7天)` 内第一笔合格、由钱包发起的 external ATTEMPT 的 `to` 地址:
- qualifying:非 null/空/全零、非 self;**attempted 口径**(失败回执保留;不做成功/金额过滤);canonical (block_number, transaction_index, event_index) 顺序;
- 两个评测入口:**retrieval**(合法 first-seen 域内检索,≤50 个不同合法对象)与 **fixed_pool**(完整排序同一冻结参考 50);
- 四类结果分列:域外 / 域内未入 50 / 50 内未入 5 / 5 内;非法与缺失预测计失败;
- 历史事实 grounding(role/owner/latest binding)三 scope 分列评价;UNKNOWN 是状态,不是父动作 id。

## 数据规模
| split | 钱包 | 查询 | 活跃 | cutoff |
|---|---:|---:|---:|---|
| train | 600 | 1800 | 985 | 2022-05-01/03/05 |
| dev | 150 | 150 | 84 | 2022-05-15 |
| external test | 250 | 250 | 95 | 2022-06-01 |

标签窗口与预测 cutoff 一一对应;gold 由原外部来源产生并独立重生成核对 2200/2200(EXPORT_VALIDATION.json)。

## 目录
```
VERSIONED_DATASET/
  queries/{train,dev,test}.jsonl              # 无答案标记的查询
  parent_actions/{split}.jsonl.gz             # 观察到的父动作行(含来源出处)
  action_views/{split}.jsonl.gz               # per (query,parent) 结构化+文本同语义视图
  candidate_index/legal_domain_index.jsonl.gz # 共享 first-seen 合法域索引(451,742 端点)
  candidate_index/legal_domain_{split}.jsonl.gz
  reference_pools/reference_top50_{split}.jsonl # 冻结参考池(train=v27lean;dev/test=pending)
  forecast_gold/{split}.jsonl                 # 隔离的预测 gold
  grounding_gold/train.jsonl                  # 隔离的 grounding gold(automatic labels)
  gold_crosswalk/{split}.jsonl                # gold-only 目标↔池成员对照
```

## 使用
1. 读 `queries/`,历史输入只用 `parent_actions/`、`action_views/`、`candidate_index/`;
2. 方法输出:每查询 ≤50 个不同地址(检索 track 要求全部合法;固定池 track 必须完整同池);
3. 用 `evaluator`(research/benchmark_release_candidate_v1_20261006/benchmark_evaluator.py)评分;gold 目录不进入方法输入;
4. 引用结果时保留 denominator(全部合格活跃查询)与 track 语义,不得混合两 track 的数字。

## 状态限制(发布前必须保留)
- 三个历史队列均已探索,不得称 fresh/未探索;
- 原 400 确认队列不在本包内;
- grounding gold 是 automatic labels,人工验证 pending;
- dev/test 无冻结角色参考池(fixed_pool 不可用);
- 统一 schema ≠ 统一语义覆盖(DEV/TEST 无角色包)。
""")

    w("DATASET_CARD.md", """# Dataset Card:eth-actions-benchmark v1.0.0-candidate

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
""")

    w("LICENSE_MATRIX.md", """# License Matrix(逐文件,unknown 保持 unknown)

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
""")

    w("KNOWN_LIMITATIONS.md", """# 已知限制(发布前必须随包展示)

1. **探索状态**:train/dev/test 三个队列都经过 v19–v27 开发使用;任何结果都是开发筛查,不是独立确认。原 400 确认队列因 root 暴露事件整组排除(EXPOSURE_EVENT.json)。
2. **语义覆盖不均**:统一 schema 下,可信本钱包角色包仅 TRAIN 有(30,494/53,024);DEV 0/13,411、TEST 0/25,270。角色方法跨 split 的表现差异首先是来源覆盖差异。
3. **标签=声明来源窗口内事实**:inactive 仅表示声明来源窗口内无合格外部动作,不是钱包终身不活跃;legal domain 是声明来源 first-seen 域,不是全部以太坊。
4. **attempted 口径**:失败回执计入合格动作;与"仅成功交易"协议的结果不可直接比较。
5. **参考池是方法产物**:v27lean 冻结池含截止后不可见地址(fixed_pool 下合法);两 track 数字不可混用。
6. **共享目标/日历依赖**:热门目标跨查询复用;钱包聚类 bootstrap 是名义区间,共享事件仍跨钱包依赖,非多重校正后的结论。
7. **automatic labels**:grounding gold 未人工验证;机器与程序文本渲染需注明来源。
8. **地址可链接性**:地址是公开可链接标识;hash 不构成匿名化。
9. **时间边界**:全部数据 2022-03–2022-06;不支撑跨周期、跨链或当前市场状态的结论。
10. **单种子基线**:已发布基线为 seed0 开发筛查;不含多种子稳定性证据。
""")

    w("AI_USE_DISCLOSURE.md", """# AI 使用说明

- 本数据集候选由 Claude Code(GLM/Anthropic CLI 会话)在人类授权与协议约束下构建:读取冻结记录、写构建/评分脚本、执行校验并撰写文档;所有构建决策遵循 RELEASE_PROTOCOL.md 与 handoff 合同。
- **数据本体**是 2022 年以太坊公开链上事实,与 AI 无关;AI 未生成任何链上内容。
- `action_views` 的 text 字段为程序模板渲染(确定性代码输出),逐条在 `structured_and_text_semantic_scope` 声明;数据集中无自由生成的机器文本。
- grounding gold 为**程序自动标签**;Claude 或其他模型的判断未被记为人工审查;人工一致率字段全部为空,等待真实人类标注(阶段 E 材料)。
- 已有模型诊断(v27lean locator)来自本项目训练的 Qwen3.5-4B 定位器,在 RESULTS.json 冻结;其输入接口与限制见原记录。
""")

    w("CORRECTIONS_PROCESS.md", """# 勘误流程(候选)

1. **发现**:任何用例发现数据/标签/文档错误,先在本地记录:涉及文件、查询/例 id、复现步骤、建议修正。
2. **分级**:
   - A 类(gold 错误、泄漏、窗口错位):立即冻结受影响 split 的评测;修正需重跑 EXPORT_VALIDATION 并在 EXPORT_VALIDATION 追加修订记录(不改写原记录);
   - B 类(文档/描述错误):修订文档并登记;
   - C 类(格式/可用性):登记并排期。
3. **登记**:所有勘误进入本目录 `ERRATA.md`(尚未创建——首个勘误出现时创建),append-only;不覆盖既有文件。
4. **版本**:数据修正使版本号升 minor(1.1.0);文档修正升 patch(1.0.1);每次修订重算文件 sha256。
5. **公开**:正式发布后,勘误随发布渠道公告;本候选阶段仅本地登记。
""")

    print("release docs written")


if __name__ == "__main__":
    main()
