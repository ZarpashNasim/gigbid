"""Client Liaison nodes for the conversation graph (C1): classify -> draft -> compliance -> approval -> send."""
from __future__ import annotations

import hashlib

from langgraph.types import interrupt

from ..config import load_prompt, wrap_untrusted
from ..deps import Deps
from ..handoffs import Approval, MessageIntent, ReplyDraft
from ..memory.promotion_rules import extract_edit_patterns, promote_style, style_rules
from ..rules import detect_signals
from .common import done
from .compliance import check_text


def _last_client_message(state) -> str:
    for m in reversed(state.get("messages", [])):
        if m.get("from") == "client":
            return m["body"]
    return ""


def make_load(d: Deps):
    def load(state):
        return done("load_messages", messages=d.market.list_messages(state["thread_id"]), status="running")
    return load


def make_classify(d: Deps):
    def classify(state):
        text = _last_client_message(state)
        intent, tok = d.llm.structured("intent", MessageIntent, load_prompt("intent"),
                                       wrap_untrusted("client_message", text))
        flags = detect_signals(text)
        if flags:                       # deterministic floor: the LLM can never talk us out of these
            intent.intent = "scam_signal"
            intent.summary += f" [rules: {', '.join(flags)}]"
        return done("classify", tok, intent=intent,
                    status="flagged" if intent.intent == "scam_signal" else "running")
    return classify


def make_draft(d: Deps):
    def draft(state):
        intent = state["intent"]
        slots = d.workspace.free_slots(3) if intent.intent == "interview_request" and d.workspace else []
        convo = "\n".join(f"{m['from']}: {m['body']}" for m in state["messages"][-6:])
        user = (wrap_untrusted("client_message", convo) + f"\nIntent: {intent.intent}"
                + f"\nFree slots: {slots}\nStyle rules: {style_rules(d.store, state['user_id'])}")
        rd, tok = d.llm.structured("liaison", ReplyDraft, load_prompt("liaison"), user)
        rd.proposed_slots = slots                       # slots come from the calendar, never from the model
        return done("draft", tok, draft=rd)
    return draft


def make_conv_compliance(d: Deps):
    def compliance(state):
        v = check_text(d.cfg, state["draft"].body)
        dr = state["draft"].model_copy(update={"body": v.cleaned_cover_letter})
        return done("compliance", compliance=v, draft=dr, status="blocked" if not v.allowed else "running")
    return compliance


def _key(state, body: str) -> str:
    h = hashlib.sha256(f"{state['user_id']}|{state['thread_id']}|{body}".encode()).hexdigest()[:16]
    return f"msg:{state['user_id']}:{state['thread_id']}:{h}"


def make_conv_approval(d: Deps):
    def approval(state):
        dr = state["draft"]
        preview = d.market.send_message(user_id=state["user_id"], thread_id=state["thread_id"], body=dr.body,
                                        idempotency_key=_key(state, dr.body), dry_run=True)
        payload = {"kind": "message_approval", "intent": state["intent"].model_dump(),
                   "draft": dr.model_dump(), "dry_run": preview.model_dump(),
                   "last_client_message": _last_client_message(state)}
        resp = Approval.model_validate(interrupt(payload))     # same gate as proposals; nothing sends before this
        if resp.decision == "reject":
            return done("approval", approval=resp, status="rejected")
        if resp.decision == "edit" and resp.edited_cover_letter:   # field name shared with proposals: edited text
            verdict = check_text(d.cfg, resp.edited_cover_letter)
            promote_style(d.store, state["user_id"],
                          extract_edit_patterns(dr.body, resp.edited_cover_letter),
                          d.cfg["memory"]["style_min_occurrences"])
            if not verdict.allowed:
                return done("approval", approval=resp, compliance=verdict, status="blocked")
            dr = dr.model_copy(update={"body": verdict.cleaned_cover_letter})
            return done("approval", approval=resp, draft=dr, status="running")
        return done("approval", approval=resp, status="running")
    return approval


def make_conv_send(d: Deps):
    def send(state):
        dr = state["draft"]
        res = d.market.send_message(user_id=state["user_id"], thread_id=state["thread_id"], body=dr.body,
                                    idempotency_key=_key(state, dr.body), dry_run=False)
        if d.workspace:                                  # tentative holds for the slots we offered (idempotent)
            for s in dr.proposed_slots:
                d.workspace.create_hold(s, f"Interview ({state['thread_id']})", f"hold:{state['thread_id']}:{s}")
        return done("send", sent_id=res["message_id"], status="sent")
    return send
