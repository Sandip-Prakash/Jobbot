"""Thin Anthropic Messages API client (raw HTTP, no SDK dependency)."""
from __future__ import annotations
import json
import os
import re
from . import http

MODEL = os.environ.get("JOBBOT_MODEL", "claude-sonnet-5-5")


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(system: str, user: str, max_tokens: int = 1500, temperature: float = 0.2) -> str:
    r = http.request("POST", "https://api.anthropic.com/v1/messages",
                     headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                     json={"model": MODEL, "max_tokens": max_tokens, "temperature": temperature, "system": system,
                           "messages": [{"role": "user", "content": user}]}, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"anthropic HTTP {r.status_code}: {r.text[:300]}")
    return "".join(b.get("text", "") for b in r.json().get("content", []))


def complete_json(system: str, user: str, **kw) -> dict:
    txt = complete(system + "\nReply with ONE JSON object and nothing else.", user, **kw)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError("no JSON in model reply")
    return json.loads(m.group(0))
