from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.contracts.errors import BusinessValidationError, NotFoundError, ServiceError
from app.contracts.material_intelligence import MaterialIntelligenceDataStatus
from app.contracts.model_gateway import (
    ModelGatewayError,
    ModelGatewayErrorCode,
    ModelGatewayCapability,
    ModelGatewayMode,
    ModelGatewayOutput,
    ModelGatewayRequest,
    ModelGatewayRunRecord,
    ModelGatewayRunStatus,
)
from app.ports.model_gateway import (
    AssembledGatewayInput,
    ModelGatewayProviderPort,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.services.model_gateway.capability_registry import CapabilityRegistry
from app.services.model_gateway.input_assembler import assemble_input, request_fingerprint
from app.services.model_gateway.output_validator import validate_output
from app.services.model_gateway.provider_router import (
    OPENAI_GATEWAY_PROVIDER_ID,
    OpenAIResponsesGatewayProvider,
    ProviderRouter,
    SyntheticFakeProvider,
)
from app.services.model_gateway.run_recorder import RunRecorder
from app.services.material_intelligence import MaterialIntelligenceProviderPort


ProviderInputAssembler = Callable[[ModelGatewayRequest], Mapping[str, str]]


class ModelGatewayOrchestrator:
    MAX_INPUT_TOKENS = 8_000
    MAX_OUTPUT_TOKENS = 2_000
    TIMEOUT_SECONDS = 2.0

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        router: ProviderRouter,
        recorder: RunRecorder,
        enabled_mode: ModelGatewayMode = ModelGatewayMode.SYNTHETIC,
        provider_input_assembler: ProviderInputAssembler | None = None,
    ) -> None:
        self._registry = registry
        self._router = router
        self._recorder = recorder
        self._enabled_mode = enabled_mode
        self._provider_input_assembler = provider_input_assembler

    def list_capabilities(self) -> list[ModelGatewayCapability]:
        if self._enabled_mode == ModelGatewayMode.DISABLED:
            return []
        return self._registry.list()

    async def execute(
        self,
        request: ModelGatewayRequest,
        *,
        idempotency_key: str,
    ) -> ModelGatewayOutput:
        if (
            self._enabled_mode == ModelGatewayMode.DISABLED
            or request.mode == ModelGatewayMode.DISABLED
        ):
            raise ServiceError(
                code="gateway_disabled",
                message="Model Gateway 当前不可用。",
                category="internal",
                status_code=503,
            )
        if (
            request.mode == ModelGatewayMode.REAL
            and self._enabled_mode != ModelGatewayMode.REAL
        ):
            raise BusinessValidationError(
                "real_provider_not_enabled",
                "real Model Gateway 未由当前环境显式启用。",
                field="mode",
            )
        capability = self._registry.require(request.capability_id)
        assembled = None
        if request.mode == ModelGatewayMode.SYNTHETIC:
            assembled = assemble_input(
                request,
                capability,
                max_input_tokens=self.MAX_INPUT_TOKENS,
            )
        provider = self._router.route(request, capability)
        ensure_configured = getattr(provider, "ensure_configured", None)
        if request.mode == ModelGatewayMode.REAL and callable(ensure_configured):
            ensure_configured()
        reservation = self._recorder.reserve(
            request=request,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint(request),
            provider_id=provider.provider_id,
            lease_seconds=self.TIMEOUT_SECONDS + 5,
        )
        if reservation.action == "replay":
            assert reservation.output is not None
            return reservation.output
        if reservation.action == "failure":
            assert reservation.error is not None
            raise reservation.error
        if reservation.action == "wait":
            return await self._wait_for_existing(
                reservation.run_id,
                timeout_seconds=self.TIMEOUT_SECONDS + 5,
            )

        try:
            if request.mode == ModelGatewayMode.REAL:
                assembled = self._assemble_real_input(request)
            assert assembled is not None
            raw_output = await asyncio.wait_for(
                provider.execute(
                    request,
                    assembled,
                    max_output_tokens=self.MAX_OUTPUT_TOKENS,
                ),
                timeout=self.TIMEOUT_SECONDS,
            )
            output = (
                _validate_real_output(
                    raw_output,
                    request=request,
                    provider_id=provider.provider_id,
                )
                if request.mode == ModelGatewayMode.REAL
                else validate_output(
                    raw_output,
                    request=request,
                    provider_id=provider.provider_id,
                )
            ).model_copy(update={"run_id": reservation.run_id})
            # model_copy does not revalidate updates in Pydantic v2.
            output = ModelGatewayOutput.model_validate(output.model_dump())
            self._recorder.record_success(reservation.run_id, output)
            return output
        except asyncio.TimeoutError as exc:
            error, gateway_error = _gateway_failure(
                ModelGatewayErrorCode.TIMEOUT,
                "Model Gateway provider 在规定时间内未返回结果。",
                status_code=504,
            )
            self._recorder.record_failure(reservation.run_id, error, gateway_error)
            raise error from exc
        except ProviderRateLimitError as exc:
            error, gateway_error = _gateway_failure(
                ModelGatewayErrorCode.RATE_LIMITED,
                "Model Gateway provider 当前达到速率限制。",
                status_code=429,
                provider_status=429,
            )
            self._recorder.record_failure(reservation.run_id, error, gateway_error)
            raise error from exc
        except ProviderUnavailableError as exc:
            error, gateway_error = _gateway_failure(
                ModelGatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Model Gateway provider 当前不可用。",
                status_code=503,
            )
            self._recorder.record_failure(reservation.run_id, error, gateway_error)
            raise error from exc
        except ServiceError as error:
            code = (
                ModelGatewayErrorCode.INVALID_OUTPUT
                if error.code == "invalid_output"
                else ModelGatewayErrorCode.PROVIDER_UNAVAILABLE
            )
            gateway_error = ModelGatewayError(
                code=code,
                message=error.message,
                retryable=code in {
                    ModelGatewayErrorCode.RATE_LIMITED,
                    ModelGatewayErrorCode.TIMEOUT,
                    ModelGatewayErrorCode.PROVIDER_UNAVAILABLE,
                },
            )
            self._recorder.record_failure(reservation.run_id, error, gateway_error)
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error, gateway_error = _gateway_failure(
                ModelGatewayErrorCode.PROVIDER_UNAVAILABLE,
                "Model Gateway provider 当前不可用。",
                status_code=503,
            )
            self._recorder.record_failure(reservation.run_id, error, gateway_error)
            raise error from exc

    def _assemble_real_input(self, request: ModelGatewayRequest) -> AssembledGatewayInput:
        if self._provider_input_assembler is None:
            raise ServiceError(
                code="provider_not_configured",
                message="real providerInput 装配器尚未配置。",
                category="internal",
                status_code=503,
            )
        safe_context: dict[str, Any] = {
            "projectContext": request.project_context.model_dump(
                by_alias=True,
                mode="json",
            ),
            "fieldSchemas": [
                item.model_dump(by_alias=True, mode="json")
                for item in request.field_schemas
            ],
        }
        encoded = json.dumps(
            safe_context,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        estimated_tokens = max(1, (len(encoded) + 3) // 4)
        if estimated_tokens > self.MAX_INPUT_TOKENS:
            raise BusinessValidationError(
                "model_budget_exceeded",
                "组装后的输入超过 capability 预算。",
                details={
                    "estimatedInputTokens": estimated_tokens,
                    "maxInputTokens": self.MAX_INPUT_TOKENS,
                },
            )
        provider_input = dict(self._provider_input_assembler(request))
        return AssembledGatewayInput(
            payload={**safe_context, "providerInput": provider_input},
            input_hash=request.input_hash,
            estimated_input_tokens=estimated_tokens,
        )

    async def _wait_for_existing(
        self,
        run_id: str,
        *,
        timeout_seconds: float,
    ) -> ModelGatewayOutput:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            state = self._recorder.wait_for_terminal(run_id)
            if state.action == "replay":
                assert state.output is not None
                return state.output
            if state.action == "failure":
                assert state.error is not None
                raise state.error
            await asyncio.sleep(0.01)
        raise ServiceError(
            code="timeout",
            message="等待同一幂等 Model Gateway 请求完成时超时。",
            category="internal",
            status_code=504,
        )

    def get_run(self, project_id: str, run_id: str) -> ModelGatewayRunRecord:
        row = self._recorder._row(run_id)
        if row["project_id"] != project_id:
            raise NotFoundError(
                "model_run_not_found",
                "Model Gateway 运行记录不存在于当前项目。",
            )
        if ModelGatewayMode(row["mode"]) != ModelGatewayMode.REAL:
            return self._recorder.get_run(project_id, run_id)
        error = None
        if row["status"] == "failed":
            error = ModelGatewayError(
                code=row["error_code"],
                message=row["error_message"],
                retryable=bool(row["error_retryable"]),
                provider_status=row["error_provider_status"],
            )
        status = {
            "running": ModelGatewayRunStatus.RUNNING,
            "succeeded": ModelGatewayRunStatus.SUCCEEDED,
            "needs_review": ModelGatewayRunStatus.NEEDS_REVIEW,
            "failed": ModelGatewayRunStatus.FAILED,
        }[row["status"]]
        return ModelGatewayRunRecord(
            run_id=row["run_id"],
            request_id=row["request_id"],
            capability_id=row["capability_id"],
            mode=ModelGatewayMode.REAL,
            status=status,
            material_id=row["material_id"],
            material_version_id=row["material_version_id"],
            input_hash=row["input_hash"],
            provider_id=row["provider_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=(
                datetime.fromisoformat(row["finished_at"])
                if row["finished_at"]
                else None
            ),
            error=error,
            advisory_only=True,
            is_simulated=False,
            data_status=MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED,
            source=row["provider_id"],
            disclaimer=(
                "Model Gateway 真实 provider 运行元数据；不包含原件正文、Base64、"
                "绝对路径或凭据，结果仍须人工核验。"
            ),
        )

    def close(self) -> None:
        self._recorder.close()


def _gateway_failure(
    code: ModelGatewayErrorCode,
    message: str,
    *,
    status_code: int,
    provider_status: int | None = None,
) -> tuple[ServiceError, ModelGatewayError]:
    retryable = code in {
        ModelGatewayErrorCode.RATE_LIMITED,
        ModelGatewayErrorCode.TIMEOUT,
        ModelGatewayErrorCode.PROVIDER_UNAVAILABLE,
    }
    return (
        ServiceError(
            code=code.value,
            message=message,
            category="internal",
            status_code=status_code,
        ),
        ModelGatewayError(
            code=code,
            message=message,
            retryable=retryable,
            provider_status=provider_status,
        ),
    )


def _validate_real_output(
    raw_output: object,
    *,
    request: ModelGatewayRequest,
    provider_id: str,
) -> ModelGatewayOutput:
    try:
        output = ModelGatewayOutput.model_validate(raw_output)
        if output.request_id != request.request_id:
            raise ValueError("requestId mismatch")
        if output.capability_id != request.capability_id:
            raise ValueError("capabilityId mismatch")
        if output.mode != ModelGatewayMode.REAL or output.mode != request.mode:
            raise ValueError("mode mismatch")
        if output.material_id != request.material.material_id:
            raise ValueError("materialId mismatch")
        if output.material_version_id != request.material.material_version_id:
            raise ValueError("materialVersionId mismatch")
        if output.input_hash != request.input_hash:
            raise ValueError("inputHash mismatch")
        if output.source != provider_id or output.is_simulated is not False:
            raise ValueError("provider truth metadata mismatch")
        if output.result is not None:
            if output.result.project_id != request.material.project_id:
                raise ValueError("result projectId mismatch")
            if output.result.context_version != request.context_version:
                raise ValueError("result contextVersion mismatch")
            if output.result.data_classification != request.material.data_classification:
                raise ValueError("result dataClassification mismatch")
            allowed_fields = {item.field_key for item in request.field_schemas}
            if any(
                candidate.field_key not in allowed_fields
                for candidate in output.result.extracted_field_candidates
            ):
                raise ValueError("candidate fieldKey was not requested")
        return output
    except (ValidationError, ValueError, TypeError) as exc:
        raise ServiceError(
            code="invalid_output",
            message="Model Gateway provider 返回了不符合严格契约的结果。",
            category="internal",
            status_code=502,
        ) from exc


def create_model_gateway_service(
    database_path: str | Path,
    *,
    providers: tuple[ModelGatewayProviderPort, ...] | None = None,
    mode: ModelGatewayMode = ModelGatewayMode.SYNTHETIC,
    timeout_seconds: float | None = None,
    provider_input_assembler: ProviderInputAssembler | None = None,
    openai_provider: MaterialIntelligenceProviderPort | None = None,
) -> ModelGatewayOrchestrator:
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if providers is None:
        configured_providers: list[ModelGatewayProviderPort] = [SyntheticFakeProvider()]
        if mode == ModelGatewayMode.REAL:
            configured_providers.append(OpenAIResponsesGatewayProvider(openai_provider))
        providers = tuple(configured_providers)
    supported_modes = [ModelGatewayMode.SYNTHETIC]
    provider_id = "synthetic_fake"
    if mode == ModelGatewayMode.REAL:
        supported_modes.append(ModelGatewayMode.REAL)
        provider_id = next(
            (
                provider.provider_id
                for provider in providers
                if provider.is_simulated is False
            ),
            OPENAI_GATEWAY_PROVIDER_ID,
        )
    default_capability = CapabilityRegistry().list()[0]
    capability = ModelGatewayCapability.model_validate(
        {
            **default_capability.model_dump(by_alias=True, mode="json"),
            "providerId": provider_id,
            "supportedModes": [item.value for item in supported_modes],
        }
    )
    service = ModelGatewayOrchestrator(
        registry=CapabilityRegistry((capability,)),
        router=ProviderRouter(providers),
        recorder=RunRecorder(database_path),
        enabled_mode=mode,
        provider_input_assembler=provider_input_assembler,
    )
    if timeout_seconds is not None:
        service.TIMEOUT_SECONDS = timeout_seconds
    return service
