"""Client-message intent evaluation (Client Liaison classifier): accuracy, per-intent P/R/F1 and scam-signal recall
split into plain vs evasive messages. Scores any predict(messages)->intent function.

python -m evals.runners.intent_eval --split dev          # keyword/rules baseline, no LLM
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from agent.rules import detect_signals
from evals.runners.metrics import prf

INTENTS = ["question", "negotiation", "interview_request", "scam_signal"]


def keyword_predict(messages: list[dict]) -> str:
    """Baseline: shared scam/injection rules first, then crude keywords. No model."""
    text = next(m["body"] for m in reversed(messages) if m["from"] == "client")
    if detect_signals(text):
        return "scam_signal"
    t = text.lower()
    if re.search(r"\b(call|interview|meet|zoom|video)\b", t):
        return "interview_request"
    if re.search(r"\b(price|budget|percent|less|discount|reduce|days instead)\b", t):
        return "negotiation"
    return "question"


def evaluate(items: list[dict], predict) -> dict:
    preds = [predict(i["messages"]) for i in items]
    gold = [i["gold"]["intent"] for i in items]
    per = {k: prf(gold, preds, k) for k in INTENTS}
    sc = [(i, p) for i, p in zip(items, preds) if i["gold"]["intent"] == "scam_signal"]
    rate = lambda xs: (sum(p == "scam_signal" for _, p in xs) / len(xs)) if xs else None
    return {"n": len(items), "accuracy": sum(g == p for g, p in zip(gold, preds)) / len(items),
            "per_intent": per, "scam_recall_plain": rate([x for x in sc if not x[0]["gold"]["evasive"]]),
            "scam_recall_evasive": rate([x for x in sc if x[0]["gold"]["evasive"]])}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    a = ap.parse_args()
    ds = json.loads(Path(f"evals/datasets/synth_messages_{a.split}.json").read_text())
    r = evaluate(ds["items"], keyword_predict)
    r["meta"] = {"system": "keyword/rules baseline (no LLM)", "split": a.split, "synthetic": True,
                 "dataset": f"evals/datasets/synth_messages_{a.split}.json"}
    Path(f"evals/results/intent_rules_{a.split}.json").write_text(json.dumps(r, indent=2))
    f = lambda x: "n/a" if x is None else f"{x:.2f}"
    print(f"accuracy={r['accuracy']:.2f}  scam recall plain={f(r['scam_recall_plain'])} evasive={f(r['scam_recall_evasive'])}")
    print({k: round(v["f1"], 2) for k, v in r["per_intent"].items()})
