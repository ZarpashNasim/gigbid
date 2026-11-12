"""Metrics with hand-checkable definitions. Binary relevance."""
from __future__ import annotations

import math
from collections import Counter


def recall_at_k(ranked_ids: list[str], gold: set[str], k: int) -> float:
    return len(set(ranked_ids[:k]) & gold) / len(gold) if gold else 0.0


def coverage_at_k(ranked_ids: list[str], groups: list[list[str]], k: int) -> float:
    """Share of requested capabilities with at least one supporting item in the top k.
    Unlike Recall@k this has no ceiling when a capability has several evidence items (what the Writer needs)."""
    top = set(ranked_ids[:k])
    return sum(bool(top & set(g)) for g in groups) / len(groups) if groups else 0.0


def mrr(ranked_ids: list[str], gold: set[str]) -> float:
    for r, i in enumerate(ranked_ids, 1):
        if i in gold:
            return 1.0 / r
    return 0.0


def ndcg_at_k(ranked_ids: list[str], gold: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(r + 2) for r, i in enumerate(ranked_ids[:k]) if i in gold)
    idcg = sum(1.0 / math.log2(r + 2) for r in range(min(len(gold), k)))
    return dcg / idcg if idcg else 0.0


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    idx = min(len(xs) - 1, max(0, math.ceil(p / 100 * len(xs)) - 1))
    return xs[idx]


def prf(y_true: list, y_pred: list, positive) -> dict:
    tp = sum(t == positive and p == positive for t, p in zip(y_true, y_pred))
    fp = sum(t != positive and p == positive for t, p in zip(y_true, y_pred))
    fn = sum(t == positive and p != positive for t, p in zip(y_true, y_pred))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": prec, "recall": rec, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def cohen_kappa(a: list, b: list) -> float:
    """Agreement between two labelers beyond chance (judge calibration: you label 30 items, judge labels same)."""
    assert len(a) == len(b) and a
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[l] * cb[l] for l in set(a) | set(b)) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def unsupported_rate(claim_statuses_per_proposal: list[list[str]]) -> dict:
    """Unsupported claims per proposal and as a share of all claims (report before vs after verification)."""
    n_prop = len(claim_statuses_per_proposal)
    total = sum(len(c) for c in claim_statuses_per_proposal)
    uns = sum(s == "unsupported" for c in claim_statuses_per_proposal for s in c)
    return {"unsupported_per_proposal": uns / n_prop if n_prop else 0.0, "unsupported_share": uns / total if total else 0.0}
