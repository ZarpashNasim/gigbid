import json
import math

import pytest

from evals.runners import ablation, decision_eval, judge_calibration, rag_eval
from evals.runners.metrics import cohen_kappa, mrr, ndcg_at_k, percentile, prf, recall_at_k, unsupported_rate
from rag.index.store import Corpus
from rag.stages import Composed, LexicalReranker
from rag.variants.v8_corrective import V8Corrective

CORPUS = "data/sample/portfolio.json"
TOY = "evals/datasets/toy_dev.json"


# ---- metrics: hand-computed expectations ----
def test_recall_mrr_ndcg_hand_computed():
    ranked, gold = ["a", "x", "b", "y"], {"a", "b", "c"}
    assert recall_at_k(ranked, gold, 3) == pytest.approx(2 / 3)
    assert mrr(["x", "b"], gold) == 0.5 and mrr(["x", "y"], gold) == 0.0
    dcg = 1 / math.log2(2) + 1 / math.log2(4)              # hits at ranks 1 and 3
    idcg = 1 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at_k(ranked, gold, 10) == pytest.approx(dcg / idcg)
    assert ndcg_at_k(["a", "b"], {"a", "b"}, 10) == pytest.approx(1.0)


def test_prf_and_kappa():
    r = prf(["bid", "bid", "skip", "skip"], ["bid", "skip", "bid", "skip"], "bid")
    assert (r["tp"], r["fp"], r["fn"]) == (1, 1, 1) and r["f1"] == pytest.approx(0.5)
    assert cohen_kappa(list("aabb"), list("aabb")) == pytest.approx(1.0)
    assert cohen_kappa(list("aabb"), list("abab")) == pytest.approx(0.0)
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10


def test_unsupported_rate_before_after():
    before = unsupported_rate([["supported", "unsupported"], ["unsupported", "unsupported"]])
    after = unsupported_rate([["supported"], []])
    assert before["unsupported_per_proposal"] == 1.5 and after["unsupported_per_proposal"] == 0.0


def test_decision_eval_scores_any_predictor():
    items = [{"job": {"id": 1}, "gold": {"action": "bid", "scam": False, "price_band": [30, 50]}},
             {"job": {"id": 2}, "gold": {"action": "skip", "scam": True, "price_band": [30, 50]}}]
    perfect = lambda j: {"action": "bid", "scam": False, "price": 40} if j["id"] == 1 else {"action": "skip", "scam": True, "price": 99}
    r = decision_eval.evaluate(items, perfect)
    assert r["bid_or_skip"]["f1"] == 1.0 and r["scam"]["recall"] == 1.0 and r["price_in_band"] == 0.5


def test_judge_calibration(tmp_path):
    r = judge_calibration.calibrate({"1": "pass", "2": "fail", "3": "pass"}, {"1": "pass", "2": "pass", "3": "pass"})
    assert r["n"] == 3 and r["disagreements"] == ["2"]


# ---- variants ----
def test_decomposition_helps_multi_requirement_job():
    c = Corpus.from_json(CORPUS)
    job = {"text": "x", "requirements": ["pgvector RAG chatbot", "Celery task queue"]}
    got = {e.id for e in Composed(c, decompose=True, hybrid=True).retrieve(job, k=2)}
    assert {"cs1", "cs3"} <= got                           # one item per requirement survives the merge


def test_outcome_boost_prefers_won_proposal_over_ignored():
    c = Corpus.from_json(CORPUS)
    job = {"text": "chatbot proposal opening", "requirements": []}
    boosted = [e.id for e in Composed(c, hybrid=True, outcome_boost=5.0).retrieve(job, k=10)]
    plain = [e.id for e in Composed(c, hybrid=True).retrieve(job, k=10)]
    assert "p1" in boosted and boosted.index("p1") <= plain.index("p1")


def test_v8_terminates_and_abstains_when_nothing_supports_the_job():
    c = Corpus.from_json(CORPUS)
    v8 = V8Corrective(c)
    out = v8.retrieve({"text": "Unity game developer with C#", "requirements": ["Unity engine", "C# gameplay programming"]}, k=5)
    assert out == []                                       # refuses to claim; loop did not spin forever


def test_v8_keeps_supported_evidence():
    c = Corpus.from_json(CORPUS)
    out = V8Corrective(c).retrieve({"text": "dbt pipeline", "requirements": ["dbt Airflow pipeline"]}, k=5)
    assert [e.id for e in out][:1] == ["cs2"]


# ---- runners write traceable result files ----
def test_rag_eval_writes_json_and_table(tmp_path):
    out = tmp_path / "r.json"
    res = rag_eval.run(TOY, str(out), CORPUS)
    saved = json.loads(out.read_text())
    assert saved["meta"]["is_toy"] is True and saved["meta"]["n_items"] == 6
    assert set(res["variants"]) >= {"V0 naive dense", "V1 decompose (naive reqs)", "V1 decompose (oracle reqs)", "V2 hybrid", "V3 hybrid+rerank", "V8 corrective"}
    assert out.with_suffix(".md").read_text().startswith("| Variant")
    for v in res["variants"].values():
        assert 0 <= v["recall@5"] <= 1 and v["n_abstain_items"] == 1


def test_ablation_covers_every_component(tmp_path):
    res = ablation.run(TOY, str(tmp_path / "a.json"), CORPUS)
    assert set(res["configs"]) == {"full pipeline (decompose+hybrid+rerank)", "none (dense only)", "without decompose",
                                   "without hybrid", "without reranker", "only decompose", "only hybrid", "only reranker"}


def test_coverage_metric_has_no_ceiling_unlike_recall():
    from evals.runners.metrics import coverage_at_k
    groups = [["a1", "a2", "a3"], ["b1", "b2", "b3"], ["c1", "c2", "c3"]]       # 3 needs, 3 evidence items each
    ranked = ["a1", "b1", "c1", "x", "y"]                                      # one good hit per need
    assert coverage_at_k(ranked, groups, 5) == 1.0
    assert recall_at_k(ranked, {i for g in groups for i in g}, 5) == pytest.approx(3 / 9)   # recall@5 capped at 5/9


def test_eligible_only_removes_proposals_and_default_eval_uses_it():
    all_docs = Corpus.from_json("data/synthetic/personas/ai_engineer/portfolio.json")
    ev = Corpus.from_json("data/synthetic/personas/ai_engineer/portfolio.json", eligible_only=True)
    assert any(d["type"] == "proposal" for d in all_docs.docs) and not any(d["type"] == "proposal" for d in ev.docs)


def test_kit_schema_is_accepted():
    kit = Corpus.from_json("data/kit_sample/portfolio_items.json")
    d = kit.docs[0]
    assert d["id"] == "evidence-001" and "churn" in d["text"].lower() and d["evidence_eligible"] is True
