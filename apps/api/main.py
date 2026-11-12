"""FastAPI backend: starts bid runs, streams progress (SSE), lists and resolves approvals.

Approvals resume the interrupted LangGraph thread. Pending approvals live in the checkpointer,
so a page refresh or an API restart never loses one.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import ConfigDict, Field

from agent.handoffs import BaseModel

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.handoffs import (Approval, BidDecision, ComplianceVerdict, Critique, FitReport, JobSpec,
                            MessageIntent, PriceQuote, ProposalDraft, ReplyDraft, RiskReport)
from apps.api.events import EventLog


class InlineExecutor:
    """Runs work immediately (tests, simple dev). Production uses a real pool / worker process."""
    def submit(self, fn, *a, **kw):
        fn(*a, **kw)


class StartRun(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)


class RunInfo(BaseModel):
    thread_id: str
    job_id: str
    status: str | None = None
    waiting_for_approval: bool = False


class RunDetail(BaseModel):
    info: RunInfo
    job: dict | None = None
    spec: JobSpec | None = None
    risk: RiskReport | None = None
    fit: FitReport | None = None
    decision: BidDecision | None = None
    price: PriceQuote | None = None
    draft: ProposalDraft | None = None
    compliance: ComplianceVerdict | None = None
    critiques: list[Critique] = Field(default_factory=list)


class StartConversation(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64, description="Marketplace conversation id")


class ConvDetail(BaseModel):
    info: RunInfo
    messages: list[dict] = Field(default_factory=list)
    intent: MessageIntent | None = None
    draft: ReplyDraft | None = None
    compliance: ComplianceVerdict | None = None


class PendingApproval(BaseModel):
    thread_id: str
    job_id: str
    payload: dict


class ApprovalIn(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edited_cover_letter: str | None = None
    reason: str | None = Field(default=None, max_length=500)


def create_app(deps, checkpointer, tokens: dict[str, str], registry_path: str = ":memory:",
               events: EventLog | None = None, executor=None) -> FastAPI:
    app = FastAPI(title="GigBid API")
    # CORS so the browser web app can call the API cross-origin. Auth is a bearer header (not cookies),
    # so "*" is safe here; set CORS_ORIGINS (comma-separated) to lock it to the web URL in production.
    _origins = os.environ.get("CORS_ORIGINS", "*")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if _origins.strip() == "*" else [o.strip() for o in _origins.split(",") if o.strip()],
        allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
    )
    graph = build_bid_graph(deps, checkpointer)
    conv_graph = build_conversation_graph(deps, checkpointer)

    def G(thread_id: str):
        """Conversation threads are namespaced 'conv:'; everything else is a bid thread."""
        return conv_graph if thread_id.startswith("conv:") else graph
    events = events or EventLog()
    executor = executor or InlineExecutor()

    def run_and_log(thread_id: str, graph_input) -> None:
        """Drive the graph with stream_mode='updates' and persist each node update as an event."""
        cfg = {"configurable": {"thread_id": thread_id}}
        try:
            for chunk in G(thread_id).stream(graph_input, cfg, stream_mode="updates"):
                for node, update in chunk.items():
                    events.append(thread_id, "node", {"node": node, "update": update})
        except Exception as exc:  # noqa: BLE001
            events.append(thread_id, "error", {"error": repr(exc)})
        snap = G(thread_id).get_state(cfg)
        waiting = bool(snap.next and snap.tasks and snap.tasks[0].interrupts)
        events.append(thread_id, "end", {"status": snap.values.get("status"), "waiting_for_approval": waiting})
    db = sqlite3.connect(registry_path, check_same_thread=False)   # tenant registry: thread -> user, job
    db.execute("create table if not exists runs (thread_id text primary key, user_id text, job_id text)")

    def current_user(authorization: str = Header(default="")) -> str:
        user = tokens.get(authorization.removeprefix("Bearer ").strip())
        if not user:
            raise HTTPException(401, "invalid token")
        return user

    def owned(thread_id: str, user: str) -> tuple[str, str]:
        row = db.execute("select user_id, job_id from runs where thread_id=?", (thread_id,)).fetchone()
        if not row or row[0] != user:       # tenant scoping: other users' threads look nonexistent
            raise HTTPException(404, "run not found")
        return row

    def info(thread_id: str, job_id: str) -> RunInfo:
        snap = G(thread_id).get_state({"configurable": {"thread_id": thread_id}})
        return RunInfo(thread_id=thread_id, job_id=job_id, status=snap.values.get("status"),
                       waiting_for_approval=bool(snap.next and snap.tasks and snap.tasks[0].interrupts))

    @app.post("/runs", response_model=RunInfo)
    def start_run(body: StartRun, user: str = Depends(current_user)):
        # Idempotent per (user, job): one thread per job, so a double click never double-analyses.
        thread_id = f"{user}:{body.job_id}"
        if not db.execute("select 1 from runs where thread_id=?", (thread_id,)).fetchone():
            db.execute("insert into runs values (?,?,?)", (thread_id, user, body.job_id))
            db.commit()
            executor.submit(run_and_log, thread_id, {"user_id": user, "job_id": body.job_id})
        return info(thread_id, body.job_id)

    @app.get("/runs", response_model=list[RunInfo])
    def list_runs(user: str = Depends(current_user)):
        rows = db.execute("select thread_id, job_id from runs where user_id=? and thread_id not like 'conv:%'",
                          (user,)).fetchall()
        return [info(t, j) for t, j in rows]

    @app.get("/runs/{thread_id}", response_model=RunDetail)
    def run_detail(thread_id: str, user: str = Depends(current_user)):
        """Everything the job-detail and proposal-studio screens need, in one typed payload."""
        _, job_id = owned(thread_id, user)
        v = G(thread_id).get_state({"configurable": {"thread_id": thread_id}}).values
        return RunDetail(info=info(thread_id, job_id), job=v.get("raw_job"), spec=v.get("spec"),
                         risk=v.get("risk"), fit=v.get("fit"), decision=v.get("decision"),
                         price=v.get("price"), draft=v.get("draft"), compliance=v.get("compliance"),
                         critiques=v.get("critiques", []))

    @app.get("/runs/{thread_id}/trace")
    def trace(thread_id: str, user: str = Depends(current_user)):
        owned(thread_id, user)
        snap = G(thread_id).get_state({"configurable": {"thread_id": thread_id}})
        return {"trace": snap.values.get("trace", [])}

    @app.get("/runs/{thread_id}/stream")
    def stream(thread_id: str, user: str = Depends(current_user), timeout_s: float = 120.0):
        """SSE: replays stored events, then tails live until the run ends (or pauses for approval)."""
        owned(thread_id, user)

        def gen():
            last, deadline = 0, time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                for eid, kind, data in events.after(thread_id, last):
                    last = eid
                    yield f"id: {eid}\nevent: {kind}\ndata: {data}\n\n"
                    if kind == "end":
                        return
                time.sleep(0.05)
            yield "event: timeout\ndata: {}\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/approvals", response_model=list[PendingApproval])
    def pending(user: str = Depends(current_user)):
        out = []
        for t, j in db.execute("select thread_id, job_id from runs where user_id=?", (user,)).fetchall():
            snap = G(t).get_state({"configurable": {"thread_id": t}})
            if snap.next and snap.tasks and snap.tasks[0].interrupts:
                out.append(PendingApproval(thread_id=t, job_id=j, payload=snap.tasks[0].interrupts[0].value))
        return out

    @app.post("/approvals/{thread_id}", response_model=RunInfo)
    def resolve(thread_id: str, body: ApprovalIn, user: str = Depends(current_user)):
        _, job_id = owned(thread_id, user)
        cfg = {"configurable": {"thread_id": thread_id}}
        snap = G(thread_id).get_state(cfg)
        if not (snap.next and snap.tasks and snap.tasks[0].interrupts):
            raise HTTPException(409, "nothing pending for this run")      # double-approve is a no-op
        Approval.model_validate(body.model_dump())
        run_and_log(thread_id, Command(resume=body.model_dump()))
        return info(thread_id, job_id)

    # ---------------- conversations (Client Liaison graph) ----------------
    @app.post("/conversations", response_model=RunInfo)
    def start_conversation(body: StartConversation, user: str = Depends(current_user)):
        """Draft a reply to the newest client message. One thread per conversation; re-running after the
        previous cycle finished handles a new client message, but never while an approval is pending."""
        cid = f"conv:{user}:{body.thread_id}"
        row = db.execute("select 1 from runs where thread_id=?", (cid,)).fetchone()
        if not row:
            db.execute("insert into runs values (?,?,?)", (cid, user, body.thread_id))
            db.commit()
        if not row or not info(cid, body.thread_id).waiting_for_approval:
            executor.submit(run_and_log, cid, {"user_id": user, "thread_id": body.thread_id})
        return info(cid, body.thread_id)

    @app.get("/conversations", response_model=list[RunInfo])
    def list_conversations(user: str = Depends(current_user)):
        rows = db.execute("select thread_id, job_id from runs where user_id=? and thread_id like 'conv:%'",
                          (user,)).fetchall()
        return [info(t, j) for t, j in rows]

    @app.get("/conversations/{conv_id}", response_model=ConvDetail)
    def conversation_detail(conv_id: str, user: str = Depends(current_user)):
        _, tid = owned(conv_id, user)
        v = conv_graph.get_state({"configurable": {"thread_id": conv_id}}).values
        return ConvDetail(info=info(conv_id, tid), messages=v.get("messages", []), intent=v.get("intent"),
                          draft=v.get("draft"), compliance=v.get("compliance"))

    @app.get("/health")
    def health():
        return {"ok": True, "marketplace": "up"}

    return app
