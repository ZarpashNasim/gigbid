"""Factory: the variant is chosen by config (agent.config rag.variant), never in code."""
from __future__ import annotations

from rag.index.store import Corpus
from rag.variants.v0_naive import V0Naive
from rag.variants.v2_hybrid import V2Hybrid

VARIANTS = {"v0_naive": V0Naive, "v2_hybrid": V2Hybrid}


def get_retriever(name: str, corpus: Corpus):
    return VARIANTS[name](corpus)
