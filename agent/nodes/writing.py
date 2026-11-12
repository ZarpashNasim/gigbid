"""Proposal Writer, claim Verifier (B3) and Critic."""
from __future__ import annotations

import re

from pydantic import BaseModel

from ..config import load_prompt, wrap_untrusted
from ..deps import Deps
from ..handoffs import Claim, Critique, EvidenceItem, ProposalDraft
from ..memory.promotion_rules import style_rules
from .common import done


def _evidence(state) -> list[EvidenceItem]:
    seen: dict[str, EvidenceItem] = {}
    for m in state["fit"].matches:
        for e in m.evidence:
            seen[e.id] = e
    return list(seen.values())


def _fmt_evidence(items: list[EvidenceItem]) -> str:
    return "\n".join(f"[{e.id}] ({e.type}, outcome={e.outcome}) {e.text}" for e in items)


def make_writer(d: Deps):
    def writer(state):
        job, spec = state["raw_job"], state["spec"]
        prior = state.get("critiques", [])
        issues = prior[-1].issues if prior else []
        user = (wrap_untrusted("job_post", f"{job['title']}\n{job['description']}")
                + f"\nPrice: {state['price'].amount}\nEvidence:\n{_fmt_evidence(_evidence(state))}"
                + f"\nStyle rules: {style_rules(d.store, state['user_id'])}"
                + f"\nScreening questions: {spec.screening_questions}"
                + f"\nCritique issues to fix: {issues}")
        draft, tok = d.llm.structured("writer", ProposalDraft, load_prompt("writer"), user)
        draft.revision = len(prior)
        return done("writer", tok, draft=draft)
    return writer


class _Claims(BaseModel):
    claims: list[Claim]


def make_verifier(d: Deps):
    def verifier(state):
        draft = state["draft"]
        ev = _evidence(state)
        user = f"Cover letter:\n{draft.cover_letter}\n\nEvidence:\n{_fmt_evidence(ev)}"
        res, tok = d.llm.structured("verifier", _Claims, load_prompt("verifier"), user)
        valid_ids = {e.id for e in ev}
        letter = draft.cover_letter
        for c in res.claims:
            c.evidence_ids = [i for i in c.evidence_ids if i in valid_ids]
            if c.status == "supported" and not c.evidence_ids:
                c.status = "unsupported"  # a 'supported' claim must point at real evidence
            if c.status == "unsupported":
                letter = re.sub(re.escape(c.text) + r"\s*", "", letter)  # remove before Critic sees it
        draft = draft.model_copy(update={"cover_letter": letter.strip(), "claims": res.claims})
        unsupported = sum(c.status == "unsupported" for c in res.claims)
        out = done("verifier", tok, draft=draft)
        out["trace"][0]["out"] = {"claims": len(res.claims), "unsupported_removed": unsupported}
        return out
    return verifier


def make_critic(d: Deps):
    def critic(state):
        draft = state["draft"]
        user = (f"Draft:\n{draft.cover_letter}\nClaims: {[c.model_dump() for c in draft.claims]}\n"
                f"Word limit: {d.cfg['policy']['max_cover_letter_words']}")
        crit, tok = d.llm.structured("critic", Critique, load_prompt("critic"), user)
        return done("critic", tok, critiques=[crit])
    return critic
