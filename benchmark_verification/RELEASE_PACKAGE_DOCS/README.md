# FACTS (eth-actions-benchmark v1.0.0-candidate) — 发布文档

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
