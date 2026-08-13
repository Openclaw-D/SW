from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable

from pydantic import ValidationError

from app.contracts.errors import BusinessValidationError, ServiceError
from app.contracts.material_intelligence import (
    MaterialIntelligenceDataStatus,
    MaterialIntelligenceModelInfo,
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
    MaterialIntelligenceStatus,
    UnresolvedItem,
    UnresolvedItemKind,
    validate_material_intelligence_result,
)
from app.contracts.model_gateway import (
    ModelGatewayCapability,
    ModelGatewayMode,
    ModelGatewayOutput,
    ModelGatewayRequest,
    ModelGatewayRunStatus,
)
from app.ports.model_gateway import (
    AssembledGatewayInput,
    ModelGatewayProviderPort,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.providers.openai_responses import (
    OpenAIProviderConfigurationError,
    OpenAIProviderError,
    OpenAIProviderResponseError,
    OpenAIResponsesMaterialProvider,
    derive_gateway_locator_bindings,
)
from app.services.material_intelligence import MaterialIntelligenceProviderPort


SYNTHETIC_DISCLAIMER = (
    "完整脱敏合成输入上的 fake provider 辅助结果；候选必须经现有人工确认 Gate，"
    "不构成权威事实、评分、制度、hard gate 或审批结论。"
)
OPENAI_GATEWAY_PROVIDER_ID = "openai_responses_api"


class SyntheticFakeProvider:
    provider_id = "synthetic_fake"
    model_id = "deterministic-v1"
    is_simulated = True
    capabilities = frozenset({"material_intelligence"})

    def __init__(self) -> None:
        self.call_count = 0

    async def execute(
        self,
        request: ModelGatewayRequest,
        assembled_input: AssembledGatewayInput,
        *,
        max_output_tokens: int,
    ) -> ModelGatewayOutput:
        self.call_count += 1
        run_id = "mgr-" + hashlib.sha256(
            f"{request.request_id}:{request.input_hash}".encode("utf-8")
        ).hexdigest()[:32]
        unresolved_id = "mgu-" + hashlib.sha256(
            f"{request.input_hash}:review".encode("utf-8")
        ).hexdigest()[:16]
        result = MaterialIntelligenceResult(
            project_id=request.material.project_id,
            material_id=request.material.material_id,
            material_version_id=request.material.material_version_id,
            content_hash=request.material.content_hash,
            media_kind=request.material.media_kind,
            context_version=request.context_version,
            data_classification=request.material.data_classification,
            status=MaterialIntelligenceStatus.NEEDS_REVIEW,
            confidence=0.5,
            observations=[],
            extracted_field_candidates=[],
            unresolved_items=[
                UnresolvedItem(
                    id=unresolved_id,
                    kind=UnresolvedItemKind.MANUAL_REVIEW,
                    question="请人工核对脱敏合成材料原件与精确 locator 后再确认候选。",
                    reason="Model Gateway 输入不含原件正文，fake provider 不得生成虚假 SourceAnchor。",
                    requires_human_review=True,
                    source_anchor_ids=[],
                )
            ],
            source_anchors=[],
            scene_spec=None,
            model_info=MaterialIntelligenceModelInfo(
                provider=self.provider_id,
                model=self.model_id,
                model_version="1",
            ),
            prompt_version="gateway-synthetic-v1",
            input_hash=request.input_hash,
            advisory_only=True,
            is_simulated=True,
            data_status=MaterialIntelligenceDataStatus.SIMULATED,
            source=self.provider_id,
            disclaimer=SYNTHETIC_DISCLAIMER,
        )
        return ModelGatewayOutput(
            request_id=request.request_id,
            run_id=run_id,
            capability_id=request.capability_id,
            mode=ModelGatewayMode.SYNTHETIC,
            status=ModelGatewayRunStatus.NEEDS_REVIEW,
            material_id=request.material.material_id,
            material_version_id=request.material.material_version_id,
            input_hash=request.input_hash,
            result=result,
            source_anchors=[],
            locator_bindings=[],
            error=None,
            advisory_only=True,
            is_simulated=True,
            data_status=MaterialIntelligenceDataStatus.SIMULATED,
            source=self.provider_id,
            disclaimer=SYNTHETIC_DISCLAIMER,
        )


class OpenAIResponsesGatewayProvider:
    """Adapt the existing candidate-only OpenAI provider to the gateway port.

    Environment configuration stays lazy so startup, health and capability
    discovery never require a credential or create an external call.
    """

    provider_id = OPENAI_GATEWAY_PROVIDER_ID
    model_id = "configured-openai-model"
    is_simulated = False
    capabilities = frozenset({"material_intelligence"})

    def __init__(
        self,
        provider: MaterialIntelligenceProviderPort | None = None,
        *,
        provider_factory: Callable[[], OpenAIResponsesMaterialProvider] | None = None,
    ) -> None:
        self._provider = provider
        self._provider_factory = (
            provider_factory or OpenAIResponsesMaterialProvider.from_environment
        )
        self._provider_lock = threading.Lock()

    def ensure_configured(self) -> None:
        self._material_provider()

    async def execute(
        self,
        request: ModelGatewayRequest,
        assembled_input: AssembledGatewayInput,
        *,
        max_output_tokens: int,
    ) -> ModelGatewayOutput:
        del max_output_tokens  # The injected adapter owns its frozen output budget.
        if request.mode != ModelGatewayMode.REAL:
            raise BusinessValidationError(
                "capability_not_supported",
                "OpenAI Responses provider 只接受显式 real 请求。",
                field="mode",
            )
        if assembled_input.input_hash != request.input_hash:
            raise ServiceError(
                code="invalid_output",
                message="Model Gateway 组装输入未绑定后端 canonical inputHash。",
                category="internal",
                status_code=502,
            )
        provider = self._material_provider()
        material_request = MaterialIntelligenceRequest(
            project_id=request.material.project_id,
            material_id=request.material.material_id,
            material_version_id=request.material.material_version_id,
            content_hash=request.material.content_hash,
            media_kind=request.material.media_kind,
            context_version=request.context_version,
            task_goals=request.task_goals,
            locale=request.project_context.locale,
            data_classification=request.material.data_classification,
            usage_authorization_ref=request.material.usage_authorization_ref,
        )
        try:
            raw_result = await provider.analyze(
                material_request,
                assembled_input.payload,
                assembled_input.input_hash,
            )
        except OpenAIProviderConfigurationError as exc:
            raise ServiceError(
                code="provider_not_configured",
                message="OpenAI Responses provider 未完成必要配置。",
                category="internal",
                status_code=503,
            ) from exc
        except OpenAIProviderResponseError as exc:
            raise ServiceError(
                code="invalid_output",
                message="OpenAI Responses provider 返回了不符合严格契约的结果。",
                category="internal",
                status_code=502,
            ) from exc
        except OpenAIProviderError as exc:
            if exc.code == "provider_http_429":
                raise ProviderRateLimitError() from exc
            raise ProviderUnavailableError() from exc

        try:
            result = MaterialIntelligenceResult.model_validate(raw_result)
            validate_material_intelligence_result(
                material_request,
                result,
                expected_input_hash=request.input_hash,
            )
            locator_bindings = derive_gateway_locator_bindings(result)
        except (ValidationError, ValueError, TypeError) as exc:
            raise ServiceError(
                code="invalid_output",
                message="OpenAI Responses provider 返回了不符合严格契约的结果。",
                category="internal",
                status_code=502,
            ) from exc
        if result.status == MaterialIntelligenceStatus.UNAVAILABLE:
            raise ProviderUnavailableError()
        status = (
            ModelGatewayRunStatus.SUCCEEDED
            if result.status == MaterialIntelligenceStatus.COMPLETED
            else ModelGatewayRunStatus.NEEDS_REVIEW
        )
        try:
            return ModelGatewayOutput(
                request_id=request.request_id,
                run_id=(
                    "mgr-"
                    + hashlib.sha256(request.request_id.encode("utf-8")).hexdigest()[:32]
                ),
                capability_id=request.capability_id,
                mode=ModelGatewayMode.REAL,
                status=status,
                material_id=request.material.material_id,
                material_version_id=request.material.material_version_id,
                input_hash=request.input_hash,
                result=result,
                source_anchors=result.source_anchors,
                locator_bindings=locator_bindings,
                error=None,
                advisory_only=True,
                is_simulated=False,
                data_status=(
                    MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED
                ),
                source=self.provider_id,
                disclaimer=result.disclaimer,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ServiceError(
                code="invalid_output",
                message="OpenAI Responses provider 返回了不符合严格契约的结果。",
                category="internal",
                status_code=502,
            ) from exc

    def _material_provider(self) -> MaterialIntelligenceProviderPort:
        if self._provider is not None:
            return self._provider
        with self._provider_lock:
            if self._provider is None:
                try:
                    self._provider = self._provider_factory()
                except (OpenAIProviderConfigurationError, ValueError) as exc:
                    raise ServiceError(
                        code="provider_not_configured",
                        message="OpenAI Responses provider 未配置 OPENAI_API_KEY。",
                        category="internal",
                        status_code=503,
                    ) from exc
        provider = self._provider
        assert provider is not None
        return provider


class ProviderRouter:
    def __init__(self, providers: tuple[ModelGatewayProviderPort, ...]) -> None:
        self._providers = {provider.provider_id: provider for provider in providers}
        if len(self._providers) != len(providers):
            raise ValueError("providerId values must be unique")

    def route(
        self,
        request: ModelGatewayRequest,
        capability: ModelGatewayCapability,
    ) -> ModelGatewayProviderPort:
        if request.mode == ModelGatewayMode.DISABLED:
            raise ServiceError(
                code="gateway_disabled",
                message="Model Gateway 当前不可用。",
                category="internal",
                status_code=503,
            )
        if request.mode not in capability.supported_modes:
            raise BusinessValidationError(
                "capability_not_supported",
                "capability 不支持请求的 gateway mode。",
                field="mode",
            )
        simulated = request.mode == ModelGatewayMode.SYNTHETIC
        candidates = [
            provider
            for provider in self._providers.values()
            if provider.is_simulated is simulated
            and request.capability_id in provider.capabilities
        ]
        if len(candidates) != 1:
            provider_label = "synthetic" if simulated else "real"
            raise ServiceError(
                code="provider_not_configured",
                message=f"{provider_label} provider 未配置或配置不唯一。",
                category="internal",
                status_code=503,
            )
        provider = candidates[0]
        if request.capability_id not in provider.capabilities:
            raise BusinessValidationError(
                "capability_not_supported",
                "provider 不支持请求的 capability。",
                field="capabilityId",
            )
        return provider
