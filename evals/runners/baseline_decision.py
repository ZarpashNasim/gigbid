"""Rules-only baseline: the system's OWN deterministic layer (risk rule floor, Matcher coverage, decide thresholds)
with the LLM replaced by a null model. This is the floor an LLM Risk Assessor / Analyst must beat, and it shows
exactly which cases rules alone cannot handle. Price is not scored (a rules baseline has no pricing model).

python -m evals.runners.baseline_decision --split dev
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from langgraph.store.memory import InMemoryStore

from agent.config import load_config
from agent.deps import Deps
from agent.handoffs import JobSpec, PriceQuote, RiskReport
from agent.marketplace_port import InMemoryMarketplace
from agent.nodes.analysis import make_matcher, make_risk
from agent.nodes.bid import make_decide
from evals.runners.decision_eval import evaluate
from rag.index.store import Corpus
from rag.stages import Composed


def client_score(c: dict) -> float:
    """Transparent rule from client history (0 = untrustworthy, 1 = trustworthy). Weights are assumptions."""
    s = 0.5
    s += 0.25 if c.get("payment_verified") else -0.25
    if c.get("average_rating") is not None:
        s += (c["average_rating"] - 4.0) * 0.2
    s -= 0.1 * c.get("open_disputes", 0)
    s += 0.1 if c.get("completed_projects", 0) >= 10 else 0
    return max(0.0, min(1.0, s))


class NullLLM:
    """Returns neutral structures: no LLM judgement, so only deterministic rules act.
    The Matcher's grader call fails here on purpose, which exercises its strict lexical fallback."""
    def __init__(self, clients: dict): self.clients = clients

    def structured(self, node, schema, system, user):
        if schema is RiskReport:
            return RiskReport(client_score=0.9), 0         # overwritten below from client history
        if schema is JobSpec:
            return JobSpec(job_id="x", title="t"), 0
        if schema is PriceQuote:
            return PriceQuote(amount=0, connects_cost=8), 0
        raise RuntimeError("no LLM in the rules-only baseline")


def build_predictor(split: str, data_root: str = "data/synthetic", eval_root: str = "evals/datasets",
                    covered_rule: str = "graded", retriever_name: str = "hybrid", lexical_threshold: float | None = None):
    items = json.loads(Path(f"{eval_root}/synth_decision_{split}.json").read_text())["items"]
    persona_of = {i["job"]["job_id"]: i["persona"] for i in items}
    clients = {c["client_id"]: c for c in json.loads(Path(f"{data_root}/clients.json").read_text())}
    corpora = {p: Corpus.from_json(f"{data_root}/personas/{p}/portfolio.json", eligible_only=True) for p in set(persona_of.values())}
    cfg = copy.deepcopy(load_config())
    if lexical_threshold is not None:
        cfg["thresholds"]["lexical_support"] = lexical_threshold
    profiles = {p: json.loads(Path(f"{data_root}/personas/{p}/freelancer.json").read_text()) for p in set(persona_of.values())}

    def predict(job: dict) -> dict:
        corpus = corpora[persona_of[job["job_id"]]]
        retr = Composed(corpus, hybrid=(retriever_name == "hybrid"), name="baseline")
        market = InMemoryMarketplace({job["job_id"]: job}, clients)
        d = Deps(llm=NullLLM(clients), market=market, retriever=retr, store=InMemoryStore(), cfg=cfg,
                 profiles={"u": profiles[persona_of[job["job_id"]]]})
        state = {"user_id": "u", "job_id": job["job_id"], "raw_job": job}
        risk = make_risk(d)(state)["risk"]
        risk.client_score = client_score(clients.get(job["client_id"], {}))
        fit = make_matcher(d)(state)["fit"]
        dec = make_decide(d)({**state, "risk": risk, "fit": fit})["decision"]
        return {"action": dec.action, "scam": risk.scam or risk.free_work_request or risk.off_platform_ask,
                "injection": risk.injection_detected, "fit": fit.score}
    return items, predict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--covered-rule", default="graded", choices=["graded"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--sweep", action="store_true", help="sweep the lexical support threshold")
    a = ap.parse_args()
    if a.sweep:
        rows = []
        for thr in (0.0, 0.1, 0.15, 0.2, 0.25, 0.34, 0.5):
            it, pr = build_predictor(a.split, lexical_threshold=thr)
            r = evaluate(it, pr)
            rows.append({"lexical_threshold": thr, "bid_recall": r["bid_or_skip"]["recall"], "bid_precision": r["bid_or_skip"]["precision"],
                         "bid_f1": r["bid_or_skip"]["f1"], "out_of_scope_acc": r["action_accuracy_by_class"]["out_of_scope"],
                         "good_fit_acc": r["action_accuracy_by_class"]["good_fit"]})
            print({k: round(v, 2) for k, v in rows[-1].items()})
        Path(f"evals/results/decision_lexical_sweep_{a.split}.json").write_text(json.dumps(
            {"meta": {"split": a.split, "synthetic": True, "note": "no threshold of a keyword judge achieves both"}, "rows": rows}, indent=2))
        return
    items, predict = build_predictor(a.split)
    res = evaluate(items, predict)
    res["meta"] = {"system": "rules-only baseline (no LLM; Matcher on lexical fallback)", "split": a.split,
                   "dataset": f"evals/datasets/synth_decision_{a.split}.json", "synthetic": True,
                   "stand_ins": ["no LLM", "HashEmbedder", "gold derived by generator rules"]}
    out = a.out or f"evals/results/decision_rules_AFTER_fixes_{a.split}.json"
    Path(out).write_text(json.dumps(res, indent=2))
    f = lambda x: "n/a" if x is None else f"{x:.2f}"
    print(f"bid-or-skip  P={res['bid_or_skip']['precision']:.2f} R={res['bid_or_skip']['recall']:.2f} F1={res['bid_or_skip']['f1']:.2f}")
    print(f"scam         P={res['scam']['precision']:.2f} R={res['scam']['recall']:.2f}  recall plain={f(res['scam_recall_plain'])} evasive={f(res['scam_recall_evasive'])}")
    print(f"injection    P={res['injection']['precision']:.2f} R={res['injection']['recall']:.2f}  lookalike false-flag={f(res['lookalike_false_flag_rate'])}")
    print("action accuracy by class:", {k: round(v, 2) for k, v in res["action_accuracy_by_class"].items()})


if __name__ == "__main__":
    main()
