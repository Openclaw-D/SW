from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api.dependencies import AgentPrincipal, IdempotencyKey
from app.api.responses import success
from app.contracts.agent_communication import (
    AgentFocusEvent,
    AgentFocusTransitionRequest,
    AgentMessage,
    AgentRunRecord,
    AgentThread,
    AgentThreadControlRequest,
    AgentThreadCreateRequest,
    AgentTurnRequest,
    AgentTurnResult,
)
from app.contracts.envelope import ApiEnvelope, ErrorEnvelope
from app.contracts.conclusion import ProjectConclusionReport
from app.ports.agent_communication import AgentCommunicationServicePort


router = APIRouter(tags=["agent-collaboration"])
ProjectId = Annotated[str, Path(min_length=1, max_length=160)]
ThreadId = Annotated[str, Path(pattern=r"^agent-thread-[0-9a-f]{32}$")]
RunId = Annotated[str, Path(pattern=r"^agent-run-[0-9a-f]{32}$")]
AfterSequence = Annotated[int, Query(ge=0)]
ListLimit = Annotated[int, Query(ge=1, le=500)]

ERROR_RESPONSES = {
    400: {"model": ErrorEnvelope, "description": "Malformed request"},
    403: {"model": ErrorEnvelope, "description": "Focus/principal boundary"},
    404: {"model": ErrorEnvelope, "description": "Project/thread/run not found"},
    409: {"model": ErrorEnvelope, "description": "Version, idempotency, run or focus conflict"},
    422: {"model": ErrorEnvelope, "description": "Strict request validation"},
    503: {"model": ErrorEnvelope, "description": "Provider unavailable or invalid"},
}


def get_agent_service(request: Request) -> AgentCommunicationServicePort:
    service = getattr(request.app.state, "agent_communication_service", None)
    if service is not None:
        return service
    lock: threading.Lock = request.app.state.agent_communication_lock
    with lock:
        service = getattr(request.app.state, "agent_communication_service", None)
        if service is None:
            service = request.app.state.agent_communication_factory()
            request.app.state.agent_communication_service = service
    return service


AgentService = Annotated[
    AgentCommunicationServicePort,
    Depends(get_agent_service),
]


@router.get(
    "/projects/{projectId}/conclusion",
    response_model=ApiEnvelope[ProjectConclusionReport],
    operation_id="readProjectConclusionReport",
    responses={
        404: {"model": ErrorEnvelope, "description": "Project not found"},
        422: {"model": ErrorEnvelope, "description": "Strict request validation"},
        503: {"model": ErrorEnvelope, "description": "Conclusion projection unavailable"},
    },
)
def read_conclusion_report(
    request: Request,
    projectId: ProjectId,
    service: AgentService,
) -> dict[str, object]:
    return success(request, service.get_conclusion_report(projectId))


@router.post(
    "/projects/{projectId}/agents/threads",
    response_model=ApiEnvelope[AgentThread],
    operation_id="createAgentCollaborationThread",
    responses=ERROR_RESPONSES,
)
def create_thread(
    request: Request,
    projectId: ProjectId,
    payload: AgentThreadCreateRequest,
    principal: AgentPrincipal,
    service: AgentService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return success(
        request,
        service.create_thread(
            projectId, principal, payload, idempotency_key=idempotency_key
        ),
    )


@router.get(
    "/projects/{projectId}/agents/threads/{threadId}",
    response_model=ApiEnvelope[AgentThread],
    operation_id="readAgentCollaborationThread",
    responses=ERROR_RESPONSES,
)
def read_thread(
    request: Request,
    projectId: ProjectId,
    threadId: ThreadId,
    principal: AgentPrincipal,
    service: AgentService,
) -> dict[str, object]:
    del principal
    return success(request, service.get_thread(projectId, threadId))


@router.get(
    "/projects/{projectId}/agents/threads/{threadId}/messages",
    response_model=ApiEnvelope[list[AgentMessage]],
    operation_id="listAgentCollaborationMessages",
    responses=ERROR_RESPONSES,
)
def list_messages(
    request: Request,
    projectId: ProjectId,
    threadId: ThreadId,
    principal: AgentPrincipal,
    service: AgentService,
    afterSequence: AfterSequence = 0,
    limit: ListLimit = 200,
) -> dict[str, object]:
    return success(
        request,
        service.list_messages(
            projectId,
            threadId,
            principal,
            after_sequence=afterSequence,
            limit=limit,
        ),
    )


@router.post(
    "/projects/{projectId}/agents/threads/{threadId}/focus-transitions",
    response_model=ApiEnvelope[AgentThread],
    operation_id="transitionAgentCollaborationFocus",
    responses=ERROR_RESPONSES,
)
def transition_focus(
    request: Request,
    projectId: ProjectId,
    threadId: ThreadId,
    payload: AgentFocusTransitionRequest,
    principal: AgentPrincipal,
    service: AgentService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return success(
        request,
        service.transition_focus(
            projectId,
            threadId,
            principal,
            payload,
            idempotency_key=idempotency_key,
        ),
    )


@router.get(
    "/projects/{projectId}/agents/threads/{threadId}/focus-events",
    response_model=ApiEnvelope[list[AgentFocusEvent]],
    operation_id="listAgentCollaborationFocusEvents",
    responses=ERROR_RESPONSES,
)
def list_focus_events(
    request: Request,
    projectId: ProjectId,
    threadId: ThreadId,
    principal: AgentPrincipal,
    service: AgentService,
    afterSequence: AfterSequence = 0,
    limit: ListLimit = 200,
) -> dict[str, object]:
    return success(
        request,
        service.list_focus_events(
            projectId,
            threadId,
            principal,
            after_sequence=afterSequence,
            limit=limit,
        ),
    )


@router.post(
    "/projects/{projectId}/agents/threads/{threadId}/turns",
    response_model=ApiEnvelope[AgentTurnResult],
    operation_id="executeFocusedAgentTurn",
    responses=ERROR_RESPONSES,
)
async def execute_turn(
    request: Request,
    projectId: ProjectId,
    threadId: ThreadId,
    payload: AgentTurnRequest,
    principal: AgentPrincipal,
    service: AgentService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    result = await service.execute_turn(
        projectId,
        threadId,
        principal,
        payload,
        idempotency_key=idempotency_key,
    )
    return success(request, result)


@router.post(
    "/projects/{projectId}/agents/threads/{threadId}/controls",
    response_model=ApiEnvelope[AgentThread],
    operation_id="controlAgentCollaborationThread",
    responses=ERROR_RESPONSES,
)
def control_thread(
    request: Request,
    projectId: ProjectId,
    threadId: ThreadId,
    payload: AgentThreadControlRequest,
    principal: AgentPrincipal,
    service: AgentService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return success(
        request,
        service.control_thread(
            projectId,
            threadId,
            principal,
            payload,
            idempotency_key=idempotency_key,
        ),
    )


@router.get(
    "/projects/{projectId}/agents/runs/{runId}",
    response_model=ApiEnvelope[AgentRunRecord],
    operation_id="readAgentCollaborationRun",
    responses=ERROR_RESPONSES,
)
def read_run(
    request: Request,
    projectId: ProjectId,
    runId: RunId,
    principal: AgentPrincipal,
    service: AgentService,
) -> dict[str, object]:
    return success(request, service.get_run(projectId, runId, principal))


__all__ = ["router"]
