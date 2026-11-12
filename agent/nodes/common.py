"""Shared node helpers: trace entry + step accounting."""
from __future__ import annotations

from typing import Any


def done(node: str, tokens: int = 0, **update: Any) -> dict:
    """Standard node return: state update + one audit trace row + step/token accounting."""
    summary = {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in update.items()
               if k in ("spec", "risk", "fit", "decision", "price", "compliance")}
    return {**update, "steps": 1, "tokens": tokens, "trace": [{"node": node, "tokens": tokens, "out": summary}]}
