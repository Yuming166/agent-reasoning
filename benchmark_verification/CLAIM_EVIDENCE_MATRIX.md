# Claim–Evidence Matrix(候选)

日期:2026-10-06。每条可能的主张对应其证据文件与当前状态。规则:证据不存在或 pending 的主张,标注为**不可主张**。

## 可主张(有本地证据,措辞受限)

| # | 主张(允许的措辞) | 证据 | 限定 |
|---|---|---|---|
| C1 | 构建了 2200 查询/1000 钱包的导出包,输入无答案标记,相对路径,无 pickle | EXPORT_VALIDATION.json (status=passed); QUALITY_AUDIT.json (all hard checks passed) | 仅本地候选;未公开发布 |
| C2 | gold 与冻结标签一致:独立重生成 2200/2200(逐字段) | EXPORT_VALIDATION.json; build_dataset_part2.py 记录 | 标签本身仍是声明来源窗口内事实 |
| C3 | 评测器按合同工作:15 项合成合同测试通过;fixed_pool 逐分支复现冻结 RESULTS.json(5/5);独立重算一致 | SCORER_VALIDATION.json; SCORING_V27LEAN_TRAIN.json; selftest 输出 | 复现的是冻结开发数字,非新方法成绩 |
| C4 | 钱包聚类配对诊断(rescue/harm/净命中/点估计/CI 端点)与冻结记录一致(7 组对比) | SCORING_V27LEAN_TRAIN_DIAGNOSTICS.json (verdict true) | 名义开发区间;非多重校正 |
| C5 | retrieval track 语义正确实现且给出新诊断:330/1800 冻结预测含截止后不可见地址,fail-closed | SCORING_V27LEAN_TRAIN.json retrieval + notes | 是更严格门下的新数字,不覆盖冻结记录 |
| C6 | 语义覆盖缺口被量化:角色包 train 30494 / dev 0 / test 0;unknown 记账规则落实 | SEMANTIC_COVERAGE.json; QUALITY_AUDIT.json coverage | 0=来源缺位,不代表无角色关系 |
| C7 | 盲审材料就绪且无泄漏:20 钱包 pilot(115 grounding + 60 窗口),人类字段全空;预算方案(200+80)未执行 | ANNOTATION_PACK/; 泄漏检查输出(本会话) | 人工审查 pending,无人工数据 |
| C8 | 本地洁净室复现:临时目录+隔离进程+相对路径,评分/重算/自检全部一致 | REPRODUCTION_RECEIPT.json (reproduction_passed=true) | **不是**外部第三方复现 |

## Pending(材料就绪但需人工/外部步骤)

| # | 事项 | 阻塞点 |
|---|---|---|
| P1 | grounding gold 的人工验证 | 无人工标注;automatic labels 不得称 verified |
| P2 | dev/test 的 fixed_pool 基线 | 无冻结角色参考池(reference_pools 标 pending) |
| P3 | 逐例 grounding 基线评分 | 冻结 v27lean 只有聚合诊断,无逐例预测;重跑方法超出阶段预算 |
| P4 | 许可矩阵逐项确认 | LICENSE_MATRIX.md 多项 unknown/pending 人工决定 |
| P5 | 公开发布 | 无上传/push;发布渠道与联系点未定 |

## 不可主张(证据不支持)

| # | 禁止的主张 | 原因 |
|---|---|---|
| N1 | 首个区块链/以太坊语言理解或时序预测 benchmark | RELATED_BENCHMARKS.md 近邻分析;无系统综述 |
| N2 | 独立确认/新时间泛化/fresh test | 三队列均已探索;400 队列被排除 |
| N3 | 预测证据/可解释性 100% | locator 完整父动作 exact=1.0 是闭包任务性质 |
| N4 | 稳定 NLP/语言证据增益 | 单种子开发筛查,种子效应不稳定(v27lean 记录) |
| N5 | 已有人工验证或人工一致率 | 人类字段全空 |
| N6 | 已公开发布或已获外部复现 | 本地候选;REPRODUCTION_RECEIPT 明示范围 |
| N7 | 简单 hash 实现身份匿名 | 地址可链接 |
| N8 | 跨周期/跨链/当前市场结论 | 数据 2022-03–06 |
