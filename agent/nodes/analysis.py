"""Scout intake + the three parallel analysis nodes (Analyst, Risk, Matcher)."""
from __future__ import annotations

import re

from ..config import load_prompt, wrap_untrusted
from ..deps import Deps
from ..handoffs import FitGrade, FitReport, JobSpec, RequirementMatch, RiskReport
from .common import done

from ..rules import SCAM_KINDS, detect_signals  # noqa: E402


def make_intake(d: Deps):
    def intake(state):
        job = d.market.get_job(state["job_id"])
        return done("intake", raw_job=job, status="running")
    return intake


def make_analyst(d: Deps):
    def analyst(state):
        job = state["raw_job"]
        user = wrap_untrusted("job_post", f"{job['title']}\n{job['description']}")
        spec, tok = d.llm.structured("analyst", JobSpec, load_prompt("analyst"), user)
        spec.job_id = state["job_id"]
        return done("analyst", tok, spec=spec)
    return analyst


def make_risk(d: Deps):
    def risk(state):
        job = state["raw_job"]
        text = f"{job['title']}\n{job['description']}"
        history = d.market.get_client_history(job.get("client_id", ""))
        user = wrap_untrusted("job_post", text) + f"\nClient history: {history}"
        rep, tok = d.llm.structured("risk", RiskReport, load_prompt("risk"), user)
        # deterministic floor: the LLM can add flags, never remove ours
        sig = detect_signals(text)
        rep.injection_detected |= "prompt_injection" in sig
        rep.off_platform_ask |= "off_platform_contact" in sig
        rep.free_work_request |= "unpaid_work" in sig
        rep.scam |= bool(set(sig) & (SCAM_KINDS - {"off_platform_contact", "unpaid_work"}))
        rep.flags += [f"rule:{k}" for k in sig]
        return done("risk", tok, risk=rep)
    return risk


def naive_requirements(job: dict) -> list[str]:
    """Matcher runs in parallel with the Analyst, so it derives requirements itself from
    structured fields / sentences (trade-off: parallel speed vs. using the Analyst's JobSpec)."""
    if job.get("requirements"):
        return list(job["requirements"])
    return [s.strip() for s in re.split(r"[.\n;]", job["description"]) if len(s.split()) >= 3][:6]


def make_matcher(d: Deps):
    thr = d.cfg["thresholds"].get("lexical_support", 0.25)

    def matcher(state):
        job = state["raw_job"]
        reqs = naive_requirements(job)
        # past proposals are the freelancer's own claims, not verified evidence: never use them to support a claim
        cands = [[e for e in d.retriever.search(r, k=6) if e.type != "proposal"][:4] for r in reqs]
        grades, tokens = {}, 0
        if any(cands):
            listing = "\n".join(f"REQ {i}: {r}\n" + "\n".join(f"  [{e.id}] ({e.type}) {e.text[:300]}" for e in ev)
                                for i, (r, ev) in enumerate(zip(reqs, cands)))
            try:
                fg, tokens = d.llm.structured("matcher", FitGrade, load_prompt("matcher"),
                                              wrap_untrusted("job_post", listing))
                grades = {g.index: g for g in fg.grades}
            except Exception:  # noqa: BLE001  grader unavailable -> conservative lexical fallback below
                grades = {}
        matches = []
        for i, (r, ev) in enumerate(zip(reqs, cands)):
            if grades:
                g = grades.get(i)
                if g is not None and not g.is_requirement:
                    continue                                   # boilerplate does not count against the fit score
                ok = {x for x in (g.supported_ids if g else [])} & {e.id for e in ev}   # ignore invented ids
                ev = [e for e in ev if e.id in ok]
            else:
                from rag.variants.v8_corrective import supports   # fallback: keyword overlap (strict, misses paraphrase)
                ev = [e for e in ev if supports(r, e, thr)]
            matches.append(RequirementMatch(requirement=r, evidence=ev, covered=bool(ev)))
        score = sum(m.covered for m in matches) / len(matches) if matches else 0.0
        reasons = [f"{'covered' if m.covered else 'MISSING'}: {m.requirement}" for m in matches]
        return done("matcher", tokens, fit=FitReport(score=score, matches=matches, reasons=reasons))
    return matcher
