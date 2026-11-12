"""Deterministic risk rules: single source of truth for the agent's rule floor AND the data tooling.

The LLM Risk Assessor can ADD flags, never remove these. Rules are deliberately about intent (instructions aimed at
an AI, requests to move off-platform, unpaid work, upfront money, credentials), not about topic words: a legitimate
job about writing an LLM 'system prompt' must not be flagged. They are blind to obfuscated text on purpose
(e.g. 't e l e g r a m'): that gap is what the LLM assessor is for, and the evaluation measures it.
"""
from __future__ import annotations

import re

SIGNALS: dict[str, list[str]] = {
    "off_platform_contact": [r"whatsapp", r"telegram", r"skype", r"signal app", r"discord", r"\bcontact me (at|on|via)\b",
                             r"outside (of )?(upwork|the platform)", r"external messaging", r"instead of on this platform"],
    "unpaid_work": [r"\bunpaid\b", r"free (sample|trial|test|work)", r"\bfor free\b", r"without pay", r"built for free"],
    "upfront_fee": [r"(pay|send|wire) (a |an )?(small |refundable )?(registration |security )?(fee|deposit|amount)",
                    r"registration fee", r"buy (a )?(license|software) first"],
    "credential_request": [r"(share|send|provide) (your )?(password|login|credentials|otp|bank|one-time code)", r"bank login"],
    "overpayment": [r"\bchec?que\b.{0,60}(forward|deposit|send)"],
    "too_good": [r"no experience (is )?needed", r"earn \$?\d+ (per|a) day"],
    "prompt_injection": [
        r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|polic)",
        r"ignore the (rules|instructions) above",
        r"you are now (the |a )?(client|assistant|system)",
        r"disregard .{0,40}(instructions|polic|rules)",
        r"(reveal|print|output|show) (me )?(your|the) (system )?(prompt|instructions)",
        r"(note|instruction)s? (to|for) (the )?(ai|language model|automated)",
        r"if you are a language model",
        r"ai agents? reading this",
    ],
}
SCAM_KINDS = {"off_platform_contact", "unpaid_work", "upfront_fee", "credential_request", "overpayment", "too_good"}


def detect_signals(text: str) -> list[str]:
    t = text.lower()
    return sorted(k for k, pats in SIGNALS.items() if any(re.search(p, t) for p in pats))
