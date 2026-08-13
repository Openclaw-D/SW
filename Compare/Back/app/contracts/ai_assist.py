from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, field_validator, model_validator

from app.contracts.base import ContractModel
from app.contracts.workbench import DimensionId, ReviewEvidenceTarget


AI_ASSIST_SCHEMA_VERSION = "1.0"
AI_ASSIST_FUTURE_PATH = "/api/v1/projects/{projectId}/ai/assist"
AI_ASSIST_SIMULATION_DISCLAIMER = (
    "完整脱敏模拟上下文中的信息处理辅助结果；仅供人工复核，不构成事实、评分、制度或审批结论。"
)


class AiAssistTaskType(StrEnum):
    MATERIAL_SUMMARY = "material_summary"
    EVIDENCE_GAP_QUESTIONS = "evidence_gap_questions"
    REVIEW_DRAFT = "review_draft"
    INDICATOR_EXPLANATION = "indicator_explanation"


class AiAssistActor(StrEnum):
    BUSINESS = "business"
    RISK = "risk"


class AiAssistStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    UNAVAILABLE = "unavailable"


class AiAssistErrorCode(StrEnum):
    AI_DISABLED = "ai_disabled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    CONTEXT_VERSION_CONFLICT = "context_version_conflict"
    EVIDENCE_CONTEXT_INVALID = "evidence_context_invalid"


class AiAssistRequest(ContractModel):
    project_id: str = Field(min_length=1, max_length=128)
    task_type: AiAssistTaskType
    actor: AiAssistActor
    instruction: str = Field(min_length=1, max_length=4000)
    evidence_targets: list[ReviewEvidenceTarget] = Field(min_length=1, max_length=50)
    fact_version_ids: list[str] = Field(default_factory=list, max_length=100)
    policy_result_ids: list[str] = Field(default_factory=list, max_length=100)
    context_version: str = Field(min_length=1, max_length=128)
    locale: Literal["zh-CN"] = "zh-CN"

    @field_validator("project_id", "context_version")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_trimmed_text(value, "identifier")

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        return _require_trimmed_text(value, "instruction")

    @field_validator("fact_version_ids", "policy_result_ids")
    @classmethod
    def validate_identifier_list(cls, values: list[str]) -> list[str]:
        for value in values:
            _require_trimmed_text(value, "id")
        if len(set(values)) != len(values):
            raise ValueError("id lists must not contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_evidence_targets(self) -> "AiAssistRequest":
        targets_by_ref: dict[str, tuple[str, str | None, str | None]] = {}
        grouped_refs: dict[tuple[str, str | None, str | None], list[str]] = {}
        for target in self.evidence_targets:
            _require_target_ids(target)
            identity = (
                target.dimension_id,
                target.review_target_id,
                target.fact_version_id,
            )
            previous = targets_by_ref.setdefault(target.evidence_ref, identity)
            if previous != identity:
                raise ValueError("an evidenceRef cannot identify inconsistent targets")
            refs = grouped_refs.setdefault(identity, [])
            if target.evidence_ref in refs:
                raise ValueError("evidenceTargets must not contain duplicates")
            refs.append(target.evidence_ref)
            if (
                target.fact_version_id is not None
                and target.fact_version_id not in self.fact_version_ids
            ):
                raise ValueError(
                    "target factVersionId must be declared in factVersionIds"
                )

        for target in self.evidence_targets:
            identity = (
                target.dimension_id,
                target.review_target_id,
                target.fact_version_id,
            )
            if (
                target.evidence_refs is not None
                and target.evidence_refs != grouped_refs[identity]
            ):
                raise ValueError(
                    "evidenceRefs must equal the complete ordered target group"
                )
        return self


class AiAssistContextItem(ContractModel):
    source_type: Literal["evidence", "fact", "policy"]
    source_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=12000)
    evidence_target: ReviewEvidenceTarget | None = None

    @field_validator("source_id", "text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "context value")

    @model_validator(mode="after")
    def validate_source_projection(self) -> "AiAssistContextItem":
        if self.source_type == "evidence":
            if self.evidence_target is None:
                raise ValueError("evidence context requires evidenceTarget")
            if self.source_id != self.evidence_target.evidence_ref:
                raise ValueError("evidence sourceId must equal evidenceTarget.evidenceRef")
        elif self.evidence_target is not None:
            raise ValueError("only evidence context may carry evidenceTarget")
        return self


class AiAssistContext(ContractModel):
    project_id: str = Field(min_length=1, max_length=128)
    context_version: str = Field(min_length=1, max_length=128)
    items: list[AiAssistContextItem] = Field(min_length=1, max_length=150)
    is_simulated: bool
    disclaimer: str = Field(min_length=1, max_length=1000)

    @field_validator("project_id", "context_version", "disclaimer")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "context value")

    @model_validator(mode="after")
    def preserve_simulation_boundary(self) -> "AiAssistContext":
        if self.is_simulated is not True:
            raise ValueError("C0 AI assist context must remain simulated")
        identities = [(item.source_type, item.source_id) for item in self.items]
        if len(set(identities)) != len(identities):
            raise ValueError("context source identities must be unique")
        return self


class AiAssistCitation(ContractModel):
    evidence_ref: str = Field(min_length=1, max_length=128)
    dimension_id: DimensionId
    review_target_id: str | None
    fact_version_id: str | None

    @field_validator("evidence_ref")
    @classmethod
    def validate_evidence_ref(cls, value: str) -> str:
        return _require_trimmed_text(value, "evidenceRef")

    @field_validator("review_target_id", "fact_version_id")
    @classmethod
    def validate_optional_identifier(cls, value: str | None) -> str | None:
        if value is not None:
            _require_trimmed_text(value, "citation id")
        return value

    def stable_tuple(self) -> tuple[str, str, str | None, str | None]:
        return (
            self.evidence_ref,
            self.dimension_id,
            self.review_target_id,
            self.fact_version_id,
        )


class AiAssistModelInfo(ContractModel):
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    model_version: str | None = Field(default=None, max_length=128)

    @field_validator("provider", "model")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "modelInfo value")

    @field_validator("model_version")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is not None:
            _require_trimmed_text(value, "modelVersion")
        return value


class AiAssistResult(ContractModel):
    task_type: AiAssistTaskType
    status: AiAssistStatus
    advisory_only: Literal[True]
    summary: str = Field(min_length=1, max_length=4000)
    observations: list[str] = Field(default_factory=list, max_length=50)
    questions: list[str] = Field(default_factory=list, max_length=50)
    proposed_review_text: str | None = Field(default=None, max_length=8000)
    citations: list[AiAssistCitation] = Field(default_factory=list, max_length=100)
    model_info: AiAssistModelInfo | None
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: Literal["1.0"] = AI_ASSIST_SCHEMA_VERSION
    is_simulated: bool
    disclaimer: str = Field(min_length=1, max_length=1000)

    @field_validator("summary", "disclaimer")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "result text")

    @field_validator("observations", "questions")
    @classmethod
    def validate_text_list(cls, values: list[str]) -> list[str]:
        for value in values:
            _require_trimmed_text(value, "result list item")
            if len(value) > 2000:
                raise ValueError("result list items must not exceed 2000 characters")
        return values

    @field_validator("proposed_review_text")
    @classmethod
    def validate_proposed_text(cls, value: str | None) -> str | None:
        if value is not None:
            _require_trimmed_text(value, "proposedReviewText")
        return value

    @model_validator(mode="after")
    def validate_status_and_content(self) -> "AiAssistResult":
        if self.is_simulated is not True:
            raise ValueError("C0 AI assist result must remain simulated")
        citation_tuples = [citation.stable_tuple() for citation in self.citations]
        if len(set(citation_tuples)) != len(citation_tuples):
            raise ValueError("citations must not contain duplicates")

        if self.status == AiAssistStatus.UNAVAILABLE:
            if (
                self.observations
                or self.questions
                or self.proposed_review_text is not None
                or self.citations
                or self.model_info is not None
            ):
                raise ValueError("unavailable result cannot contain generated content")
            return self

        if self.model_info is None:
            raise ValueError("completed or needs_review result requires modelInfo")
        if self.status == AiAssistStatus.COMPLETED and not self.citations:
            raise ValueError("completed result requires at least one citation")
        if self.status == AiAssistStatus.NEEDS_REVIEW and not (
            self.observations or self.questions
        ):
            raise ValueError("needs_review result requires an observation or question")

        if self.task_type == AiAssistTaskType.REVIEW_DRAFT:
            if self.status == AiAssistStatus.COMPLETED:
                if self.proposed_review_text is None:
                    raise ValueError("completed review_draft requires proposedReviewText")
            elif self.proposed_review_text is not None:
                raise ValueError("needs_review cannot present a review draft")
        elif self.proposed_review_text is not None:
            raise ValueError("proposedReviewText is only allowed for review_draft")

        if (
            self.task_type == AiAssistTaskType.EVIDENCE_GAP_QUESTIONS
            and self.status == AiAssistStatus.COMPLETED
            and not self.questions
        ):
            raise ValueError("completed evidence_gap_questions requires questions")
        return self


class AiAssistErrorDetail(ContractModel):
    code: AiAssistErrorCode
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return _require_trimmed_text(value, "error message")


def validate_ai_assist_context(
    request: AiAssistRequest,
    context: AiAssistContext,
) -> AiAssistContext:
    """Validate the read-only context before invoking any future provider."""

    if context.project_id != request.project_id:
        raise ValueError("context projectId must match request projectId")
    if context.context_version != request.context_version:
        raise ValueError("contextVersion conflict")

    allowed_targets = {_target_tuple(target) for target in request.evidence_targets}
    allowed_fact_ids = set(request.fact_version_ids)
    allowed_policy_ids = set(request.policy_result_ids)
    for item in context.items:
        if item.source_type == "evidence":
            assert item.evidence_target is not None
            if _target_tuple(item.evidence_target) not in allowed_targets:
                raise ValueError("evidence context is not declared by the request")
        elif item.source_type == "fact":
            if item.source_id not in allowed_fact_ids:
                raise ValueError("fact context is not declared by the request")
        elif item.source_id not in allowed_policy_ids:
            raise ValueError("policy context is not declared by the request")
    return context


def validate_ai_assist_result(
    request: AiAssistRequest,
    result: AiAssistResult,
) -> AiAssistResult:
    """Reject task drift or citations not present in the authoritative request."""

    if result.task_type != request.task_type:
        raise ValueError("result taskType must match request taskType")
    allowed_targets = {_target_tuple(target) for target in request.evidence_targets}
    for citation in result.citations:
        if citation.stable_tuple() not in allowed_targets:
            raise ValueError("citation must match an input ReviewEvidenceTarget")
    return result


@runtime_checkable
class AiAssistProviderPort(Protocol):
    """Provider-neutral, advisory-only async boundary for a future B2 adapter.

    The caller must run ``validate_ai_assist_context`` before invocation and
    ``validate_ai_assist_result`` before returning or persisting any output.
    Implementations must not mutate core workbench state.
    """

    async def assist(
        self,
        request: AiAssistRequest,
        context: AiAssistContext,
    ) -> AiAssistResult: ...


def _require_trimmed_text(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be blank")
    if value != value.strip():
        raise ValueError(f"{label} must not have surrounding whitespace")
    return value


def _require_target_ids(target: ReviewEvidenceTarget) -> None:
    _require_trimmed_text(target.evidence_ref, "evidenceRef")
    for value in target.evidence_refs or []:
        _require_trimmed_text(value, "evidenceRefs item")
    if target.review_target_id is not None:
        _require_trimmed_text(target.review_target_id, "reviewTargetId")
    if target.fact_version_id is not None:
        _require_trimmed_text(target.fact_version_id, "factVersionId")


def _target_tuple(
    target: ReviewEvidenceTarget,
) -> tuple[str, str, str | None, str | None]:
    return (
        target.evidence_ref,
        target.dimension_id,
        target.review_target_id,
        target.fact_version_id,
    )
