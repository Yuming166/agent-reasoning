#!/bin/bash
# Qwen3-Embedding-0.6B OpenAI-compatible embeddings server with GPUs 0,1,2 visible, port 31522.
set -euo pipefail
cd /storage/gaoym/ex-graph-microtransaction-analysis
export CUDA_VISIBLE_DEVICES=0,1,2
exec .venv-cuda/bin/python src/embed/serve_qwen_embedding.py --host 0.0.0.0 --port 31522
