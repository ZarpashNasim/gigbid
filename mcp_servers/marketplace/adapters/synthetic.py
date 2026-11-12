"""SyntheticBackend: serves data/synthetic (jobs, clients, message threads) through the Backend interface.

A stand-in for GigSim so the whole app runs offline on realistic data. It is NOT GigSim and does not reproduce its
behaviour (rate limits, simulated client replies). Sent messages and created proposals live in memory only.
"""
from __future__ import annotations

import json
from pathlib import Path

from .memory import MemoryBackend


class SyntheticBackend(MemoryBackend):
    def __init__(self, data_dir: str = "data/synthetic", split: str = "dev", connects: int = 200):
        root = Path(data_dir)
        jobs = {j["job_id"]: j for j in map(json.loads, (root / f"jobs_{split}.jsonl").read_text().splitlines())}
        clients = {c["client_id"]: c for c in json.loads((root / "clients.json").read_text())}
        super().__init__(jobs, clients, connects)
        self.threads = {t["thread_id"]: t["messages"] for t in json.loads((root / f"threads_{split}.json").read_text())}

    def list_messages(self, thread_id):
        return list(self.threads.get(thread_id, [])) + [m for m in self.sent if m["thread_id"] == thread_id]
