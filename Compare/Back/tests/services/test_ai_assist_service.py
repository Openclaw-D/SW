from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest

from app.contracts.ai_assist import (
    AI_ASSIST_SIMULATION_DISCLAIMER,
    AiAssistContext,
    AiAssistRequest,
    AiAssistResult,
)
from app.contracts.errors import ServiceError
from app.services.ai_assist import (
    AiAssistHarnessConfig,
    ai_assist_cache_key,
    calculate_ai_assist_input_hash,
    execute_ai_assist,
)


def _target(evidence_ref: str = "ev-sim-1") -> dict[str, object]:
    return {
        "evidenceRef": evidence_ref,
        "evidenceRefs": [evidence_ref],
        "dimensionId": "compliance",
        "reviewTargetId": "review-sim-1",
        "factVersionId": "fact-sim-1-v1",
        "unavailableReason": None,
    }


def _request() -> AiAssistRequest:
    return AiAssistRequest.model_validate(
        {
            "projectId": "project-sim-001",
            "taskType": "material_summary",
            "actor": "risk",
            "instruction": "概括模拟材料并标出人工复核点。",
            "evidenceTargets": [_target()],
            "factVersionIds": ["fact-sim-1-v1"],
            "policyResultIds": ["policy-sim-1-v1"],
            "contextVersion": "ctx-sim-001-v1",
        }
    )


def _context(request: AiAssistRequest) -> AiAssistContext:
    return AiAssistContext.model_validate(
        {
            "projectId": request.project_id,
            "contextVersion": request.context_version,
            "items": [
                {
                    "sourceType": "evidence",
                    "sourceId": "ev-sim-1",
                    "text": "完整脱敏模拟材料片段。",
                    "evidenceTarget": _target(),
                },
                {
                    "sourceType": "fact",
                    "sourceId": "fact-sim-1-v1",
                    "text": "由现有事实版本投影的只读模拟说明。",
                    "evidenceTarget": None,
                },
            ],
            "isSimulated": True,
            "disclaimer": AI_ASSIST_SIMULATION_DISCLAIMER,
        }
    )


def _result(request: AiAssistRequest, context: AiAssistContext, **changes: object) -> AiAssistResult:
    payload: dict[str, object] = {
        "taskType": request.task_type,
        "status": "completed",
        "advisoryOnly": True,
        "summary": "登记信息已提供，但材料版本仍需人工复核。",
        "observations": ["该内容只来自授权的脱敏模拟上下文。"],
        "questions": [],
        "proposedReviewText": None,
        "citations": [
            {
                "evidenceRef": "ev-sim-1",
                "dimensionId": "compliance",
                "reviewTargetId": "review-sim-1",
                "factVersionId": "fact-sim-1-v1",
            }
        ],
        "modelInfo": {"provider": "fake", "model": "test", "modelVersion": "1"},
        "inputHash": calculate_ai_assist_input_hash(request, context),
        "schemaVersion": "1.0",
        "isSimulated": True,
        "disclaimer": AI_ASSIST_SIMULATION_DISCLAIMER,
    }
    payload.update(changes)
    return AiAssistResult.model_validate(payload)


@dataclass
class FakeProvider:
    response: object | None = None
    error: Exception | None = None
    delay_seconds: float = 0
    calls: int = 0

    async def assist(self, request: AiAssistRequest, context: AiAssistContext) -> AiAssistResult:
        self.calls += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return self.response  # type: ignore[return-value]


def _run(
    request: AiAssistRequest,
    context: AiAssistContext,
    provider: FakeProvider,
    *,
    enabled: bool = True,
    timeout_seconds: float = 0.1,
) -> AiAssistResult:
    return asyncio.run(
        execute_ai_assist(
            request,
            context,
            provider,
            AiAssistHarnessConfig(enabled=enabled, timeout_seconds=timeout_seconds),
        )
    )


def _assert_error(code: str, action: object) -> None:
    with pytest.raises(ServiceError) as captured:
        action()  # type: ignore[operator]
    assert captured.value.code == code


def test_success_is_advisory_only_and_does_not_have_core_write_dependencies() -> None:
    request = _request()
    context = _context(request)
    provider = FakeProvider(response=_result(request, context))

    result = _run(request, context, provider)

    assert result.advisory_only is True
    assert result.input_hash == calculate_ai_assist_input_hash(request, context)
    assert provider.calls == 1
    # The harness has no core service/repository parameter or import: provider is
    # its sole effect boundary, so Fact/Evidence/Policy/Approval/Review cannot write.


def test_needs_review_is_returned_without_fabricating_completed_output() -> None:
    request = _request()
    context = _context(request)
    response = _result(
        request,
        context,
        status="needs_review",
        citations=[],
        observations=[],
        questions=["请人工确认材料版本是否为当前有效版本。"],
    )

    assert _run(request, context, FakeProvider(response=response)).status == "needs_review"


def test_disabled_does_not_call_provider() -> None:
    request = _request()
    context = _context(request)
    provider = FakeProvider(response=_result(request, context))

    _assert_error("ai_disabled", lambda: _run(request, context, provider, enabled=False))

    assert provider.calls == 0


def test_timeout_and_provider_error_have_stable_codes() -> None:
    request = _request()
    context = _context(request)
    _assert_error(
        "provider_timeout",
        lambda: _run(
            request,
            context,
            FakeProvider(delay_seconds=0.02),
            timeout_seconds=0.001,
        ),
    )
    _assert_error(
        "provider_unavailable",
        lambda: _run(request, context, FakeProvider(error=RuntimeError("offline"))),
    )


def test_malformed_output_and_request_external_citation_are_rejected() -> None:
    request = _request()
    context = _context(request)
    _assert_error(
        "invalid_model_output",
        lambda: _run(request, context, FakeProvider(response={"summary": "missing fields"})),
    )

    foreign = _result(request, context).model_dump(mode="json", by_alias=True)
    foreign["citations"][0]["evidenceRef"] = "ev-not-requested"  # type: ignore[index]
    # Re-validating the result makes it a syntactically valid model whose citation
    # remains outside the request's authoritative evidence target.
    _assert_error(
        "invalid_model_output",
        lambda: _run(
            request,
            context,
            FakeProvider(response=AiAssistResult.model_validate(foreign)),
        ),
    )


def test_context_conflict_and_out_of_scope_evidence_are_rejected_before_provider() -> None:
    request = _request()
    stale = _context(request).model_copy(update={"context_version": "ctx-stale"})
    provider = FakeProvider()

    _assert_error("context_version_conflict", lambda: _run(request, stale, provider))
    assert provider.calls == 0

    invalid_payload = _context(request).model_dump(mode="json", by_alias=True)
    invalid_payload["items"][0]["evidenceTarget"]["evidenceRef"] = "ev-other"  # type: ignore[index]
    invalid_payload["items"][0]["evidenceTarget"]["evidenceRefs"] = ["ev-other"]  # type: ignore[index]
    invalid_payload["items"][0]["sourceId"] = "ev-other"  # type: ignore[index]
    invalid = AiAssistContext.model_validate(invalid_payload)
    _assert_error("evidence_context_invalid", lambda: _run(request, invalid, provider))
    assert provider.calls == 0


def test_input_hash_and_cache_key_are_stable_across_input_order() -> None:
    request = _request()
    context = _context(request)
    request_payload = request.model_dump(mode="json", by_alias=True)
    request_payload["factVersionIds"] = ["fact-sim-1-v1"]
    request_payload["policyResultIds"] = ["policy-sim-1-v1"]
    reordered_request = AiAssistRequest.model_validate(request_payload)

    context_payload: dict[str, Any] = deepcopy(context.model_dump(mode="json", by_alias=True))
    context_payload["items"].reverse()
    reordered_context = AiAssistContext.model_validate(context_payload)

    assert calculate_ai_assist_input_hash(request, context) == calculate_ai_assist_input_hash(
        reordered_request, reordered_context
    )
    assert ai_assist_cache_key(request, context) == ai_assist_cache_key(
        reordered_request, reordered_context
    )
