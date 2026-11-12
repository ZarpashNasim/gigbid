"""Integration tests against the self-built GigSim service (gigsim/).

Runs the ASGI app in-process (no real port): TestClient for direct HTTP checks, and an httpx ASGITransport
so the real GigSimBackend adapter talks to the same app. Proves the marketplace port is wired to GigSim's
documented contract end-to-end, offline and deterministically.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gigsim.app import build_gigsim
from mcp_servers.marketplace.adapters.gigsim import GigSimBackend

TOKEN = "test-token"


@pytest.fixture
def app():
    return build_gigsim(data_dir="data/synthetic", split="dev", token=TOKEN, connects=200, per_minute=20)


@pytest.fixture
def client(app):
    return TestClient(app)


def adapter(app) -> GigSimBackend:
    # TestClient is a sync httpx.Client with an in-process ASGI transport; drop it in as the adapter's
    # http client so the real GigSimBackend talks to the app without a real port.
    be = GigSimBackend("http://gigsim", TOKEN)
    be.http = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
    return be


def test_health_is_unauthenticated(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["jobs"] > 0


def test_auth_required(client):
    assert client.get("/me/connects").status_code == 401
    assert client.get("/me/connects", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/me/connects", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_adapter_reads(app):
    be = adapter(app)
    jobs = be.search_jobs("", 5)
    assert jobs, "expected some dev jobs"
    job = be.get_job(jobs[0]["job_id"])
    assert job["job_id"] == jobs[0]["job_id"]
    assert isinstance(be.get_client_history(job["client_id"]), dict)
    assert isinstance(be.get_connects_balance(), int)


def test_proposal_spends_connects(app):
    be = adapter(app)
    job = be.search_jobs("", 1)[0]
    before = be.get_connects_balance()
    rec = be.create_proposal(job["job_id"], "A relevant cover letter for this job.", 500.0, {})
    assert rec["proposal_id"] and rec["status"] == "draft"
    assert be.get_connects_balance() == before - job["connects_cost"]
    assert be.submit_proposal(rec["proposal_id"])["status"] == "submitted"


def test_send_message_gets_deterministic_client_reply(app):
    be = adapter(app)
    out = be.send_message("t-new", "Hello, I'd love to help with this.")
    assert out["message_id"] and out["client_reply"]["from"] == "client"
    msgs = be.list_messages("t-new")
    assert [m["from"] for m in msgs] == ["me", "client"]
    # deterministic: a fresh app + same thread/first-reply yields the same client line
    be2 = adapter(build_gigsim(split="dev", token=TOKEN))
    assert be2.send_message("t-new", "Different opening text")["client_reply"]["body"] == out["client_reply"]["body"]


def test_rate_limit_returns_429(client):
    h = {"Authorization": f"Bearer {TOKEN}"}
    codes = [client.get("/me/connects", headers=h).status_code for _ in range(25)]
    assert 429 in codes, "burst of 25 should exceed the 20/min bucket"


def test_unknown_ids_are_404(client):
    h = {"Authorization": f"Bearer {TOKEN}"}
    assert client.get("/jobs/does-not-exist", headers=h).status_code == 404
    assert client.get("/clients/does-not-exist", headers=h).status_code == 404
    assert client.post("/proposals", headers=h,
                       json={"job_id": "nope", "cover_letter": "x" * 20, "amount": 10.0, "answers": {}}).status_code == 404
