"""GigSim FastAPI service. Endpoints mirror what the marketplace adapter (mcp_servers/marketplace/adapters/
gigsim.py) calls; see gigsim/README.md for the documented contract. In-memory, deterministic, offline.
"""
from __future__ import annotations

import hmac
import json
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .client_sim import client_reply

DEV_TOKEN = "dev-local-token"   # default when GIGSIM_API_TOKEN is unset; override in .env for anything shared


class _Bucket:
    """Per-token token bucket. Default 20 requests/minute matches the starter-kit config
    (marketplace.max_requests_per_minute). On exhaustion the endpoint returns 429 + Retry-After,
    which the adapter already treats as retryable with back-off."""
    def __init__(self, per_minute: int = 20, clock=time.monotonic):
        self.rate = per_minute / 60.0
        self.burst = float(per_minute)
        self.clock = clock
        self.state: dict[str, tuple[float, float]] = {}

    def take(self, key: str) -> float | None:
        now = self.clock()
        tokens, last = self.state.get(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        if tokens < 1:
            self.state[key] = (tokens, now)
            return (1 - tokens) / self.rate            # seconds until one token is available
        self.state[key] = (tokens - 1, now)
        return None


class ProposalIn(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    cover_letter: str = Field(min_length=1, max_length=5000)
    amount: float = Field(gt=0, le=1_000_000)
    answers: dict[str, str] = Field(default_factory=dict)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


def _load(data_dir: str, split: str):
    root = Path(data_dir)
    jobs = {j["job_id"]: j for j in map(json.loads, (root / f"jobs_{split}.jsonl").read_text().splitlines()) if j}
    clients = {c["client_id"]: c for c in json.loads((root / "clients.json").read_text())}
    threads = {t["thread_id"]: {"job_id": t.get("job_id"), "messages": list(t["messages"])}
               for t in json.loads((root / f"threads_{split}.json").read_text())}
    return jobs, clients, threads


def build_gigsim(data_dir: str = "data/synthetic", split: str = "dev", token: str | None = None,
                 connects: int = 200, per_minute: int = 20) -> FastAPI:
    jobs, clients, threads = _load(data_dir, split)
    token = token or DEV_TOKEN
    bucket = _Bucket(per_minute)
    state = {"connects": connects, "proposals": {}}      # proposal_id -> record

    app = FastAPI(title="GigSim (self-built stand-in)", version="0.1")

    def auth(authorization: str = Header(default="")) -> str:
        if not authorization.startswith("Bearer ") or not hmac.compare_digest(authorization[7:], token):
            raise HTTPException(status_code=401, detail="unauthorized")
        return "local"                                   # single-tenant simulator

    def gate(request: Request, user: str = Depends(auth)) -> str:
        wait = bucket.take(user)
        if wait is not None:
            raise HTTPException(status_code=429, detail="rate limited",
                                headers={"Retry-After": str(max(1, round(wait)))})
        return user

    @app.get("/health")                                  # unauthenticated readiness probe
    def health():
        return {"status": "ok", "jobs": len(jobs), "note": "self-built GigSim stand-in, not the instructor's"}

    @app.get("/jobs")
    def search_jobs(q: str = "", limit: int = 20, user: str = Depends(gate)):
        ql = q.lower()
        hits = [j for j in jobs.values() if ql in (j.get("title", "") + " " + j.get("description", "")).lower()]
        return hits[: max(1, min(limit, 50))]

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, user: str = Depends(gate)):
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="job not found")
        return jobs[job_id]

    @app.get("/clients/{client_id}")
    def get_client(client_id: str, user: str = Depends(gate)):
        if client_id not in clients:
            raise HTTPException(status_code=404, detail="client not found")
        return clients[client_id]

    @app.get("/me/connects")
    def connects_balance(user: str = Depends(gate)):
        return {"balance": state["connects"]}

    @app.get("/threads/{thread_id}/messages")
    def list_messages(thread_id: str, user: str = Depends(gate)):
        return threads.get(thread_id, {"messages": []})["messages"]

    @app.post("/proposals")
    def create_proposal(body: ProposalIn, user: str = Depends(gate)):
        if body.job_id not in jobs:
            raise HTTPException(status_code=404, detail="job not found")
        cost = int(jobs[body.job_id].get("connects_cost", 8))
        pid = f"gsim-prop-{len(state['proposals']) + 1:04d}"
        state["connects"] = max(0, state["connects"] - cost)
        rec = {"proposal_id": pid, "job_id": body.job_id, "amount": body.amount,
               "status": "draft", "connects_spent": cost, "connects_balance": state["connects"]}
        state["proposals"][pid] = rec
        return rec

    @app.post("/proposals/{proposal_id}/submit")
    def submit_proposal(proposal_id: str, user: str = Depends(gate)):
        rec = state["proposals"].get(proposal_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        rec["status"] = "submitted"
        return rec

    @app.post("/threads/{thread_id}/messages")
    def send_message(thread_id: str, body: MessageIn, user: str = Depends(gate)):
        thread = threads.setdefault(thread_id, {"job_id": None, "messages": []})
        msgs = thread["messages"]
        mine = {"from": "me", "body": body.body}
        msgs.append(mine)
        reply_index = sum(1 for m in msgs if m.get("from") == "client")
        reply = {"from": "client", "body": client_reply(thread_id, reply_index, jobs.get(thread["job_id"]))}
        msgs.append(reply)
        mid = f"gsim-msg-{len(msgs):04d}"
        return {"message_id": mid, "thread_id": thread_id, "body": body.body, "client_reply": reply}

    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException):     # keep Retry-After on 429 responses
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail},
                            headers=getattr(exc, "headers", None))

    return app
