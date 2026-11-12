from worker.scout import SeenStore, scout_once

J = lambda i, t="RAG bot", d="Need a RAG chatbot.": {"id": i, "title": t, "description": d}


def test_dedupes_near_duplicates_and_is_idempotent():
    jobs = [J("a"), J("b", t="rag BOT!", d="need a  RAG chatbot"), J("c", t="dbt pipeline", d="x")]
    seen, queue = SeenStore(), []
    enq = lambda u, j: queue.append(j)
    first = scout_once("u1", ["rag"], lambda q, n: jobs, seen, enq)
    again = scout_once("u1", ["rag"], lambda q, n: jobs, seen, enq)      # worker restart / retried task
    assert first == ["a", "c"] and again == [] and queue == ["a", "c"]


def test_seen_is_per_user():
    seen, q = SeenStore(), []
    scout_once("u1", ["x"], lambda *_: [J("a")], seen, lambda u, j: q.append((u, j)))
    scout_once("u2", ["x"], lambda *_: [J("a")], seen, lambda u, j: q.append((u, j)))
    assert q == [("u1", "a"), ("u2", "a")]
