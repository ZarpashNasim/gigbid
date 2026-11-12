"""V3: cross-encoder reranking over hybrid candidates. Default reranker is a lexical stand-in."""
from rag.stages import Composed, LexicalReranker


def make(corpus, reranker=None):
    return Composed(corpus, hybrid=True, reranker=reranker or LexicalReranker(), name="v3_rerank")
