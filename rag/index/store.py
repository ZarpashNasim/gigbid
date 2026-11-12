"""Corpus + indexes: pure-Python BM25 and a pluggable dense embedder (no heavy deps for tests).

`HashEmbedder` is a deterministic bag-of-hashed-ngrams stand-in so tests/CI run offline.
For real runs swap in an open embedding model (bge-m3 / nomic-embed-text) via `Embedder`.
"""
from __future__ import annotations

import json
import math
import re
import zlib
from collections import Counter
from pathlib import Path
from typing import Protocol

import numpy as np

from agent.handoffs import EvidenceItem

TOKEN = re.compile(r"[a-z0-9\+\#\.]+")


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    """Placeholder embedder: hashed unigrams+bigrams, L2-normalised. NOT a semantic model."""
    def __init__(self, dim: int = 512): self.dim = dim

    def embed(self, texts):
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for i, t in enumerate(texts):
            toks = tokenize(t)
            for g in toks + [a + "_" + b for a, b in zip(toks, toks[1:])]:
                out[i, zlib.crc32(g.encode()) % self.dim] += 1.0
        n = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(n == 0, 1, n)


def normalise_doc(d: dict) -> dict:
    """Accept both our flat schema (id/text/outcome) and the starter-kit schema (evidence_id/title/summary).

    Kit `outcome` is a free-text project result; `proposal_outcome` (won|replied|ignored) is the marketplace outcome
    used by outcome-aware ranking. Past proposals are claims, not verified evidence, so they are marked ineligible
    as support for new claims (they are still retrievable as style/outcome references).
    """
    out = dict(d)
    out["id"] = d.get("id") or d["evidence_id"]
    out["text"] = d.get("text") or " ".join(x for x in (d.get("title"), d.get("summary")) if x)
    label = d.get("proposal_outcome") or (d.get("outcome") if d.get("outcome") in ("won", "replied", "ignored") else None)
    out["outcome"] = label
    out["source"] = d.get("source", "unknown")
    out["evidence_eligible"] = d.get("type") != "proposal"
    return out


class Corpus:
    def __init__(self, docs: list[dict], embedder: Embedder | None = None, eligible_only: bool = False):
        docs = [normalise_doc(d) for d in docs]
        self.eligible_only = eligible_only
        if eligible_only:       # evidence index: verified work only; past proposals are claims, kept in a separate index
            docs = [d for d in docs if d["evidence_eligible"]]
        self.docs = docs
        self.by_id = {d["id"]: d for d in docs}
        self.embedder = embedder or HashEmbedder()
        self._toks = [tokenize(d["text"] + " " + " ".join(d.get("skills", []))) for d in docs]
        self._df = Counter(t for toks in self._toks for t in set(toks))
        self._avg = sum(map(len, self._toks)) / max(len(self._toks), 1)
        self._emb = self.embedder.embed([d["text"] for d in docs])

    @classmethod
    def from_json(cls, path: str | Path, **kw) -> "Corpus":
        return cls(json.loads(Path(path).read_text()), **kw)

    def add(self, doc: dict) -> None:
        """Incremental re-index when the user adds work (B1)."""
        self.__init__(self.docs + [doc], self.embedder, self.eligible_only)

    def bm25(self, query: str, k1: float = 1.5, b: float = 0.75) -> list[float]:
        q, n = tokenize(query), len(self.docs)
        scores = []
        for toks in self._toks:
            tf, s = Counter(toks), 0.0
            for t in q:
                if t in tf:
                    idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                    s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(toks) / self._avg))
            scores.append(s)
        return scores

    def dense(self, query: str) -> list[float]:
        return (self._emb @ self.embedder.embed([query])[0]).tolist()

    def item(self, i: int) -> EvidenceItem:
        d = self.docs[i]
        return EvidenceItem(id=d["id"], type=d["type"], source=d["source"], text=d["text"],
                            date=d.get("date"), outcome=d.get("outcome"))
