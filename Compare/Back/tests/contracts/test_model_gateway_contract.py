from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.contracts.model_gateway import (
    ModelGatewayCapability,
    ModelGatewayError,
    ModelGatewayErrorCode,
    ModelGatewayMode,
    ModelGatewayOutput,
    ModelGatewayRequest,
    ModelGatewayRunRecord,
    ModelGatewayRunStatus,
)


INPUT_HASH = "b" * 64
CONTENT_HASH = "a" * 64
DISCLAIMER = "仅供人工核验，候选不得直接写入权威事实。"


def _request_payload() -> dict:
    return {
        "requestId": "request-001",
        "capabilityId": "material-intelligence-v1",
        "mode": "synthetic",
        "trigger": "explicit_action",
        "material": {
            "projectId": "project-sim-001",
            "materialId": "material-sim-001",
            "materialVersionId": "material-sim-001-v1",
            "contentHash": CONTENT_HASH,
            "mediaKind": "excel",
            "sourceRef": "material://project-sim-001/material-sim-001/v1",
            "dataClassification": "synthetic_demo",
            "usageAuthorizationRef": "synthetic-fixture-v1",
        },
        "contextVersion": "context-v1",
        "projectContext": {"dimensionId": "compliance", "locale": "zh-CN"},
        "fieldSchemas": [
            {"fieldKey": "registration_valid", "label": "登记状态", "valueType": "boolean"}
        ],
        "taskGoals": ["observe", "extract_field_candidates"],
        "inputHash": INPUT_HASH,
        "schemaVersion": "1.0",
    }


def _result_payload() -> dict:
    return {
        "projectId": "project-sim-001",
        "materialId": "material-sim-001",
        "materialVersionId": "material-sim-001-v1",
        "contentHash": CONTENT_HASH,
        "mediaKind": "excel",
        "contextVersion": "context-v1",
        "dataClassification": "synthetic_demo",
        "status": "completed",
        "confidence": 0.7,
        "observations": [],
        "extractedFieldCandidates": [
            {
                "id": "candidate-001",
                "fieldKey": "registration_valid",
                "label": "登记状态候选",
                "value": True,
                "unit": None,
                "status": "needs_review",
                "sourceAnchorIds": ["anchor-001"],
            }
        ],
        "unresolvedItems": [],
        "sourceAnchors": [
            {
                "id": "anchor-001",
                "kind": "excel",
                "materialId": "material-sim-001",
                "materialVersionId": "material-sim-001-v1",
                "contentHash": CONTENT_HASH,
                "sheet": "登记",
                "range": "B4:B4",
            }
        ],
        "sceneSpec": None,
        "modelInfo": {
            "provider": "compare-synthetic",
            "model": "deterministic-material-intelligence",
            "modelVersion": "1.0",
        },
        "promptVersion": "material-intelligence-v1",
        "schemaVersion": "1.0",
        "inputHash": INPUT_HASH,
        "advisoryOnly": True,
        "isSimulated": True,
        "dataStatus": "simulated",
        "source": "compare_synthetic_material_provider",
        "disclaimer": DISCLAIMER,
    }


def _output_payload() -> dict:
    result = _result_payload()
    return {
        "requestId": "request-001",
        "runId": "run-001",
        "capabilityId": "material-intelligence-v1",
        "mode": "synthetic",
        "status": "succeeded",
        "materialId": "material-sim-001",
        "materialVersionId": "material-sim-001-v1",
        "inputHash": INPUT_HASH,
        "result": result,
        "sourceAnchors": result["sourceAnchors"],
        "locatorBindings": [
            {
                "sourceAnchorId": "anchor-001",
                "locator": {
                    "kind": "excel",
                    "materialId": "material-sim-001",
                    "materialVersionId": "material-sim-001-v1",
                    "sheet": "登记",
                    "range": "B4:B4",
                },
            }
        ],
        "error": None,
        "advisoryOnly": True,
        "isSimulated": True,
        "dataStatus": "simulated",
        "source": result["source"],
        "disclaimer": DISCLAIMER,
        "schemaVersion": "1.0",
    }


def test_gateway_modes_capability_and_request_are_frozen() -> None:
    assert {item.value for item in ModelGatewayMode} == {"disabled", "synthetic", "real"}
    capability = ModelGatewayCapability(
        capabilityId="material-intelligence-v1",
        providerId="provider-neutral",
        supportedModes=["synthetic", "real"],
        inputKinds=["image", "pdf", "excel"],
        outputKinds=["observations", "field_candidates", "source_anchors", "scene_spec"],
        advisoryOnly=True,
    )
    assert capability.advisory_only is True
    request = ModelGatewayRequest.model_validate(_request_payload())
    dumped = request.model_dump(by_alias=True, mode="json")
    assert dumped["trigger"] == "explicit_action"
    assert "value" not in dumped["fieldSchemas"][0]
    assert "unit" not in dumped["fieldSchemas"][0]


def test_gateway_output_binds_version_anchor_locator_and_advisory_truth() -> None:
    output = ModelGatewayOutput.model_validate(_output_payload())
    assert output.advisory_only is True
    assert output.result is not None
    assert output.result.advisory_only is True

    mismatched = _output_payload()
    mismatched["locatorBindings"][0]["sourceAnchorId"] = "invented-anchor"
    with pytest.raises(ValidationError, match="must reference a SourceAnchor"):
        ModelGatewayOutput.model_validate(mismatched)

    wrong_version = _output_payload()
    wrong_version["locatorBindings"][0]["locator"]["materialVersionId"] = "other-v2"
    with pytest.raises(ValidationError, match="bind the SourceAnchor material/version"):
        ModelGatewayOutput.model_validate(wrong_version)

    forbidden = deepcopy(_output_payload())
    forbidden["result"]["factValue"] = True
    with pytest.raises(ValidationError):
        ModelGatewayOutput.model_validate(forbidden)


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        ("timeout", True),
        ("rate_limited", True),
        ("provider_unavailable", True),
        ("invalid_output", False),
        ("authorization_required", False),
        ("safety_blocked", False),
    ],
)
def test_gateway_error_taxonomy_freezes_retryability(code: str, retryable: bool) -> None:
    assert ModelGatewayError(code=code, message="稳定错误", retryable=retryable)
    with pytest.raises(ValidationError, match="retryable"):
        ModelGatewayError(code=code, message="稳定错误", retryable=not retryable)


def test_run_record_status_and_mode_truth_are_cross_validated() -> None:
    record = ModelGatewayRunRecord(
        runId="run-real-001",
        requestId="request-real-001",
        capabilityId="material-intelligence-v1",
        mode="real",
        status="needs_review",
        materialId="material-001",
        materialVersionId="material-001-v1",
        inputHash=INPUT_HASH,
        providerId="future-provider",
        startedAt="2026-08-12T08:00:00Z",
        finishedAt="2026-08-12T08:00:01Z",
        advisoryOnly=True,
        isSimulated=False,
        dataStatus="provider_generated_unverified",
        source="future_provider_unverified",
        disclaimer=DISCLAIMER,
    )
    assert record.status == ModelGatewayRunStatus.NEEDS_REVIEW

    invalid = record.model_dump(by_alias=True, mode="json")
    invalid["isSimulated"] = True
    with pytest.raises(ValidationError, match="mode must match"):
        ModelGatewayRunRecord.model_validate(invalid)


def test_disabled_output_cannot_claim_success_or_generated_content() -> None:
    payload = _output_payload()
    payload.update(
        {
            "mode": "disabled",
            "status": "unavailable",
            "result": None,
            "sourceAnchors": [],
            "locatorBindings": [],
            "isSimulated": False,
            "dataStatus": "unavailable",
            "source": "model_gateway_disabled",
        }
    )
    assert ModelGatewayOutput.model_validate(payload).status == ModelGatewayRunStatus.UNAVAILABLE
    payload["status"] = "succeeded"
    with pytest.raises(ValidationError):
        ModelGatewayOutput.model_validate(payload)


def test_schema_keeps_authority_fields_out_of_gateway_request_and_output() -> None:
    schema_text = str(
        {
            "request": ModelGatewayRequest.model_json_schema(by_alias=True),
            "output": ModelGatewayOutput.model_json_schema(by_alias=True),
        }
    )
    for field in (
        "scoreGrade",
        "decisionGrade",
        "hardGate",
        "approval",
        "transition",
        "factVersion",
    ):
        assert field not in schema_text
