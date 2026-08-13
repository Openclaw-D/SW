from __future__ import annotations

import hashlib
import json
import os
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.contracts.reconstruction import (
    CaptureGateMetrics,
    CaptureGateReport,
    CaptureGateStatus,
    OutputQualityGateReport,
    RECONSTRUCTION_DISCLAIMER,
    ReconstructionAsset,
    ReconstructionAssetDataStatus,
    ReconstructionAssetKind,
    ReconstructionAssetOrigin,
    ReconstructionClaim,
    ReconstructionError,
    ReconstructionErrorCode,
    ReconstructionGateIssue,
    ReconstructionJob,
    ReconstructionJobRequest,
    ReconstructionJobStatus,
    ReconstructionPipeline,
    ReconstructionProgress,
    ReconstructionProviderInfo,
    ReconstructionProviderPort,
    ReconstructionQualityMetrics,
    ReconstructionQualityProfile,
    ReconstructionSpatialBinding,
    ReconstructionStage,
    ReconstructionSubjectKind,
    ReconstructionUnits,
    ScaleMode,
    SiteFlowNodeKind,
)
from app.repositories.reconstruction import SqliteReconstructionRepository


CAPTURE_GATE_DISCLAIMER = (
    "输入 Gate 只核对材料版本、声明角度和声明重叠关系，不等于已完成特征匹配、"
    "相机位姿求解或几何质量验证；真实覆盖度必须由重建引擎输出 Gate 再确认。"
)
MAX_RECONSTRUCTION_ARTIFACT_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class ProviderArtifactPayload:
    kind: ReconstructionAssetKind
    file_name: str
    content: bytes
    coordinate_system: str = "local_cartesian_y_up"
    units: ReconstructionUnits = ReconstructionUnits.UNSCALED


@dataclass(frozen=True)
class ProviderReconstructionResult:
    provider_info: ReconstructionProviderInfo
    origin: ReconstructionAssetOrigin
    metrics: ReconstructionQualityMetrics
    artifacts: tuple[ProviderArtifactPayload, ...]
    spatial_bindings: tuple[ReconstructionSpatialBinding, ...]
    is_simulated: bool
    source: str
    disclaimer: str


class ReconstructionServiceError(RuntimeError):
    pass


class ReconstructionStateError(ReconstructionServiceError):
    pass


class ReconstructionProviderFailure(ReconstructionServiceError):
    def __init__(
        self,
        code: ReconstructionErrorCode,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        if code not in {
            ReconstructionErrorCode.PROVIDER_NOT_CONFIGURED,
            ReconstructionErrorCode.PROVIDER_UNAVAILABLE,
            ReconstructionErrorCode.PROVIDER_TIMEOUT,
        }:
            raise ValueError("provider failures must use a provider error code")
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LocalReconstructionArtifactStore:
    """Atomic, repo-external artifact storage with strict relative keys."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        *,
        job: ReconstructionJob,
        result: ProviderReconstructionResult,
        payload: ProviderArtifactPayload,
    ) -> ReconstructionAsset:
        _validate_artifact_payload(payload)
        asset_id = f"recon-asset-{uuid.uuid4().hex}"
        storage_key = f"{job.project_id}/{job.job_id}/{asset_id}/{payload.file_name}"
        target = self._target_for_storage_key(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
        try:
            temporary.write_bytes(payload.content)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

        data_status, claim = _asset_truth(result)
        return ReconstructionAsset(
            asset_id=asset_id,
            project_id=job.project_id,
            job_id=job.job_id,
            kind=payload.kind,
            mime_type=_mime_type(payload.kind),
            file_name=payload.file_name,
            storage_key=storage_key,
            byte_size=len(payload.content),
            content_hash=hashlib.sha256(payload.content).hexdigest(),
            coordinate_system="local_cartesian_y_up",
            units=payload.units,
            origin=result.origin,
            claim=claim,
            quality_gate_passed=True,
            consumer_ready=True,
            is_simulated=result.is_simulated,
            data_status=data_status,
            source=result.source,
            disclaimer=result.disclaimer,
            spatial_bindings=(
                list(result.spatial_bindings)
                if payload.kind == ReconstructionAssetKind.GLB
                else []
            ),
        )

    def resolve_for_read(self, storage_key: str) -> Path:
        if (
            not storage_key
            or storage_key.startswith("/")
            or "\\" in storage_key
            or ":" in storage_key
            or any(part in {"", ".", ".."} for part in storage_key.split("/"))
        ):
            raise ReconstructionServiceError("invalid reconstruction storage key")
        target = self._target_for_storage_key(storage_key)
        if not target.is_file():
            raise ReconstructionServiceError("reconstruction artifact not found")
        return target

    def delete_unpublished(self, asset: ReconstructionAsset) -> None:
        """Remove one exact newly-written artifact after a failed publish."""

        target = self._target_for_storage_key(asset.storage_key)
        target.unlink(missing_ok=True)

    def _target_for_storage_key(self, storage_key: str) -> Path:
        if (
            not storage_key
            or storage_key.startswith("/")
            or "\\" in storage_key
            or ":" in storage_key
            or any(part in {"", ".", ".."} for part in storage_key.split("/"))
        ):
            raise ReconstructionServiceError("invalid reconstruction storage key")
        # Preserve the readable storage key in API provenance, but hash physical
        # directories so a deep project/job/asset chain remains below Windows
        # path limits and cannot be traversed through an identifier.
        project_id, job_id, asset_id, file_name = storage_key.split("/", 3)
        job_digest = hashlib.sha256(f"{project_id}/{job_id}".encode()).hexdigest()
        asset_digest = hashlib.sha256(asset_id.encode()).hexdigest()
        target = (self.root / job_digest[:16] / asset_digest[:16] / file_name).resolve()
        if self.root not in target.parents:
            raise ReconstructionServiceError("artifact path escaped configured root")
        return target


class ReconstructionService:
    """Provider-neutral job orchestration without any authority-chain writes."""

    def __init__(
        self,
        repository: SqliteReconstructionRepository,
        artifact_store: LocalReconstructionArtifactStore,
        *,
        max_attempts: int = 3,
    ) -> None:
        if not 1 <= max_attempts <= 5:
            raise ValueError("maxAttempts must be between 1 and 5")
        self.repository = repository
        self.artifact_store = artifact_store
        self.max_attempts = max_attempts

    def create_job(
        self,
        project_id: str,
        request: ReconstructionJobRequest,
        *,
        idempotency_key: str,
    ) -> tuple[ReconstructionJob, bool]:
        _require_identifier(project_id, "projectId")
        request_hash = canonical_request_hash(request)
        capture_gate = assess_capture_gate(request)
        now = _utc_now()

        error: ReconstructionError | None = None
        if capture_gate.status == CaptureGateStatus.PASSED:
            status = ReconstructionJobStatus.QUEUED
            progress = ReconstructionProgress(
                stage=ReconstructionStage.QUEUED,
                percent=0,
                message="输入覆盖 Gate 已通过，等待已配置的重建 worker。",
            )
        elif capture_gate.status == CaptureGateStatus.NEEDS_MORE_INPUT:
            status = ReconstructionJobStatus.NEEDS_MORE_INPUT
            progress = ReconstructionProgress(
                stage=ReconstructionStage.INPUT_GATE,
                percent=0,
                message="输入图组未达到最低覆盖要求，需要补拍或补充关联信息。",
            )
        else:
            status = ReconstructionJobStatus.BLOCKED
            progress = ReconstructionProgress(
                stage=ReconstructionStage.INPUT_GATE,
                percent=0,
                message="AI 推测式生成已与真实多视角重建分流。",
            )
            error = ReconstructionError(
                code=ReconstructionErrorCode.AI_INFERRED_NOT_RECONSTRUCTION,
                message=(
                    "该请求属于 AI inferred generation，不能进入扫描/重建队列；"
                    "未来可由独立生成 provider 处理，但资产必须保持 inferred_not_scan。"
                ),
                retryable=False,
                stage=ReconstructionStage.INPUT_GATE,
            )

        job = ReconstructionJob(
            job_id=f"recon-job-{uuid.uuid4().hex}",
            project_id=project_id,
            request_hash=request_hash,
            request=request,
            status=status,
            progress=progress,
            capture_gate=capture_gate,
            error=error,
            attempt=0,
            max_attempts=self.max_attempts,
            version=1,
            created_at=now,
            updated_at=now,
        )
        return self.repository.create_job(job, idempotency_key=idempotency_key)

    def get_job(self, project_id: str, job_id: str) -> ReconstructionJob:
        return self.repository.get_job(project_id, job_id)

    def get_asset(self, project_id: str, job_id: str, asset_id: str) -> ReconstructionAsset:
        job = self.repository.get_job(project_id, job_id)
        if job.status != ReconstructionJobStatus.SUCCEEDED:
            raise ReconstructionStateError("only succeeded jobs expose derived assets")
        for asset in job.assets:
            if asset.asset_id == asset_id:
                return asset
        raise ReconstructionStateError("reconstruction asset does not belong to this job")

    def get_latest_succeeded_job(
        self, project_id: str, subject_kind: str, subject_id: str
    ) -> ReconstructionJob | None:
        return self.repository.get_latest_succeeded_job(
            project_id, subject_kind, subject_id
        )

    def recover_interrupted_jobs(self) -> int:
        """Fail stale in-process work after a restart; callers may retry it safely."""

        recovered = 0
        for job in self.repository.list_interrupted_jobs():
            try:
                self._fail_running_job(
                    job,
                    code=ReconstructionErrorCode.PROVIDER_UNAVAILABLE,
                    message="服务重启时发现未完成的 worker；没有发布任何资产，可使用新幂等键重试。",
                    retryable=True,
                )
            except Exception:
                # Another worker may have completed it between the snapshot and
                # transition; optimistic versioning is the concurrency guard.
                continue
            recovered += 1
        return recovered

    def run_job(
        self,
        project_id: str,
        job_id: str,
        provider: ReconstructionProviderPort,
    ) -> ReconstructionJob:
        job = self.repository.get_job(project_id, job_id)
        if job.status != ReconstructionJobStatus.QUEUED:
            raise ReconstructionStateError("only queued jobs may run")
        if not provider.supports(job.request.pipeline):
            return self._fail_without_start(
                job,
                code=ReconstructionErrorCode.PROVIDER_NOT_CONFIGURED,
                message="本机没有可用且已配置的多视角重建引擎；未生成任何三维资产。",
                retryable=True,
            )

        running = _updated_job(
            job,
            status=ReconstructionJobStatus.RUNNING,
            progress=ReconstructionProgress(
                stage=ReconstructionStage.FEATURE_MATCHING,
                percent=10,
                message="worker 已领取任务；尚未通过输出质量 Gate。",
            ),
            attempt=job.attempt + 1,
            version=job.version + 1,
            updated_at=_utc_now(),
        )
        running, _ = self.repository.transition_job(
            running,
            expected_version=job.version,
            event_kind="job_started",
        )

        try:
            result = provider.reconstruct(running.job_id, running.request)
            _validate_provider_result(running.request, result)
        except ReconstructionProviderFailure as exc:
            code = exc.code
            retryable = exc.retryable and running.attempt < running.max_attempts
            if exc.retryable and not retryable:
                code = ReconstructionErrorCode.ATTEMPTS_EXHAUSTED
            return self._fail_running_job(
                running,
                code=code,
                message=str(exc),
                retryable=retryable,
            )
        except Exception as exc:
            return self._fail_running_job(
                running,
                code=ReconstructionErrorCode.INVALID_PROVIDER_OUTPUT,
                message=f"重建 provider 输出未通过契约校验：{exc}",
                retryable=False,
            )

        output_gate = assess_output_quality(running.request, result.metrics)
        reviewing = _updated_job(
            running,
            status=ReconstructionJobStatus.QUALITY_REVIEW,
            progress=ReconstructionProgress(
                stage=ReconstructionStage.QUALITY_GATE,
                percent=90,
                message="重建计算已返回，正在执行输出覆盖与几何质量 Gate。",
            ),
            output_quality_gate=output_gate,
            provider_info=result.provider_info,
            version=running.version + 1,
            updated_at=_utc_now(),
        )
        reviewing, _ = self.repository.transition_job(
            reviewing,
            expected_version=running.version,
            event_kind="quality_gate_evaluated",
        )
        if not output_gate.passed:
            return self._fail_running_job(
                reviewing,
                code=ReconstructionErrorCode.QUALITY_GATE_FAILED,
                message="重建结果未达到输出质量 Gate，不发布前端可消费资产。",
                retryable=reviewing.attempt < reviewing.max_attempts,
            )

        try:
            assets: list[ReconstructionAsset] = []
            for artifact in result.artifacts:
                assets.append(
                    self.artifact_store.store(
                        job=reviewing,
                        result=result,
                        payload=artifact,
                    )
                )
        except Exception as exc:
            for asset in assets:
                self.artifact_store.delete_unpublished(asset)
            return self._fail_running_job(
                reviewing,
                code=ReconstructionErrorCode.INVALID_PROVIDER_OUTPUT,
                message=f"重建资产未通过存储边界校验：{exc}",
                retryable=False,
            )

        succeeded = _updated_job(
            reviewing,
            status=ReconstructionJobStatus.SUCCEEDED,
            progress=ReconstructionProgress(
                stage=ReconstructionStage.COMPLETE,
                percent=100,
                message="输入与输出 Gate 均通过，资产可由受控下载接口消费。",
            ),
            assets=assets,
            version=reviewing.version + 1,
            updated_at=_utc_now(),
        )
        try:
            succeeded, _ = self.repository.transition_job(
                succeeded,
                expected_version=reviewing.version,
                event_kind="job_succeeded",
            )
        except Exception:
            for asset in assets:
                self.artifact_store.delete_unpublished(asset)
            raise
        return succeeded

    def retry_job(
        self,
        project_id: str,
        job_id: str,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> tuple[ReconstructionJob, bool]:
        operation_hash = hashlib.sha256(
            json.dumps(
                {"jobId": job_id, "expectedVersion": expected_version},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        replay = self.repository.get_idempotency_replay(
            project_id=project_id,
            operation="transition:job_retried",
            idempotency_key=idempotency_key,
            request_hash=operation_hash,
        )
        if replay is not None:
            return replay, True

        job = self.repository.get_job(project_id, job_id)
        if job.version != expected_version:
            raise ReconstructionStateError("expectedVersion does not match current job")
        if job.status not in {
            ReconstructionJobStatus.FAILED,
            ReconstructionJobStatus.UNAVAILABLE,
        } or job.error is None:
            raise ReconstructionStateError("only failed or unavailable jobs may retry")
        if not job.error.retryable or job.attempt >= job.max_attempts:
            raise ReconstructionStateError("reconstruction failure is not retryable")
        queued = _updated_job(
            job,
            status=ReconstructionJobStatus.QUEUED,
            progress=ReconstructionProgress(
                stage=ReconstructionStage.QUEUED,
                percent=0,
                message="失败任务已按新幂等操作重新入队。",
            ),
            output_quality_gate=None,
            provider_info=None,
            error=None,
            version=job.version + 1,
            updated_at=_utc_now(),
        )
        return self.repository.transition_job(
            queued,
            expected_version=job.version,
            event_kind="job_retried",
            idempotency_key=idempotency_key,
            operation_hash=operation_hash,
        )

    def _fail_without_start(
        self,
        job: ReconstructionJob,
        *,
        code: ReconstructionErrorCode,
        message: str,
        retryable: bool,
    ) -> ReconstructionJob:
        failed = _updated_job(
            job,
            status=(
                ReconstructionJobStatus.UNAVAILABLE
                if code == ReconstructionErrorCode.PROVIDER_NOT_CONFIGURED
                else ReconstructionJobStatus.FAILED
            ),
            progress=ReconstructionProgress(
                stage=ReconstructionStage.FAILED,
                percent=0,
                message=message,
            ),
            error=ReconstructionError(
                code=code,
                message=message,
                retryable=retryable,
                stage=ReconstructionStage.QUEUED,
            ),
            version=job.version + 1,
            updated_at=_utc_now(),
        )
        failed, _ = self.repository.transition_job(
            failed,
            expected_version=job.version,
            event_kind="job_failed",
        )
        return failed

    def _fail_running_job(
        self,
        job: ReconstructionJob,
        *,
        code: ReconstructionErrorCode,
        message: str,
        retryable: bool,
    ) -> ReconstructionJob:
        failed = _updated_job(
            job,
            status=ReconstructionJobStatus.FAILED,
            progress=ReconstructionProgress(
                stage=ReconstructionStage.FAILED,
                percent=job.progress.percent,
                message=message,
            ),
            error=ReconstructionError(
                code=code,
                message=message,
                retryable=retryable,
                stage=job.progress.stage,
            ),
            version=job.version + 1,
            updated_at=_utc_now(),
        )
        failed, _ = self.repository.transition_job(
            failed,
            expected_version=job.version,
            event_kind="job_failed",
        )
        return failed


def canonical_request_hash(request: ReconstructionJobRequest) -> str:
    payload = request.model_dump(mode="json", by_alias=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assess_capture_gate(request: ReconstructionJobRequest) -> CaptureGateReport:
    capture_set = request.capture_set
    images = capture_set.images
    azimuth_bins = {
        int(((image.azimuth_degrees + 180) % 360) // 45) for image in images
    }
    elevation_bands = {
        "low" if image.elevation_degrees < -15
        else "high" if image.elevation_degrees >= 20
        else "level"
        for image in images
    }
    thresholds = _capture_thresholds(request.quality_profile)
    qualifying_edges = [
        edge
        for edge in capture_set.overlaps
        if edge.estimated_overlap_percent >= thresholds["minimum_overlap"]
    ]
    connected_ids = _connected_image_ids(images[0].image_id, qualifying_edges)
    minimum_overlap = (
        min(edge.estimated_overlap_percent for edge in capture_set.overlaps)
        if capture_set.overlaps
        else None
    )
    flow_kinds = sorted(
        {node.kind for node in capture_set.site_flow_nodes}, key=lambda value: value.value
    )
    metrics = CaptureGateMetrics(
        image_count=len(images),
        distinct_azimuth_bins=len(azimuth_bins),
        distinct_elevation_bands=len(elevation_bands),
        connected_image_count=len(connected_ids),
        overlap_edge_count=len(capture_set.overlaps),
        minimum_declared_overlap_percent=minimum_overlap,
        site_flow_kinds=flow_kinds,
        scale_mode=capture_set.scale_reference.mode,
    )

    if request.pipeline == ReconstructionPipeline.AI_INFERRED:
        return CaptureGateReport(
            status=CaptureGateStatus.NOT_RECONSTRUCTION,
            profile=request.quality_profile,
            metrics=metrics,
            issues=[
                ReconstructionGateIssue(
                    code="ai_inferred_not_reconstruction",
                    message=(
                        "单图或 AI image-to-3D 属于推测式生成；即使产生 GLB，也不能"
                        "标为扫描、测绘或 multi-view reconstruction。"
                    ),
                    retryable_with_more_input=False,
                )
            ],
            disclaimer=CAPTURE_GATE_DISCLAIMER,
        )

    issues: list[ReconstructionGateIssue] = []
    if len(images) < thresholds["minimum_images"]:
        issues.append(
            _capture_issue(
                "image_count_below_minimum",
                f"至少需要 {thresholds['minimum_images']} 张互有重叠的照片；当前为 {len(images)} 张。",
            )
        )
    if len(azimuth_bins) < thresholds["minimum_azimuth_bins"]:
        issues.append(
            _capture_issue(
                "azimuth_coverage_insufficient",
                f"至少覆盖 {thresholds['minimum_azimuth_bins']} 个方位区间；当前为 {len(azimuth_bins)} 个。",
            )
        )
    if len(elevation_bands) < thresholds["minimum_elevation_bands"]:
        issues.append(
            _capture_issue(
                "elevation_coverage_insufficient",
                f"至少覆盖 {thresholds['minimum_elevation_bands']} 个俯仰层；当前为 {len(elevation_bands)} 个。",
            )
        )
    if len(connected_ids) != len(images):
        issues.append(
            _capture_issue(
                "overlap_graph_disconnected",
                "达到最低重叠阈值的图像关系没有连通全部照片。",
            )
        )
    if minimum_overlap is None or minimum_overlap < thresholds["minimum_overlap"]:
        issues.append(
            _capture_issue(
                "declared_overlap_insufficient",
                f"相邻照片声明重叠应不低于 {thresholds['minimum_overlap']:.0f}%。",
            )
        )

    if request.subject.subject_kind == ReconstructionSubjectKind.SITE:
        kinds = set(flow_kinds)
        has_equipment_or_workstation = bool(
            kinds & {SiteFlowNodeKind.EQUIPMENT, SiteFlowNodeKind.WORKSTATION}
        )
        if not (
            SiteFlowNodeKind.RAW_MATERIAL_AREA in kinds
            and has_equipment_or_workstation
            and SiteFlowNodeKind.PROCESS in kinds
            and SiteFlowNodeKind.FINISHED_GOODS_AREA in kinds
        ):
            issues.append(
                _capture_issue(
                    "site_flow_chain_incomplete",
                    "现场必须绑定原料区→设备/工位→工艺→成品区四段空间链。",
                )
            )

    return CaptureGateReport(
        status=(
            CaptureGateStatus.NEEDS_MORE_INPUT
            if issues
            else CaptureGateStatus.PASSED
        ),
        profile=request.quality_profile,
        metrics=metrics,
        issues=issues,
        disclaimer=CAPTURE_GATE_DISCLAIMER,
    )


def assess_output_quality(
    request: ReconstructionJobRequest,
    metrics: ReconstructionQualityMetrics,
) -> OutputQualityGateReport:
    thresholds = _quality_thresholds(request.quality_profile)
    issues: list[ReconstructionGateIssue] = []
    checks = [
        (
            metrics.input_image_count == len(request.capture_set.images),
            "input_count_mismatch",
            "provider 的 inputImageCount 与冻结图组不一致。",
            False,
        ),
        (
            metrics.registration_ratio >= thresholds["registration_ratio"],
            "registration_ratio_low",
            "成功注册的相机比例不足。",
            True,
        ),
        (
            metrics.median_reprojection_error_px <= thresholds["reprojection_error"],
            "reprojection_error_high",
            "中位重投影误差超过质量阈值。",
            True,
        ),
        (
            metrics.sparse_point_count >= thresholds["sparse_points"],
            "sparse_geometry_low",
            "稀疏几何点数量不足。",
            True,
        ),
        (
            metrics.dense_point_count >= thresholds["dense_points"],
            "dense_geometry_low",
            "稠密点云数量不足。",
            True,
        ),
        (
            metrics.mesh_face_count >= thresholds["mesh_faces"],
            "mesh_density_low",
            "网格面数量不足。",
            True,
        ),
        (
            metrics.coverage_percent >= thresholds["coverage_percent"],
            "geometry_coverage_low",
            "几何覆盖率不足。",
            True,
        ),
        (
            metrics.texture_coverage_percent >= thresholds["texture_coverage"],
            "texture_coverage_low",
            "纹理覆盖率不足。",
            True,
        ),
    ]
    if request.subject.subject_kind == ReconstructionSubjectKind.SITE:
        checks.append(
            (
                metrics.spatial_flow_coverage_percent is not None
                and metrics.spatial_flow_coverage_percent
                >= thresholds["spatial_flow_coverage"],
                "site_flow_coverage_low",
                "原料区→设备/工位→工艺→成品区空间链未完整落入场景。",
                True,
            )
        )
    for passed, code, message, retryable in checks:
        if not passed:
            issues.append(
                ReconstructionGateIssue(
                    code=code,
                    message=message,
                    retryable_with_more_input=retryable,
                )
            )
    return OutputQualityGateReport(
        passed=not issues,
        profile=request.quality_profile,
        metrics=metrics,
        issues=issues,
    )


def _capture_thresholds(profile: ReconstructionQualityProfile) -> dict[str, float]:
    if profile == ReconstructionQualityProfile.EQUIPMENT_REVIEW_V1:
        return {
            "minimum_images": 12,
            "minimum_azimuth_bins": 6,
            "minimum_elevation_bands": 2,
            "minimum_overlap": 60,
        }
    return {
        "minimum_images": 24,
        "minimum_azimuth_bins": 4,
        "minimum_elevation_bands": 2,
        "minimum_overlap": 70,
    }


def _quality_thresholds(profile: ReconstructionQualityProfile) -> dict[str, float]:
    if profile == ReconstructionQualityProfile.EQUIPMENT_REVIEW_V1:
        return {
            "registration_ratio": 0.80,
            "reprojection_error": 2.0,
            "sparse_points": 5_000,
            "dense_points": 50_000,
            "mesh_faces": 10_000,
            "coverage_percent": 70,
            "texture_coverage": 60,
            "spatial_flow_coverage": 0,
        }
    return {
        "registration_ratio": 0.85,
        "reprojection_error": 1.5,
        "sparse_points": 20_000,
        "dense_points": 200_000,
        "mesh_faces": 50_000,
        "coverage_percent": 75,
        "texture_coverage": 65,
        "spatial_flow_coverage": 100,
    }


def _connected_image_ids(start: str, edges: list[object]) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for raw_edge in edges:
        from_id = getattr(raw_edge, "from_image_id")
        to_id = getattr(raw_edge, "to_image_id")
        adjacency.setdefault(from_id, set()).add(to_id)
        adjacency.setdefault(to_id, set()).add(from_id)
    visited: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, set()) - visited)
    return visited


def _capture_issue(code: str, message: str) -> ReconstructionGateIssue:
    return ReconstructionGateIssue(
        code=code,
        message=message,
        retryable_with_more_input=True,
    )


def _validate_provider_result(
    request: ReconstructionJobRequest,
    result: ProviderReconstructionResult,
) -> None:
    expected_origin = {
        ReconstructionPipeline.MULTI_VIEW:
            ReconstructionAssetOrigin.MULTI_VIEW_RECONSTRUCTION,
        ReconstructionPipeline.AI_INFERRED:
            ReconstructionAssetOrigin.AI_INFERRED_GENERATION,
    }[request.pipeline]
    if result.origin != expected_origin:
        raise ValueError("provider asset origin does not match requested pipeline")
    if result.is_simulated != request.truth.is_simulated:
        raise ValueError("provider simulation truth does not match input declaration")
    if not result.source.strip() or result.source != result.source.strip():
        raise ValueError("provider result source must be non-blank and trimmed")
    if not result.disclaimer.strip() or result.disclaimer != result.disclaimer.strip():
        raise ValueError("provider result disclaimer must be non-blank and trimmed")
    returned_kinds = [artifact.kind for artifact in result.artifacts]
    if len(set(returned_kinds)) != len(returned_kinds):
        raise ValueError("provider returned duplicate asset kinds")
    if set(returned_kinds) != set(request.requested_outputs):
        raise ValueError("provider artifacts must exactly match requestedOutputs")
    expected_units = (
        ReconstructionUnits.UNSCALED
        if request.capture_set.scale_reference.mode == ScaleMode.UNKNOWN
        else ReconstructionUnits.METER
    )
    if any(artifact.units != expected_units for artifact in result.artifacts):
        raise ValueError("artifact units do not match capture scale reference")
    if request.subject.subject_kind == ReconstructionSubjectKind.SITE:
        expected_nodes = {
            node.node_id: node for node in request.capture_set.site_flow_nodes
        }
        returned_nodes = {binding.node_id: binding for binding in result.spatial_bindings}
        if set(returned_nodes) != set(expected_nodes):
            raise ValueError("site output must bind every declared site flow node")
        known_images = {image.image_id for image in request.capture_set.images}
        for binding in result.spatial_bindings:
            expected = expected_nodes[binding.node_id]
            if binding.kind != expected.kind:
                raise ValueError("site output binding kind drifted from input")
            if not set(binding.source_image_ids).issubset(known_images):
                raise ValueError("site output binding references an unknown image")
    elif result.spatial_bindings:
        raise ValueError("equipment output cannot carry site spatial bindings")


def _validate_artifact_payload(payload: ProviderArtifactPayload) -> None:
    if not payload.content:
        raise ValueError("artifact content cannot be empty")
    if len(payload.content) > MAX_RECONSTRUCTION_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds the reconstruction size limit")
    if (
        not payload.file_name
        or payload.file_name != payload.file_name.strip()
        or payload.file_name in {".", ".."}
        or any(character in payload.file_name for character in ("/", "\\", ":"))
    ):
        raise ValueError("artifact fileName must be a safe base name")
    expected_suffix = {
        ReconstructionAssetKind.GLB: ".glb",
        ReconstructionAssetKind.POINT_CLOUD_PLY: ".ply",
        ReconstructionAssetKind.MESH_OBJ: ".obj",
    }[payload.kind]
    if not payload.file_name.lower().endswith(expected_suffix):
        raise ValueError("artifact extension does not match kind")
    if payload.coordinate_system != "local_cartesian_y_up":
        raise ValueError("unsupported artifact coordinate system")
    if payload.kind == ReconstructionAssetKind.GLB:
        if len(payload.content) < 24:
            raise ValueError("GLB is shorter than a JSON chunk")
        magic, version, declared_length = struct.unpack("<4sII", payload.content[:12])
        if magic != b"glTF" or version != 2 or declared_length != len(payload.content):
            raise ValueError("GLB header/version/declared length is invalid")
        chunk_length, chunk_type = struct.unpack("<I4s", payload.content[12:20])
        if chunk_type != b"JSON" or chunk_length <= 0 or 20 + chunk_length > len(payload.content):
            raise ValueError("GLB must begin with a bounded JSON chunk")
        try:
            json.loads(payload.content[20 : 20 + chunk_length].decode("utf-8").rstrip(" "))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("GLB JSON chunk is invalid") from exc
    elif payload.kind == ReconstructionAssetKind.POINT_CLOUD_PLY:
        if not payload.content.startswith(b"ply\n"):
            raise ValueError("PLY artifact is missing its header")
    elif not payload.content.lstrip().startswith((b"v ", b"o ", b"#")):
        raise ValueError("OBJ artifact does not contain a recognized text header")


def _asset_truth(
    result: ProviderReconstructionResult,
) -> tuple[ReconstructionAssetDataStatus, ReconstructionClaim]:
    if result.is_simulated:
        return (
            ReconstructionAssetDataStatus.SYNTHETIC,
            ReconstructionClaim.SIMULATED_NOT_SCAN,
        )
    if result.origin == ReconstructionAssetOrigin.MULTI_VIEW_RECONSTRUCTION:
        return (
            ReconstructionAssetDataStatus.RECONSTRUCTED,
            ReconstructionClaim.MULTI_VIEW_RECONSTRUCTION,
        )
    if result.origin == ReconstructionAssetOrigin.AI_INFERRED_GENERATION:
        return (
            ReconstructionAssetDataStatus.INFERRED,
            ReconstructionClaim.INFERRED_NOT_SCAN,
        )
    raise ValueError("simulated fixture output must set isSimulated=true")


def _mime_type(kind: ReconstructionAssetKind) -> str:
    return {
        ReconstructionAssetKind.GLB: "model/gltf-binary",
        ReconstructionAssetKind.POINT_CLOUD_PLY: "application/ply",
        ReconstructionAssetKind.MESH_OBJ: "text/plain",
    }[kind]


def _updated_job(job: ReconstructionJob, **updates: object) -> ReconstructionJob:
    payload = job.model_dump(mode="python")
    payload.update(updates)
    return ReconstructionJob.model_validate(payload)


def _require_identifier(value: str, label: str) -> str:
    if (
        not value
        or value != value.strip()
        or len(value) > 128
        or any(character in value for character in ("/", "\\", ":"))
        or value in {".", ".."}
    ):
        raise ValueError(f"{label} must be a safe, trimmed identifier")
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "CAPTURE_GATE_DISCLAIMER",
    "LocalReconstructionArtifactStore",
    "MAX_RECONSTRUCTION_ARTIFACT_BYTES",
    "ProviderArtifactPayload",
    "ProviderReconstructionResult",
    "ReconstructionProviderFailure",
    "ReconstructionService",
    "ReconstructionServiceError",
    "ReconstructionStateError",
    "assess_capture_gate",
    "assess_output_quality",
    "canonical_request_hash",
]
