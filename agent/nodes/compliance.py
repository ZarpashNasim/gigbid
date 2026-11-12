"""Compliance Guard: deterministic policy-pack enforcement. Rules come from config (change-request ready)."""
from __future__ import annotations

import re

from ..deps import Deps
from ..handoffs import ComplianceVerdict
from .common import done

EMAIL = r"[\w.+-]+@[\w-]+\.[\w.]+"
PHONE = r"\+?\d[\d\s().-]{8,}\d"
OFF_PLATFORM = r"(whatsapp|telegram|skype|pay(ment)? outside|contact me at)"
GUARANTEE = r"(guarantee[sd]?|100% (satisfaction|success)|risk[- ]free)"


def check_text(cfg: dict, text: str) -> ComplianceVerdict:
    pol = cfg["policy"]
    violations: list[str] = []
    cleaned = text
    if re.search(EMAIL, cleaned) or re.search(PHONE, cleaned):
        violations.append("contact details removed")
        cleaned = re.sub(EMAIL, "[removed]", cleaned)
        cleaned = re.sub(PHONE, "[removed]", cleaned)
    blocking = False
    if pol.get("forbid_off_platform") and re.search(OFF_PLATFORM, cleaned, re.I):
        violations.append("off-platform request")
        blocking = True
    if pol.get("forbid_guarantees") and re.search(GUARANTEE, cleaned, re.I):
        violations.append("guarantee language")
        blocking = True
    if len(cleaned.split()) > pol["max_cover_letter_words"]:
        violations.append(f"over {pol['max_cover_letter_words']} words")
        blocking = True
    for rule in pol.get("extra_rules", []):  # {"name":..., "pattern":...} added via config only
        if re.search(rule["pattern"], cleaned, re.I):
            violations.append(rule["name"])
            blocking = True
    return ComplianceVerdict(allowed=not blocking, violations=violations, cleaned_cover_letter=cleaned)


def make_compliance(d: Deps):
    def compliance(state):
        v = check_text(d.cfg, state["draft"].cover_letter)
        draft = state["draft"].model_copy(update={"cover_letter": v.cleaned_cover_letter})
        return done("compliance", 0, compliance=v, draft=draft,
                    status="blocked" if not v.allowed else "running")
    return compliance
