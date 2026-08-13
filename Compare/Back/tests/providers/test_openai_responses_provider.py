from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from typing import Any

import pytest

from app.contracts.material_intelligence import MaterialIntelligenceRequest
from app.contracts.material_intelligence import MATERIAL_INTELLIGENCE_DISCLAIMER
from app.providers.openai_responses import (
    OPENAI_PROMPT_VERSION,
    OpenAIProviderConfigurationError,
    OpenAIProviderError,
    OpenAIProviderResponseError,
    OpenAIResponsesMaterialProvider,
    OpenAIResponsesProviderConfig,
    ResponsesHttpResponse,
    derive_gateway_locator_bindings,
    parse_openai_responses_result,
    serialize_openai_responses_request,
)


CONTENT_HASH = "a" * 64
INPUT_HASH = "b" * 64
MODEL = "gpt-5.6-terra"


def _request(kind: str = "image", *, scene: bool = False) -> MaterialIntelligenceRequest:
    goals = ["observe", "extract_field_candidates", "identify_unresolved"]
    if scene:
        goals.append("scene_spec")
    return MaterialIntelligenceRequest.model_validate(
        {
            "projectId": "project-01",
            "materialId": f"material-{kind}",
            "materialVersionId": f"material-{kind}-v1",
            "contentHash": CONTENT_HASH,
            "mediaKind": kind,
            "contextVersion": "p5-mg-provider-v1",
            "taskGoals": goals,
            "dataClassification": "synthetic_demo",
        }
    )


def _provider_input(
    filename: str, mime_type: str, *, detail: str = "auto"
) -> dict[str, Any]:
    return {
        "filename": filename,
        "mimeType": mime_type,
        "fileDataBase64": base64.b64encode(b"synthetic-deidentified").decode(),
        "detail": detail,
    }


def _anchor(request: MaterialIntelligenceRequest) -> dict[str, Any]:
    base = {
        "id": "anchor-provider-1",
        "materialId": request.material_id,
        "materialVersionId": request.material_version_id,
        "contentHash": request.content_hash,
        "kind": request.media_kind.value,
    }
    if request.media_kind.value == "image":
        return {
            **base,
            "page": 1,
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
            "ocrTokenIds": [],
        }
    if request.media_kind.value == "pdf":
        return {
            **base,
            "page": 1,
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
            "ocrTokenIds": [],
        }
    if request.media_kind.value == "excel":
        return {**base, "sheet": "核验表", "range": "B2:C3"}
    raise AssertionError(f"unsupported fixture kind {request.media_kind.value}")


def _candidate(request: MaterialIntelligenceRequest, *, scene: bool = False) -> dict[str, Any]:
    scene_spec = None
    if scene:
        scene_spec = {
            "cameraPreset": "perspective",
            "objects": [
                {
                    "id": "equipment-1",
                    "kind": "box",
                    "regionId": "equipment",
                    "position": {"x": 0, "y": 0, "z": 0},
                    "size": {"x": 2, "y": 1, "z": 1},
                    "rotation": {"x": 0, "y": 0, "z": 0},
                }
            ],
            "hotspots": [
                {
                    "id": "hotspot-1",
                    "objectId": "equipment-1",
                    "regionId": "equipment",
                    "sourceAnchorId": "anchor-provider-1",
                }
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
        "confidence": 0.82,
        "observations": [
            {
                "id": "observation-provider-1",
                "kind": "structure",
                "text": "脱敏合成材料中的候选结构观察。",
                "sourceAnchorIds": ["anchor-provider-1"],
            }
        ],
        "extractedFieldCandidates": [
            {
                "id": "candidate-provider-1",
                "fieldKey": "registration_valid",
                "label": "登记状态",
                "value": True,
                "unit": None,
                "status": "candidate",
                "sourceAnchorIds": ["anchor-provider-1"],
            }
        ],
        "unresolvedItems": [],
        "sourceAnchors": [_anchor(request)],
        "sceneSpec": scene_spec,
        "modelInfo": {"provider": "openai", "model": MODEL, "modelVersion": None},
        "promptVersion": OPENAI_PROMPT_VERSION,
        "schemaVersion": "1.0",
        "inputHash": INPUT_HASH,
        "advisoryOnly": True,
        "isSimulated": False,
        "dataStatus": "provider_generated_unverified",
        "source": "openai_responses_api",
        "disclaimer": MATERIAL_INTELLIGENCE_DISCLAIMER,
    }


def _response(candidate: Mapping[str, Any], *, status: str = "completed") -> bytes:
    return json.dumps(
        {
            "id": "resp_synthetic_test",
            "status": status,
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(candidate)}
                    ],
                }
            ],
        }
    ).encode()


class SequenceTransport:
    def __init__(self, responses: list[ResponsesHttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Mapping[str, str], Mapping[str, Any], float]] = []

    async def post_json(self, url, headers, payload, *, timeout_seconds):
        self.calls.append((url, headers, payload, timeout_seconds))
        return self.responses.pop(0)


def _http(status: int, body: bytes = b"{}") -> ResponsesHttpResponse:
    return ResponsesHttpResponse(status_code=status, headers={}, body=body)


def test_serializes_image_as_multimodal_strict_candidate_request() -> None:
    request = _request("image")
    payload = serialize_openai_responses_request(
        request,
        {
            "fieldKey": "registration_valid",
            "providerInput": _provider_input("factory.png", "image/png", detail="high"),
        },
        INPUT_HASH,
        model=MODEL,
    )

    assert payload["store"] is False
    assert payload["metadata"] == {
        "project_id": "project-01",
        "material_id": "material-image",
        "input_hash": INPUT_HASH,
        "advisory_only": "true",
    }
    image = payload["input"][0]["content"][1]
    assert image["type"] == "input_image"
    assert image["detail"] == "high"
    assert image["image_url"].startswith("data:image/png;base64,")
    output_format = payload["text"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert output_format["schema"]["additionalProperties"] is False
    assert "authoritative FactVersion write" in payload["instructions"]
    assert "factVersion" not in output_format["schema"]["properties"]


@pytest.mark.parametrize(
    ("kind", "filename", "mime_type", "detail"),
    [
        ("pdf", "report.pdf", "application/pdf", "high"),
        (
            "excel",
            "facts.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "auto",
        ),
    ],
)
def test_serializes_pdf_and_excel_as_file_inputs(
    kind: str, filename: str, mime_type: str, detail: str
) -> None:
    payload = serialize_openai_responses_request(
        _request(kind),
        {"providerInput": _provider_input(filename, mime_type, detail=detail)},
        INPUT_HASH,
        model=MODEL,
    )
    item = payload["input"][0]["content"][1]
    assert item["type"] == "input_file"
    assert item["filename"] == filename
    assert item["file_data"].startswith(f"data:{mime_type};base64,")
    if kind == "pdf":
        assert item["detail"] == "high"
    else:
        assert "detail" not in item


def test_scene_spec_goal_stays_declarative_and_strictly_parses() -> None:
    request = _request("image", scene=True)
    payload = serialize_openai_responses_request(
        request,
        {"providerInput": _provider_input("site.png", "image/png")},
        INPUT_HASH,
        model=MODEL,
    )
    prompt = json.loads(payload["input"][0]["content"][0]["text"])
    assert "Return sceneSpec only" in prompt["scenePolicy"]
    assert all(term in payload["instructions"] for term in ("URL", "HTML", "JavaScript", "shader"))

    result, response_id = parse_openai_responses_result(
        _response(_candidate(request, scene=True)),
        request=request,
        input_hash=INPUT_HASH,
        configured_model=MODEL,
    )
    assert result.scene_spec is not None
    assert result.scene_spec.hotspots[0].source_anchor_id == "anchor-provider-1"
    assert result.is_simulated is False
    assert response_id == "resp_synthetic_test"


@pytest.mark.parametrize(
    ("kind", "expected_locator"),
    [
        (
            "image",
            {
                "kind": "image",
                "materialId": "material-image",
                "materialVersionId": "material-image-v1",
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
            },
        ),
        (
            "pdf",
            {
                "kind": "pdf",
                "materialId": "material-pdf",
                "materialVersionId": "material-pdf-v1",
                "page": 1,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
            },
        ),
        (
            "excel",
            {
                "kind": "excel",
                "materialId": "material-excel",
                "materialVersionId": "material-excel-v1",
                "sheet": "核验表",
                "range": "B2:C3",
            },
        ),
    ],
)
def test_derives_stable_gateway_locator_binding_from_validated_anchor(
    kind: str,
    expected_locator: dict[str, Any],
) -> None:
    result, _response_id = parse_openai_responses_result(
        _response(_candidate(_request(kind))),
        request=_request(kind),
        input_hash=INPUT_HASH,
        configured_model=MODEL,
    )

    assert derive_gateway_locator_bindings(result) == [
        {
            "sourceAnchorId": "anchor-provider-1",
            "locator": expected_locator,
        }
    ]


def test_strict_parse_rejects_result_content_hash_mismatch() -> None:
    request = _request("image")
    mismatched = _candidate(request)
    mismatched["contentHash"] = "c" * 64
    mismatched["sourceAnchors"][0]["contentHash"] = "c" * 64

    with pytest.raises(OpenAIProviderResponseError, match="frozen material contract"):
        parse_openai_responses_result(
            _response(mismatched),
            request=request,
            input_hash=INPUT_HASH,
            configured_model=MODEL,
        )


def test_strict_parse_rejects_authority_fields_and_identity_spoofing() -> None:
    request = _request("image")
    authority = _candidate(request)
    authority["factVersion"] = {"id": "forbidden"}
    with pytest.raises(OpenAIProviderResponseError, match="frozen material contract"):
        parse_openai_responses_result(
            _response(authority),
            request=request,
            input_hash=INPUT_HASH,
            configured_model=MODEL,
        )

    simulated = _candidate(request)
    simulated["isSimulated"] = True
    simulated["dataStatus"] = "simulated"
    with pytest.raises(OpenAIProviderResponseError, match="real provider"):
        parse_openai_responses_result(
            _response(simulated),
            request=request,
            input_hash=INPUT_HASH,
            configured_model=MODEL,
        )


def test_provider_retries_only_retryable_status_and_records_metadata() -> None:
    request = _request("image")
    transport = SequenceTransport([_http(429), _http(200, _response(_candidate(request)))])
    provider = OpenAIResponsesMaterialProvider(
        OpenAIResponsesProviderConfig(
            api_key="test-placeholder",
            model=MODEL,
            max_retries=1,
            retry_base_seconds=0,
        ),
        transport=transport,
    )

    result = asyncio.run(
        provider.analyze(
            request,
            {"providerInput": _provider_input("site.png", "image/png")},
            INPUT_HASH,
        )
    )

    assert result.input_hash == INPUT_HASH
    assert len(transport.calls) == 2
    assert transport.calls[0][1]["Authorization"] == "Bearer test-placeholder"
    assert provider.last_call is not None
    assert provider.last_call.status == "completed"
    assert provider.last_call.attempts == 2
    assert provider.last_call.error is None


def test_non_retryable_error_stops_after_one_attempt() -> None:
    request = _request("image")
    transport = SequenceTransport([_http(400)])
    provider = OpenAIResponsesMaterialProvider(
        OpenAIResponsesProviderConfig(api_key="test-placeholder", model=MODEL),
        transport=transport,
    )

    with pytest.raises(OpenAIProviderError) as raised:
        asyncio.run(
            provider.analyze(
                request,
                {"providerInput": _provider_input("site.png", "image/png")},
                INPUT_HASH,
            )
        )
    assert raised.value.code == "provider_http_400"
    assert raised.value.retryable is False
    assert len(transport.calls) == 1
    assert provider.last_call is not None
    assert provider.last_call.status == "failed"
    assert provider.last_call.retryable is False


def test_cancellation_propagates_and_records_cancelled_status() -> None:
    class HangingTransport:
        async def post_json(self, *_args, **_kwargs):
            await asyncio.Event().wait()

    async def scenario() -> OpenAIResponsesMaterialProvider:
        provider = OpenAIResponsesMaterialProvider(
            OpenAIResponsesProviderConfig(api_key="test-placeholder", model=MODEL),
            transport=HangingTransport(),
        )
        task = asyncio.create_task(
            provider.analyze(
                _request("image"),
                {"providerInput": _provider_input("site.png", "image/png")},
                INPUT_HASH,
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return provider

    provider = asyncio.run(scenario())
    assert provider.last_call is not None
    assert provider.last_call.status == "cancelled"
    assert provider.last_call.error == "provider_cancelled"


def test_missing_environment_credential_stops_without_network(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(OpenAIProviderConfigurationError) as raised:
        OpenAIResponsesMaterialProvider.from_environment()
    assert raised.value.code == "provider_not_configured"
    assert raised.value.retryable is False


def test_rejects_multiple_or_invalid_provider_sources() -> None:
    context = _provider_input("site.png", "image/png")
    context["imageUrl"] = "https://example.invalid/site.png"
    with pytest.raises(OpenAIProviderConfigurationError) as raised:
        serialize_openai_responses_request(
            _request("image"), {"providerInput": context}, INPUT_HASH, model=MODEL
        )
    assert raised.value.code == "provider_source_invalid"
