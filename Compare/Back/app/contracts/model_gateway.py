from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.base import ContractModel
from app.contracts.material_intelligence import (
    DataClassification,
    MaterialIntelligenceDataStatus,
    MaterialIntelligenceResult,
    MaterialIntelligenceTaskGoal,
    MaterialMediaKind,
    SourceAnchor,
)
from app.contracts.workbench import EvidenceLocator


MODEL_GATEWAY_SCHEMA_VERSION = "1.0"


class ModelGatewayMode(StrEnum):
    DISABLED = "disabled"
    SYNTHETIC = "synthetic"
    REAL = "real"


class ModelGatewayOutputKind(StrEnum):
    OBSERVATIONS = "observations"
    FIELD_CANDIDATES = "field_candidates"
    SOURCE_ANCHORS = "source_anchors"
    SCENE_SPEC = "scene_spec"


class ModelGatewayRunStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"


class ModelGatewayErrorCode(StrEnum):
    GATEWAY_DISABLED = "gateway_disabled"
    CAPABILITY_NOT_SUPPORTED = "capability_not_supported"
    REQUEST_INVALID = "request_invalid"
    AUTHORIZATION_REQUIRED = "authorization_required"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    CONTENT_UNSUPPORTED = "content_unsupported"
    SAFETY_BLOCKED = "safety_blocked"
    INVALID_OUTPUT = "invalid_output"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


RETRYABLE_MODEL_GATEWAY_ERRORS = frozenset(
    {
        ModelGatewayErrorCode.RATE_LIMITED,
        ModelGatewayErrorCode.TIMEOUT,
        ModelGatewayErrorCode.PROVIDER_UNAVAILABLE,
    }
)


class ModelGatewayCapability(ContractModel):
    capability_id: str = Field(min_length=1, max_length=128)
    provider_id: str = Field(min_length=1, max_length=128)
    supported_modes: list[ModelGatewayMode] = Field(min_length=1, max_length=2)
    input_kinds: list[MaterialMediaKind] = Field(min_length=1)
    output_kinds: list[ModelGatewayOutputKind] = Field(min_length=1)
    advisory_only: Literal[True] = True
    schema_version: Literal["1.0"] = MODEL_GATEWAY_SCHEMA_VERSION

    @model_validator(mode="after")
    def validate_capability(self) -> "ModelGatewayCapability":
        if ModelGatewayMode.DISABLED in self.supported_modes:
            raise ValueError("disabled is a gateway state, not a provider capability")
        for label, values in (
            ("supportedModes", self.supported_modes),
            ("inputKinds", self.input_kinds),
            ("outputKinds", self.output_kinds),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must not contain duplicates")
        return self


class ModelGatewayFieldSchema(ContractModel):
    field_key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    value_type: Literal["string", "integer", "number", "boolean", "unknown"]


class ModelGatewayProjectContext(ContractModel):
    dimension_id: Literal[
        "compliance", "transaction", "production", "revenue", "debt", "cashflow"
    ]
    industry_code: str | None = Field(default=None, max_length=128)
    locale: Literal["zh-CN"] = "zh-CN"


class ModelGatewayMaterialInput(ContractModel):
    project_id: str = Field(min_length=1, max_length=128)
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_kind: MaterialMediaKind
    source_ref: str = Field(min_length=1, max_length=512)
    data_classification: DataClassification
    usage_authorization_ref: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_authorization(self) -> "ModelGatewayMaterialInput":
        if (
            self.data_classification == DataClassification.AUTHORIZED_CUSTOMER
            and not self.usage_authorization_ref
        ):
            raise ValueError("authorized_customer material requires usageAuthorizationRef")
        return self


class ModelGatewayRequest(ContractModel):
    request_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=128)
    mode: ModelGatewayMode
    trigger: Literal["explicit_action"]
    material: ModelGatewayMaterialInput
    context_version: str = Field(min_length=1, max_length=128)
    project_context: ModelGatewayProjectContext
    field_schemas: list[ModelGatewayFieldSchema] = Field(default_factory=list, max_length=100)
    task_goals: list[MaterialIntelligenceTaskGoal] = Field(min_length=1, max_length=4)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: Literal["1.0"] = MODEL_GATEWAY_SCHEMA_VERSION

    @model_validator(mode="after")
    def validate_request(self) -> "ModelGatewayRequest":
        if len(set(self.task_goals)) != len(self.task_goals):
            raise ValueError("taskGoals must not contain duplicates")
        field_keys = [item.field_key for item in self.field_schemas]
        if len(set(field_keys)) != len(field_keys):
            raise ValueError("fieldSchemas fieldKey values must be unique")
        return self


class ModelGatewayLocatorBinding(ContractModel):
    source_anchor_id: str = Field(min_length=1, max_length=128)
    locator: EvidenceLocator


class ModelGatewayError(ContractModel):
    code: ModelGatewayErrorCode
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool
    provider_status: int | None = Field(default=None, ge=100, le=599)

    @model_validator(mode="after")
    def validate_retryability(self) -> "ModelGatewayError":
        expected = self.code in RETRYABLE_MODEL_GATEWAY_ERRORS
        if self.retryable is not expected:
            raise ValueError("retryable must match the frozen error taxonomy")
        return self


class ModelGatewayOutput(ContractModel):
    request_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=128)
    mode: ModelGatewayMode
    status: ModelGatewayRunStatus
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: MaterialIntelligenceResult | None = None
    source_anchors: list[SourceAnchor] = Field(default_factory=list, max_length=500)
    locator_bindings: list[ModelGatewayLocatorBinding] = Field(default_factory=list, max_length=500)
    error: ModelGatewayError | None = None
    advisory_only: Literal[True] = True
    is_simulated: bool
    data_status: MaterialIntelligenceDataStatus
    source: str = Field(min_length=1, max_length=256)
    disclaimer: str = Field(min_length=1, max_length=2000)
    schema_version: Literal["1.0"] = MODEL_GATEWAY_SCHEMA_VERSION

    @model_validator(mode="after")
    def validate_output(self) -> "ModelGatewayOutput":
        successful = {
            ModelGatewayRunStatus.SUCCEEDED,
            ModelGatewayRunStatus.NEEDS_REVIEW,
        }
        if self.status in successful and self.result is None:
            raise ValueError("successful gateway output requires result")
        if self.status not in successful and self.result is not None:
            raise ValueError("non-successful gateway output must not carry result")
        if self.status == ModelGatewayRunStatus.FAILED and self.error is None:
            raise ValueError("failed gateway output requires error")
        if self.status != ModelGatewayRunStatus.FAILED and self.error is not None:
            raise ValueError("only failed gateway output may carry error")
        self._validate_mode_truth()
        self._validate_result_binding()
        return self

    def _validate_mode_truth(self) -> None:
        expected = {
            ModelGatewayMode.DISABLED: (False, MaterialIntelligenceDataStatus.UNAVAILABLE),
            ModelGatewayMode.SYNTHETIC: (True, MaterialIntelligenceDataStatus.SIMULATED),
            ModelGatewayMode.REAL: (
                False,
                MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED,
            ),
        }[self.mode]
        if (self.is_simulated, self.data_status) != expected:
            raise ValueError("mode must match isSimulated and dataStatus")
        if self.mode == ModelGatewayMode.DISABLED and self.status != ModelGatewayRunStatus.UNAVAILABLE:
            raise ValueError("disabled mode must be unavailable")

    def _validate_result_binding(self) -> None:
        if self.result is None:
            if self.source_anchors or self.locator_bindings:
                raise ValueError("output without result must not carry anchors or locators")
            return
        if (
            self.result.material_id != self.material_id
            or self.result.material_version_id != self.material_version_id
            or self.result.input_hash != self.input_hash
        ):
            raise ValueError("gateway result must bind materialId/version/inputHash")
        if (
            self.result.advisory_only is not True
            or self.result.is_simulated != self.is_simulated
            or self.result.data_status != self.data_status
            or self.result.source != self.source
            or self.result.disclaimer != self.disclaimer
        ):
            raise ValueError("gateway result metadata must match the output envelope")
        result_anchors = {item.id: item for item in self.result.source_anchors}
        anchors_by_id = {item.id: item for item in self.source_anchors}
        if (
            len(anchors_by_id) != len(self.source_anchors)
            or result_anchors.keys() != anchors_by_id.keys()
            or any(
                result_anchors[anchor_id] != anchors_by_id[anchor_id]
                for anchor_id in result_anchors
            )
        ):
            raise ValueError("sourceAnchors must match the validated result")
        for binding in self.locator_bindings:
            anchor = anchors_by_id.get(binding.source_anchor_id)
            if anchor is None:
                raise ValueError("locatorBinding must reference a SourceAnchor")
            locator = binding.locator
            if (
                locator.material_id != anchor.material_id
                or locator.material_version_id != anchor.material_version_id
            ):
                raise ValueError("locatorBinding must bind the SourceAnchor material/version")
            if locator.kind != anchor.kind:
                raise ValueError("locatorBinding kind must match the SourceAnchor kind")


class ModelGatewayRunRecord(ContractModel):
    run_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=128)
    mode: ModelGatewayMode
    status: ModelGatewayRunStatus
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_id: str | None = Field(default=None, max_length=128)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: ModelGatewayError | None = None
    advisory_only: Literal[True] = True
    is_simulated: bool
    data_status: MaterialIntelligenceDataStatus
    source: str = Field(min_length=1, max_length=256)
    disclaimer: str = Field(min_length=1, max_length=2000)
    schema_version: Literal["1.0"] = MODEL_GATEWAY_SCHEMA_VERSION

    @model_validator(mode="after")
    def validate_record(self) -> "ModelGatewayRunRecord":
        terminal = {
            ModelGatewayRunStatus.SUCCEEDED,
            ModelGatewayRunStatus.NEEDS_REVIEW,
            ModelGatewayRunStatus.FAILED,
            ModelGatewayRunStatus.CANCELLED,
            ModelGatewayRunStatus.UNAVAILABLE,
        }
        if self.status in terminal and self.finished_at is None:
            raise ValueError("terminal run status requires finishedAt")
        if self.status not in terminal and self.finished_at is not None:
            raise ValueError("non-terminal run status must not carry finishedAt")
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValueError("finishedAt must not precede startedAt")
        if (self.status == ModelGatewayRunStatus.FAILED) != (self.error is not None):
            raise ValueError("failed run status and error must appear together")
        expected = {
            ModelGatewayMode.DISABLED: (False, MaterialIntelligenceDataStatus.UNAVAILABLE),
            ModelGatewayMode.SYNTHETIC: (True, MaterialIntelligenceDataStatus.SIMULATED),
            ModelGatewayMode.REAL: (
                False,
                MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED,
            ),
        }[self.mode]
        if (self.is_simulated, self.data_status) != expected:
            raise ValueError("mode must match isSimulated and dataStatus")
        if self.mode == ModelGatewayMode.DISABLED and self.status != ModelGatewayRunStatus.UNAVAILABLE:
            raise ValueError("disabled mode must be unavailable")
        return self


__all__ = [
    "MODEL_GATEWAY_SCHEMA_VERSION",
    "RETRYABLE_MODEL_GATEWAY_ERRORS",
    "ModelGatewayCapability",
    "ModelGatewayError",
    "ModelGatewayErrorCode",
    "ModelGatewayFieldSchema",
    "ModelGatewayLocatorBinding",
    "ModelGatewayMaterialInput",
    "ModelGatewayMode",
    "ModelGatewayOutput",
    "ModelGatewayOutputKind",
    "ModelGatewayProjectContext",
    "ModelGatewayRequest",
    "ModelGatewayRunRecord",
    "ModelGatewayRunStatus",
]
