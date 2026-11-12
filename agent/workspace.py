"""Workspace port (calendar slots, tentative holds, email drafts).
The Workspace MCP server wraps a real implementation (Google Calendar/Gmail); agents only see these methods."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol


class Workspace(Protocol):
    def free_slots(self, n: int = 3) -> list[str]: ...
    def create_hold(self, slot: str, title: str, key: str) -> dict: ...
    def create_email_draft(self, to: str, subject: str, body: str, key: str) -> dict: ...


class InMemoryWorkspace:
    def __init__(self, start: datetime | None = None):
        self.start = start or datetime(2026, 11, 16, 10, 0)
        self.holds: dict[str, dict] = {}
        self.drafts: dict[str, dict] = {}

    def free_slots(self, n: int = 3) -> list[str]:
        taken = {h["slot"] for h in self.holds.values()}
        out, day = [], 0
        while len(out) < n:
            s = (self.start + timedelta(days=day)).strftime("%Y-%m-%d %H:%M")
            if s not in taken:
                out.append(s)
            day += 1
        return out

    def create_hold(self, slot, title, key):
        return self.holds.setdefault(key, {"slot": slot, "title": title, "status": "tentative"})   # idempotent

    def create_email_draft(self, to, subject, body, key):
        return self.drafts.setdefault(key, {"to": to, "subject": subject, "body": body})
