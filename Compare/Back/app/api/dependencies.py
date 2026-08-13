from __future__ import annotations

import re
import threading
from typing import Annotated

from fastapi import Depends, Header, Request

from app.contracts.errors import BusinessValidationError
from app.contracts.ports import WorkbenchServicePort
from app.contracts.agent_communication import AgentRole


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


def require_agent_principal(
    value: Annotated[AgentRole, Header(alias="X-Compare-Role")],
) -> AgentRole:
    """Local simulated principal; production deployments must replace this dependency."""

    return value


AgentPrincipal = Annotated[AgentRole, Depends(require_agent_principal)]
