"""Durable per-thread event log. The worker/executor appends node updates; SSE tails it live.

Because events are stored (not held in memory), a client that connects late or reconnects after a
refresh gets the full history and then the live tail.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any


def jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "value"):          # langgraph Interrupt
        return jsonable(obj.value)
    return str(obj)


class EventLog:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("create table if not exists events (id integer primary key autoincrement,"
                        " thread_id text, kind text, data text)")
        self.lock = threading.Lock()

    def append(self, thread_id: str, kind: str, data: Any) -> None:
        with self.lock:
            self.db.execute("insert into events (thread_id, kind, data) values (?,?,?)",
                            (thread_id, kind, json.dumps(jsonable(data))))
            self.db.commit()

    def after(self, thread_id: str, last_id: int = 0) -> list[tuple[int, str, str]]:
        with self.lock:
            return self.db.execute("select id, kind, data from events where thread_id=? and id>? order by id",
                                   (thread_id, last_id)).fetchall()
