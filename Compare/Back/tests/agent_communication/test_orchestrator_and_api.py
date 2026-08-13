from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.contracts.agent_communication import (
    AgentDisposition,
    AgentMode,
    AgentRole,
    AgentScopeStatus,
    GeneratedAgentContent,
)
from app.core.config import Settings
from app.main import create_app
from app.services.agent_communication.repository import AgentCommunicationRepository


def _headers(role: str, key: str | None = None) -> dict[str, str]:
    value = {"X-Compare-Role": role}
    if key is not None:
        value["Idempotency-Key"] = key
    return value


def _create_thread(
    client: TestClient,
    project_id: str,
    *,
    role: str = "business",
    key: str = "agent-thread-0001",
) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/agents/threads",
        headers=_headers(role, key),
        json={"title": "单焦点首审协作"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _turn_body(version: int, instruction: str = "请复核当前材料缺口。") -> dict:
    return {
        "instruction": instruction,
        "replyToMessageId": None,
        "evidenceTargets": [],
        "expectedVersion": version,
        "locale": "zh-CN",
    }


@pytest.fixture(scope="module")
def agent_api(tmp_path_factory: pytest.TempPathFactory):
    database = tmp_path_factory.mktemp("single-focus-api") / "agent-api.db"
    with TestClient(
        create_app(
            Settings(database_path=database, agent_mode=AgentMode.SYNTHETIC)
        ),
        raise_server_exceptions=False,
    ) as client:
        catalog = client.get("/api/v1/projects").json()["data"]
        yield client, catalog, database


def test_openapi_exposes_only_single_focus_surface_and_error_contracts(agent_api) -> None:
    client, _, _ = agent_api
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    suffixes = {
        "/api/v1/projects/{projectId}/conclusion",
        "/api/v1/projects/{projectId}/agents/threads",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/messages",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/focus-transitions",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/focus-events",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/turns",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/controls",
        "/api/v1/projects/{projectId}/agents/runs/{runId}",
    }
    assert suffixes <= set(paths)
    assert not any("/channels" in path or "/turns/" in path for path in paths)
    for method in ("post",):
        operation = paths[
            "/api/v1/projects/{projectId}/agents/threads/{threadId}/turns"
        ][method]
        assert {"400", "403", "404", "409", "422", "503"} <= set(
            operation["responses"]
        )
    schemas = json_text = str(schema["components"]["schemas"])
    for removed in (
        "AgentChannelPolicy",
        "AgentGovernanceState",
        "coordinationMode",
        "maxAgentSteps",
        "expectedGovernanceVersion",
        "suggestedHandoffs",
    ):
        assert removed not in json_text

    preflight = client.options(
        "/api/v1/projects/project-01/agents/threads",
        headers={
            "Origin": "http://127.0.0.1:4317",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-compare-role,idempotency-key,content-type",
        },
    )
    assert preflight.status_code == 200
    assert "x-compare-role" in preflight.headers["access-control-allow-headers"].lower()


def test_default_business_focus_single_turn_risk_takeover_and_auto_return(agent_api) -> None:
    client, catalog, _ = agent_api
    project_id = catalog[0]["projectId"]
    thread = _create_thread(client, project_id, key="flow-thread-0001")
    assert thread["focusRole"] == "business"

    first = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
        headers=_headers("business", "flow-business-001"),
        json=_turn_body(thread["version"]),
    )
    assert first.status_code == 200, first.text
    business = first.json()["data"]
    assert business["focusRole"] == business["currentFocusRole"] == "business"
    assert len(business["messages"]) == 1
    assert business["messages"][0]["advisoryOnly"] is True
    assert business["execution"] == business["messages"][0]["execution"]

    replay = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
        headers=_headers("business", "flow-business-001"),
        json=_turn_body(thread["version"]),
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["runId"] == business["runId"]

    transition = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/focus-transitions",
        headers=_headers("business", "focus-risk-api-001"),
        json={
            "toFocusRole": "risk",
            "expectedVersion": business["nextExpectedVersion"],
            "reason": "请求风控短暂复核。",
        },
    )
    assert transition.status_code == 200, transition.text
    focused = transition.json()["data"]
    assert focused["focusRole"] == "risk"

    mismatch = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
        headers=_headers("business", "focus-mismatch-001"),
        json=_turn_body(focused["version"]),
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["errors"][0]["code"] == "agent_focus_mismatch"

    risk_response = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
        headers=_headers("risk", "flow-risk-00001"),
        json=_turn_body(focused["version"], "请风控复核证据充分性。"),
    )
    assert risk_response.status_code == 200, risk_response.text
    risk = risk_response.json()["data"]
    assert risk["focusRole"] == "risk"
    assert risk["currentFocusRole"] == "business"

    messages = client.get(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/messages",
        headers=_headers("leadership"),
    ).json()["data"]
    assert [item["authorType"] for item in messages] == [
        "human",
        "agent",
        "human",
        "agent",
    ]
    assert {item["role"] for item in messages} == {"business", "risk"}
    events = client.get(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/focus-events",
        headers=_headers("leadership"),
    ).json()["data"]
    assert [item["kind"] for item in events] == [
        "thread_created",
        "focus_transferred",
        "focus_returned",
    ]

    run = client.get(
        f"/api/v1/projects/{project_id}/agents/runs/{risk['runId']}",
        headers=_headers("business"),
    ).json()["data"]
    assert len(run["steps"]) == 1
    step = run["steps"][0]
    for field in (
        "providerId",
        "modelId",
        "promptVersion",
        "inputHash",
        "contextVersion",
        "outputHash",
    ):
        assert run["execution"][field] == step[field] == risk["execution"][field]


def test_idempotency_payload_conflict_validation_and_removed_routes(agent_api) -> None:
    client, catalog, _ = agent_api
    project_id = catalog[1]["projectId"]
    thread = _create_thread(client, project_id, key="idem-thread-0001")
    first = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
        headers=_headers("business", "idem-turn-000001"),
        json=_turn_body(1, "请求 A"),
    )
    assert first.status_code == 200
    conflict = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
        headers=_headers("business", "idem-turn-000001"),
        json=_turn_body(1, "请求 B"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["errors"][0]["code"] == "idempotency_key_reused"
    assert conflict.json()["data"] is None

    missing_key = client.post(
        f"/api/v1/projects/{project_id}/agents/threads",
        headers=_headers("business"),
        json={"title": "缺键"},
    )
    assert missing_key.status_code == 422
    assert missing_key.json()["errors"][0]["code"] == "idempotency_key_required"

    forbidden_fields = _turn_body(first.json()["data"]["nextExpectedVersion"])
    forbidden_fields["targetRole"] = "risk"
    strict = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
        headers=_headers("business", "strict-turn-0001"),
        json=forbidden_fields,
    )
    assert strict.status_code == 422
    assert client.get(
        f"/api/v1/projects/{project_id}/agents/channels",
        headers=_headers("business"),
    ).status_code == 404
    assert client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns/business",
        headers=_headers("business", "old-route-00001"),
        json=_turn_body(2),
    ).status_code == 404


def test_different_turn_key_is_rejected_while_another_run_is_active(agent_api) -> None:
    client, catalog, database = agent_api
    project_id = catalog[3]["projectId"]
    thread = _create_thread(client, project_id, key="active-http-thread-01")
    repository = AgentCommunicationRepository(database)
    reservation = repository.reserve_turn(
        project_id,
        thread["id"],
        turn_id="agent-turn-active-http-01",
        role="business",
        mode="synthetic",
        idempotency_key="active-http-owner-01",
        request_fingerprint="a" * 64,
        input_hash="b" * 64,
        context_version="c" * 64,
        expected_thread_version=thread["version"],
        provider_id="deterministic_agent_simulator",
        model_id="deterministic-agent-v1",
        prompt_version="synthetic-single-focus-v2",
        lease_seconds=30,
    )
    try:
        response = client.post(
            f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
            headers=_headers("business", "active-http-other-01"),
            json=_turn_body(thread["version"], "这是不同的第二条请求。"),
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "agent_run_active"
        assert response.json()["data"] is None
    finally:
        repository.fail_turn(
            project_id,
            reservation["run"]["runId"],
            lease_token=reservation["leaseToken"],
            status="failed",
            error={"code": "test_cleanup", "message": "测试清理", "retryable": False},
        )
        repository.close()


def test_collaboration_reject_close_and_reopen_are_not_formal_decisions(agent_api) -> None:
    client, catalog, _ = agent_api
    project_id = catalog[2]["projectId"]
    thread = _create_thread(client, project_id, key="control-thread-01")
    denied = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/controls",
        headers=_headers("business", "reject-denied-01"),
        json={"action": "reject", "expectedVersion": 1, "reason": "测试"},
    )
    assert denied.status_code == 403
    focused = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/focus-transitions",
        headers=_headers("business", "control-focus-01"),
        json={"toFocusRole": "risk", "expectedVersion": 1, "reason": "风控复核"},
    ).json()["data"]
    rejected = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/controls",
        headers=_headers("risk", "control-reject-1"),
        json={
            "action": "reject",
            "expectedVersion": focused["version"],
            "reason": "仅结束协作会话，不构成正式风控拒绝。",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"
    reopened = client.post(
        f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/controls",
        headers=_headers("leadership", "control-reopen-1"),
        json={
            "action": "reopen",
            "expectedVersion": rejected.json()["data"]["version"],
            "reason": "重新开始协作。",
        },
    )
    assert reopened.status_code == 200
    assert reopened.json()["data"]["status"] == "active"
    assert reopened.json()["data"]["focusRole"] == "business"


class FailOnceProvider:
    provider_id = "fail_once_provider"
    model_id = "fail-once-v1"
    prompt_version = "fail-once-prompt-v1"
    is_simulated = True
    supported_roles = frozenset(AgentRole)

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, role, request, context, assembled_input, *, max_output_tokens):
        del role, request, context, assembled_input, max_output_tokens
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("provider down")
        return GeneratedAgentContent(
            reply_text="第二个幂等键重试成功，但仍仅供人工复核。",
            observations=[],
            questions=[],
            citations=[],
            scope_status=AgentScopeStatus.IN_SCOPE,
            disposition=AgentDisposition.ANSWER,
        )


def test_failed_run_same_key_replays_error_new_key_retries_without_message(
    tmp_path: Path,
) -> None:
    database = tmp_path / "retry.db"
    provider = FailOnceProvider()
    providers = {role: provider for role in AgentRole}
    settings = Settings(database_path=database, agent_mode=AgentMode.SYNTHETIC)
    with TestClient(
        create_app(settings, agent_providers=providers), raise_server_exceptions=False
    ) as client:
        project_id = client.get("/api/v1/projects").json()["data"][0]["projectId"]
        thread = _create_thread(client, project_id, key="retry-thread-0001")
        url = f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns"
        failed = client.post(
            url,
            headers=_headers("business", "retry-turn-key01"),
            json=_turn_body(1),
        )
        assert failed.status_code == 503
        assert failed.json()["errors"][0]["code"] == "agent_provider_unavailable"
        same_key = client.post(
            url,
            headers=_headers("business", "retry-turn-key01"),
            json=_turn_body(1),
        )
        assert same_key.status_code == 503
        assert provider.calls == 1
        messages = client.get(url.removesuffix("/turns") + "/messages", headers=_headers("business"))
        assert messages.json()["data"] == []
        recovered = client.post(
            url,
            headers=_headers("business", "retry-turn-key02"),
            json=_turn_body(1),
        )
        assert recovered.status_code == 200, recovered.text
        assert provider.calls == 2


class AuthorityClaimProvider:
    provider_id = "authority_claim_provider"
    model_id = "authority-claim-v1"
    prompt_version = "authority-claim-prompt-v1"
    is_simulated = False
    supported_roles = frozenset(AgentRole)

    async def generate(self, role, request, context, assembled_input, *, max_output_tokens):
        del role, request, context, assembled_input, max_output_tokens
        return GeneratedAgentContent(
            reply_text="我已批准本项目。",
            observations=[],
            questions=[],
            citations=[],
            scope_status=AgentScopeStatus.IN_SCOPE,
            disposition=AgentDisposition.ANSWER,
        )


def test_real_provider_authority_claim_fails_without_authority_or_message_write(
    tmp_path: Path,
) -> None:
    database = tmp_path / "authority.db"
    provider = AuthorityClaimProvider()
    settings = Settings(database_path=database, agent_mode=AgentMode.REAL)
    with TestClient(
        create_app(
            settings, agent_providers={role: provider for role in AgentRole}
        ),
        raise_server_exceptions=False,
    ) as client:
        project_id = client.get("/api/v1/projects").json()["data"][0]["projectId"]
        thread = _create_thread(client, project_id, key="authority-thread1")
        connection = sqlite3.connect(database)
        tables = (
            "fact_versions",
            "policy_results",
            "approval_states",
            "approval_transitions",
            "review_events",
        )
        before = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        response = client.post(
            f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
            headers=_headers("business", "authority-turn-01"),
            json=_turn_body(1),
        )
        assert response.status_code == 503
        assert response.json()["errors"][0]["code"] == "agent_provider_output_invalid"
        after = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        assert after == before
        assert connection.execute("SELECT COUNT(*) FROM agent_messages").fetchone()[0] == 0
        run = connection.execute("SELECT status, advisory_only FROM agent_runs").fetchone()
        assert run == ("failed", 1)
        connection.close()


def test_cross_project_ids_are_404_and_restart_preserves_focus_events(agent_api) -> None:
    client, catalog, database = agent_api
    project_a = catalog[3]["projectId"]
    project_b = catalog[4]["projectId"]
    thread = _create_thread(client, project_a, key="restart-thread-01")
    cross = client.get(
        f"/api/v1/projects/{project_b}/agents/threads/{thread['id']}",
        headers=_headers("business"),
    )
    assert cross.status_code == 404
    thread_id = thread["id"]

    # The module-scoped client remains open; use SQLite restart proof in a separate
    # test database to avoid two application lifespans owning the same service.
    restart_db = database.parent / "restart-proof.db"
    settings = Settings(database_path=restart_db, agent_mode=AgentMode.SYNTHETIC)
    with TestClient(create_app(settings), raise_server_exceptions=False) as first:
        project_id = first.get("/api/v1/projects").json()["data"][0]["projectId"]
        durable = _create_thread(first, project_id, key="durable-thread-01")
        first.post(
            f"/api/v1/projects/{project_id}/agents/threads/{durable['id']}/focus-transitions",
            headers=_headers("business", "durable-focus-01"),
            json={"toFocusRole": "leadership", "expectedVersion": 1, "reason": "协调"},
        )
    with TestClient(create_app(settings), raise_server_exceptions=False) as restarted:
        read = restarted.get(
            f"/api/v1/projects/{project_id}/agents/threads/{durable['id']}",
            headers=_headers("risk"),
        )
        assert read.status_code == 200
        assert read.json()["data"]["focusRole"] == "leadership"
        events = restarted.get(
            f"/api/v1/projects/{project_id}/agents/threads/{durable['id']}/focus-events",
            headers=_headers("risk"),
        ).json()["data"]
        assert [item["kind"] for item in events] == [
            "thread_created",
            "focus_transferred",
        ]
    assert thread_id.startswith("agent-thread-")
