from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import FileResponse

from app.api.dependencies import IdempotencyKey
from app.api.responses import success
from app.contracts.envelope import ApiEnvelope, ErrorEnvelope
from app.contracts.errors import ConflictError, NotFoundError, ServiceError
from app.contracts.reconstruction import (
    ReconstructionEngineStatus,
    ReconstructionJob,
    ReconstructionJobRequest,
    ReconstructionRetryRequest,
    ReconstructionSubjectKind,
)
from app.repositories.reconstruction import (
    ReconstructionIdempotencyConflictError,
    ReconstructionNotFoundError,
    ReconstructionVersionConflictError,
)
from app.services.reconstruction import ReconstructionService, ReconstructionStateError


router = APIRouter(tags=["image-to-3d-reconstruction"])
ProjectId = Annotated[str, Path(min_length=1, max_length=128)]
JobId = Annotated[str, Path(pattern=r"^recon-job-[0-9a-f]{32}$")]
AssetId = Annotated[str, Path(pattern=r"^recon-asset-[0-9a-f]{32}$")]
SubjectId = Annotated[str, Path(min_length=1, max_length=128)]

ERROR_RESPONSES = {
    404: {"model": ErrorEnvelope, "description": "Project, job or asset not found"},
    409: {"model": ErrorEnvelope, "description": "Idempotency, version or state conflict"},
    422: {"model": ErrorEnvelope, "description": "Strict request validation"},
    503: {"model": ErrorEnvelope, "description": "Local engine unavailable"},
}


def get_reconstruction_service(request: Request) -> ReconstructionService:
    service = getattr(request.app.state, "reconstruction_service", None)
    if service is not None:
        return service
    lock: threading.Lock = request.app.state.reconstruction_lock
    with lock:
        service = getattr(request.app.state, "reconstruction_service", None)
        if service is None:
            service = request.app.state.reconstruction_service_factory()
            request.app.state.reconstruction_service = service
    return service


ReconstructionServiceDependency = Annotated[
    ReconstructionService, Depends(get_reconstruction_service)
]


def _service_error(exc: Exception) -> ServiceError:
    if isinstance(exc, ReconstructionNotFoundError):
        return NotFoundError("reconstruction_not_found", "未找到当前项目中的重建 Job 或资产。")
    if isinstance(exc, ReconstructionIdempotencyConflictError):
        return ConflictError(
            "idempotency_key_reused", "同一 Idempotency-Key 已用于不同重建请求。"
        )
    if isinstance(exc, ReconstructionVersionConflictError):
        return ConflictError(
            "version_conflict",
            "expectedVersion 与当前重建 Job 版本不一致，请刷新后重试。",
            details={
                "expectedVersion": exc.expected_version,
                "actualVersion": exc.current_version,
            },
        )
    if isinstance(exc, ReconstructionStateError):
        return ConflictError("reconstruction_state_conflict", str(exc))
    return ServiceError(
        code="reconstruction_internal_error",
        message="重建作业服务处理失败。",
        category="internal",
        status_code=500,
    )


def _provider(request: Request) -> object:
    return request.app.state.reconstruction_provider


@router.get(
    "/reconstruction/engine-status",
    response_model=ApiEnvelope[ReconstructionEngineStatus],
    operation_id="readLocalReconstructionEngineStatus",
)
def read_engine_status(request: Request) -> dict[str, object]:
    provider = _provider(request)
    return success(request, provider.status())


@router.post(
    "/projects/{projectId}/reconstruction/jobs",
    response_model=ApiEnvelope[ReconstructionJob],
    operation_id="createImageTo3dReconstructionJob",
    responses=ERROR_RESPONSES,
)
def create_job(
    request: Request,
    projectId: ProjectId,
    payload: ReconstructionJobRequest,
    service: ReconstructionServiceDependency,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    try:
        job, replayed = service.create_job(
            projectId, payload, idempotency_key=idempotency_key
        )
        if job.status == "queued" and not replayed:
            job = service.run_job(projectId, job.job_id, _provider(request))
        elif replayed:
            job = service.get_job(projectId, job.job_id)
        return success(request, job)
    except Exception as exc:
        raise _service_error(exc) from exc


@router.get(
    "/projects/{projectId}/reconstruction/jobs/{jobId}",
    response_model=ApiEnvelope[ReconstructionJob],
    operation_id="readImageTo3dReconstructionJob",
    responses=ERROR_RESPONSES,
)
def read_job(
    request: Request,
    projectId: ProjectId,
    jobId: JobId,
    service: ReconstructionServiceDependency,
) -> dict[str, object]:
    try:
        return success(request, service.get_job(projectId, jobId))
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post(
    "/projects/{projectId}/reconstruction/jobs/{jobId}/retry",
    response_model=ApiEnvelope[ReconstructionJob],
    operation_id="retryImageTo3dReconstructionJob",
    responses=ERROR_RESPONSES,
)
def retry_job(
    request: Request,
    projectId: ProjectId,
    jobId: JobId,
    payload: ReconstructionRetryRequest,
    service: ReconstructionServiceDependency,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    try:
        job, replayed = service.retry_job(
            projectId,
            jobId,
            expected_version=payload.expected_version,
            idempotency_key=idempotency_key,
        )
        if job.status == "queued" and not replayed:
            job = service.run_job(projectId, job.job_id, _provider(request))
        elif replayed:
            job = service.get_job(projectId, job.job_id)
        return success(request, job)
    except Exception as exc:
        raise _service_error(exc) from exc


@router.get(
    "/projects/{projectId}/reconstruction/subjects/{subjectKind}/{subjectId}/latest",
    response_model=ApiEnvelope[ReconstructionJob],
    operation_id="readLatestImageTo3dReconstruction",
    responses=ERROR_RESPONSES,
)
def read_latest_job(
    request: Request,
    projectId: ProjectId,
    subjectKind: ReconstructionSubjectKind,
    subjectId: SubjectId,
    service: ReconstructionServiceDependency,
) -> dict[str, object]:
    try:
        job = service.get_latest_succeeded_job(projectId, subjectKind.value, subjectId)
        if job is None:
            raise ReconstructionNotFoundError("no successful reconstruction job")
        return success(request, job)
    except Exception as exc:
        raise _service_error(exc) from exc


@router.get(
    "/projects/{projectId}/reconstruction/jobs/{jobId}/assets/{assetId}",
    operation_id="downloadImageTo3dReconstructionAsset",
    responses=ERROR_RESPONSES,
)
def download_asset(
    request: Request,
    projectId: ProjectId,
    jobId: JobId,
    assetId: AssetId,
    service: ReconstructionServiceDependency,
) -> FileResponse:
    try:
        asset = service.get_asset(projectId, jobId, assetId)
        path = service.artifact_store.resolve_for_read(asset.storage_key)
        return FileResponse(path, media_type=asset.mime_type, filename=asset.file_name)
    except Exception as exc:
        raise _service_error(exc) from exc


__all__ = ["router"]
