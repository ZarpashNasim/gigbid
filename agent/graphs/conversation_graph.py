"""Conversation graph (C1): one thread per client conversation. Same approval gate as the bid graph.

load -> classify --scam_signal--> END (flagged, nothing drafted)
              `--> draft -> compliance -> approval (interrupt) -> send
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..deps import Deps
from ..nodes.liaison import (make_classify, make_conv_approval, make_conv_compliance, make_conv_send,
                             make_draft, make_load)
from ..state import ConvState
from .bid_graph import TERMINAL, _guarded

CONV_TERMINAL = TERMINAL | {"flagged", "sent"}


def build_conversation_graph(d: Deps, checkpointer=None):
    g = StateGraph(ConvState)
    nodes = {"load": make_load(d), "classify": make_classify(d), "draft": make_draft(d),
             "compliance": make_conv_compliance(d), "approval": make_conv_approval(d), "send": make_conv_send(d)}
    for name, fn in nodes.items():
        g.add_node(name, _guarded(name, fn, d.cfg))

    def go(nxt):
        return lambda s: END if s.get("status") in CONV_TERMINAL else nxt

    g.add_edge(START, "load")
    g.add_edge("load", "classify")
    g.add_conditional_edges("classify", go("draft"), ["draft", END])
    g.add_edge("draft", "compliance")
    g.add_conditional_edges("compliance", go("approval"), ["approval", END])
    g.add_conditional_edges("approval", go("send"), ["send", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer)
