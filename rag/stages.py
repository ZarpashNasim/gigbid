"""Composable retrieval stages shared by all variants, so one ablation runner can toggle each component."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from agent.handoffs import EvidenceItem
from rag.index.store import Corpus, tokenize
from rag.variants.v2_hybrid import ranked, rrf

OUTCOME_WEIGHT = {"won": 1.0, "replied": 0.5}


class Reranker(Protocol):
    def score(self, query: str, text: str) -> float: ...


class LexicalReranker:
    """STAND-IN cross-scorer: unigram+bigram overlap. Swap for bge-reranker-v2-m3 (CrossEncoderReranker)."""
    def score(self, query: str, text: str) -> float:
        def grams(s):
            t = tokenize(s)
            return set(t) | {a + "_" + b for a, b in zip(t, t[1:])}
        q, d = grams(query), grams(text)
        return len(q & d) / (len(q) ** 0.5 * len(d) ** 0.5 or 1)


class CrossEncoderReranker:
    """Real reranker (needs `pip install sentence-transformers` and a model download; not run in the sandbox)."""
    def __init__(self, model: str = "BAAI/bge-reranker-v2-m3"):
        from sentence_transformers import CrossEncoder
        self.m = CrossEncoder(model)

    def score(self, query, text):
        return float(self.m.predict([(query, text)])[0])


@dataclass
class Composed:
    """decompose: one retrieval per requirement then RRF-merge (V1). hybrid: BM25+dense RRF (V2).
    reranker: rerank top candidates (V3). outcome_boost: favour evidence from won/replied proposals (V4)."""
    corpus: Corpus
    decompose: bool = False
    hybrid: bool = False
    reranker: Reranker | None = None
    outcome_boost: float = 0.0
    rerank_depth: int = 20
    name: str = "composed"
    last_ids: list[int] = field(default_factory=list, repr=False)

    def _rank(self, q: str) -> list[int]:
        c = self.corpus
        return rrf([ranked(c.bm25(q)), ranked(c.dense(q))]) if self.hybrid else ranked(c.dense(q))

    def retrieve(self, job: dict, k: int = 5) -> list[EvidenceItem]:
        queries = job["requirements"] if self.decompose and job.get("requirements") else [job["text"]]
        lists = [self._rank(q) for q in queries]
        order = lists[0] if len(lists) == 1 else rrf(lists)
        if self.reranker:
            cands = order[: max(self.rerank_depth, k)]
            order = sorted(cands, key=lambda i: -max(self.reranker.score(q, self.corpus.docs[i]["text"]) for q in queries))
        if self.outcome_boost:
            base = {i: 1.0 / (60 + r + 1) for r, i in enumerate(order)}
            w = lambda i: 1 + self.outcome_boost * OUTCOME_WEIGHT.get(self.corpus.docs[i].get("outcome"), 0.0)
            order = sorted(order, key=lambda i: -base[i] * w(i))
        return [self.corpus.item(i) for i in order[:k]]

    def search(self, requirement: str, k: int = 5) -> list[EvidenceItem]:   # Retriever protocol for the agent graph
        return self.retrieve({"text": requirement, "requirements": [requirement]}, k)
