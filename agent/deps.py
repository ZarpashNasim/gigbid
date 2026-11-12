"""Dependency bundle injected into nodes (keeps nodes free of globals and easy to fake in tests)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from langgraph.store.base import BaseStore

from .handoffs import EvidenceItem
from .llm import LLM
from .marketplace_port import MarketplacePort


class Retriever(Protocol):
    def search(self, requirement: str, k: int = 5) -> list[EvidenceItem]: ...


@dataclass
class Deps:
    llm: LLM
    market: MarketplacePort
    retriever: Retriever
    store: BaseStore
    cfg: dict
    workspace: object | None = None   # agent.workspace.Workspace
    profiles: dict = field(default_factory=dict)   # user_id -> {hourly_rate_usd, minimum_project_budget_usd}
