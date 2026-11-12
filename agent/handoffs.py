"""Structured hand-offs between agents (C3).

Anything a later step *decides on* is a Pydantic object, never free text.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel as _BM, ConfigDict, Field


class BaseModel(_BM):
    # defaults are always present in serialized output -> required in the OpenAPI response schema,
    # so the generated TypeScript client has no spurious optionals
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Requirement(BaseModel):
    text: str
    skills: list[str] = Field(default_factory=list)
    must_have: bool = True


class JobSpec(BaseModel):
    job_id: str
    title: str
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    budget_min: float | None = None
    budget_max: float | None = None
    timeline_days: int | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)
    category: str = "general"


class RiskReport(BaseModel):
    client_score: float = Field(ge=0, le=1, description="1 = trustworthy client")
    scam: bool = False
    free_work_request: bool = False
    off_platform_ask: bool = False
    injection_detected: bool = False
    flags: list[str] = Field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return self.scam or self.free_work_request or self.off_platform_ask or self.injection_detected


class EvidenceItem(BaseModel):
    id: str
    type: str  # case_study | repo | review | proposal | cv
    source: str
    text: str
    date: str | None = None
    outcome: str | None = None  # won | replied | ignored | None


class RequirementMatch(BaseModel):
    requirement: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    covered: bool = False


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matches: list[RequirementMatch] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["skip", "watch", "bid"]
    reason: str


class PriceQuote(BaseModel):
    amount: float = Field(ge=0)
    connects_cost: int = Field(ge=0)
    worth_connects: bool = True
    rationale: str = ""


class Claim(BaseModel):
    text: str
    status: Literal["supported", "partly_supported", "unsupported"] = "unsupported"
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    cover_letter: str
    screening_answers: dict[str, str] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)
    revision: int = 0


class Critique(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)


class ComplianceVerdict(BaseModel):
    allowed: bool
    violations: list[str] = Field(default_factory=list)
    cleaned_cover_letter: str | None = None


class DryRunPreview(BaseModel):
    payload: dict
    connects_cost: int
    amount: float


class Approval(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edited_cover_letter: str | None = None
    reason: str | None = None


class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal"]
    summary: str = ""


class ReplyDraft(BaseModel):
    body: str
    proposed_slots: list[str] = Field(default_factory=list)


class ReqGrade(BaseModel):
    index: int
    is_requirement: bool = True      # False for boilerplate ("we are a company...", "weekly updates required")
    supported_ids: list[str] = Field(default_factory=list)


class FitGrade(BaseModel):
    grades: list[ReqGrade] = Field(default_factory=list)
