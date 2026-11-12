"""API + durability tests. The crash test uses a real on-disk checkpointer and two app instances."""
from __future__ import annotations

import copy
import json

from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from agent.checkpointing import make_checkpointer
from agent.config import load_config
from agent.deps import Deps
from agent.marketplace_port import InMemoryMarketplace
from apps.api.main import create_app
from tests.unit.test_bid_graph import JOB, FakeLLM, FakeRetriever

A = {"Authorization": "Bearer tok-a"}
B = {"Authorization": "Bearer tok-b"}
TOKENS = {"tok-a": "alice", "tok-b": "bob"}


def deps(market):
    return Deps(llm=FakeLLM(), market=market, retriever=FakeRetriever(), store=InMemoryStore(),
                cfg=copy.deepcopy(load_config()))


def make_app(market, tmp_path):
    return create_app(deps(market), make_checkpointer(f"sqlite:///{tmp_path}/ck.db"), TOKENS,
                      registry_path=str(tmp_path / "reg.db"))


def test_requires_auth(tmp_path):
    c = TestClient(make_app(InMemoryMarketplace({"j1": JOB}, {}), tmp_path))
    assert c.get("/approvals").status_code == 401


def test_full_flow_and_refresh_keeps_pending_approval(tmp_path):
    market = InMemoryMarketplace({"j1": JOB}, {})
    c = TestClient(make_app(market, tmp_path))
    r = c.post("/runs", json={"job_id": "j1"}, headers=A).json()
    assert r["waiting_for_approval"]
    for _ in range(2):                                   # "page refresh": same pending approval each time
        p = c.get("/approvals", headers=A).json()
        assert len(p) == 1 and p[0]["payload"]["dry_run"]["connects_cost"] == 8
    assert market.write_calls == 0
    done = c.post(f"/approvals/{r['thread_id']}", json={"decision": "approve"}, headers=A).json()
    assert done["status"] == "submitted" and market.write_calls == 1


def test_double_approve_is_rejected_and_sends_once(tmp_path):
    market = InMemoryMarketplace({"j1": JOB}, {})
    c = TestClient(make_app(market, tmp_path))
    t = c.post("/runs", json={"job_id": "j1"}, headers=A).json()["thread_id"]
    assert c.post(f"/approvals/{t}", json={"decision": "approve"}, headers=A).status_code == 200
    assert c.post(f"/approvals/{t}", json={"decision": "approve"}, headers=A).status_code == 409
    assert market.write_calls == 1


def test_crash_while_waiting_then_resume_submits_exactly_once(tmp_path):
    market = InMemoryMarketplace({"j1": JOB}, {})        # stands in for the marketplace that outlives the API
    app1 = make_app(market, tmp_path)
    t = TestClient(app1).post("/runs", json={"job_id": "j1"}, headers=A).json()["thread_id"]
    del app1                                             # "kill the API" while approval is pending
    app2 = make_app(market, tmp_path)                    # fresh process, same disk
    c2 = TestClient(app2)
    assert len(c2.get("/approvals", headers=A).json()) == 1        # pending approval survived the crash
    done = c2.post(f"/approvals/{t}", json={"decision": "approve"}, headers=A).json()
    assert done["status"] == "submitted"
    assert market.write_calls == 1 and len(market.submissions) == 1


def test_tenant_isolation(tmp_path):
    c = TestClient(make_app(InMemoryMarketplace({"j1": JOB}, {}), tmp_path))
    t = c.post("/runs", json={"job_id": "j1"}, headers=A).json()["thread_id"]
    assert c.get("/approvals", headers=B).json() == []
    assert c.post(f"/approvals/{t}", json={"decision": "approve"}, headers=B).status_code == 404
    assert c.get(f"/runs/{t}/trace", headers=B).status_code == 404


def test_stream_emits_node_events(tmp_path):
    c = TestClient(make_app(InMemoryMarketplace({"j1": JOB}, {}), tmp_path))
    t = c.post("/runs", json={"job_id": "j1"}, headers=A).json()["thread_id"]
    body = c.get(f"/runs/{t}/stream", headers=A).text
    assert "event: node" in body and '"node": "critic"' in body and "event: end" in body


def test_live_streaming_with_background_executor(tmp_path):
    """Run starts in a background thread; POST returns before the run finishes; SSE delivers
    node events as they happen, in order, ending with an 'end' event that says approval is pending."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    class SlowLLM(FakeLLM):
        def structured(self, node, schema, system, user):
            time.sleep(0.05)
            return super().structured(node, schema, system, user)

    market = InMemoryMarketplace({"j1": JOB}, {})
    d = Deps(llm=SlowLLM(), market=market, retriever=FakeRetriever(), store=InMemoryStore(),
             cfg=copy.deepcopy(load_config()))
    app = create_app(d, make_checkpointer(f"sqlite:///{tmp_path}/ck.db"), TOKENS,
                     registry_path=str(tmp_path / "reg.db"), executor=ThreadPoolExecutor(max_workers=2))
    c = TestClient(app)
    t0 = time.monotonic()
    t = c.post("/runs", json={"job_id": "j1"}, headers=A).json()["thread_id"]
    assert time.monotonic() - t0 < 0.3                 # returned immediately, run continues in background
    nodes, end = [], None
    with c.stream("GET", f"/runs/{t}/stream", headers=A) as r:
        kind = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: ") and kind == "node":
                nodes.append(json.loads(line[6:])["node"])
            elif line.startswith("data: ") and kind == "end":
                end = json.loads(line[6:])
    assert nodes[0] == "intake" and nodes.index("decide") > nodes.index("analyst")
    assert nodes.index("critic") < nodes.index("compliance")
    assert end["waiting_for_approval"] is True and market.write_calls == 0


def test_backend_port_dry_run_and_idempotent_create():
    from agent.marketplace_port import BackendPort
    from mcp_servers.marketplace.adapters.memory import MemoryBackend
    be = MemoryBackend({"j1": JOB}, connects=100)
    port = BackendPort(be)
    kw = dict(user_id="u", job_id="j1", cover_letter="x" * 30, amount=40.0, answers={}, idempotency_key="k-00001")
    assert port.create_proposal_draft(**kw, dry_run=True).connects_cost == 8 and be.write_calls == 0
    a = port.create_proposal_draft(**kw, dry_run=False)
    b = port.create_proposal_draft(**kw, dry_run=False)
    assert a["submission_id"] == b["submission_id"] and be.write_calls == 1 and be.connects == 92


def test_run_detail_has_everything_the_ui_needs(tmp_path):
    c = TestClient(make_app(InMemoryMarketplace({"j1": JOB}, {}), tmp_path))
    t = c.post("/runs", json={"job_id": "j1"}, headers=A).json()["thread_id"]
    d = c.get(f"/runs/{t}", headers=A).json()
    assert d["decision"]["action"] == "bid" and d["fit"]["matches"] and d["draft"]["claims"]
    assert d["price"]["amount"] >= 30 and d["risk"]["client_score"] > 0
    assert c.get(f"/runs/{t}", headers=B).status_code == 404


def _conv_app(tmp_path, text, intent="interview_request"):
    from agent.handoffs import MessageIntent, ReplyDraft
    from agent.workspace import InMemoryWorkspace

    class Both(FakeLLM):
        def structured(self, node, schema, system, user):
            if schema is MessageIntent:
                return MessageIntent(intent=intent, summary="s"), 1
            if schema is ReplyDraft:
                return ReplyDraft(body="Happy to chat, do these times work?"), 1
            return super().structured(node, schema, system, user)

    market = InMemoryMarketplace({"j1": JOB}, {})
    market.threads["m1"] = [{"from": "client", "body": text}]
    ws = InMemoryWorkspace()
    d = Deps(llm=Both(), market=market, retriever=FakeRetriever(), store=InMemoryStore(),
             cfg=copy.deepcopy(load_config()), workspace=ws)
    app = create_app(d, make_checkpointer(f"sqlite:///{tmp_path}/ck.db"), TOKENS, registry_path=str(tmp_path / "reg.db"))
    return TestClient(app), market, ws


def test_conversation_flow_through_api(tmp_path):
    c, market, ws = _conv_app(tmp_path, "Can we have a call?")
    r = c.post("/conversations", json={"thread_id": "m1"}, headers=A).json()
    assert r["waiting_for_approval"] and r["thread_id"] == "conv:user1:m1".replace("user1", "alice")
    det = c.get(f"/conversations/{r['thread_id']}", headers=A).json()
    assert det["intent"]["intent"] == "interview_request" and len(det["draft"]["proposed_slots"]) == 3
    # conversations never show up in the bid-run list, and their approvals show up in /approvals
    assert c.get("/runs", headers=A).json() == []
    pend = c.get("/approvals", headers=A).json()
    assert pend[0]["payload"]["kind"] == "message_approval"
    assert market.message_writes == 0
    out = c.post(f"/approvals/{r['thread_id']}", json={"decision": "approve"}, headers=A).json()
    assert out["status"] == "sent" and market.message_writes == 1 and len(ws.holds) == 3


def test_conversation_scam_flagged_and_tenant_scoped(tmp_path):
    c, market, _ = _conv_app(tmp_path, "Pay me on WhatsApp please", intent="question")
    r = c.post("/conversations", json={"thread_id": "m1"}, headers=A).json()
    assert r["status"] == "flagged" and not r["waiting_for_approval"]
    assert c.get(f"/conversations/{r['thread_id']}", headers=B).status_code == 404
    assert market.message_writes == 0
