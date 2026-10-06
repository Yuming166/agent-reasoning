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
| `SCORING_V27LEAN_TRAIN.json` | 冻结基线重评分(fixed_pool + retrieval 双轨) |
| `CLAIM_EVIDENCE_MATRIX.md` | 8 可主张 / 5 pending / 8 不可主张 |
| `NLP_VALIDITY_PLAN_AND_AVAILABLE_RESULTS.md` | NLP 有效性:已有 automatic 结果 vs pending 计划 |
| `SPLIT_EXPOSURE_LEDGER.json` | split 探索状态台账(400 队列排除记录) |
| `REPRODUCTION_RECEIPT.json` | 洁净室搬迁复现回执(passed) |
| `STAGE_STATUS.json` | 六阶段 A–F 状态与证据 |
| `evaluator/` | 评分器 + 全部构建/评分/复现脚本 |
| `annotation_pack/` | 盲审指南 + 未执行预算方案。pilot20 工作表含链上视图数据,按纪律仅本地分发(不进公开仓库);标注结果文件回传后计算一致性 |
| `RELEASE_PACKAGE_DOCS/` | README / DATASET_CARD / LICENSE_MATRIX / KNOWN_LIMITATIONS / AI_USE_DISCLOSURE / CORRECTIONS_PROCESS |

## 需要作者验证的最小集

1. ~~License 选择~~ **已决定(2026-10-06):代码 MIT、文档与 grounding gold CC BY 4.0、链上事实数据 CC0 1.0**
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
