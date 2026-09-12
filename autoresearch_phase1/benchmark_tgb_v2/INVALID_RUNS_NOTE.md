# 无效运行说明（审计留档，不计入结论）

以下版本因实现 bug 判无效，保留 .pt/.json 仅作审计证据；有效结论见 TGB2_REPORT.md §4。

| 版本 | 无效原因 |
|---|---|
| v1a/v1b/v1c/v1d | build_train_data 标签与行未对齐（块序 y vs 交错 X），约一半样本标签错位 → 模型无法学习（val MRR 0.19-0.40） |
| v2a | decay 特征用全局 cumsum 相减，训练期灾难性消去 → pair_decay 训练恒≈0、test 真实 → 训练/test 分布不一致，test MRR 从 0.83 崩溃至 0.47（v2a val 0.8325 亦基于部分损坏特征，一并无效） |

修复后（v3 系列）：
- 标签：X 按块序 [pos…, neg…] 与 y 对齐
- decay：按组（node/pair）累积和，无全局相减（随机数据与真实数据均与暴力计算 0 误差）
- reverse-pair 越界：searchsorted 结果加掩码

v3a/v3b 为有效结果（val 0.8347/0.8373，test 0.8525/0.8550）。
