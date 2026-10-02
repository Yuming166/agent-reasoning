# Qwen Embedding 端点 + BigQuery 客户端就绪（2026-09-11）

## Gap 2: Qwen3-Embedding OpenAI 兼容端点（端口 31522）

- 模型：`/storage/lianjh/modelzoos/Qwen/Qwen3-Embedding-0.6B`（本地权重，无下载流量）。
- 服务：`src/embed/serve_qwen_embedding.py`，`run_embed_server.sh` 启动，tmux session `embed-qwen`，
  GPU3（`CUDA_VISIBLE_DEVICES=3`），占用约 1.5GB 显存。
- 端点：`http://127.0.0.1:31522/v1/models`、`/v1/embeddings`（OpenAI 兼容）。
- 实现：官方 last-token pooling + L2 normalize（与 Qwen3-Embedding README 一致），bf16，支持 str/list[str]。
- 实测：dim=1024，相似文本 cos=1.0、不同文本 0.68，向量 L2 归一化，返回 usage tokens。
- 管理：`tmux attach -t embed-qwen`；`tmux kill-session -t embed-qwen` 停止；
  重启 `bash run_embed_server.sh > logs/embed_server_31522.log 2>&1`。
- 说明：这是 Qwen3-Embedding 系列（非 Qwen3.5-4B chat），满足 Group E "Qwen latent representation"。
  若需更强质量可换 4B（同目录 Qwen3-Embedding-4B），改 MODEL_PATH 与端口即可。
- 注意：Qwen3.5-4B chat 服务（31518）仍无 /v1/embeddings，本次新增的是独立 embedding 服务。

## Gap 1: google-cloud-bigquery 客户端（.venv-cuda）

- 安装：`.venv-cuda/bin/pip install "google-cloud-bigquery>=3.30"` -> 3.45.0。
- 使用：本机外网 HTTPS 必须走代理，否则 client 会直连卡死：
  ```bash
  export HTTPS_PROXY=http://10.63.0.72:7890 HTTP_PROXY=http://10.63.0.72:7890
  export GOOGLE_APPLICATION_CREDENTIALS=/home/gaoym/.config/gcloud/application_default_credentials.json
  ```
- 实测：`get_table` 返回 external_transactions 2,877,009 行；带 `maximum_bytes_billed=1e9` 的
  2022-08-01 单日 COUNT 查询返回 11,356 行，bytes_billed=10,485,760（约 10MB），端到端可用。
- 原则不变：事件表只物化在 BigQuery，查询需分区过滤 + bytes-billed 上限，不整表导出。
