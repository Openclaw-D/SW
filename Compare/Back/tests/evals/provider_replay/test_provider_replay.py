from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
from copy import deepcopy

import pytest

from app.contracts.errors import ServiceError
from app.contracts.material_intelligence import MATERIAL_INTELLIGENCE_DISCLAIMER
from app.contracts.model_gateway import ModelGatewayOutput, ModelGatewayRequest
from evals.model_gateway.provider_replay import ProviderReplayHarness


CONTENT_HASH = "a" * 64
CANONICAL_INPUT_HASH = "b" * 64


def _request() -> ModelGatewayRequest:
    return ModelGatewayRequest.model_validate(
        {
            "requestId": "request-provider-replay-001",
            "capabilityId": "material_intelligence",
            "mode": "real",
            "trigger": "explicit_action",
            "material": {
                "projectId": "project-provider-replay",
                "materialId": "material-provider-replay",
                "materialVersionId": "material-provider-replay-v1",
                "contentHash": CONTENT_HASH,
                "mediaKind": "excel",
                "sourceRef": "authorized/project-provider-replay/material-provider-replay",
                "dataClassification": "synthetic_demo",
                "usageAuthorizationRef": None,
            },
            "contextVersion": "context-provider-replay-v1",
            "projectContext": {
                "dimensionId": "transaction",
                "industryCode": "synthetic-provider-replay",
                "locale": "zh-CN",
            },
            "fieldSchemas": [
                {
                    "fieldKey": "equipment_model",
                    "label": "设备型号",
                    "valueType": "string",
                }
            ],
            "taskGoals": ["extract_field_candidates"],
            "inputHash": CANONICAL_INPUT_HASH,
            "schemaVersion": "1.0",
        }
    )


def _raw_result(request: ModelGatewayRequest) -> dict:
    return {
        "projectId": request.material.project_id,
        "materialId": request.material.material_id,
        "materialVersionId": request.material.material_version_id,
        "contentHash": request.material.content_hash,
        "mediaKind": request.material.media_kind.value,
        "contextVersion": request.context_version,
        "dataClassification": request.material.data_classification.value,
        "status": "completed",
        "confidence": 0.81,
        "observations": [],
        "extractedFieldCandidates": [
            {
                "id": "candidate-equipment-model",
                "fieldKey": "equipment_model",
                "label": "设备型号候选",
                "value": "SYNTHETIC-MODEL-01",
                "unit": None,
                "status": "candidate",
                "sourceAnchorIds": ["anchor-equipment-model"],
            }
        ],
        "unresolvedItems": [],
        "sourceAnchors": [
            {
                "id": "anchor-equipment-model",
                "kind": "excel",
                "materialId": request.material.material_id,
                "materialVersionId": request.material.material_version_id,
                "contentHash": request.material.content_hash,
                "sheet": "设备清单",
                "range": "E4",
            }
        ],
        "sceneSpec": None,
        "modelInfo": {
            "provider": "openai",
            "model": "mock-responses-model",
            "modelVersion": "provider-replay-v1",
        },
        "promptVersion": "provider-replay-v1",
        "schemaVersion": "1.0",
        "inputHash": request.input_hash,
        "advisoryOnly": True,
        "isSimulated": False,
        "dataStatus": "provider_generated_unverified",
        "source": "openai_responses_api",
        "disclaimer": MATERIAL_INTELLIGENCE_DISCLAIMER,
    }


def _provider_input() -> tuple[dict[str, str], tuple[str, ...]]:
    raw_marker = "provider-replay-raw-material-marker"
    encoded_marker = base64.b64encode(raw_marker.encode()).decode("ascii")
    path_segment_marker = "provider-replay-absolute-path-marker"
    path_marker = rf"C:\private\{path_segment_marker}\material.xlsx"
    key_marker = "provider-replay-placeholder-key-never-persist"
    filename_marker = "private-provider-replay.xlsx"
    return (
        {
            "filename": filename_marker,
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "fileDataBase64": encoded_marker,
            "absolutePath": path_marker,
            "apiKey": key_marker,
        },
        (
            raw_marker,
            encoded_marker,
            path_segment_marker,
            path_marker,
            key_marker,
            filename_marker,
        ),
    )


def _run_once(tmp_path, raw_result: dict):
    request = _request()
    provider_input, _markers = _provider_input()
    harness = ProviderReplayHarness(
        database_path=tmp_path / "provider-replay-invalid.db",
        request=request,
        raw_result=raw_result,
        provider_input=provider_input,
    )
    try:
        return asyncio.run(harness.execute(idempotency_key="provider-replay-invalid-001"))
    finally:
        harness.close()


def test_real_replay_owns_canonical_hash_idempotency_and_redacted_record(
    tmp_path,
) -> None:
    request = _request()
    raw_result = _raw_result(request)
    provider_input, forbidden_markers = _provider_input()
    database_path = tmp_path / "provider-replay.db"

    with ProviderReplayHarness(
        database_path=database_path,
        request=request,
        raw_result=raw_result,
        provider_input=provider_input,
    ) as harness:
        evidence = asyncio.run(
            harness.execute_and_replay(
                idempotency_key="provider-replay-success-001",
            )
        )

    output = evidence.first_output
    assert evidence.first_execution_provider_calls == 1
    assert evidence.replay_provider_calls == 0
    assert evidence.observed_input_hashes == (request.input_hash,)
    assert evidence.replay_output == output
    assert output.input_hash == request.input_hash
    assert output.result is not None
    assert output.result.input_hash == request.input_hash
    assert output.source_anchors == output.result.source_anchors
    assert evidence.run_record.run_id == output.run_id
    assert evidence.run_record.input_hash == request.input_hash

    serialized_output = output.model_dump_json(by_alias=True)
    assert "factVersion" not in serialized_output
    with sqlite3.connect(database_path) as connection:
        database_dump = "\n".join(connection.iterdump())
    for marker in forbidden_markers:
        assert marker not in database_dump


def test_adapter_derives_envelope_locator_bindings_from_validated_anchors(
    tmp_path,
) -> None:
    request = _request()
    provider_input, _markers = _provider_input()
    with ProviderReplayHarness(
        database_path=tmp_path / "provider-replay-locator.db",
        request=request,
        raw_result=_raw_result(request),
        provider_input=provider_input,
    ) as harness:
        output = asyncio.run(
            harness.execute(idempotency_key="provider-replay-locator-001")
        )

    assert output.source_anchors == output.result.source_anchors
    assert [
        binding.model_dump(by_alias=True, mode="json")
        for binding in output.locator_bindings
    ] == [
        {
            "sourceAnchorId": "anchor-equipment-model",
            "locator": {
                "kind": "excel",
                "materialId": request.material.material_id,
                "materialVersionId": request.material.material_version_id,
                "sheet": "设备清单",
                "range": "E4",
            },
        }
    ]


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        (lambda payload: payload.update({"schemaVersion": "2.0"}), "invalid_output"),
        (lambda payload: payload.update({"materialId": "other-material"}), "invalid_output"),
        (
            lambda payload: payload.update({"materialVersionId": "other-material-v2"}),
            "invalid_output",
        ),
        (lambda payload: payload.update({"inputHash": "c" * 64}), "invalid_output"),
        (
            lambda payload: payload["sourceAnchors"][0].update({"range": "not-a-range"}),
            "invalid_output",
        ),
        (
            lambda payload: payload.update(
                {
                    "locatorBindings": [
                        {
                            "sourceAnchorId": "anchor-equipment-model",
                            "locator": {"kind": "excel", "sheet": "模型伪造", "range": "A1"},
                        }
                    ]
                }
            ),
            "invalid_output",
        ),
    ],
    ids=(
        "schema",
        "material",
        "version",
        "input-hash",
        "anchor-locator",
        "model-owned-envelope-locator",
    ),
)
def test_schema_locator_material_version_and_input_hash_mismatch_are_rejected(
    tmp_path,
    mutation,
    expected_fragment: str,
) -> None:
    payload = deepcopy(_raw_result(_request()))
    mutation(payload)
    with pytest.raises(ServiceError) as raised:
        _run_once(tmp_path, payload)
    assert raised.value.code == expected_fragment


def test_content_hash_mismatch_is_rejected_against_the_backend_request(tmp_path) -> None:
    payload = deepcopy(_raw_result(_request()))
    payload["contentHash"] = "d" * 64
    payload["sourceAnchors"][0]["contentHash"] = "d" * 64

    with pytest.raises(ServiceError) as raised:
        _run_once(tmp_path, payload)
    assert raised.value.code == "invalid_output"


def test_provider_result_cannot_carry_fact_version_authority(tmp_path) -> None:
    payload = deepcopy(_raw_result(_request()))
    payload["factVersion"] = {
        "id": "forbidden-fact-version",
        "value": "must-not-write",
    }

    with pytest.raises(ServiceError) as raised:
        _run_once(tmp_path, payload)
    assert raised.value.code == "invalid_output"
    assert "factVersion" not in json.dumps(
        ModelGatewayOutput.model_json_schema(by_alias=True),
        ensure_ascii=False,
    )
