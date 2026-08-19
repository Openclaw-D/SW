from __future__ import annotations

import re
import threading
from typing import Annotated

from fastapi import Depends, Header, Request

from app.contracts.errors import BusinessValidationError, ForbiddenError
from app.contracts.ports import WorkbenchServicePort
from app.contracts.agent_communication import AgentRole
from app.contracts.authentication import AuthenticatedAccount
from app.services.authentication import AuthenticationService, SESSION_COOKIE_NAME


_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def get_workbench_service(request: Request) -> WorkbenchServicePort:
    service = getattr(request.app.state, "workbench_service", None)
    if service is not None:
        return service
    lock: threading.Lock = request.app.state.service_lock
    with lock:
        service = getattr(request.app.state, "workbench_service", None)
        if service is None:
            service = request.app.state.service_factory()
            request.app.state.workbench_service = service
    return service


def require_idempotency_key(
    value: Annotated[str, Header(alias="Idempotency-Key")],
) -> str:
    value = value.strip()
    if not _IDEMPOTENCY_KEY.fullmatch(value):
        raise BusinessValidationError(
            "idempotency_key_invalid",
            "Idempotency-Key 必须为 8–128 位安全字符。",
            field="Idempotency-Key",
        )
    return value


WorkbenchService = Annotated[WorkbenchServicePort, Depends(get_workbench_service)]
IdempotencyKey = Annotated[str, Depends(require_idempotency_key)]


def get_authentication_service(request: Request) -> AuthenticationService:
    # Project generation must finish before auth seeds and reconciles memberships.
    get_workbench_service(request)
    service: AuthenticationService = request.app.state.authentication_service
    service.seed()
    # seed() cross-joins memberships only once; projects generated later are
    # healed here without re-executing SCHEMA_SQL on authenticated requests.
    service.reconcile_project_memberships()
    return service

AuthenticationServiceDependency = Annotated[AuthenticationService, Depends(get_authentication_service)]

def require_authenticated_account(request: Request, service: AuthenticationServiceDependency) -> AuthenticatedAccount:
    principal = service.authenticate(request.cookies.get(SESSION_COOKIE_NAME))
    request.state.principal = principal
    return principal

AuthenticatedPrincipal = Annotated[AuthenticatedAccount, Depends(require_authenticated_account)]

def require_project_membership(request: Request, principal: AuthenticatedPrincipal, service: AuthenticationServiceDependency) -> AuthenticatedAccount:
    project_id = request.path_params.get("projectId")
    if project_id:
        service.require_membership(principal, project_id)
    return principal

ProjectPrincipal = Annotated[AuthenticatedAccount, Depends(require_project_membership)]

def require_business(principal: ProjectPrincipal, service: AuthenticationServiceDependency) -> AuthenticatedAccount:
    service.require_role(principal, "business")
    return principal

def require_risk(principal: ProjectPrincipal, service: AuthenticationServiceDependency) -> AuthenticatedAccount:
    service.require_role(principal, "risk")
    return principal

def require_leadership(principal: ProjectPrincipal, service: AuthenticationServiceDependency) -> AuthenticatedAccount:
    service.require_role(principal, "leadership")
    return principal

BusinessPrincipal = Annotated[AuthenticatedAccount, Depends(require_business)]
RiskPrincipal = Annotated[AuthenticatedAccount, Depends(require_risk)]
LeadershipPrincipal = Annotated[AuthenticatedAccount, Depends(require_leadership)]

def require_agent_principal(principal: ProjectPrincipal) -> AgentRole:
    """Agent identity is derived only from the authenticated server session."""

    return AgentRole(principal.role)


AgentPrincipal = Annotated[AgentRole, Depends(require_agent_principal)]


def require_chat_principal(principal: AgentPrincipal) -> AgentRole:
    """Only the two actual conversation roles may write or invoke an Agent."""

    if principal == AgentRole.LEADERSHIP:
        raise ForbiddenError(
            "chat_principal_forbidden",
            "设置账号只管理系统配置，不参与项目群聊。",
            details={"principalRole": principal.value, "allowedRoles": ["business", "risk"]},
        )
    return principal


ChatPrincipal = Annotated[AgentRole, Depends(require_chat_principal)]
