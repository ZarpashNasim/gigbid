"""Step 6 - two controlled A/B experiments on the synthetic dev jobs.

The LLM is held fixed (a deterministic scripted stand-in) in every arm, so each measured difference is
attributable to the ONE factor varied. Offline, free, reproducible; every number is written to
evals/results/. These are synthetic-data, fixed-LLM results: they isolate the *pipeline's* structural
effects, not LLM-quality interactions.

  Experiment A  - factor: RAG retrieval variant (V0 naive / V2 hybrid / V3 hybrid+rerank).
                  Retrieval feeds the Matcher (d.retriever.search), whose fit score drives the bid/skip
                  decision, so a better retriever can change what the agent decides to bid on.
                  Metrics: bid/watch/skip rates, mean fit score, mean requirement coverage.

  Experiment B  - factor: graph topology (full multi-agent bid graph vs a single-agent one-shot writer).
                  Metrics: unsafe-proposal rate on scam/injection jobs (deterministic risk rules),
                  unsupported-claim rate in produced proposals (claim verifier), and LLM calls (cost).

Run:  py -m evals.runners.ab_experiments --split dev
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.config import load_config
from agent.deps import Deps
from agent.graphs.bid_graph import build_bid_graph
from agent.handoffs import (Claim, Critique, FitGrade, JobSpec, PriceQuote, ProposalDraft, ReqGrade,
                            Requirement, RiskReport)
from agent.marketplace_port import InMemoryMarketplace
from agent.nodes.writing import _Claims
from agent.rules import detect_signals
from rag.index.store import Corpus
from rag.stages import LexicalReranker
from rag.variants import v3_rerank
from rag.variants.v0_naive import V0Naive
from rag.variants.v2_hybrid import V2Hybrid

MOON = "I also walked on the moon."                       # a planted unsupported claim the verifier should strip
LETTER = f"I built a RAG chatbot. {MOON}"
NOT_PRODUCED = {"skipped", "blocked", "needs_attention", "dead_letter"}


class ScriptedLLM:
    """Fixed outputs per node so the LLM is a constant across arms. Risk is benign here; the deterministic
    rules in agent/rules.py add the real scam/injection flags.

    `grade` controls the Matcher's support grader (held constant within an experiment):
      True  - a generous grader marks every retrieved id as supporting (fit saturates; used in Exp B,
              where topology, not retrieval, is the factor).
      False - the grader is 'unavailable', so the Matcher falls back to its strict lexical support check
              (keyword overlap with the retrieved text). Coverage then reflects retrieval *quality*, which
              is what Exp A varies."""
    def __init__(self, grade: bool = True):
        self.calls: list[str] = []
        self.grade = grade

    def structured(self, node, schema, system, user):
        self.calls.append(node)
        if schema is FitGrade:
            if not self.grade:
                raise RuntimeError("grader unavailable -> strict lexical fallback")
            blocks = re.split(r"(?m)^REQ (\d+):", user)[1:]
            grades = [ReqGrade(index=int(blocks[i]), supported_ids=re.findall(r"\[([\w.-]+)\]", blocks[i + 1]))
                      for i in range(0, len(blocks), 2)]
            return FitGrade(grades=grades), 5
        if schema is JobSpec:
            return JobSpec(job_id="x", title="t", requirements=[Requirement(text="RAG")]), 10
        if schema is RiskReport:
            return RiskReport(client_score=0.9), 10
        if schema is PriceQuote:
            return PriceQuote(amount=40, connects_cost=8, rationale="market median"), 10
        if schema is ProposalDraft:
            return ProposalDraft(cover_letter=LETTER), 20
        if schema is _Claims:
            return _Claims(claims=[Claim(text=MOON, status="unsupported")]), 10
        if schema is Critique:
            return Critique(ok=True), 10
        raise AssertionError(f"unexpected schema {schema}")


def load_job_groups(split: str) -> dict[str, list[dict]]:
    rows = [json.loads(l) for l in Path(f"data/synthetic/jobs_{split}.jsonl").read_text().splitlines() if l.strip()]
    groups: dict[str, list[dict]] = {}
    for j in rows:
        persona = j["job_id"].split("-")[2]           # syn-<split>-<persona>-NNN
        groups.setdefault(persona, []).append(j)
    return groups


def make_retriever(arm: str, corpus: Corpus):
    if arm == "V0 naive dense":
        return V0Naive(corpus)
    if arm == "V2 hybrid":
        return V2Hybrid(corpus)
    if arm == "V3 hybrid+rerank":
        return v3_rerank.make(corpus, reranker=LexicalReranker())
    raise ValueError(arm)


def _graph_for(persona_jobs: list[dict], retriever, llm):
    market = InMemoryMarketplace({j["job_id"]: j for j in persona_jobs}, {})
    deps = Deps(llm=llm, market=market, retriever=retriever, store=InMemoryStore(), cfg=copy.deepcopy(load_config()))
    return build_bid_graph(deps, InMemorySaver())


def run_bid(graph, llm, job_id: str) -> tuple[dict, int]:
    llm.calls.clear()
    cfg = {"configurable": {"thread_id": job_id}}
    graph.invoke({"user_id": "u1", "job_id": job_id}, cfg)   # pauses at the approval interrupt for bid jobs
    return graph.get_state(cfg).values, len(llm.calls)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# ---------------------------------------------------------------- Experiment A
def experiment_a(split: str) -> dict:
    groups = load_job_groups(split)
    arms = ["V0 naive dense", "V2 hybrid", "V3 hybrid+rerank"]
    results = {}
    for arm in arms:
        actions, fits, covers = [], [], []
        for persona, jobs in groups.items():
            corpus = Corpus.from_json(f"data/synthetic/personas/{persona}/portfolio.json", eligible_only=True)
            llm = ScriptedLLM(grade=False)       # strict lexical grader held constant; retrieval is the factor
            graph = _graph_for(jobs, make_retriever(arm, corpus), llm)
            for j in jobs:
                vals, _ = run_bid(graph, llm, j["job_id"])
                dec = vals.get("decision")
                fit = vals.get("fit")
                actions.append(dec.action if dec else "skip")
                fits.append(fit.score if fit else 0.0)
                covers.append(_mean([float(m.covered) for m in fit.matches]) if fit and fit.matches else 0.0)
        n = len(actions)
        results[arm] = {
            "n_jobs": n,
            "bid_rate": actions.count("bid") / n,
            "watch_rate": actions.count("watch") / n,
            "skip_rate": actions.count("skip") / n,
            "mean_fit_score": _mean(fits),
            "mean_coverage": _mean(covers),
        }
    return {"experiment": "A: retrieval variant -> bid decisions",
            "factor": "RAG retrieval variant (LLM held fixed)",
            "meta": {"split": split, "synthetic": True, "llm": "ScriptedLLM(fixed)",
                     "grader": "strict lexical (held constant)",
                     "note": "Grader held constant as the strict lexical check; coverage/fit reflect retrieval quality."},
            "arms": results}


# ---------------------------------------------------------------- Experiment B
def single_agent(job: dict, llm: ScriptedLLM) -> tuple[str, int]:
    """One LLM call: read the job, write a proposal. No risk rules, matcher, verifier or compliance."""
    llm.calls.clear()
    draft, _ = llm.structured("writer", ProposalDraft, "Write a proposal for this job.",
                              f"{job['title']}\n{job['description']}")
    return draft.cover_letter, len(llm.calls)


def experiment_b(split: str) -> dict:
    groups = load_job_groups(split)
    all_jobs = [j for js in groups.values() for j in js]
    risky = {j["job_id"]: bool(detect_signals(f"{j['title']}\n{j['description']}")) for j in all_jobs}
    n_risky = sum(risky.values())

    def summarise(rows: list[dict]) -> dict:
        produced = [r for r in rows if r["produced"]]
        risky_rows = [r for r in rows if risky[r["job_id"]]]
        return {
            "proposals_produced": len(produced),
            "unsafe_proposal_rate": (_mean([float(r["produced"]) for r in risky_rows]) if risky_rows else None),
            "unsupported_claim_rate": (_mean([float(MOON in r["letter"]) for r in produced]) if produced else None),
            "mean_llm_calls": _mean([r["calls"] for r in rows]),
        }

    # multi-agent arm: full bid graph, retrieval fixed at V2 (so topology is the only factor vs single-agent)
    multi_rows = []
    for persona, jobs in groups.items():
        corpus = Corpus.from_json(f"data/synthetic/personas/{persona}/portfolio.json", eligible_only=True)
        llm = ScriptedLLM()
        graph = _graph_for(jobs, make_retriever("V2 hybrid", corpus), llm)
        for j in jobs:
            vals, calls = run_bid(graph, llm, j["job_id"])
            draft = vals.get("draft")
            produced = draft is not None and vals.get("status") not in NOT_PRODUCED
            multi_rows.append({"job_id": j["job_id"], "produced": produced,
                               "letter": draft.cover_letter if draft else "", "calls": calls})

    # single-agent arm: one-shot writer, no guardrails
    single_rows = []
    llm = ScriptedLLM()
    for j in all_jobs:
        letter, calls = single_agent(j, llm)
        single_rows.append({"job_id": j["job_id"], "produced": True, "letter": letter, "calls": calls})

    return {"experiment": "B: single-agent vs multi-agent",
            "factor": "graph topology (LLM held fixed)",
            "meta": {"split": split, "synthetic": True, "llm": "ScriptedLLM(fixed)",
                     "n_jobs": len(all_jobs), "n_risky_jobs": n_risky,
                     "note": "unsafe = produced a proposal on a scam/injection job (agent/rules.py ground truth); "
                             "unsupported-claim rate = planted claim surviving in produced proposals."},
            "arms": {"multi-agent (full graph)": summarise(multi_rows),
                     "single-agent (one-shot writer)": summarise(single_rows)}}


# ---------------------------------------------------------------- output
def _fmt(v) -> str:
    return "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def table_a(res: dict) -> str:
    lines = ["| Arm | Bid rate | Watch rate | Skip rate | Mean fit | Mean coverage |", "|---|---|---|---|---|---|"]
    for arm, r in res["arms"].items():
        lines.append(f"| {arm} | {r['bid_rate']:.3f} | {r['watch_rate']:.3f} | {r['skip_rate']:.3f} | "
                     f"{r['mean_fit_score']:.3f} | {r['mean_coverage']:.3f} |")
    return "\n".join(lines)


def table_b(res: dict) -> str:
    m = res["meta"]
    lines = [f"jobs={m['n_jobs']} scam/injection jobs={m['n_risky_jobs']}",
             "| Arm | Proposals produced | Unsafe-proposal rate | Unsupported-claim rate | Mean LLM calls |",
             "|---|---|---|---|---|"]
    for arm, r in res["arms"].items():
        lines.append(f"| {arm} | {r['proposals_produced']} | {_fmt(r['unsafe_proposal_rate'])} | "
                     f"{_fmt(r['unsupported_claim_rate'])} | {r['mean_llm_calls']:.2f} |")
    return "\n".join(lines)


def write(res: dict, out: str, table: str) -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=2))
    Path(out).with_suffix(".md").write_text(table + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--experiment", default="both", choices=["a", "b", "both"])
    a = ap.parse_args()
    if a.experiment in ("a", "both"):
        ra = experiment_a(a.split)
        write(ra, f"evals/results/ab_retrieval_decisions_{a.split}.json", table_a(ra))
        print("Experiment A - retrieval variant -> bid decisions (synthetic, fixed LLM)\n" + table_a(ra) + "\n")
    if a.experiment in ("b", "both"):
        rb = experiment_b(a.split)
        write(rb, f"evals/results/ab_single_vs_multi_{a.split}.json", table_b(rb))
        print("Experiment B - single-agent vs multi-agent (synthetic, fixed LLM)\n" + table_b(rb) + "\n")
