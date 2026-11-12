"""V1: requirement decomposition (one retrieval per extracted requirement, then merge)."""
from rag.stages import Composed


def make(corpus): return Composed(corpus, decompose=True, name="v1_decompose")
