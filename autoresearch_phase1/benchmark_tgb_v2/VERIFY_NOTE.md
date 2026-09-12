# 独立复跑确认（2026-09-12，Codex 主线程）

- 命令：`python tgb_mlp2.py --eval-split test --tag v3b --device cuda:5 --eval-only`
  （tmux session verify-tgb；日志 `logs/verify_v3b_test_run3.log`）
- 结果：test MRR = **0.8550222516059875**，与原 `tgb_mlp2_v3b_test_results.json` **逐位一致**（确定性评估）。
- MRR 轨迹与原报告一致：0.8024 → 0.8501 → 0.8489 → 0.8486 → ... → 0.8550。
- 判定：可复现。对比 TPNet 0.832±0.001（活榜单 2026-09-11 引用）= +0.023。
- 边界：本地官方协议评估（官方 split/evaluator/负采样），**非官方榜单提交回执**；需正式提交才能称"榜单击败"。
