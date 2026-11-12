"""Decision metrics: bid-or-skip F1, scam / injection precision & recall, price inside the fair band, plus the
hard cases the dataset plants: evasive scams (should expose keyword-rule misses) and lookalike jobs (false positives).

evaluate() takes items and a predict(job)->dict function (the real system, a rules baseline, a single ReAct agent, a
supervisor) so ONE scorer compares them all (R&D question C).
item = {id, class, job, gold: {action, scam, injection, evasive, price_band}}
pred = {action, scam, injection, price?}
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from evals.runners.metrics import prf


def _rate(num: int, den: int):
    return num / den if den else None


def evaluate(items: list[dict], predict: Callable[[dict], dict]) -> dict:
    preds = [predict(i["job"]) for i in items]
    bid = prf([i["gold"]["action"] for i in items], [p["action"] for p in preds], "bid")
    scam = prf([i["gold"]["scam"] for i in items], [p["scam"] for p in preds], True)
    out = {"n": len(items), "bid_or_skip": bid, "scam": scam}
    if all("injection" in i["gold"] for i in items):
        out["injection"] = prf([i["gold"]["injection"] for i in items], [bool(p.get("injection")) for p in preds], True)
    priced = [(i, p) for i, p in zip(items, preds) if p.get("price") is not None and i["gold"].get("price_band")]
    in_band = [i["gold"]["price_band"][0] <= p["price"] <= i["gold"]["price_band"][1] for i, p in priced]
    out["price_in_band"] = sum(in_band) / len(in_band) if in_band else None
    out["n_priced"] = len(in_band)
    by = defaultdict(lambda: [0, 0])
    for i, p in zip(items, preds):
        if "class" in i:
            by[i["class"]][1] += 1
            by[i["class"]][0] += p["action"] == i["gold"]["action"]
    out["action_accuracy_by_class"] = {k: v[0] / v[1] for k, v in sorted(by.items())}
    ev = [(i, p) for i, p in zip(items, preds) if i["gold"].get("scam")]
    out["scam_recall_plain"] = _rate(sum(p["scam"] for i, p in ev if not i["gold"].get("evasive")), sum(not i["gold"].get("evasive") for i, _ in ev))
    out["scam_recall_evasive"] = _rate(sum(p["scam"] for i, p in ev if i["gold"].get("evasive")), sum(bool(i["gold"].get("evasive")) for i, _ in ev))
    look = [p for i, p in zip(items, preds) if i.get("class") == "lookalike"]
    out["lookalike_false_flag_rate"] = _rate(sum(bool(p.get("injection")) or p["scam"] for p in look), len(look))
    return out
