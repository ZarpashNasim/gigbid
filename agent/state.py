"""Typed bid-graph state (C2).

Three things are kept apart:
  * State        - what this job needs right now (this TypedDict)
  * Trace        - append-only audit of tool calls/observations (`trace`, reducer = concat)
  * Memory       - promoted knowledge only, lives in the LangGraph store (agent/memory)
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from .handoffs import (
    Approval, BidDecision, ComplianceVerdict, Critique, DryRunPreview,
    FitReport, JobSpec, MessageIntent, PriceQuote, ProposalDraft, ReplyDraft, RiskReport,
)

Status = Literal["running", "skipped", "awaiting_approval", "submitted", "rejected",
                 "blocked", "needs_attention", "dead_letter", "flagged", "sent"]


def _last(_old: Any, new: Any) -> Any:
    return new


class BidState(TypedDict, total=False):
    # input
    user_id: str
    job_id: str
    raw_job: dict
    # analyses (written by parallel branches -> distinct keys, no clobbering)
    spec: JobSpec
    risk: RiskReport
    fit: FitReport
    # downstream
    decision: BidDecision
    price: PriceQuote
    draft: ProposalDraft
    critiques: Annotated[list[Critique], operator.add]
    compliance: ComplianceVerdict
    preview: DryRunPreview
    approval: Approval
    submission_id: str | None
    # control
    status: Annotated[Status, _last]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    # execution trace (audit; never fed to memory)
    trace: Annotated[list[dict], operator.add]


class ConvState(TypedDict, total=False):
    """Conversation graph state: one thread per client conversation."""
    user_id: str
    thread_id: str
    messages: list[dict]
    intent: MessageIntent
    draft: ReplyDraft
    compliance: ComplianceVerdict
    preview: DryRunPreview
    approval: Approval
    sent_id: str | None
    status: Annotated[Status, _last]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    trace: Annotated[list[dict], operator.add]
