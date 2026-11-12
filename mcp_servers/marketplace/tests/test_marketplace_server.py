import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.marketplace.adapters.memory import MemoryBackend
from mcp_servers.marketplace.infra import AuditLog, IdempotencyStore, RateLimiter
from mcp_servers.marketplace.server import build_server

JOB = {"title": "RAG bot", "description": "pgvector chatbot", "connects_cost": 8}
LETTER = "I built a similar RAG chatbot on pgvector last year."


def payload(res):
    return res.structuredContent or json.loads(res.content[0].text)


def setup(**kw):
    be = MemoryBackend({"j1": JOB}, connects=100)
    audit = AuditLog()
    return be, audit, build_server(be, audit=audit, **kw)


def args(**over):
    return {"job_id": "j1", "cover_letter": LETTER, "amount": 40.0, "idempotency_key": "key-0001", **over}


@pytest.mark.anyio
async def test_annotations_are_correct():
    _, _, s = setup()
    async with connect(s._mcp_server) as c:
        t = {x.name: x.annotations for x in (await c.list_tools()).tools}
        assert t["get_job"].readOnlyHint is True
        assert t["create_proposal_draft"].readOnlyHint is False and t["create_proposal_draft"].destructiveHint is False
        assert t["submit_proposal"].destructiveHint is True and t["send_message"].destructiveHint is True
        assert all(a.idempotentHint for a in t.values())


@pytest.mark.anyio
async def test_dry_run_is_default_and_has_no_side_effects():
    be, _, s = setup()
    async with connect(s._mcp_server) as c:
        res = payload(await c.call_tool("create_proposal_draft", {k: v for k, v in args().items()}))
        assert res["dry_run"] is True and res["connects_cost"] == 8 and res["would_send"]["amount"] == 40.0
        assert be.write_calls == 0 and be.connects == 100


@pytest.mark.anyio
async def test_retry_with_same_key_spends_connects_once():
    be, _, s = setup()
    async with connect(s._mcp_server) as c:
        a = payload(await c.call_tool("create_proposal_draft", args(dry_run=False)))
        b = payload(await c.call_tool("create_proposal_draft", args(dry_run=False)))
        assert a["deduplicated"] is False and b["deduplicated"] is True
        assert be.write_calls == 1 and be.connects == 92
        assert a["result"] == b["result"]


@pytest.mark.anyio
async def test_idempotency_survives_server_restart(tmp_path):
    db = str(tmp_path / "idem.sqlite")
    be = MemoryBackend({"j1": JOB})
    for _ in range(2):  # two separate server instances sharing one sqlite file = a restart
        s = build_server(be, idem=IdempotencyStore(db))
        async with connect(s._mcp_server) as c:
            await c.call_tool("create_proposal_draft", args(dry_run=False))
    assert be.write_calls == 1


@pytest.mark.anyio
async def test_input_constraints_rejected():
    _, _, s = setup()
    async with connect(s._mcp_server) as c:
        assert (await c.call_tool("create_proposal_draft", args(amount=-5))).isError
        assert (await c.call_tool("create_proposal_draft", args(cover_letter="short"))).isError
        assert (await c.call_tool("create_proposal_draft", args(idempotency_key="x"))).isError


@pytest.mark.anyio
async def test_audit_log_records_calls_and_errors():
    _, audit, s = setup()
    async with connect(s._mcp_server) as c:
        await c.call_tool("get_job", {"job_id": "j1"})
        await c.call_tool("get_job", {"job_id": "missing"})
    assert [r["tool"] for r in audit.rows] == ["get_job", "get_job"]
    assert audit.rows[0]["error"] is None and audit.rows[1]["error"]


@pytest.mark.anyio
async def test_rate_limiter_blocks_bursts():
    _, _, s = setup(limiter=RateLimiter(rate_per_s=0.001, burst=2))
    async with connect(s._mcp_server) as c:
        r = [await c.call_tool("get_connects_balance", {}) for _ in range(3)]
        assert [x.isError for x in r] == [False, False, True]


@pytest.mark.anyio
async def test_send_message_requires_dry_run_false_to_send():
    be, _, s = setup()
    async with connect(s._mcp_server) as c:
        await c.call_tool("send_message", {"thread_id": "t1", "body": "Hello", "idempotency_key": "msg-00001"})
        assert be.sent == []
        await c.call_tool("send_message", {"thread_id": "t1", "body": "Hello", "idempotency_key": "msg-00001", "dry_run": False})
        assert len(be.sent) == 1


def test_bearer_auth_rejects_missing_token():
    from starlette.testclient import TestClient
    from mcp_servers.marketplace.server import http_app
    _, _, s = setup()
    client = TestClient(http_app(s, {"secret-token": "user1"}))
    assert client.post("/mcp", json={}).status_code == 401
    assert client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
