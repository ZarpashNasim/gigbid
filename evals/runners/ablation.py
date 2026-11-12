"""Ablate the pipeline one component at a time (R&D question B), on the same dataset formats as rag_eval.

python -m evals.runners.ablation --dataset evals/datasets/synth_retrieval_dev.json --out evals/results/ablation_synth_dev.json

Components: decompose (per-requirement retrieval from the naive splitter), hybrid (BM25+dense), reranker.
`outcome_boost` is not ablated here: it only re-ranks past proposals, which are not in the evidence index.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.runners.rag_eval import collect, load_groups, summarise
from rag.index.store import Corpus
from rag.stages import Composed, LexicalReranker

FULL = {"decompose": True, "hybrid": True, "reranker": True}


def build(corpus: Corpus, flags: dict) -> Composed:
    return Composed(corpus, decompose=flags["decompose"], hybrid=flags["hybrid"],
                    reranker=LexicalReranker() if flags["reranker"] else None)


def run(dataset_path: str, out: str, corpus_path: str | None = None, root: str | None = None) -> dict:
    ds = json.loads(Path(dataset_path).read_text())
    groups = load_groups(ds, corpus_path, root)
    configs = {"full pipeline (decompose+hybrid+rerank)": FULL, "none (dense only)": {k: False for k in FULL}}
    for comp in FULL:
        configs[f"without {comp}"] = {**FULL, comp: False}
    for comp in FULL:
        configs[f"only {comp}"] = {k: k == comp for k in FULL}
    res = {"meta": {"dataset": dataset_path, "synthetic": ds.get("synthetic", False), "is_toy": ds.get("is_toy", False),
                    "stand_ins": ["HashEmbedder", "LexicalReranker"]}, "configs": {}}
    for name, flags in configs.items():
        acc = [[], [], []]
        for corpus, items in groups.values():
            for slot, part in zip(acc, collect(build(corpus, flags), items)):
                slot += part
        r = summarise(*acc)
        res["configs"][name] = {k: v for k, v in r.items() if k not in ("per_item", "abstain_items")}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--dataset", default="evals/datasets/synth_retrieval_dev.json")
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", default="evals/results/ablation_synth_dev.json")
    a = ap.parse_args()
    for n, r in run(a.dataset, a.out, a.corpus, a.root)["configs"].items():
        print(f"{n:42s} recall@5={r['recall@5']:.3f} coverage@5={r['coverage@5']:.3f} mrr={r['mrr']:.3f} ndcg@10={r['ndcg@10']:.3f}")
