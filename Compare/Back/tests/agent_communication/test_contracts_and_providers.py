from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.contracts.agent_communication import (
    AGENT_COMMUNICATION_SCHEMA_VERSION,
    AgentChatMessageRequest,
    AgentFocusEvent,
    AgentMessage,
    AgentProviderContext,
    AgentRole,
    AgentThread,
    AgentTurnRequest,
    GeneratedAgentContent,
    validate_generated_agent_content,
)
from app.ports.agent_communication import AgentAssembledInput
from app.providers.openai_agent_responses import (
    OpenAIAgentResponsesConfig,
    OpenAIAgentResponsesProvider,
    parse_openai_agent_response,
    serialize_openai_agent_request,
)
from app.providers.openai_responses import (
    OpenAIProviderResponseError,
    ResponsesHttpResponse,
)
from app.services.agent_communication.synthetic_provider import SyntheticAgentProvider


def _request(**updates) -> AgentTurnRequest:
    payload = {
        "instruction": "请复核当前材料缺口",
        "evidenceTargets": [],
        "expectedVersion": 1,
        "locale": "zh-CN",
    }
    payload.update(updates)
    return AgentTurnRequest.model_validate(payload)


def _context(role: AgentRole = AgentRole.BUSINESS) -> AgentProviderContext:
    return AgentProviderContext.model_validate(
        {
            "projectId": "project-a",
            "threadId": "agent-thread-" + "a" * 32,
            "targetRole": role.value,
            "contextVersion": "1" * 64,
            "projectSummary": {
                "projectId": "project-a",
                "name": "脱敏项目",
                "summary": "材料待补，当前仅供人工复核。",
                "isSimulated": True,
            },
            "dimensionSummaries": [],
            "policyResults": [],
            "selectedEvidence": [],
            "selectedFacts": [],
            "approvalState": {
                "version": 1,
                "status": "draft",
                "hardGateStatus": "manual_review",
                "blockingRuleIds": [],
                "riskVeto": False,
                "summary": "只读审批状态。",
            },
            "recentVisibleMessages": [],
            "citationAllowlist": [],
            "currentInstruction": "请复核当前材料缺口",
            "isContextSimulated": True,
            "disclaimer": "仅供 advisory Agent。",
        }
    )


def _assembled() -> AgentAssembledInput:
    return AgentAssembledInput(
        payload={"request": {}, "context": {}},
        input_hash="2" * 64,
        estimated_input_tokens=10,
    )


def _generated(reply: str = "当前材料需人工复核。") -> dict[str, object]:
    return {
        "replyText": reply,
        "observations": ["现有材料仍有缺口。"],
        "questions": [],
        "citations": [],
        "scopeStatus": "in_scope",
        "disposition": "answer",
    }


def _response(
    generated: dict[str, object],
    *,
    model: str = "gpt-5.5",
    output_type: str = "message",
) -> bytes:
    output: dict[str, object]
    if output_type == "message":
        output = {
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps(generated)}],
        }
    else:
        output = {"type": output_type, "name": "forbidden_tool"}
    return json.dumps(
        {
            "id": "resp-test",
            "status": "completed",
            "model": model,
            "output": [output],
        }
    ).encode()


def test_lightweight_group_chat_contract_keeps_agent_routing_explicit() -> None:
    assert AGENT_COMMUNICATION_SCHEMA_VERSION == "2.0"
    assert set(GeneratedAgentContent.model_fields) == {
        "reply_text",
        "observations",
        "questions",
        "citations",
        "scope_status",
        "disposition",
    }
    assert set(AgentTurnRequest.model_fields) == {
        "instruction",
        "target_agent_role",
        "source_message_id",
        "reply_to_message_id",
        "evidence_targets",
        "expected_version",
        "locale",
        "response_depth",
        "response_focus",
        "custom_guidance",
    }
    schema_text = json.dumps(AgentTurnRequest.model_json_schema(by_alias=True))
    for removed in (
        "targetRole",
        "coordinationMode",
        "maxAgentSteps",
        "expectedGovernanceVersion",
        "suggestedHandoffs",
        "channelRole",
        "audienceSnapshot",
    ):
        assert removed not in schema_text
    message = AgentChatMessageRequest.model_validate(
        {"content": "先补一条正常讨论，不触发 Agent。", "locale": "zh-CN"}
    )
    assert message.reply_to_message_id is None
    with pytest.raises(ValidationError):
        _request(targetAgentRole="risk")


def test_thread_focus_event_and_advisory_message_are_strict() -> None:
    thread = AgentThread.model_validate(
        {
            "id": "agent-thread-" + "a" * 32,
            "projectId": "project-a",
            "title": "首审协作",
            "version": 1,
            "status": "active",
            "focusRole": "business",
            "createdByRole": "leadership",
            "closedReason": None,
            "createdAt": "2026-08-13T00:00:00Z",
            "updatedAt": "2026-08-13T00:00:00Z",
        }
    )
    assert thread.focus_role == AgentRole.BUSINESS
    event = AgentFocusEvent.model_validate(
        {
            "id": "agent-focus-" + "b" * 32,
            "projectId": "project-a",
            "threadId": thread.id,
            "sequence": 1,
            "kind": "thread_created",
            "fromFocusRole": None,
            "toFocusRole": "business",
            "actorRole": "leadership",
            "reason": "默认业务焦点。",
            "expectedVersion": 0,
            "resultingVersion": 1,
            "createdAt": "2026-08-13T00:00:00Z",
            "immutable": True,
        }
    )
    assert event.immutable is True
    message = {
        "id": "agent-message-" + "c" * 32,
        "projectId": "project-a",
        "threadId": thread.id,
        "sequence": 1,
        "role": "business",
        "authorType": "human",
        "kind": "user_input",
        "content": "请复核",
        "citations": [],
        "generatedContent": None,
        "execution": None,
        "replyToMessageId": None,
        "runId": "agent-run-" + "d" * 32,
        "createdAt": "2026-08-13T00:00:00Z",
        "immutable": True,
        "advisoryOnly": True,
        "isSimulated": False,
    }
    AgentMessage.model_validate(message)
    message["advisoryOnly"] = False
    with pytest.raises(ValidationError):
        AgentMessage.model_validate(message)


@pytest.mark.parametrize(
    "claim",
    [
        "我已批准本项目。",
        "本项目已拒绝。",
        "审批结论：通过，可以放款。",
        "该项目符合放款条件，批准融资。",
        "风险审查结论为通过。",
        "我已将该证据确认为正式事实。",
        "系统已解除正式 hard gate。",
        "I hereby approve this financing request.",
        "hard gate has been overridden.",
    ],
)
def test_generated_authority_claims_fail_closed(claim: str) -> None:
    content = GeneratedAgentContent.model_validate(_generated(claim))
    with pytest.raises(ValueError, match="authority claim"):
        validate_generated_agent_content(AgentRole.BUSINESS, _context(), content)


@pytest.mark.parametrize(
    "advisory_text",
    [
        "建议补齐流水后，再由人工审批人判断是否通过。",
        "当前材料不足，尚未形成风险审查结论。",
        "不能批准融资，也不得绕过 hard gate。",
        "只有满足制度条件并经人工审批后，才可进入放款流程。",
        "材料原文写道：“审批结论：通过”，该引文仍需人工核验。",
        "请人工确认该信息能否作为正式事实，本 Agent 不作确权。",
        "请人工确认是否审批通过，本 Agent 仅提供材料整理。",
    ],
)
def test_advisory_negation_conditions_and_quotes_remain_allowed(
    advisory_text: str,
) -> None:
    content = GeneratedAgentContent.model_validate(_generated(advisory_text))
    validate_generated_agent_content(AgentRole.BUSINESS, _context(), content)


def test_synthetic_provider_is_single_step_dynamic_and_advisory() -> None:
    provider = SyntheticAgentProvider()
    content = asyncio.run(
        provider.generate(
            AgentRole.BUSINESS,
            _request(),
            _context(),
            _assembled(),
            max_output_tokens=512,
        )
    )
    assert provider.call_count == 1
    assert "补" in content.reply_text or content.questions
    assert "suggested_handoffs" not in type(content).model_fields


def test_synthetic_risk_reply_locates_blocking_rules_and_next_action() -> None:
    provider = SyntheticAgentProvider()
    request = _request(instruction="这条制度结果是什么意思？")
    context_payload = _context(AgentRole.RISK).model_dump(by_alias=True)
    context_payload["currentInstruction"] = request.instruction
    context_payload["approvalState"] = {
        "version": 1,
        "status": "draft",
        "hardGateStatus": "block",
        "blockingRuleIds": ["HG-OWNERSHIP"],
        "riskVeto": False,
        "summary": "主体关系尚未满足制度条件。",
    }
    context_payload["policyResults"] = [
        {
            "policyResultId": "policy-ownership",
            "ruleId": "HG-OWNERSHIP",
            "title": "主体关系核验",
            "result": "block",
            "explanation": "实控人关系缺少可定位原件。",
            "nextAction": "补充股权结构原件并标注页码。",
            "citations": [],
        }
    ]
    context = AgentProviderContext.model_validate(context_payload)
    content = asyncio.run(
        provider.generate(
            AgentRole.RISK,
            request,
            context,
            _assembled(),
            max_output_tokens=512,
        )
    )
    assert content.disposition.value == "escalate"
    assert "HG-OWNERSHIP" in content.reply_text
    assert "主体关系核验" in content.reply_text
    assert "补充股权结构原件并标注页码" in content.reply_text
    assert "这条制度结果" in content.reply_text
    assert content.questions == ["请业务侧按上述动作补齐或核对后，再由人工复核 HG-OWNERSHIP。"]


def test_openai_request_is_strict_single_focus_and_has_no_tool_surface() -> None:
    payload = serialize_openai_agent_request(
        AgentRole.BUSINESS,
        _request(),
        _context(),
        _assembled(),
        model="gpt-5.5",
        max_output_tokens=512,
    )
    schema = payload["text"]["format"]["schema"]
    schema_text = json.dumps(schema)
    assert payload["tools"] == []
    assert payload["tool_choice"] == "none"
    assert "suggestedHandoffs" not in schema_text
    assert "focus state" in payload["instructions"]


def test_openai_parser_rejects_tool_model_authority_and_foreign_shape() -> None:
    context = _context()
    with pytest.raises(OpenAIProviderResponseError) as tool:
        parse_openai_agent_response(
            _response(_generated(), output_type="function_call"),
            role=AgentRole.BUSINESS,
            context=context,
            expected_model="gpt-5.5",
        )
    assert tool.value.code == "provider_tool_attempted"

    with pytest.raises(OpenAIProviderResponseError) as model:
        parse_openai_agent_response(
            _response(_generated(), model="different-model"),
            role=AgentRole.BUSINESS,
            context=context,
            expected_model="gpt-5.5",
        )
    assert model.value.code == "provider_model_identity_unverified"

    with pytest.raises(OpenAIProviderResponseError) as authority:
        parse_openai_agent_response(
            _response(_generated("我已批准本项目。")),
            role=AgentRole.BUSINESS,
            context=context,
            expected_model="gpt-5.5",
        )
    assert authority.value.code == "provider_agent_content_invalid"

    structural = _generated()
    structural["approval"] = {"status": "completed"}
    with pytest.raises(OpenAIProviderResponseError):
        parse_openai_agent_response(
            _response(structural),
            role=AgentRole.BUSINESS,
            context=context,
            expected_model="gpt-5.5",
        )


class RetryTransport:
    def __init__(self) -> None:
        self.calls = 0

    async def post_json(self, url, headers, payload, *, timeout_seconds):
        del url, headers, payload, timeout_seconds
        self.calls += 1
        if self.calls == 1:
            return ResponsesHttpResponse(429, {}, b"{}")
        return ResponsesHttpResponse(200, {}, _response(_generated()))


def test_openai_provider_retries_rate_limit_without_synthetic_fallback() -> None:
    transport = RetryTransport()
    provider = OpenAIAgentResponsesProvider(
        OpenAIAgentResponsesConfig(
            api_key="placeholder",
            model="gpt-5.5",
            max_retries=1,
            retry_base_seconds=0,
        ),
        transport=transport,
    )
    content = asyncio.run(
        provider.generate(
            AgentRole.BUSINESS,
            _request(),
            _context(),
            _assembled(),
            max_output_tokens=512,
        )
    )
    assert transport.calls == 2
    assert content.reply_text == "当前材料需人工复核。"
    assert provider.is_simulated is False
