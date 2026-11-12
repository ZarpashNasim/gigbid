"""Decision + pricing."""
from __future__ import annotations

from ..config import load_prompt
from ..deps import Deps
from ..handoffs import BidDecision, PriceQuote
from .common import done


def _budget_problem(d: Deps, state) -> str | None:
    """Skip jobs paying far below the freelancer's own minimum (profile comes from the user's settings)."""
    prof = d.profiles.get(state.get("user_id"), {})
    b = (state["raw_job"].get("budget") or {})
    hi = b.get("max")
    if not prof or hi is None:
        return None
    if state["raw_job"].get("pricing_type") == "hourly":
        floor = 0.8 * prof.get("hourly_rate_usd", 0)
        return f"hourly budget {hi} below your rate" if floor and hi < floor else None
    floor = 0.8 * prof.get("minimum_project_budget_usd", 0)
    return f"budget {hi} below your minimum {prof['minimum_project_budget_usd']}" if floor and hi < floor else None


def make_decide(d: Deps):
    t = d.cfg["thresholds"]

    def decide(state):
        risk, fit = state["risk"], state["fit"]
        if risk.blocking:
            dec = BidDecision(action="skip", reason=f"risk: {', '.join(risk.flags) or 'blocking flag'}")
        elif (why := _budget_problem(d, state)):
            dec = BidDecision(action="skip", reason=why)
        elif risk.client_score < t["min_client_score"]:
            dec = BidDecision(action="skip", reason=f"low client score {risk.client_score:.2f}")
        elif fit.score >= t["min_fit_to_bid"]:
            dec = BidDecision(action="bid", reason=f"fit {fit.score:.2f}")
        elif fit.score >= t["watch_fit_floor"]:
            dec = BidDecision(action="watch", reason=f"borderline fit {fit.score:.2f}")
        else:
            dec = BidDecision(action="skip", reason=f"low fit {fit.score:.2f}")
        status = "skipped" if dec.action != "bid" else "running"
        return done("decide", 0, decision=dec, status=status)
    return decide


def make_pricing(d: Deps):
    cap = d.cfg["policy"].get("connects_cap_per_bid")

    def pricing(state):
        job, spec = state["raw_job"], state["spec"]
        user = (f"Job budget: {spec.budget_min}-{spec.budget_max}. Floor rate: {job.get('user_floor', 0)}. "
                f"Market stats: {job.get('market_stats', {})}. Connects cost: {job.get('connects_cost', 8)}. "
                f"Connects balance: {d.market.get_connects_balance(state['user_id'])}.")
        quote, tok = d.llm.structured("pricing", PriceQuote, load_prompt("pricing"), user)
        quote.amount = max(quote.amount, float(job.get("user_floor", 0)))  # never below floor
        quote.connects_cost = int(job.get("connects_cost", quote.connects_cost))
        if cap is not None and quote.connects_cost > cap:  # policy-update hook (config only)
            quote.worth_connects = False
            quote.rationale += f" Connects cost exceeds policy cap {cap}."
        status = "running" if quote.worth_connects else "skipped"
        return done("pricing", tok, price=quote, status=status)
    return pricing
