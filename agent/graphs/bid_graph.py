"""Bid graph (C1): hand-written StateGraph.

intake -> [analyst | risk | matcher] (parallel via Send) -> decide
  skip/watch -> END
  bid -> pricing -> writer -> verifier -> critic --(not ok, <=2 loops)--> writer
                                            `--> compliance -> approval (interrupt) -> submit
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..deps import Deps
from ..nodes.analysis import make_analyst, make_intake, make_matcher, make_risk
from ..nodes.approval import make_approval, make_submit
from ..nodes.bid import make_decide, make_pricing
from ..nodes.compliance import make_compliance
from ..nodes.writing import make_critic, make_verifier, make_writer
from ..state import BidState

TERMINAL = {"skipped", "rejected", "blocked", "needs_attention", "dead_letter", "submitted"}


def _guarded(name: str, fn, cfg: dict):
    """C4/C7: step + token budget per thread; exceeding either -> visible 'needs_attention'.
    Node exceptions go to a dead-letter state instead of crashing the thread."""
    b = cfg["budgets"]

    def run(state):
        if state.get("steps", 0) >= b["max_steps_per_thread"] or state.get("tokens", 0) >= b["max_tokens_per_thread"]:
            return {"status": "needs_attention",
                    "trace": [{"node": name, "error": "budget exceeded"}]}
        try:
            return fn(state)
        except GraphBubbleUp:      # interrupt()/control-flow signals must pass through untouched
            raise
        except Exception as exc:  # noqa: BLE001  (real impl: retry/backoff first, then dead-letter)
            return {"status": "dead_letter", "trace": [{"node": name, "error": repr(exc)}]}
    run.__name__ = name
    return run


def build_bid_graph(d: Deps, checkpointer: BaseCheckpointSaver | None = None):
    cfg = d.cfg
    g = StateGraph(BidState)
    nodes = {
        "intake": make_intake(d), "analyst": make_analyst(d), "risk": make_risk(d),
        "matcher": make_matcher(d), "decide": make_decide(d), "pricing": make_pricing(d),
        "writer": make_writer(d), "verifier": make_verifier(d), "critic": make_critic(d),
        "compliance": make_compliance(d), "approval": make_approval(d), "submit": make_submit(d),
    }
    for name, fn in nodes.items():
        g.add_node(name, _guarded(name, fn, cfg))

    def fan_out(state):
        if state.get("status") in TERMINAL:
            return END
        return [Send("analyst", state), Send("risk", state), Send("matcher", state)]

    def proceed(nxt: str):
        return lambda state: END if state.get("status") in TERMINAL else nxt

    def after_critic(state):
        if state.get("status") in TERMINAL:
            return END
        crits = state["critiques"]
        if not crits[-1].ok and len(crits) <= cfg["budgets"]["max_critic_loops"]:
            return "writer"            # bounded: at most 2 send-backs
        return "compliance"

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk", "matcher", END])
    g.add_edge(["analyst", "risk", "matcher"], "decide")   # join: waits for all three
    g.add_conditional_edges("decide", proceed("pricing"), ["pricing", END])
    g.add_conditional_edges("pricing", proceed("writer"), ["writer", END])
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", END])
    g.add_conditional_edges("compliance", proceed("approval"), ["approval", END])
    g.add_conditional_edges("approval", proceed("submit"), ["submit", END])
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer)
