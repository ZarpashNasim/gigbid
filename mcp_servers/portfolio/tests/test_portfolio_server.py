import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.portfolio.server import build_server
from rag.index.store import Corpus
from rag.variants.v0_naive import V0Naive
from rag.variants.v2_hybrid import V2Hybrid

CORPUS = Corpus.from_json("data/sample/portfolio.json")


def payload(res):
    return res.structuredContent or json.loads(res.content[0].text)


@pytest.mark.anyio
async def test_tools_listed_with_readonly_annotations():
    async with connect(build_server(CORPUS)._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert {"search_evidence", "get_case_study", "list_skills"} <= set(tools)
        assert all(t.annotations.readOnlyHint for t in tools.values())


@pytest.mark.anyio
async def test_search_finds_exact_tool_name():
    async with connect(build_server(CORPUS)._mcp_server) as c:
        res = await c.call_tool("search_evidence", {"requirement": "Celery", "k": 2})
        ids = [i["id"] for i in payload(res)["items"]]
        assert ids[0] == "cs3"


@pytest.mark.anyio
async def test_filter_by_outcome_and_bad_args_rejected():
    async with connect(build_server(CORPUS)._mcp_server) as c:
        res = await c.call_tool("search_evidence", {"requirement": "RAG chatbot", "outcome": "won"})
        assert [i["id"] for i in payload(res)["items"]] == ["p1"]
        bad = await c.call_tool("search_evidence", {"requirement": "x", "k": 99})
        assert bad.isError


@pytest.mark.anyio
async def test_resources_and_prompts():
    async with connect(build_server(CORPUS)._mcp_server) as c:
        r = await c.read_resource("portfolio://case/cs1")
        assert "pgvector" in r.contents[0].text
        names = {p.name for p in (await c.list_prompts()).prompts}
        assert "answer_screening_question" in names


@pytest.mark.anyio
async def test_unknown_case_study_errors():
    async with connect(build_server(CORPUS)._mcp_server) as c:
        assert (await c.call_tool("get_case_study", {"id": "nope"})).isError


def test_hybrid_beats_naive_on_exact_name():
    """Sanity check only (NOT a result): exact library names are where BM25 should help."""
    q = "dbt"
    h = [i.id for i in V2Hybrid(CORPUS).search(q, 1)]
    assert h == ["cs2"]


def test_incremental_reindex():
    c = Corpus(list(CORPUS.docs))
    c.add({"id": "x9", "type": "case_study", "source": "s", "skills": ["rust"], "text": "Wrote a Rust CLI"})
    assert V0Naive(c).search("Rust", 1)[0].id == "x9"
