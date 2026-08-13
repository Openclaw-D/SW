from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypeAlias
from uuid import uuid4


JSONValue: TypeAlias = (
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
)
DimensionId: TypeAlias = Literal[
    "compliance", "transaction", "production", "revenue", "debt", "cashflow"
]
EvidenceLocationStatus: TypeAlias = Literal[
    "located", "pending", "unverifiable", "version_mismatch"
]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def jsonable(value: Any) -> JSONValue:
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class NormalizedBBox:
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class ExcelLocator:
    material_id: str
    material_version_id: str
    sheet: str
    range: str
    kind: Literal["excel"] = "excel"

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": self.kind,
            "materialId": self.material_id,
            "materialVersionId": self.material_version_id,
            "sheet": self.sheet,
            "range": self.range,
        }


@dataclass(frozen=True, slots=True)
class PdfLocator:
    material_id: str
    material_version_id: str
    page: int
    bbox: NormalizedBBox
    text_anchor: str | None = None
    kind: Literal["pdf"] = "pdf"

    def to_dict(self) -> dict[str, JSONValue]:
        result: dict[str, JSONValue] = {
            "kind": self.kind,
            "materialId": self.material_id,
            "materialVersionId": self.material_version_id,
            "page": self.page,
            "bbox": self.bbox.to_dict(),
        }
        if self.text_anchor is not None:
            result["textAnchor"] = self.text_anchor
        return result


@dataclass(frozen=True, slots=True)
class ImageLocator:
    material_id: str
    material_version_id: str
    bbox: NormalizedBBox
    kind: Literal["image"] = "image"

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": self.kind,
            "materialId": self.material_id,
            "materialVersionId": self.material_version_id,
            "bbox": self.bbox.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DocumentLocator:
    material_id: str
    material_version_id: str
    paragraph_id: str
    run_id: str
    rendered_page: int
    rendered_page_bbox: NormalizedBBox
    kind: Literal["document"] = "document"

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": self.kind,
            "materialId": self.material_id,
            "materialVersionId": self.material_version_id,
            "paragraphId": self.paragraph_id,
            "runId": self.run_id,
            "renderedPage": self.rendered_page,
            "renderedPageBbox": self.rendered_page_bbox.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MediaLocator:
    material_id: str
    material_version_id: str
    start_seconds: float
    end_seconds: float
    kind: Literal["media"] = "media"

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": self.kind,
            "materialId": self.material_id,
            "materialVersionId": self.material_version_id,
            "startSeconds": self.start_seconds,
            "endSeconds": self.end_seconds,
        }


@dataclass(frozen=True, slots=True)
class SceneLocator:
    material_id: str
    material_version_id: str
    point_ids: tuple[str, ...]
    kind: Literal["scene"] = "scene"

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": self.kind,
            "materialId": self.material_id,
            "materialVersionId": self.material_version_id,
            "pointIds": list(self.point_ids),
        }


EvidenceLocator: TypeAlias = (
    ExcelLocator
    | PdfLocator
    | ImageLocator
    | DocumentLocator
    | MediaLocator
    | SceneLocator
)


def _bbox_from_mapping(value: Any) -> NormalizedBBox:
    if not isinstance(value, dict):
        raise ValueError("bbox must be an object")
    try:
        return NormalizedBBox(
            x=float(value["x"]),
            y=float(value["y"]),
            width=float(value["width"]),
            height=float(value["height"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("bbox requires numeric x, y, width and height") from exc


def locator_from_mapping(value: Any) -> EvidenceLocator:
    if not isinstance(value, dict):
        raise ValueError("locator must be an object")
    kind = value.get("kind")
    material_id = value.get("materialId", value.get("material_id"))
    material_version_id = value.get(
        "materialVersionId", value.get("material_version_id")
    )
    if not isinstance(material_id, str) or not material_id:
        raise ValueError("locator.materialId is required")
    if not isinstance(material_version_id, str) or not material_version_id:
        raise ValueError("locator.materialVersionId is required")
    if kind in {"excel", "spreadsheet"}:
        sheet = value.get("sheet")
        cell_range = value.get("range")
        if not isinstance(sheet, str) or not isinstance(cell_range, str):
            raise ValueError("excel locator requires sheet and range")
        return ExcelLocator(material_id, material_version_id, sheet, cell_range)
    if kind == "pdf":
        page = value.get("page")
        if isinstance(page, bool) or not isinstance(page, int):
            raise ValueError("pdf locator page must be an integer")
        text_anchor = value.get("textAnchor", value.get("text_anchor"))
        if text_anchor is not None and not isinstance(text_anchor, str):
            raise ValueError("pdf locator textAnchor must be a string")
        return PdfLocator(
            material_id,
            material_version_id,
            page,
            _bbox_from_mapping(value.get("bbox")),
            text_anchor,
        )
    if kind == "image":
        return ImageLocator(
            material_id,
            material_version_id,
            _bbox_from_mapping(value.get("bbox")),
        )
    if kind == "document":
        paragraph_id = value.get("paragraphId", value.get("paragraph_id"))
        run_id = value.get("runId", value.get("run_id"))
        rendered_page = value.get("renderedPage", value.get("rendered_page"))
        if (
            not isinstance(paragraph_id, str)
            or not paragraph_id
            or not isinstance(run_id, str)
            or not run_id
            or isinstance(rendered_page, bool)
            or not isinstance(rendered_page, int)
        ):
            raise ValueError(
                "document locator requires paragraphId, runId and integer renderedPage"
            )
        return DocumentLocator(
            material_id,
            material_version_id,
            paragraph_id,
            run_id,
            rendered_page,
            _bbox_from_mapping(
                value.get(
                    "renderedPageBbox",
                    value.get("renderedPageBBox", value.get("rendered_page_bbox")),
                )
            ),
        )
    if kind in {"media", "video"}:
        try:
            start = float(value.get("startSeconds", value.get("start_seconds")))
            end = float(value.get("endSeconds", value.get("end_seconds")))
        except (TypeError, ValueError) as exc:
            raise ValueError("media locator requires numeric startSeconds and endSeconds") from exc
        return MediaLocator(material_id, material_version_id, start, end)
    if kind == "scene":
        point_ids = value.get("pointIds", value.get("point_ids"))
        if not isinstance(point_ids, (list, tuple)) or not all(
            isinstance(item, str) for item in point_ids
        ):
            raise ValueError("scene locator pointIds must be a string array")
        return SceneLocator(material_id, material_version_id, tuple(point_ids))
    raise ValueError(f"unsupported locator kind: {kind!r}")


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    payload: dict[str, JSONValue]
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    id: str
    project_id: str
    version: int
    payload: dict[str, JSONValue]
    created_at: str
    created_by: str


@dataclass(frozen=True, slots=True)
class Material:
    id: str
    project_id: str
    kind: str
    file_name: str
    availability: str
    current_version_id: str | None
    metadata: dict[str, JSONValue]
    created_at: str


@dataclass(frozen=True, slots=True)
class MaterialVersion:
    id: str
    project_id: str
    material_id: str
    version: int
    mime_type: str
    content_hash: str
    payload: dict[str, JSONValue]
    created_at: str
    created_by: str


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    id: str
    project_id: str
    label: str
    locator: EvidenceLocator | None
    location_status: EvidenceLocationStatus
    material_status: str
    created_at: str

    def to_front_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "label": self.label,
            "locator": self.locator.to_dict() if self.locator else None,
            "locationStatus": self.location_status,
            "materialStatus": self.material_status,
        }


@dataclass(frozen=True, slots=True)
class FactVersion:
    id: str
    project_id: str
    fact_key: str
    dimension_id: str
    version: int
    label: str
    value: JSONValue
    unit: str | None
    source: str
    evidence_refs: tuple[str, ...]
    supersedes_version_id: str | None
    created_at: str
    created_by: str
    is_simulated: bool

    def to_front_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "factKey": self.fact_key,
            "dimensionId": self.dimension_id,
            "version": self.version,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "evidenceRefs": list(self.evidence_refs),
            "createdAt": self.created_at,
            "isSimulated": self.is_simulated,
        }


@dataclass(frozen=True, slots=True)
class BusinessCorrection:
    id: str
    project_id: str
    fact_key: str
    from_fact_version_id: str
    to_fact_version_id: str
    expected_version: int
    proposed_value: JSONValue
    reason: str
    evidence_refs: tuple[str, ...]
    status: str
    created_by: str
    created_at: str
    is_simulated: bool

    def to_front_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "factKey": self.fact_key,
            "fromFactVersionId": self.from_fact_version_id,
            "proposedValue": self.proposed_value,
            "reason": self.reason,
            "evidenceRefs": list(self.evidence_refs),
            "status": self.status,
            "createdBy": "business",
            "createdAt": self.created_at,
            "isSimulated": self.is_simulated,
        }


@dataclass(frozen=True, slots=True)
class ReviewEvidenceTarget:
    evidence_ref: str
    evidence_refs: tuple[str, ...]
    dimension_id: str
    review_target_id: str | None
    fact_version_id: str | None
    unavailable_reason: str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        result: dict[str, JSONValue] = {
            "evidenceRef": self.evidence_ref,
            "evidenceRefs": list(self.evidence_refs),
            "dimensionId": self.dimension_id,
            "reviewTargetId": self.review_target_id,
            "factVersionId": self.fact_version_id,
        }
        if self.unavailable_reason:
            result["unavailableReason"] = self.unavailable_reason
        return result


@dataclass(frozen=True, slots=True)
class ReviewEvent:
    id: str
    project_id: str
    sequence: int
    thread_id: str
    reply_to_event_id: str | None
    issue_status: str
    event_type: str
    actor: str
    actor_label: str
    dimension_id: str
    evidence_targets: tuple[ReviewEvidenceTarget, ...]
    review_target_id: str | None
    title: str
    summary: str
    fact_version_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    rule_refs: tuple[str, ...]
    created_at: str
    immutable: bool
    is_simulated: bool

    def to_front_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "sequence": self.sequence,
            "threadId": self.thread_id,
            "replyToEventId": self.reply_to_event_id,
            "issueStatus": self.issue_status,
            "eventType": self.event_type,
            "actor": self.actor,
            "actorLabel": self.actor_label,
            "dimensionId": self.dimension_id,
            "evidenceTargets": [target.to_dict() for target in self.evidence_targets],
            "reviewTargetId": self.review_target_id,
            "title": self.title,
            "summary": self.summary,
            "factVersionIds": list(self.fact_version_ids),
            "evidenceRefs": list(self.evidence_refs),
            "ruleRefs": list(self.rule_refs),
            "createdAt": self.created_at,
            "immutable": self.immutable,
            "isSimulated": self.is_simulated,
        }


@dataclass(frozen=True, slots=True)
class RuleVersion:
    id: str
    rule_id: str
    version: str
    title: str
    is_hard_gate: bool
    definition: dict[str, JSONValue]
    definition_hash: str
    created_at: str
    created_by: str


@dataclass(frozen=True, slots=True)
class PolicyResult:
    id: str
    project_id: str
    rule_version_id: str
    rule_id: str
    rule_version: str
    title: str
    result: str
    evidence_targets: tuple[ReviewEvidenceTarget, ...]
    primary_target: ReviewEvidenceTarget | None
    scope: str
    evidence_requirement: str
    gate_triggered: bool
    responsible_party: str
    next_action: str
    explanation: str
    evaluation_input: dict[str, JSONValue]
    evaluated_at: str
    is_simulated: bool

    def to_front_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "ruleId": self.rule_id,
            "ruleVersion": self.rule_version,
            "title": self.title,
            "result": self.result,
            "evidenceTargets": [target.to_dict() for target in self.evidence_targets],
            "primaryTarget": self.primary_target.to_dict() if self.primary_target else None,
            "scope": self.scope,
            "evidenceRequirement": self.evidence_requirement,
            "gateTriggered": self.gate_triggered,
            "responsibleParty": self.responsible_party,
            "nextAction": self.next_action,
            "explanation": self.explanation,
            "evaluatedAt": self.evaluated_at,
            "isSimulated": self.is_simulated,
        }


@dataclass(frozen=True, slots=True)
class ApprovalState:
    project_id: str
    state: str
    version: int
    decision_grade: str | None
    updated_at: str
    updated_by: str


@dataclass(frozen=True, slots=True)
class ApprovalTransition:
    id: str
    project_id: str
    sequence: int
    from_state: str
    to_state: str
    actor_role: str
    reason: str
    policy_result_ids: tuple[str, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    key: str
    operation: str
    request_hash: str
    response: dict[str, JSONValue]
    status_code: int
    created_at: str


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: str
    project_id: str
    sequence: int
    action: str
    aggregate_type: str
    aggregate_id: str
    actor: str
    payload: dict[str, JSONValue]
    previous_hash: str | None
    event_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class EvidenceResolution:
    status: str
    evidence: EvidenceReference
    material: Material | None
    material_version: MaterialVersion | None
    message: str


@dataclass(frozen=True, slots=True)
class SelectionResolution:
    group_id: str
    project_id: str
    targets: tuple[ReviewEvidenceTarget, ...]
    evidence: tuple[EvidenceResolution, ...]
