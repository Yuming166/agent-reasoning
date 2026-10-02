"""Minimal OpenAI-compatible chat client with retry and measured usage.

Reads endpoint from LLM_BASE_URL, defaulting to the approved Qwen service.
Bearer token is kept local and never logged. No secrets are written to artifacts.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://10.63.0.82:31518/v1"
DEFAULT_MODEL = "Qwen3.5-4B"


def _load_bearer():
    return os.environ.get("LLM_BEARER", "")


def chat(messages, model=DEFAULT_MODEL, base_url=None,
         temperature=0.0, max_tokens=900, timeout=120, retries=4,
         reasoning_effort="low"):
    base_url = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE).strip()
    endpoint = urllib.parse.urlsplit(base_url)
    if endpoint.hostname == "10.63.0.72" and endpoint.port == 8317:
        raise ValueError("This LLM endpoint is prohibited for project use.")
    if (endpoint.scheme not in ("http", "https") or not endpoint.hostname
            or endpoint.hostname.endswith(".invalid")):
        raise ValueError("Set LLM_BASE_URL to an approved LLM endpoint before running.")
    body = {"model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}}
    # Some Qwen/vLLM deployments interpret reasoning_effort=low as enabling
    # hidden thinking. With the frozen 700-token budget that can consume the
    # entire completion and leave no JSON content. Qwen requests therefore
    # omit the optional field by default; an explicit environment value still
    # overrides this (use LLM_REASONING_EFFORT= to omit it explicitly).
    if "LLM_REASONING_EFFORT" in os.environ:
        configured_reasoning_effort = os.environ["LLM_REASONING_EFFORT"] or None
    elif model == DEFAULT_MODEL or str(model).lower().startswith("qwen"):
        configured_reasoning_effort = None
    else:
        configured_reasoning_effort = reasoning_effort
    if configured_reasoning_effort:
        body["reasoning_effort"] = configured_reasoning_effort
    token = _load_bearer()
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions", data=data,
            headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
            choice = out["choices"][0]
            ch = choice["message"]
            usage = out.get("usage", {})
            return {"content": ch.get("content") or "",
                    "usage": usage,
                    "model": out.get("model", model),
                    "finish_reason": choice.get("finish_reason"),
                    "reasoning_nonempty": bool(ch.get("reasoning") or ch.get("reasoning_content")),
                    "latency_s": None}
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = repr(e)
            time.sleep(min(2 ** attempt, 10))
    return {"content": "", "usage": {}, "model": model,
            "latency_s": None, "error": last}
