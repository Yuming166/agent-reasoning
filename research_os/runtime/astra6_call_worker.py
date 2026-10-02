#!/usr/bin/env python3
"""Single Astra6 HTTP call worker for a parent-enforced hard deadline.

This worker intentionally performs no scientific reasoning locally. It only
loads the already configured Astra6 relay, sends one request, and emits a
machine-readable result to a file. The parent process owns audit logging and
may terminate this process when the absolute deadline is reached.
"""
from __future__ import annotations

import argparse
import json
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path("/home/gaoym/.codex/astra.config.toml")
MODEL = "gpt-6-astra"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_result(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--result-file", required=True)
    ap.add_argument("--max-tokens", type=int, default=2400)
    ap.add_argument("--socket-timeout", type=float, default=420.0)
    args = ap.parse_args()

    result_path = Path(args.result_file)
    started = time.monotonic()
    try:
        cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        provider = cfg.get("model_providers", {}).get("astra", {})
        base_url = str(provider.get("base_url", "")).rstrip("/")
        api_key = str(provider.get("experimental_bearer_token", ""))
        configured_model = str(cfg.get("model", ""))
        if configured_model != MODEL:
            raise RuntimeError(f"configured model mismatch: {configured_model!r}")
        if not base_url.endswith("/v1") or not api_key:
            raise RuntimeError("Astra configuration is incomplete")
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an Astra6 scientific research agent. Do not reveal private chain-of-thought; return only the requested concise report or JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "reasoning_effort": "max",
            "max_tokens": int(args.max_tokens),
        }
        req = urllib.request.Request(
            base_url + "/chat/completions",
            data=canonical(payload).encode("utf-8"),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + api_key)
        with urllib.request.urlopen(req, timeout=float(args.socket_timeout)) as response:
            raw = response.read(8_000_000)
            status = int(response.status)
        data = json.loads(raw)
        returned = data.get("model")
        choices = data.get("choices") or []
        content = ""
        if choices and isinstance(choices[0], dict):
            content = str((choices[0].get("message") or {}).get("content") or "")
        if status != 200 or returned != MODEL or not content.strip():
            raise RuntimeError(
                f"status={status}, returned_model={returned!r}, content={bool(content.strip())}"
            )
        write_result(
            result_path,
            {
                "ok": True,
                "http_status": status,
                "returned_model": returned,
                "content": content,
                "usage": data.get("usage") or {},
                "latency_seconds": round(time.monotonic() - started, 3),
            },
        )
        return 0
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(4096).decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        write_result(
            result_path,
            {
                "ok": False,
                "error": f"http_{exc.code}:{detail[:500]}",
                "latency_seconds": round(time.monotonic() - started, 3),
            },
        )
        return 2
    except Exception as exc:
        write_result(
            result_path,
            {
                "ok": False,
                "error": f"{type(exc).__name__}:{exc}",
                "latency_seconds": round(time.monotonic() - started, 3),
            },
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
