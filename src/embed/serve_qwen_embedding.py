#!/usr/bin/env python
"""OpenAI-compatible /v1/embeddings server for Qwen3-Embedding.

Serves Qwen3-Embedding-0.6B (local path) with last-token pooling + L2
normalization, matching the official Qwen3-Embedding README recipe.

Usage:
  CUDA_VISIBLE_DEVICES=3 .venv-cuda/bin/python src/embed/serve_qwen_embedding.py \
      --host 0.0.0.0 --port 31522
"""
import argparse
import time
from typing import Union

import torch
import torch.nn.functional as F
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
from transformers import AutoModel, AutoTokenizer

MODEL_PATH = "/storage/lianjh/modelzoos/Qwen/Qwen3-Embedding-0.6B"
MODEL_ID = "Qwen3-Embedding-0.6B"

app = FastAPI(title="Qwen3-Embedding local server")
_model = None
_tokenizer = None
_device = None


class EmbeddingRequest(BaseModel):
    model: str = MODEL_ID
    input: Union[str, list[str]] = Field(...)
    encoding_format: str = "float"  # only float supported
    dimensions: int | None = None   # not supported for Qwen3-Embedding


def last_token_pool(last_hidden_states: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
    if left_padding:
        return last_hidden_states[:, -1]
    sequence_lengths = attention_mask.sum(dim=1) - 1
    batch_size = last_hidden_states.shape[0]
    return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]


def load_model() -> None:
    global _model, _tokenizer, _device
    if _model is not None:
        return
    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[embed-server] loading {MODEL_PATH} on {_device}", flush=True)
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    _tokenizer.padding_side = "left"
    _model = AutoModel.from_pretrained(MODEL_PATH, torch_dtype=torch.bfloat16, trust_remote_code=True)
    _model.to(_device)
    _model.eval()
    print(f"[embed-server] model loaded on {next(_model.parameters()).device}", flush=True)


@app.on_event("startup")
def startup() -> None:
    load_model()


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [
        {"id": MODEL_ID, "object": "model", "created": int(time.time()), "owned_by": "local"}
    ]}


@app.post("/v1/embeddings")
def embed(req: EmbeddingRequest):
    texts = req.input if isinstance(req.input, list) else [req.input]
    if not texts:
        raise HTTPException(status_code=400, detail="input must not be empty")
    if len(texts) > 128:
        raise HTTPException(status_code=400, detail="batch too large; max 128")
    if req.encoding_format not in ("float",):
        raise HTTPException(status_code=400, detail="only encoding_format=float supported")
    with torch.inference_mode():
        encoded = _tokenizer(texts, padding=True, truncation=True, max_length=32768, return_tensors="pt")
        input_ids = encoded["input_ids"].to(_device)
        attn = encoded["attention_mask"].to(_device)
        hidden = _model(input_ids=input_ids, attention_mask=attn).last_hidden_state
        pooled = last_token_pool(hidden, attn)
        pooled = F.normalize(pooled, p=2, dim=1)
        emb = pooled.float().cpu().tolist()
    tokens = int(encoded["input_ids"].numel())
    return {
        "object": "list",
        "data": [{"object": "embedding", "index": i, "embedding": emb[i]} for i in range(len(texts))],
        "model": req.model,
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=31522)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
