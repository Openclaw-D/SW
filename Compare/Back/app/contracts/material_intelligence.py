from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import Field, field_validator, model_validator

from app.contracts.base import ContractModel
from app.contracts.workbench import NormalizedBBox


MATERIAL_INTELLIGENCE_SCHEMA_VERSION = "1.0"
MATERIAL_INTELLIGENCE_DISCLAIMER = (
    "材料智能输出仅供人工核验参考；候选、观察与 SceneSpec 均不得直接写入"
    "权威事实、评分、决策、置信度、hard gate 或审批状态。"
)
MATERIAL_INTELLIGENCE_FUTURE_PATH = (
    "/api/v1/projects/{projectId}/materials/{materialId}/intelligence"
)


class MaterialMediaKind(StrEnum):
    IMAGE = "image"
    PDF = "pdf"
    EXCEL = "excel"
    DOCUMENT = "document"
    MEDIA = "media"


class DataClassification(StrEnum):
    AUTHORIZED_CUSTOMER = "authorized_customer"
    PUBLIC_REFERENCE = "public_reference"
    SYNTHETIC_DEMO = "synthetic_demo"


class MaterialIntelligenceTaskGoal(StrEnum):
    OBSERVE = "observe"
    EXTRACT_FIELD_CANDIDATES = "extract_field_candidates"
    IDENTIFY_UNRESOLVED = "identify_unresolved"
    SCENE_SPEC = "scene_spec"


class MaterialIntelligenceStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    UNAVAILABLE = "unavailable"


class MaterialIntelligenceDataStatus(StrEnum):
    SIMULATED = "simulated"
    PROVIDER_GENERATED_UNVERIFIED = "provider_generated_unverified"
    UNAVAILABLE = "unavailable"


class ObservationKind(StrEnum):
    CONTENT_SUMMARY = "content_summary"
    VISUAL_DETAIL = "visual_detail"
    OCR_TEXT = "ocr_text"
    STRUCTURE = "structure"


class FieldCandidateStatus(StrEnum):
    CANDIDATE = "candidate"
    NEEDS_REVIEW = "needs_review"
    CONFLICTING = "conflicting"


class UnresolvedItemKind(StrEnum):
    MISSING_MATERIAL = "missing_material"
    UNREADABLE_CONTENT = "unreadable_content"
    AMBIGUOUS_CONTENT = "ambiguous_content"
    CROSS_SOURCE_CONFLICT = "cross_source_conflict"
    MANUAL_REVIEW = "manual_review"


class SceneObjectKind(StrEnum):
    BOX = "box"
    PLANE = "plane"
    MARKER = "marker"
    LABEL = "label"


class SceneCameraPreset(StrEnum):
    PERSPECTIVE = "perspective"
    FRONT = "front"
    SIDE = "side"
    TOP = "top"


class MaterialIntelligenceRequest(ContractModel):
    project_id: str = Field(min_length=1, max_length=128)
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_kind: MaterialMediaKind
    context_version: str = Field(min_length=1, max_length=128)
    task_goals: list[MaterialIntelligenceTaskGoal] = Field(min_length=1, max_length=4)
    locale: Literal["zh-CN"] = "zh-CN"
    data_classification: DataClassification
    usage_authorization_ref: str | None = Field(default=None, max_length=256)

    @field_validator(
        "project_id",
        "material_id",
        "material_version_id",
        "context_version",
    )
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_trimmed_text(value, "identifier")

    @field_validator("usage_authorization_ref")
    @classmethod
    def validate_authorization_ref(cls, value: str | None) -> str | None:
        if value is not None:
            _require_trimmed_text(value, "usageAuthorizationRef")
        return value

    @model_validator(mode="after")
    def validate_request_scope(self) -> "MaterialIntelligenceRequest":
        if len(set(self.task_goals)) != len(self.task_goals):
            raise ValueError("taskGoals must not contain duplicates")
        if (
            self.data_classification == DataClassification.AUTHORIZED_CUSTOMER
            and self.usage_authorization_ref is None
        ):
            raise ValueError(
                "authorized_customer material requires usageAuthorizationRef"
            )
        return self


class NormalizedPoint(ContractModel):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)


class BaseSourceAnchor(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("id", "material_id", "material_version_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_trimmed_text(value, "anchor identifier")


class ImageSourceAnchor(BaseSourceAnchor):
    kind: Literal["image"]
    page: Literal[1] = 1
    bbox: NormalizedBBox
    polygon: list[NormalizedPoint] | None = Field(default=None, min_length=3, max_length=64)
    ocr_token_ids: list[str] = Field(default_factory=list, max_length=256)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_ocr_span(self) -> "ImageSourceAnchor":
        _validate_ocr_span(self.ocr_token_ids, self.char_start, self.char_end)
        return self


class PdfSourceAnchor(BaseSourceAnchor):
    kind: Literal["pdf"]
    page: int = Field(ge=1)
    bbox: NormalizedBBox
    polygon: list[NormalizedPoint] | None = Field(default=None, min_length=3, max_length=64)
    ocr_token_ids: list[str] = Field(default_factory=list, max_length=256)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_ocr_span(self) -> "PdfSourceAnchor":
        _validate_ocr_span(self.ocr_token_ids, self.char_start, self.char_end)
        return self


class ExcelSourceAnchor(BaseSourceAnchor):
    kind: Literal["excel"]
    sheet: str = Field(min_length=1, max_length=128)
    range: str = Field(
        pattern=r"^[A-Za-z]+[1-9][0-9]*(?::[A-Za-z]+[1-9][0-9]*)?$"
    )

    @field_validator("sheet")
    @classmethod
    def validate_sheet(cls, value: str) -> str:
        return _require_trimmed_text(value, "sheet")


class DocumentSourceAnchor(BaseSourceAnchor):
    kind: Literal["document"]
    paragraph_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    rendered_page: int = Field(ge=1)
    rendered_page_bbox: NormalizedBBox

    @field_validator("paragraph_id", "run_id")
    @classmethod
    def validate_document_identifier(cls, value: str) -> str:
        return _require_trimmed_text(value, "document anchor identifier")


class MediaSourceAnchor(BaseSourceAnchor):
    kind: Literal["media"]
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(ge=0, allow_inf_nan=False)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    bbox: NormalizedBBox

    @model_validator(mode="after")
    def validate_temporal_range(self) -> "MediaSourceAnchor":
        if self.end_seconds < self.start_seconds:
            raise ValueError("media endSeconds must not precede startSeconds")
        if self.end_frame < self.start_frame:
            raise ValueError("media endFrame must not precede startFrame")
        return self


SourceAnchor = Annotated[
    Union[
        ImageSourceAnchor,
        PdfSourceAnchor,
        ExcelSourceAnchor,
        DocumentSourceAnchor,
        MediaSourceAnchor,
    ],
    Field(discriminator="kind"),
]


class Observation(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    kind: ObservationKind
    text: str = Field(min_length=1, max_length=4000)
    source_anchor_ids: list[str] = Field(min_length=1, max_length=32)

    @field_validator("id", "text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "observation value")

    @field_validator("source_anchor_ids")
    @classmethod
    def validate_source_anchor_ids(cls, values: list[str]) -> list[str]:
        return _validate_unique_identifiers(values, "sourceAnchorIds")


CandidateValue = str | int | float | bool | None


class ExtractedFieldCandidate(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    field_key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=256)
    value: CandidateValue
    unit: str | None = Field(default=None, max_length=64)
    status: FieldCandidateStatus
    source_anchor_ids: list[str] = Field(min_length=1, max_length=32)

    @field_validator("id", "field_key", "label")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "candidate value")

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str | None) -> str | None:
        if value is not None:
            _require_trimmed_text(value, "unit")
        return value

    @field_validator("source_anchor_ids")
    @classmethod
    def validate_source_anchor_ids(cls, values: list[str]) -> list[str]:
        return _validate_unique_identifiers(values, "sourceAnchorIds")


class UnresolvedItem(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    kind: UnresolvedItemKind
    question: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    requires_human_review: Literal[True]
    source_anchor_ids: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("id", "question", "reason")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _require_trimmed_text(value, "unresolved value")

    @field_validator("source_anchor_ids")
    @classmethod
    def validate_source_anchor_ids(cls, values: list[str]) -> list[str]:
        return _validate_unique_identifiers(values, "sourceAnchorIds")


class SceneVector3(ContractModel):
    x: float = Field(ge=-10000, le=10000, allow_inf_nan=False)
    y: float = Field(ge=-10000, le=10000, allow_inf_nan=False)
    z: float = Field(ge=-10000, le=10000, allow_inf_nan=False)


class SceneSize3(ContractModel):
    x: float = Field(gt=0, le=10000, allow_inf_nan=False)
    y: float = Field(gt=0, le=10000, allow_inf_nan=False)
    z: float = Field(gt=0, le=10000, allow_inf_nan=False)


class SceneRotation3(ContractModel):
    x: float = Field(ge=-360, le=360, allow_inf_nan=False)
    y: float = Field(ge=-360, le=360, allow_inf_nan=False)
    z: float = Field(ge=-360, le=360, allow_inf_nan=False)


class SceneObject(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    kind: SceneObjectKind
    region_id: str = Field(min_length=1, max_length=128)
    position: SceneVector3
    size: SceneSize3
    rotation: SceneRotation3

    @field_validator("id", "region_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_trimmed_text(value, "scene identifier")


class SceneHotspot(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    object_id: str = Field(min_length=1, max_length=128)
    region_id: str = Field(min_length=1, max_length=128)
    source_anchor_id: str = Field(min_length=1, max_length=128)

    @field_validator("id", "object_id", "region_id", "source_anchor_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_trimmed_text(value, "hotspot identifier")


class SceneSpec(ContractModel):
    camera_preset: SceneCameraPreset
    objects: list[SceneObject] = Field(min_length=1, max_length=200)
    hotspots: list[SceneHotspot] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_object_references(self) -> "SceneSpec":
        object_ids = [item.id for item in self.objects]
        hotspot_ids = [item.id for item in self.hotspots]
        if len(set(object_ids)) != len(object_ids):
            raise ValueError("SceneSpec object ids must be unique")
        if len(set(hotspot_ids)) != len(hotspot_ids):
            raise ValueError("SceneSpec hotspot ids must be unique")
        if any(item.object_id not in object_ids for item in self.hotspots):
            raise ValueError("SceneSpec hotspot objectId must reference an object")
        return self


class MaterialIntelligenceModelInfo(ContractModel):
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


class MaterialIntelligenceResult(ContractModel):
    project_id: str = Field(min_length=1, max_length=128)
    material_id: str = Field(min_length=1, max_length=128)
    material_version_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_kind: MaterialMediaKind
    context_version: str = Field(min_length=1, max_length=128)
    data_classification: DataClassification
    status: MaterialIntelligenceStatus
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    observations: list[Observation] = Field(default_factory=list, max_length=100)
    extracted_field_candidates: list[ExtractedFieldCandidate] = Field(
        default_factory=list, max_length=100
    )
    unresolved_items: list[UnresolvedItem] = Field(default_factory=list, max_length=100)
    source_anchors: list[SourceAnchor] = Field(default_factory=list, max_length=500)
    scene_spec: SceneSpec | None = None
    model_info: MaterialIntelligenceModelInfo | None
    prompt_version: str = Field(min_length=1, max_length=128)
    schema_version: Literal["1.0"] = MATERIAL_INTELLIGENCE_SCHEMA_VERSION
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    advisory_only: Literal[True] = True
    is_simulated: bool = True
    data_status: MaterialIntelligenceDataStatus = MaterialIntelligenceDataStatus.SIMULATED
    source: str = Field(default="material_intelligence_legacy_synthetic", min_length=1, max_length=256)
    disclaimer: str = Field(default=MATERIAL_INTELLIGENCE_DISCLAIMER, min_length=1, max_length=2000)

    @field_validator(
        "project_id",
        "material_id",
        "material_version_id",
        "context_version",
        "prompt_version",
    )
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        return _require_trimmed_text(value, "result identifier")

    @model_validator(mode="after")
    def validate_result_structure(self) -> "MaterialIntelligenceResult":
        if self.status == MaterialIntelligenceStatus.UNAVAILABLE:
            expected_truth = (False, MaterialIntelligenceDataStatus.UNAVAILABLE)
        elif self.is_simulated:
            expected_truth = (True, MaterialIntelligenceDataStatus.SIMULATED)
        else:
            expected_truth = (
                False,
                MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED,
            )
        if (self.is_simulated, self.data_status) != expected_truth:
            raise ValueError("isSimulated must match dataStatus and result status")
        anchor_ids = [anchor.id for anchor in self.source_anchors]
        if len(set(anchor_ids)) != len(anchor_ids):
            raise ValueError("sourceAnchors ids must be unique")
        expected_binding = (self.material_id, self.material_version_id, self.content_hash)
        expected_kind = self.media_kind.value
        for anchor in self.source_anchors:
            if _anchor_binding(anchor) != expected_binding:
                raise ValueError("every SourceAnchor must bind this material/version/hash")
            if anchor.kind != expected_kind:
                raise ValueError("SourceAnchor kind must match mediaKind")

        self._validate_anchor_references(set(anchor_ids))

        if self.status == MaterialIntelligenceStatus.UNAVAILABLE:
            if (
                self.observations
                or self.extracted_field_candidates
                or self.unresolved_items
                or self.source_anchors
                or self.scene_spec is not None
                or self.model_info is not None
                or self.confidence != 0
            ):
                raise ValueError("unavailable result cannot contain model output")
            return self

        if self.model_info is None:
            raise ValueError("completed or needs_review result requires modelInfo")
        if self.status == MaterialIntelligenceStatus.COMPLETED and not (
            self.observations
            or self.extracted_field_candidates
            or self.scene_spec is not None
        ):
            raise ValueError("completed result requires candidate output")
        if (
            self.status == MaterialIntelligenceStatus.NEEDS_REVIEW
            and not self.unresolved_items
        ):
            raise ValueError("needs_review result requires unresolvedItems")
        return self

    def _validate_anchor_references(self, anchor_ids: set[str]) -> None:
        for observation in self.observations:
            if not set(observation.source_anchor_ids).issubset(anchor_ids):
                raise ValueError("observation sourceAnchorIds must exist in sourceAnchors")
        for candidate in self.extracted_field_candidates:
            if not set(candidate.source_anchor_ids).issubset(anchor_ids):
                raise ValueError("candidate sourceAnchorIds must exist in sourceAnchors")
        for unresolved in self.unresolved_items:
            if not set(unresolved.source_anchor_ids).issubset(anchor_ids):
                raise ValueError("unresolved sourceAnchorIds must exist in sourceAnchors")
        if self.scene_spec is not None:
            for hotspot in self.scene_spec.hotspots:
                if hotspot.source_anchor_id not in anchor_ids:
                    raise ValueError("SceneSpec hotspot must reference a SourceAnchor")


def validate_material_intelligence_result(
    request: MaterialIntelligenceRequest,
    result: MaterialIntelligenceResult,
    *,
    expected_input_hash: str,
) -> MaterialIntelligenceResult:
    """Validate request/result binding after a future model invocation."""

    if not _is_sha256(expected_input_hash):
        raise ValueError("expectedInputHash must be a lowercase SHA-256 hash")
    request_binding = (
        request.project_id,
        request.material_id,
        request.material_version_id,
        request.content_hash,
        request.media_kind,
        request.context_version,
        request.data_classification,
    )
    result_binding = (
        result.project_id,
        result.material_id,
        result.material_version_id,
        result.content_hash,
        result.media_kind,
        result.context_version,
        result.data_classification,
    )
    if result_binding != request_binding:
        raise ValueError("result must bind the same request material context")
    if result.input_hash != expected_input_hash:
        raise ValueError("result inputHash does not match the harness input hash")
    if (
        result.scene_spec is not None
        and MaterialIntelligenceTaskGoal.SCENE_SPEC not in request.task_goals
    ):
        raise ValueError("SceneSpec was not requested by taskGoals")
    return result


def _require_trimmed_text(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} must not be blank")
    if value != value.strip():
        raise ValueError(f"{label} must not have surrounding whitespace")
    return value


def _validate_unique_identifiers(values: list[str], label: str) -> list[str]:
    for value in values:
        _require_trimmed_text(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicates")
    return values


def _validate_ocr_span(
    token_ids: list[str],
    char_start: int | None,
    char_end: int | None,
) -> None:
    _validate_unique_identifiers(token_ids, "ocrTokenIds")
    if (char_start is None) != (char_end is None):
        raise ValueError("OCR charStart and charEnd must be provided together")
    if char_start is not None:
        if not token_ids:
            raise ValueError("OCR char span requires ocrTokenIds")
        if char_end is None or char_end <= char_start:
            raise ValueError("OCR charEnd must be greater than charStart")


def _anchor_binding(anchor: SourceAnchor) -> tuple[str, str, str]:
    return (anchor.material_id, anchor.material_version_id, anchor.content_hash)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
