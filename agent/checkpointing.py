"""Durable checkpointer factory (C6). Postgres in production, sqlite for local dev/tests.

CHECKPOINT_URL=postgresql://...  -> PostgresSaver     (docker compose)
CHECKPOINT_URL=sqlite:///path.db -> SqliteSaver       (default; real on-disk persistence)
"""
from __future__ import annotations

import os
import sqlite3

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from agent import handoffs


def make_serde() -> JsonPlusSerializer:
    """Explicitly allow our own Pydantic hand-off types in checkpoints. LangGraph is moving to block
    unregistered types on deserialize; without this, resuming a paused approval could fail after an upgrade."""
    names = [n for n, v in vars(handoffs).items()
             if isinstance(v, type) and v.__module__ == handoffs.__name__ and n != "BaseModel"]
    return JsonPlusSerializer(allowed_msgpack_modules=[("agent.handoffs", n) for n in names])


def make_checkpointer(url: str | None = None):
    url = url or os.environ.get("CHECKPOINT_URL", "sqlite:///gigbid_checkpoints.db")
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres import PostgresSaver   # pip install langgraph-checkpoint-postgres
        from psycopg import Connection
        conn = Connection.connect(url, autocommit=True, prepare_threshold=0)
        saver = PostgresSaver(conn, serde=make_serde())
        saver.setup()
        return saver
    from langgraph.checkpoint.sqlite import SqliteSaver
    path = url.removeprefix("sqlite:///")
    saver = SqliteSaver(sqlite3.connect(path, check_same_thread=False), serde=make_serde())
    saver.setup()
    return saver
