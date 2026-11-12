"""Deterministic simulated client replies.

GigSim's signature behaviour: when the freelancer sends a message, the client answers. The reply is
template-based and seeded by (thread_id, reply_index), so the whole conversation is reproducible across
runs and process restarts — no LLM call, no network, no cost. Replies are benign and professional on
purpose; prompt-injection / scam handling is exercised by dedicated fixtures elsewhere, not injected here.
"""
from __future__ import annotations

import hashlib

# Conversation moves roughly through stages as the freelancer and client exchange turns. Each stage
# offers a few interchangeable lines; the seed picks one deterministically.
_STAGES: list[list[str]] = [
    [  # stage 0 - first substantive reply: a clarifying question
        "Thanks for the thoughtful note. Before we go further, how would you approach {skill}?",
        "Appreciate the detail. What is the first milestone you would aim for, and how long would it take?",
        "Good to hear from you. Have you handled {skill} at this scale before? A quick example would help.",
    ],
    [  # stage 1 - commercials / timeline
        "That makes sense. The budget we had in mind is around ${budget}. Does that work for your scope?",
        "Understood. We would want this wrapped within the posted timeline - is that realistic for you?",
        "Helpful, thank you. What would you need from us to get started this week?",
    ],
    [  # stage 2 - moving toward a call
        "This is promising. Could we set up a short call to align on scope?",
        "I like the direction. Are you available for a 20-minute call in the next few days?",
        "Sounds solid. Let's talk live - what times suit you this week?",
    ],
    [  # stage 3+ - wind-down / holding
        "Great - I'll loop in my colleague and come back to you shortly.",
        "Thanks, that covers my questions for now. We'll review and follow up.",
        "Perfect. I'll confirm next steps on our side and be in touch.",
    ],
]


def _pick(options: list[str], thread_id: str, reply_index: int) -> str:
    seed = f"{thread_id}:{reply_index}".encode()
    n = int.from_bytes(hashlib.sha256(seed).digest()[:4], "big")
    return options[n % len(options)]


def client_reply(thread_id: str, reply_index: int, job: dict | None) -> str:
    """Return the client's next line. `reply_index` is how many client replies already exist in the thread."""
    stage = _STAGES[min(reply_index, len(_STAGES) - 1)]
    line = _pick(stage, thread_id, reply_index)
    job = job or {}
    skills = job.get("required_skills") or ["the core work"]
    skill = _pick(list(skills), thread_id, reply_index) if skills else "the core work"
    budget = (job.get("budget") or {}).get("max") or (job.get("budget") or {}).get("min") or 1500
    return line.format(skill=skill, budget=int(budget))
