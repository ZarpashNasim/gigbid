"""LLM access. Nodes depend on the `LLM` protocol, never on a vendor.

`OpenAICompatLLM` works with OpenRouter, Groq and Ollama (all OpenAI-compatible).
Model per node comes from config routing; cheap nodes fall back to `fallback_small` on error.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .config import model_for

_RETRY_AFTER = re.compile(r"try again in ([\d.]+)\s*s", re.I)

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def structured(self, node: str, schema: type[T], system: str, user: str) -> tuple[T, int]:
        """Return (parsed object, tokens used)."""


class OpenAICompatLLM:
    def __init__(self, cfg: dict):
        from openai import OpenAI  # lazy: only needed outside tests

        self.cfg = cfg
        p = cfg["profiles"][cfg["active_profile"]]
        self.profile = p
        # We pace 429s ourselves (see _create) because the SDK's own retry does not reliably wait out Groq's
        # tokens-per-minute limit on the free tier; max_retries=0 avoids double-handling.
        self.max_rl_waits = p.get("max_rate_limit_waits", 12)
        self.client = OpenAI(base_url=p["base_url"], api_key=os.environ.get(p["api_key_env"], "none"),
                             max_retries=0, timeout=p.get("timeout_s", 90))

    def _create(self, **kw):
        """chat.completions.create, but on a 429 sleep for the server-suggested interval and retry (free-tier TPM)."""
        for _ in range(self.max_rl_waits):
            try:
                return self.client.chat.completions.create(**kw)
            except Exception as e:                                   # noqa: BLE001
                msg = str(e)
                if "429" not in msg and "rate limit" not in msg.lower():
                    raise
                m = _RETRY_AFTER.search(msg)
                time.sleep(min((float(m.group(1)) + 0.3) if m else 5.0, 65.0))
        return self.client.chat.completions.create(**kw)            # last try: let the error propagate if still limited

    def _call(self, model: str, schema: type[T], system: str, user: str) -> tuple[T, int]:
        resp = self._create(
            model=model,
            messages=[
                {"role": "system", "content": system + "\nReply with JSON only matching this schema:\n"
                 + json.dumps(schema.model_json_schema())},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        text = resp.choices[0].message.content or "{}"
        tokens = resp.usage.total_tokens if resp.usage else 0
        return schema.model_validate_json(text), tokens

    def structured(self, node: str, schema: type[T], system: str, user: str) -> tuple[T, int]:
        model = model_for(self.cfg, node)
        try:
            return self._call(model, schema, system, user)
        except Exception:
            if self.cfg["routing"][node] == "small":  # fallback model for cheap nodes (C7)
                return self._call(self.profile["fallback_small"], schema, system, user)
            raise
