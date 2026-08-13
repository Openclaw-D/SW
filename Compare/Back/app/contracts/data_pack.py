from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.base import ContractModel
from app.contracts.material_intelligence import (
    DataClassification,
    MaterialIntelligenceResult,
    MaterialIntelligenceTaskGoal,
    SceneSpec,
)
from app.contracts.model_gateway import ModelGatewayMode
from app.contracts.workbench import (
    ApprovalState,
    CommonReviewEvent,
    FactValue,
    FactVersion,
    HardConstraintResult,
)


class ControlledImportManifestItem(ContractModel):
    material_id: str = Field(min_length=1, max_length=200)
    source_file: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: DataClassification
    authorization_ref: str = Field(min_length=1, max_length=256)
    material: dict[str, Any]

    @field_validator("source_file")
    @classmethod
    def validate_relative_source(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized or ".." in normalized.split("/"):
            raise ValueError("sourceFile must be a safe path relative to the authorized import root")
        return normalized


class ControlledImportManifest(ContractModel):
    manifest_version: Literal["1.0"] = "1.0"
    project_id: str = Field(min_length=1, max_length=160)
    items: list[ControlledImportManifestItem] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_unique_materials(self) -> "ControlledImportManifest":
        ids = [item.material_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("manifest materialId values must be unique")
        return self


class ImportManifestRequest(ContractModel):
    project_id: str = Field(min_length=1, max_length=160)
    manifest_ref: str = Field(min_length=1, max_length=500)

    @field_validator("manifest_ref")
    @classmethod
    def validate_manifest_ref(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if (
            normalized.startswith("/")
            or ":" in normalized
            or any(not part or part in {".", ".."} for part in parts)
        ):
            raise ValueError("manifestRef must be a safe relative path")
        return normalized


class ExecuteImportManifestRequest(ImportManifestRequest):
    expected_version: int = Field(ge=1)


class MaterialImportPreview(ContractModel):
    material_id: str
    material_version_id: str
    kind: Literal["excel", "pdf", "document", "image", "media", "scene"]
    content_hash: str
    classification: DataClassification
    authorization_ref: str
    source_ref: str
    folder_path: str | None = None
    business_path: str | None = None


class MaterialImportPreflight(ContractModel):
    project_id: str
    manifest_ref: str
    manifest_hash: str
    project_version: int = Field(ge=1)
    items: list[MaterialImportPreview]
    is_simulated: bool


class MaterialUploadReceipt(ContractModel):
    project_id: str
    upload_id: str
    file_name: str
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_ref: str
    is_simulated: Literal[True] = True


class MaterialImportResult(MaterialImportPreflight):
    import_id: str
    imported_count: int = Field(ge=0)
    replayed: bool = False


class MaterialIntelligenceRunCommand(ContractModel):
    project_id: str
    material_id: str
    material_version_id: str
    context_version: str = Field(min_length=1, max_length=128)
    task_goals: list[MaterialIntelligenceTaskGoal] = Field(min_length=1, max_length=4)
    expected_version: int = Field(ge=1)
    provider_mode: ModelGatewayMode | None = None

    @model_validator(mode="after")
    def validate_goals(self) -> "MaterialIntelligenceRunCommand":
        if len(set(self.task_goals)) != len(self.task_goals):
            raise ValueError("taskGoals must be unique")
        return self


class StoredMaterialIntelligence(ContractModel):
    run_id: str
    result: MaterialIntelligenceResult
    candidate_ids: list[str]
    evidence_refs: list[str]
    created_at: str


class CandidateConfirmationCommand(ContractModel):
    project_id: str
    candidate_id: str
    from_fact_version_id: str
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    proposed_value: FactValue | None = None


class CandidateConfirmationResult(ContractModel):
    confirmation_id: str
    candidate_id: str
    fact_version: FactVersion
    event: CommonReviewEvent
    policy_results: list[HardConstraintResult]
    approval: ApprovalState


class StoredSceneSpec(ContractModel):
    scene_id: str
    project_id: str
    material_id: str
    material_version_id: str
    source_anchor_ids: list[str]
    spec: SceneSpec
    is_simulated: bool
    created_at: str


__all__ = [
    "CandidateConfirmationCommand",
    "CandidateConfirmationResult",
    "ControlledImportManifest",
    "ExecuteImportManifestRequest",
    "ImportManifestRequest",
    "MaterialImportPreflight",
    "MaterialImportResult",
    "MaterialUploadReceipt",
    "MaterialIntelligenceRunCommand",
    "StoredMaterialIntelligence",
    "StoredSceneSpec",
]
