"""R4/C5: human approval via interrupt(), then a separate submit node.

The submit side effect lives in its OWN node. A node that calls interrupt() is re-executed from
its start on resume, so putting submit after the interrupt in the same node would be fragile.
Submission also carries an idempotency key, so even a replayed submit cannot double-send (C6).
"""
from __future__ import annotations

import hashlib

from langgraph.types import interrupt

from ..deps import Deps
from ..handoffs import Approval
from ..memory.promotion_rules import extract_edit_patterns, promote_style
from .common import done
from .compliance import check_text


def _key(state, letter: str) -> str:
    h = hashlib.sha256(f"{state['user_id']}|{state['job_id']}|{letter}".encode()).hexdigest()[:16]
    return f"bid:{state['user_id']}:{state['job_id']}:{h}"


def make_approval(d: Deps):
    def approval(state):
        draft, price = state["draft"], state["price"]
        # dry_run is read-only, so re-running it after resume is safe
        preview = d.market.create_proposal_draft(
            user_id=state["user_id"], job_id=state["job_id"], cover_letter=draft.cover_letter,
            amount=price.amount, answers=draft.screening_answers,
            idempotency_key=_key(state, draft.cover_letter), dry_run=True)
        payload = {
            "kind": "proposal_approval",
            "draft": draft.model_dump(),
            "claims_evidence": [c.model_dump() for c in draft.claims],
            "risk": state["risk"].model_dump(),
            "price_rationale": price.rationale,
            "critic_open_issues": state["critiques"][-1].issues if state.get("critiques") else [],
            "dry_run": preview.model_dump(),
        }
        resp = Approval.model_validate(interrupt(payload))   # <- graph pauses here, state in checkpointer

        if resp.decision == "reject":
            return done("approval", approval=resp, status="rejected")
        if resp.decision == "edit" and resp.edited_cover_letter:
            verdict = check_text(d.cfg, resp.edited_cover_letter)  # edits are re-checked by Compliance
            patterns = extract_edit_patterns(draft.cover_letter, resp.edited_cover_letter)
            promote_style(d.store, state["user_id"], patterns, d.cfg["memory"]["style_min_occurrences"])
            if not verdict.allowed:
                return done("approval", approval=resp, compliance=verdict, status="blocked")
            draft = draft.model_copy(update={"cover_letter": verdict.cleaned_cover_letter})
            return done("approval", approval=resp, draft=draft, status="running")
        return done("approval", approval=resp, status="running")
    return approval


def make_submit(d: Deps):
    def submit(state):
        draft, price = state["draft"], state["price"]
        res = d.market.create_proposal_draft(
            user_id=state["user_id"], job_id=state["job_id"], cover_letter=draft.cover_letter,
            amount=price.amount, answers=draft.screening_answers,
            idempotency_key=_key(state, draft.cover_letter), dry_run=False)
        return done("submit", submission_id=res["submission_id"], status="submitted")
    return submit
