"""V0 baseline: top-k dense similarity on the whole query. The number everything else must beat."""
from __future__ import annotations

from agent.handoffs import EvidenceItem
from rag.index.store import Corpus


class V0Naive:
    name = "v0_naive"

    def __init__(self, corpus: Corpus): self.c = corpus

    def search(self, requirement: str, k: int = 5) -> list[EvidenceItem]:
        s = self.c.dense(requirement)
        top = sorted(range(len(s)), key=lambda i: -s[i])[:k]
        return [self.c.item(i) for i in top if s[i] > 0]

    def retrieve(self, job: dict, k: int = 5):
        return self.search(job["text"], k)
