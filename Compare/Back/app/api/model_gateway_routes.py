from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.api.dependencies import IdempotencyKey, require_business, require_project_membership
from app.api.responses import success
from app.contracts.envelope import ApiEnvelope
from app.contracts.errors import BusinessValidationError
from app.contracts.model_gateway import (
    ModelGatewayCapability,
    ModelGatewayOutput,
    ModelGatewayRequest,
    ModelGatewayRunRecord,
)
from app.ports.model_gateway import ModelGatewayServicePort


router = APIRouter(tags=["model-gateway"], dependencies=[Depends(require_project_membership)])
ProjectId = Annotated[str, Path(min_length=1, max_length=160)]
RunId = Annotated[str, Path(pattern=r"^mgr-[0-9a-f]{32}$")]


def get_model_gateway_service(request: Request) -> ModelGatewayServicePort:
    service = getattr(request.app.state, "model_gateway_service", None)
    if service is not None:
        return service
    lock: threading.Lock = request.app.state.model_gateway_lock
    with lock:
        service = getattr(request.app.state, "model_gateway_service", None)
        if service is None:
            service = request.app.state.model_gateway_factory()
            request.app.state.model_gateway_service = service
    return service


ModelGatewayService = Annotated[
    ModelGatewayServicePort,
    Depends(get_model_gateway_service),
]


@router.get(
    "/model-gateway/capabilities",
    response_model=ApiEnvelope[list[ModelGatewayCapability]],
    operation_id="listModelGatewayCapabilities",
)
def list_capabilities(
    request: Request,
    service: ModelGatewayService,
) -> dict[str, object]:
    return success(request, service.list_capabilities())


@router.post(
    "/projects/{projectId}/model-gateway/runs",
    response_model=ApiEnvelope[ModelGatewayOutput],
    operation_id="executeModelGatewayRun",
    dependencies=[Depends(require_business)],
)
async def execute_run(
    request: Request,
    projectId: ProjectId,
    service: ModelGatewayService,
    idempotency_key: IdempotencyKey,
    payload: ModelGatewayRequest,
) -> dict[str, object]:
    if payload.material.project_id != projectId:
        raise BusinessValidationError(
            "path_body_mismatch",
            "projectId 必须与路径 projectId 一致。",
            field="projectId",
            details={"projectId": projectId, "bodyProjectId": payload.material.project_id},
        )
    result = await service.execute(payload, idempotency_key=idempotency_key)
    return success(request, result)


@router.get(
    "/projects/{projectId}/model-gateway/runs/{runId}",
    response_model=ApiEnvelope[ModelGatewayRunRecord],
    operation_id="readModelGatewayRun",
)
def read_run(
    request: Request,
    projectId: ProjectId,
    runId: RunId,
    service: ModelGatewayService,
) -> dict[str, object]:
    result = service.get_run(projectId, runId)
    return success(request, result)
