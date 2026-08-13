from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts.agent_communication import AgentMessage, AgentRole, AgentThreadStatus
from app.contracts.base import ContractModel
from app.contracts.workbench import (
    DecisionGrade,
    DimensionId,
    EvidenceLocationStatus,
    LocalMaterialStatus,
    RiskLevel,
    ScoreGrade,
)


CONCLUSION_SCHEMA_VERSION = "1.0"
CONCLUSION_DISCLAIMER = (
    "本报告是对当前项目状态、证据、正式协同、制度 Gate 与单焦点 Agent 建议的"
    "只读汇总。Agent 内容始终为 advisory-only；报告不执行审批、不替代人工判断，"
    "也不证明真实生产模型质量或外部网络核验结果。"
)


class ConclusionOverall(ContractModel):
    risk_level: RiskLevel
    score_grade: ScoreGrade
    decision_grade: DecisionGrade
    confidence: float = Field(ge=0, le=100)
    summary: str


class ConclusionDimension(ContractModel):
    dimension_id: DimensionId
    name: str
    score: float = Field(ge=0, le=100)
    score_grade: ScoreGrade
    decision_grade: DecisionGrade
    confidence: float = Field(ge=0, le=100)
    summary: str
    conclusion: str


class ConclusionEvidenceItem(ContractModel):
    evidence_ref: str
    label: str
    location_status: EvidenceLocationStatus
    material_status: LocalMaterialStatus
    locator_summary: str


class ConclusionOpenItem(ContractModel):
    id: str
    source: Literal["formal_review", "risk_summary", "policy"]
    title: str
    detail: str
    status: Literal["open", "pending_gate", "manual_review", "block"]
    dimension_id: DimensionId | None = None
    responsible_party: Literal["business", "risk", "joint"]
    next_action: str
    evidence_refs: list[str]


class ConclusionPolicyCounts(ContractModel):
    passed: int = Field(ge=0)
    blocked: int = Field(ge=0)
    manual_review: int = Field(ge=0)


class ConclusionGateSummary(ContractModel):
    approval_status: Literal["draft", "returned", "submitted", "completed"]
    approval_version: int = Field(ge=1)
    hard_gate_status: Literal["pass", "block", "manual_review"]
    blocking_rule_ids: list[str]
    risk_veto: bool
    risk_veto_rule_ids: list[str]
    policy_counts: ConclusionPolicyCounts
    completion_allowed: bool


class ConclusionCollaboration(ContractModel):
    has_thread: bool
    thread_id: str | None = None
    thread_title: str | None = None
    thread_status: AgentThreadStatus | None = None
    focus_role: AgentRole | None = None
    thread_version: int | None = Field(default=None, ge=1)
    message_count: int = Field(ge=0)
    agent_message_count: int = Field(ge=0)
    focus_event_count: int = Field(ge=0)
    focus_transition_count: int = Field(ge=0)
    latest_advice: AgentMessage | None = None

    @model_validator(mode="after")
    def validate_thread_projection(self) -> "ConclusionCollaboration":
        thread_values = (
            self.thread_id,
            self.thread_title,
            self.thread_status,
            self.focus_role,
            self.thread_version,
        )
        if self.has_thread != all(value is not None for value in thread_values):
            raise ValueError("hasThread must match the projected thread fields")
        if self.latest_advice is not None and not self.has_thread:
            raise ValueError("latestAdvice requires a projected thread")
        return self


class ConclusionHumanConfirmation(ContractModel):
    required: Literal[True] = True
    status: Literal["human_action_required", "ready_for_human", "completed"]
    checks: list[str]
    boundary: str


class ConclusionAiValue(ContractModel):
    source_sections_consolidated: list[str]
    evidence_items_organized: int = Field(ge=0)
    open_items_surfaced: int = Field(ge=0)
    follow_up_questions_surfaced: int = Field(ge=0)
    traceable_reference_count: int = Field(ge=0)
    advisory_messages_available: int = Field(ge=0)
    focus_transitions_recorded: int = Field(ge=0)
    summary: str


class ProjectConclusionReport(ContractModel):
    schema_version: Literal["1.0"] = CONCLUSION_SCHEMA_VERSION
    project_id: str
    project_name: str
    generated_at: datetime
    overall: ConclusionOverall
    dimensions: list[ConclusionDimension] = Field(min_length=6, max_length=6)
    evidence_total: int = Field(ge=0)
    evidence_status_counts: dict[EvidenceLocationStatus, int]
    key_evidence: list[ConclusionEvidenceItem]
    open_items: list[ConclusionOpenItem]
    gates: ConclusionGateSummary
    collaboration: ConclusionCollaboration
    human_confirmation: ConclusionHumanConfirmation
    ai_value: ConclusionAiValue
    advisory_only: Literal[True] = True
    is_simulated: bool
    data_status: Literal["simulated", "provider_generated_unverified"]
    source: Literal["server_conclusion_projection"] = "server_conclusion_projection"
    disclaimer: str = CONCLUSION_DISCLAIMER


__all__ = [
    "CONCLUSION_DISCLAIMER",
    "CONCLUSION_SCHEMA_VERSION",
    "ConclusionAiValue",
    "ConclusionCollaboration",
    "ConclusionDimension",
    "ConclusionEvidenceItem",
    "ConclusionGateSummary",
    "ConclusionHumanConfirmation",
    "ConclusionOpenItem",
    "ConclusionOverall",
    "ConclusionPolicyCounts",
    "ProjectConclusionReport",
]
