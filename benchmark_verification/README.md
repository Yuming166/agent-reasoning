# benchmark_verification — eth-actions-benchmark v1.0.0-candidate 验证包

**用途**:ARR October 2026(截稿 2026-10-12)投稿的 benchmark contribution 验证材料。
**状态**:本地发布候选;**未公开发布**;人工审查 pending。本目录是工作验证副本,不是正式发布物。

## 目录

| 文件/目录 | 内容 |
|---|---|
| `GAP_TO_PAPER.md` | **先读这个**:距文章级的差距清单 + 需要作者拍板的 6 项决策 |
| `RELEASE_PROTOCOL.md` | 冻结的任务定义/窗口/域对象/统计单位合同 |
| `QUALITY_AUDIT.json` | 自动效度审计(全部硬检查通过) |
| `SEMANTIC_COVERAGE.json` | 语义覆盖缺口(角色包 train 30494 / dev 0 / test 0) |
| `SCORER_VALIDATION.json` | 评分器验证(15 合同测试;fixed_pool 复现冻结结果 5/5 分支) |
| `EXECUTABLE_SEMANTICS_VALIDATION.json` | grounding gold 可执行语义验证:L1 回程解析 + L2 双实现重执行,全部 3755/3755;变异测试 3/3 |
| `BASELINES_RETRIEVAL.json` | 三个免训练基线(频率/最近性/随机合法域)× 三 split,同一评测器 retrieval 轨;random_legal 0 命中为期望模态结果(E[hits]≈0.09) |
| `SCORING_V27LEAN_TRAIN.json` | 冻结基线重评分(fixed_pool + retrieval 双轨) |
| `scoring/` | 钱包聚类配对诊断 + bootstrap CI(含首次缺陷跑的存档与 NOTICE) |
| `DATASET_MANIFEST.json` | 数据集契约:标签定义/split 统计/暴露/隔离/单位 |
| `EXPORT_VALIDATION.json` | 导出校验(status=passed;gold 独立重生成 2200/2200) |
| `SOURCE_MANIFEST.json` | 41 个声明来源(链上转存口径) |
| `FINAL_RELEASE_PREP_REPORT.json` | 六阶段收尾报告:50 个交付文件哈希 |
| `CLAIM_EVIDENCE_MATRIX.md` | 9 可主张 / 4 pending / 8 不可主张 |
| `NLP_VALIDITY_PLAN_AND_AVAILABLE_RESULTS.md` | NLP 有效性:已有 automatic 结果 vs pending 计划 |
| `SPLIT_EXPOSURE_LEDGER.json` | split 探索状态台账(400 队列排除记录) |
| `REPRODUCTION_RECEIPT.json` | 洁净室搬迁复现回执(passed) |
| `STAGE_STATUS.json` | 六阶段 A–F 状态与证据 |
| `evaluator/` | 评分器 + 全部构建/评分/复现脚本 |
| `annotation_pack/` | 盲审指南 + 未执行预算方案。pilot20 工作表含链上视图数据,按纪律仅本地分发(不进公开仓库);标注结果文件回传后计算一致性 |
| `RELEASE_PACKAGE_DOCS/` | README / DATASET_CARD / LICENSE_MATRIX / KNOWN_LIMITATIONS / AI_USE_DISCLOSURE / CORRECTIONS_PROCESS |

## 需要作者验证的最小集

1. ~~License 选择~~ **已决定(2026-10-06):代码 MIT、文档与 grounding gold CC BY 4.0、链上事实数据 CC0 1.0**
2. ~~人工 pilot~~ **已由可执行语义验证替代主路径**(EXECUTABLE_SEMANTICS_VALIDATION.json):逐例标注降级为可选增强;剩余人工=书面规范审阅(~30 分钟)
2. dev/test fixed_pool 主张口径((a) 仅 train 或 (b) 补冻结)
3. 审稿期匿名发布渠道
4. 20-wallet 人工 pilot 启动(≥30 例)
5. 频率/最近性/随机基线是否进主表
6. 数据集 bibtex 定名

## 复现

```bash
python evaluator/benchmark_evaluator.py selftest   # 15 项合同测试
```
(基线重评分需冻结 PREDICTIONS.npz,见 SCORER_VALIDATION.json 的输入哈希)

## 双盲注意

本仓库与作者身份关联。**审稿期内不要**将本 URL 写进投稿;匿名材料另行准备。
