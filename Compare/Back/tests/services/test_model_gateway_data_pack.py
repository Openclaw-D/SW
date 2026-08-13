from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from app.contracts.data_pack import (
    ExecuteImportManifestRequest,
    ImportManifestRequest,
    MaterialIntelligenceRunCommand,
)
from app.contracts.errors import BusinessValidationError, ServiceError
from app.contracts.model_gateway import ModelGatewayMode, ModelGatewayRequest
from app.core.config import Settings
from app.services.workbench import create_workbench_service
from app.services.generation import generate_project_bundle
from app.services.generator_adapter import GeneratedProjectBundle
from app.services.material_intelligence import DeterministicSyntheticMaterialProvider
from app.models import DocumentLocator
from tests.services.fixtures import StaticGenerator, make_bundle


def _command(
    material_id: str,
    version_id: str,
    *,
    mode: str | None = None,
    context: str = "explicit-v1",
    expected_version: int = 1,
):
    return MaterialIntelligenceRunCommand(
        projectId="project-a",
        materialId=material_id,
        materialVersionId=version_id,
        contextVersion=context,
        taskGoals=["observe", "extract_field_candidates"],
        expectedVersion=expected_version,
        providerMode=mode,
    )


def _controlled_original_service(tmp_path, *, mode=ModelGatewayMode.REAL):
    import_root = tmp_path / "imports"
    manifest_root = import_root / "uploads" / "project-a" / "upload-001" / "extracted"
    source_root = manifest_root / "files"
    source_root.mkdir(parents=True)
    bundle = make_bundle("project-a")
    bundle.workbench["materials"].append(
        {
            "id": "project-a-document",
            "versionId": "project-a-document-v1",
            "fileName": "脱敏说明.docx",
            "label": "脱敏 Word 说明",
            "availability": "available",
            "isSimulated": True,
            "sourceLabel": "测试生成器",
            "kind": "document",
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "description": "完整脱敏模拟 Word 原件",
        }
    )
    bundle.workbench["project"]["materialCount"] += 1
    materials = {item["id"]: deepcopy(item) for item in bundle.workbench["materials"]}
    source_specs = {
        "project-a-image": ("site.png", b"synthetic-deidentified-image-bytes"),
        "project-a-pdf": ("contract.pdf", b"%PDF synthetic deidentified contract"),
        "project-a-excel": ("ledger.xlsx", b"PK synthetic deidentified workbook"),
        "project-a-document": ("memo.docx", b"PK synthetic deidentified document"),
    }
    items = []
    for material_id, (filename, content) in source_specs.items():
        (source_root / filename).write_bytes(content)
        items.append(
            {
                "materialId": material_id,
                "sourceFile": f"files/{filename}",
                "sha256": hashlib.sha256(content).hexdigest(),
                "classification": "synthetic_demo",
                "authorizationRef": "provider-input-test-authorization",
                "material": materials[material_id],
            }
        )
    manifest_path = manifest_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {"manifestVersion": "1.0", "projectId": "project-a", "items": items},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = create_workbench_service(
        Settings(
            database_path=tmp_path / "provider-input.db",
            import_root=import_root,
            model_gateway_mode=mode,
        ),
        generator=StaticGenerator(bundle, identity="provider-input-test-v1"),
    )
    old_versions = {
        material_id: service.get_material("project-a", material_id).version_id
        for material_id in source_specs
    }
    manifest_ref = "uploads/project-a/upload-001/extracted/manifest.json"
    service.preflight_material_import(
        "project-a",
        ImportManifestRequest(projectId="project-a", manifestRef=manifest_ref),
    )
    service.execute_material_import(
        "project-a",
        ExecuteImportManifestRequest(
            projectId="project-a",
            manifestRef=manifest_ref,
            expectedVersion=1,
        ),
        idempotency_key="provider-input-import-001",
    )
    return service, source_specs, old_versions


def _gateway_request_for(service, material_id: str) -> ModelGatewayRequest:
    with service.repository.transaction(write=False) as connection:
        material = service.repository.get_material("project-a", material_id, connection)
        version = service.repository.get_material_version(
            "project-a", material.current_version_id, connection
        )
        source = connection.execute(
            "SELECT * FROM material_source_records WHERE material_version_id = ?",
            (version.id,),
        ).fetchone()
    media_kind = {
        "image": "image",
        "pdf": "pdf",
        "excel": "excel",
        "document": "document",
        "scene": "document",
    }[version.payload["kind"]]
    return ModelGatewayRequest.model_validate(
        {
            "requestId": f"request-{material_id}",
            "capabilityId": "material_intelligence",
            "mode": "real",
            "trigger": "explicit_action",
            "material": {
                "projectId": "project-a",
                "materialId": material_id,
                "materialVersionId": version.id,
                "contentHash": version.content_hash,
                "mediaKind": media_kind,
                "sourceRef": source["source_ref"],
                "dataClassification": source["classification"],
                "usageAuthorizationRef": source["authorization_ref"],
            },
            "contextVersion": "provider-input-v1",
            "projectContext": {"dimensionId": "compliance", "locale": "zh-CN"},
            "fieldSchemas": [
                {"fieldKey": "registration_valid", "label": "登记状态", "valueType": "boolean"}
            ],
            "taskGoals": ["observe", "extract_field_candidates"],
            "inputHash": version.content_hash,
        }
    )


class CaptureRealProvider:
    def __init__(self) -> None:
        self.call_count = 0
        self.context = None

    async def analyze(self, request, context, input_hash):
        self.call_count += 1
        self.context = context
        return {
            "projectId": request.project_id,
            "materialId": request.material_id,
            "materialVersionId": request.material_version_id,
            "contentHash": request.content_hash,
            "mediaKind": request.media_kind.value,
            "contextVersion": request.context_version,
            "dataClassification": request.data_classification.value,
            "status": "needs_review",
            "confidence": 0.25,
            "observations": [],
            "extractedFieldCandidates": [],
            "unresolvedItems": [
                {
                    "id": "unresolved-provider-input-test",
                    "kind": "manual_review",
                    "question": "请人工核验 provider 返回结果。",
                    "reason": "测试 provider 不生成权威候选。",
                    "requiresHumanReview": True,
                    "sourceAnchorIds": [],
                }
            ],
            "sourceAnchors": [],
            "sceneSpec": None,
            "modelInfo": {
                "provider": "capture-real-test-provider",
                "model": "no-network-test-model",
                "modelVersion": "1",
            },
            "promptVersion": "provider-input-test-v1",
            "schemaVersion": "1.0",
            "inputHash": input_hash,
            "advisoryOnly": True,
            "isSimulated": False,
            "dataStatus": "provider_generated_unverified",
            "source": "capture_real_test_provider",
            "disclaimer": "测试 fake transport，仅验证 real providerInput 边界，不代表真实外部调用。",
        }


def test_model_gateway_settings_freeze_environment_modes(monkeypatch) -> None:
    monkeypatch.setenv("COMPARE_MODEL_GATEWAY_MODE", "real")
    monkeypatch.setenv("COMPARE_MODEL_GATEWAY_TIMEOUT_SECONDS", "12.5")
    settings = Settings.from_environment()
    assert settings.model_gateway_mode == ModelGatewayMode.REAL
    assert settings.model_gateway_timeout_seconds == 12.5


@pytest.mark.parametrize(
    "material_id",
    ["project-a-image", "project-a-pdf", "project-a-excel", "project-a-document"],
)
def test_real_provider_input_assembles_four_controlled_original_carriers_in_memory(
    tmp_path,
    material_id: str,
) -> None:
    service, source_specs, _old_versions = _controlled_original_service(tmp_path)
    try:
        request = _gateway_request_for(service, material_id)
        provider_input = service.data_pack.assemble_model_gateway_provider_input(request)
        assert set(provider_input) == {"filename", "mimeType", "fileDataBase64"}
        assert base64.b64decode(provider_input["fileDataBase64"], validate=True) == source_specs[material_id][1]
        assert "/" not in provider_input["filename"]
        assert "\\" not in provider_input["filename"]
        serialized = json.dumps(provider_input, ensure_ascii=False)
        assert str(service.data_pack.settings.import_root) not in serialized
        assert request.material.source_ref not in serialized
    finally:
        service.close()


def test_document_original_produces_reviewable_paragraph_run_locator(tmp_path) -> None:
    service, _source_specs, _old_versions = _controlled_original_service(tmp_path)
    try:
        material = service.get_material("project-a", "project-a-document")
        version = service.repository.raw_connection_for_tests().execute(
            "SELECT version FROM material_versions WHERE id = ?", (material.version_id,)
        ).fetchone()["version"]
        stored = service.run_material_intelligence(
            "project-a",
            material.id,
            _command(material.id, material.version_id, expected_version=version),
            idempotency_key="document-anchor-001",
        )
        assert stored.result.source_anchors[0].kind == "document"
        with service.repository.transaction(write=False) as connection:
            evidence = service.repository.get_evidence_reference(
                "project-a", stored.evidence_refs[0], connection
            )
            service.locators.validate_reference("project-a", evidence, connection)
        assert isinstance(evidence.locator, DocumentLocator)
        assert evidence.locator.paragraph_id == "p1"
        assert evidence.locator.run_id == "r1"
        assert evidence.locator.rendered_page == 1
    finally:
        service.close()


def test_provider_input_requires_explicit_real_and_real_configuration(tmp_path) -> None:
    service, _source_specs, _old_versions = _controlled_original_service(tmp_path)
    try:
        real_request = _gateway_request_for(service, "project-a-image")
        payload = real_request.model_dump(by_alias=True, mode="json")
        payload["mode"] = "synthetic"
        synthetic_request = ModelGatewayRequest.model_validate(payload)
        with pytest.raises(BusinessValidationError) as wrong_mode:
            service.data_pack.assemble_model_gateway_provider_input(synthetic_request)
        assert wrong_mode.value.code == "provider_input_real_only"
    finally:
        service.close()

    disabled, _source_specs, _old_versions = _controlled_original_service(
        tmp_path / "disabled",
        mode=ModelGatewayMode.DISABLED,
    )
    try:
        request = _gateway_request_for(disabled, "project-a-image")
        with pytest.raises(BusinessValidationError) as disabled_error:
            disabled.data_pack.assemble_model_gateway_provider_input(request)
        assert disabled_error.value.code == "model_gateway_real_not_enabled"
    finally:
        disabled.close()


def test_synthetic_disabled_and_seed_paths_never_assemble_provider_input(tmp_path, monkeypatch) -> None:
    service, _source_specs, _old_versions = _controlled_original_service(tmp_path)
    real_provider = CaptureRealProvider()
    service.data_pack.providers[ModelGatewayMode.REAL] = real_provider
    calls = 0

    def forbidden_assembly(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("providerInput assembly must remain real-only")

    monkeypatch.setattr(service.data_pack, "_assemble_provider_input", forbidden_assembly)
    try:
        material = service.get_material("project-a", "project-a-image")
        version = service.repository.raw_connection_for_tests().execute(
            "SELECT version FROM material_versions WHERE id = ?", (material.version_id,)
        ).fetchone()["version"]
        synthetic, synthetic_context = service.data_pack.prepare_intelligence(
            "project-a",
            material.id,
            _command(material.id, material.version_id, expected_version=version),
        )
        assert synthetic.result.is_simulated is True
        assert "providerInput" not in synthetic_context

        disabled, disabled_context = service.data_pack.prepare_intelligence(
            "project-a",
            material.id,
            _command(
                material.id,
                material.version_id,
                mode="disabled",
                expected_version=version,
            ),
        )
        assert disabled.result.status.value == "unavailable"
        assert "providerInput" not in disabled_context

        seeded, seed_context = service.data_pack.prepare_intelligence(
            "project-a",
            material.id,
            _command(
                material.id,
                material.version_id,
                context="p5-seed-v1",
                expected_version=version,
            ),
        )
        assert seeded.result.status.value == "unavailable"
        assert "providerInput" not in seed_context
        assert calls == 0
        assert real_provider.call_count == 0
    finally:
        service.close()


def test_provider_input_rejects_cross_project_old_version_and_hash_mismatch(tmp_path) -> None:
    service, _source_specs, old_versions = _controlled_original_service(tmp_path)
    try:
        request = _gateway_request_for(service, "project-a-image")

        cross_payload = request.model_dump(by_alias=True, mode="json")
        cross_payload["material"]["projectId"] = "project-b"
        cross = ModelGatewayRequest.model_validate(cross_payload)
        with pytest.raises(Exception) as cross_error:
            service.data_pack.assemble_model_gateway_provider_input(cross)
        assert getattr(cross_error.value, "code", None) == "material_not_found"

        old_payload = request.model_dump(by_alias=True, mode="json")
        old_payload["material"]["materialVersionId"] = old_versions["project-a-image"]
        old = ModelGatewayRequest.model_validate(old_payload)
        with pytest.raises(Exception) as old_error:
            service.data_pack.assemble_model_gateway_provider_input(old)
        assert getattr(old_error.value, "code", None) == "version_conflict"

        hash_payload = request.model_dump(by_alias=True, mode="json")
        hash_payload["material"]["contentHash"] = "f" * 64
        hash_payload["inputHash"] = "f" * 64
        mismatched_hash = ModelGatewayRequest.model_validate(hash_payload)
        with pytest.raises(BusinessValidationError) as hash_error:
            service.data_pack.assemble_model_gateway_provider_input(mismatched_hash)
        assert hash_error.value.code == "provider_input_binding_mismatch"
    finally:
        service.close()


def test_provider_input_rejects_path_traversal_missing_authorization_and_changed_bytes(tmp_path) -> None:
    service, _source_specs, _old_versions = _controlled_original_service(tmp_path)
    try:
        request = _gateway_request_for(service, "project-a-image")
        version_id = request.material.material_version_id
        with service.repository.transaction(write=True) as connection:
            connection.execute("DROP TRIGGER material_source_records_immutable_update")
            connection.execute(
                "UPDATE material_source_records SET source_file_ref = ? WHERE material_version_id = ?",
                ("../outside.png", version_id),
            )
        with pytest.raises(BusinessValidationError) as traversal:
            service.data_pack.assemble_model_gateway_provider_input(request)
        assert traversal.value.code == "provider_input_path_invalid"

        with service.repository.transaction(write=True) as connection:
            connection.execute(
                "UPDATE material_source_records SET source_file_ref = ?, authorization_ref = ? WHERE material_version_id = ?",
                (
                    "uploads/project-a/upload-001/extracted/files/site.png",
                    "",
                    version_id,
                ),
            )
        with pytest.raises(BusinessValidationError) as unauthorized:
            service.data_pack.assemble_model_gateway_provider_input(request)
        assert unauthorized.value.code == "material_source_unauthorized"
    finally:
        service.close()

    changed, _source_specs, _old_versions = _controlled_original_service(tmp_path / "changed")
    try:
        changed_request = _gateway_request_for(changed, "project-a-image")
        with changed.repository.transaction(write=False) as connection:
            source = connection.execute(
                "SELECT source_file_ref FROM material_source_records WHERE material_version_id = ?",
                (changed_request.material.material_version_id,),
            ).fetchone()
        original_path = changed.data_pack.settings.import_root / source["source_file_ref"]
        original_path.write_bytes(b"tampered-synthetic-bytes")
        with pytest.raises(BusinessValidationError) as hash_error:
            changed.data_pack.assemble_model_gateway_provider_input(changed_request)
        assert hash_error.value.code == "provider_input_hash_mismatch"
    finally:
        changed.close()


def test_real_provider_input_is_not_persisted_or_logged(tmp_path, caplog) -> None:
    service, source_specs, _old_versions = _controlled_original_service(tmp_path)
    provider = CaptureRealProvider()
    service.data_pack.providers[ModelGatewayMode.REAL] = provider
    try:
        material = service.get_material("project-a", "project-a-image")
        with service.repository.transaction(write=False) as connection:
            version = service.repository.get_material_version(
                "project-a", material.version_id, connection
            )
        result = service.run_material_intelligence(
            "project-a",
            material.id,
            _command(
                material.id,
                material.version_id,
                mode="real",
                expected_version=version.version,
            ),
            idempotency_key="provider-input-real-run-001",
        )
        assert provider.call_count == 1
        assert provider.context is not None
        encoded = provider.context["providerInput"]["fileDataBase64"]
        assert base64.b64decode(encoded, validate=True) == source_specs[material.id][1]
        assert result.result.is_simulated is False

        database_dump = "\n".join(service.repository.raw_connection_for_tests().iterdump())
        assert encoded not in database_dump
        assert str(service.data_pack.settings.import_root) not in database_dump
        assert "fileDataBase64" not in database_dump
        assert encoded not in caplog.text
        assert str(service.data_pack.settings.import_root) not in caplog.text
        assert "fileDataBase64" not in caplog.text
    finally:
        service.close()


def test_provider_context_excludes_authoritative_fact_answer_and_unit(tmp_path) -> None:
    bundle = make_bundle("project-a")
    authoritative = bundle.workbench["facts"][0]
    authoritative["value"] = "DO-NOT-LEAK-AUTHORITATIVE-ANSWER"
    authoritative["unit"] = "DO-NOT-LEAK-UNIT"
    service = create_workbench_service(
        Settings(database_path=tmp_path / "no-answer-leak.db"),
        generator=StaticGenerator(bundle, identity="no-answer-leak-v1"),
    )
    try:
        material = service.get_material("project-a", "project-a-excel")
        prepared, context = service.data_pack.prepare_intelligence(
            "project-a", material.id, _command(material.id, material.version_id)
        )
        serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)
        assert "DO-NOT-LEAK-AUTHORITATIVE-ANSWER" not in serialized
        assert "DO-NOT-LEAK-UNIT" not in serialized
        assert set(context) >= {"fieldKey", "dimensionId", "label", "valueType", "materialPayloadHash", "providerMode"}
        assert set(context).isdisjoint(
            {
                "value",
                "unit",
                "scoreGrade",
                "decisionGrade",
                "confidence",
                "evidence",
                "hardGate",
                "approval",
                "hiddenTruth",
            }
        )
        assert prepared.result.extracted_field_candidates[0].value != "DO-NOT-LEAK-AUTHORITATIVE-ANSWER"
        assert prepared.result.advisory_only is True
    finally:
        service.close()


def test_real_mode_requires_explicit_action_and_provider_wiring(tmp_path) -> None:
    service = create_workbench_service(
        Settings(
            database_path=tmp_path / "real-explicit.db",
            model_gateway_mode=ModelGatewayMode.REAL,
        ),
        generator=StaticGenerator(make_bundle("project-a"), identity="real-explicit-v1"),
    )
    try:
        connection = service.repository.raw_connection_for_tests()
        seeded = connection.execute(
            "SELECT status, provider, model, is_simulated FROM material_intelligence_runs"
        ).fetchall()
        # This fixture has no production-site material, so startup cannot synthesize a
        # hidden call merely because real mode is configured.
        assert seeded == []

        material = service.get_material("project-a", "project-a-excel")
        implicit, _ = service.data_pack.prepare_intelligence(
            "project-a", material.id, _command(material.id, material.version_id)
        )
        assert implicit.result.is_simulated is True
        assert implicit.result.model_info.provider == "compare-synthetic"

        with pytest.raises(BusinessValidationError) as error:
            service.data_pack.prepare_intelligence(
                "project-a",
                material.id,
                _command(material.id, material.version_id, mode="real"),
            )
        assert error.value.code == "model_gateway_provider_not_configured"
    finally:
        service.close()


def test_application_startup_in_real_mode_never_invokes_real_provider(tmp_path) -> None:
    generated = generate_project_bundle(20260810, 0).to_mapping()
    bundle = GeneratedProjectBundle(
        catalog=generated["catalog"],
        workbench=generated["workbench"],
        dimension_series=tuple(generated["dimensionSeries"]),
    )
    service = create_workbench_service(
        Settings(
            database_path=tmp_path / "real-startup.db",
            model_gateway_mode=ModelGatewayMode.REAL,
        ),
        generator=StaticGenerator(bundle, identity="real-startup-v1"),
    )
    try:
        connection = service.repository.raw_connection_for_tests()
        rows = connection.execute(
            "SELECT status, provider, model, is_simulated, result_json FROM material_intelligence_runs"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["status"] == "unavailable"
        assert rows[0]["provider"] is None
        assert rows[0]["model"] is None
        assert rows[0]["is_simulated"] == 0
        result = json.loads(rows[0]["result_json"])
        assert result["source"] == "model_gateway_startup_guard"
        assert result["dataStatus"] == "unavailable"
        assert connection.execute("SELECT COUNT(*) FROM extracted_fact_candidates").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM source_anchors").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM scene_specs").fetchone()[0] == 0
    finally:
        service.close()


def test_real_mode_rejects_provider_output_mislabelled_as_synthetic(tmp_path) -> None:
    service, _source_specs, _old_versions = _controlled_original_service(tmp_path)
    try:
        service.data_pack.providers[ModelGatewayMode.REAL] = DeterministicSyntheticMaterialProvider()
        material = service.get_material("project-a", "project-a-excel")
        with service.repository.transaction(write=False) as connection:
            version = service.repository.get_material_version(
                "project-a", material.version_id, connection
            )
        with pytest.raises(ServiceError) as error:
            service.data_pack.prepare_intelligence(
                "project-a",
                material.id,
                _command(
                    material.id,
                    material.version_id,
                    mode="real",
                    expected_version=version.version,
                ),
            )
        assert error.value.code == "model_gateway_mode_mismatch"
    finally:
        service.close()


def test_disabled_mode_returns_unavailable_without_provider_output(tmp_path) -> None:
    service = create_workbench_service(
        Settings(
            database_path=tmp_path / "disabled.db",
            model_gateway_mode=ModelGatewayMode.DISABLED,
        ),
        generator=StaticGenerator(make_bundle("project-a"), identity="disabled-v1"),
    )
    try:
        material = service.get_material("project-a", "project-a-excel")
        prepared, _ = service.data_pack.prepare_intelligence(
            "project-a", material.id, _command(material.id, material.version_id)
        )
        result = prepared.result
        assert result.status.value == "unavailable"
        assert result.advisory_only is True
        assert result.is_simulated is False
        assert result.data_status.value == "unavailable"
        assert result.extracted_field_candidates == []
        assert result.source_anchors == []
    finally:
        service.close()
