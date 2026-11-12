"""R7: long-term memory is written ONLY through these rules. Raw tool output never enters memory.

Style memory: an edit pattern from the user's diffs is promoted only after it recurs
`style_min_occurrences` times (so one-off edits don't become rules).
Outcome memory: per job category win/reply counts; a category "lesson" is exposed only after
`outcome_min_samples` outcomes.
"""
from __future__ import annotations

import re

from langgraph.store.base import BaseStore

BANNED_WORD_CANDIDATES = ["passionate", "excited", "guarantee", "dear sir", "i am writing"]


def extract_edit_patterns(original: str, edited: str) -> list[str]:
    """Turn a draft->edit diff into candidate rules (deterministic, auditable)."""
    patterns: list[str] = []
    o_sents = re.split(r"(?<=[.!?])\s+", original.strip())
    e_text = edited.lower()
    if o_sents and o_sents[0].lower() not in e_text and len(o_sents) > 1:
        patterns.append("cut the first sentence")
    for w in BANNED_WORD_CANDIDATES:
        if w in original.lower() and w not in e_text:
            patterns.append(f"never say '{w}'")
    if len(edited.split()) < 0.8 * len(original.split()):
        patterns.append("keep proposals shorter")
    return patterns


def promote_style(store: BaseStore, user_id: str, patterns: list[str], min_occurrences: int) -> list[str]:
    """Count candidates; promote those that reach the threshold. Returns newly promoted rules."""
    promoted: list[str] = []
    for p in patterns:
        key = re.sub(r"\W+", "_", p)
        cand = store.get(("style_candidates", user_id), key)
        count = (cand.value["count"] if cand else 0) + 1
        store.put(("style_candidates", user_id), key, {"rule": p, "count": count})
        if count >= min_occurrences and not store.get(("style", user_id), key):
            store.put(("style", user_id), key, {"rule": p, "evidence_count": count})
            promoted.append(p)
    return promoted


def style_rules(store: BaseStore, user_id: str) -> list[str]:
    return [i.value["rule"] for i in store.search(("style", user_id))]


def record_outcome(store: BaseStore, user_id: str, category: str, outcome: str) -> None:
    """outcome: won | replied | ignored. Only aggregated counters are stored."""
    cur = store.get(("outcome", user_id), category)
    v = cur.value if cur else {"won": 0, "replied": 0, "ignored": 0}
    v[outcome] = v.get(outcome, 0) + 1
    store.put(("outcome", user_id), category, v)


def outcome_lesson(store: BaseStore, user_id: str, category: str, min_samples: int) -> dict | None:
    cur = store.get(("outcome", user_id), category)
    if not cur:
        return None
    n = sum(cur.value.values())
    if n < min_samples:
        return None
    return {"samples": n, "reply_rate": (cur.value["won"] + cur.value["replied"]) / n}
