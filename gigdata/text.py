"""Shared text helpers: PII redaction, warning-signal detection, fingerprints."""
from __future__ import annotations

import hashlib
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"https?://\S+|www\.\S+")
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")

from agent.rules import SIGNALS, detect_signals  # noqa: E402,F401  (single source of truth)


def redact(text: str) -> tuple[str, int]:
    """Replace emails, URLs and phone numbers with tokens. Returns (clean text, number of redactions)."""
    n = 0
    for pat, tok in ((EMAIL, "[EMAIL]"), (URL, "[URL]"), (PHONE, "[PHONE]")):
        text, k = pat.subn(tok, text)
        n += k
    return text, n


def fingerprint(title: str, description: str) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", f"{title} {description}".lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()[:20]
