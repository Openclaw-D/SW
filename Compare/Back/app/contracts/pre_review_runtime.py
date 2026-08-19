from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts.base import ContractModel
from app.contracts.pre_review import PreReviewIssueActionType, PreReviewProjection, PreReviewSnapshotKind


class PreReviewBindings(ContractModel):
    project_snapshot_id: str
    project_snapshot_version: int = Field(ge=1)
    material_version_ids: list[str]
    evidence_ref_ids: list[str]
    fact_version_ids: list[str]
    policy_result_ids: list[str]
    rule_version_ids: list[str]
    review_event_ids: list[str]
    review_event_sequence: int = Field(ge=0)
    approval_version: int = Field(ge=1)
    approval_status: str
    issue_action_ids: list[str]


class PreReviewExecutionProvenance(ContractModel):
    source: Literal["deterministic_business_rules"] = "deterministic_business_rules"
    calculation_version: Literal["pre-review-v1"] = "pre-review-v1"
    input_hash: str = Field(min_length=64, max_length=64)
    provider_id: None = None
    model_id: None = None
    advisory_only: Literal[True] = True
    formal_writes: Literal[False] = False


class PreReviewRunRecord(ContractModel):
    id: str
    project_id: str
    sequence: int = Field(ge=1)
    trigger: Literal["start", "rejudge", "submit"]
    projection: PreReviewProjection
    bindings: PreReviewBindings
    provenance: PreReviewExecutionProvenance
    created_at: datetime
    created_by: str


class PreReviewVisibleSnapshot(ContractModel):
    id: str
    project_id: str
    visible_version: int = Field(ge=1)
    label: str
    kind: PreReviewSnapshotKind
    run_id: str
    projection: PreReviewProjection
    bindings: PreReviewBindings
    created_at: datetime
    created_by: str
    locked_at: datetime | None
    immutable: Literal[True] = True

    @model_validator(mode="after")
    def validate_lock(self) -> "PreReviewVisibleSnapshot":
        if (self.kind == "final") != (self.locked_at is not None):
            raise ValueError("only a final pre-review snapshot is locked")
        return self


class PreReviewRunCommand(ContractModel):
    project_id: str
    trigger: Literal["start", "rejudge"]
    expected_version: int = Field(ge=0)
    snapshot_limit: int = Field(default=3, ge=2, le=5)
    idempotency_key: str | None = Field(default=None, max_length=200)


class PreReviewCheckpointCommand(ContractModel):
    project_id: str
    expected_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=200)


class PreReviewSubmitCommand(ContractModel):
    project_id: str
    expected_version: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=200)


class PreReviewIssueActionCommand(ContractModel):
    project_id: str
    expected_version: int = Field(ge=1)
    action_type: PreReviewIssueActionType
    evidence_ref: str | None = None
    note: str | None = Field(default=None, max_length=2000)
    idempotency_key: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_payload(self) -> "PreReviewIssueActionCommand":
        if self.action_type == "link_evidence" and not (self.evidence_ref or "").strip():
            raise ValueError("link_evidence requires evidenceRef")
        if self.action_type != "link_evidence" and self.evidence_ref is not None:
            raise ValueError("only link_evidence accepts evidenceRef")
        if self.action_type == "explain" and not (self.note or "").strip():
            raise ValueError("explain requires note")
        return self


class StoredPreReviewIssueAction(ContractModel):
    id: str
    project_id: str
    issue_id: str
    action_type: PreReviewIssueActionType
    evidence_ref: str | None
    note: str | None
    created_at: datetime
    created_by: str


class PreReviewStateView(ContractModel):
    project_id: str
    started: bool
    version: int = Field(ge=0)
    snapshot_limit: int = Field(ge=2, le=5)
    hard_snapshot_limit: Literal[5] = 5
    visible_snapshots: list[PreReviewVisibleSnapshot]
    current_run: PreReviewRunRecord | None
    current_projection: PreReviewProjection | None
    current_bindings: PreReviewBindings | None
    stale: bool
    can_save_checkpoint: bool
    can_submit: bool
    submitted: bool
    submitted_snapshot_id: str | None


class PreReviewTendencyChange(ContractModel):
    support: int
    return_value: int = Field(alias="return")
    review: int
    deny: int


class PreReviewDimensionChange(ContractModel):
    dimension_id: str
    from_score: float
    to_score: float
    score_delta: float
    from_score_grade: str
    to_score_grade: str
    from_decision_grade: str
    to_decision_grade: str
    confidence_delta: float


class JudgmentDiff(ContractModel):
    project_id: str
    from_snapshot_id: str
    from_label: str
    to_snapshot_id: str | None
    to_label: str
    tendency_change: PreReviewTendencyChange
    disposition_change: str
    dimension_changes: list[PreReviewDimensionChange]
    new_evidence_ref_ids: list[str]
    new_fact_version_ids: list[str]
    resolved_issue_ids: list[str]
    unchanged_issue_ids: list[str]
    new_issue_ids: list[str]
    rule_changes: list[str]
    hard_gate_change: str
    next_actions: list[str]
    generated_by: Literal["deterministic_snapshot_comparison"] = "deterministic_snapshot_comparison"


__all__ = [
    "JudgmentDiff",
    "PreReviewBindings",
    "PreReviewCheckpointCommand",
    "PreReviewExecutionProvenance",
    "PreReviewIssueActionCommand",
    "PreReviewRunCommand",
    "PreReviewRunRecord",
    "PreReviewStateView",
    "PreReviewSubmitCommand",
    "PreReviewVisibleSnapshot",
    "StoredPreReviewIssueAction",
]
