from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import Field, field_validator, model_validator

from app.contracts.base import ContractModel

if TYPE_CHECKING:
    from app.services.reconstruction import ProviderReconstructionResult


RECONSTRUCTION_SCHEMA_VERSION = "1.0"
RECONSTRUCTION_DISCLAIMER = (
    "三维资产仅按其明确 provenance 使用；多视角重建、AI 推测和模拟夹具必须分开，"
    "未通过输入覆盖与输出质量 Gate 的结果不得标为扫描、测绘或可消费资产。"
)


class ReconstructionPipeline(StrEnum):
    MULTI_VIEW = "multi_view_reconstruction"
    AI_INFERRED = "ai_inferred_generation"


class ReconstructionSubjectKind(StrEnum):
    EQUIPMENT = "equipment"
    SITE = "site"


class ReconstructionQualityProfile(StrEnum):
    EQUIPMENT_REVIEW_V1 = "equipment_review_v1"
    SITE_PROCESS_V1 = "site_process_v1"


class InputDataStatus(StrEnum):
    CAPTURED_ORIGINALS = "captured_originals"
    SYNTHETIC = "synthetic"


class CapturePoseSource(StrEnum):
    OPERATOR_DECLARED = "operator_declared"
    EXIF = "exif"
    CALIBRATED = "calibrated"


class OverlapBasis(StrEnum):
    OPERATOR_DECLARED = "operator_declared"
    ENGINE_MEASURED = "engine_measured"


class ScaleMode(StrEnum):
    UNKNOWN = "unknown"
    KNOWN_DISTANCE = "known_distance"
    CALIBRATION_TARGET = "calibration_target"


class SiteFlowNodeKind(StrEnum):
    RAW_MATERIAL_AREA = "raw_material_area"
    EQUIPMENT = "equipment"
    WORKSTATION = "workstation"
    PROCESS = "process"
    FINISHED_GOODS_AREA = "finished_goods_area"


class CaptureGateStatus(StrEnum):
    PASSED = "passed"
    NEEDS_MORE_INPUT = "needs_more_input"
    NOT_RECONSTRUCTION = "not_reconstruction"


class ReconstructionJobStatus(StrEnum):
    NEEDS_MORE_INPUT = "needs_more_input"
    BLOCKED = "blocked"
    QUEUED = "queued"
    RUNNING = "running"
    UNAVAILABLE = "unavailable"
    QUALITY_REVIEW = "quality_review"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReconstructionStage(StrEnum):
    INPUT_GATE = "input_gate"
    QUEUED = "queued"
    FEATURE_MATCHING = "feature_matching"
    GEOMETRY = "geometry"
    MESHING = "meshing"
    QUALITY_GATE = "quality_gate"
    PERSISTING_ASSETS = "persisting_assets"
    COMPLETE = "complete"
    FAILED = "failed"


class ReconstructionAssetKind(StrEnum):
    GLB = "glb"
    POINT_CLOUD_PLY = "point_cloud_ply"
    MESH_OBJ = "mesh_obj"


class ReconstructionAssetOrigin(StrEnum):
    MULTI_VIEW_RECONSTRUCTION = "multi_view_reconstruction"
    AI_INFERRED_GENERATION = "ai_inferred_generation"
    SIMULATED_FIXTURE = "simulated_fixture"


class ReconstructionAssetDataStatus(StrEnum):
    RECONSTRUCTED = "reconstructed"
    INFERRED = "inferred"
    SYNTHETIC = "synthetic"


class ReconstructionClaim(StrEnum):
    MULTI_VIEW_RECONSTRUCTION = "multi_view_reconstruction"
    INFERRED_NOT_SCAN = "inferred_not_scan"
    SIMULATED_NOT_SCAN = "simulated_not_scan"


class ReconstructionUnits(StrEnum):
    METER = "meter"
    UNSCALED = "unscaled"


class ReconstructionErrorCode(StrEnum):
    AI_INFERRED_NOT_RECONSTRUCTION = "ai_inferred_not_reconstruction"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    INVALID_PROVIDER_OUTPUT = "invalid_provider_output"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    CANCELLED = "cancelled"


class ReconstructionEngineStatus(ContractModel):
    """Local-engine availability only; it is not a reconstruction result."""

    engine: str = Field(min_length=1, max_length=128)
    available: bool
    supports_multi_view: bool
    detail: str = Field(min_length=1, max_length=1000)
    network_access: Literal[False] = False
    disclaimer: str = Field(min_length=1, max_length=1000)

    @field_validator("engine", "detail", "disclaimer")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "engine status")


class ReconstructionTruthDeclaration(ContractModel):
    is_simulated: bool
    data_status: InputDataStatus
    source: str = Field(min_length=1, max_length=500)
    disclaimer: str = Field(min_length=1, max_length=1000)

    @field_validator("source", "disclaimer")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "truth declaration")

    @model_validator(mode="after")
    def validate_simulation_truth(self) -> "ReconstructionTruthDeclaration":
        if self.is_simulated and self.data_status != InputDataStatus.SYNTHETIC:
            raise ValueError("simulated input must use synthetic dataStatus")
        if not self.is_simulated and self.data_status == InputDataStatus.SYNTHETIC:
            raise ValueError("synthetic input must set isSimulated=true")
        return self


class ReconstructionSubjectBinding(ContractModel):
    subject_kind: ReconstructionSubjectKind
    subject_id: str = Field(min_length=1, max_length=128)

    @field_validator("subject_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_identifier(value, "subjectId")


class ReconstructionImageInput(ContractModel):
    image_id: str = Field(min_length=1, max_length=128)
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_anchor_ids: list[str] = Field(default_factory=list, max_length=20)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    pixel_width: int = Field(gt=0, le=100_000)
    pixel_height: int = Field(gt=0, le=100_000)
    capture_order: int = Field(ge=0)
    azimuth_degrees: float = Field(ge=-180, lt=180)
    elevation_degrees: float = Field(ge=-90, le=90)
    pose_source: CapturePoseSource
    camera_id: str | None = Field(default=None, max_length=128)

    @field_validator("image_id", "material_id", "material_version_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_identifier(value, "image material identifier")

    @field_validator("source_anchor_ids")
    @classmethod
    def validate_source_anchor_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _require_identifier(value, "sourceAnchorId")
        if len(set(values)) != len(values):
            raise ValueError("sourceAnchorIds must be unique")
        return values

    @field_validator("camera_id")
    @classmethod
    def validate_camera_id(cls, value: str | None) -> str | None:
        if value is not None:
            _require_identifier(value, "cameraId")
        return value


class ReconstructionOverlap(ContractModel):
    from_image_id: str = Field(min_length=1, max_length=128)
    to_image_id: str = Field(min_length=1, max_length=128)
    estimated_overlap_percent: float = Field(ge=0, le=100)
    basis: OverlapBasis

    @field_validator("from_image_id", "to_image_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_identifier(value, "overlap image id")

    @model_validator(mode="after")
    def reject_self_edge(self) -> "ReconstructionOverlap":
        if self.from_image_id == self.to_image_id:
            raise ValueError("overlap edge cannot reference the same image twice")
        return self


class ReconstructionScaleReference(ContractModel):
    mode: ScaleMode
    distance_meters: float | None = Field(default=None, gt=0)
    source_image_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("source_image_ids")
    @classmethod
    def validate_source_image_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _require_identifier(value, "scale source image id")
        if len(set(values)) != len(values):
            raise ValueError("scale sourceImageIds must be unique")
        return values

    @model_validator(mode="after")
    def validate_scale_fields(self) -> "ReconstructionScaleReference":
        if self.mode == ScaleMode.UNKNOWN:
            if self.distance_meters is not None or self.source_image_ids:
                raise ValueError("unknown scale cannot carry a distance or source images")
        elif self.distance_meters is None or not self.source_image_ids:
            raise ValueError("known scale requires distanceMeters and sourceImageIds")
        return self


class SiteFlowNodeBinding(ContractModel):
    node_id: str = Field(min_length=1, max_length=128)
    kind: SiteFlowNodeKind
    label: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0)
    linked_subject_id: str | None = Field(default=None, max_length=128)
    capture_image_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("node_id", "label")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "site flow value")

    @field_validator("linked_subject_id")
    @classmethod
    def validate_linked_subject_id(cls, value: str | None) -> str | None:
        if value is not None:
            _require_identifier(value, "linkedSubjectId")
        return value

    @field_validator("capture_image_ids")
    @classmethod
    def validate_capture_image_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _require_identifier(value, "captureImageId")
        if len(set(values)) != len(values):
            raise ValueError("captureImageIds must be unique within a site flow node")
        return values


class ReconstructionCaptureSet(ContractModel):
    images: list[ReconstructionImageInput] = Field(min_length=1, max_length=500)
    overlaps: list[ReconstructionOverlap] = Field(default_factory=list, max_length=5000)
    scale_reference: ReconstructionScaleReference
    site_flow_nodes: list[SiteFlowNodeBinding] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_references(self) -> "ReconstructionCaptureSet":
        image_ids = [item.image_id for item in self.images]
        if len(set(image_ids)) != len(image_ids):
            raise ValueError("capture imageIds must be unique")
        material_versions = [
            (item.material_id, item.material_version_id) for item in self.images
        ]
        if len(set(material_versions)) != len(material_versions):
            raise ValueError("a material version may appear only once in a capture set")
        orders = [item.capture_order for item in self.images]
        if len(set(orders)) != len(orders):
            raise ValueError("captureOrder must be unique")

        known = set(image_ids)
        edge_keys: set[tuple[str, str]] = set()
        for edge in self.overlaps:
            if edge.from_image_id not in known or edge.to_image_id not in known:
                raise ValueError("overlap edges must reference capture images")
            key = tuple(sorted((edge.from_image_id, edge.to_image_id)))
            if key in edge_keys:
                raise ValueError("overlap edges must be unique regardless of direction")
            edge_keys.add(key)

        if any(value not in known for value in self.scale_reference.source_image_ids):
            raise ValueError("scale sourceImageIds must reference capture images")

        node_ids = [node.node_id for node in self.site_flow_nodes]
        sequences = [node.sequence for node in self.site_flow_nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("site flow nodeIds must be unique")
        if len(set(sequences)) != len(sequences):
            raise ValueError("site flow sequence values must be unique")
        for node in self.site_flow_nodes:
            if any(value not in known for value in node.capture_image_ids):
                raise ValueError("site flow nodes must reference capture images")
        return self


class ReconstructionJobRequest(ContractModel):
    subject: ReconstructionSubjectBinding
    pipeline: ReconstructionPipeline
    quality_profile: ReconstructionQualityProfile
    capture_set: ReconstructionCaptureSet
    requested_outputs: list[ReconstructionAssetKind] = Field(
        default_factory=lambda: [ReconstructionAssetKind.GLB],
        min_length=1,
        max_length=3,
    )
    truth: ReconstructionTruthDeclaration
    schema_version: Literal["1.0"] = RECONSTRUCTION_SCHEMA_VERSION

    @field_validator("requested_outputs")
    @classmethod
    def validate_requested_outputs(
        cls, values: list[ReconstructionAssetKind]
    ) -> list[ReconstructionAssetKind]:
        if len(set(values)) != len(values):
            raise ValueError("requestedOutputs must be unique")
        return values

    @model_validator(mode="after")
    def validate_profile_and_pipeline(self) -> "ReconstructionJobRequest":
        expected_profile = {
            ReconstructionSubjectKind.EQUIPMENT:
                ReconstructionQualityProfile.EQUIPMENT_REVIEW_V1,
            ReconstructionSubjectKind.SITE:
                ReconstructionQualityProfile.SITE_PROCESS_V1,
        }[self.subject.subject_kind]
        if self.quality_profile != expected_profile:
            raise ValueError("qualityProfile must match subjectKind")
        if self.pipeline == ReconstructionPipeline.MULTI_VIEW:
            if len(self.capture_set.images) < 2:
                raise ValueError("multi-view reconstruction requires at least two images")
        if (
            self.subject.subject_kind == ReconstructionSubjectKind.EQUIPMENT
            and self.capture_set.site_flow_nodes
        ):
            raise ValueError("equipment reconstruction cannot carry siteFlowNodes")
        return self


class ReconstructionGateIssue(ContractModel):
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=1000)
    retryable_with_more_input: bool

    @field_validator("code", "message")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "gate issue")


class CaptureGateMetrics(ContractModel):
    image_count: int = Field(ge=0)
    distinct_azimuth_bins: int = Field(ge=0)
    distinct_elevation_bands: int = Field(ge=0)
    connected_image_count: int = Field(ge=0)
    overlap_edge_count: int = Field(ge=0)
    minimum_declared_overlap_percent: float | None = Field(default=None, ge=0, le=100)
    site_flow_kinds: list[SiteFlowNodeKind] = Field(default_factory=list)
    scale_mode: ScaleMode
    measurement_scope: Literal["declared_metadata_only"] = "declared_metadata_only"


class CaptureGateReport(ContractModel):
    status: CaptureGateStatus
    profile: ReconstructionQualityProfile
    metrics: CaptureGateMetrics
    issues: list[ReconstructionGateIssue] = Field(default_factory=list, max_length=50)
    disclaimer: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_status(self) -> "CaptureGateReport":
        if self.status == CaptureGateStatus.PASSED and self.issues:
            raise ValueError("passed capture gate cannot contain issues")
        if self.status != CaptureGateStatus.PASSED and not self.issues:
            raise ValueError("non-passed capture gate requires issues")
        return self


class ReconstructionProgress(ContractModel):
    stage: ReconstructionStage
    percent: float = Field(ge=0, le=100)
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return _require_trimmed_text(value, "progress message")


class ReconstructionError(ContractModel):
    code: ReconstructionErrorCode
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool
    stage: ReconstructionStage

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return _require_trimmed_text(value, "error message")


class ReconstructionQualityMetrics(ContractModel):
    input_image_count: int = Field(gt=0)
    registered_image_count: int = Field(ge=0)
    registration_ratio: float = Field(ge=0, le=1)
    median_reprojection_error_px: float = Field(ge=0)
    sparse_point_count: int = Field(ge=0)
    dense_point_count: int = Field(ge=0)
    mesh_face_count: int = Field(ge=0)
    coverage_percent: float = Field(ge=0, le=100)
    texture_coverage_percent: float = Field(ge=0, le=100)
    spatial_flow_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    scale_mode: ScaleMode

    @model_validator(mode="after")
    def validate_registration_ratio(self) -> "ReconstructionQualityMetrics":
        expected = self.registered_image_count / self.input_image_count
        if abs(expected - self.registration_ratio) > 0.001:
            raise ValueError("registrationRatio must match registered/input image counts")
        return self


class OutputQualityGateReport(ContractModel):
    passed: bool
    profile: ReconstructionQualityProfile
    metrics: ReconstructionQualityMetrics
    issues: list[ReconstructionGateIssue] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_status(self) -> "OutputQualityGateReport":
        if self.passed and self.issues:
            raise ValueError("passed output quality gate cannot contain issues")
        if not self.passed and not self.issues:
            raise ValueError("failed output quality gate requires issues")
        return self


class ReconstructionProviderInfo(ContractModel):
    provider: str = Field(min_length=1, max_length=128)
    engine: str = Field(min_length=1, max_length=128)
    engine_version: str | None = Field(default=None, max_length=128)

    @field_validator("provider", "engine", "engine_version")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is not None:
            _require_trimmed_text(value, "provider info")
        return value


class ReconstructionVector3(ContractModel):
    x: float
    y: float
    z: float


class ReconstructionSpatialBinding(ContractModel):
    node_id: str = Field(min_length=1, max_length=128)
    kind: SiteFlowNodeKind
    label: str = Field(min_length=1, max_length=200)
    position: ReconstructionVector3
    source_image_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("node_id", "label")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "spatial binding")

    @field_validator("source_image_ids")
    @classmethod
    def validate_source_image_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            _require_identifier(value, "spatial sourceImageId")
        if len(set(values)) != len(values):
            raise ValueError("spatial sourceImageIds must be unique")
        return values


class ReconstructionAsset(ContractModel):
    asset_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=128)
    kind: ReconstructionAssetKind
    mime_type: Literal["model/gltf-binary", "application/ply", "text/plain"]
    file_name: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=1000)
    byte_size: int = Field(gt=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    coordinate_system: Literal["local_cartesian_y_up"]
    units: ReconstructionUnits
    origin: ReconstructionAssetOrigin
    claim: ReconstructionClaim
    quality_gate_passed: Literal[True]
    consumer_ready: Literal[True]
    is_simulated: bool
    data_status: ReconstructionAssetDataStatus
    source: str = Field(min_length=1, max_length=500)
    disclaimer: str = Field(min_length=1, max_length=1000)
    spatial_bindings: list[ReconstructionSpatialBinding] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("asset_id", "project_id", "job_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_identifier(value, "asset identifier")

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        value = _require_trimmed_text(value, "fileName")
        if value in {".", ".."} or "/" in value or "\\" in value or ":" in value:
            raise ValueError("fileName must be a safe base name")
        return value

    @field_validator("storage_key")
    @classmethod
    def validate_storage_key(cls, value: str) -> str:
        value = _require_trimmed_text(value, "storageKey")
        parts = value.split("/")
        if (
            value.startswith("/")
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("storageKey must be a safe relative POSIX path")
        return value

    @field_validator("source", "disclaimer")
    @classmethod
    def validate_truth_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "asset truth")

    @model_validator(mode="after")
    def preserve_asset_truth(self) -> "ReconstructionAsset":
        expected_mime = {
            ReconstructionAssetKind.GLB: "model/gltf-binary",
            ReconstructionAssetKind.POINT_CLOUD_PLY: "application/ply",
            ReconstructionAssetKind.MESH_OBJ: "text/plain",
        }[self.kind]
        if self.mime_type != expected_mime:
            raise ValueError("mimeType must match asset kind")

        if self.is_simulated:
            if (
                self.data_status != ReconstructionAssetDataStatus.SYNTHETIC
                or self.claim != ReconstructionClaim.SIMULATED_NOT_SCAN
            ):
                raise ValueError("simulated assets must remain synthetic and not-scan")
        elif self.origin == ReconstructionAssetOrigin.MULTI_VIEW_RECONSTRUCTION:
            if (
                self.data_status != ReconstructionAssetDataStatus.RECONSTRUCTED
                or self.claim != ReconstructionClaim.MULTI_VIEW_RECONSTRUCTION
            ):
                raise ValueError("real multi-view assets require reconstructed provenance")
        elif self.origin == ReconstructionAssetOrigin.AI_INFERRED_GENERATION:
            if (
                self.data_status != ReconstructionAssetDataStatus.INFERRED
                or self.claim != ReconstructionClaim.INFERRED_NOT_SCAN
            ):
                raise ValueError("AI-inferred assets must be marked inferred_not_scan")
        else:
            raise ValueError("simulated fixture assets must set isSimulated=true")
        node_ids = [binding.node_id for binding in self.spatial_bindings]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("spatialBindings nodeIds must be unique")
        return self


class ReconstructionJob(ContractModel):
    job_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    request: ReconstructionJobRequest
    status: ReconstructionJobStatus
    progress: ReconstructionProgress
    capture_gate: CaptureGateReport
    output_quality_gate: OutputQualityGateReport | None = None
    provider_info: ReconstructionProviderInfo | None = None
    assets: list[ReconstructionAsset] = Field(default_factory=list, max_length=10)
    error: ReconstructionError | None = None
    attempt: int = Field(ge=0)
    max_attempts: int = Field(ge=1, le=5)
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    schema_version: Literal["1.0"] = RECONSTRUCTION_SCHEMA_VERSION

    @field_validator("job_id", "project_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_identifier(value, "job identifier")

    @model_validator(mode="after")
    def validate_state(self) -> "ReconstructionJob":
        if self.request.subject.subject_id == "":
            raise ValueError("subjectId cannot be blank")
        if self.status == ReconstructionJobStatus.QUEUED:
            if self.capture_gate.status != CaptureGateStatus.PASSED:
                raise ValueError("queued job requires a passed capture gate")
        if self.status == ReconstructionJobStatus.NEEDS_MORE_INPUT:
            if self.capture_gate.status != CaptureGateStatus.NEEDS_MORE_INPUT:
                raise ValueError("needs_more_input job requires matching capture gate")
        if self.status in {
            ReconstructionJobStatus.BLOCKED,
            ReconstructionJobStatus.FAILED,
            ReconstructionJobStatus.UNAVAILABLE,
        }:
            if self.error is None:
                raise ValueError("blocked or failed job requires an error")
        elif self.error is not None:
            raise ValueError("only blocked or failed jobs may carry an error")
        if self.status == ReconstructionJobStatus.SUCCEEDED:
            if (
                self.output_quality_gate is None
                or not self.output_quality_gate.passed
                or not self.assets
            ):
                raise ValueError("succeeded job requires passed quality gate and assets")
        elif self.assets:
            raise ValueError("unaccepted assets cannot be exposed before job success")
        if any(
            asset.project_id != self.project_id or asset.job_id != self.job_id
            for asset in self.assets
        ):
            raise ValueError("assets must belong to the job project and id")
        if self.status == ReconstructionJobStatus.SUCCEEDED:
            if self.request.subject.subject_kind == ReconstructionSubjectKind.SITE:
                glb_assets = [
                    asset for asset in self.assets
                    if asset.kind == ReconstructionAssetKind.GLB
                ]
                expected_nodes = {
                    node.node_id for node in self.request.capture_set.site_flow_nodes
                }
                if not glb_assets or not any(
                    {binding.node_id for binding in asset.spatial_bindings}
                    == expected_nodes
                    for asset in glb_assets
                ):
                    raise ValueError(
                        "succeeded site GLB must bind every declared site flow node"
                    )
            elif any(asset.spatial_bindings for asset in self.assets):
                raise ValueError("equipment assets cannot carry site spatialBindings")
        if self.updated_at < self.created_at:
            raise ValueError("updatedAt cannot precede createdAt")
        return self


class ReconstructionRetryRequest(ContractModel):
    expected_version: int = Field(ge=1)


@runtime_checkable
class ReconstructionProviderPort(Protocol):
    """Execution boundary for a future local GPU or explicitly authorized provider.

    Implementations may only derive reconstruction artifacts. They cannot write
    facts, evidence, scores, decisions, hard gates, approvals, or P5 candidates.
    """

    def supports(self, pipeline: ReconstructionPipeline) -> bool: ...

    def status(self) -> ReconstructionEngineStatus: ...

    def reconstruct(
        self,
        job_id: str,
        request: ReconstructionJobRequest,
    ) -> "ProviderReconstructionResult": ...


def _require_trimmed_text(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be blank")
    if value != value.strip():
        raise ValueError(f"{label} must not have surrounding whitespace")
    return value


def _require_identifier(value: str, label: str) -> str:
    value = _require_trimmed_text(value, label)
    if any(character in value for character in ("/", "\\", ":")) or value in {".", ".."}:
        raise ValueError(f"{label} must not contain path syntax")
    return value


__all__ = [
    "CaptureGateMetrics",
    "CaptureGateReport",
    "CaptureGateStatus",
    "CapturePoseSource",
    "InputDataStatus",
    "OutputQualityGateReport",
    "OverlapBasis",
    "RECONSTRUCTION_DISCLAIMER",
    "RECONSTRUCTION_SCHEMA_VERSION",
    "ReconstructionAsset",
    "ReconstructionAssetDataStatus",
    "ReconstructionAssetKind",
    "ReconstructionAssetOrigin",
    "ReconstructionCaptureSet",
    "ReconstructionClaim",
    "ReconstructionError",
    "ReconstructionErrorCode",
    "ReconstructionEngineStatus",
    "ReconstructionGateIssue",
    "ReconstructionImageInput",
    "ReconstructionJob",
    "ReconstructionJobRequest",
    "ReconstructionJobStatus",
    "ReconstructionOverlap",
    "ReconstructionPipeline",
    "ReconstructionProgress",
    "ReconstructionProviderInfo",
    "ReconstructionProviderPort",
    "ReconstructionQualityMetrics",
    "ReconstructionQualityProfile",
    "ReconstructionRetryRequest",
    "ReconstructionScaleReference",
    "ReconstructionStage",
    "ReconstructionSpatialBinding",
    "ReconstructionSubjectBinding",
    "ReconstructionSubjectKind",
    "ReconstructionTruthDeclaration",
    "ReconstructionUnits",
    "ReconstructionVector3",
    "ScaleMode",
    "SiteFlowNodeBinding",
    "SiteFlowNodeKind",
]
