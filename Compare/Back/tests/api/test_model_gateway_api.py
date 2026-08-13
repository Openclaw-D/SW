from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from fastapi.testclient import TestClient

from app.contracts.material_intelligence import MATERIAL_INTELLIGENCE_DISCLAIMER
from app.contracts.model_gateway import ModelGatewayMode, ModelGatewayRequest
from app.core.config import Settings
from app.main import create_app
from app.providers.openai_responses import (
    OPENAI_PROMPT_VERSION,
    OpenAIResponsesMaterialProvider,
    OpenAIResponsesProviderConfig,
    ResponsesHttpResponse,
)
from tests.model_gateway.fixtures import gateway_request


class ProviderInputSpy:
    def __init__(self, raw_bytes: bytes = b"synthetic-production-wire-bytes") -> None:
        self.raw_bytes = raw_bytes
        self.call_count = 0

    def assemble_model_gateway_provider_input(
        self,
        request: ModelGatewayRequest,
    ) -> dict[str, str]:
        self.call_count += 1
        assert request.mode == ModelGatewayMode.REAL
        return {
            "filename": "material.png",
            "mimeType": "image/png",
            "fileDataBase64": base64.b64encode(self.raw_bytes).decode("ascii"),
        }


class WorkbenchSpy:
    def __init__(self, data_pack: ProviderInputSpy) -> None:
        self.data_pack = data_pack

    def close(self) -> None:
        pass


class CaptureTransport:
    def __init__(self, response_body: bytes) -> None:
        self.response_body = response_body
        self.calls: list[tuple[str, Mapping[str, str], Mapping[str, Any], float]] = []

    async def post_json(self, url, headers, payload, *, timeout_seconds):
        self.calls.append((url, headers, payload, timeout_seconds))
        return ResponsesHttpResponse(
            status_code=200,
            headers={},
            body=self.response_body,
        )


def _real_gateway_request() -> ModelGatewayRequest:
    payload = gateway_request().model_dump(mode="json", by_alias=True)
    payload["mode"] = "real"
    payload["material"].update(
        {
            "contentHash": "a" * 64,
            "mediaKind": "image",
            "sourceRef": "synthetic/project-01/material-01",
        }
    )
    payload["inputHash"] = "a" * 64
    return ModelGatewayRequest.model_validate(payload)


def _openai_needs_review_response(request: ModelGatewayRequest, model: str) -> bytes:
    result = {
        "projectId": request.material.project_id,
        "materialId": request.material.material_id,
        "materialVersionId": request.material.material_version_id,
        "contentHash": request.material.content_hash,
        "mediaKind": request.material.media_kind.value,
        "contextVersion": request.context_version,
        "dataClassification": request.material.data_classification.value,
        "status": "needs_review",
        "confidence": 0.25,
        "observations": [],
        "extractedFieldCandidates": [],
        "unresolvedItems": [
            {
                "id": "unresolved-production-wire-1",
                "kind": "manual_review",
                "question": "请人工核验 mock transport 返回结果。",
                "reason": "该结果只验证生产接线，不代表真实外部实调。",
                "requiresHumanReview": True,
                "sourceAnchorIds": [],
            }
        ],
        "sourceAnchors": [],
        "sceneSpec": None,
        "modelInfo": {"provider": "openai", "model": model, "modelVersion": None},
        "promptVersion": OPENAI_PROMPT_VERSION,
        "schemaVersion": "1.0",
        "inputHash": request.input_hash,
        "advisoryOnly": True,
        "isSimulated": False,
        "dataStatus": "provider_generated_unverified",
        "source": "openai_responses_api",
        "disclaimer": MATERIAL_INTELLIGENCE_DISCLAIMER,
    }
    return json.dumps(
        {
            "id": "resp_production_wire_mock",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(result)}
                    ],
                }
            ],
        }
    ).encode("utf-8")


def test_startup_is_lazy_and_capabilities_are_synthetic_only(tmp_path) -> None:
    application = create_app(settings=Settings(database_path=tmp_path / "lazy.db"))
    calls = 0
    original_factory = application.state.model_gateway_factory

    def counting_factory():
        nonlocal calls
        calls += 1
        return original_factory()

    application.state.model_gateway_factory = counting_factory
    with TestClient(application) as client:
        assert calls == 0
        response = client.get("/api/v1/model-gateway/capabilities")
        assert response.status_code == 200
        assert calls == 1
        capability = response.json()["data"][0]
        assert capability["supportedModes"] == ["synthetic"]
        assert capability["advisoryOnly"] is True


def test_explicit_execution_idempotency_restart_and_project_isolation(tmp_path) -> None:
    database_path = tmp_path / "api-gateway.db"
    settings = Settings(database_path=database_path)
    request = gateway_request()
    payload = request.model_dump(mode="json", by_alias=True)

    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-api-001"},
            json=payload,
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["status"] == "needs_review"
        assert result["advisoryOnly"] is True
        assert result["isSimulated"] is True
        assert result["dataStatus"] == "simulated"
        assert result["result"]["extractedFieldCandidates"] == []
        assert result["result"]["unresolvedItems"][0]["requiresHumanReview"] is True
        run_id = result["runId"]

        replay = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-api-001"},
            json=payload,
        )
        assert replay.status_code == 200
        assert replay.json()["data"] == result

        cross_project = client.get(
            f"/api/v1/projects/project-02/model-gateway/runs/{run_id}"
        )
        assert cross_project.status_code == 404
        assert cross_project.json()["errors"][0]["code"] == "model_run_not_found"

    with TestClient(create_app(settings=settings)) as restarted:
        persisted = restarted.get(
            f"/api/v1/projects/project-01/model-gateway/runs/{run_id}"
        )
        assert persisted.status_code == 200
        record = persisted.json()["data"]
        assert record["runId"] == run_id
        assert record["status"] == "needs_review"
        serialized = persisted.text.lower()
        assert str(Path.cwd()).lower() not in serialized
        assert "authorization" not in serialized
        assert "customer.pdf" not in serialized


def test_api_requires_explicit_action_and_safe_path_match(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "validation.db")
    payload = gateway_request().model_dump(mode="json", by_alias=True)
    with TestClient(create_app(settings=settings)) as client:
        missing_key = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            json=payload,
        )
        assert missing_key.status_code == 422
        assert missing_key.json()["errors"][0]["code"] == "idempotency_key_required"

        mismatch = client.post(
            "/api/v1/projects/project-02/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-mismatch-001"},
            json=payload,
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["errors"][0]["code"] == "path_body_mismatch"

        implicit = dict(payload)
        implicit["trigger"] = "automatic"
        invalid_trigger = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-trigger-001"},
            json=implicit,
        )
        assert invalid_trigger.status_code == 422
        assert invalid_trigger.json()["errors"][0]["code"] == "validation_error"


def test_real_configuration_keeps_synthetic_fake_and_disabled_is_unavailable(
    tmp_path,
) -> None:
    data_pack = ProviderInputSpy()
    real_settings = Settings(
        database_path=tmp_path / "real-with-synthetic.db",
        model_gateway_mode=ModelGatewayMode.REAL,
    )
    with TestClient(create_app(settings=real_settings, service=WorkbenchSpy(data_pack))) as client:
        capabilities = client.get("/api/v1/model-gateway/capabilities")
        assert capabilities.status_code == 200
        capability = capabilities.json()["data"][0]
        assert capability["providerId"] == "openai_responses_api"
        assert capability["supportedModes"] == ["synthetic", "real"]

        synthetic = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-real-config-synthetic-001"},
            json=gateway_request().model_dump(mode="json", by_alias=True),
        )
        assert synthetic.status_code == 200
        assert synthetic.json()["data"]["source"] == "synthetic_fake"
        assert synthetic.json()["data"]["isSimulated"] is True
        assert data_pack.call_count == 0

    disabled_settings = Settings(
        database_path=tmp_path / "disabled.db",
        model_gateway_mode=ModelGatewayMode.DISABLED,
    )
    with TestClient(
        create_app(settings=disabled_settings, service=WorkbenchSpy(ProviderInputSpy()))
    ) as client:
        assert client.get("/api/v1/model-gateway/capabilities").json()["data"] == []
        disabled = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-disabled-001"},
            json=gateway_request().model_dump(mode="json", by_alias=True),
        )
        assert disabled.status_code == 503
        assert disabled.json()["errors"][0]["code"] == "gateway_disabled"


def test_missing_openai_key_fails_before_material_assembly_or_network(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    data_pack = ProviderInputSpy()
    settings = Settings(
        database_path=tmp_path / "missing-key.db",
        model_gateway_mode=ModelGatewayMode.REAL,
    )
    application = create_app(settings=settings, service=WorkbenchSpy(data_pack))
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/model-gateway/capabilities").status_code == 200
        assert data_pack.call_count == 0

        response = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-missing-key-001"},
            json=_real_gateway_request().model_dump(mode="json", by_alias=True),
        )
        assert response.status_code == 503
        assert response.json()["errors"][0]["code"] == "provider_not_configured"
        assert data_pack.call_count == 0
        assert application.state.workbench_service is not None


def test_real_mode_workbench_seed_never_calls_openai_transport(tmp_path) -> None:
    request = _real_gateway_request()
    model = "gpt-5.6-terra"
    transport = CaptureTransport(_openai_needs_review_response(request, model))
    provider = OpenAIResponsesMaterialProvider(
        OpenAIResponsesProviderConfig(
            api_key="test-placeholder-seed-guard-key",
            model=model,
            max_retries=0,
        ),
        transport=transport,
    )
    settings = Settings(
        database_path=tmp_path / "real-seed-guard.db",
        model_gateway_mode=ModelGatewayMode.REAL,
    )
    application = create_app(settings=settings, openai_provider=provider)
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/model-gateway/capabilities").status_code == 200
        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200
        assert projects.json()["data"]
        assert transport.calls == []


def test_mock_transport_real_run_calls_once_and_persists_only_redacted_metadata(
    tmp_path,
    caplog,
) -> None:
    request = _real_gateway_request()
    model = "gpt-5.6-terra"
    transport = CaptureTransport(_openai_needs_review_response(request, model))
    provider = OpenAIResponsesMaterialProvider(
        OpenAIResponsesProviderConfig(
            api_key="test-placeholder-production-wire-key",
            model=model,
            max_retries=0,
        ),
        transport=transport,
    )
    raw_bytes = b"synthetic-production-wire-secret-material"
    data_pack = ProviderInputSpy(raw_bytes)
    database_path = tmp_path / "production-wire.db"
    settings = Settings(
        database_path=database_path,
        model_gateway_mode=ModelGatewayMode.REAL,
    )
    with TestClient(
        create_app(
            settings=settings,
            service=WorkbenchSpy(data_pack),
            openai_provider=provider,
        )
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/model-gateway/capabilities").status_code == 200
        assert transport.calls == []
        assert data_pack.call_count == 0

        payload = request.model_dump(mode="json", by_alias=True)
        first = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-production-wire-001"},
            json=payload,
        )
        assert first.status_code == 200
        result = first.json()["data"]
        assert result["mode"] == "real"
        assert result["isSimulated"] is False
        assert result["dataStatus"] == "provider_generated_unverified"
        assert result["source"] == "openai_responses_api"
        assert len(transport.calls) == 1
        assert data_pack.call_count == 1

        replay = client.post(
            "/api/v1/projects/project-01/model-gateway/runs",
            headers={"Idempotency-Key": "gateway-production-wire-001"},
            json=payload,
        )
        assert replay.status_code == 200
        assert replay.json()["data"] == result
        assert len(transport.calls) == 1
        assert data_pack.call_count == 1

        record = client.get(
            f"/api/v1/projects/project-01/model-gateway/runs/{result['runId']}"
        )
        assert record.status_code == 200
        assert record.json()["data"]["isSimulated"] is False
        assert record.json()["data"]["dataStatus"] == "provider_generated_unverified"

    encoded = base64.b64encode(raw_bytes).decode("ascii")
    transport_payload = json.dumps(transport.calls[0][2], ensure_ascii=False)
    assert encoded in transport_payload
    with sqlite3.connect(database_path) as connection:
        database_dump = "\n".join(connection.iterdump())
    forbidden = (
        encoded,
        raw_bytes.decode("ascii"),
        "fileDataBase64",
        request.material.source_ref,
        "material.png",
        "test-placeholder-production-wire-key",
        str(tmp_path),
    )
    for value in forbidden:
        assert value not in database_dump
        assert value not in caplog.text
