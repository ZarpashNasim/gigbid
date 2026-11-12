"""Idempotency store (sqlite, survives restarts), per-user rate limiter, append-only audit log, request context."""
from __future__ import annotations

import contextvars
import json
import sqlite3
import threading
import time
from pathlib import Path

current_user: contextvars.ContextVar[str] = contextvars.ContextVar("current_user", default="local")
current_trace: contextvars.ContextVar[str] = contextvars.ContextVar("current_trace", default="-")


class IdempotencyStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("create table if not exists idem (key text primary key, result text)")
        self.lock = threading.Lock()

    def run_once(self, key: str, fn):
        """Run fn at most once per key; a retry returns the stored result and does NOT call fn again."""
        with self.lock:
            row = self.db.execute("select result from idem where key=?", (key,)).fetchone()
            if row:
                return json.loads(row[0]), True
            result = fn()
            self.db.execute("insert into idem values (?,?)", (key, json.dumps(result)))
            self.db.commit()
            return result, False


class RateLimiter:
    """Token bucket per user, kept under GigSim's published limit (20 requests/minute; see gigsim/README.md)."""
    def __init__(self, rate_per_s: float = 20 / 60, burst: int = 20, clock=time.monotonic):
        self.rate, self.burst, self.clock = rate_per_s, burst, clock
        self.state: dict[str, tuple[float, float]] = {}

    def check(self, user: str) -> None:
        now = self.clock()
        tokens, last = self.state.get(user, (float(self.burst), now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        if tokens < 1:
            raise RuntimeError("rate limit: slow down (client-side limiter)")
        self.state[user] = (tokens - 1, now)


class AuditLog:
    """Append-only JSONL: user, tool, arguments, result, trace id. Never rewritten."""
    def __init__(self, path: str | None = None):
        self.path, self.rows = (Path(path) if path else None), []

    def write(self, tool: str, args: dict, result: object, error: str | None = None):
        row = {"ts": time.time(), "user": current_user.get(), "trace_id": current_trace.get(),
               "tool": tool, "args": args, "result": result, "error": error}
        self.rows.append(row)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(row, default=str) + "\n")
