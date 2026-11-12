"""LLM access. Nodes depend on the `LLM` protocol, never on a vendor.

`OpenAICompatLLM` works with OpenRouter, Groq and Ollama (all OpenAI-compatible).
Model per node comes from config routing; cheap nodes fall back to `fallback_small` on error.
"""
from __future__ import annotations

import json
import os
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .config import model_for

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
        self.client = OpenAI(base_url=p["base_url"], api_key=os.environ.get(p["api_key_env"], "none"))

    def _call(self, model: str, schema: type[T], system: str, user: str) -> tuple[T, int]:
        resp = self.client.chat.completions.create(
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
