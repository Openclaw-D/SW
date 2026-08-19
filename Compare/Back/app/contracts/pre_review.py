from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.contracts.base import ContractModel
from app.contracts.workbench import (
    DIMENSION_IDS,
    DecisionGrade,
    DimensionId,
    EvidenceLocationStatus,
    ScoreGrade,
)


PreReviewDisposition = Literal["support", "return", "review", "deny"]
PreReviewSnapshotKind = Literal["baseline", "checkpoint", "final"]
PreReviewIssueActionType = Literal["link_evidence", "explain", "request_manual_review"]
PreReviewActionType = Literal[
    "upload_or_link_evidence",
    "provide_explanation",
    "request_manual_review",
    "resolve_verified_issue",
]
PreReviewClosureRequirement = Literal["verified_evidence", "human_review"]
PreReviewDriverKind = Literal[
    "score", "confidence", "evidence", "issue", "rule", "hard_gate"
]


class PreReviewTendencies(ContractModel):
    support: int = Field(ge=0, le=100)
    return_value: int = Field(alias="return", ge=0, le=100)
    review: int = Field(ge=0, le=100)
    deny: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_total(self) -> "PreReviewTendencies":
        if self.support + self.return_value + self.review + self.deny != 100:
            raise ValueError("pre-review tendencies must sum to 100")
        return self


class PreReviewDimension(ContractModel):
    dimension_id: DimensionId
    score: float = Field(ge=0, le=100)
    score_grade: ScoreGrade
    decision_grade: DecisionGrade
    confidence: float = Field(ge=0, le=100)


class PreReviewDriver(ContractModel):
    id: str
    kind: PreReviewDriverKind
    title: str
    explanation: str
    direction: PreReviewDisposition
    dimension_id: DimensionId | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    fact_version_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    issue_ids: list[str] = Field(default_factory=list)


class PreReviewIssue(ContractModel):
    id: str
    thread_id: str | None = None
    dimension_id: DimensionId | None = None
    title: str
    summary: str
    status: Literal["open", "pending_gate"]
    evidence_refs: list[str] = Field(default_factory=list)
    fact_version_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    next_action: PreReviewActionType


class PreReviewAction(ContractModel):
    id: str
    issue_id: str | None = None
    dimension_id: DimensionId | None = None
    action_type: PreReviewActionType
    title: str
    description: str
    completed: bool
    closure_requires: PreReviewClosureRequirement
    evidence_refs: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


class PreReviewHardGate(ContractModel):
    status: Literal["pass", "manual_review", "block"]
    enforced: bool
    blocking_rule_ids: list[str]
    manual_review_rule_ids: list[str]
    explanation: str


class PreReviewApprovalEstimate(ContractModel):
    min_days: int = Field(ge=0, le=90)
    max_days: int = Field(ge=0, le=90)
    estimate_kind: Literal["rule_based_range"]
    drivers: list[str]
    disclaimer: str
    next_action: str

    @model_validator(mode="after")
    def validate_range(self) -> "PreReviewApprovalEstimate":
        if self.max_days < self.min_days:
            raise ValueError("estimate maxDays must be greater than or equal to minDays")
        return self


class PreReviewProjection(ContractModel):
    project_id: str
    calculation_version: Literal["pre-review-v1"]
    disposition: PreReviewDisposition
    tendencies: PreReviewTendencies
    overall_score: float = Field(ge=0, le=100)
    score_grade: ScoreGrade
    decision_grade: DecisionGrade
    confidence: float = Field(ge=0, le=100)
    dimensions: list[PreReviewDimension]
    drivers: list[PreReviewDriver]
    issues: list[PreReviewIssue]
    hard_gate: PreReviewHardGate
    actions: list[PreReviewAction]
    estimate: PreReviewApprovalEstimate
    provisional: Literal[True] = True
    calibrated_probability: Literal[False] = False
    formal_decision: Literal[False] = False

    @model_validator(mode="after")
    def validate_projection_invariants(self) -> "PreReviewProjection":
        if [dimension.dimension_id for dimension in self.dimensions] != list(DIMENSION_IDS):
            raise ValueError(
                "pre-review projection requires the six frozen dimensions in order"
            )
        if self.hard_gate.status == "block" and self.hard_gate.enforced:
            frozen = (
                self.tendencies.support,
                self.tendencies.return_value,
                self.tendencies.review,
                self.tendencies.deny,
            )
            if self.disposition != "deny" or frozen != (0, 0, 0, 100):
                raise ValueError(
                    "an enforced blocking hard gate must force deny with 0/0/0/100"
                )
        return self


class PreReviewSourceEvidence(ContractModel):
    id: str
    dimension_id: DimensionId | None = None
    location_status: EvidenceLocationStatus


class PreReviewSourceFact(ContractModel):
    id: str
    fact_key: str
    dimension_id: DimensionId
    evidence_refs: list[str] = Field(default_factory=list)


class PreReviewSourcePolicy(ContractModel):
    id: str
    rule_id: str
    rule_version: str
    title: str
    result: Literal["pass", "block", "manual_review"]
    gate_triggered: bool
    dimension_id: DimensionId | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    next_action: str
    explanation: str


class PreReviewSourceIssue(ContractModel):
    id: str
    thread_id: str | None = None
    dimension_id: DimensionId | None = None
    title: str
    summary: str
    status: Literal["open", "pending_gate"]
    evidence_refs: list[str] = Field(default_factory=list)
    fact_version_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


class PreReviewSourceIssueAction(ContractModel):
    id: str
    issue_id: str
    action_type: PreReviewIssueActionType
    evidence_ref: str | None = None
    note: str | None = None


class PreReviewSource(ContractModel):
    project_id: str
    overall_score: float = Field(ge=0, le=100)
    score_grade: ScoreGrade
    decision_grade: DecisionGrade
    confidence: float = Field(ge=0, le=100)
    dimensions: list[PreReviewDimension]
    evidence: list[PreReviewSourceEvidence]
    facts: list[PreReviewSourceFact]
    policies: list[PreReviewSourcePolicy]
    issues: list[PreReviewSourceIssue]
    issue_actions: list[PreReviewSourceIssueAction]

    @model_validator(mode="after")
    def validate_source_dimensions(self) -> "PreReviewSource":
        if [dimension.dimension_id for dimension in self.dimensions] != list(DIMENSION_IDS):
            raise ValueError(
                "pre-review source requires the six frozen dimensions in order"
            )
        return self


__all__ = [
    "PreReviewAction",
    "PreReviewActionType",
    "PreReviewApprovalEstimate",
    "PreReviewClosureRequirement",
    "PreReviewDimension",
    "PreReviewDisposition",
    "PreReviewDriver",
    "PreReviewDriverKind",
    "PreReviewHardGate",
    "PreReviewIssue",
    "PreReviewIssueActionType",
    "PreReviewProjection",
    "PreReviewSnapshotKind",
    "PreReviewSource",
    "PreReviewSourceEvidence",
    "PreReviewSourceFact",
    "PreReviewSourceIssue",
    "PreReviewSourceIssueAction",
    "PreReviewSourcePolicy",
    "PreReviewTendencies",
]
