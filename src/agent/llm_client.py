"""Minimal OpenAI-compatible chat client with retry and measured usage.

Reads endpoint config from ~/.codex/config.toml (bearer token kept local,
never logged). No secrets are written to artifacts.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8317/v1")
DEFAULT_MODEL = "glm-5.3"


def _load_bearer():
    path = os.path.expanduser("~/.codex/config.toml")
    try:
        cfg = open(path).read()
        m = re.search(r'experimental_bearer_token\s*=\s*"([^"]+)"', cfg)
        return m.group(1) if m else os.environ.get("LLM_BEARER", "none")
    except FileNotFoundError:
        return os.environ.get("LLM_BEARER", "none")


def chat(messages, model=DEFAULT_MODEL, base_url=DEFAULT_BASE,
         temperature=0.0, max_tokens=900, timeout=120, retries=4,
         reasoning_effort="low"):
    body = {"model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
            "reasoning_effort": reasoning_effort,
            "response_format": {"type": "json_object"}}
    token = _load_bearer()
    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions", data=data,
            headers={"Authorization": "Bearer " + token,
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
            ch = out["choices"][0]["message"]
            usage = out.get("usage", {})
            return {"content": ch.get("content") or "",
                    "usage": usage,
                    "model": out.get("model", model),
                    "latency_s": None}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = repr(e)
            time.sleep(min(2 ** attempt, 10))
    return {"content": "", "usage": {}, "model": model,
            "latency_s": None, "error": last}
