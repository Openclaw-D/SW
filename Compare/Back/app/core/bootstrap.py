from __future__ import annotations

from collections.abc import Callable, Mapping

from app.contracts.model_gateway import ModelGatewayRequest
from app.contracts.ports import WorkbenchServicePort
from app.core.config import Settings
from app.ports.model_gateway import ModelGatewayServicePort
from app.services.material_intelligence import MaterialIntelligenceProviderPort
from app.contracts.agent_communication import AgentMode, AgentRole
from app.contracts.errors import ServiceError
from app.ports.agent_communication import AgentCommunicationServicePort, AgentProviderPort
from app.services.reconstruction import (
    LocalReconstructionArtifactStore,
    ReconstructionService,
)
from app.repositories.reconstruction import SqliteReconstructionRepository


def create_default_service(settings: Settings) -> WorkbenchServicePort:
    """Load the Back-2 composition root without coupling HTTP to storage."""

    from app.services.workbench import create_workbench_service

    return create_workbench_service(settings)


def create_default_reconstruction_service(settings: Settings) -> ReconstructionService:
    """Compose isolated reconstruction state without touching workbench authority tables."""

    service = ReconstructionService(
        SqliteReconstructionRepository(settings.reconstruction_database_path),
        LocalReconstructionArtifactStore(settings.reconstruction_asset_root),
    )
    service.recover_interrupted_jobs()
    return service


def create_default_model_gateway_service(
    settings: Settings,
    *,
    provider_input_assembler: Callable[[ModelGatewayRequest], Mapping[str, str]],
    openai_provider: MaterialIntelligenceProviderPort | None = None,
) -> ModelGatewayServicePort:
    """Compose the gateway lazily without performing an external provider call."""

    from app.services.model_gateway import create_model_gateway_service

    return create_model_gateway_service(
        settings.database_path,
        mode=settings.model_gateway_mode,
        timeout_seconds=settings.model_gateway_timeout_seconds,
        provider_input_assembler=provider_input_assembler,
        openai_provider=openai_provider,
    )


def create_default_agent_communication_service(
    settings: Settings,
    *,
    workbench_service: WorkbenchServicePort,
    providers: Mapping[AgentRole, AgentProviderPort] | None = None,
) -> AgentCommunicationServicePort:
    """Compose the single-focus collaboration service without calling a provider."""

    from app.services.agent_communication.orchestrator import AgentCommunicationService
    from app.services.agent_communication.repository import AgentCommunicationRepository

    selected: dict[AgentRole, AgentProviderPort]
    if providers is not None:
        selected = dict(providers)
    elif settings.agent_mode == AgentMode.SYNTHETIC:
        from app.services.agent_communication.synthetic_provider import SyntheticAgentProvider

        provider = SyntheticAgentProvider()
        selected = {role: provider for role in AgentRole}
    elif settings.agent_mode == AgentMode.REAL:
        if settings.agent_provider == "glm_cli":
            from app.providers.glm_cli_agent import (
                GlmCliAgentConfig,
                GlmCliAgentProvider,
            )

            provider = GlmCliAgentProvider(
                GlmCliAgentConfig(
                    executable=settings.agent_glm_cli_executable,
                    timeout_seconds=min(
                        settings.agent_glm_cli_timeout_seconds,
                        max(0.1, settings.agent_timeout_seconds - 1.0),
                    ),
                )
            )
            selected = {role: provider for role in AgentRole}
        elif settings.agent_provider == "openai":
            import os

            from app.providers.openai_agent_responses import (
                OpenAIAgentResponsesConfig,
                OpenAIAgentResponsesProvider,
            )

            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise ServiceError(
                    code="agent_provider_not_configured",
                    message="真实 Agent provider 尚未配置凭据。",
                    category="internal",
                    status_code=503,
                    details={"retryable": False},
                )
            models = {
                AgentRole.BUSINESS: settings.agent_business_model,
                AgentRole.RISK: settings.agent_risk_model,
                AgentRole.LEADERSHIP: settings.agent_leadership_model,
            }
            selected = {
                role: OpenAIAgentResponsesProvider(
                    OpenAIAgentResponsesConfig(
                        api_key=api_key,
                        model=model,
                        timeout_seconds=settings.agent_timeout_seconds,
                    )
                )
                for role, model in models.items()
            }
        else:
            raise ServiceError(
                code="agent_provider_not_configured",
                message="真实 Agent provider 类型无效。",
                category="internal",
                status_code=503,
                details={"retryable": False},
            )
    else:
        selected = {}

    return AgentCommunicationService(
        workbench=workbench_service,
        repository=AgentCommunicationRepository(settings.database_path),
        mode=settings.agent_mode,
        providers=selected,
        timeout_seconds=settings.agent_timeout_seconds,
    )
