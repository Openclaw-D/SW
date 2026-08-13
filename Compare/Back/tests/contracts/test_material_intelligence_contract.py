from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.contracts.material_intelligence import (
    DataClassification,
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
    MaterialIntelligenceTaskGoal,
    MaterialMediaKind,
    validate_material_intelligence_result,
)


CONTENT_HASH = "a" * 64
INPUT_HASH = "b" * 64


def _request_payload() -> dict[str, object]:
    return {
        "projectId": "project-sim-001",
        "materialId": "material-sim-image-001",
        "materialVersionId": "material-sim-image-001-v1",
        "contentHash": CONTENT_HASH,
        "mediaKind": "image",
        "contextVersion": "ctx-sim-001-v1",
        "taskGoals": ["observe", "extract_field_candidates", "scene_spec"],
        "locale": "zh-CN",
        "dataClassification": "synthetic_demo",
        "usageAuthorizationRef": None,
    }


def _image_anchor() -> dict[str, object]:
    return {
        "id": "anchor-sim-image-001",
        "kind": "image",
        "materialId": "material-sim-image-001",
        "materialVersionId": "material-sim-image-001-v1",
        "contentHash": CONTENT_HASH,
        "page": 1,
        "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.2},
        "polygon": [
            {"x": 0.1, "y": 0.2},
            {"x": 0.4, "y": 0.2},
            {"x": 0.4, "y": 0.4},
        ],
        "ocrTokenIds": ["ocr-sim-1"],
        "charStart": 0,
        "charEnd": 5,
    }


def _result_payload() -> dict[str, object]:
    return {
        "projectId": "project-sim-001",
        "materialId": "material-sim-image-001",
        "materialVersionId": "material-sim-image-001-v1",
        "contentHash": CONTENT_HASH,
        "mediaKind": "image",
        "contextVersion": "ctx-sim-001-v1",
        "dataClassification": "synthetic_demo",
        "status": "completed",
        "confidence": 0.65,
        "observations": [
            {
                "id": "observation-sim-001",
                "kind": "visual_detail",
                "text": "模拟图像中存在可供人工复核的设备外观区域。",
                "sourceAnchorIds": ["anchor-sim-image-001"],
            }
        ],
        "extractedFieldCandidates": [
            {
                "id": "candidate-sim-001",
                "fieldKey": "equipment_label",
                "label": "设备标识候选",
                "value": "模拟设备标识",
                "unit": None,
                "status": "needs_review",
                "sourceAnchorIds": ["anchor-sim-image-001"],
            }
        ],
        "unresolvedItems": [],
        "sourceAnchors": [_image_anchor()],
        "sceneSpec": {
            "cameraPreset": "perspective",
            "objects": [
                {
                    "id": "scene-object-sim-001",
                    "kind": "marker",
                    "regionId": "region-sim-001",
                    "position": {"x": 0, "y": 1, "z": 0},
                    "size": {"x": 1, "y": 1, "z": 1},
                    "rotation": {"x": 0, "y": 0, "z": 0},
                }
            ],
            "hotspots": [
                {
                    "id": "hotspot-sim-001",
                    "objectId": "scene-object-sim-001",
                    "regionId": "region-sim-001",
                    "sourceAnchorId": "anchor-sim-image-001",
                }
            ],
        },
        "modelInfo": {
            "provider": "contract-example-provider",
            "model": "simulated-no-inference",
            "modelVersion": "c1",
        },
        "promptVersion": "material-intelligence-c1",
        "schemaVersion": "1.0",
        "inputHash": INPUT_HASH,
    }


def test_input_enums_are_frozen() -> None:
    assert {item.value for item in MaterialMediaKind} == {
        "image",
        "pdf",
        "excel",
        "document",
        "media",
    }
    assert {item.value for item in DataClassification} == {
        "authorized_customer",
        "public_reference",
        "synthetic_demo",
    }
    assert {item.value for item in MaterialIntelligenceTaskGoal} == {
        "observe",
        "extract_field_candidates",
        "identify_unresolved",
        "scene_spec",
    }


def test_authorized_customer_requires_non_blank_authorization_reference() -> None:
    payload = _request_payload()
    payload["dataClassification"] = "authorized_customer"
    with pytest.raises(ValidationError, match="requires usageAuthorizationRef"):
        MaterialIntelligenceRequest.model_validate(payload)

    payload["usageAuthorizationRef"] = "auth-record-sim-001"
    assert (
        MaterialIntelligenceRequest.model_validate(payload).usage_authorization_ref
        == "auth-record-sim-001"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("projectId", ""),
        ("materialId", " "),
        ("materialVersionId", ""),
        ("contextVersion", " "),
        ("contentHash", "not-a-sha256"),
        ("taskGoals", []),
        ("taskGoals", ["observe", "observe"]),
    ],
)
def test_request_rejects_empty_or_invalid_boundaries(field: str, value: object) -> None:
    payload = _request_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        MaterialIntelligenceRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        (
            {
                "id": "pdf-anchor",
                "kind": "pdf",
                "materialId": "material-pdf",
                "materialVersionId": "material-pdf-v1",
                "contentHash": CONTENT_HASH,
                "page": 2,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.3},
                "ocrTokenIds": ["token-1"],
                "charStart": 2,
                "charEnd": 9,
            },
            "pdf",
        ),
        (
            {
                "id": "excel-anchor",
                "kind": "excel",
                "materialId": "material-excel",
                "materialVersionId": "material-excel-v1",
                "contentHash": CONTENT_HASH,
                "sheet": "模拟明细",
                "range": "B4:D8",
            },
            "excel",
        ),
        (
            {
                "id": "document-anchor",
                "kind": "document",
                "materialId": "material-document",
                "materialVersionId": "material-document-v1",
                "contentHash": CONTENT_HASH,
                "paragraphId": "p-1",
                "runId": "r-1",
                "renderedPage": 1,
                "renderedPageBbox": {
                    "x": 0.2,
                    "y": 0.2,
                    "width": 0.3,
                    "height": 0.2,
                },
            },
            "document",
        ),
        (
            {
                "id": "media-anchor",
                "kind": "media",
                "materialId": "material-media",
                "materialVersionId": "material-media-v1",
                "contentHash": CONTENT_HASH,
                "startSeconds": 3.2,
                "endSeconds": 5.8,
                "startFrame": 96,
                "endFrame": 174,
                "bbox": {"x": 0.2, "y": 0.2, "width": 0.4, "height": 0.4},
            },
            "media",
        ),
    ],
)
def test_source_anchor_discriminator_accepts_each_precise_kind(
    anchor: dict[str, object], expected: str
) -> None:
    payload = _result_payload()
    payload["mediaKind"] = expected
    payload["materialId"] = anchor["materialId"]
    payload["materialVersionId"] = anchor["materialVersionId"]
    payload["sourceAnchors"] = [anchor]
    payload["observations"][0]["sourceAnchorIds"] = [anchor["id"]]
    payload["extractedFieldCandidates"][0]["sourceAnchorIds"] = [anchor["id"]]
    payload["sceneSpec"]["hotspots"][0]["sourceAnchorId"] = anchor["id"]
    result = MaterialIntelligenceResult.model_validate(payload)
    assert result.source_anchors[0].kind == expected


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("sourceAnchors", 0, "bbox"), {"x": 0.9, "y": 0.2, "width": 0.2, "height": 0.2}),
        (("sourceAnchors", 0, "charEnd"), 0),
        (("sceneSpec", "objects", 0, "size", "x"), 0),
    ],
)
def test_rejects_out_of_bounds_geometry_or_reverse_character_span(
    path: tuple[object, ...], value: object
) -> None:
    payload = _result_payload()
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        MaterialIntelligenceResult.model_validate(payload)


def test_rejects_cross_material_anchor_and_missing_anchor_reference() -> None:
    payload = _result_payload()
    payload["sourceAnchors"][0]["materialVersionId"] = "other-version"
    with pytest.raises(ValidationError, match="bind this material/version/hash"):
        MaterialIntelligenceResult.model_validate(payload)

    payload = _result_payload()
    payload["observations"][0]["sourceAnchorIds"] = ["anchor-invented"]
    with pytest.raises(ValidationError, match="must exist in sourceAnchors"):
        MaterialIntelligenceResult.model_validate(payload)


def test_scene_spec_rejects_executable_or_external_fields() -> None:
    for field in ("script", "javascript", "html", "shader", "url", "code"):
        payload = _result_payload()
        payload["sceneSpec"][field] = "forbidden"
        with pytest.raises(ValidationError):
            MaterialIntelligenceResult.model_validate(payload)

    payload = _result_payload()
    payload["sceneSpec"]["cameraPreset"] = "free_camera"
    with pytest.raises(ValidationError):
        MaterialIntelligenceResult.model_validate(payload)


def test_scene_spec_hotspot_requires_registered_source_anchor() -> None:
    payload = _result_payload()
    payload["sceneSpec"]["hotspots"][0]["sourceAnchorId"] = "not-registered"
    with pytest.raises(ValidationError, match="must reference a SourceAnchor"):
        MaterialIntelligenceResult.model_validate(payload)


def test_result_status_requires_real_candidate_or_human_review_item() -> None:
    payload = _result_payload()
    payload["status"] = "needs_review"
    with pytest.raises(ValidationError, match="requires unresolvedItems"):
        MaterialIntelligenceResult.model_validate(payload)

    payload["unresolvedItems"] = [
        {
            "id": "unresolved-sim-001",
            "kind": "manual_review",
            "question": "请人工确认模拟图像的版本对应关系。",
            "reason": "当前候选不能替代人工核验。",
            "requiresHumanReview": True,
            "sourceAnchorIds": ["anchor-sim-image-001"],
        }
    ]
    assert MaterialIntelligenceResult.model_validate(payload).status.value == "needs_review"


def test_result_cross_validates_request_binding_hash_and_goal() -> None:
    request = MaterialIntelligenceRequest.model_validate(_request_payload())
    result = MaterialIntelligenceResult.model_validate(_result_payload())
    assert (
        validate_material_intelligence_result(
            request, result, expected_input_hash=INPUT_HASH
        )
        is result
    )

    altered_request = _request_payload()
    altered_request["taskGoals"] = ["observe"]
    with pytest.raises(ValueError, match="SceneSpec was not requested"):
        validate_material_intelligence_result(
            MaterialIntelligenceRequest.model_validate(altered_request),
            result,
            expected_input_hash=INPUT_HASH,
        )

    invalid = deepcopy(_result_payload())
    invalid["inputHash"] = "c" * 64
    with pytest.raises(ValueError, match="does not match"):
        validate_material_intelligence_result(
            request,
            MaterialIntelligenceResult.model_validate(invalid),
            expected_input_hash=INPUT_HASH,
        )


def test_result_schema_excludes_authoritative_and_executable_fields() -> None:
    forbidden = {
        "factVersion",
        "factValue",
        "scoreGrade",
        "decisionGrade",
        "confidenceScore",
        "hardConstraintResults",
        "approval",
        "transition",
        "javascript",
        "shader",
        "url",
    }
    schema_text = str(MaterialIntelligenceResult.model_json_schema(by_alias=True))
    for field in forbidden:
        assert field not in schema_text
