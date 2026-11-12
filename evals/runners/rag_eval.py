"""Retrieval evaluation. One command reruns the whole variant comparison and writes results + table.

python -m evals.runners.rag_eval --dataset evals/datasets/synth_retrieval_dev.json --out evals/results/rag_synth_dev.json

Dataset formats:
  single corpus : {"items": [...]} with --corpus path
  multi persona : {"corpora_root": "data/synthetic", "corpora": {persona: relative path}, "items": [{persona, ...}]}

Every number in README/report must trace to a file in evals/results/. Each result records the dataset, whether it is
synthetic/toy, and which stand-in components (placeholder embedder, lexical reranker) produced it.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from evals.runners.metrics import coverage_at_k, mrr, ndcg_at_k, percentile, recall_at_k
from rag.index.store import Corpus
from rag.variants import v1_decompose, v3_rerank, v4_outcome
from rag.variants.v0_naive import V0Naive
from rag.variants.v2_hybrid import V2Hybrid
from rag.variants.v8_corrective import V8Corrective


class OracleReqs:
    """Feeds a variant the dataset's oracle requirement list instead of the naive sentence splitter: the upper bound
    for what a good Analyst agent could give V1, so the cost of weak requirement extraction can be measured."""
    def __init__(self, v, name): self.v, self.name = v, name
    def retrieve(self, job, k=5):
        return self.v.retrieve({**job, "requirements": job.get("requirements_oracle") or job["requirements"]}, k)


def variants(corpus: Corpus, reranker=None, grader=None) -> dict:
    return {
        "V0 naive dense": V0Naive(corpus),
        "V1 decompose (naive reqs)": v1_decompose.make(corpus),
        "V1 decompose (oracle reqs)": OracleReqs(v1_decompose.make(corpus), "oracle"),
        "V2 hybrid": V2Hybrid(corpus),
        "V3 hybrid+rerank": v3_rerank.make(corpus, reranker=reranker),
        "V4 outcome-aware": v4_outcome.make(corpus, reranker=reranker),
        "V8 corrective": V8Corrective(corpus, grader=grader),
    }


def group_of(item: dict) -> str:
    n = item.get("n_requirements", len(item.get("requirements", [])))
    return "4+ requirements" if n >= 4 else "1-3 requirements"


def collect(v, items: list[dict]) -> tuple[list, list, list]:
    """Run one variant over items. Items with no gold are abstention checks (the right output is NO evidence)."""
    rows, lat, abstain = [], [], []
    for it in items:
        t0 = time.perf_counter()
        ids = [e.id for e in v.retrieve({"text": it["text"], "requirements": it.get("requirements", []),
                                         "requirements_oracle": it.get("requirements_oracle")}, k=10)]
        lat.append(time.perf_counter() - t0)
        gold = set(it["gold"])
        if not gold:
            abstain.append({"id": it["id"], "returned": ids[:5], "abstained": not ids})
            continue
        rows.append({"id": it["id"], "group": group_of(it), "recall@5": recall_at_k(ids, gold, 5),
                     "mrr": mrr(ids, gold), "ndcg@10": ndcg_at_k(ids, gold, 10), "returned": ids[:5],
                     "coverage@5": coverage_at_k(ids, it.get("gold_groups") or [list(gold)], 5)})
    return rows, lat, abstain


def summarise(rows: list, lat: list, abstain: list) -> dict:
    mean = lambda key, rs=None: (lambda r: sum(x[key] for x in r) / len(r) if r else 0.0)(rows if rs is None else rs)
    groups = {g: {m: mean(m, [r for r in rows if r["group"] == g]) for m in ("recall@5", "coverage@5", "mrr", "ndcg@10")}
              | {"n": sum(r["group"] == g for r in rows)} for g in sorted({r["group"] for r in rows})}
    return {"recall@5": mean("recall@5"), "coverage@5": mean("coverage@5"), "mrr": mean("mrr"), "ndcg@10": mean("ndcg@10"), "n_scored": len(rows),
            "p50_ms": 1000 * percentile(lat, 50), "p95_ms": 1000 * percentile(lat, 95),
            "abstain_rate": (sum(a["abstained"] for a in abstain) / len(abstain)) if abstain else None,
            "n_abstain_items": len(abstain), "by_group": groups, "per_item": rows, "abstain_items": abstain}


def score_variant(v, items: list[dict], k: int = 5) -> dict:
    return summarise(*collect(v, items))


def markdown_table(res: dict) -> str:
    lines = ["| Variant | Recall@5 | Coverage@5 | MRR | nDCG@10 | Abstain rate | p95 ms |", "|---|---|---|---|---|---|---|"]
    for name, r in res["variants"].items():
        ab = "n/a" if r["abstain_rate"] is None else f"{r['abstain_rate']:.2f}"
        lines.append(f"| {name} | {r['recall@5']:.3f} | {r['coverage@5']:.3f} | {r['mrr']:.3f} | {r['ndcg@10']:.3f} | {ab} | {r['p95_ms']:.1f} |")
    return "\n".join(lines)


def load_groups(ds: dict, corpus_path=None, root=None, embedder=None, eligible_only: bool = True) -> dict:
    """persona -> (Corpus, items). Shared by the variant comparison and the ablation."""
    if "corpora" in ds:
        base = Path(root or ds.get("corpora_root", "."))
        kw = {"eligible_only": eligible_only, **({"embedder": embedder} if embedder else {})}
        return {p: (Corpus.from_json(base / rel, **kw), [i for i in ds["items"] if i["persona"] == p])
                for p, rel in ds["corpora"].items()}
    return {"_": (Corpus.from_json(corpus_path or "data/sample/portfolio.json", eligible_only=eligible_only), ds["items"])}


def run(dataset_path: str, out: str, corpus_path: str | None = None, root: str | None = None, embedder=None,
        eligible_only: bool = True, reranker=None, grader=None,
        embedder_name: str | None = None, reranker_name: str | None = None,
        grader_name: str | None = None, llm_name: str | None = None, limit: int | None = None) -> dict:
    from rag.stages import LLM_FALLBACKS
    LLM_FALLBACKS["reranker"] = LLM_FALLBACKS["grader"] = 0          # reset per run so meta counts only this run
    ds = json.loads(Path(dataset_path).read_text())
    if limit:                                                       # quick validation runs (e.g. rate-limit probing)
        ds = {**ds, "items": ds["items"][:limit]}
    groups = load_groups(ds, corpus_path, root, embedder, eligible_only)
    acc: dict[str, list] = {}
    for _persona, (corpus, items) in groups.items():
        for name, v in variants(corpus, reranker, grader).items():
            rows, lat, ab = collect(v, items)
            a = acc.setdefault(name, [[], [], []])
            a[0] += rows; a[1] += lat; a[2] += ab
    first = next(iter(groups.values()))[0]
    emb_name = embedder_name or type(first.embedder).__name__
    rr_name = reranker_name or "LexicalReranker(stand-in)"
    gr_name = grader_name or "V8 grader (lexical)"
    is_standin = lambda s: any(w in s.lower() for w in ("stand-in", "lexical", "hashembedder", "no key"))
    stand_ins = [c for c, nm in (("embedder", emb_name), ("reranker", rr_name), ("V8 grader", gr_name)) if is_standin(nm)]
    res = {"meta": {"dataset": dataset_path, "split": ds.get("split"), "n_items": len(ds["items"]), "personas": sorted(groups),
                    "eligible_only": eligible_only, "synthetic": ds.get("synthetic", False), "is_toy": ds.get("is_toy", False),
                    "generator_version": ds.get("generator_version"), "dataset_note": ds.get("note"),
                    "embedder": emb_name, "reranker": rr_name, "v8_grader": gr_name, "llm": llm_name,
                    "llm_fallbacks": dict(LLM_FALLBACKS), "stand_in_components": stand_ins},
           "variants": {n: summarise(*a) for n, a in acc.items()}}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=2))
    Path(out).with_suffix(".md").write_text(markdown_table(res) + "\n")
    return res


if __name__ == "__main__":
    from rag.components import load_env, make_embedder, make_grader, make_llm, make_reranker

    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--dataset", default="evals/datasets/toy_dev.json")
    ap.add_argument("--root", default=None, help="overrides the dataset's corpora_root")
    ap.add_argument("--out", default="evals/results/rag_toy.json")
    ap.add_argument("--mixed", action="store_true", help="index past proposals together with evidence (stress test)")
    ap.add_argument("--embedder", default="hash", help="hash | ollama[:model]")
    ap.add_argument("--reranker", default="lexical", help="lexical | llm")
    ap.add_argument("--grader", default="lexical", help="lexical | llm  (V8 support grader)")
    ap.add_argument("--profile", default=None, help="override active LLM profile in agent/config.yaml (e.g. groq)")
    ap.add_argument("--limit", type=int, default=None, help="only score the first N items (quick validation)")
    a = ap.parse_args()
    load_env()
    llm, llm_name = make_llm(a.profile) if (a.reranker == "llm" or a.grader == "llm") else (None, None)
    embedder, emb_name = make_embedder(a.embedder)
    reranker, rr_name = make_reranker(a.reranker, llm)
    grader, gr_name = make_grader(a.grader, llm)
    r = run(a.dataset, a.out, a.corpus, a.root, embedder=embedder, eligible_only=not a.mixed,
            reranker=reranker, grader=grader, embedder_name=emb_name, reranker_name=rr_name,
            grader_name=gr_name, llm_name=llm_name, limit=a.limit)
    print(markdown_table(r))
    m = r["meta"]
    print(f"\ndataset={m['dataset']} synthetic={m['synthetic']} toy={m['is_toy']}")
    print(f"components: embedder={m['embedder']} reranker={m['reranker']} v8_grader={m['v8_grader']} llm={m['llm']}")
    print(f"stand-ins remaining: {m['stand_in_components']}")
    if m["is_toy"] or m["synthetic"]:
        print("NOT real-world ground truth: report these as synthetic-dev results, with the stand-ins named.")
