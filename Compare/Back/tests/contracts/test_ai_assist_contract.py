from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.contracts.ai_assist import (
    AI_ASSIST_SIMULATION_DISCLAIMER,
    AiAssistContext,
    AiAssistErrorCode,
    AiAssistRequest,
    AiAssistResult,
    AiAssistStatus,
    AiAssistTaskType,
    validate_ai_assist_context,
    validate_ai_assist_result,
)


def _target(
    evidence_ref: str = "ev-sim-1",
    *,
    evidence_refs: list[str] | None = None,
    fact_version_id: str | None = "fact-sim-1-v1",
) -> dict[str, object]:
    return {
        "evidenceRef": evidence_ref,
        "evidenceRefs": evidence_refs,
        "dimensionId": "compliance",
        "reviewTargetId": "review-sim-1",
        "factVersionId": fact_version_id,
        "unavailableReason": None,
    }


def _request_payload() -> dict[str, object]:
    return {
        "projectId": "project-sim-001",
        "taskType": "material_summary",
        "actor": "risk",
        "instruction": "概括已提供材料并标出仍需人工复核的内容。",
        "evidenceTargets": [_target()],
        "factVersionIds": ["fact-sim-1-v1"],
        "policyResultIds": ["policy-sim-1-v1"],
        "contextVersion": "ctx-sim-001-v1",
        "locale": "zh-CN",
    }


def _citation() -> dict[str, object]:
    return {
        "evidenceRef": "ev-sim-1",
        "dimensionId": "compliance",
        "reviewTargetId": "review-sim-1",
        "factVersionId": "fact-sim-1-v1",
    }


def _result_payload() -> dict[str, object]:
    return {
        "taskType": "material_summary",
        "status": "completed",
        "advisoryOnly": True,
        "summary": "模拟材料显示登记信息已提供，仍需人工复核版本一致性。",
        "observations": ["当前文字仅来自请求声明的模拟证据上下文。"],
        "questions": [],
        "proposedReviewText": None,
        "citations": [_citation()],
        "modelInfo": {
            "provider": "contract-example-provider",
            "model": "simulated-no-inference",
            "modelVersion": "c0",
        },
        "inputHash": "a" * 64,
        "schemaVersion": "1.0",
        "isSimulated": True,
        "disclaimer": AI_ASSIST_SIMULATION_DISCLAIMER,
    }


def test_task_status_and_error_enums_are_frozen() -> None:
    assert {item.value for item in AiAssistTaskType} == {
        "material_summary",
        "evidence_gap_questions",
        "review_draft",
        "indicator_explanation",
    }
    assert {item.value for item in AiAssistStatus} == {
        "completed",
        "needs_review",
        "unavailable",
    }
    assert {item.value for item in AiAssistErrorCode} == {
        "ai_disabled",
        "provider_unavailable",
        "provider_timeout",
        "invalid_model_output",
        "context_version_conflict",
        "evidence_context_invalid",
    }


@pytest.mark.parametrize("instruction", ["", "   ", "\n"])
def test_request_rejects_empty_instruction(instruction: str) -> None:
    payload = _request_payload()
    payload["instruction"] = instruction
    with pytest.raises(ValidationError):
        AiAssistRequest.model_validate(payload)


def test_request_rejects_overlong_instruction() -> None:
    payload = _request_payload()
    payload["instruction"] = "审" * 4001
    with pytest.raises(ValidationError):
        AiAssistRequest.model_validate(payload)


def test_request_rejects_empty_evidence_targets() -> None:
    payload = _request_payload()
    payload["evidenceTargets"] = []
    with pytest.raises(ValidationError):
        AiAssistRequest.model_validate(payload)


def test_request_rejects_duplicate_or_inconsistent_targets() -> None:
    duplicate = _request_payload()
    duplicate["evidenceTargets"] = [_target(), _target()]
    with pytest.raises(ValidationError, match="duplicates"):
        AiAssistRequest.model_validate(duplicate)

    inconsistent = _request_payload()
    inconsistent["evidenceTargets"] = [_target(fact_version_id="fact-other-v1")]
    with pytest.raises(ValidationError, match="declared in factVersionIds"):
        AiAssistRequest.model_validate(inconsistent)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("projectId", ""),
        ("contextVersion", " "),
        ("factVersionIds", [""]),
        ("policyResultIds", ["policy-sim-1-v1", "policy-sim-1-v1"]),
    ],
)
def test_request_rejects_invalid_or_duplicate_ids(field: str, value: object) -> None:
    payload = _request_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        AiAssistRequest.model_validate(payload)


def test_request_requires_complete_ordered_evidence_group() -> None:
    payload = _request_payload()
    payload["evidenceTargets"] = [
        _target("ev-sim-1", evidence_refs=["ev-sim-1", "ev-sim-2"]),
        _target("ev-sim-2", evidence_refs=["ev-sim-2", "ev-sim-1"]),
    ]
    with pytest.raises(ValidationError, match="complete ordered target group"):
        AiAssistRequest.model_validate(payload)


def test_advisory_only_is_literal_true() -> None:
    payload = _result_payload()
    payload["advisoryOnly"] = False
    with pytest.raises(ValidationError):
        AiAssistResult.model_validate(payload)
    schema = AiAssistResult.model_json_schema(by_alias=True)
    assert schema["properties"]["advisoryOnly"]["const"] is True


def test_review_draft_status_controls_proposed_text() -> None:
    payload = _result_payload()
    payload["taskType"] = "review_draft"
    with pytest.raises(ValidationError, match="requires proposedReviewText"):
        AiAssistResult.model_validate(payload)

    payload["proposedReviewText"] = "建议由人工核对材料版本后形成正式审查意见。"
    assert AiAssistResult.model_validate(payload).proposed_review_text is not None

    payload["status"] = "needs_review"
    with pytest.raises(ValidationError, match="cannot present a review draft"):
        AiAssistResult.model_validate(payload)


def test_non_review_task_rejects_proposed_text() -> None:
    payload = _result_payload()
    payload["proposedReviewText"] = "不应出现的审查草稿"
    with pytest.raises(ValidationError, match="only allowed for review_draft"):
        AiAssistResult.model_validate(payload)


def test_unavailable_is_not_a_fabricated_success() -> None:
    payload = _result_payload()
    payload.update(
        {
            "status": "unavailable",
            "summary": "辅助能力当前不可用，请继续人工审查。",
            "observations": [],
            "citations": [],
            "modelInfo": None,
        }
    )
    result = AiAssistResult.model_validate(payload)
    assert result.status == AiAssistStatus.UNAVAILABLE

    payload["observations"] = ["伪造的降级结果"]
    with pytest.raises(ValidationError, match="cannot contain generated content"):
        AiAssistResult.model_validate(payload)


def test_completed_requires_citation_and_model_info() -> None:
    payload = _result_payload()
    payload["citations"] = []
    with pytest.raises(ValidationError, match="requires at least one citation"):
        AiAssistResult.model_validate(payload)

    payload = _result_payload()
    payload["modelInfo"] = None
    with pytest.raises(ValidationError, match="requires modelInfo"):
        AiAssistResult.model_validate(payload)


def test_completed_gap_task_requires_questions() -> None:
    payload = _result_payload()
    payload["taskType"] = "evidence_gap_questions"
    with pytest.raises(ValidationError, match="requires questions"):
        AiAssistResult.model_validate(payload)


def test_context_must_match_request_scope_and_version() -> None:
    request = AiAssistRequest.model_validate(_request_payload())
    context_payload = {
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
    context = AiAssistContext.model_validate(context_payload)
    assert validate_ai_assist_context(request, context) is context

    invalid = deepcopy(context_payload)
    invalid["contextVersion"] = "ctx-stale"
    with pytest.raises(ValueError, match="contextVersion conflict"):
        validate_ai_assist_context(request, AiAssistContext.model_validate(invalid))


def test_citations_must_match_input_target_stable_tuple() -> None:
    request = AiAssistRequest.model_validate(_request_payload())
    result = AiAssistResult.model_validate(_result_payload())
    assert validate_ai_assist_result(request, result) is result

    payload = _result_payload()
    payload["citations"][0]["evidenceRef"] = "ev-invented"
    invented = AiAssistResult.model_validate(payload)
    with pytest.raises(ValueError, match="input ReviewEvidenceTarget"):
        validate_ai_assist_result(request, invented)


def test_result_schema_excludes_authoritative_fields() -> None:
    forbidden = {
        "factValue",
        "scoreGrade",
        "decisionGrade",
        "confidence",
        "hardConstraintResults",
        "approval",
        "transition",
    }
    schema_text = str(AiAssistResult.model_json_schema(by_alias=True))
    for field in forbidden:
        assert field not in schema_text


def test_simulation_boundary_rejects_false() -> None:
    payload = _result_payload()
    payload["isSimulated"] = False
    with pytest.raises(ValidationError, match="must remain simulated"):
        AiAssistResult.model_validate(payload)
