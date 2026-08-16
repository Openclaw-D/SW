from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import install_error_handlers
from app.api.model_gateway_routes import router as model_gateway_router
from app.api.agent_routes import router as agent_communication_router
from app.api.reconstruction_routes import router as reconstruction_router
from app.api.routes import api_router, router as health_router
from app.api.auth_routes import router as auth_router
from app.contracts.errors import ServiceError
from app.contracts.model_gateway import ModelGatewayRequest
from app.contracts.ports import WorkbenchServicePort
from app.ports.model_gateway import ModelGatewayServicePort
from app.ports.agent_communication import AgentCommunicationServicePort, AgentProviderPort
from app.contracts.agent_communication import AgentRole
from app.contracts.reconstruction import ReconstructionProviderPort
from app.core.bootstrap import (
    create_default_agent_communication_service,
    create_default_model_gateway_service,
    create_default_reconstruction_service,
    create_default_service,
)
from app.core.config import Settings, get_settings
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.services.material_intelligence import MaterialIntelligenceProviderPort
from app.services.reconstruction import ReconstructionService
from app.services.authentication import AuthenticationService


def create_app(
    settings: Settings | None = None,
    service: WorkbenchServicePort | None = None,
    model_gateway_service: ModelGatewayServicePort | None = None,
    openai_provider: MaterialIntelligenceProviderPort | None = None,
    agent_communication_service: AgentCommunicationServicePort | None = None,
    agent_providers: dict[AgentRole, AgentProviderPort] | None = None,
    reconstruction_service: ReconstructionService | None = None,
    reconstruction_provider: ReconstructionProviderPort | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        active_service = getattr(application.state, "workbench_service", None)
        active_agent_service = getattr(
            application.state, "agent_communication_service", None
        )
        if active_agent_service is not None:
            close = getattr(active_agent_service, "close", None)
            if callable(close):
                close()
        if active_service is not None:
            close = getattr(active_service, "close", None)
            if callable(close):
                close()
        active_model_gateway = getattr(application.state, "model_gateway_service", None)
        if active_model_gateway is not None and active_model_gateway is not active_service:
            close = getattr(active_model_gateway, "close", None)
            if callable(close):
                close()
        active_reconstruction = getattr(application.state, "reconstruction_service", None)
        if active_reconstruction is not None:
            close = getattr(active_reconstruction.repository, "close", None)
            if callable(close):
                close()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "signal-council 融资租赁首轮材料核验工作台本地 API。"
            "结果来自确定性业务规则和完整脱敏生成数据，不是统计模型或自动审批。"
        ),
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.authentication_service = AuthenticationService(settings.database_path, session_hours=settings.session_hours)
    application.state.workbench_service = service
    application.state.service_lock = threading.Lock()
    application.state.service_factory = lambda: create_default_service(settings)
    application.state.model_gateway_service = model_gateway_service
    application.state.model_gateway_lock = threading.Lock()
    application.state.agent_communication_service = agent_communication_service
    application.state.agent_communication_lock = threading.Lock()
    application.state.reconstruction_service = reconstruction_service
    application.state.reconstruction_lock = threading.Lock()
    application.state.reconstruction_service_factory = (
        lambda: create_default_reconstruction_service(settings)
    )
    if reconstruction_provider is None:
        from app.providers.local_reconstruction import UnavailableLocalReconstructionProvider

        reconstruction_provider = UnavailableLocalReconstructionProvider()
    application.state.reconstruction_provider = reconstruction_provider

    def get_or_create_workbench() -> WorkbenchServicePort:
        active_service = getattr(application.state, "workbench_service", None)
        if active_service is None:
            lock: threading.Lock = application.state.service_lock
            with lock:
                active_service = getattr(application.state, "workbench_service", None)
                if active_service is None:
                    active_service = application.state.service_factory()
                    application.state.workbench_service = active_service
        return active_service

    def assemble_provider_input(request: ModelGatewayRequest) -> dict[str, str]:
        active_service = get_or_create_workbench()
        data_pack = getattr(active_service, "data_pack", None)
        assembler = getattr(data_pack, "assemble_model_gateway_provider_input", None)
        if not callable(assembler):
            raise ServiceError(
                code="provider_not_configured",
                message="Workbench DataPack providerInput 装配器不可用。",
                category="internal",
                status_code=503,
            )
        return dict(assembler(request))

    def create_model_gateway() -> ModelGatewayServicePort:
        return create_default_model_gateway_service(
            settings,
            provider_input_assembler=assemble_provider_input,
            openai_provider=openai_provider,
        )

    application.state.model_gateway_factory = create_model_gateway

    def create_agent_communication() -> AgentCommunicationServicePort:
        return create_default_agent_communication_service(
            settings,
            workbench_service=get_or_create_workbench(),
            providers=agent_providers,
        )

    application.state.agent_communication_factory = create_agent_communication

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Idempotency-Key",
            "X-File-Name",
            REQUEST_ID_HEADER,
        ],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )
    application.add_middleware(RequestIdMiddleware)
    install_error_handlers(application)
    application.include_router(health_router)
    application.include_router(auth_router, prefix=settings.api_prefix)
    application.include_router(api_router, prefix=settings.api_prefix)
    application.include_router(model_gateway_router, prefix=settings.api_prefix)
    application.include_router(agent_communication_router, prefix=settings.api_prefix)
    application.include_router(reconstruction_router, prefix=settings.api_prefix)
    return application


app = create_app()


def get_openapi_paths() -> dict[str, Any]:
    return app.openapi()["paths"]
