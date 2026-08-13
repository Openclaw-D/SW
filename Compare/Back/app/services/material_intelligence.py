from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from pydantic import ValidationError

from app.contracts.errors import BusinessValidationError, ServiceError
from app.contracts.material_intelligence import (
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
    MaterialIntelligenceTaskGoal,
    validate_material_intelligence_result,
)


class MaterialIntelligenceProviderPort(Protocol):
    async def analyze(
        self,
        request: MaterialIntelligenceRequest,
        context: Mapping[str, Any],
        input_hash: str,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class MaterialIntelligenceHarnessConfig:
    enabled: bool
    timeout_seconds: float

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


def calculate_material_intelligence_input_hash(
    request: MaterialIntelligenceRequest,
    context: Mapping[str, Any],
) -> str:
    payload = {
        "schemaVersion": "1.0",
        "request": request.model_dump(by_alias=True, mode="json"),
        "context": context,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


async def execute_material_intelligence(
    request: MaterialIntelligenceRequest,
    context: Mapping[str, Any],
    provider: MaterialIntelligenceProviderPort,
    config: MaterialIntelligenceHarnessConfig,
) -> MaterialIntelligenceResult:
    if not config.enabled:
        raise BusinessValidationError(
            "material_intelligence_disabled",
            "材料智能编排当前未启用，请继续人工核验。",
        )
    input_hash = calculate_material_intelligence_input_hash(request, context)
    try:
        raw = await asyncio.wait_for(
            provider.analyze(request, context, input_hash),
            timeout=config.timeout_seconds,
        )
    except TimeoutError as exc:
        raise ServiceError(
            code="material_intelligence_timeout",
            message="材料智能 provider 在规定时间内未返回。",
            category="internal",
            status_code=504,
        ) from exc
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise ServiceError(
            code="material_intelligence_unavailable",
            message="材料智能 provider 当前不可用。",
            category="internal",
            status_code=503,
        ) from exc
    try:
        result = MaterialIntelligenceResult.model_validate(raw)
        return validate_material_intelligence_result(
            request, result, expected_input_hash=input_hash
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ServiceError(
            code="material_intelligence_invalid_output",
            message="材料智能 provider 输出未通过冻结契约校验。",
            category="internal",
            status_code=502,
        ) from exc


class DeterministicSyntheticMaterialProvider:
    """Credential-free localhost provider; never presents output as a real model."""

    async def analyze(
        self,
        request: MaterialIntelligenceRequest,
        context: Mapping[str, Any],
        input_hash: str,
    ) -> object:
        token = input_hash[:16]
        anchor_id = f"anchor-{token}"
        anchor = self._anchor(request, context, anchor_id)
        field_key = str(context["fieldKey"])
        dimension_id = str(context["dimensionId"])
        candidate = {
            "id": f"candidate-{token}",
            "fieldKey": field_key,
            "label": str(context["label"]),
            "value": context.get("value"),
            "unit": context.get("unit"),
            "status": "candidate",
            "sourceAnchorIds": [anchor_id],
        }
        scene_spec = None
        if MaterialIntelligenceTaskGoal.SCENE_SPEC in request.task_goals:
            if request.media_kind.value not in {"image", "media"}:
                raise ValueError("SceneSpec requires image or media input")
            scene_spec = {
                "cameraPreset": "perspective",
                "objects": [
                    {"id": f"factory-{token}", "kind": "box", "regionId": "factory", "position": {"x": 0, "y": 0, "z": 0}, "size": {"x": 12, "y": 4, "z": 8}, "rotation": {"x": 0, "y": 0, "z": 0}},
                    {"id": f"equipment-{token}", "kind": "box", "regionId": "equipment", "position": {"x": 2, "y": 1, "z": 1}, "size": {"x": 3, "y": 2, "z": 2}, "rotation": {"x": 0, "y": 15, "z": 0}},
                    {"id": f"process-{token}", "kind": "marker", "regionId": "process", "position": {"x": -2, "y": 1, "z": -1}, "size": {"x": 1, "y": 1, "z": 1}, "rotation": {"x": 0, "y": 0, "z": 0}},
                ],
                "hotspots": [
                    {"id": f"hotspot-factory-{token}", "objectId": f"factory-{token}", "regionId": "factory", "sourceAnchorId": anchor_id},
                    {"id": f"hotspot-equipment-{token}", "objectId": f"equipment-{token}", "regionId": "equipment", "sourceAnchorId": anchor_id},
                    {"id": f"hotspot-process-{token}", "objectId": f"process-{token}", "regionId": "process", "sourceAnchorId": anchor_id},
                ],
            }
        return {
            "projectId": request.project_id,
            "materialId": request.material_id,
            "materialVersionId": request.material_version_id,
            "contentHash": request.content_hash,
            "mediaKind": request.media_kind.value,
            "contextVersion": request.context_version,
            "dataClassification": request.data_classification.value,
            "status": "completed",
            "confidence": 1.0,
            "observations": [{"id": f"observation-{token}", "kind": "structure", "text": f"确定性 synthetic 结构观察：{dimension_id}", "sourceAnchorIds": [anchor_id]}],
            "extractedFieldCandidates": [candidate],
            "unresolvedItems": [],
            "sourceAnchors": [anchor],
            "sceneSpec": scene_spec,
            "modelInfo": {"provider": "compare-synthetic", "model": "deterministic-material-intelligence", "modelVersion": "1.0"},
            "promptVersion": "synthetic-material-v1",
            "schemaVersion": "1.0",
            "inputHash": input_hash,
            "isSimulated": True,
        }

    @staticmethod
    def _anchor(
        request: MaterialIntelligenceRequest,
        context: Mapping[str, Any],
        anchor_id: str,
    ) -> dict[str, Any]:
        base = {
            "id": anchor_id,
            "materialId": request.material_id,
            "materialVersionId": request.material_version_id,
            "contentHash": request.content_hash,
        }
        kind = request.media_kind.value
        if kind == "excel":
            return {**base, "kind": "excel", "sheet": str(context.get("sheet", "数据")), "range": str(context.get("range", "A4:A4"))}
        if kind == "pdf":
            return {**base, "kind": "pdf", "page": 1, "bbox": {"x": 0.05, "y": 0.08, "width": 0.90, "height": 0.84}, "ocrTokenIds": []}
        if kind == "image":
            return {**base, "kind": "image", "page": 1, "bbox": {"x": 0.05, "y": 0.08, "width": 0.90, "height": 0.84}, "ocrTokenIds": []}
        if kind == "media":
            return {**base, "kind": "media", "startSeconds": 0, "endSeconds": 0, "startFrame": 0, "endFrame": 0, "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}}
        return {**base, "kind": "document", "paragraphId": "p1", "runId": "r1", "renderedPage": 1, "renderedPageBbox": {"x": 0, "y": 0, "width": 1, "height": 1}}


__all__ = [
    "DeterministicSyntheticMaterialProvider",
    "MaterialIntelligenceHarnessConfig",
    "MaterialIntelligenceProviderPort",
    "calculate_material_intelligence_input_hash",
    "execute_material_intelligence",
]
