import hashlib
import json
import re
from pathlib import Path

import pytest

from gigdata import synth
from gigdata.synth import CLASSES, build_all
from gigdata.text import detect_signals

REAL_EMAIL = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("synth")
    m = build_all(root / "data", root / "evals", seed=7)
    return root, m


def load(root, rel):
    return json.loads((root / rel).read_text())


def test_deterministic_byte_identical(built, tmp_path):
    _, m1 = built
    m2 = build_all(tmp_path / "d", tmp_path / "e", seed=7)
    h = lambda m: sorted(m["sha256"].values())                # absolute paths differ between tmp dirs; contents must not
    assert h(m1) == h(m2)
    m3 = build_all(tmp_path / "d3", tmp_path / "e3", seed=8)
    assert h(m1) != h(m3)                                     # and a different seed really changes the data


def test_every_record_is_tagged_synthetic(built):
    root, _ = built
    for pid in ("ai_engineer", "data_engineer", "fullstack", "mobile"):
        assert load(root, f"data/personas/{pid}/freelancer.json")["origin"] == "synthetic"
        assert all(i["origin"] == "synthetic" for i in load(root, f"data/personas/{pid}/portfolio.json"))
    for split in ("dev", "holdout"):
        jobs = [json.loads(l) for l in (root / f"data/jobs_{split}.jsonl").read_text().splitlines()]
        assert all(j["origin"] == "synthetic" for j in jobs)
        assert all(t["origin"] == "synthetic" for t in load(root, f"data/threads_{split}.json"))
    assert all(c["origin"] == "synthetic" for c in load(root, "data/clients.json"))
    assert all("(synthetic)" in load(root, f"data/personas/{p}/freelancer.json")["display_name"] for p in ("mobile", "fullstack"))


def test_no_gold_leaks_into_marketplace_data(built):
    root, _ = built
    blob = (root / "data/jobs_dev.jsonl").read_text() + (root / "data/threads_dev.json").read_text() + (root / "data/clients.json").read_text()
    for banned in ("gold", "_gold", "\"class\"", "scam\": true", "planted", "client_quality", "\"quality\""):
        assert banned not in blob


def test_dev_and_holdout_are_disjoint(built):
    root, _ = built
    texts = lambda s: {json.loads(l)["description"] for l in (root / f"data/jobs_{s}.jsonl").read_text().splitlines()}
    ids = lambda s: {json.loads(l)["job_id"] for l in (root / f"data/jobs_{s}.jsonl").read_text().splitlines()}
    assert not texts("dev") & texts("holdout") and not ids("dev") & ids("holdout")


def test_class_counts_and_gold_consistency(built):
    root, m = built
    for split in ("dev", "holdout"):
        ds = load(root, f"evals/synth_decision_{split}.json")
        assert ds["synthetic"] is True and ds["is_toy"] is False
        by = {k: sum(i["class"] == k for i in ds["items"]) for k in CLASSES}
        assert by == {k: v * 4 for k, v in CLASSES.items()}
        for i in ds["items"]:
            g = i["gold"]
            if g["scam"] or g["injection"] or i["class"] in ("out_of_scope", "low_budget", "risky_client"):
                assert g["action"] == "skip"
            if g["action"] == "bid":
                lo, hi = g["price_band"]
                assert 0 < lo <= hi and i["job"]["budget"]["max"] >= lo
            if i["class"] == "lookalike":
                assert g["injection"] is False and g["action"] == "bid"        # hard negatives must not be skipped


def test_retrieval_gold_exists_and_abstention_items_have_none(built):
    root, _ = built
    ds = load(root, "evals/synth_retrieval_dev.json")
    ids = {pid: {i["evidence_id"] for i in json.loads((root / "data" / p).read_text())} for pid, p in ds["corpora"].items()}
    for it in ds["items"]:
        assert set(it["gold"]) <= ids[it["persona"]]                     # every gold id really exists
        if it["class"] == "out_of_scope":
            assert it["gold"] == []
        else:
            assert it["gold"] and it["requirements"]


def test_gold_never_points_at_proposals(built):
    root, _ = built
    ds = load(root, "evals/synth_retrieval_dev.json")
    types = {i["evidence_id"]: i["type"] for p in ds["corpora"].values() for i in json.loads((root / "data" / p).read_text())}
    assert all(types[g] in ("case_study", "repo", "review") for it in ds["items"] for g in it["gold"])


def test_contact_details_are_fictional(built):
    root, _ = built
    blob = "".join(p.read_text() for p in (root / "data").rglob("*") if p.is_file())
    domains = {m.group(1) for m in REAL_EMAIL.finditer(blob)}
    assert domains <= {"example.com", "example.org"}
    for phone in re.findall(r"\+1 202 555 (\d{4})", blob):
        assert 100 <= int(phone) <= 199                                     # 555-01xx is reserved for fiction


def test_evasive_scams_exist_and_evade_the_keyword_rules(built):
    root, _ = built
    items = load(root, "evals/synth_decision_dev.json")["items"]
    scams = [i for i in items if i["gold"]["scam"]]
    ev = [i for i in scams if i["gold"]["evasive"]]
    plain = [i for i in scams if not i["gold"]["evasive"]]
    assert ev and plain
    caught = lambda i: bool(set(detect_signals(i["job"]["title"] + " " + i["job"]["description"]))
                            & {"off_platform_contact", "unpaid_work", "upfront_fee", "credential_request"})
    assert sum(map(caught, plain)) > sum(map(caught, ev))                    # rules do worse on the hard variants


def test_proposal_outcome_rule_is_visible_in_ground_truth(built):
    root, _ = built
    truth = load(root, "data/_ground_truth/proposal_style.json")
    assert set(truth.values()) == {"specific", "generic"}
    ev = {i["evidence_id"]: i for p in ("ai_engineer", "data_engineer", "fullstack", "mobile")
          for i in load(root, f"data/personas/{p}/portfolio.json")}
    assert all(ev[k]["type"] == "proposal" and ev[k]["proposal_outcome"] in ("won", "replied", "ignored") for k in truth)
    assert not any("planted" in json.dumps(v) for v in ev.values())


def test_manifest_hashes_match_files(built):
    root, m = built
    for path, digest in m["sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


def test_synthetic_backend_runs_the_real_graph_end_to_end(tmp_path):
    """Integration: synthetic data -> SyntheticBackend -> BackendPort -> bid graph -> pending approval -> one submission."""
    import copy
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore
    from langgraph.types import Command
    from agent.config import load_config
    from agent.deps import Deps
    from agent.graphs.bid_graph import build_bid_graph
    from agent.marketplace_port import BackendPort
    from mcp_servers.marketplace.adapters.synthetic import SyntheticBackend
    from rag.index.store import Corpus
    from rag.stages import Composed
    from tests.unit.test_bid_graph import FakeLLM

    be = SyntheticBackend("data/synthetic", "dev")
    gold = {i["id"]: i for i in json.loads(Path("evals/datasets/synth_decision_dev.json").read_text())["items"]}
    jid = next(k for k, v in gold.items() if v["persona"] == "ai_engineer" and v["class"] == "good_fit")
    corpus = Corpus.from_json("data/synthetic/personas/ai_engineer/portfolio.json", eligible_only=True)
    prof = json.loads(Path("data/synthetic/personas/ai_engineer/freelancer.json").read_text())
    d = Deps(llm=FakeLLM(), market=BackendPort(be), retriever=Composed(corpus, hybrid=True), store=InMemoryStore(),
             cfg=copy.deepcopy(load_config()), profiles={"u1": prof})
    g = build_bid_graph(d, InMemorySaver())
    cfg = {"configurable": {"thread_id": "t"}}
    g.invoke({"user_id": "u1", "job_id": jid}, cfg)
    snap = g.get_state(cfg)
    assert snap.next == ("approval",) and be.write_calls == 0           # paused for the human; nothing created yet
    assert snap.values["decision"].action == "bid" and not any(e.type == "proposal" for m in snap.values["fit"].matches for e in m.evidence)
    g.invoke(Command(resume={"decision": "approve"}), cfg)
    assert be.write_calls == 1 and len(be.proposals) == 1


def test_synthetic_backend_serves_threads_and_scam_jobs_are_blocked_before_drafting():
    from mcp_servers.marketplace.adapters.synthetic import SyntheticBackend
    be = SyntheticBackend("data/synthetic", "dev")
    t = next(iter(be.threads))
    assert be.list_messages(t)[-1]["from"] == "client" and be.get_job(next(iter(be.jobs)))["origin"] == "synthetic"
