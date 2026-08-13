"""Internal, advisory-only harness for the frozen AI assist contract.

This module deliberately has no route, repository, or workbench-service
dependency.  It only validates a read-only context, calls a provider, and
validates the provider's advisory response.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from app.contracts.ai_assist import (
    AI_ASSIST_SCHEMA_VERSION,
    AiAssistContext,
    AiAssistErrorCode,
    AiAssistProviderPort,
    AiAssistRequest,
    AiAssistResult,
    validate_ai_assist_context,
    validate_ai_assist_result,
)
from app.contracts.errors import BusinessValidationError, ConflictError, ServiceError


@dataclass(frozen=True, slots=True)
class AiAssistHarnessConfig:
    """Runtime-only controls; this package neither persists nor caches output."""

    enabled: bool
    timeout_seconds: float

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


def canonical_ai_assist_input(
    request: AiAssistRequest,
    context: AiAssistContext,
) -> dict[str, Any]:
    """Return a deterministic, order-normalized provider input projection."""

    return _canonicalize(
        {
            "schemaVersion": AI_ASSIST_SCHEMA_VERSION,
            "request": request.model_dump(mode="json", by_alias=True),
            "context": context.model_dump(mode="json", by_alias=True),
        }
    )


def calculate_ai_assist_input_hash(
    request: AiAssistRequest,
    context: AiAssistContext,
) -> str:
    """Hash the complete read-only input using canonical JSON."""

    encoded = json.dumps(
        canonical_ai_assist_input(request, context),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ai_assist_cache_key(
    request: AiAssistRequest,
    context: AiAssistContext,
) -> str:
    """Return the future cache key without creating or consulting a cache."""

    return f"ai-assist:{calculate_ai_assist_input_hash(request, context)}"


async def execute_ai_assist(
    request: AiAssistRequest,
    context: AiAssistContext,
    provider: AiAssistProviderPort,
    config: AiAssistHarnessConfig,
) -> AiAssistResult:
    """Validate, invoke a provider once, and return only a valid advisory result."""

    _validate_context(request, context)
    if not config.enabled:
        raise BusinessValidationError(
            AiAssistErrorCode.AI_DISABLED.value,
            "AI 辅助能力当前未启用，请继续人工复核。",
        )

    input_hash = calculate_ai_assist_input_hash(request, context)
    try:
        raw_result = await asyncio.wait_for(
            provider.assist(request, context), timeout=config.timeout_seconds
        )
    except TimeoutError as error:
        raise ServiceError(
            code=AiAssistErrorCode.PROVIDER_TIMEOUT.value,
            message="AI provider 在规定时间内未返回结果。",
            category="internal",
            status_code=504,
        ) from error
    except asyncio.CancelledError:
        raise
    except Exception as error:
        raise ServiceError(
            code=AiAssistErrorCode.PROVIDER_UNAVAILABLE.value,
            message="AI provider 当前不可用。",
            category="internal",
            status_code=503,
        ) from error

    return _validate_result(request, raw_result, input_hash)


def _validate_context(request: AiAssistRequest, context: AiAssistContext) -> None:
    try:
        validate_ai_assist_context(request, context)
    except ValueError as error:
        if str(error) == "contextVersion conflict":
            raise ConflictError(
                AiAssistErrorCode.CONTEXT_VERSION_CONFLICT.value,
                "AI 上下文版本与请求不一致，请刷新后重试。",
            ) from error
        raise BusinessValidationError(
            AiAssistErrorCode.EVIDENCE_CONTEXT_INVALID.value,
            "AI 只读证据上下文不在请求授权范围内。",
        ) from error


def _validate_result(
    request: AiAssistRequest,
    raw_result: object,
    input_hash: str,
) -> AiAssistResult:
    try:
        result = AiAssistResult.model_validate(raw_result)
        validate_ai_assist_result(request, result)
        if result.input_hash != input_hash:
            raise ValueError("result inputHash does not match the canonical input")
    except (ValidationError, ValueError, TypeError) as error:
        raise ServiceError(
            code=AiAssistErrorCode.INVALID_MODEL_OUTPUT.value,
            message="AI provider 返回了不符合冻结契约的结果。",
            category="internal",
            status_code=502,
        ) from error
    return result


def _canonicalize(value: Any) -> Any:
    """Recursively sort mappings and collections whose order has no cache meaning."""

    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items())}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        normalized = [_canonicalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
        )
    return value
