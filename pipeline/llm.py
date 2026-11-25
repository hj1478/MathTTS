#!/usr/bin/env python3
"""Shared OpenAI chat plumbing for the eval scripts (inbox judge, dot_check).

One JSON-mode chat call with retries; config comes from .env / environment
(same keys as inbox_eval.py documents: OPENAI_API_KEY / _MODEL / _BASE_URL).
"""
import json
import os
import sys
import time

import requests

from tts_probe import load_dotenv


def openai_cfg(model_flag=None):
    load_dotenv()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set (put it in .env or the environment), "
                 "or rerun with --no-llm for pipeline + lint only.")
    return {"key": key,
            "model": model_flag or os.environ.get("OPENAI_MODEL", "gpt-4o"),
            "base": os.environ.get("OPENAI_BASE_URL",
                                   "https://api.openai.com/v1").rstrip("/")}


def chat_json(cfg, system, user, tag, temperature=None):
    """One JSON-object chat completion. Returns (parsed dict, "") on success,
    (None, error_string) after 3 failed attempts (5xx/429/malformed JSON)."""
    body = {"model": cfg["model"],
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    if temperature is not None:
        body["temperature"] = temperature
    last = ""
    for attempt in range(1, 4):  # transient 5xx/429/malformed JSON; back off,
        if attempt > 1:          # OpenAI 500s often need a few seconds to clear
            time.sleep(5 * attempt)
        try:
            r = requests.post(cfg["base"] + "/chat/completions",
                              headers={"Authorization": f"Bearer {cfg['key']}"},
                              json=body, timeout=180)
            if r.status_code != 200:
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                continue
            data = json.loads(r.json()["choices"][0]["message"]["content"])
            if not isinstance(data, dict):
                last = f"model returned JSON {type(data).__name__}, not object"
                continue
            return data, ""
        except (requests.RequestException, KeyError, ValueError, TypeError) as e:
            last = f"{type(e).__name__}: {e}"
    return None, f"LLM call failed for {tag} after 3 attempts — {last}"
