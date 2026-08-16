from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import FileResponse

from app.api.dependencies import IdempotencyKey, WorkbenchService, require_business, require_leadership, require_project_membership, require_risk
from app.api.responses import success
from app.contracts.envelope import ApiEnvelope, ErrorEnvelope
from app.contracts.errors import BusinessValidationError
from app.contracts.data_pack import (
    CandidateConfirmationCommand,
    CandidateConfirmationResult,
    ExecuteImportManifestRequest,
    ImportManifestRequest,
    MaterialImportPreflight,
    MaterialImportResult,
    MaterialUploadReceipt,
    MaterialIntelligenceRunCommand,
    StoredMaterialIntelligence,
    StoredSceneSpec,
)
from app.contracts.project_selection import ProjectCatalogItem
from app.contracts.material_schema import MaterialFieldSchema
from app.contracts.workbench import (
    ApprovalState,
    ApprovalTransitionInput,
    BusinessAnswerCommand,
    BusinessCorrectionCommand,
    BusinessCorrectionResult,
    CollaborationSubmissionResult,
    CommonReviewEvent,
    DimensionId,
    DimensionSeriesRequest,
    DimensionSeriesResponse,
    EvidenceSelectionResolution,
    HardConstraintResult,
    HealthStatus,
    Material,
    ReviewEvidenceSelectionGroup,
    RiskAnswerCommand,
    RiskQuestionCommand,
    WorkbenchProject,
)


ERROR_RESPONSES = {
    404: {"model": ErrorEnvelope, "description": "项目或项目内资源不存在"},
    409: {"model": ErrorEnvelope, "description": "版本、幂等或 hard gate 冲突"},
    422: {"model": ErrorEnvelope, "description": "请求或业务字段校验失败"},
    500: {"model": ErrorEnvelope, "description": "未预期的服务错误"},
}

router = APIRouter(responses={500: ERROR_RESPONSES[500]})
api_router = APIRouter(
    prefix="/projects",
    tags=["workbench"],
    responses=ERROR_RESPONSES,
    dependencies=[Depends(require_project_membership)],
)
ProjectId = Annotated[str, Path(min_length=1, max_length=160)]


def _require_match(
    *,
    path_name: str,
    path_value: object,
    body_name: str,
    body_value: object,
) -> None:
    if path_value != body_value:
        raise BusinessValidationError(
            "path_body_mismatch",
            f"{body_name} 必须与路径 {path_name} 一致。",
            field=body_name,
            details={path_name: path_value, body_name: body_value},
        )


@router.get(
    "/health",
    response_model=ApiEnvelope[HealthStatus],
    operation_id="getHealth",
    tags=["health"],
)
def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return success(
        request,
        HealthStatus(status="ok", service=settings.app_name, version=settings.app_version),
    )


@api_router.get(
    "",
    response_model=ApiEnvelope[list[ProjectCatalogItem]],
    operation_id="listProjects",
)
def list_projects(request: Request, service: WorkbenchService) -> dict[str, object]:
    return success(request, service.list_projects())


@api_router.get(
    "/{projectId}/workbench",
    response_model=ApiEnvelope[WorkbenchProject],
    operation_id="loadProjectWorkbench",
)
def load_workbench(
    request: Request,
    projectId: ProjectId,
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.get_workbench(projectId))


@api_router.get(
    "/{projectId}/materials",
    response_model=ApiEnvelope[list[Material]],
    operation_id="listProjectMaterials",
)
def list_materials(
    request: Request,
    projectId: ProjectId,
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.list_materials(projectId))


@api_router.get(
    "/{projectId}/material-field-schema",
    response_model=ApiEnvelope[MaterialFieldSchema],
    operation_id="readProjectMaterialFieldSchema",
)
def read_material_field_schema(
    request: Request,
    projectId: ProjectId,
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.get_material_field_schema(projectId))


@api_router.get(
    "/{projectId}/materials/{materialId}",
    response_model=ApiEnvelope[Material],
    operation_id="readProjectMaterial",
)
def read_material(
    request: Request,
    projectId: ProjectId,
    materialId: Annotated[str, Path(min_length=1, max_length=200)],
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.get_material(projectId, materialId))


@api_router.get(
    "/{projectId}/materials/{materialId}/original",
    operation_id="readProjectMaterialOriginal",
)
def read_material_original(
    projectId: ProjectId,
    materialId: Annotated[str, Path(min_length=1, max_length=200)],
    service: WorkbenchService,
) -> FileResponse:
    path, mime_type, file_name = service.get_material_original(projectId, materialId)
    # FileResponse streams from disk and lets Starlette satisfy Range requests;
    # keep originals project-scoped and avoid forcing high-resolution media into
    # Python or browser memory as a whole response.
    return FileResponse(
        path,
        media_type=mime_type,
        filename=file_name,
        content_disposition_type="inline",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@api_router.post(
    "/{projectId}/materials/uploads",
    response_model=ApiEnvelope[MaterialUploadReceipt],
    operation_id="uploadControlledMaterialPack",
    dependencies=[Depends(require_business)],
)
async def upload_material_pack(
    request: Request,
    projectId: ProjectId,
    service: WorkbenchService,
) -> dict[str, object]:
    file_name = request.headers.get("X-File-Name")
    if not file_name:
        raise BusinessValidationError("upload_file_name_missing", "必须通过 X-File-Name 提供 ZIP 文件名。", field="X-File-Name")
    content_length: int | None = None
    if request.headers.get("Content-Length"):
        try:
            content_length = int(request.headers["Content-Length"])
        except ValueError as exc:
            raise BusinessValidationError("upload_content_length_invalid", "Content-Length 必须为有效整数。") from exc
        if content_length < 0:
            raise BusinessValidationError("upload_content_length_invalid", "Content-Length 必须为非负整数。")
    receipt = await service.upload_material_pack(projectId, file_name, content_length, request.stream())
    return success(request, receipt)


@api_router.post(
    "/{projectId}/materials/imports/preflight",
    response_model=ApiEnvelope[MaterialImportPreflight],
    operation_id="preflightControlledMaterialImport",
    dependencies=[Depends(require_business)],
)
def preflight_material_import(
    request: Request,
    projectId: ProjectId,
    payload: ImportManifestRequest,
    service: WorkbenchService,
) -> dict[str, object]:
    _require_match(path_name="projectId", path_value=projectId, body_name="projectId", body_value=payload.project_id)
    return success(request, service.preflight_material_import(projectId, payload))


@api_router.post(
    "/{projectId}/materials/imports",
    response_model=ApiEnvelope[MaterialImportResult],
    operation_id="executeControlledMaterialImport",
    dependencies=[Depends(require_business)],
)
def execute_material_import(
    request: Request,
    projectId: ProjectId,
    payload: ExecuteImportManifestRequest,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    _require_match(path_name="projectId", path_value=projectId, body_name="projectId", body_value=payload.project_id)
    return success(request, service.execute_material_import(projectId, payload, idempotency_key=idempotency_key))


@api_router.post(
    "/{projectId}/materials/{materialId}/intelligence",
    response_model=ApiEnvelope[StoredMaterialIntelligence],
    operation_id="runMaterialIntelligence",
    dependencies=[Depends(require_business)],
)
def run_material_intelligence(
    request: Request,
    projectId: ProjectId,
    materialId: Annotated[str, Path(min_length=1, max_length=200)],
    payload: MaterialIntelligenceRunCommand,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    _require_match(path_name="projectId", path_value=projectId, body_name="projectId", body_value=payload.project_id)
    _require_match(path_name="materialId", path_value=materialId, body_name="materialId", body_value=payload.material_id)
    return success(request, service.run_material_intelligence(projectId, materialId, payload, idempotency_key=idempotency_key))


@api_router.get(
    "/{projectId}/materials/{materialId}/intelligence/latest",
    response_model=ApiEnvelope[StoredMaterialIntelligence],
    operation_id="readLatestMaterialIntelligence",
)
def read_latest_material_intelligence(
    request: Request,
    projectId: ProjectId,
    materialId: Annotated[str, Path(min_length=1, max_length=200)],
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.get_material_intelligence(projectId, materialId))


@api_router.get(
    "/{projectId}/materials/{materialId}/scene-spec",
    response_model=ApiEnvelope[StoredSceneSpec],
    operation_id="readMaterialSceneSpec",
)
def read_material_scene_spec(
    request: Request,
    projectId: ProjectId,
    materialId: Annotated[str, Path(min_length=1, max_length=200)],
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.get_material_scene_spec(projectId, materialId))


@api_router.post(
    "/{projectId}/candidates/{candidateId}/confirm",
    response_model=ApiEnvelope[CandidateConfirmationResult],
    operation_id="confirmMaterialFactCandidate",
    dependencies=[Depends(require_business)],
)
def confirm_material_candidate(
    request: Request,
    projectId: ProjectId,
    candidateId: Annotated[str, Path(min_length=1, max_length=200)],
    payload: CandidateConfirmationCommand,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    _require_match(path_name="projectId", path_value=projectId, body_name="projectId", body_value=payload.project_id)
    _require_match(path_name="candidateId", path_value=candidateId, body_name="candidateId", body_value=payload.candidate_id)
    return success(request, service.confirm_material_candidate(projectId, candidateId, payload, idempotency_key=idempotency_key))


@api_router.post(
    "/{projectId}/evidence/resolve",
    response_model=ApiEnvelope[EvidenceSelectionResolution],
    operation_id="resolveProjectEvidenceSelection",
)
def resolve_evidence(
    request: Request,
    projectId: ProjectId,
    payload: ReviewEvidenceSelectionGroup,
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.resolve_evidence(projectId, payload))


@api_router.post(
    "/{projectId}/dimensions/{dimensionId}/series/query",
    response_model=ApiEnvelope[DimensionSeriesResponse],
    operation_id="queryProjectDimensionSeries",
)
def query_dimension_series(
    request: Request,
    projectId: ProjectId,
    dimensionId: DimensionId,
    payload: DimensionSeriesRequest,
    service: WorkbenchService,
) -> dict[str, object]:
    _require_match(
        path_name="projectId",
        path_value=projectId,
        body_name="projectId",
        body_value=payload.project_id,
    )
    _require_match(
        path_name="dimensionId",
        path_value=dimensionId,
        body_name="dimensionId",
        body_value=payload.dimension_id,
    )
    return success(
        request,
        service.query_dimension_series(projectId, dimensionId, payload),
    )


@api_router.post(
    "/{projectId}/facts/{factKey}/corrections",
    response_model=ApiEnvelope[BusinessCorrectionResult],
    operation_id="submitBusinessCorrection",
    dependencies=[Depends(require_business)],
)
def submit_business_correction(
    request: Request,
    projectId: ProjectId,
    factKey: Annotated[str, Path(min_length=1, max_length=200)],
    payload: BusinessCorrectionCommand,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    _require_match(
        path_name="projectId",
        path_value=projectId,
        body_name="projectId",
        body_value=payload.project_id,
    )
    _require_match(
        path_name="factKey",
        path_value=factKey,
        body_name="factKey",
        body_value=payload.fact_key,
    )
    return success(
        request,
        service.submit_business_correction(
            projectId,
            factKey,
            payload,
            idempotency_key=idempotency_key,
        ),
    )


@api_router.post(
    "/{projectId}/review/risk/questions",
    response_model=ApiEnvelope[CommonReviewEvent],
    operation_id="submitRiskQuestion",
    dependencies=[Depends(require_risk)],
)
def submit_risk_question(
    request: Request,
    projectId: ProjectId,
    payload: RiskQuestionCommand,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    _require_match(
        path_name="projectId",
        path_value=projectId,
        body_name="projectId",
        body_value=payload.project_id,
    )
    return success(
        request,
        service.submit_risk_question(
            projectId, payload, idempotency_key=idempotency_key
        ),
    )


@api_router.post(
    "/{projectId}/review/business/answers",
    response_model=ApiEnvelope[CollaborationSubmissionResult],
    operation_id="submitBusinessAnswer",
    dependencies=[Depends(require_business)],
)
def submit_business_answer(
    request: Request,
    projectId: ProjectId,
    payload: BusinessAnswerCommand,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    _require_match(
        path_name="projectId",
        path_value=projectId,
        body_name="projectId",
        body_value=payload.project_id,
    )
    return success(
        request,
        service.submit_business_answer(
            projectId, payload, idempotency_key=idempotency_key
        ),
    )


@api_router.post(
    "/{projectId}/review/risk/answers",
    response_model=ApiEnvelope[CollaborationSubmissionResult],
    operation_id="submitRiskAnswer",
    dependencies=[Depends(require_risk)],
)
def submit_risk_answer(
    request: Request,
    projectId: ProjectId,
    payload: RiskAnswerCommand,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    _require_match(
        path_name="projectId",
        path_value=projectId,
        body_name="projectId",
        body_value=payload.project_id,
    )
    return success(
        request,
        service.submit_risk_answer(
            projectId, payload, idempotency_key=idempotency_key
        ),
    )


@api_router.get(
    "/{projectId}/review/events",
    response_model=ApiEnvelope[list[CommonReviewEvent]],
    operation_id="readReviewEvents",
)
def read_review_events(
    request: Request,
    projectId: ProjectId,
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.list_review_events(projectId))


@api_router.get(
    "/{projectId}/policy/results",
    response_model=ApiEnvelope[list[HardConstraintResult]],
    operation_id="readPolicyResults",
)
def read_policy_results(
    request: Request,
    projectId: ProjectId,
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.list_policy_results(projectId))


@api_router.get(
    "/{projectId}/approval",
    response_model=ApiEnvelope[ApprovalState],
    operation_id="readApprovalState",
)
def read_approval_state(
    request: Request,
    projectId: ProjectId,
    service: WorkbenchService,
) -> dict[str, object]:
    return success(request, service.get_approval_state(projectId))


@api_router.post(
    "/{projectId}/approval/transitions",
    response_model=ApiEnvelope[ApprovalState],
    operation_id="transitionApprovalState",
    dependencies=[Depends(require_leadership)],
)
def transition_approval_state(
    request: Request,
    projectId: ProjectId,
    payload: ApprovalTransitionInput,
    service: WorkbenchService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return success(
        request,
        service.transition_approval(
            projectId, payload, idempotency_key=idempotency_key
        ),
    )
