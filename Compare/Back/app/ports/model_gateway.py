from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from app.contracts.model_gateway import (
    ModelGatewayCapability,
    ModelGatewayOutput,
    ModelGatewayRequest,
    ModelGatewayRunRecord,
)


@dataclass(frozen=True, slots=True)
class AssembledGatewayInput:
    """Provider input assembled only from the frozen, answer-free contract."""

    payload: Mapping[str, Any]
    input_hash: str
    estimated_input_tokens: int


class ProviderExecutionError(Exception):
    """Base exception for stable provider failure translation."""


class ProviderRateLimitError(ProviderExecutionError):
    pass


class ProviderUnavailableError(ProviderExecutionError):
    pass


@runtime_checkable
class ModelGatewayProviderPort(Protocol):
    provider_id: str
    model_id: str
    is_simulated: bool
    capabilities: frozenset[str]

    async def execute(
        self,
        request: ModelGatewayRequest,
        assembled_input: AssembledGatewayInput,
        *,
        max_output_tokens: int,
    ) -> ModelGatewayOutput | Mapping[str, Any]: ...


@runtime_checkable
class ModelGatewayServicePort(Protocol):
    def list_capabilities(self) -> list[ModelGatewayCapability]: ...

    async def execute(
        self,
        request: ModelGatewayRequest,
        *,
        idempotency_key: str,
    ) -> ModelGatewayOutput: ...

    def get_run(self, project_id: str, run_id: str) -> ModelGatewayRunRecord: ...

    def close(self) -> None: ...
