from __future__ import annotations

import struct
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.reconstruction import (
    CapturePoseSource,
    InputDataStatus,
    OverlapBasis,
    ReconstructionAsset,
    ReconstructionAssetDataStatus,
    ReconstructionAssetKind,
    ReconstructionAssetOrigin,
    ReconstructionClaim,
    ReconstructionErrorCode,
    ReconstructionImageInput,
    ReconstructionJobRequest,
    ReconstructionJobStatus,
    ReconstructionOverlap,
    ReconstructionPipeline,
    ReconstructionProviderInfo,
    ReconstructionQualityMetrics,
    ReconstructionQualityProfile,
    ReconstructionScaleReference,
    ReconstructionSubjectBinding,
    ReconstructionSubjectKind,
    ReconstructionTruthDeclaration,
    ReconstructionUnits,
    ScaleMode,
)
from app.repositories.reconstruction import (
    ReconstructionIdempotencyConflictError,
    ReconstructionNotFoundError,
    ReconstructionVersionConflictError,
    SqliteReconstructionRepository,
)
from app.services.reconstruction import (
    LocalReconstructionArtifactStore,
    ProviderArtifactPayload,
    ProviderReconstructionResult,
    ReconstructionProviderFailure,
    ReconstructionService,
)


def _image(index: int, count: int) -> ReconstructionImageInput:
    return ReconstructionImageInput(
        image_id=f"capture-{index:02d}",
        material_id=f"material-{index:02d}",
        material_version_id=f"material-{index:02d}-v1",
        content_hash=f"{index + 1:064x}",
        source_anchor_ids=[f"anchor-{index:02d}"],
        mime_type="image/jpeg",
        pixel_width=2400,
        pixel_height=1600,
        capture_order=index,
        azimuth_degrees=-180 + (360 * index / count),
        elevation_degrees=-20 if index % 2 == 0 else 25,
        pose_source=CapturePoseSource.OPERATOR_DECLARED,
        camera_id="camera-a",
    )


def _request(
    *,
    count: int = 12,
    pipeline: ReconstructionPipeline = ReconstructionPipeline.MULTI_VIEW,
    simulated: bool = True,
) -> ReconstructionJobRequest:
    images = [_image(index, count) for index in range(count)]
    overlaps = [
        ReconstructionOverlap(
            from_image_id=images[index].image_id,
            to_image_id=images[(index + 1) % count].image_id,
            estimated_overlap_percent=70,
            basis=OverlapBasis.OPERATOR_DECLARED,
        )
        for index in range(count)
    ] if count > 1 else []
    return ReconstructionJobRequest.model_validate(
        {
            "subject": {
                "subjectKind": "equipment",
                "subjectId": "equipment-line-01",
            },
            "pipeline": pipeline,
            "qualityProfile": "equipment_review_v1",
            "captureSet": {
                "images": [item.model_dump(mode="json", by_alias=True) for item in images],
                "overlaps": [item.model_dump(mode="json", by_alias=True) for item in overlaps],
                "scaleReference": {
                    "mode": "unknown",
                    "distanceMeters": None,
                    "sourceImageIds": [],
                },
                "siteFlowNodes": [],
            },
            "requestedOutputs": ["glb"],
            "truth": {
                "isSimulated": simulated,
                "dataStatus": "synthetic" if simulated else "captured_originals",
                "source": "de-identified reconstruction contract fixture",
                "disclaimer": "测试图组仅验证 orchestration，不代表真实客户扫描。",
            },
        }
    )


def _valid_glb() -> bytes:
    json_chunk = b"{}  "
    return struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(json_chunk)) + struct.pack(
        "<I4s", len(json_chunk), b"JSON"
    ) + json_chunk


def _site_request_without_flow() -> ReconstructionJobRequest:
    payload = _request(count=24).model_dump(mode="json", by_alias=True)
    payload["subject"] = {"subjectKind": "site", "subjectId": "site-01"}
    payload["qualityProfile"] = "site_process_v1"
    return ReconstructionJobRequest.model_validate(payload)


class _Provider:
    def __init__(self, *, quality_passes: bool = True) -> None:
        self.quality_passes = quality_passes

    def supports(self, pipeline: ReconstructionPipeline) -> bool:
        return pipeline == ReconstructionPipeline.MULTI_VIEW

    def reconstruct(
        self, job_id: str, request: ReconstructionJobRequest
    ) -> ProviderReconstructionResult:
        count = len(request.capture_set.images)
        return ProviderReconstructionResult(
            provider_info=ReconstructionProviderInfo(
                provider="test-only",
                engine="deterministic-contract-fixture",
                engine_version="1",
            ),
            origin=ReconstructionAssetOrigin.MULTI_VIEW_RECONSTRUCTION,
            metrics=ReconstructionQualityMetrics(
                input_image_count=count,
                registered_image_count=count if self.quality_passes else 2,
                registration_ratio=1 if self.quality_passes else 2 / count,
                median_reprojection_error_px=1 if self.quality_passes else 5,
                sparse_point_count=10_000 if self.quality_passes else 100,
                dense_point_count=100_000 if self.quality_passes else 500,
                mesh_face_count=20_000 if self.quality_passes else 50,
                coverage_percent=85 if self.quality_passes else 10,
                texture_coverage_percent=80 if self.quality_passes else 5,
                spatial_flow_coverage_percent=None,
                scale_mode=ScaleMode.UNKNOWN,
            ),
            artifacts=(
                ProviderArtifactPayload(
                    kind=ReconstructionAssetKind.GLB,
                    file_name="equipment.glb",
                    content=_valid_glb(),
                    units=ReconstructionUnits.UNSCALED,
                ),
            ),
            spatial_bindings=(),
            is_simulated=request.truth.is_simulated,
            source="test-only deterministic provider payload",
            disclaimer="模拟 provider 产物只验证 Job 与 Gate，不得标为真实扫描。",
        )


class _UnavailableProvider:
    def supports(self, pipeline: ReconstructionPipeline) -> bool:
        return True

    def reconstruct(
        self, job_id: str, request: ReconstructionJobRequest
    ) -> ProviderReconstructionResult:
        raise ReconstructionProviderFailure(
            ReconstructionErrorCode.PROVIDER_UNAVAILABLE,
            "test provider unavailable",
            retryable=True,
        )


class _PartiallyInvalidProvider(_Provider):
    def reconstruct(
        self, job_id: str, request: ReconstructionJobRequest
    ) -> ProviderReconstructionResult:
        result = super().reconstruct(job_id, request)
        return replace(
            result,
            artifacts=(
                result.artifacts[0],
                ProviderArtifactPayload(
                    kind=ReconstructionAssetKind.POINT_CLOUD_PLY,
                    file_name="equipment.ply",
                    content=b"not-a-ply",
                    units=ReconstructionUnits.UNSCALED,
                ),
            ),
        )


def _service(tmp_path: Path) -> tuple[ReconstructionService, SqliteReconstructionRepository]:
    repository = SqliteReconstructionRepository(tmp_path / "reconstruction.sqlite3")
    service = ReconstructionService(
        repository,
        LocalReconstructionArtifactStore(tmp_path / "artifacts"),
    )
    return service, repository


def test_input_gate_requires_multi_angle_connected_capture_set(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    try:
        job, replayed = service.create_job(
            "project-01", _request(count=3), idempotency_key="create-short"
        )
        assert replayed is False
        assert job.status == ReconstructionJobStatus.NEEDS_MORE_INPUT
        assert job.capture_gate.metrics.measurement_scope == "declared_metadata_only"
        assert {issue.code for issue in job.capture_gate.issues} >= {
            "image_count_below_minimum",
            "azimuth_coverage_insufficient",
        }
        assert job.assets == []
    finally:
        repository.close()


def test_ai_inferred_request_is_blocked_from_reconstruction_queue(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    try:
        job, _ = service.create_job(
            "project-01",
            _request(count=1, pipeline=ReconstructionPipeline.AI_INFERRED),
            idempotency_key="create-ai",
        )
        assert job.status == ReconstructionJobStatus.BLOCKED
        assert job.capture_gate.status == "not_reconstruction"
        assert job.error is not None
        assert job.error.code == ReconstructionErrorCode.AI_INFERRED_NOT_RECONSTRUCTION
        assert job.assets == []
    finally:
        repository.close()


def test_site_gate_requires_raw_to_finished_spatial_chain(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    try:
        job, _ = service.create_job(
            "project-01",
            _site_request_without_flow(),
            idempotency_key="create-site-without-flow",
        )
        assert job.status == ReconstructionJobStatus.NEEDS_MORE_INPUT
        assert "site_flow_chain_incomplete" in {
            issue.code for issue in job.capture_gate.issues
        }
    finally:
        repository.close()


def test_create_is_idempotent_and_rejects_key_reuse_with_new_payload(
    tmp_path: Path,
) -> None:
    service, repository = _service(tmp_path)
    try:
        request = _request()
        first, first_replayed = service.create_job(
            "project-01", request, idempotency_key="create-01"
        )
        replay, replayed = service.create_job(
            "project-01", request, idempotency_key="create-01"
        )
        assert first_replayed is False
        assert replayed is True
        assert replay.job_id == first.job_id

        changed = request.model_copy(
            update={
                "requested_outputs": [
                    ReconstructionAssetKind.GLB,
                    ReconstructionAssetKind.POINT_CLOUD_PLY,
                ]
            }
        )
        with pytest.raises(ReconstructionIdempotencyConflictError):
            service.create_job(
                "project-01", changed, idempotency_key="create-01"
            )
    finally:
        repository.close()


def test_success_exposes_only_gate_passed_simulated_asset(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    try:
        created, _ = service.create_job(
            "project-01", _request(), idempotency_key="create-success"
        )
        assert created.status == ReconstructionJobStatus.QUEUED
        completed = service.run_job("project-01", created.job_id, _Provider())
        assert completed.status == ReconstructionJobStatus.SUCCEEDED
        assert completed.output_quality_gate is not None
        assert completed.output_quality_gate.passed is True
        assert len(completed.assets) == 1
        asset = completed.assets[0]
        assert asset.is_simulated is True
        assert asset.data_status == ReconstructionAssetDataStatus.SYNTHETIC
        assert asset.claim == ReconstructionClaim.SIMULATED_NOT_SCAN
        stored = service.artifact_store.resolve_for_read(asset.storage_key)
        assert stored.read_bytes() == _valid_glb()
        assert [event["eventKind"] for event in repository.list_events(
            "project-01", created.job_id
        )] == [
            "job_created",
            "job_started",
            "quality_gate_evaluated",
            "job_succeeded",
        ]
    finally:
        repository.close()


def test_failed_quality_gate_publishes_no_asset(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    try:
        created, _ = service.create_job(
            "project-01", _request(), idempotency_key="create-low-quality"
        )
        failed = service.run_job(
            "project-01", created.job_id, _Provider(quality_passes=False)
        )
        assert failed.status == ReconstructionJobStatus.FAILED
        assert failed.error is not None
        assert failed.error.code == ReconstructionErrorCode.QUALITY_GATE_FAILED
        assert failed.assets == []
        assert not list((tmp_path / "artifacts").rglob("*.glb"))
    finally:
        repository.close()


def test_partial_asset_write_is_removed_when_later_artifact_is_invalid(
    tmp_path: Path,
) -> None:
    service, repository = _service(tmp_path)
    try:
        request = _request().model_copy(
            update={
                "requested_outputs": [
                    ReconstructionAssetKind.GLB,
                    ReconstructionAssetKind.POINT_CLOUD_PLY,
                ]
            }
        )
        created, _ = service.create_job(
            "project-01", request, idempotency_key="create-partial-invalid"
        )
        failed = service.run_job(
            "project-01", created.job_id, _PartiallyInvalidProvider()
        )
        assert failed.status == ReconstructionJobStatus.FAILED
        assert failed.error is not None
        assert failed.error.code == ReconstructionErrorCode.INVALID_PROVIDER_OUTPUT
        assert failed.assets == []
        assert not [path for path in (tmp_path / "artifacts").rglob("*") if path.is_file()]
    finally:
        repository.close()


def test_retry_is_versioned_and_idempotent(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    try:
        created, _ = service.create_job(
            "project-01", _request(), idempotency_key="create-retry"
        )
        failed = service.run_job("project-01", created.job_id, _UnavailableProvider())
        assert failed.status == ReconstructionJobStatus.FAILED
        assert failed.error is not None and failed.error.retryable is True

        queued, replayed = service.retry_job(
            "project-01",
            failed.job_id,
            expected_version=failed.version,
            idempotency_key="retry-01",
        )
        replay, second_replayed = service.retry_job(
            "project-01",
            failed.job_id,
            expected_version=failed.version,
            idempotency_key="retry-01",
        )
        assert replayed is False
        assert second_replayed is True
        assert queued.status == ReconstructionJobStatus.QUEUED
        assert replay.version == queued.version
    finally:
        repository.close()


def test_sqlite_restart_project_isolation_and_optimistic_version(
    tmp_path: Path,
) -> None:
    database = tmp_path / "restart.sqlite3"
    artifacts = tmp_path / "artifacts"
    first_repository = SqliteReconstructionRepository(database)
    service = ReconstructionService(
        first_repository, LocalReconstructionArtifactStore(artifacts)
    )
    created, _ = service.create_job(
        "project-01", _request(), idempotency_key="restart-create"
    )
    first_repository.close()

    repository = SqliteReconstructionRepository(database)
    try:
        restored = repository.get_job("project-01", created.job_id)
        assert restored.request_hash == created.request_hash
        with pytest.raises(ReconstructionNotFoundError):
            repository.get_job("project-02", created.job_id)

        payload = restored.model_dump(mode="python")
        payload.update({"version": 2})
        version_two = type(restored).model_validate(payload)
        repository.transition_job(
            version_two, expected_version=1, event_kind="worker_lease_refreshed"
        )
        with pytest.raises(ReconstructionVersionConflictError):
            repository.transition_job(
                version_two, expected_version=1, event_kind="stale_worker_update"
            )
    finally:
        repository.close()


def test_asset_contract_cannot_label_ai_inference_as_reconstruction() -> None:
    with pytest.raises(ValidationError):
        ReconstructionAsset(
            asset_id="asset-ai",
            project_id="project-01",
            job_id="job-01",
            kind=ReconstructionAssetKind.GLB,
            mime_type="model/gltf-binary",
            file_name="inferred.glb",
            storage_key="project-01/job-01/asset-ai/inferred.glb",
            byte_size=12,
            content_hash="a" * 64,
            coordinate_system="local_cartesian_y_up",
            units=ReconstructionUnits.UNSCALED,
            origin=ReconstructionAssetOrigin.AI_INFERRED_GENERATION,
            claim=ReconstructionClaim.MULTI_VIEW_RECONSTRUCTION,
            quality_gate_passed=True,
            consumer_ready=True,
            is_simulated=False,
            data_status=ReconstructionAssetDataStatus.RECONSTRUCTED,
            source="future AI provider",
            disclaimer="AI 推测资产不是扫描。",
        )
