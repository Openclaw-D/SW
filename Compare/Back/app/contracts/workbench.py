from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import Field, field_validator, model_validator

from app.contracts.base import ContractModel


DimensionId = Literal[
    "compliance", "transaction", "production", "revenue", "debt", "cashflow"
]
DIMENSION_IDS: tuple[DimensionId, ...] = (
    "compliance",
    "transaction",
    "production",
    "revenue",
    "debt",
    "cashflow",
)
ScoreGrade = Literal["A", "B", "C", "D", "E"]
DecisionGrade = ScoreGrade
DataStatus = Literal["simulated", "loading", "empty", "error"]
LocalMaterialStatus = Literal["confirmed", "review", "conflict"]
MaterialAvailability = Literal["available", "processing", "missing", "error"]
MaterialOriginalAccessStatus = Literal[
    "available", "not_configured", "invalid_root", "not_imported", "integrity_mismatch"
]
BUSINESS_MATERIAL_ROOTS: tuple[str, ...] = (
    "基本证照",
    "经营证明",
    "现场照片",
    "增信",
    "租赁标的",
)
EvidenceLocationStatus = Literal[
    "located", "pending", "unverifiable", "version_mismatch"
]
RiskLevel = Literal["support", "attention", "confirm", "risk", "forbid"]
AssessmentTone = Literal["positive", "neutral", "attention", "critical"]
FactValue = str | int | float | bool | None


class DimensionDefinition(ContractModel):
    id: DimensionId
    index: Literal[1, 2, 3, 4, 5, 6]
    name: Literal["合规", "交易", "生产", "营收", "负债", "流水"]
    full_name: str
    score: float = Field(ge=0, le=100)
    score_grade: ScoreGrade
    confidence: float = Field(ge=0, le=100)
    summary: str


class DimensionMetric(ContractModel):
    id: str
    label: str
    value: str
    note: str
    tone: AssessmentTone
    evidence_refs: list[str]


class DimensionSeriesMeasure(ContractModel):
    id: str
    label: str
    value: float
    unit: str
    evidence_refs: list[str]
    comparison_evidence_refs: list[str] | None = None


class DimensionSeriesPoint(ContractModel):
    id: str
    label: str
    measures: list[DimensionSeriesMeasure]
    note: str | None = None


class DimensionSeriesGroup(ContractModel):
    id: str
    label: str
    points: list[DimensionSeriesPoint]


TimeGrain = Literal["day", "week", "month", "year"]
TimeAggregation = Literal["sum", "average", "last"]


class DimensionSeriesRequest(ContractModel):
    project_id: str
    dimension_id: DimensionId
    metric_ids: list[str] = Field(min_length=1)
    grain: TimeGrain
    start_date: str
    end_date: str
    timezone: str


class DimensionTimeMetric(ContractModel):
    id: str
    label: str
    unit: str
    aggregation: TimeAggregation


class DimensionTimeObservation(ContractModel):
    id: str
    date: str
    metric_id: str
    value: float
    evidence_refs: list[str]
    is_simulated: bool


class DimensionTimeSeries(ContractModel):
    dimension_id: DimensionId
    supported_grains: list[TimeGrain]
    metrics: list[DimensionTimeMetric]
    observations: list[DimensionTimeObservation]
    source_label: str
    is_simulated: bool


class PeriodDimensionSeriesPoint(DimensionSeriesPoint):
    period_start: str
    period_end: str


class AvailableDimensionSeriesResponse(ContractModel):
    status: Literal["available"]
    request: DimensionSeriesRequest
    points: list[PeriodDimensionSeriesPoint]
    source_label: str
    is_simulated: bool


class UnavailableDimensionSeriesResponse(ContractModel):
    status: Literal["empty", "invalid", "unavailable"]
    request: DimensionSeriesRequest
    points: list[PeriodDimensionSeriesPoint] = Field(max_length=0)
    message: str
    source_label: str
    is_simulated: bool


DimensionSeriesResponse = Union[
    AvailableDimensionSeriesResponse, UnavailableDimensionSeriesResponse
]


class DimensionBreakdownItem(ContractModel):
    id: str
    label: str
    value: str
    detail: str
    tone: AssessmentTone
    evidence_refs: list[str]


class DimensionCompositionSegment(ContractModel):
    id: str
    label: str
    value: float
    unit: str
    note: str | None = None
    evidence_refs: list[str]
    tone: AssessmentTone


class DimensionComposition(ContractModel):
    id: str
    label: str
    segments: list[DimensionCompositionSegment]


DimensionViewMode = Literal["visual", "table"]
DimensionVisualKind = Literal[
    "subject-network",
    "transaction-structure",
    "production-series",
    "revenue-series",
    "debt-structure",
    "cashflow-series",
]


class DimensionDetail(ContractModel):
    dimension_id: DimensionId
    visual: DimensionVisualKind
    default_view: DimensionViewMode
    available_views: list[DimensionViewMode]
    unit: str
    metrics: list[DimensionMetric]
    series: list[DimensionSeriesPoint]
    series_groups: list[DimensionSeriesGroup] | None = None
    compositions: list[DimensionComposition] | None = None
    breakdown: list[DimensionBreakdownItem]
    conclusion: str
    source_label: str
    is_simulated: bool


class NormalizedBBox(ContractModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "NormalizedBBox":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("normalized bbox must remain inside [0, 1]")
        return self


class BaseMaterial(ContractModel):
    id: str
    version_id: str
    file_name: str
    label: str
    availability: MaterialAvailability
    is_simulated: bool
    source_label: str
    # Runtime-only availability of the archived original. This does not alter
    # the immutable material/version record or the material's business status.
    original_access: "MaterialOriginalAccess | None" = None
    # Optional for backward compatibility with P0-P4 snapshots. Every newly
    # generated/imported P5 original supplies both fields and preserves the
    # business-facing Windows folder hierarchy instead of grouping by MIME.
    folder_path: str | None = None
    business_path: str | None = None

    @field_validator("folder_path", "business_path")
    @classmethod
    def validate_business_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if (
            normalized.startswith("/")
            or ":" in normalized
            or any(not part or part in {".", ".."} for part in parts)
            or parts[0] not in BUSINESS_MATERIAL_ROOTS
        ):
            raise ValueError("material business path must remain under an approved business root")
        return normalized

    @model_validator(mode="after")
    def validate_business_path_pair(self) -> "BaseMaterial":
        if self.folder_path is None and self.business_path is None:
            return self
        if self.folder_path is None or self.business_path is None:
            raise ValueError("folderPath and businessPath must be supplied together")
        parent, separator, file_name = self.business_path.rpartition("/")
        if not separator or parent != self.folder_path or file_name != self.file_name:
            raise ValueError("businessPath must equal folderPath plus fileName")
        return self


class MaterialOriginalAccess(ContractModel):
    status: MaterialOriginalAccessStatus
    available: bool


class ExcelSheet(ContractModel):
    name: str
    columns: list[str]
    rows: list[list[str | int | float | None]]


class ExcelMaterial(BaseMaterial):
    kind: Literal["excel"]
    mime_type: Literal[
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]
    sheets: list[ExcelSheet]


class PdfPage(ContractModel):
    page: int = Field(ge=1)
    title: str
    lines: list[str]


class PdfMaterial(BaseMaterial):
    kind: Literal["pdf"]
    mime_type: Literal["application/pdf"]
    page_count: int = Field(ge=0)
    pages: list[PdfPage]


class DocumentMaterial(BaseMaterial):
    """A preserved Office original; parsing/OCR remains a derived service."""

    kind: Literal["document"]
    mime_type: Literal[
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]
    description: str


class ImageMaterial(BaseMaterial):
    kind: Literal["image"]
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    asset_url: str | None = None
    pixel_width: int = Field(gt=0)
    pixel_height: int = Field(gt=0)
    description: str
    focal_area: NormalizedBBox


class MediaMaterial(BaseMaterial):
    kind: Literal["media"]
    mime_type: Literal["video/mp4", "image/vnd.compare.panorama"]
    media_kind: Literal["video", "panorama"]
    duration_seconds: float | None = Field(default=None, ge=0)
    description: str
    poster_material_id: str


class ScenePoint(ContractModel):
    id: str
    x: float
    y: float
    z: float
    size: float = Field(gt=0)
    color: str


class SceneMaterial(BaseMaterial):
    kind: Literal["scene"]
    mime_type: Literal["application/vnd.compare.gaussian-scene+json", "model/gltf-binary"]
    scene_format: Literal["compare-gaussian-preview-v1", "glb"]
    points: list[ScenePoint]
    fallback_material_id: str
    description: str


Material = Annotated[
    Union[
        ExcelMaterial,
        PdfMaterial,
        DocumentMaterial,
        ImageMaterial,
        MediaMaterial,
        SceneMaterial,
    ],
    Field(discriminator="kind"),
]


class BaseEvidenceLocator(ContractModel):
    material_id: str
    material_version_id: str


class ExcelEvidenceLocator(BaseEvidenceLocator):
    kind: Literal["excel"]
    sheet: str
    range: str = Field(pattern=r"^[A-Za-z]+[1-9][0-9]*(?::[A-Za-z]+[1-9][0-9]*)?$")


class PdfEvidenceLocator(BaseEvidenceLocator):
    kind: Literal["pdf"]
    page: int = Field(ge=1)
    bbox: NormalizedBBox
    text_anchor: str | None = None


class ImageEvidenceLocator(BaseEvidenceLocator):
    kind: Literal["image"]
    bbox: NormalizedBBox


class DocumentEvidenceLocator(BaseEvidenceLocator):
    kind: Literal["document"]
    paragraph_id: str
    run_id: str
    rendered_page: int = Field(ge=1)
    rendered_page_bbox: NormalizedBBox


class MediaEvidenceLocator(BaseEvidenceLocator):
    kind: Literal["media"]
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "MediaEvidenceLocator":
        if self.end_seconds < self.start_seconds:
            raise ValueError("endSeconds must be greater than or equal to startSeconds")
        return self


class SceneEvidenceLocator(BaseEvidenceLocator):
    kind: Literal["scene"]
    point_ids: list[str] = Field(min_length=1)


EvidenceLocator = Annotated[
    Union[
        ExcelEvidenceLocator,
        PdfEvidenceLocator,
        ImageEvidenceLocator,
        DocumentEvidenceLocator,
        MediaEvidenceLocator,
        SceneEvidenceLocator,
    ],
    Field(discriminator="kind"),
]


class EvidenceReference(ContractModel):
    id: str
    label: str
    locator: EvidenceLocator | None
    location_status: EvidenceLocationStatus
    material_status: LocalMaterialStatus

    @model_validator(mode="after")
    def validate_locator_status(self) -> "EvidenceReference":
        if self.location_status == "located" and self.locator is None:
            raise ValueError("located evidence requires a locator")
        if self.locator is None and self.location_status == "version_mismatch":
            raise ValueError("version_mismatch evidence must retain the rejected locator")
        return self


class FactVersion(ContractModel):
    id: str
    fact_key: str
    dimension_id: DimensionId
    version: int = Field(ge=1)
    label: str
    value: FactValue
    unit: str | None
    source: Literal["mock_material_extract", "mock_business_correction"]
    evidence_refs: list[str]
    created_at: datetime
    is_simulated: bool


class ReviewEvidenceTarget(ContractModel):
    evidence_ref: str
    evidence_refs: list[str] | None = None
    dimension_id: DimensionId
    review_target_id: str | None
    fact_version_id: str | None
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def validate_group_projection(self) -> "ReviewEvidenceTarget":
        if self.evidence_refs is not None:
            if self.evidence_ref not in self.evidence_refs:
                raise ValueError("evidenceRefs must include evidenceRef")
            if len(set(self.evidence_refs)) != len(self.evidence_refs):
                raise ValueError("evidenceRefs must be unique")
        return self


class ReviewEvidenceSelectionGroup(ContractModel):
    id: str
    dimension_id: DimensionId
    review_target_id: str | None
    fact_version_id: str | None
    targets: list[ReviewEvidenceTarget] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_atomic_target_identity(self) -> "ReviewEvidenceSelectionGroup":
        group_refs = [target.evidence_ref for target in self.targets]
        for target in self.targets:
            if (
                target.dimension_id != self.dimension_id
                or target.review_target_id != self.review_target_id
                or target.fact_version_id != self.fact_version_id
            ):
                raise ValueError("selection-group targets must share dimension and target identity")
            if target.evidence_refs != group_refs:
                raise ValueError("every target evidenceRefs must equal the complete atomic group")
        if len(set(group_refs)) != len(self.targets):
            raise ValueError("selection-group evidenceRef values must be unique")
        expected_id = "::".join(
            [
                self.dimension_id,
                self.review_target_id or "review",
                self.fact_version_id or "fact",
                *group_refs,
            ]
        )
        if self.id != expected_id:
            raise ValueError("selection-group id must be derived from its authoritative targets")
        return self


class ResolvedEvidenceItem(ContractModel):
    target: ReviewEvidenceTarget
    evidence: EvidenceReference


class EvidenceSelectionResolution(ContractModel):
    status: Literal["located"] = "located"
    selection_group: ReviewEvidenceSelectionGroup
    items: list[ResolvedEvidenceItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_resolution(self) -> "EvidenceSelectionResolution":
        requested = [target.evidence_ref for target in self.selection_group.targets]
        resolved = [item.target.evidence_ref for item in self.items]
        if resolved != requested:
            raise ValueError("atomic resolution must return every target in request order")
        if any(item.evidence.id != item.target.evidence_ref for item in self.items):
            raise ValueError("resolved evidence must match its authoritative target")
        return self


class ComplianceSubjectNode(ContractModel):
    id: str
    kind: Literal["company", "person"]
    name: str
    role: str
    verification_status: LocalMaterialStatus
    evidence_refs: list[str]


class ComplianceSubjectRelation(ContractModel):
    id: str
    from_id: str
    to_id: str
    relation: Literal[
        "shareholding",
        "legal_representative",
        "controller",
        "affiliate",
        "transaction",
    ]
    share_percent: float | None = Field(default=None, ge=0, le=100)
    label: str
    verification_status: LocalMaterialStatus
    evidence_refs: list[str]


class ComplianceSubjectAttachment(ContractModel):
    id: str
    subject_id: str
    fact_version_id: str
    label: str
    verification_status: LocalMaterialStatus
    evidence_refs: list[str]


class ComplianceSubjectGraph(ContractModel):
    nodes: list[ComplianceSubjectNode]
    relations: list[ComplianceSubjectRelation]
    attachments: list[ComplianceSubjectAttachment]
    source_label: str
    is_simulated: bool


EquipmentModelKind = Literal[
    "turning-center", "sliding-head-lathe", "machining-center"
]
AvailabilityState = Literal["available", "missing", "invalid", "unavailable"]


class EquipmentModelPreset(ContractModel):
    kind: EquipmentModelKind
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    depth: float = Field(gt=0)
    spindle_count: int = Field(ge=1)
    axis_count: int = Field(ge=1)
    accent: str


class EquipmentPriceBenchmark(ContractModel):
    status: AvailabilityState
    price_basis: Literal["per_unit"]
    low: float | None = Field(default=None, ge=0)
    median: float | None = Field(default=None, ge=0)
    high: float | None = Field(default=None, ge=0)
    sample_label: str
    message: str
    unit: Literal["元/台"]
    source_label: str
    fact_version_id: str | None
    evidence_refs: list[str]

    @model_validator(mode="after")
    def validate_price_band(self) -> "EquipmentPriceBenchmark":
        values = (self.low, self.median, self.high)
        if self.status == "available":
            if any(value is None for value in values):
                raise ValueError("available price benchmark requires low, median and high")
            low, median, high = values
            if not (low <= median <= high):  # type: ignore[operator]
                raise ValueError("price benchmark must satisfy low <= median <= high")
        return self


class EquipmentConfigurationRow(ContractModel):
    id: str
    fact_version_id: str | None
    label: str
    unit: str
    current: str
    median: str
    range: str
    source_label: str
    tone: Literal["positive", "neutral", "attention", "risk"]
    evidence_refs: list[str]


class EquipmentConfigurationComparison(ContractModel):
    status: AvailabilityState
    message: str
    rows: list[EquipmentConfigurationRow]


TransactionRating = Literal["A级", "B级", "C级", "D级", "E级"]


class TransactionRepaymentPoint(ContractModel):
    id: str
    period: int = Field(ge=1)
    principal: float = Field(ge=0)
    interest: float = Field(ge=0)
    rent: float = Field(ge=0)
    evidence_refs: list[str]
    is_simulated: bool


class TransactionRepaymentSchedule(ContractModel):
    status: AvailabilityState
    term_months: int = Field(ge=0)
    amount_unit: Literal["元"]
    points: list[TransactionRepaymentPoint]
    first_payment_evidence_refs: list[str]
    first_twelve_evidence_refs: list[str]
    total_rent_evidence_refs: list[str]
    term_evidence_refs: list[str]
    message: str
    source_label: str
    is_simulated: bool


class FinancedEquipmentLine(ContractModel):
    id: str
    equipment: str
    brand: str
    model: str
    quantity: int = Field(gt=0)
    contract_unit_price: float = Field(ge=0)
    supplier: str
    contract_quote_source: str
    supplier_quote_source: str
    image_id: str
    image_ids: list[str] = Field(default_factory=list)
    nameplate_material_id: str | None = None
    # Identifier of a backend-derived model/SceneSpec. It is intentionally not
    # a Material id and therefore never increases the original-material count.
    derived_model_ref: str | None = None
    model_preset: EquipmentModelPreset
    price_benchmark: EquipmentPriceBenchmark
    configuration: EquipmentConfigurationComparison
    supplier_rating: TransactionRating | None = None
    supplier_rating_evidence_refs: list[str] | None = None
    brand_rating: TransactionRating | None = None
    brand_rating_evidence_refs: list[str] | None = None
    contract_evidence_refs: list[str]
    supplier_quote_evidence_refs: list[str]


class FinancedEquipmentLedger(ContractModel):
    currency: Literal["CNY"]
    amount_unit: Literal["元"]
    lines: list[FinancedEquipmentLine]
    transaction_structure: Literal["direct-lease", "sale-and-leaseback"]
    lessor: str
    term_months: int = Field(gt=0)
    down_payment_amount: float = Field(ge=0)
    financing_plan_evidence_refs: list[str]
    project_amount_evidence_refs: list[str]
    financing_ratio_evidence_refs: list[str]
    party_relationship_evidence_refs: list[str]
    total_contract_evidence_refs: list[str]
    repayment_schedule: TransactionRepaymentSchedule
    source_label: str
    is_simulated: bool


class OperatingEquipmentStatus(ContractModel):
    id: str
    equipment: str
    model: str
    operating_quantity: int = Field(ge=0)
    status: Literal["operating", "maintenance", "idle"]
    utilization: str
    rated_capacity: str
    process_use: str
    evidence_refs: list[str]
    source_label: str
    is_simulated: bool


ProductionStageId = Literal["raw-material", "process", "finished-product"]


class ProductionStageField(ContractModel):
    label: str
    value: str


class ProductionStage(ContractModel):
    id: str
    stage: ProductionStageId
    title: str
    summary: str
    fields: list[ProductionStageField]
    image_ids: list[str]
    evidence_refs: list[str]
    source_label: str
    is_simulated: bool


class ProductionEnergyPoint(ContractModel):
    id: str
    date: str
    label: str
    electricity: float = Field(ge=0)
    output: float = Field(ge=0)
    electricity_evidence_refs: list[str]
    output_evidence_refs: list[str]
    is_simulated: bool


class ProductionEnergySeries(ContractModel):
    status: AvailabilityState
    electricity_metric: Literal["usage"]
    electricity_unit: Literal["kWh"]
    output_metric: Literal["absolute"]
    output_unit: Literal["件"]
    aggregation: Literal["sum"]
    points: list[ProductionEnergyPoint]
    message: str
    source_label: str
    is_simulated: bool


PublicReferenceCategory = Literal[
    "equipment", "raw-material", "process", "finished-product"
]


class PublicReferenceImage(ContractModel):
    id: str
    category: PublicReferenceCategory
    src: str
    title: str
    description: str
    author: str
    origin_url: str
    license: str
    license_url: str
    usage: str
    is_evidence: Literal[False]


class OnsiteAsset(ContractModel):
    id: str
    label: str
    kind: Literal[
        "image",
        "supplement",
        "video",
        "panorama",
        "equipment_point",
        "scene_3dgs",
    ]
    collection_status: Literal["collected", "processing", "pending", "failed"]
    material_id: str | None
    source_label: str
    evidence_refs: list[str]
    lazy_load: bool
    is_simulated: bool


class BusinessCorrection(ContractModel):
    id: str
    project_id: str
    fact_key: str
    from_fact_version_id: str
    proposed_value: FactValue
    reason: str
    evidence_refs: list[str]
    status: Literal["draft", "submitted", "accepted", "rejected"]
    created_by: Literal["business"]
    created_at: datetime
    is_simulated: bool


class HardConstraintResult(ContractModel):
    id: str
    rule_id: str
    rule_version: str
    title: str
    result: Literal["pass", "block", "manual_review"]
    evidence_targets: list[ReviewEvidenceTarget]
    primary_target: ReviewEvidenceTarget | None
    scope: str
    evidence_requirement: str
    gate_triggered: bool
    responsible_party: Literal["business", "risk", "joint"]
    next_action: str
    explanation: str
    evaluated_at: datetime
    is_simulated: bool


class RiskSummaryItem(ContractModel):
    id: str
    title: str
    detail: str
    level: RiskLevel
    evidence_targets: list[ReviewEvidenceTarget]
    primary_target: ReviewEvidenceTarget | None
    responsible_party: Literal["business", "risk", "joint"]
    next_action: str
    is_simulated: bool


class GlobalRiskSummary(ContractModel):
    id: str
    name: Literal["风险"]
    level: RiskLevel
    score_grade: ScoreGrade
    decision_grade: DecisionGrade
    confidence: float = Field(ge=0, le=100)
    summary: str
    evidence_refs: list[str]
    hard_constraint_results: list[HardConstraintResult]
    key_anomalies: list[RiskSummaryItem]
    pending_human_determinations: list[RiskSummaryItem]
    is_simulated: bool


class SoftRecommendation(ContractModel):
    id: str
    dimension_id: DimensionId
    title: str
    recommendation: str
    confidence: float = Field(ge=0, le=100)
    evidence_refs: list[str]
    advisory_only: Literal[True]
    is_simulated: bool


class RiskDetermination(ContractModel):
    id: str
    dimension_id: DimensionId
    score: float = Field(ge=0, le=100)
    score_grade: ScoreGrade
    decision_grade: DecisionGrade
    confidence: float = Field(ge=0, le=100)
    conclusion: str
    evidence_refs: list[str]
    hard_constraint_results: list[HardConstraintResult]
    soft_recommendations: list[SoftRecommendation]
    is_simulated: bool


ReviewActor = Literal["business", "risk", "system"]
ReviewIssueStatus = Literal["open", "answered", "pending_gate", "resolved"]
ReviewEventType = Literal[
    "fact_version_created",
    "business_correction_submitted",
    "risk_question_submitted",
    "risk_answer_submitted",
    "business_answer_submitted",
    "issue_opened",
    "policy_result_recorded",
]


class CommonReviewEvent(ContractModel):
    id: str
    project_id: str
    sequence: int = Field(ge=1)
    thread_id: str
    reply_to_event_id: str | None
    issue_status: ReviewIssueStatus
    event_type: ReviewEventType
    actor: ReviewActor
    actor_label: str
    dimension_id: DimensionId
    # Backend responses always provide the authoritative mapping. The Front
    # optional form is transport compatibility only and must not weaken storage.
    evidence_targets: list[ReviewEvidenceTarget]
    review_target_id: str | None
    title: str
    summary: str
    fact_version_ids: list[str]
    evidence_refs: list[str]
    rule_refs: list[str]
    created_at: datetime
    immutable: Literal[True]
    is_simulated: bool

    @model_validator(mode="after")
    def validate_authoritative_projections(self) -> "CommonReviewEvent":
        target_refs: list[str] = []
        target_fact_ids: list[str] = []
        target_review_ids: list[str] = []
        for target in self.evidence_targets:
            refs = target.evidence_refs or [target.evidence_ref]
            target_refs.extend(refs)
            if target.fact_version_id is not None:
                target_fact_ids.append(target.fact_version_id)
            if target.review_target_id is not None:
                target_review_ids.append(target.review_target_id)
        if list(dict.fromkeys(target_refs)) != self.evidence_refs:
            raise ValueError("evidenceRefs must be derived from authoritative evidenceTargets")
        if list(dict.fromkeys(target_fact_ids)) != self.fact_version_ids:
            raise ValueError("factVersionIds must be derived from authoritative evidenceTargets")
        unique_review_ids = list(dict.fromkeys(target_review_ids))
        projected_review_id = unique_review_ids[0] if len(unique_review_ids) == 1 else None
        if projected_review_id != self.review_target_id:
            raise ValueError("reviewTargetId must be derived from authoritative evidenceTargets")
        return self


class LayoutState(ContractModel):
    navigation_width: float
    material_width: float
    collaboration_height: float
    navigation_collapsed: bool
    middle_collapsed: bool
    material_collapsed: bool
    collaboration_collapsed: bool
    business_collapsed: bool
    policy_collapsed: bool
    risk_collapsed: bool
    active_dimension_id: DimensionId


class ProjectSummary(ContractModel):
    id: str
    name: str
    material_count: int = Field(ge=0)
    collaboration_issue_count: int = Field(ge=0)
    data_status: DataStatus
    disclaimer: str
    is_simulated: bool


class WorkbenchProject(ContractModel):
    project: ProjectSummary
    risk_summary: GlobalRiskSummary
    dimensions: list[DimensionDefinition]
    dimension_details: list[DimensionDetail]
    materials: list[Material]
    evidence: list[EvidenceReference]
    facts: list[FactVersion]
    compliance_graph: ComplianceSubjectGraph
    financed_equipment: FinancedEquipmentLedger
    operating_equipment: list[OperatingEquipmentStatus]
    production_stages: list[ProductionStage]
    production_energy: ProductionEnergySeries
    reference_images: list[PublicReferenceImage]
    onsite_assets: list[OnsiteAsset]
    corrections: list[BusinessCorrection]
    determinations: list[RiskDetermination]
    review_events: list[CommonReviewEvent]
    layout: LayoutState

    @model_validator(mode="after")
    def validate_snapshot_integrity(self) -> "WorkbenchProject":
        dimension_ids = tuple(item.id for item in self.dimensions)
        if dimension_ids != DIMENSION_IDS:
            raise ValueError("dimensions must contain the frozen six dimensions in order")
        if tuple(item.dimension_id for item in self.dimension_details) != DIMENSION_IDS:
            raise ValueError("dimensionDetails must contain the frozen six dimensions in order")
        if self.layout.active_dimension_id not in dimension_ids:
            raise ValueError("layout activeDimensionId must be one of the six dimensions")

        material_by_id = self._unique_by_id(self.materials, "materials")
        evidence_by_id = self._unique_by_id(self.evidence, "evidence")
        fact_by_id = self._unique_by_id(self.facts, "facts")

        for line in self.financed_equipment.lines:
            # P0-P4 snapshots used imageId for a public presentation reference.
            # The presence of the new imageIds field marks the P5 binding and
            # makes imageId plus every angle server-authoritative originals.
            if line.image_ids:
                image_ids = list(dict.fromkeys([line.image_id, *line.image_ids]))
                for material_id in image_ids:
                    material = material_by_id.get(material_id)
                    if material is None or getattr(material, "kind", None) != "image":
                        raise ValueError("financedEquipment image ids must reference image originals")
            if line.nameplate_material_id is not None:
                material = material_by_id.get(line.nameplate_material_id)
                if material is None or getattr(material, "kind", None) != "image":
                    raise ValueError("nameplateMaterialId must reference an image original")
        for stage in self.production_stages:
            if any(
                material_id not in material_by_id
                or getattr(material_by_id[material_id], "kind", None) != "image"
                for material_id in stage.image_ids
                # Legacy stage imageIds could be public reference ids. New P5
                # original ids are stable project-scoped mat-* identifiers.
                if material_id.startswith("mat-")
            ):
                raise ValueError("productionStage imageIds must reference image originals")
        for asset in self.onsite_assets:
            if asset.material_id is None:
                continue
            material = material_by_id.get(asset.material_id)
            if material is None:
                raise ValueError("onsiteAsset materialId must reference an original material")
            if asset.kind == "image" and getattr(material, "kind", None) != "image":
                raise ValueError("image onsiteAsset must reference an image original")

        for evidence in self.evidence:
            if evidence.locator is None:
                continue
            locator = evidence.locator
            material = material_by_id.get(locator.material_id)
            if material is None:
                raise ValueError(f"evidence {evidence.id} references an unknown material")
            if locator.kind != material.kind:
                raise ValueError(f"evidence {evidence.id} locator kind does not match material")
            version_matches = locator.material_version_id == material.version_id
            if evidence.location_status == "located" and not version_matches:
                raise ValueError(f"located evidence {evidence.id} has a material version mismatch")
            if evidence.location_status == "version_mismatch" and version_matches:
                raise ValueError(f"version_mismatch evidence {evidence.id} uses the current version")

        for fact in self.facts:
            if any(ref not in evidence_by_id for ref in fact.evidence_refs):
                raise ValueError(f"fact {fact.id} references unknown evidence")
        for correction in self.corrections:
            if correction.project_id != self.project.id:
                raise ValueError("correction projectId does not match snapshot project")
            if correction.from_fact_version_id not in fact_by_id:
                raise ValueError("correction fromFactVersionId is unknown")
        previous_sequence = 0
        for event in self.review_events:
            if event.project_id != self.project.id:
                raise ValueError("review event projectId does not match snapshot project")
            if event.sequence <= previous_sequence:
                raise ValueError("review event sequence must be unique and increasing")
            previous_sequence = event.sequence
        return self

    @staticmethod
    def _unique_by_id(items: list[object], label: str) -> dict[str, object]:
        result: dict[str, object] = {}
        for item in items:
            item_id = getattr(item, "id")
            if item_id in result:
                raise ValueError(f"{label} ids must be unique")
            result[item_id] = item
        return result


class BusinessCorrectionInput(ContractModel):
    project_id: str
    fact_key: str
    from_fact_version_id: str
    proposed_value: FactValue
    reason: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str]


class ReviewSubmissionInput(ContractModel):
    project_id: str
    dimension_id: DimensionId
    evidence_targets: list[ReviewEvidenceTarget]
    review_target_id: str | None
    thread_id: str
    reply_to_event_id: str | None
    fact_version_ids: list[str]
    evidence_refs: list[str]

    @model_validator(mode="after")
    def validate_authoritative_input(self) -> "ReviewSubmissionInput":
        if any(target.dimension_id != self.dimension_id for target in self.evidence_targets):
            raise ValueError("all evidenceTargets must match dimensionId")
        refs: list[str] = []
        facts: list[str] = []
        review_ids: list[str] = []
        for target in self.evidence_targets:
            refs.extend(target.evidence_refs or [target.evidence_ref])
            if target.fact_version_id is not None:
                facts.append(target.fact_version_id)
            if target.review_target_id is not None:
                review_ids.append(target.review_target_id)
        if list(dict.fromkeys(refs)) != self.evidence_refs:
            raise ValueError("evidenceRefs must match evidenceTargets")
        if list(dict.fromkeys(facts)) != self.fact_version_ids:
            raise ValueError("factVersionIds must match evidenceTargets")
        unique_review_ids = list(dict.fromkeys(review_ids))
        projected = unique_review_ids[0] if len(unique_review_ids) == 1 else None
        if projected != self.review_target_id:
            raise ValueError("reviewTargetId must match evidenceTargets")
        return self


class RiskQuestionInput(ReviewSubmissionInput):
    question: str = Field(min_length=1, max_length=4000)


class BusinessAnswerInput(ReviewSubmissionInput):
    answer: str = Field(min_length=1, max_length=4000)


class RiskAnswerInput(ReviewSubmissionInput):
    answer: str = Field(min_length=1, max_length=4000)


class CollaborationSubmissionResult(ContractModel):
    event: CommonReviewEvent
    open_issue_count: int = Field(ge=0)


class BusinessCorrectionResult(ContractModel):
    correction: BusinessCorrection
    fact_version: FactVersion
    event: CommonReviewEvent


class ExpectedVersionInput(ContractModel):
    expected_version: int = Field(ge=1)


class BusinessCorrectionCommand(BusinessCorrectionInput, ExpectedVersionInput):
    pass


class RiskQuestionCommand(RiskQuestionInput, ExpectedVersionInput):
    pass


class BusinessAnswerCommand(BusinessAnswerInput, ExpectedVersionInput):
    pass


class RiskAnswerCommand(RiskAnswerInput, ExpectedVersionInput):
    pass


ApprovalStatus = Literal["draft", "returned", "submitted", "completed"]
ApprovalTransition = Literal["save_draft", "return", "submit", "complete"]
ApprovalActorRole = Literal["business", "risk", "leadership"]


class ApprovalState(ContractModel):
    project_id: str
    version: int = Field(ge=1)
    status: ApprovalStatus
    hard_gate_status: Literal["pass", "block", "manual_review"]
    blocking_rule_ids: list[str]
    risk_veto: bool
    risk_veto_rule_ids: list[str]
    updated_at: datetime
    is_simulated: bool

    @model_validator(mode="after")
    def validate_completion_invariant(self) -> "ApprovalState":
        blocked = (
            self.hard_gate_status != "pass"
            or bool(self.blocking_rule_ids)
            or self.risk_veto
            or bool(self.risk_veto_rule_ids)
        )
        if self.status == "completed" and blocked:
            raise ValueError("completed approval cannot retain a hard gate or risk veto")
        return self


class ApprovalTransitionInput(ExpectedVersionInput):
    transition: ApprovalTransition
    requested_by: ApprovalActorRole
    reason: str = Field(default="", max_length=2000)


class HealthStatus(ContractModel):
    status: Literal["ok"]
    service: str
    version: str
