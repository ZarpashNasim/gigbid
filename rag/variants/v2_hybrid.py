"""V2 hybrid: BM25 + dense fused with reciprocal rank fusion. Targets exact names (Celery, dbt)."""
from __future__ import annotations

from agent.handoffs import EvidenceItem
from rag.index.store import Corpus


def rrf(rankings: list[list[int]], k: int = 60) -> list[int]:
    score: dict[int, float] = {}
    for r in rankings:
        for rank, i in enumerate(r):
            score[i] = score.get(i, 0.0) + 1.0 / (k + rank + 1)
    return sorted(score, key=lambda i: -score[i])


def ranked(scores: list[float]) -> list[int]:
    return [i for i in sorted(range(len(scores)), key=lambda i: -scores[i]) if scores[i] > 0]


class V2Hybrid:
    name = "v2_hybrid"

    def __init__(self, corpus: Corpus): self.c = corpus

    def search(self, requirement: str, k: int = 5) -> list[EvidenceItem]:
        fused = rrf([ranked(self.c.bm25(requirement)), ranked(self.c.dense(requirement))])
        return [self.c.item(i) for i in fused[:k]]

    def retrieve(self, job: dict, k: int = 5):
        return self.search(job["text"], k)
