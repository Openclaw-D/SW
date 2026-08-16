from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import require_project_membership
from app.contracts.agent_communication import AgentMode
from app.core.config import Settings
from app.main import create_app
from app.services.authentication import SESSION_COOKIE_NAME


CHAT_ROLES = ("business", "risk")
ACCOUNT_ROLES = (*CHAT_ROLES, "leadership")
PRINCIPAL_ACCOUNTS = {
    "business": "business",
    "risk": "risk",
    "leadership": "coordinator",
}
AUTHORITY_TABLES = (
    "fact_versions",
    "evidence_references",
    "policy_results",
    "approval_states",
    "approval_transitions",
    "review_events",
)


def _login(client: TestClient, role: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": PRINCIPAL_ACCOUNTS[role],
            "password": "123456",
        },
    )
    assert response.status_code == 200, response.text
    assert SESSION_COOKIE_NAME in response.cookies
    account = response.json()["data"]
    assert account["role"] == role
    return account


def _headers(key: str, *, spoof_role: str | None = None) -> dict[str, str]:
    headers = {"Idempotency-Key": key}
    if spoof_role is not None:
        headers["X-Compare-Role"] = spoof_role
    return headers


def _create_thread(
    client: TestClient,
    project_id: str,
    *,
    key: str,
) -> dict[str, object]:
    _login(client, "business")
    response = client.post(
        f"/api/v1/projects/{project_id}/agents/threads",
        headers=_headers(key),
        json={"title": "认证群聊契约矩阵"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _message_url(project_id: str, thread_id: str) -> str:
    return f"/api/v1/projects/{project_id}/agents/threads/{thread_id}/messages"


def _turn_url(project_id: str, thread_id: str) -> str:
    return f"/api/v1/projects/{project_id}/agents/threads/{thread_id}/turns"


def _post_human_message(
    client: TestClient,
    project_id: str,
    thread_id: str,
    *,
    key: str,
    content: str,
    evidence_targets: list[dict[str, str | None]] | None = None,
) -> dict[str, object]:
    response = client.post(
        _message_url(project_id, thread_id),
        headers=_headers(key),
        json={
            "content": content,
            "replyToMessageId": None,
            "evidenceTargets": evidence_targets or [],
            "locale": "zh-CN",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _turn_payload(
    thread_version: int,
    *,
    instruction: str,
    target_role: str,
    source_message_id: str | None,
) -> dict[str, object]:
    return {
        "instruction": instruction,
        "targetAgentRole": target_role,
        "sourceMessageId": source_message_id,
        "replyToMessageId": None,
        "evidenceTargets": [],
        "expectedVersion": thread_version,
        "locale": "zh-CN",
    }


def _counts(
    database: Path, tables: tuple[str, ...], project_id: str | None = None
) -> dict[str, int]:
    with sqlite3.connect(database) as connection:
        return {
            table: connection.execute(
                (
                    f"SELECT COUNT(*) FROM {table}"
                    if project_id is None
                    else f"SELECT COUNT(*) FROM {table} WHERE project_id = ?"
                ),
                () if project_id is None else (project_id,),
            ).fetchone()[0]
            for table in tables
        }


def _thread_counts(database: Path, project_id: str, thread_id: str) -> tuple[int, int]:
    with sqlite3.connect(database) as connection:
        messages = connection.execute(
            """SELECT COUNT(*) FROM agent_messages
               WHERE project_id = ? AND thread_id = ?""",
            (project_id, thread_id),
        ).fetchone()[0]
        runs = connection.execute(
            """SELECT COUNT(*) FROM agent_runs
               WHERE project_id = ? AND thread_id = ?""",
            (project_id, thread_id),
        ).fetchone()[0]
    return messages, runs


@pytest.fixture(scope="module")
def authenticated_matrix(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[TestClient, str, Path]]:
    """Use a real cookie session against a fresh local SQLite database.

    The optional legacy-test adapter in tests/conftest.py installs a role
    dependency override for older modules. Remove it so this contract matrix
    exercises the production authenticated membership dependency and cookie.
    """

    database = tmp_path_factory.mktemp("group-chat-contract-matrix") / "matrix.db"
    with TestClient(
        create_app(Settings(database_path=database, agent_mode=AgentMode.SYNTHETIC)),
        raise_server_exceptions=False,
    ) as client:
        client.app.dependency_overrides.pop(require_project_membership, None)
        assert client.get("/api/v1/projects").status_code == 401
        _login(client, "business")
        catalog = client.get("/api/v1/projects")
        assert catalog.status_code == 200, catalog.text
        yield client, catalog.json()["data"][0]["projectId"], database


def test_openapi_message_and_turn_contracts_expose_group_chat_fields(
    authenticated_matrix: tuple[TestClient, str, Path],
) -> None:
    client, _, _ = authenticated_matrix
    schema = client.get("/openapi.json")
    assert schema.status_code == 200, schema.text
    document = schema.json()
    paths = document["paths"]
    schemas = document["components"]["schemas"]

    message_path = (
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/messages"
    )
    turn_path = "/api/v1/projects/{projectId}/agents/threads/{threadId}/turns"
    message_body = paths[message_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    turn_body = paths[turn_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert message_body["$ref"] == "#/components/schemas/AgentChatMessageRequest"
    assert turn_body["$ref"] == "#/components/schemas/AgentTurnRequest"

    message = schemas["AgentChatMessageRequest"]
    assert {"content", "replyToMessageId", "evidenceTargets", "locale"} <= set(
        message["properties"]
    )
    assert message["properties"]["content"]["maxLength"] == 4000
    assert message["properties"]["evidenceTargets"]["maxItems"] == 50
    locale = message["properties"]["locale"]
    locale_values = locale.get("enum", [locale.get("const")])
    assert locale_values == ["zh-CN"]
    assert locale["default"] == "zh-CN"

    turn = schemas["AgentTurnRequest"]
    assert {"targetAgentRole", "sourceMessageId"} <= set(turn["properties"])
    target_role = turn["properties"]["targetAgentRole"]
    target_variants = target_role.get("anyOf", [target_role])
    assert any(item.get("enum") == list(CHAT_ROLES) for item in target_variants)
    source_message_id = turn["properties"]["sourceMessageId"]
    source_variants = source_message_id.get("anyOf", [source_message_id])
    assert any(item.get("maxLength") == 128 for item in source_variants)
    assert turn["properties"]["evidenceTargets"]["maxItems"] == 50


def test_authenticated_plain_human_message_never_creates_agent_run_for_any_role(
    authenticated_matrix: tuple[TestClient, str, Path],
) -> None:
    client, project_id, database = authenticated_matrix
    thread = _create_thread(client, project_id, key="matrix-plain-thread")
    thread_id = str(thread["id"])

    for role in CHAT_ROLES:
        _login(client, role)
        response = client.post(
            _message_url(project_id, thread_id),
            headers=_headers(f"matrix-plain-{role}", spoof_role="business"),
            json={
                "content": f"{role} 同步人工信息，不显式调用 Agent。",
                "replyToMessageId": None,
                "evidenceTargets": [],
                "locale": "zh-CN",
            },
        )
        assert response.status_code == 200, response.text
        message = response.json()["data"]
        assert message["authorType"] == "human"
        assert message["role"] == role
        assert message["runId"] is None
        assert message["advisoryOnly"] is True
        assert message["isSimulated"] is False
        assert message["execution"] is None
        assert message["generatedContent"] is None

    history = client.get(_message_url(project_id, thread_id))
    assert history.status_code == 200, history.text
    assert [item["role"] for item in history.json()["data"]] == list(CHAT_ROLES)
    assert _thread_counts(database, project_id, thread_id) == (2, 0)


@pytest.mark.parametrize("principal", CHAT_ROLES)
@pytest.mark.parametrize("target_role", CHAT_ROLES)
def test_explicit_routing_persists_source_then_one_advisory_agent_reply(
    authenticated_matrix: tuple[TestClient, str, Path],
    principal: str,
    target_role: str,
) -> None:
    client, project_id, database = authenticated_matrix
    thread = _create_thread(
        client,
        project_id,
        key=f"matrix-route-thread-{principal}-{target_role}",
    )
    thread_id = str(thread["id"])
    instruction = f"{principal} 显式请求 {target_role} Agent 复核。"

    _login(client, principal)
    source = _post_human_message(
        client,
        project_id,
        thread_id,
        key=f"matrix-route-source-{principal}-{target_role}",
        content=instruction,
    )
    assert source["runId"] is None
    authority_before = _counts(database, AUTHORITY_TABLES, project_id)

    turn = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers(f"matrix-route-turn-{principal}-{target_role}"),
        json=_turn_payload(
            int(thread["version"]),
            instruction=instruction,
            target_role=target_role,
            source_message_id=str(source["id"]),
        ),
    )
    assert turn.status_code == 200, turn.text
    result = turn.json()["data"]
    assert result["focusRole"] == target_role
    assert result["currentFocusRole"] == "business"
    assert result["advisoryOnly"] is True

    execution = result["execution"]
    assert execution["mode"] == "synthetic"
    assert execution["advisoryOnly"] is True
    assert execution["isSimulated"] is True
    assert execution["dataStatus"] == "simulated"
    assert execution["source"] == execution["providerId"]
    assert execution["providerId"]
    assert execution["modelId"]
    assert execution["promptVersion"]
    for field in ("inputHash", "contextVersion", "outputHash"):
        assert re.fullmatch(r"[0-9a-f]{64}", execution[field])

    agent_message = result["messages"][0]
    assert agent_message["authorType"] == "agent"
    assert agent_message["role"] == target_role
    assert agent_message["replyToMessageId"] == source["id"]
    assert agent_message["runId"] == result["runId"]
    assert agent_message["advisoryOnly"] is True
    assert agent_message["isSimulated"] is True
    assert agent_message["execution"] == execution
    assert agent_message["content"] == agent_message["generatedContent"]["replyText"]

    history = client.get(_message_url(project_id, thread_id))
    assert history.status_code == 200, history.text
    persisted = history.json()["data"]
    assert [(item["authorType"], item["role"]) for item in persisted] == [
        ("human", principal),
        ("agent", target_role),
    ]
    assert persisted[0]["id"] == source["id"]
    assert persisted[1]["replyToMessageId"] == source["id"]
    assert _thread_counts(database, project_id, thread_id) == (2, 1)

    stored_run = client.get(
        f"/api/v1/projects/{project_id}/agents/runs/{result['runId']}"
    )
    assert stored_run.status_code == 200, stored_run.text
    run = stored_run.json()["data"]
    assert run["role"] == target_role
    assert run["advisoryOnly"] is True
    assert run["execution"] == execution
    assert run["steps"][0]["providerId"] == execution["providerId"]
    assert run["steps"][0]["modelId"] == execution["modelId"]
    assert run["steps"][0]["promptVersion"] == execution["promptVersion"]
    assert run["steps"][0]["inputHash"] == execution["inputHash"]
    assert run["steps"][0]["contextVersion"] == execution["contextVersion"]
    assert run["steps"][0]["outputHash"] == execution["outputHash"]
    assert _counts(database, AUTHORITY_TABLES, project_id) == authority_before


def test_settings_account_cannot_chat_and_leadership_cannot_be_targeted(
    authenticated_matrix: tuple[TestClient, str, Path],
) -> None:
    client, project_id, database = authenticated_matrix
    thread = _create_thread(client, project_id, key="matrix-settings-boundary-thread")
    thread_id = str(thread["id"])

    _login(client, "business")
    source = _post_human_message(
        client,
        project_id,
        thread_id,
        key="matrix-settings-boundary-source",
        content="设置不是 Agent。",
    )
    leadership_target = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-settings-target"),
        json=_turn_payload(
            int(thread["version"]),
            instruction=str(source["content"]),
            target_role="leadership",
            source_message_id=str(source["id"]),
        ),
    )
    assert leadership_target.status_code == 422, leadership_target.text

    _login(client, "leadership")
    settings_message = client.post(
        _message_url(project_id, thread_id),
        headers=_headers("matrix-settings-message"),
        json={
            "content": "设置账号不应写入群聊。",
            "replyToMessageId": None,
            "evidenceTargets": [],
            "locale": "zh-CN",
        },
    )
    assert settings_message.status_code == 403, settings_message.text
    settings_turn = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-settings-turn"),
        json=_turn_payload(
            int(thread["version"]),
            instruction=str(source["content"]),
            target_role="risk",
            source_message_id=str(source["id"]),
        ),
    )
    assert settings_turn.status_code == 403, settings_turn.text
    assert _thread_counts(database, project_id, thread_id) == (1, 0)


def test_idempotency_replays_same_payload_and_conflicts_on_changed_payload(
    authenticated_matrix: tuple[TestClient, str, Path],
) -> None:
    client, project_id, database = authenticated_matrix
    thread = _create_thread(client, project_id, key="matrix-idempotency-thread")
    thread_id = str(thread["id"])
    payload = {
        "content": "幂等保存的一条人工消息。",
        "replyToMessageId": None,
        "evidenceTargets": [],
        "locale": "zh-CN",
    }

    first = client.post(
        _message_url(project_id, thread_id),
        headers=_headers("matrix-idempotency-message"),
        json=payload,
    )
    assert first.status_code == 200, first.text
    replay = client.post(
        _message_url(project_id, thread_id),
        headers=_headers("matrix-idempotency-message"),
        json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["data"] == first.json()["data"]
    changed = client.post(
        _message_url(project_id, thread_id),
        headers=_headers("matrix-idempotency-message"),
        json={**payload, "content": "同键不同内容必须冲突。"},
    )
    assert changed.status_code == 409, changed.text
    assert _thread_counts(database, project_id, thread_id) == (1, 0)

    source = first.json()["data"]
    turn_payload = _turn_payload(
        int(thread["version"]),
        instruction=str(source["content"]),
        target_role="risk",
        source_message_id=str(source["id"]),
    )
    first_turn = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-idempotency-turn"),
        json=turn_payload,
    )
    assert first_turn.status_code == 200, first_turn.text
    turn_replay = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-idempotency-turn"),
        json=turn_payload,
    )
    assert turn_replay.status_code == 200, turn_replay.text
    assert turn_replay.json()["data"] == first_turn.json()["data"]
    changed_turn = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-idempotency-turn"),
        json={**turn_payload, "instruction": "同键不同 turn 载荷。"},
    )
    assert changed_turn.status_code == 409, changed_turn.text
    assert _thread_counts(database, project_id, thread_id) == (2, 1)


def test_human_evidence_targets_round_trip_with_limit_50_and_duplicate_422(
    authenticated_matrix: tuple[TestClient, str, Path],
) -> None:
    client, project_id, database = authenticated_matrix
    thread = _create_thread(client, project_id, key="matrix-evidence-thread")
    thread_id = str(thread["id"])

    def target(index: int) -> dict[str, str]:
        return {
            "evidenceRef": f"matrix-evidence-{index:03d}",
            "dimensionId": "transaction",
            "reviewTargetId": f"matrix-review-{index:03d}",
            "factVersionId": f"matrix-fact-{index:03d}",
        }

    accepted = [target(index) for index in range(50)]
    message = _post_human_message(
        client,
        project_id,
        thread_id,
        key="matrix-evidence-50",
        content="以下 50 项证据需要人工引用。",
        evidence_targets=accepted,
    )
    assert message["citations"] == accepted
    history = client.get(_message_url(project_id, thread_id))
    assert history.status_code == 200, history.text
    assert history.json()["data"][0]["citations"] == accepted

    too_many = client.post(
        _message_url(project_id, thread_id),
        headers=_headers("matrix-evidence-51"),
        json={
            "content": "第 51 项应被结构校验拒绝。",
            "replyToMessageId": None,
            "evidenceTargets": [target(index) for index in range(51)],
            "locale": "zh-CN",
        },
    )
    assert too_many.status_code == 422, too_many.text
    duplicate = client.post(
        _message_url(project_id, thread_id),
        headers=_headers("matrix-evidence-duplicate"),
        json={
            "content": "重复证据引用应被拒绝。",
            "replyToMessageId": None,
            "evidenceTargets": [target(0), target(0)],
            "locale": "zh-CN",
        },
    )
    assert duplicate.status_code == 422, duplicate.text
    assert "evidenceTargets must not contain duplicates" in duplicate.text
    assert _thread_counts(database, project_id, thread_id) == (1, 0)


def test_invalid_or_mismatched_source_message_fails_before_agent_creation(
    authenticated_matrix: tuple[TestClient, str, Path],
) -> None:
    client, project_id, database = authenticated_matrix
    thread = _create_thread(client, project_id, key="matrix-invalid-source-thread")
    thread_id = str(thread["id"])
    version = int(thread["version"])

    missing_pair = {
        "instruction": "缺少 sourceMessageId 的显式路由。",
        "targetAgentRole": "risk",
        "sourceMessageId": None,
        "replyToMessageId": None,
        "evidenceTargets": [],
        "expectedVersion": version,
        "locale": "zh-CN",
    }
    missing = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-missing-source"),
        json=missing_pair,
    )
    assert missing.status_code == 422, missing.text
    assert "targetAgentRole and sourceMessageId must be provided together" in missing.text

    _login(client, "business")
    source = _post_human_message(
        client,
        project_id,
        thread_id,
        key="matrix-invalid-source-message",
        content="业务原始消息。",
    )

    invalid = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-invalid-source-id"),
        json=_turn_payload(
            version,
            instruction=str(source["content"]),
            target_role="risk",
            source_message_id="agent-message-does-not-exist",
        ),
    )
    assert invalid.status_code == 404, invalid.text

    _login(client, "risk")
    principal_mismatch = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-principal-mismatch", spoof_role="business"),
        json=_turn_payload(
            version,
            instruction=str(source["content"]),
            target_role="risk",
            source_message_id=str(source["id"]),
        ),
    )
    assert principal_mismatch.status_code == 403, principal_mismatch.text
    assert (
        principal_mismatch.json()["errors"][0]["code"]
        == "agent_source_message_mismatch"
    )

    _login(client, "business")
    content_mismatch = client.post(
        _turn_url(project_id, thread_id),
        headers=_headers("matrix-content-mismatch"),
        json=_turn_payload(
            version,
            instruction="这不是来源消息的原文。",
            target_role="risk",
            source_message_id=str(source["id"]),
        ),
    )
    assert content_mismatch.status_code == 403, content_mismatch.text
    assert (
        content_mismatch.json()["errors"][0]["code"]
        == "agent_source_message_mismatch"
    )
    assert _thread_counts(database, project_id, thread_id) == (1, 0)


__all__ = []
