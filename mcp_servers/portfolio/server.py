"""Portfolio MCP server (read-only), built on the official MCP Python SDK (FastMCP).

Run:  python -m mcp_servers.portfolio.server            (stdio, for Claude Desktop / Cursor)
Env:  PORTFOLIO_PATH=path/to/portfolio.json   PORTFOLIO_VARIANT=v2_hybrid
"""
from __future__ import annotations

import json
import os
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from rag.index.store import Corpus
from rag.retriever import get_retriever

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class EvidenceOut(BaseModel):
    id: str
    type: str
    source: str
    date: str | None = None
    outcome: str | None = None
    text: str


class SearchOut(BaseModel):
    items: list[EvidenceOut]


def build_server(corpus: Corpus, variant: str = "v2_hybrid") -> FastMCP:
    mcp = FastMCP("gigbid-portfolio")
    retriever = get_retriever(variant, corpus)

    @mcp.tool(annotations=READ_ONLY)
    def search_evidence(
        requirement: str = Field(min_length=2, max_length=500, description="One job requirement, e.g. 'Celery task queues'"),
        k: int = Field(default=5, ge=1, le=10),
        type: Literal["case_study", "repo", "review", "proposal", "cv"] | None = None,
        outcome: Literal["won", "replied", "ignored"] | None = None,
    ) -> SearchOut:
        """Find portfolio evidence (case studies, repos, reviews, past proposals) proving a requirement.
        Returns items with type, source, date and outcome. Use one call per requirement."""
        hits = retriever.search(requirement, k=corpus_size(corpus))
        if type: hits = [h for h in hits if h.type == type]
        if outcome: hits = [h for h in hits if h.outcome == outcome]
        return SearchOut(items=[EvidenceOut(**h.model_dump()) for h in hits[:k]])

    @mcp.tool(annotations=READ_ONLY)
    def get_case_study(id: str = Field(description="Evidence id, e.g. 'cs1'")) -> EvidenceOut:
        """Return one full portfolio item by id."""
        d = corpus.by_id.get(id)
        if not d:
            raise ValueError(f"unknown id {id!r}")
        return EvidenceOut(**{k: d.get(k) for k in ("id", "type", "source", "date", "outcome", "text")})

    @mcp.tool(annotations=READ_ONLY)
    def list_skills() -> list[str]:
        """List every skill tagged anywhere in the portfolio."""
        return sorted({s for d in corpus.docs for s in d.get("skills", [])})

    @mcp.resource("portfolio://case/{id}")
    def case_resource(id: str) -> str:
        """Full case study / repo / review as JSON so a host can load it."""
        return json.dumps(corpus.by_id[id])

    @mcp.resource("portfolio://proposal/{id}")
    def proposal_resource(id: str) -> str:
        """A past proposal with its outcome."""
        d = corpus.by_id[id]
        if d["type"] != "proposal":
            raise ValueError("not a proposal")
        return json.dumps(d)

    @mcp.prompt()
    def answer_screening_question(question: str) -> str:
        """Answer a client's screening question using only my portfolio."""
        return ("Answer this screening question using ONLY evidence from the portfolio tools "
                f"(call search_evidence first). Cite evidence ids. If there is no evidence, say so.\n\nQuestion: {question}")

    @mcp.prompt()
    def draft_cover_letter(job_description: str) -> str:
        """Draft a grounded cover letter for a job post."""
        return ("Break the job into requirements, call search_evidence for each, then write a short, specific "
                "cover letter that claims only what the evidence supports.\n\n<job_post>\n"
                f"{job_description}\n</job_post>")

    return mcp


def corpus_size(c: Corpus) -> int:
    return len(c.docs)


if __name__ == "__main__":
    path = os.environ.get("PORTFOLIO_PATH", "data/sample/portfolio.json")
    build_server(Corpus.from_json(path), os.environ.get("PORTFOLIO_VARIANT", "v2_hybrid")).run()
