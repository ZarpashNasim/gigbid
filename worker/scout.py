"""Scout worker logic: run saved searches, dedupe, queue new jobs. Idempotent: a worker restart or a
retried task never queues (hence never analyses or submits) the same job twice.

Scheduling wrapper (Celery beat / Arq cron) lives in worker/tasks.py and just calls `scout_once`.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Callable


def fingerprint(job: dict) -> str:
    """Near-duplicate key: same title+description after normalising case/punctuation/whitespace."""
    text = re.sub(r"[^a-z0-9]+", " ", (job["title"] + " " + job["description"]).lower()).strip()
    return hashlib.sha256(text.encode()).hexdigest()[:20]


class SeenStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("create table if not exists seen (user_id text, fp text, job_id text, primary key (user_id, fp))")

    def add_if_new(self, user_id: str, job: dict) -> bool:
        cur = self.db.execute("insert or ignore into seen values (?,?,?)", (user_id, fingerprint(job), job["id"]))
        self.db.commit()
        return cur.rowcount == 1


def scout_once(user_id: str, queries: list[str], search: Callable[[str, int], list[dict]],
               seen: SeenStore, enqueue: Callable[[str, str], None], limit: int = 20) -> list[str]:
    """Returns job ids newly queued. `search` is the marketplace port's search (rate-limited server-side)."""
    queued: list[str] = []
    for q in queries:
        for job in search(q, limit):
            if seen.add_if_new(user_id, job):
                enqueue(user_id, job["id"])
                queued.append(job["id"])
    return queued
