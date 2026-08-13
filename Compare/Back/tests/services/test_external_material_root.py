from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.generator_adapter import GeneratedProjectBundle
from app.services.workbench import create_workbench_service
from tests.services.fixtures import StaticGenerator, make_bundle


def _external_pack(tmp_path, bundle: GeneratedProjectBundle) -> tuple[object, dict, bytes]:
    archive_root = tmp_path / "archive-root"
    pack_root = archive_root / "native-material-packs" / "project-01"
    pack_root.mkdir(parents=True)
    material = bundle.workbench["materials"][0]
    source = b"controlled external material fixture"
    source_name = "originals/fixture.xlsx"
    target = pack_root / source_name
    target.parent.mkdir()
    target.write_bytes(source)
    (pack_root / "manifest.json").write_text(
        json.dumps(
            {
                "manifestVersion": "1.0",
                "projectId": "project-a",
                "items": [
                    {
                        "materialId": material["id"],
                        "sourceFile": source_name,
                        "sha256": hashlib.sha256(source).hexdigest(),
                        "classification": "synthetic_demo",
                        "authorizationRef": "external-root-test",
                        "material": material,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return archive_root, material, source


def test_external_root_serves_only_manifest_bound_project_originals_without_writes(tmp_path) -> None:
    bundle = make_bundle("project-a")
    archive_root, material, source = _external_pack(tmp_path, bundle)
    settings = Settings(
        database_path=tmp_path / "external.db",
        import_root=archive_root / "native-material-packs",
        material_root=archive_root,
    )
    service = create_workbench_service(
        settings,
        generator=StaticGenerator(
            bundle, make_bundle("project-b"), identity="external-root-v1"
        ),
    )
    with TestClient(create_app(settings=settings, service=service)) as client:
        listed = client.get("/api/v1/projects/project-a/materials")
        assert listed.status_code == 200
        listed_material = next(
            item for item in listed.json()["data"] if item["id"] == material["id"]
        )
        assert listed_material["originalAccess"] == {"status": "available", "available": True}
        assert client.get("/api/v1/projects/project-b/workbench").status_code == 200
        writes_before = service.repository.raw_connection_for_tests().total_changes
        original = client.get(
            f"/api/v1/projects/project-a/materials/{material['id']}/original"
        )
        assert original.status_code == 200 and original.content == source
        assert original.headers["content-type"].startswith(material["mimeType"])
        assert original.headers["cache-control"] == "private, no-store"
        assert client.get(
            f"/api/v1/projects/project-a/materials/{material['id']}/original",
            headers={"Range": "bytes=0-5"},
        ).status_code == 206
        # A second known material has no external manifest binding, so no
        # arbitrary archive file is discoverable through this API.
        unimported = bundle.workbench["materials"][1]["id"]
        missing = client.get(
            f"/api/v1/projects/project-a/materials/{unimported}/original"
        )
        assert missing.status_code == 404
        assert missing.json()["errors"][0]["code"] == "material_original_not_imported"
        cross_project = client.get(
            f"/api/v1/projects/project-b/materials/{material['id']}/original"
        )
        assert cross_project.status_code == 404
        assert "archive-root" not in cross_project.text
        assert service.repository.raw_connection_for_tests().total_changes == writes_before
    service.close()


def test_no_or_invalid_external_root_is_explicit_and_does_not_fall_back(tmp_path, monkeypatch) -> None:
    bundle = make_bundle("project-a")
    archive_root, material, _source = _external_pack(tmp_path, bundle)
    settings = Settings(
        database_path=tmp_path / "no-root.db",
        import_root=archive_root / "native-material-packs",
    )
    service = create_workbench_service(
        settings, generator=StaticGenerator(bundle, identity="no-external-root-v1")
    )
    with TestClient(create_app(settings=settings, service=service)) as client:
        access = next(
            item for item in client.get("/api/v1/projects/project-a/materials").json()["data"]
            if item["id"] == material["id"]
        )["originalAccess"]
        assert access == {"status": "not_configured", "available": False}
        response = client.get(
            f"/api/v1/projects/project-a/materials/{material['id']}/original"
        )
        assert response.status_code == 503
        assert response.json()["errors"][0]["code"] == "material_root_not_configured"
        assert client.get("/api/v1/projects/project-a/workbench").status_code == 200
    service.close()

    monkeypatch.setenv("COMPARE_MATERIAL_ROOT", "relative/archive")
    invalid = Settings.from_environment()
    assert invalid.material_root is None and invalid.material_root_config_invalid is True


def test_external_root_rejects_manifest_path_escape_without_disclosing_paths(tmp_path) -> None:
    archive_root = tmp_path / "archive-root"
    pack_root = archive_root / "native-material-packs" / "project-01"
    pack_root.mkdir(parents=True)
    (archive_root / "secret.xlsx").write_bytes(b"must not be served")
    material = make_bundle("project-a").workbench["materials"][0]
    (pack_root / "manifest.json").write_text(
        json.dumps(
            {
                "manifestVersion": "1.0",
                "projectId": "project-a",
                "items": [{
                    "materialId": material["id"], "sourceFile": "../secret.xlsx",
                    "sha256": hashlib.sha256(b"must not be served").hexdigest(),
                    "classification": "synthetic_demo", "authorizationRef": "test",
                    "material": material,
                }],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        database_path=tmp_path / "escape.db",
        import_root=tmp_path / "empty-import-root",
        material_root=archive_root,
    )
    service = create_workbench_service(
        settings,
        generator=StaticGenerator(make_bundle("project-a"), identity="escape-root-v1"),
    )
    with TestClient(create_app(settings=settings, service=service)) as client:
        response = client.get(
            f"/api/v1/projects/project-a/materials/{material['id']}/original"
        )
        assert response.status_code == 503
        assert response.json()["errors"][0]["code"] == "material_root_invalid"
        assert "secret.xlsx" not in response.text and "archive-root" not in response.text
    service.close()
