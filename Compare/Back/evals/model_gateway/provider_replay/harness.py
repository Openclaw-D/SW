from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.contracts.material_intelligence import (
    MaterialIntelligenceRequest,
    MaterialIntelligenceResult,
)
from app.contracts.model_gateway import (
    ModelGatewayMode,
    ModelGatewayOutput,
    ModelGatewayRequest,
    ModelGatewayRunRecord,
)
from app.services.model_gateway.orchestrator import create_model_gateway_service
from app.services.model_gateway.provider_router import OpenAIResponsesGatewayProvider


RawMaterialIntelligenceResult = MaterialIntelligenceResult | Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderReplayEvidence:
    """Observable ownership evidence; never includes provider input or raw output."""

    first_output: ModelGatewayOutput
    replay_output: ModelGatewayOutput
    run_record: ModelGatewayRunRecord
    first_execution_provider_calls: int
    replay_provider_calls: int
    observed_input_hashes: tuple[str, ...]


class _ExplicitResultProvider:
    """Direct adapter seam: the caller supplies only the model result payload."""

    def __init__(self, raw_result: RawMaterialIntelligenceResult) -> None:
        self._raw_result = raw_result
        self.call_count = 0
        self.observed_input_hashes: list[str] = []

    async def analyze(
        self,
        request: MaterialIntelligenceRequest,
        context: Mapping[str, Any],
        input_hash: str,
    ) -> object:
        del request, context
        self.call_count += 1
        self.observed_input_hashes.append(input_hash)
        return self._raw_result


class ProviderReplayHarness:
    """Run explicit raw results through the production adapter and gateway.

    The harness performs no path discovery and reads no eval artifact. The caller
    owns every input, including the SQLite path, request, provider payload and raw
    ``MaterialIntelligenceResult``. The injected provider cannot access the
    network and returns the raw result unchanged; canonical request binding,
    envelope construction, validation, recording and idempotency therefore stay
    owned by the production adapter/gateway under test.
    """

    def __init__(
        self,
        *,
        database_path: str | Path,
        request: ModelGatewayRequest,
        raw_result: RawMaterialIntelligenceResult,
        provider_input: Mapping[str, str],
    ) -> None:
        if request.mode != ModelGatewayMode.REAL:
            raise ValueError("provider replay requires an explicit real request")
        self.request = request
        self._provider = _ExplicitResultProvider(raw_result)
        adapter = OpenAIResponsesGatewayProvider(self._provider)
        frozen_provider_input = dict(provider_input)
        self._service = create_model_gateway_service(
            database_path,
            providers=(adapter,),
            mode=ModelGatewayMode.REAL,
            provider_input_assembler=lambda _request: dict(frozen_provider_input),
        )

    @property
    def provider_call_count(self) -> int:
        return self._provider.call_count

    @property
    def observed_input_hashes(self) -> tuple[str, ...]:
        return tuple(self._provider.observed_input_hashes)

    async def execute(self, *, idempotency_key: str) -> ModelGatewayOutput:
        return await self._service.execute(
            self.request,
            idempotency_key=idempotency_key,
        )

    def get_run(self, run_id: str) -> ModelGatewayRunRecord:
        return self._service.get_run(self.request.material.project_id, run_id)

    async def execute_and_replay(
        self,
        *,
        idempotency_key: str,
    ) -> ProviderReplayEvidence:
        before_first = self.provider_call_count
        first = await self.execute(idempotency_key=idempotency_key)
        after_first = self.provider_call_count
        replay = await self.execute(idempotency_key=idempotency_key)
        after_replay = self.provider_call_count
        return ProviderReplayEvidence(
            first_output=first,
            replay_output=replay,
            run_record=self.get_run(first.run_id),
            first_execution_provider_calls=after_first - before_first,
            replay_provider_calls=after_replay - after_first,
            observed_input_hashes=self.observed_input_hashes,
        )

    def close(self) -> None:
        self._service.close()

    def __enter__(self) -> "ProviderReplayHarness":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


__all__ = ["ProviderReplayEvidence", "ProviderReplayHarness"]
