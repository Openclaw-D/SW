from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.base import ContractModel
from app.contracts.workbench import DimensionId, ReviewEvidenceTarget


AGENT_COMMUNICATION_SCHEMA_VERSION = "2.0"
AGENT_COMMUNICATION_DISCLAIMER = (
    "项目群聊中的协作 Agent 仅提供项目内、可追踪的辅助内容；不构成已核验事实、评分、"
    "制度、hard gate、正式拒绝或审批结论，正式动作仍须经过既有人工 Gate。"
)


class AgentRole(StrEnum):
    BUSINESS = "business"
    RISK = "risk"
    LEADERSHIP = "leadership"


class AgentMode(StrEnum):
    DISABLED = "disabled"
    SYNTHETIC = "synthetic"
    REAL = "real"


class AgentScopeStatus(StrEnum):
    IN_SCOPE = "in_scope"
    NEEDS_CLARIFICATION = "needs_clarification"
    OUT_OF_SCOPE = "out_of_scope"


class AgentDisposition(StrEnum):
    ANSWER = "answer"
    REQUEST_INFORMATION = "request_information"
    ESCALATE = "escalate"
    DECLINE_OUT_OF_SCOPE = "decline_out_of_scope"


class AgentThreadStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    REJECTED = "rejected"


class AgentMessageAuthorType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class AgentMessageKind(StrEnum):
    USER_INPUT = "user_input"
    AGENT_REPLY = "agent_reply"


class AgentTurnStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    OUT_OF_SCOPE = "out_of_scope"
    UNAVAILABLE = "unavailable"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    OUT_OF_SCOPE = "out_of_scope"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class AgentRunStepStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class AgentDataStatus(StrEnum):
    SIMULATED = "simulated"
    PROVIDER_GENERATED_UNVERIFIED = "provider_generated_unverified"
    UNAVAILABLE = "unavailable"


class AgentFocusEventKind(StrEnum):
    THREAD_CREATED = "thread_created"
    THREAD_MIGRATED = "thread_migrated"
    FOCUS_TRANSFERRED = "focus_transferred"
    FOCUS_RETURNED = "focus_returned"
    THREAD_CLOSED = "thread_closed"
    THREAD_REJECTED = "thread_rejected"
    THREAD_REOPENED = "thread_reopened"


class AgentCitation(ContractModel):
    evidence_ref: str = Field(min_length=1, max_length=128)
    dimension_id: DimensionId
    review_target_id: str | None = Field(default=None, max_length=128)
    fact_version_id: str | None = Field(default=None, max_length=128)

    @field_validator("evidence_ref")
    @classmethod
    def validate_evidence_ref(cls, value: str) -> str:
        return _trimmed(value, "evidenceRef")

    @field_validator("review_target_id", "fact_version_id")
    @classmethod
    def validate_optional_id(cls, value: str | None) -> str | None:
        return _optional_trimmed(value, "citation id")

    def stable_tuple(self) -> tuple[str, str, str | None, str | None]:
        return (
            self.evidence_ref,
            self.dimension_id,
            self.review_target_id,
            self.fact_version_id,
        )

    @classmethod
    def from_evidence_target(cls, target: ReviewEvidenceTarget) -> "AgentCitation":
        return cls(
            evidence_ref=target.evidence_ref,
            dimension_id=target.dimension_id,
            review_target_id=target.review_target_id,
            fact_version_id=target.fact_version_id,
        )


class GeneratedAgentContent(ContractModel):
    """The complete model-authored shape; trusted provenance is added server-side."""

    reply_text: str = Field(min_length=1, max_length=8000)
    observations: list[str] = Field(default_factory=list, max_length=50)
    questions: list[str] = Field(default_factory=list, max_length=50)
    citations: list[AgentCitation] = Field(default_factory=list, max_length=100)
    scope_status: AgentScopeStatus
    disposition: AgentDisposition

    @field_validator("reply_text")
    @classmethod
    def validate_reply(cls, value: str) -> str:
        return _trimmed(value, "replyText")

    @field_validator("observations", "questions")
    @classmethod
    def validate_text_items(cls, values: list[str]) -> list[str]:
        for value in values:
            _trimmed(value, "generated item")
            if len(value) > 2000:
                raise ValueError("generated list items must not exceed 2000 characters")
        if len(set(values)) != len(values):
            raise ValueError("generated list items must be unique")
        return values

    @model_validator(mode="after")
    def validate_generated_semantics(self) -> "GeneratedAgentContent":
        citation_keys = [item.stable_tuple() for item in self.citations]
        if len(set(citation_keys)) != len(citation_keys):
            raise ValueError("citations must be unique")
        if self.scope_status == AgentScopeStatus.OUT_OF_SCOPE:
            if self.disposition != AgentDisposition.DECLINE_OUT_OF_SCOPE:
                raise ValueError("out_of_scope content must decline out of scope")
            if self.observations or self.questions or self.citations:
                raise ValueError("out_of_scope content cannot claim project analysis")
        elif self.disposition == AgentDisposition.DECLINE_OUT_OF_SCOPE:
            raise ValueError("decline_out_of_scope requires out_of_scope status")
        if self.scope_status == AgentScopeStatus.NEEDS_CLARIFICATION:
            if self.disposition != AgentDisposition.REQUEST_INFORMATION or not self.questions:
                raise ValueError("needs_clarification requires information questions")
        if self.disposition == AgentDisposition.REQUEST_INFORMATION and not self.questions:
            raise ValueError("request_information requires at least one question")
        return self


class AgentTurnRequest(ContractModel):
    """Explicit routing is separate from the authenticated human principal.

    The optional pair keeps old single-focus callers readable during the local
    migration. New group-chat callers always provide both fields.
    """

    instruction: str = Field(min_length=1, max_length=4000)
    target_agent_role: Literal[AgentRole.BUSINESS, AgentRole.RISK] | None = None
    source_message_id: str | None = Field(default=None, max_length=128)
    reply_to_message_id: str | None = Field(default=None, max_length=128)
    evidence_targets: list[ReviewEvidenceTarget] = Field(default_factory=list, max_length=50)
    expected_version: int = Field(ge=1)
    locale: Literal["zh-CN"] = "zh-CN"
    response_depth: Literal["brief", "balanced", "detailed"] = "balanced"
    response_focus: Literal["balanced", "risk", "evidence", "next_steps"] = "balanced"
    custom_guidance: str = ""

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        return _trimmed(value, "instruction")

    @field_validator("source_message_id", "reply_to_message_id")
    @classmethod
    def validate_reply_id(cls, value: str | None) -> str | None:
        return _optional_trimmed(value, "replyToMessageId")

    @field_validator("custom_guidance")
    @classmethod
    def validate_custom_guidance(cls, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) > 500:
            raise ValueError("customGuidance must not exceed 500 characters")
        return trimmed

    @model_validator(mode="after")
    def validate_evidence_targets(self) -> "AgentTurnRequest":
        if (self.target_agent_role is None) != (self.source_message_id is None):
            raise ValueError(
                "targetAgentRole and sourceMessageId must be provided together"
            )
        identities = [
            (
                item.evidence_ref,
                item.dimension_id,
                item.review_target_id,
                item.fact_version_id,
            )
            for item in self.evidence_targets
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("evidenceTargets must not contain duplicates")
        return self


class AgentChatMessageRequest(ContractModel):
    """A human group-chat message. It never triggers an Agent by itself."""

    content: str = Field(min_length=1, max_length=4000)
    reply_to_message_id: str | None = Field(default=None, max_length=128)
    evidence_targets: list[ReviewEvidenceTarget] = Field(
        default_factory=list, max_length=50
    )
    locale: Literal["zh-CN"] = "zh-CN"

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _trimmed(value, "content")

    @field_validator("reply_to_message_id")
    @classmethod
    def validate_reply_id(cls, value: str | None) -> str | None:
        return _optional_trimmed(value, "replyToMessageId")

    @model_validator(mode="after")
    def validate_evidence_targets(self) -> "AgentChatMessageRequest":
        identities = [
            (
                item.evidence_ref,
                item.dimension_id,
                item.review_target_id,
                item.fact_version_id,
            )
            for item in self.evidence_targets
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("evidenceTargets must not contain duplicates")
        return self


class AgentFocusTransitionRequest(ContractModel):
    to_focus_role: AgentRole
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _trimmed(value, "reason")


class AgentThreadControlRequest(ContractModel):
    action: Literal["close", "reject", "reopen"]
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _trimmed(value, "reason")


class AgentThreadCreateRequest(ContractModel):
    title: str = Field(min_length=1, max_length=512)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _trimmed(value, "title")


class AgentThread(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    version: int = Field(ge=1)
    status: AgentThreadStatus
    focus_role: AgentRole
    created_by_role: AgentRole
    closed_reason: str | None = Field(default=None, max_length=2000)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_thread(self) -> "AgentThread":
        if self.updated_at < self.created_at:
            raise ValueError("updatedAt must not precede createdAt")
        if (self.status == AgentThreadStatus.ACTIVE) == (self.closed_reason is not None):
            raise ValueError("only a non-active thread requires closedReason")
        return self


class AgentFocusEvent(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1)
    kind: AgentFocusEventKind
    from_focus_role: AgentRole | None = None
    to_focus_role: AgentRole
    actor_role: AgentRole
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=0)
    resulting_version: int = Field(ge=1)
    created_at: datetime
    immutable: Literal[True] = True

    @model_validator(mode="after")
    def validate_transition(self) -> "AgentFocusEvent":
        if self.kind == AgentFocusEventKind.THREAD_CREATED and self.from_focus_role is not None:
            raise ValueError("thread_created cannot have fromFocusRole")
        if self.kind in {
            AgentFocusEventKind.FOCUS_TRANSFERRED,
            AgentFocusEventKind.FOCUS_RETURNED,
        }:
            if self.from_focus_role is None or self.from_focus_role == self.to_focus_role:
                raise ValueError("focus transition requires distinct from/to roles")
        if self.resulting_version < max(1, self.expected_version):
            raise ValueError("resultingVersion cannot precede expectedVersion")
        return self


class AgentRunError(ContractModel):
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool
    provider_status: int | None = Field(default=None, ge=100, le=599)


class AgentExecutionMetadata(ContractModel):
    mode: AgentMode
    provider_id: str | None = Field(default=None, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    advisory_only: Literal[True] = True
    is_simulated: bool
    data_status: AgentDataStatus
    source: str = Field(min_length=1, max_length=256)
    disclaimer: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_execution_truth(self) -> "AgentExecutionMetadata":
        expected = {
            AgentMode.DISABLED: (False, AgentDataStatus.UNAVAILABLE),
            AgentMode.SYNTHETIC: (True, AgentDataStatus.SIMULATED),
            AgentMode.REAL: (False, AgentDataStatus.PROVIDER_GENERATED_UNVERIFIED),
        }[self.mode]
        if (self.is_simulated, self.data_status) != expected:
            raise ValueError("mode must match isSimulated and dataStatus")
        if self.mode == AgentMode.DISABLED:
            if any((self.provider_id, self.model_id, self.prompt_version)):
                raise ValueError("disabled execution cannot claim provider identity")
            if self.source != "agent_disabled":
                raise ValueError("disabled execution source is invalid")
        else:
            if not all((self.provider_id, self.model_id, self.prompt_version)):
                raise ValueError("enabled execution requires complete provider identity")
            if self.source != self.provider_id:
                raise ValueError("execution source must equal providerId")
        return self


class AgentMessage(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1)
    role: AgentRole
    author_type: AgentMessageAuthorType
    kind: AgentMessageKind
    content: str = Field(min_length=1, max_length=8000)
    citations: list[AgentCitation] = Field(default_factory=list, max_length=100)
    generated_content: GeneratedAgentContent | None = None
    execution: AgentExecutionMetadata | None = None
    reply_to_message_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    created_at: datetime
    immutable: Literal[True] = True
    advisory_only: Literal[True] = True
    is_simulated: bool

    @field_validator("id", "project_id", "thread_id", "content")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _trimmed(value, "message value")

    @field_validator("reply_to_message_id")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return _optional_trimmed(value, "message reference")

    @model_validator(mode="after")
    def validate_message_authority(self) -> "AgentMessage":
        if self.author_type == AgentMessageAuthorType.HUMAN:
            if self.kind != AgentMessageKind.USER_INPUT:
                raise ValueError("human message must be user_input")
            if self.generated_content is not None or self.execution is not None:
                raise ValueError("human message cannot carry generated content or execution")
            if self.is_simulated:
                raise ValueError("human input cannot be marked simulated")
        else:
            if self.run_id is None:
                raise ValueError("Agent reply requires runId")
            if self.kind != AgentMessageKind.AGENT_REPLY:
                raise ValueError("Agent message must be agent_reply")
            if self.generated_content is None or self.execution is None:
                raise ValueError("Agent reply requires generated content and execution")
            if self.content != self.generated_content.reply_text:
                raise ValueError("Agent reply content must equal generated replyText")
            if self.citations != self.generated_content.citations:
                raise ValueError("Agent reply citations must equal generated citations")
            if self.is_simulated != self.execution.is_simulated:
                raise ValueError("message simulation truth must match execution")
        return self


class AgentRunStepRecord(ContractModel):
    step_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    step_index: Literal[1] = 1
    role: AgentRole
    status: AgentRunStepStatus
    provider_id: str
    model_id: str
    prompt_version: str
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    finished_at: datetime
    error: AgentRunError | None = None
    advisory_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_step(self) -> "AgentRunStepRecord":
        if self.finished_at < self.started_at:
            raise ValueError("finishedAt must not precede startedAt")
        if self.status == AgentRunStepStatus.COMPLETED:
            if self.output_hash is None or self.error is not None:
                raise ValueError("completed step requires outputHash and no error")
        elif self.output_hash is not None or self.error is None:
            raise ValueError("failed step requires error and no outputHash")
        return self


class AgentRunRecord(ContractModel):
    run_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    role: AgentRole
    status: AgentRunStatus
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_count: int = Field(ge=1, le=10)
    started_at: datetime
    finished_at: datetime | None = None
    error: AgentRunError | None = None
    execution: AgentExecutionMetadata
    steps: list[AgentRunStepRecord] = Field(default_factory=list, max_length=1)
    advisory_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_run(self) -> "AgentRunRecord":
        terminal = set(AgentRunStatus) - {AgentRunStatus.RUNNING}
        if (self.status in terminal) != (self.finished_at is not None):
            raise ValueError("terminal run status and finishedAt must appear together")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finishedAt must not precede startedAt")
        failure_statuses = {AgentRunStatus.FAILED, AgentRunStatus.UNAVAILABLE}
        if (self.status in failure_statuses) != (self.error is not None):
            raise ValueError("failed or unavailable status and error must appear together")
        if len(self.steps) > 1 or any(
            item.run_id != self.run_id or item.step_index != 1 for item in self.steps
        ):
            raise ValueError("a single-focus run may contain only step 1")
        if self.steps:
            step = self.steps[0]
            for field in ("provider_id", "model_id", "prompt_version", "input_hash", "context_version"):
                if getattr(step, field) != getattr(self.execution, field):
                    raise ValueError("run/step provenance must match")
            if step.output_hash != self.execution.output_hash:
                raise ValueError("run/step outputHash must match")
        return self


class AgentTurnResult(ContractModel):
    turn_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    status: AgentTurnStatus
    focus_role: AgentRole
    current_focus_role: AgentRole
    messages: list[AgentMessage] = Field(min_length=1, max_length=1)
    next_expected_version: int = Field(ge=1)
    execution: AgentExecutionMetadata
    advisory_only: Literal[True] = True
    schema_version: Literal["2.0"] = AGENT_COMMUNICATION_SCHEMA_VERSION

    @model_validator(mode="after")
    def validate_turn_result(self) -> "AgentTurnResult":
        message = self.messages[0]
        if message.run_id != self.run_id or message.author_type != AgentMessageAuthorType.AGENT:
            raise ValueError("turn result must contain its single Agent reply")
        if message.role != self.focus_role or message.execution != self.execution:
            raise ValueError("turn message role/provenance must match result")
        if self.focus_role in {AgentRole.RISK, AgentRole.LEADERSHIP}:
            if self.current_focus_role != AgentRole.BUSINESS:
                raise ValueError("temporary focus must return to business after success")
        elif self.current_focus_role != AgentRole.BUSINESS:
            raise ValueError("business turn must retain business focus")
        return self


class AgentProjectContext(ContractModel):
    project_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    summary: str = Field(min_length=1, max_length=4000)
    is_simulated: bool


class AgentDimensionContext(ContractModel):
    dimension_id: DimensionId
    name: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=4000)


class AgentPolicyContext(ContractModel):
    policy_result_id: str = Field(min_length=1, max_length=128)
    rule_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    result: Literal["pass", "block", "manual_review"]
    explanation: str = Field(min_length=1, max_length=4000)
    next_action: str = Field(min_length=1, max_length=2000)
    citations: list[AgentCitation] = Field(default_factory=list, max_length=50)


class AgentEvidenceContext(ContractModel):
    evidence_ref: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=512)
    dimension_id: DimensionId
    location_status: Literal["located", "pending", "unverifiable", "version_mismatch"]
    material_status: Literal["confirmed", "review", "conflict"]
    locator_summary: str | None = Field(default=None, max_length=2000)


class AgentFactContext(ContractModel):
    fact_version_id: str = Field(min_length=1, max_length=128)
    fact_key: str = Field(min_length=1, max_length=128)
    dimension_id: DimensionId
    label: str = Field(min_length=1, max_length=512)
    value_text: str = Field(min_length=1, max_length=4000)
    unit: str | None = Field(default=None, max_length=128)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)


class AgentApprovalContext(ContractModel):
    version: int = Field(ge=1)
    status: Literal["draft", "returned", "submitted", "completed"]
    hard_gate_status: Literal["pass", "block", "manual_review"]
    blocking_rule_ids: list[str] = Field(default_factory=list, max_length=100)
    risk_veto: bool
    summary: str = Field(min_length=1, max_length=2000)


class AgentVisibleMessageContext(ContractModel):
    message_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1)
    role: AgentRole
    author_type: AgentMessageAuthorType
    content: str = Field(min_length=1, max_length=8000)


class AgentProviderContext(ContractModel):
    project_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    target_role: AgentRole
    context_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    project_summary: AgentProjectContext
    dimension_summaries: list[AgentDimensionContext] = Field(default_factory=list, max_length=6)
    policy_results: list[AgentPolicyContext] = Field(default_factory=list, max_length=100)
    selected_evidence: list[AgentEvidenceContext] = Field(default_factory=list, max_length=50)
    selected_facts: list[AgentFactContext] = Field(default_factory=list, max_length=50)
    approval_state: AgentApprovalContext
    recent_visible_messages: list[AgentVisibleMessageContext] = Field(
        default_factory=list, max_length=40
    )
    citation_allowlist: list[AgentCitation] = Field(default_factory=list, max_length=100)
    current_instruction: str = Field(min_length=1, max_length=4000)
    is_context_simulated: bool
    disclaimer: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_context(self) -> "AgentProviderContext":
        if self.project_summary.project_id != self.project_id:
            raise ValueError("projectSummary.projectId must match projectId")
        messages = [item.message_id for item in self.recent_visible_messages]
        if len(set(messages)) != len(messages):
            raise ValueError("recentVisibleMessages must be unique by messageId")
        if any(
            left.sequence >= right.sequence
            for left, right in zip(
                self.recent_visible_messages, self.recent_visible_messages[1:]
            )
        ):
            raise ValueError("recentVisibleMessages must have increasing sequence")
        citations = [item.stable_tuple() for item in self.citation_allowlist]
        if len(set(citations)) != len(citations):
            raise ValueError("citationAllowlist must contain unique citation tuples")
        return self


_AUTHORITY_CLAIMS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:我|本Agent|系统)(?:已经|已|现予)?(?:批准|审批通过|拒绝|驳回)(?:本项目|该项目|申请|融资)",
        r"(?:本项目|该项目|申请|融资)(?:已经|已|现已)(?:批准|审批通过|拒绝|驳回)",
        r"(?:已经|已)(?:写入|修改|覆盖)(?:正式事实|权威事实|证据|制度|hard\s*gate|审批状态)",
        r"(?:审批|风险审查|正式审查|正式审批)(?:结论)?(?:已经|已|现已)?(?:为|是|：|:)?(?:通过|批准|同意|拒绝|驳回)",
        r"(?:本项目|该项目|申请|融资)[^。！？\n]{0,24}(?:符合放款条件|准予放款|批准融资|同意融资|审批通过)",
        r"(?:我|本Agent|系统)(?:已经|已|现已)?(?:将)?[^。！？\n]{0,24}(?:确认为|认定为|确权为|写入为)(?:正式事实|权威事实|正式证据|权威证据|制度|审批状态)",
        r"(?:我|本Agent|系统|本项目|该项目)?(?:已经|已|现已)?(?:解除|绕过|覆盖|废止|撤销)(?:正式)?\s*(?:hard\s*gate|gate|制度门槛|风险否决)",
        r"(?:批准融资|准予放款|批准放款|同意放款)",
        r"\bI\s+(?:hereby\s+)?(?:approve|reject|override)\b",
        r"\b(?:approval|rejection)\s+is\s+(?:final|authoritative)\b",
        r"\bhard\s*gate\s+(?:has\s+been\s+)?overridden\b",
        r"\b(?:wrote|updated|modified)\s+(?:the\s+)?(?:formal\s+fact|approval\s+state|evidence)\b",
    )
)

_QUOTED_TEXT = re.compile(
    r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"]*"|\'[^\']*\'', re.DOTALL
)
_NON_AUTHORITATIVE_PREFIX = re.compile(
    r"(?:不|未|无权|不得|不能|不可|不应|禁止|避免|尚未|并未|没有|不要|不作|建议|提议|请|是否|能否|待)"
    r"[^。！？；;\n]{0,12}$",
    re.IGNORECASE,
)


def _contains_forbidden_authority_claim(text: str) -> bool:
    without_quotes = _QUOTED_TEXT.sub("", text)
    for pattern in _AUTHORITY_CLAIMS:
        for match in pattern.finditer(without_quotes):
            sentence_start = max(
                without_quotes.rfind(separator, 0, match.start())
                for separator in ("。", "！", "？", "；", ";", "\n")
            )
            prefix = without_quotes[sentence_start + 1 : match.start()]
            if _NON_AUTHORITATIVE_PREFIX.search(prefix):
                continue
            return True
    return False


def validate_agent_provider_context(
    role: AgentRole,
    request: AgentTurnRequest,
    context: AgentProviderContext,
) -> AgentProviderContext:
    if context.target_role != role:
        raise ValueError("provider context targetRole must match server focus role")
    if context.current_instruction != request.instruction:
        raise ValueError("provider context currentInstruction must match request instruction")
    allowed = {item.stable_tuple() for item in context.citation_allowlist}
    for target in request.evidence_targets:
        if AgentCitation.from_evidence_target(target).stable_tuple() not in allowed:
            raise ValueError("request evidenceTarget must appear in citationAllowlist")
    return context


def validate_generated_agent_content(
    role: AgentRole,
    context: AgentProviderContext,
    content: GeneratedAgentContent,
) -> GeneratedAgentContent:
    del role
    allowed = {item.stable_tuple() for item in context.citation_allowlist}
    if any(item.stable_tuple() not in allowed for item in content.citations):
        raise ValueError("generated citation is outside the context allowlist")
    authored_text = "\n".join(
        [content.reply_text, *content.observations, *content.questions]
    )
    if _contains_forbidden_authority_claim(authored_text):
        raise ValueError("generated content contains a forbidden authority claim")
    return content


def _trimmed(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be blank")
    if value != value.strip():
        raise ValueError(f"{label} must not have surrounding whitespace")
    return value


def _optional_trimmed(value: str | None, label: str) -> str | None:
    if value is not None:
        _trimmed(value, label)
    return value


__all__ = [name for name in globals() if name.startswith("Agent") or name.startswith("AGENT_")]
__all__ += ["GeneratedAgentContent", "validate_agent_provider_context", "validate_generated_agent_content"]
