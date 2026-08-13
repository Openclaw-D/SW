from __future__ import annotations

import struct
from pathlib import Path

from fastapi.testclient import TestClient

from app.contracts.reconstruction import (
    ReconstructionAssetKind,
    ReconstructionAssetOrigin,
    ReconstructionEngineStatus,
    ReconstructionPipeline,
    ReconstructionProviderInfo,
    ReconstructionQualityMetrics,
    ReconstructionSpatialBinding,
    ReconstructionUnits,
    ScaleMode,
)
from app.core.config import Settings
from app.main import create_app
from app.providers.local_reconstruction import (
    LocalEngineDiscovery,
    UnavailableLocalReconstructionProvider,
)
from app.services.reconstruction import (
    ProviderArtifactPayload,
    ProviderReconstructionResult,
)


def _payload() -> dict[str, object]:
    images = [
        {
            "imageId": f"capture-{index:02d}",
            "materialId": f"material-{index:02d}",
            "materialVersionId": f"material-{index:02d}-v1",
            "contentHash": f"{index + 1:064x}",
            "sourceAnchorIds": [f"anchor-{index:02d}"],
            "mimeType": "image/jpeg",
            "pixelWidth": 2400,
            "pixelHeight": 1600,
            "captureOrder": index,
            "azimuthDegrees": -180 + 30 * index,
            "elevationDegrees": -20 if index % 2 == 0 else 25,
            "poseSource": "operator_declared",
        }
        for index in range(12)
    ]
    return {
        "subject": {"subjectKind": "equipment", "subjectId": "equipment-line-01"},
        "pipeline": "multi_view_reconstruction",
        "qualityProfile": "equipment_review_v1",
        "captureSet": {
            "images": images,
            "overlaps": [
                {
                    "fromImageId": images[index]["imageId"],
                    "toImageId": images[(index + 1) % len(images)]["imageId"],
                    "estimatedOverlapPercent": 70,
                    "basis": "operator_declared",
                }
                for index in range(len(images))
            ],
            "scaleReference": {"mode": "unknown", "sourceImageIds": []},
            "siteFlowNodes": [],
        },
        "requestedOutputs": ["glb"],
        "truth": {
            "isSimulated": True,
            "dataStatus": "synthetic",
            "source": "de-identified API fixture",
            "disclaimer": "只验证本地重建 Job API，不代表照片扫描。",
        },
    }


def _valid_glb() -> bytes:
    json_chunk = b"{}  "
    return struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(json_chunk)) + struct.pack(
        "<I4s", len(json_chunk), b"JSON"
    ) + json_chunk


class FixtureProvider:
    def supports(self, pipeline: ReconstructionPipeline) -> bool:
        return pipeline == ReconstructionPipeline.MULTI_VIEW

    def status(self) -> ReconstructionEngineStatus:
        return ReconstructionEngineStatus(
            engine="test-controlled-fixture",
            available=True,
            supportsMultiView=True,
            detail="仅用于隔离测试的受控 fixture，不是本机照片重建引擎。",
            disclaimer="不联网，不读取项目原图，不代表真实重建。",
        )

    def reconstruct(self, job_id: str, request):
        count = len(request.capture_set.images)
        return ProviderReconstructionResult(
            provider_info=ReconstructionProviderInfo(
                provider="test-only", engine="controlled-fixture", engine_version="1"
            ),
            origin=ReconstructionAssetOrigin.MULTI_VIEW_RECONSTRUCTION,
            metrics=ReconstructionQualityMetrics(
                input_image_count=count,
                registered_image_count=count,
                registration_ratio=1,
                median_reprojection_error_px=1,
                sparse_point_count=10_000,
                dense_point_count=100_000,
                mesh_face_count=20_000,
                coverage_percent=85,
                texture_coverage_percent=80,
                scale_mode=ScaleMode.UNKNOWN,
            ),
            artifacts=(
                ProviderArtifactPayload(
                    kind=ReconstructionAssetKind.GLB,
                    file_name="controlled-fixture.glb",
                    content=_valid_glb(),
                    units=ReconstructionUnits.UNSCALED,
                ),
            ),
            spatial_bindings=tuple[ReconstructionSpatialBinding, ...](),
            is_simulated=True,
            source="controlled reconstruction API fixture",
            disclaimer="模拟 fixture 的 GLB 不得称为客户照片重建。",
        )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "workbench.sqlite3",
        reconstruction_database_path=tmp_path / "reconstruction.sqlite3",
        reconstruction_asset_root=tmp_path / "reconstruction-assets",
    )


def test_no_engine_status_and_create_are_explicitly_unavailable(tmp_path: Path) -> None:
    provider = UnavailableLocalReconstructionProvider(LocalEngineDiscovery(engine=None))
    with TestClient(create_app(_settings(tmp_path), reconstruction_provider=provider)) as client:
        status = client.get("/api/v1/reconstruction/engine-status")
        assert status.status_code == 200
        assert status.json()["data"]["available"] is False

        headers = {"Idempotency-Key": "reconstruction-create-unavailable-01"}
        created = client.post(
            "/api/v1/projects/project-01/reconstruction/jobs", json=_payload(), headers=headers
        )
        assert created.status_code == 200
        job = created.json()["data"]
        assert job["status"] == "unavailable"
        assert job["error"]["code"] == "provider_not_configured"
        assert job["assets"] == []

        replay = client.post(
            "/api/v1/projects/project-01/reconstruction/jobs", json=_payload(), headers=headers
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["jobId"] == job["jobId"]

        retried = client.post(
            f"/api/v1/projects/project-01/reconstruction/jobs/{job['jobId']}/retry",
            json={"expectedVersion": job["version"]},
            headers={"Idempotency-Key": "reconstruction-retry-unavailable-01"},
        )
        assert retried.status_code == 200
        assert retried.json()["data"]["status"] == "unavailable"


def test_controlled_fixture_is_the_only_success_path_and_asset_is_project_isolated(
    tmp_path: Path,
) -> None:
    with TestClient(
        create_app(_settings(tmp_path), reconstruction_provider=FixtureProvider())
    ) as client:
        created = client.post(
            "/api/v1/projects/project-01/reconstruction/jobs",
            json=_payload(),
            headers={"Idempotency-Key": "reconstruction-create-fixture-01"},
        )
        assert created.status_code == 200
        job = created.json()["data"]
        assert job["status"] == "succeeded", job["error"]
        assert job["assets"][0]["dataStatus"] == "synthetic"
        assert job["assets"][0]["claim"] == "simulated_not_scan"

        asset = job["assets"][0]
        downloaded = client.get(
            f"/api/v1/projects/project-01/reconstruction/jobs/{job['jobId']}/assets/{asset['assetId']}"
        )
        assert downloaded.status_code == 200
        assert downloaded.content == _valid_glb()
        assert client.get(
            f"/api/v1/projects/project-02/reconstruction/jobs/{job['jobId']}"
        ).status_code == 404
        latest = client.get(
            "/api/v1/projects/project-01/reconstruction/subjects/equipment/equipment-line-01/latest"
        )
        assert latest.status_code == 200
        assert latest.json()["data"]["jobId"] == job["jobId"]


def test_api_rejects_path_url_and_payload_smuggling_and_openapi_labels_jobs(tmp_path: Path) -> None:
    with TestClient(
        create_app(
            _settings(tmp_path),
            reconstruction_provider=UnavailableLocalReconstructionProvider(LocalEngineDiscovery(None)),
        )
    ) as client:
        unsafe = _payload()
        unsafe["captureSet"]["images"][0]["imageId"] = "https://untrusted.example/photo.jpg"  # type: ignore[index]
        response = client.post(
            "/api/v1/projects/project-01/reconstruction/jobs",
            json=unsafe,
            headers={"Idempotency-Key": "reconstruction-unsafe-url-01"},
        )
        assert response.status_code == 422

        smuggled = _payload()
        smuggled["captureSet"]["images"][0]["base64"] = "AAAA"  # type: ignore[index]
        response = client.post(
            "/api/v1/projects/project-01/reconstruction/jobs",
            json=smuggled,
            headers={"Idempotency-Key": "reconstruction-smuggled-binary-01"},
        )
        assert response.status_code == 422

        schema = client.app.openapi()
        create_operation = schema["paths"]["/api/v1/projects/{projectId}/reconstruction/jobs"]["post"]
        assert create_operation["operationId"] == "createImageTo3dReconstructionJob"
        assert "Idempotency-Key" in {item["name"] for item in create_operation["parameters"]}
