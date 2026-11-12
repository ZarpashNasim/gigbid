"""V8: corrective RAG loop in LangGraph: retrieve -> grade -> (re-query wider if weak) -> finalize.
Refuses to claim: evidence that supports no requirement is dropped, and no evidence is returned for a job
the persona cannot support. The grader here is lexical (testable offline); swap in an LLM grader node.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agent.handoffs import EvidenceItem
from rag.index.store import Corpus, tokenize
from rag.stages import Composed

STOP = {"a", "an", "the", "and", "or", "with", "for", "of", "in", "to", "on", "we", "you", "need", "must", "have", "experience", "using", "build"}


class S(TypedDict, total=False):
    job: dict
    k: int
    evidence: list[EvidenceItem]
    supported: dict
    retries: int
    final: list[EvidenceItem]


def supports(req: str, ev: EvidenceItem, thr: float) -> bool:
    q = {t for t in tokenize(req) if t not in STOP}
    d = set(tokenize(ev.text))
    return bool(q) and len(q & d) / len(q) >= thr


class V8Corrective:
    name = "v8_corrective"

    def __init__(self, corpus: Corpus, threshold: float = 0.34, min_coverage: float = 0.5, max_retries: int = 1,
                 grader=None):
        self.base = Composed(corpus, decompose=True, hybrid=True)
        self.thr, self.min_cov, self.max_retries = threshold, min_coverage, max_retries
        self.grader = grader   # optional LLMSupportGrader; None -> strict lexical supports() below
        g = StateGraph(S)
        g.add_node("retrieve", self._retrieve)
        g.add_node("grade", self._grade)
        g.add_node("finalize", self._finalize)
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges("grade", self._route, ["retrieve", "finalize"])
        g.add_edge("finalize", END)
        self.graph = g.compile()

    def _retrieve(self, s):
        attempt = s.get("retries", 0)      # attempts made so far; each retry widens the candidate pool
        return {"evidence": self.base.retrieve(s["job"], k=s["k"] * (1 + 2 * attempt)), "retries": attempt + 1}

    def _grade(self, s):
        reqs = s["job"].get("requirements") or [s["job"]["text"]]
        ev = s["evidence"]
        sup = {}
        for r in reqs:
            ids = self.grader.supported_ids(r, ev) if self.grader else None   # LLM grader (semantic) if configured
            if ids is None:                                                   # else / on failure: strict lexical check
                ids = {e.id for e in ev if supports(r, e, self.thr)}
            sup[r] = [e.id for e in ev if e.id in ids]
        return {"supported": sup}

    def _route(self, s):
        cov = sum(bool(v) for v in s["supported"].values()) / max(len(s["supported"]), 1)
        # bounded: first attempt + at most max_retries corrective re-queries
        return "retrieve" if cov < self.min_cov and s["retries"] < 1 + self.max_retries else "finalize"

    def _finalize(self, s):
        keep = {i for ids in s["supported"].values() for i in ids}
        return {"final": [e for e in s["evidence"] if e.id in keep][: s["k"]]}

    def retrieve(self, job: dict, k: int = 5) -> list[EvidenceItem]:
        return self.graph.invoke({"job": job, "k": k, "retries": 0})["final"]

    def search(self, requirement: str, k: int = 5):
        return self.retrieve({"text": requirement, "requirements": [requirement]}, k)
