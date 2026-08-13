from __future__ import annotations

import hashlib
import io
import json
import zipfile
from copy import deepcopy

from fastapi.testclient import TestClient

from app.contracts.data_pack import ExecuteImportManifestRequest, ImportManifestRequest
from app.contracts.errors import ServiceError
from app.contracts.model_gateway import ModelGatewayMode
from app.contracts.workbench import WorkbenchProject
from app.core.config import Settings
from app.main import create_app
from app.services.workbench import create_workbench_service
from app.services.generation import generate_project_bundle
from app.services.generation.generator import P5_MATERIAL_COVERAGE
from app.services.generator_adapter import GeneratedProjectBundle
from app.services.material_intelligence import DeterministicSyntheticMaterialProvider
from tests.services.fixtures import StaticGenerator, make_bundle


def _excel_payload(material_id: str) -> dict:
    return {
        "id": material_id,
        "versionId": f"{material_id}-placeholder",
        "fileName": "synthetic-import.xlsx",
        "label": "受控导入 synthetic 台账",
        "availability": "available",
        "isSimulated": True,
        "sourceLabel": "测试授权目录中的 synthetic fixture",
        "kind": "excel",
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "sheets": [{"name": "数据", "columns": ["字段", "值"], "rows": [["registration_valid", True]]}],
    }


def _carrier_payload(kind: str, material_id: str, image_id: str) -> dict:
    base = {
        "id": material_id, "versionId": f"{material_id}-placeholder",
        "fileName": f"{material_id}.demo", "label": f"{kind} synthetic fixture",
        "availability": "available", "isSimulated": True,
        "sourceLabel": "synthetic carrier test", "kind": kind,
    }
    if kind == "excel":
        return _excel_payload(material_id)
    if kind == "pdf":
        return {**base, "mimeType": "application/pdf", "pageCount": 1, "pages": [{"page": 1, "title": "synthetic", "lines": ["synthetic"]}]}
    if kind == "document":
        return {
            **base,
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "description": "synthetic deidentified Word original",
        }
    if kind == "image":
        return {**base, "mimeType": "image/png", "pixelWidth": 100, "pixelHeight": 100, "description": "synthetic", "focalArea": {"x": 0, "y": 0, "width": 1, "height": 1}}
    if kind == "media":
        return {**base, "mimeType": "video/mp4", "mediaKind": "video", "durationSeconds": 1, "description": "synthetic", "posterMaterialId": image_id}
    return {**base, "mimeType": "application/vnd.compare.gaussian-scene+json", "sceneFormat": "compare-gaussian-preview-v1", "points": [{"id": "point-1", "x": 0, "y": 0, "z": 0, "size": 1, "color": "#ffffff"}], "fallbackMaterialId": image_id, "description": "synthetic declarative scene"}


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def _source_name_for(material: dict, stem: str = "source") -> str:
    suffix_by_mime = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "image/vnd.compare.panorama": ".json",
        "application/vnd.compare.gaussian-scene+json": ".json",
        "model/gltf-binary": ".glb",
    }
    return f"{stem}{suffix_by_mime[material['mimeType']]}"


class _ReviewableSyntheticCandidateProvider:
    """Test-only fake that never reads an authoritative FactVersion answer."""

    def __init__(self) -> None:
        self.delegate = DeterministicSyntheticMaterialProvider()

    async def analyze(self, request, context, input_hash):
        result = await self.delegate.analyze(request, context, input_hash)
        result["extractedFieldCandidates"][0]["value"] = True
        return result


def test_native_manifest_binds_seed_v1_to_original_without_staling_evidence(tmp_path) -> None:
    bundle = make_bundle("project-a")
    material = deepcopy(bundle.workbench["materials"][0])
    source_bytes = b"native seed material bound before the first database snapshot"
    archive_root = tmp_path / "external-materials"
    project_root = archive_root / "native-material-packs" / "project-01"
    project_root.mkdir(parents=True)
    source_name = _source_name_for(material)
    (project_root / source_name).write_bytes(source_bytes)
    (project_root / "manifest.json").write_text(json.dumps({
        "manifestVersion": "1.0",
        "projectId": "project-a",
        "items": [{
            "materialId": material["id"],
            "sourceFile": source_name,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "classification": "synthetic_demo",
            "authorizationRef": "native-seed-test",
            "material": material,
        }],
    }), encoding="utf-8")
    settings = Settings(
        database_path=tmp_path / "native-seed.db",
        import_root=archive_root / "native-material-packs",
        material_root=archive_root,
    )
    service = create_workbench_service(settings, generator=StaticGenerator(bundle, identity="native-seed-v1"))
    current = service.repository.raw_connection_for_tests().execute(
        """SELECT m.current_version_id, mv.content_hash, ms.source_file_ref
           FROM materials m
           JOIN material_versions mv ON mv.id = m.current_version_id
           JOIN material_source_records ms ON ms.material_version_id = mv.id
           WHERE m.project_id = 'project-a' AND m.id = ?""",
        (material["id"],),
    ).fetchone()
    assert current["current_version_id"] == material["versionId"]
    assert current["content_hash"] == hashlib.sha256(source_bytes).hexdigest()
    assert current["source_file_ref"] == f"project-01/{source_name}"
    assert service.get_material_original("project-a", material["id"])[0].read_bytes() == source_bytes
    service.close()


def test_identical_complete_package_reuses_versions_after_restart(tmp_path) -> None:
    bundle = make_bundle("project-a")
    import_root = tmp_path / "imports"
    pack_root = import_root / "project-01"
    pack_root.mkdir(parents=True)
    items = []
    for material in bundle.workbench["materials"]:
        if material["kind"] == "scene" or (
            material["kind"] == "media" and material.get("mediaKind") != "video"
        ):
            continue
        source_name = f"sources/{_source_name_for(material, material['id'])}"
        source_bytes = f"complete-package::{material['id']}".encode()
        target = pack_root / source_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source_bytes)
        items.append({
            "materialId": material["id"], "sourceFile": source_name,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "classification": "synthetic_demo", "authorizationRef": "complete-package-test",
            "material": material,
        })
    (pack_root / "manifest.json").write_text(json.dumps({
        "manifestVersion": "1.0", "projectId": "project-a", "items": items,
    }), encoding="utf-8")
    settings = Settings(database_path=tmp_path / "identical-package.db", import_root=import_root)
    generator = StaticGenerator(bundle, identity="identical-package-v1")
    first = create_workbench_service(settings, generator=generator)
    command = ImportManifestRequest(projectId="project-a", manifestRef="project-01/manifest.json")
    preview = first.preflight_material_import("project-a", command)
    execute = ExecuteImportManifestRequest(projectId="project-a", manifestRef="project-01/manifest.json", expectedVersion=1)
    first.execute_material_import("project-a", execute, idempotency_key="complete-import-001")
    first_versions = [item.material_version_id for item in preview.items]
    version_count_after_first = first.repository.raw_connection_for_tests().execute(
        "SELECT COUNT(*) FROM material_versions WHERE project_id = 'project-a'"
    ).fetchone()[0]
    first.close()

    restarted = create_workbench_service(settings, generator=generator)
    repeat_preview = restarted.preflight_material_import("project-a", command)
    repeated = restarted.execute_material_import("project-a", execute, idempotency_key="complete-import-002")
    assert [item.material_version_id for item in repeat_preview.items] == first_versions
    assert [item.material_version_id for item in repeated.items] == first_versions
    connection = restarted.repository.raw_connection_for_tests()
    assert connection.execute("SELECT COUNT(*) FROM material_versions WHERE project_id = 'project-a'").fetchone()[0] == version_count_after_first
    restarted.close()


def test_material_upload_cors_allows_file_name_header(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "cors.db", import_root=tmp_path / "imports")
    service = create_workbench_service(settings, generator=StaticGenerator(make_bundle("project-a"), identity="cors-v1"))
    with TestClient(create_app(settings=settings, service=service)) as client:
        response = client.options(
            "/api/v1/projects/project-a/materials/uploads",
            headers={
                "Origin": "http://127.0.0.1:4317",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-file-name",
            },
        )
        assert response.status_code == 200
        assert "x-file-name" in response.headers["access-control-allow-headers"].lower()
    service.close()


def test_zip_upload_import_and_original_are_isolated_and_persistent(tmp_path) -> None:
    source_bytes = b"original synthetic ledger bytes"
    material_id = "project-a-upload-ledger"
    manifest = {
        "manifestVersion": "1.0", "projectId": "project-a", "items": [{
            "materialId": material_id, "sourceFile": "ledger.xlsx",
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "classification": "synthetic_demo", "authorizationRef": "zip-test-auth",
            "material": _excel_payload(material_id),
        }],
    }
    archive = _zip_bytes({"pack/manifest.json": json.dumps(manifest).encode(), "pack/ledger.xlsx": source_bytes})
    settings = Settings(database_path=tmp_path / "zip.db", import_root=tmp_path / "imports")
    generator = StaticGenerator(make_bundle("project-a"), make_bundle("project-b"), identity="zip-upload-v1")
    service = create_workbench_service(settings, generator=generator)
    with TestClient(create_app(settings=settings, service=service)) as client:
        upload = client.post("/api/v1/projects/project-a/materials/uploads", content=archive, headers={"X-File-Name": "pack.zip"})
        assert upload.status_code == 200
        receipt = upload.json()["data"]
        assert receipt["byteSize"] == len(archive) and receipt["isSimulated"] is True
        assert str(settings.import_root) not in json.dumps(receipt)
        preflight = client.post("/api/v1/projects/project-a/materials/imports/preflight", json={"projectId": "project-a", "manifestRef": receipt["manifestRef"]})
        assert preflight.status_code == 200
        imported = client.post("/api/v1/projects/project-a/materials/imports", headers={"Idempotency-Key": "zip-import-key-01"}, json={"projectId": "project-a", "manifestRef": receipt["manifestRef"], "expectedVersion": 1})
        assert imported.status_code == 200
        original = client.get(f"/api/v1/projects/project-a/materials/{material_id}/original")
        assert original.status_code == 503
        assert original.json()["errors"][0]["code"] == "material_root_not_configured"
        assert client.get(f"/api/v1/projects/project-b/materials/{material_id}/original").status_code == 404
    service.close()
    restarted = create_workbench_service(settings, generator=generator)
    try:
        restarted.get_material_original("project-a", material_id)
        raise AssertionError("an unset external material root must not serve import-root files")
    except ServiceError as error:
        assert error.code == "material_root_not_configured"
    restarted.close()


def test_zip_upload_rejects_slip_and_early_limit_without_writing_project(tmp_path, monkeypatch) -> None:
    import app.services.data_pack as data_pack
    monkeypatch.setattr(data_pack, "MAX_UPLOAD_BYTES", 8)
    settings = Settings(database_path=tmp_path / "zip-invalid.db", import_root=tmp_path / "imports")
    service = create_workbench_service(settings, generator=StaticGenerator(make_bundle("project-a"), identity="zip-invalid-v1"))
    with TestClient(create_app(settings=settings, service=service)) as client:
        too_large = client.post("/api/v1/projects/project-a/materials/uploads", content=b"123456789", headers={"X-File-Name": "pack.zip", "Content-Length": "9"})
        assert too_large.status_code == 422
        monkeypatch.setattr(data_pack, "MAX_UPLOAD_BYTES", 100 * 1024 * 1024)
        slip = _zip_bytes({"../manifest.json": b"{}"})
        unsafe = client.post("/api/v1/projects/project-a/materials/uploads", content=slip, headers={"X-File-Name": "pack.zip"})
        assert unsafe.status_code == 422
        assert service.repository.raw_connection_for_tests().execute("SELECT COUNT(*) FROM material_imports").fetchone()[0] == 0
    service.close()


def test_upload_size_gate_has_99_100_and_over_boundaries_without_large_fixtures(tmp_path, monkeypatch) -> None:
    """Content-Length is rejected before the body is consumed, so no 100 MiB fixture is needed."""
    import app.services.data_pack as data_pack

    monkeypatch.setattr(data_pack, "MAX_UPLOAD_BYTES", 100)
    settings = Settings(database_path=tmp_path / "size-boundary.db", import_root=tmp_path / "imports")
    service = create_workbench_service(settings, generator=StaticGenerator(make_bundle("project-a"), identity="size-boundary-v1"))

    async def one_chunk():
        yield b"not-a-zip"

    import asyncio
    for size in (99, 100):
        try:
            asyncio.run(service.data_pack.upload_zip("project-a", "pack.zip", size, one_chunk()))
        except Exception as exc:
            assert getattr(exc, "code", None) == "upload_zip_invalid"
        else:  # pragma: no cover - the deliberately invalid archive must fail after the size guard
            raise AssertionError("invalid ZIP unexpectedly accepted")
    try:
        asyncio.run(service.data_pack.upload_zip("project-a", "pack.zip", 101, one_chunk()))
    except Exception as exc:
        assert getattr(exc, "code", None) == "upload_too_large"
    else:  # pragma: no cover
        raise AssertionError("oversized Content-Length unexpectedly accepted")
    service.close()


def test_extract_project_total_and_compression_bomb_are_limited(tmp_path, monkeypatch) -> None:
    import app.services.data_pack as data_pack

    monkeypatch.setattr(data_pack, "MAX_PROJECT_BYTES", 100)
    settings = Settings(database_path=tmp_path / "extract-limits.db", import_root=tmp_path / "imports")
    service = create_workbench_service(settings, generator=StaticGenerator(make_bundle("project-a"), identity="extract-limits-v1"))
    for size in (99, 100):
        archive_path = tmp_path / f"{size}.zip"
        archive_path.write_bytes(_zip_bytes({"pack/original.pdf": b"a" * size}))
        target = tmp_path / f"target-{size}"
        service.data_pack._extract_zip(archive_path, target)
        assert (target / "pack/original.pdf").stat().st_size == size
    archive_path = tmp_path / "101.zip"
    archive_path.write_bytes(_zip_bytes({"pack/original.pdf": b"a" * 101}))
    try:
        service.data_pack._extract_zip(archive_path, tmp_path / "target-101")
    except Exception as exc:
        assert getattr(exc, "code", None) == "upload_project_too_large"
    else:  # pragma: no cover
        raise AssertionError("101-byte project unexpectedly accepted")

    bomb_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pack/highly-compressible.pdf", b"0" * 10_000)
    try:
        service.data_pack._extract_zip(bomb_path, tmp_path / "bomb-target")
    except Exception as exc:
        assert getattr(exc, "code", None) == "upload_zip_bomb"
    else:  # pragma: no cover
        raise AssertionError("compression bomb unexpectedly accepted")
    service.close()


def test_preflight_accepts_controlled_carriers_and_rejects_unknown_or_mismatched_types(tmp_path) -> None:
    import_root = tmp_path / "controlled-carriers"
    import_root.mkdir()
    material_id = "project-a-control-image"
    valid_material = _carrier_payload("image", material_id, material_id)
    source = import_root / "image.webp"
    source.write_bytes(b"synthetic-webp")
    valid_material["mimeType"] = "image/webp"
    valid_material["fileName"] = source.name
    manifest = {
        "manifestVersion": "1.0", "projectId": "project-a", "items": [{
            "materialId": material_id, "sourceFile": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "classification": "synthetic_demo", "authorizationRef": "carrier-test",
            "material": valid_material,
        }],
    }
    (import_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    service = create_workbench_service(
        Settings(database_path=tmp_path / "controlled-carriers.db", import_root=import_root),
        generator=StaticGenerator(make_bundle("project-a"), identity="carrier-v1"),
    )
    assert service.preflight_material_import("project-a", ImportManifestRequest(projectId="project-a", manifestRef="manifest.json")).items[0].kind == "image"
    valid_material["folderPath"] = "现场照片"
    valid_material["businessPath"] = "现场照片/image.webp"
    (import_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    try:
        service.preflight_material_import("project-a", ImportManifestRequest(projectId="project-a", manifestRef="manifest.json"))
    except Exception as exc:
        assert getattr(exc, "code", None) == "import_business_path_mismatch"
    else:  # pragma: no cover
        raise AssertionError("business path mismatch unexpectedly accepted")
    valid_material.pop("folderPath")
    valid_material.pop("businessPath")
    source.rename(import_root / "image.exe")
    manifest["items"][0]["sourceFile"] = "image.exe"
    (import_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    try:
        service.preflight_material_import("project-a", ImportManifestRequest(projectId="project-a", manifestRef="manifest.json"))
    except Exception as exc:
        assert getattr(exc, "code", None) == "import_source_type_invalid"
    else:  # pragma: no cover
        raise AssertionError("executable carrier unexpectedly accepted")
    service.close()


def test_preflight_rejects_glb_because_scene_is_a_derived_artifact(tmp_path) -> None:
    import_root = tmp_path / "glb-carrier"
    import_root.mkdir()
    material_id = "project-a-control-scene"
    source = import_root / "scene.glb"
    source.write_bytes(b"synthetic-glb")
    material = _carrier_payload("scene", material_id, "project-a-control-image")
    material.update({"fileName": source.name, "mimeType": "model/gltf-binary", "sceneFormat": "glb"})
    (import_root / "manifest.json").write_text(json.dumps({
        "manifestVersion": "1.0", "projectId": "project-a", "items": [{
            "materialId": material_id, "sourceFile": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "classification": "synthetic_demo", "authorizationRef": "glb-test", "material": material,
        }],
    }), encoding="utf-8")
    service = create_workbench_service(
        Settings(database_path=tmp_path / "glb-carrier.db", import_root=import_root),
        generator=StaticGenerator(make_bundle("project-a"), identity="glb-v1"),
    )
    try:
        service.preflight_material_import(
            "project-a", ImportManifestRequest(projectId="project-a", manifestRef="manifest.json")
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "import_source_type_invalid"
    else:  # pragma: no cover
        raise AssertionError("derived GLB unexpectedly accepted as an original")
    service.close()


def test_preflight_rejects_panorama_descriptor_but_keeps_real_mp4_compatible(tmp_path) -> None:
    import_root = tmp_path / "panorama-carrier"
    import_root.mkdir()
    image_id = "project-a-control-image"
    material_id = "project-a-control-panorama"
    source = import_root / "panorama.json"
    source.write_bytes(b'{"derived":"panorama descriptor"}')
    material = _carrier_payload("media", material_id, image_id)
    material.update({
        "fileName": source.name,
        "mimeType": "image/vnd.compare.panorama",
        "mediaKind": "panorama",
    })
    (import_root / "manifest.json").write_text(json.dumps({
        "manifestVersion": "1.0", "projectId": "project-a", "items": [{
            "materialId": material_id, "sourceFile": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "classification": "synthetic_demo", "authorizationRef": "panorama-test",
            "material": material,
        }],
    }), encoding="utf-8")
    service = create_workbench_service(
        Settings(database_path=tmp_path / "panorama.db", import_root=import_root),
        generator=StaticGenerator(make_bundle("project-a"), identity="panorama-v1"),
    )
    try:
        service.preflight_material_import(
            "project-a", ImportManifestRequest(projectId="project-a", manifestRef="manifest.json")
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "import_source_type_invalid"
    else:  # pragma: no cover
        raise AssertionError("derived panorama descriptor unexpectedly accepted")
    service.close()


def test_controlled_import_candidate_confirmation_scene_and_restart_end_to_end(tmp_path) -> None:
    import_root = tmp_path / "authorized-imports"
    import_root.mkdir()
    source = import_root / "synthetic-ledger.xlsx"
    source.write_bytes(b"compare-p5-synthetic-material-v1")
    content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    material_id = "project-a-compliance-import-ledger"
    manifest = {
        "manifestVersion": "1.0",
        "projectId": "project-a",
        "items": [{
            "materialId": material_id,
            "sourceFile": source.name,
            "sha256": content_hash,
            "classification": "synthetic_demo",
            "authorizationRef": "test-authorization-p5",
            "material": _excel_payload(material_id),
        }],
    }
    manifest_path = import_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    database = tmp_path / "p5-data-pack.db"
    settings = Settings(database_path=database, import_root=import_root)
    generator = StaticGenerator(
        make_bundle("project-a", frozen_policies=True),
        make_bundle("project-b", frozen_policies=True),
        identity="p5-data-pack-test-v1",
    )
    service = create_workbench_service(settings, generator=generator)
    app = create_app(settings=settings, service=service)

    with TestClient(app) as client:
        preflight = client.post(
            "/api/v1/projects/project-a/materials/imports/preflight",
            json={"projectId": "project-a", "manifestRef": "manifest.json"},
        )
        assert preflight.status_code == 200
        preview = preflight.json()["data"]
        assert preview["items"][0]["contentHash"] == content_hash
        assert "synthetic-ledger" not in json.dumps(preview)

        imported = client.post(
            "/api/v1/projects/project-a/materials/imports",
            headers={"Idempotency-Key": "p5-import-key-001"},
            json={"projectId": "project-a", "manifestRef": "manifest.json", "expectedVersion": 1},
        )
        assert imported.status_code == 200
        imported_data = imported.json()["data"]
        assert imported_data["importedCount"] == 1
        version_id = imported_data["items"][0]["materialVersionId"]

        run = client.post(
            f"/api/v1/projects/project-a/materials/{material_id}/intelligence",
            headers={"Idempotency-Key": "p5-intel-key-001"},
            json={
                "projectId": "project-a", "materialId": material_id,
                "materialVersionId": version_id, "contextVersion": "test-context-v1",
                "taskGoals": ["observe", "extract_field_candidates"], "expectedVersion": 1,
            },
        )
        assert run.status_code == 200
        intel = run.json()["data"]
        assert intel["result"]["isSimulated"] is True
        assert intel["result"]["modelInfo"]["provider"] == "compare-synthetic"
        candidate_id = intel["candidateIds"][0]
        assert intel["evidenceRefs"]

        latest_fact = service.repository.raw_connection_for_tests().execute(
            "SELECT id, version FROM fact_versions WHERE project_id = 'project-a' AND fact_key = 'registration_valid' ORDER BY version DESC LIMIT 1"
        ).fetchone()
        assert latest_fact["version"] == 1  # candidate output has not written authoritative state
        confirmed = client.post(
            f"/api/v1/projects/project-a/candidates/{candidate_id}/confirm",
            headers={"Idempotency-Key": "p5-confirm-key-001"},
            json={
                "projectId": "project-a", "candidateId": candidate_id,
                "fromFactVersionId": latest_fact["id"], "expectedVersion": latest_fact["version"],
                "reason": "人工核对 SourceAnchor 后确认 synthetic 候选。",
            },
        )
        assert confirmed.status_code == 200
        confirmation = confirmed.json()["data"]
        assert confirmation["factVersion"]["version"] == latest_fact["version"] + 1
        assert len(confirmation["policyResults"]) == 3
        assert confirmation["approval"]["hardGateStatus"] in {"pass", "manual_review", "block"}

        image_id = "project-a-image"
        scene_run = client.post(
            f"/api/v1/projects/project-a/materials/{image_id}/intelligence",
            headers={"Idempotency-Key": "p5-scene-key-001"},
            json={
                "projectId": "project-a", "materialId": image_id,
                "materialVersionId": "project-a-image-v1", "contextVersion": "test-scene-v1",
                "taskGoals": ["observe", "scene_spec"], "expectedVersion": 1,
            },
        )
        assert scene_run.status_code == 200
        scene = client.get(f"/api/v1/projects/project-a/materials/{image_id}/scene-spec")
        assert scene.status_code == 200
        scene_data = scene.json()["data"]
        assert {item["regionId"] for item in scene_data["spec"]["objects"]} == {"factory", "equipment", "process"}
        assert "url" not in json.dumps(scene_data).lower()
        assert "shader" not in json.dumps(scene_data).lower()

        isolated = client.get(f"/api/v1/projects/project-b/materials/{image_id}/scene-spec")
        assert isolated.status_code == 404

        connection = service.repository.raw_connection_for_tests()
        source_row = connection.execute(
            "SELECT * FROM material_source_records WHERE material_version_id = ?", (version_id,)
        ).fetchone()
        assert source_row["content_hash"] == content_hash
        assert source_row["classification"] == "synthetic_demo"
        assert source_row["authorization_ref"] == "test-authorization-p5"
        assert str(import_root) not in source_row["source_ref"]
        assert str(source) not in source_row["source_ref"]
        actions = {row[0] for row in connection.execute("SELECT action FROM audit_records WHERE project_id = 'project-a'")}
        assert {"controlled_material_imported", "material_intelligence_recorded", "material_candidate_confirmed", "policy_result_recorded"} <= actions

    restarted = create_workbench_service(settings, generator=generator)
    assert restarted.get_material_intelligence("project-a", material_id).candidate_ids == [candidate_id]
    assert restarted.get_material_scene_spec("project-a", "project-a-image").is_simulated is True
    restarted.close()


def test_p5_http_sqlite_loop_keeps_all_24_material_packs_and_source_anchors_consistent(tmp_path) -> None:
    settings = Settings(database_path=tmp_path / "p5-24-loop.db")
    service = create_workbench_service(settings)
    app = create_app(settings=settings, service=service)

    with TestClient(app) as client:
        catalog_response = client.get("/api/v1/projects")
        assert catalog_response.status_code == 200
        catalog = catalog_response.json()["data"]
        assert len(catalog) == 24
        assert len({item["projectId"] for item in catalog}) == 24

        connection = service.repository.raw_connection_for_tests()
        for catalog_item in catalog:
            project_id = catalog_item["projectId"]
            materials_response = client.get(f"/api/v1/projects/{project_id}/materials")
            workbench_response = client.get(f"/api/v1/projects/{project_id}/workbench")
            assert materials_response.status_code == workbench_response.status_code == 200
            materials = materials_response.json()["data"]
            workbench = workbench_response.json()["data"]
            assert len(materials) == len(workbench["materials"]) == workbench["project"]["materialCount"] == 56
            material_ids = {item["id"] for item in materials}
            versions = {item["versionId"] for item in materials}
            assert len(material_ids) == len(versions) == 56
            for dimension, categories in P5_MATERIAL_COVERAGE.items():
                for category in categories:
                    assert f"mat-{project_id}-{dimension}-{category}" in material_ids

            located_evidence = [item for item in workbench["evidence"] if item["locator"] is not None]
            assert material_ids <= {item["locator"]["materialId"] for item in located_evidence}
            assert all(item["locator"]["materialVersionId"] in versions for item in located_evidence)

            site = next(item for item in materials if item["id"].endswith("production-site"))
            intelligence_response = client.get(f"/api/v1/projects/{project_id}/materials/{site['id']}/intelligence/latest")
            scene_response = client.get(f"/api/v1/projects/{project_id}/materials/{site['id']}/scene-spec")
            assert intelligence_response.status_code == scene_response.status_code == 200
            intelligence = intelligence_response.json()["data"]
            scene = scene_response.json()["data"]
            anchors = intelligence["result"]["sourceAnchors"]
            anchor_ids = {anchor["id"] for anchor in anchors}
            assert anchors and all(anchor["materialId"] == site["id"] for anchor in anchors)
            assert all(anchor["materialVersionId"] == site["versionId"] for anchor in anchors)
            assert set(intelligence["evidenceRefs"]) == {f"ev-mi-{anchor_id}" for anchor_id in anchor_ids}
            assert scene["materialVersionId"] == site["versionId"]
            assert set(scene["sourceAnchorIds"]) == anchor_ids
            assert {item["regionId"] for item in scene["spec"]["objects"]} == {"factory", "equipment", "process"}
            assert all(item["sourceAnchorId"] in anchor_ids for item in scene["spec"]["hotspots"])
            assert connection.execute("SELECT COUNT(*) FROM materials WHERE project_id = ?", (project_id,)).fetchone()[0] == 56
            assert connection.execute("SELECT COUNT(*) FROM source_anchors WHERE project_id = ?", (project_id,)).fetchone()[0] >= 1
            assert connection.execute("SELECT COUNT(*) FROM scene_specs WHERE project_id = ?", (project_id,)).fetchone()[0] == 1


def test_complete_zip_version_rollover_keeps_workbench_valid_and_reviewable(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "runtimeqa-rollover.db",
        import_root=tmp_path / "imports",
    )
    service = create_workbench_service(settings)
    app = create_app(settings=settings, service=service)

    with TestClient(app) as client:
        catalog = client.get("/api/v1/projects").json()["data"]
        assert len(catalog) == 24
        project_id = catalog[0]["projectId"]
        isolated_project_id = catalog[1]["projectId"]
        seeded = client.get(f"/api/v1/projects/{project_id}/workbench")
        assert seeded.status_code == 200
        seeded_workbench = seeded.json()["data"]
        assert len(seeded_workbench["materials"]) == 56
        stale_evidence_ids = {
            item["id"]
            for item in seeded_workbench["evidence"]
            if item["locationStatus"] == "located"
        }
        assert stale_evidence_ids

        items = []
        archive_entries: dict[str, bytes] = {}
        for index, material in enumerate(seeded_workbench["materials"], start=1):
            source_name = f"originals/{material['businessPath']}"
            source_bytes = f"runtimeqa-controlled-v2::{material['id']}".encode()
            archive_entries[f"pack/{source_name}"] = source_bytes
            items.append(
                {
                    "materialId": material["id"],
                    "sourceFile": source_name,
                    "sha256": hashlib.sha256(source_bytes).hexdigest(),
                    "classification": "synthetic_demo",
                    "authorizationRef": "runtimeqa-controlled-v2",
                    "material": material,
                }
            )
        archive_entries["pack/manifest.json"] = json.dumps(
            {
                "manifestVersion": "1.0",
                "projectId": project_id,
                "items": items,
            },
            ensure_ascii=False,
        ).encode()
        archive = _zip_bytes(archive_entries)
        upload = client.post(
            f"/api/v1/projects/{project_id}/materials/uploads",
            content=archive,
            headers={"X-File-Name": "runtimeqa-complete-pack.zip"},
        )
        assert upload.status_code == 200, upload.text
        manifest_ref = upload.json()["data"]["manifestRef"]
        preflight = client.post(
            f"/api/v1/projects/{project_id}/materials/imports/preflight",
            json={"projectId": project_id, "manifestRef": manifest_ref},
        )
        assert preflight.status_code == 200
        assert len(preflight.json()["data"]["items"]) == 56
        assert {
            item["materialVersionId"].rsplit("-v", 1)[1]
            for item in preflight.json()["data"]["items"]
        } == {"2"}

        import_payload = {
            "projectId": project_id,
            "manifestRef": manifest_ref,
            "expectedVersion": 1,
        }
        imported = client.post(
            f"/api/v1/projects/{project_id}/materials/imports",
            headers={"Idempotency-Key": "runtimeqa-rollover-import-001"},
            json=import_payload,
        )
        assert imported.status_code == 200
        replayed = client.post(
            f"/api/v1/projects/{project_id}/materials/imports",
            headers={"Idempotency-Key": "runtimeqa-rollover-import-001"},
            json=import_payload,
        )
        assert replayed.status_code == 200
        assert replayed.json()["data"]["importId"] == imported.json()["data"]["importId"]

        current = client.get(f"/api/v1/projects/{project_id}/workbench")
        assert current.status_code == 200
        current_workbench = current.json()["data"]
        current_versions = {
            item["id"]: item["versionId"] for item in current_workbench["materials"]
        }
        assert all(version_id.endswith("-v2") for version_id in current_versions.values())
        evidence_by_id = {item["id"]: item for item in current_workbench["evidence"]}
        for evidence_id in stale_evidence_ids:
            evidence = evidence_by_id[evidence_id]
            assert evidence["locationStatus"] == "pending"
            assert evidence["materialStatus"] == "review"
            assert evidence["locator"] is None
        for evidence in current_workbench["evidence"]:
            if evidence["locationStatus"] == "located":
                locator = evidence["locator"]
                assert locator["materialVersionId"] == current_versions[locator["materialId"]]

        connection = service.repository.raw_connection_for_tests()
        stored_stale = connection.execute(
            """SELECT COUNT(*) FROM evidence_references
               WHERE project_id = ? AND location_status = 'located'
                 AND material_version_id LIKE '%-v1'""",
            (project_id,),
        ).fetchone()[0]
        assert stored_stale == len(stale_evidence_ids)
        assert connection.execute(
            "SELECT COUNT(*) FROM source_anchors WHERE project_id = ? AND material_version_id LIKE '%-v1'",
            (project_id,),
        ).fetchone()[0] >= 1
        service.data_pack.providers[ModelGatewayMode.SYNTHETIC] = (
            _ReviewableSyntheticCandidateProvider()
        )
        imported_material = next(
            item
            for item in current_workbench["materials"]
            if item["kind"] in {"excel", "pdf", "image", "media"}
            and "-compliance-" in item["id"]
        )
        intelligence = client.post(
            f"/api/v1/projects/{project_id}/materials/{imported_material['id']}/intelligence",
            headers={"Idempotency-Key": "runtimeqa-rollover-intelligence-001"},
            json={
                "projectId": project_id,
                "materialId": imported_material["id"],
                "materialVersionId": imported_material["versionId"],
                "contextVersion": "runtimeqa-rollover-v2",
                "taskGoals": ["observe", "extract_field_candidates"],
                "expectedVersion": 2,
            },
        )
        assert intelligence.status_code == 200
        candidate_id = intelligence.json()["data"]["candidateIds"][0]
        candidate = connection.execute(
            "SELECT field_key FROM extracted_fact_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        fact = connection.execute(
            """SELECT id, version FROM fact_versions
               WHERE project_id = ? AND fact_key = ? ORDER BY version DESC LIMIT 1""",
            (project_id, candidate["field_key"]),
        ).fetchone()
        confirmed = client.post(
            f"/api/v1/projects/{project_id}/candidates/{candidate_id}/confirm",
            headers={"Idempotency-Key": "runtimeqa-rollover-confirm-001"},
            json={
                "projectId": project_id,
                "candidateId": candidate_id,
                "fromFactVersionId": fact["id"],
                "expectedVersion": fact["version"],
                "reason": "人工核验 v2 synthetic 原件与 SourceAnchor 后确认。",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        confirmation = confirmed.json()["data"]
        assert confirmation["factVersion"]["version"] == fact["version"] + 1
        assert len(confirmation["policyResults"]) == 3
        assert confirmation["approval"]["hardGateStatus"] in {
            "pass",
            "manual_review",
            "block",
        }
        after_confirmation = client.get(f"/api/v1/projects/{project_id}/workbench")
        assert after_confirmation.status_code == 200
        assert any(
            item["locationStatus"] == "located"
            and item["locator"]["materialVersionId"] == imported_material["versionId"]
            for item in after_confirmation.json()["data"]["evidence"]
        )
        isolated = client.get(f"/api/v1/projects/{isolated_project_id}/workbench")
        assert isolated.status_code == 200
        assert all(
            item["versionId"].endswith("-v1")
            for item in isolated.json()["data"]["materials"]
        )

    service.close()
    restarted = create_workbench_service(settings)
    try:
        restarted_workbench = restarted.get_workbench(project_id)
        assert all(
            item.version_id.endswith("-v2")
            for item in restarted_workbench.materials
        )
        restarted_evidence = {
            item.id: item for item in restarted_workbench.evidence
        }
        assert all(
            restarted_evidence[evidence_id].location_status == "pending"
            and restarted_evidence[evidence_id].locator is None
            and restarted_evidence[evidence_id].material_status == "review"
            for evidence_id in stale_evidence_ids
        )
    finally:
        restarted.close()


def test_manifest_rejects_escape_hash_mismatch_and_path_body_mismatch(tmp_path) -> None:
    import_root = tmp_path / "authorized"
    import_root.mkdir()
    database = tmp_path / "invalid-import.db"
    settings = Settings(database_path=database, import_root=import_root)
    service = create_workbench_service(
        settings, generator=StaticGenerator(make_bundle("project-a"), identity="invalid-import-v1")
    )
    app = create_app(settings=settings, service=service)
    (import_root / "bad.json").write_text(json.dumps({
        "manifestVersion": "1.0", "projectId": "project-b", "items": [{
            "materialId": "bad-material", "sourceFile": "../secret.pdf",
            "sha256": "0" * 64, "classification": "synthetic_demo",
            "authorizationRef": "test-auth", "material": _excel_payload("bad-material"),
        }],
    }), encoding="utf-8")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/projects/project-a/materials/imports/preflight",
            json={"projectId": "project-a", "manifestRef": "bad.json"},
        )
        assert response.status_code == 422
        assert "secret" not in response.text


def test_controlled_manifest_accepts_all_frozen_material_carriers(tmp_path) -> None:
    import_root = tmp_path / "all-carriers"
    import_root.mkdir()
    kinds = ("excel", "pdf", "document", "image", "media")
    image_id = "project-a-import-image"
    items = []
    for kind in kinds:
        material_id = f"project-a-import-{kind}"
        source = import_root / _source_name_for(_carrier_payload(kind, material_id, image_id), kind)
        source.write_bytes(f"synthetic-{kind}".encode())
        items.append({
            "materialId": material_id, "sourceFile": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "classification": "synthetic_demo", "authorizationRef": "all-carriers-test",
            "material": _carrier_payload(kind, material_id, image_id),
        })
    (import_root / "all.json").write_text(json.dumps({
        "manifestVersion": "1.0", "projectId": "project-a", "items": items,
    }), encoding="utf-8")
    settings = Settings(database_path=tmp_path / "all-carriers.db", import_root=import_root)
    service = create_workbench_service(
        settings, generator=StaticGenerator(make_bundle("project-a"), identity="all-carriers-v1")
    )
    preflight = service.preflight_material_import(
        "project-a",
        ImportManifestRequest(projectId="project-a", manifestRef="all.json"),
    )
    assert {item.kind for item in preflight.items} == set(kinds)
    service.close()


def test_existing_p4_seed_is_append_only_upgraded_to_p5_pack(tmp_path) -> None:
    generated = generate_project_bundle(20260810, 0).to_mapping()
    full_workbench = deepcopy(generated["workbench"])
    old_workbench = deepcopy(full_workbench)
    allowed_materials = {item["id"] for item in old_workbench["materials"][:3]}
    allowed_evidence = {
        item["id"] for item in old_workbench["evidence"]
        if item["locator"] is None or item["locator"]["materialId"] in allowed_materials
    }

    def strip_p5_refs(value):
        if isinstance(value, dict):
            result = {key: strip_p5_refs(item) for key, item in value.items()}
            if "evidenceRefs" in result and isinstance(result["evidenceRefs"], list):
                result["evidenceRefs"] = [item for item in result["evidenceRefs"] if item in allowed_evidence]
            if "evidenceTargets" in result and isinstance(result["evidenceTargets"], list):
                result["evidenceTargets"] = [
                    item for item in result["evidenceTargets"]
                    if item.get("evidenceRef") in allowed_evidence
                ]
                target_fact_ids = list(dict.fromkeys(
                    item["factVersionId"]
                    for item in result["evidenceTargets"]
                    if item.get("factVersionId")
                ))
                if "factVersionIds" in result:
                    result["factVersionIds"] = target_fact_ids
                target_review_ids = list(dict.fromkeys(
                    item["reviewTargetId"]
                    for item in result["evidenceTargets"]
                    if item.get("reviewTargetId")
                ))
                if "reviewTargetId" in result:
                    result["reviewTargetId"] = (
                        target_review_ids[0] if len(target_review_ids) == 1 else None
                    )
                if "primaryTarget" in result and (result.get("primaryTarget") or {}).get("evidenceRef") not in allowed_evidence:
                    result["primaryTarget"] = result["evidenceTargets"][0] if result["evidenceTargets"] else None
            return result
        if isinstance(value, list):
            return [strip_p5_refs(item) for item in value]
        return value

    old_workbench = strip_p5_refs(old_workbench)
    old_workbench["materials"] = old_workbench["materials"][:3]
    old_workbench["evidence"] = [item for item in old_workbench["evidence"] if item["id"] in allowed_evidence]
    old_workbench["project"]["materialCount"] = 3
    base_image_id = old_workbench["materials"][2]["id"]
    for line in old_workbench["financedEquipment"]["lines"]:
        line["imageId"] = base_image_id
        line["imageIds"] = [base_image_id]
        line["nameplateMaterialId"] = None
        line["derivedModelRef"] = None
    for stage in old_workbench["productionStages"]:
        stage["imageIds"] = [base_image_id]
    old_workbench["onsiteAssets"] = [{
        "id": "p4-base-image", "label": "旧版设备图片", "kind": "image",
        "collectionStatus": "collected", "materialId": base_image_id,
        "sourceLabel": "旧版兼容", "evidenceRefs": [], "lazyLoad": True,
        "isSimulated": True,
    }]
    WorkbenchProject.model_validate(old_workbench)
    identity = "p4-to-p5-upgrade-test"
    old_bundle = GeneratedProjectBundle(
        catalog=generated["catalog"], workbench=old_workbench,
        dimension_series=tuple(generated["dimensionSeries"]),
    )
    full_bundle = GeneratedProjectBundle(
        catalog=generated["catalog"], workbench=full_workbench,
        dimension_series=tuple(generated["dimensionSeries"]),
    )
    settings = Settings(database_path=tmp_path / "upgrade.db")
    first = create_workbench_service(
        settings, generator=StaticGenerator(old_bundle, identity=identity)
    )
    project_id = generated["catalog"]["projectId"]
    assert len(first.list_materials(project_id)) == 3
    first.close()

    upgraded = create_workbench_service(
        settings, generator=StaticGenerator(full_bundle, identity=identity)
    )
    assert len(upgraded.list_materials(project_id)) == 56
    assert upgraded.get_workbench(project_id).project.material_count == 56
    connection = upgraded.repository.raw_connection_for_tests()
    assert connection.execute("SELECT COUNT(*) FROM material_source_records").fetchone()[0] == 56
    assert connection.execute("SELECT COUNT(*) FROM material_intelligence_runs").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM scene_specs").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM project_snapshots WHERE project_id = ?", (project_id,)).fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM audit_records WHERE project_id = ? AND action = 'p5_material_pack_upgraded'", (project_id,)).fetchone()[0] == 1
    upgraded.close()
