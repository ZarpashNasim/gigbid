"""V4: outcome-aware ranking - boost evidence from proposals that won / got replies."""
from rag.stages import Composed, LexicalReranker


def make(corpus, boost: float = 0.5, reranker=None):
    return Composed(corpus, decompose=True, hybrid=True, reranker=reranker or LexicalReranker(),
                    outcome_boost=boost, name="v4_outcome")
