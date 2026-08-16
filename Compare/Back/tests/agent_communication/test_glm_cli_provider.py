from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts.agent_communication import (
    AgentDataStatus,
    AgentMode,
    AgentProviderContext,
    AgentRole,
    AgentTurnRequest,
)
from app.contracts.errors import ServiceError
from app.core.bootstrap import create_default_agent_communication_service
from app.core.config import Settings
from app.main import create_app
from app.ports.agent_communication import AgentAssembledInput
from app.providers.glm_cli_agent import (
    GLM_CLI_MAX_REPLY_CHARS,
    GLM_CLI_MODEL_ID,
    GLM_CLI_PROMPT_VERSION,
    GLM_CLI_PROVIDER_ID,
    GlmCliAgentConfig,
    GlmCliAgentProvider,
    GlmCliProcessResult,
    _system_prompt,
)
from app.providers.openai_responses import (
    OpenAIProviderConfigurationError,
    OpenAIProviderError,
)
from app.services.agent_communication.synthetic_provider import SyntheticAgentProvider


class MockTransport:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[tuple[tuple[str, ...], bytes, float]] = []

    async def run(self, command, *, stdin, timeout_seconds):
        self.calls.append((tuple(command), stdin, timeout_seconds))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _generated() -> dict[str, object]:
    return {
        "replyText": (
            "定位：交易\n"
            "判断：合同金额口径尚缺少已绑定证据，当前不能完成实质核验。\n"
            "建议：请人工绑定合同金额对应的原始材料。"
        ),
        "observations": ["没有访问文件、网络或外部工具。"],
        "questions": [],
        "citations": [],
        "scopeStatus": "in_scope",
        "disposition": "answer",
    }


def _envelope(
    *,
    content: object | None = None,
    is_error: bool = False,
    subtype: str = "success",
    permission_denials: list[object] | None = None,
    model_usage: object | None = None,
    use_result_text: bool = False,
) -> bytes:
    generated = _generated() if content is None else content
    payload: dict[str, object] = {
        "type": "result",
        "subtype": subtype,
        "is_error": is_error,
        "duration_ms": 1250,
        "duration_api_ms": 1100,
        "num_turns": 1,
        "total_cost_usd": 0.0123,
        "usage": {
            "input_tokens": 321,
            "output_tokens": 87,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 20,
        },
        "modelUsage": (
            {GLM_CLI_MODEL_ID: {"inputTokens": 321, "outputTokens": 87}}
            if model_usage is None
            else model_usage
        ),
        "permission_denials": permission_denials or [],
        "result": (
            json.dumps(generated, ensure_ascii=False)
            if use_result_text
            else "structured output returned"
        ),
    }
    if not use_result_text:
        payload["structured_output"] = generated
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _process(
    stdout: bytes | None = None,
    *,
    exit_code: int = 0,
    stderr: bytes = b"",
) -> GlmCliProcessResult:
    return GlmCliProcessResult(
        exit_code=exit_code,
        stdout=_envelope() if stdout is None else stdout,
        stderr=stderr,
    )


def _request() -> AgentTurnRequest:
    return AgentTurnRequest.model_validate(
        {
            "instruction": "请业务解释脱敏合同金额口径并交给风控复核。",
            "evidenceTargets": [],
            "expectedVersion": 1,
            "locale": "zh-CN",
        }
    )


def _context() -> AgentProviderContext:
    instruction = _request().instruction
    return AgentProviderContext.model_validate(
        {
            "projectId": "glm-eval-project-01",
            "threadId": "glm-eval-thread-01",
            "targetRole": "business",
            "contextVersion": "3" * 64,
            "projectSummary": {
                "projectId": "glm-eval-project-01",
                "name": "脱敏设备融资租赁项目",
                "summary": "合同口径已由人工确认，可供文本核验。",
                "isSimulated": True,
            },
            "dimensionSummaries": [],
            "policyResults": [],
            "selectedEvidence": [],
            "selectedFacts": [],
            "approvalState": {
                "version": 1,
                "status": "draft",
                "hardGateStatus": "pass",
                "blockingRuleIds": [],
                "riskVeto": False,
                "summary": "审批仍由人工 Gate 决定。",
            },
            "recentVisibleMessages": [],
            "citationAllowlist": [],
            "currentInstruction": instruction,
            "isContextSimulated": True,
            "disclaimer": "脱敏白名单文本，仅供 advisory Agent。",
        }
    )


def _assembled(payload: object | None = None) -> AgentAssembledInput:
    request = _request()
    context = _context()
    provider_payload = (
        {
            "schemaVersion": "2.0",
            "request": request.model_dump(mode="json", by_alias=True),
            "context": context.model_dump(mode="json", by_alias=True),
        }
        if payload is None
        else payload
    )
    return AgentAssembledInput(
        payload=provider_payload,
        input_hash=hashlib.sha256(b"glm-cli-agent-safe-input").hexdigest(),
        estimated_input_tokens=300,
    )


def _generate(provider: GlmCliAgentProvider, assembled: AgentAssembledInput | None = None):
    return asyncio.run(
        provider.generate(
            AgentRole.BUSINESS,
            _request(),
            _context(),
            assembled or _assembled(),
            max_output_tokens=2000,
        )
    )


def test_success_uses_stdin_strict_no_tool_command_and_safe_audit() -> None:
    transport = MockTransport(_process(stderr=b"AUTH_SECRET_MUST_NOT_BE_RECORDED"))
    audits = []
    provider = GlmCliAgentProvider(
        GlmCliAgentConfig(executable="claude.cmd", timeout_seconds=17),
        transport=transport,
        audit_sink=audits.append,
    )

    generated = _generate(provider)

    assert generated.reply_text == _generated()["replyText"]
    assert len(transport.calls) == 1
    command, stdin, timeout = transport.calls[0]
    assert command[0] == "claude.cmd"
    assert timeout == 17
    assert command[command.index("--permission-mode") + 1] == "plan"
    assert command[command.index("--tools") + 1] == ""
    assert command[command.index("--model") + 1] == GLM_CLI_MODEL_ID
    assert command[command.index("--effort") + 1] == "medium"
    assert "--safe-mode" in command
    assert "--strict-mcp-config" in command
    assert "--no-session-persistence" in command
    assert "--json-schema" in command
    assert _request().instruction not in " ".join(command)
    stdin_payload = json.loads(stdin)
    assert stdin_payload["inputHash"] == _assembled().input_hash
    assert stdin_payload["contextVersion"] == _context().context_version
    assert stdin_payload["providerInput"]["context"]["projectId"] == "glm-eval-project-01"

    audit = provider.last_call
    assert audit == audits[0]
    assert audit.provider_id == GLM_CLI_PROVIDER_ID
    assert audit.model_id == GLM_CLI_MODEL_ID
    assert audit.prompt_version == GLM_CLI_PROMPT_VERSION
    assert audit.context_version == _context().context_version
    assert audit.cli_exit_code == 0
    assert audit.cli_is_error is False
    assert audit.model_usage == (GLM_CLI_MODEL_ID,)
    assert audit.input_tokens == 321
    assert audit.output_tokens == 87
    assert audit.output_hash is not None
    safe_audit = json.dumps(audit.to_safe_dict(), sort_keys=True)
    assert "AUTH_SECRET_MUST_NOT_BE_RECORDED" not in safe_audit
    assert _request().instruction not in safe_audit


def test_real_smoke_runtime_constraints_are_embedded_in_cli_schema() -> None:
    transport = MockTransport(_process())
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)

    _generate(provider)

    command = transport.calls[0][0]
    schema = json.loads(command[command.index("--json-schema") + 1])
    properties = schema["properties"]
    assert properties["citations"]["maxItems"] == 0
    assert properties["citations"]["uniqueItems"] is True
    assert properties["observations"]["uniqueItems"] is True
    assert properties["questions"]["uniqueItems"] is True
    assert "suggestedHandoffs" not in properties
    assert _request().instruction not in " ".join(command)


def _preference_request(**overrides: object) -> AgentTurnRequest:
    payload: dict[str, object] = {
        "instruction": "请业务解释脱敏合同金额口径并交给风控复核。",
        "evidenceTargets": [],
        "expectedVersion": 1,
        "locale": "zh-CN",
    }
    payload.update(overrides)
    return AgentTurnRequest.model_validate(payload)


def test_turn_request_response_preference_defaults_and_camel_case_aliases() -> None:
    request = _request()
    assert request.response_depth == "balanced"
    assert request.response_focus == "balanced"
    assert request.custom_guidance == ""
    serialized = request.model_dump(mode="json", by_alias=True)
    assert serialized["responseDepth"] == "balanced"
    assert serialized["responseFocus"] == "balanced"
    assert serialized["customGuidance"] == ""


@pytest.mark.parametrize(
    ("depth", "focus"),
    [
        ("brief", "risk"),
        ("balanced", "evidence"),
        ("detailed", "next_steps"),
    ],
)
def test_turn_request_accepts_preference_aliases_and_trims_custom_guidance(
    depth,
    focus,
) -> None:
    request = _preference_request(
        responseDepth=depth,
        responseFocus=focus,
        customGuidance="  请优先说明合同金额证据链。  ",
    )
    assert request.response_depth == depth
    assert request.response_focus == focus
    assert request.custom_guidance == "请优先说明合同金额证据链。"
    serialized = request.model_dump(mode="json", by_alias=True)
    assert serialized["responseDepth"] == depth
    assert serialized["responseFocus"] == focus
    assert serialized["customGuidance"] == "请优先说明合同金额证据链。"


def test_turn_request_custom_guidance_max_boundary_and_whitespace_only() -> None:
    boundary = "补" * 500
    request = _preference_request(customGuidance=f"  {boundary}\n")
    assert request.custom_guidance == boundary
    assert _preference_request(customGuidance=" \n\t ").custom_guidance == ""
    with pytest.raises(ValidationError):
        _preference_request(customGuidance="补" * 501)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("responseDepth", "deep"),
        ("responseFocus", "decision"),
        ("responseDepth", None),
    ],
)
def test_turn_request_rejects_invalid_preference_values(field, value) -> None:
    with pytest.raises(ValidationError):
        _preference_request(**{field: value})


def test_response_preferences_serialize_with_camel_case_into_provider_input() -> None:
    transport = MockTransport(_process())
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)
    request = _preference_request(
        responseDepth="detailed",
        responseFocus="evidence",
        customGuidance="聚焦合同金额口径",
    )
    context = _context()
    assembled = AgentAssembledInput(
        payload={
            "schemaVersion": "2.0",
            "request": request.model_dump(mode="json", by_alias=True),
            "context": context.model_dump(mode="json", by_alias=True),
        },
        input_hash=hashlib.sha256(b"glm-cli-agent-safe-input").hexdigest(),
        estimated_input_tokens=300,
    )

    asyncio.run(
        provider.generate(
            AgentRole.BUSINESS,
            request,
            context,
            assembled,
            max_output_tokens=2000,
        )
    )

    provider_request = json.loads(transport.calls[0][1])["providerInput"]["request"]
    assert provider_request["responseDepth"] == "detailed"
    assert provider_request["responseFocus"] == "evidence"
    assert provider_request["customGuidance"] == "聚焦合同金额口径"


def test_system_prompt_keeps_business_and_risk_agent_ontology_only() -> None:
    for role in (AgentRole.BUSINESS, AgentRole.RISK):
        prompt = _system_prompt(role)
        lowered = prompt.lower()
        assert f"Your targetRole is exactly {role.value}" in prompt
        assert "leadership" not in lowered
        assert "coordinator" not in lowered
        assert "coordinates" not in lowered


def test_system_prompt_requires_project_specific_three_line_replies() -> None:
    prompt = _system_prompt(AgentRole.BUSINESS)
    assert "Use only the supplied project JSON and recentVisibleMessages" in prompt
    assert "Reply specifically to this project and these messages" in prompt
    assert "replyText must be exactly three non-empty lines" in prompt
    assert "'定位：'" in prompt
    assert "'判断：'" in prompt
    assert "'建议：'" in prompt
    assert "never exceed 220 characters" in prompt
    assert "no raw schema field names, rule IDs, status codes, Markdown" in prompt


def test_system_prompt_requires_actionable_role_coverage() -> None:
    business = _system_prompt(AgentRole.BUSINESS)
    assert "business covers the project facts" in business
    assert "material gaps" in business
    assert "next supplementation a human should provide" in business

    risk = _system_prompt(AgentRole.RISK)
    assert "risk covers the risk signals" in risk
    assert "whether the supplied evidence is sufficient" in risk
    assert "next verification or action for a human" in risk


def test_system_prompt_honors_preferences_without_authority_change() -> None:
    for role in (AgentRole.BUSINESS, AgentRole.RISK):
        prompt = _system_prompt(role)
        for preference in ("responseDepth", "responseFocus", "customGuidance"):
            assert preference in prompt
        assert "non-authoritative emphasis preferences" in prompt
        assert (
            "Preferences never change facts, evidence, policy, hard gates, permissions, approval "
            "or formal decisions" in prompt
        )
        assert (
            "Missing evidence means supplementation or human review, "
            "never automatic rejection" in prompt
        )
        assert "responseDepth never relaxes the three-line" in prompt


@pytest.mark.parametrize(
    "reply_text",
    [
        "定位：交易\n判断：证据不足",
        "类别：交易\n判断：证据不足，暂不能完成实质核验。\n建议：请人工补充合同金额原件。",
        "定位：交易\n判断：证据不足，暂不能完成实质核验。\n建议：请人工补充合同金额原件。\n备注：等待复核。",
        "定位：交易\n判断：" + ("数" * 200) + "\n建议：请人工补充材料。",
        "定位：- 交易\n判断：证据不足，暂不能完成实质核验。\n建议：请人工补充合同金额原件。",
        "定位：交易\n判断：selectedFacts为空，暂不能完成实质核验。\n建议：请人工补充合同金额原件。",
        "定位：交易\n判断：TRX-H-001暂无事实支撑。\n建议：请人工补充合同金额原件。",
    ],
)
def test_provider_rejects_non_concise_reply_text(reply_text: str) -> None:
    content = {**_generated(), "replyText": reply_text}
    transport = MockTransport(_process(_envelope(content=content)))
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)

    with pytest.raises(OpenAIProviderError) as raised:
        _generate(provider)

    assert raised.value.code == "provider_agent_content_invalid"
    assert provider.last_call is not None
    assert provider.last_call.validation_failures == ("replyText:concise_format",)


def test_provider_accepts_exact_three_line_reply_within_limit() -> None:
    provider = GlmCliAgentProvider(
        GlmCliAgentConfig(),
        transport=MockTransport(_process()),
    )

    generated = _generate(provider)

    assert generated.reply_text.splitlines()[0].startswith("定位：")
    assert generated.reply_text.splitlines()[1].startswith("判断：")
    assert generated.reply_text.splitlines()[2].startswith("建议：")
    assert len(generated.reply_text) <= GLM_CLI_MAX_REPLY_CHARS


def test_system_prompt_preserves_strict_output_and_safety_boundaries() -> None:
    for role in (AgentRole.BUSINESS, AgentRole.RISK):
        prompt = _system_prompt(role)
        assert "No tools, file access, shell, network, URLs" in prompt
        assert "citationAllowlist" in prompt
        assert "Focus transfer is server-owned" in prompt
        assert (
            "Return exactly these six fields and nothing else: replyText, observations, "
            "questions, citations, scopeStatus, disposition" in prompt
        )


def test_supported_roles_are_exactly_business_and_risk() -> None:
    assert GlmCliAgentProvider.supported_roles == frozenset(
        {AgentRole.BUSINESS, AgentRole.RISK}
    )


def test_leadership_agent_route_is_rejected_before_transport() -> None:
    transport = MockTransport(_process())
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)

    with pytest.raises(OpenAIProviderConfigurationError) as raised:
        asyncio.run(
            provider.generate(
                AgentRole.LEADERSHIP,
                _request(),
                _context(),
                _assembled(),
                max_output_tokens=2000,
            )
        )

    assert raised.value.code == "provider_role_unsupported"
    assert transport.calls == []


def test_frozen_glm_provider_and_model_identity_is_unchanged() -> None:
    assert GLM_CLI_PROVIDER_ID == "glm_5_3_coding_plan_cli"
    assert GLM_CLI_MODEL_ID == "glm-5.3[1m]"
    provider = GlmCliAgentProvider(
        GlmCliAgentConfig(), transport=MockTransport(_process())
    )
    assert provider.provider_id == "glm_5_3_coding_plan_cli"
    assert provider.model_id == "glm-5.3[1m]"
    assert provider.is_simulated is False


def test_contract_failure_audit_records_only_safe_field_path_and_type() -> None:
    generated = {
        **_generated(),
        "citations": [
            {
                "evidenceRef": "ev-mi-redacted-001",
                "dimensionId": "transaction",
                "reviewTargetId": None,
                "factVersionId": None,
            }
        ],
    }
    transport = MockTransport(_process(_envelope(content=generated)))
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)

    with pytest.raises(OpenAIProviderError) as raised:
        _generate(provider)

    assert raised.value.code == "provider_agent_content_invalid"
    assert provider.last_call.validation_failures == ("citations:outside_allowlist",)
    safe_audit = json.dumps(provider.last_call.to_safe_dict(), sort_keys=True)
    assert "ev-mi-redacted-001" not in safe_audit
    assert _generated()["replyText"] not in safe_audit


def test_result_text_fallback_still_requires_one_strict_json_object() -> None:
    transport = MockTransport(_process(_envelope(use_result_text=True)))
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)
    assert _generate(provider).disposition.value == "answer"


@pytest.mark.parametrize(
    "unsafe_payload",
    [
        {"filePath": "C:\\private\\contract.pdf"},
        {"materialPath": "redacted"},
        {"context": {"reference": "https://example.invalid/customer"}},
        {"command": "Get-Content secret.txt"},
        {"context": {"message": "Get-Content secret.txt"}},
        {"context": {"message": "请执行 rm secret.txt"}},
        {"context": {"reference": "../private/contract.pdf"}},
        {"context": {"raw": b"binary"}},
        {"context": {"encoded": "A" * 600}},
    ],
)
def test_text_boundary_rejects_paths_commands_binary_and_encoded_files(
    unsafe_payload,
) -> None:
    transport = MockTransport(_process())
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)
    with pytest.raises(OpenAIProviderError) as raised:
        _generate(provider, _assembled(unsafe_payload))
    assert raised.value.code == "provider_context_invalid"
    assert transport.calls == []


@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        (FileNotFoundError("missing executable"), "provider_start_failed"),
        (TimeoutError("timeout"), "provider_timeout"),
        (_process(b"not-json", exit_code=7), "provider_cli_exit_nonzero"),
        (_process(b"not-json"), "provider_response_invalid_json"),
        (
            _process(_envelope(is_error=True, subtype="error_during_execution")),
            "provider_cli_error",
        ),
        (
            _process(_envelope(permission_denials=[{"tool": "Read"}])),
            "provider_tool_attempted",
        ),
        (
            _process(_envelope(model_usage={"claude-sonnet": {}})),
            "provider_model_identity_unverified",
        ),
        (
            _process(_envelope(content={**_generated(), "approval": "completed"})),
            "provider_agent_content_invalid",
        ),
        (
            _process(_envelope(content="not-an-object")),
            "provider_agent_content_invalid",
        ),
    ],
)
def test_all_cli_failure_paths_are_explicit_and_never_return_synthetic(
    outcome,
    expected_code,
) -> None:
    transport = MockTransport(outcome)
    audits = []
    provider = GlmCliAgentProvider(
        GlmCliAgentConfig(), transport=transport, audit_sink=audits.append
    )
    with pytest.raises(OpenAIProviderError) as raised:
        _generate(provider)
    assert raised.value.code == expected_code
    assert provider.is_simulated is False
    assert provider.last_call == audits[-1]
    assert provider.last_call.status == "failed"
    assert provider.last_call.error_code == expected_code


@pytest.mark.parametrize(
    "model_usage",
    [
        {"glm-5.2": {}},
        {"evil-glm-5.3[1m]-proxy": {}},
        {"glm-5.3[1m]-extra": {}},
        {GLM_CLI_MODEL_ID: {}, "other-model": {}},
        {},
        [GLM_CLI_MODEL_ID],
    ],
)
def test_glm_model_usage_requires_exact_single_frozen_identity(model_usage) -> None:
    provider = GlmCliAgentProvider(
        GlmCliAgentConfig(),
        transport=MockTransport(_process(_envelope(model_usage=model_usage))),
    )
    with pytest.raises(OpenAIProviderError) as raised:
        _generate(provider)
    assert raised.value.code == "provider_model_identity_unverified"


def test_glm_model_usage_is_required() -> None:
    envelope = json.loads(_envelope())
    envelope.pop("modelUsage")
    provider = GlmCliAgentProvider(
        GlmCliAgentConfig(),
        transport=MockTransport(_process(json.dumps(envelope).encode("utf-8"))),
    )
    with pytest.raises(OpenAIProviderError) as raised:
        _generate(provider)
    assert raised.value.code == "provider_model_identity_unverified"


def test_cli_is_error_does_not_leak_auth_text_into_audit() -> None:
    auth_text = "Not authenticated: TOKEN-SHOULD-NOT-LEAK"
    envelope = json.loads(_envelope(is_error=True, subtype="error_during_execution"))
    envelope["result"] = auth_text
    transport = MockTransport(
        _process(json.dumps(envelope).encode("utf-8"), stderr=auth_text.encode())
    )
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)
    with pytest.raises(OpenAIProviderError) as raised:
        _generate(provider)
    assert raised.value.code == "provider_cli_error"
    assert auth_text not in json.dumps(provider.last_call.to_safe_dict())


def test_environment_defaults_to_synthetic_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "COMPARE_AGENT_MODE",
        "COMPARE_AGENT_PROVIDER",
        "COMPARE_AGENT_MODEL",
        "COMPARE_AGENT_BUSINESS_MODEL",
        "COMPARE_AGENT_RISK_MODEL",
        "COMPARE_AGENT_LEADERSHIP_MODEL",
        "COMPARE_AGENT_TIMEOUT_SECONDS",
        "COMPARE_AGENT_GLM_CLI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_environment()
    assert settings.agent_mode == AgentMode.SYNTHETIC
    assert settings.agent_provider == "glm_cli"
    assert settings.agent_business_model == GLM_CLI_MODEL_ID
    assert settings.agent_risk_model == GLM_CLI_MODEL_ID
    assert settings.agent_leadership_model == GLM_CLI_MODEL_ID
    assert settings.agent_timeout_seconds == 75
    assert settings.agent_glm_cli_timeout_seconds == 60


def test_environment_and_bootstrap_support_real_glm_selection_and_explicit_synthetic_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPARE_AGENT_MODE", "real")
    monkeypatch.setenv("COMPARE_AGENT_PROVIDER", "glm_cli")
    monkeypatch.setenv("COMPARE_AGENT_GLM_CLI_EXECUTABLE", "custom-claude.cmd")
    monkeypatch.setenv("COMPARE_AGENT_TIMEOUT_SECONDS", "40")
    monkeypatch.setenv("COMPARE_AGENT_GLM_CLI_TIMEOUT_SECONDS", "35")
    settings = Settings.from_environment()
    assert settings.agent_mode == AgentMode.REAL
    assert settings.agent_provider == "glm_cli"
    assert settings.agent_glm_cli_executable == "custom-claude.cmd"
    assert settings.agent_glm_cli_timeout_seconds == 35

    service = create_default_agent_communication_service(
        Settings(
            database_path=tmp_path / "glm-bootstrap.db",
            agent_mode=AgentMode.REAL,
            agent_provider="glm_cli",
            agent_timeout_seconds=30,
            agent_glm_cli_timeout_seconds=90,
        ),
        workbench_service=object(),
    )
    try:
        assert all(
            isinstance(provider, GlmCliAgentProvider)
            for provider in service.providers.values()
        )
        assert all(provider.is_simulated is False for provider in service.providers.values())
        assert next(iter(service.providers.values())).config.timeout_seconds == 29
    finally:
        service.close()

    synthetic = create_default_agent_communication_service(
        Settings(
            database_path=tmp_path / "synthetic-default.db",
            agent_mode=AgentMode.SYNTHETIC,
            agent_provider="glm_cli",
        ),
        workbench_service=object(),
    )
    try:
        assert all(
            isinstance(provider, SyntheticAgentProvider)
            for provider in synthetic.providers.values()
        )
    finally:
        synthetic.close()


def test_invalid_provider_selector_fails_before_composition(
    tmp_path: Path,
) -> None:
    with pytest.raises(ServiceError, match="类型无效"):
        create_default_agent_communication_service(
            Settings(
                database_path=tmp_path / "invalid-provider.db",
                agent_mode=AgentMode.REAL,
                agent_provider="invalid",
            ),
            workbench_service=object(),
        )


def test_api_real_glm_failure_is_audited_without_message_or_synthetic_fallback(
    tmp_path: Path,
) -> None:
    database = tmp_path / "glm-api-failure.db"
    transport = MockTransport(
        _process(_envelope(is_error=True, subtype="error_during_execution"))
    )
    provider = GlmCliAgentProvider(GlmCliAgentConfig(), transport=transport)
    providers = {role: provider for role in (AgentRole.BUSINESS, AgentRole.RISK)}
    settings = Settings(
        database_path=database,
        agent_mode=AgentMode.REAL,
        agent_provider="glm_cli",
    )
    with TestClient(
        create_app(settings, agent_providers=providers), raise_server_exceptions=False
    ) as client:
        project_id = client.get("/api/v1/projects").json()["data"][0]["projectId"]
        thread_response = client.post(
            f"/api/v1/projects/{project_id}/agents/threads",
            headers={
                "X-Compare-Role": "business",
                "Idempotency-Key": "glm-api-thread-001",
            },
            json={"title": "GLM CLI mock failure"},
        )
        assert thread_response.status_code == 200, thread_response.text
        thread = thread_response.json()["data"]
        response = client.post(
            f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
            headers={
                "X-Compare-Role": "business",
                "Idempotency-Key": "glm-api-turn-001",
            },
            json={
                "instruction": "请风控核验当前脱敏项目材料。",
                "evidenceTargets": [],
                "expectedVersion": thread["version"],
                "locale": "zh-CN",
            },
        )
        assert response.status_code == 503, response.text
        assert response.json()["errors"][0]["code"] == "agent_provider_cli_error"

        connection = sqlite3.connect(database)
        try:
            run_id = connection.execute(
                "SELECT run_id FROM agent_runs WHERE idempotency_key = ?",
                ("glm-api-turn-001",),
            ).fetchone()[0]
            assert connection.execute(
                "SELECT COUNT(*) FROM agent_messages WHERE run_id = ?", (run_id,)
            ).fetchone()[0] == 0
        finally:
            connection.close()
        run = client.get(
            f"/api/v1/projects/{project_id}/agents/runs/{run_id}",
            headers={"X-Compare-Role": "leadership"},
        ).json()["data"]
        execution = run["execution"]
        assert execution["providerId"] == GLM_CLI_PROVIDER_ID
        assert execution["modelId"] == GLM_CLI_MODEL_ID
        assert execution["promptVersion"] == GLM_CLI_PROMPT_VERSION
        assert execution["isSimulated"] is False
        assert execution["dataStatus"] == AgentDataStatus.PROVIDER_GENERATED_UNVERIFIED
        assert run["status"] == "failed"
        assert run["steps"][0]["error"]["code"] == "agent_provider_cli_error"
