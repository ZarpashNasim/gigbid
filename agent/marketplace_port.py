"""R1: the single marketplace interface. The graph imports only this.

Adapters: GigSim (wraps the Marketplace MCP server) and live Upwork (official MCP server).
Switching marketplaces is a config change; no node changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .handoffs import DryRunPreview


class MarketplaceUnavailable(Exception):
    """Raised on timeouts/5xx after bounded retries -> UI shows degraded mode, work is queued."""


class MarketplacePort(ABC):
    @abstractmethod
    def get_job(self, job_id: str) -> dict: ...

    @abstractmethod
    def get_client_history(self, client_id: str) -> dict: ...

    @abstractmethod
    def get_connects_balance(self, user_id: str) -> int: ...

    @abstractmethod
    def create_proposal_draft(
        self, *, user_id: str, job_id: str, cover_letter: str, amount: float,
        answers: dict[str, str], idempotency_key: str, dry_run: bool,
    ) -> DryRunPreview | dict:
        """dry_run=True returns exactly what would be sent and its cost; False creates the draft
        (idempotent on idempotency_key: a retry never submits or spends Connects twice)."""


    def list_messages(self, thread_id: str) -> list[dict]:
        raise NotImplementedError

    def send_message(self, *, user_id: str, thread_id: str, body: str,
                     idempotency_key: str, dry_run: bool) -> "DryRunPreview | dict":
        raise NotImplementedError


class InMemoryMarketplace(MarketplacePort):
    """Test double with real idempotency semantics; also useful for offline demos."""

    def __init__(self, jobs: dict[str, dict], clients: dict[str, dict], connects: int = 100):
        self.jobs, self.clients, self.connects = jobs, clients, connects
        self.submissions: dict[str, dict] = {}
        self.write_calls = 0
        self.threads: dict[str, list[dict]] = {}
        self.sent: dict[str, dict] = {}
        self.message_writes = 0

    def list_messages(self, thread_id):
        return list(self.threads.get(thread_id, []))

    def send_message(self, *, user_id, thread_id, body, idempotency_key, dry_run):
        payload = {"thread_id": thread_id, "body": body}
        if dry_run:
            return DryRunPreview(payload=payload, connects_cost=0, amount=0)
        if idempotency_key in self.sent:
            return self.sent[idempotency_key]
        self.message_writes += 1
        rec = {"message_id": f"msg_{len(self.sent)+1}", **payload}
        self.sent[idempotency_key] = rec
        self.threads.setdefault(thread_id, []).append({"from": "me", "body": body})
        return rec

    def get_job(self, job_id): return self.jobs[job_id]
    def get_client_history(self, client_id): return self.clients.get(client_id, {})
    def get_connects_balance(self, user_id): return self.connects

    def create_proposal_draft(self, *, user_id, job_id, cover_letter, amount, answers,
                              idempotency_key, dry_run):
        cost = self.jobs[job_id].get("connects_cost", 8)
        payload = {"job_id": job_id, "cover_letter": cover_letter, "amount": amount, "answers": answers}
        if dry_run:
            return DryRunPreview(payload=payload, connects_cost=cost, amount=amount)
        self.write_calls += 1
        if idempotency_key in self.submissions:
            return self.submissions[idempotency_key]
        self.connects -= cost
        rec = {"submission_id": f"sub_{len(self.submissions)+1}", **payload}
        self.submissions[idempotency_key] = rec
        return rec


class BackendPort(MarketplacePort):
    """Port adapter over a marketplace Backend (GigSim today, live Upwork later).

    NOTE: this calls the backend in-process. Strict R2 wants these calls to go through the Marketplace
    MCP server (MultiServerMCPClient); swap this class for an MCP-client-backed port without touching
    any node. Idempotency/dry_run semantics are kept identical here.
    """

    def __init__(self, backend, idem=None):
        from mcp_servers.marketplace.infra import IdempotencyStore
        self.b, self.idem = backend, idem or IdempotencyStore()

    def get_job(self, job_id): return self.b.get_job(job_id)
    def get_client_history(self, client_id): return self.b.get_client_history(client_id)
    def get_connects_balance(self, user_id): return self.b.get_connects_balance()

    def create_proposal_draft(self, *, user_id, job_id, cover_letter, amount, answers, idempotency_key, dry_run):
        cost = self.b.connects_cost(job_id)
        payload = {"job_id": job_id, "cover_letter": cover_letter, "amount": amount, "answers": answers}
        if dry_run:
            return DryRunPreview(payload=payload, connects_cost=cost, amount=amount)
        rec, _ = self.idem.run_once(f"{user_id}:{idempotency_key}",
                                    lambda: self.b.create_proposal(job_id, cover_letter, amount, answers))
        return {"submission_id": rec.get("proposal_id") or rec.get("id"), **rec}

    def list_messages(self, thread_id): return self.b.list_messages(thread_id)

    def send_message(self, *, user_id, thread_id, body, idempotency_key, dry_run):
        payload = {"thread_id": thread_id, "body": body}
        if dry_run:
            return DryRunPreview(payload=payload, connects_cost=0, amount=0)
        rec, _ = self.idem.run_once(f"{user_id}:msg:{idempotency_key}", lambda: self.b.send_message(thread_id, body))
        return {"message_id": rec.get("message_id") or rec.get("id"), **rec}
