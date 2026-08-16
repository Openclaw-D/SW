from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from app.contracts.agent_communication import (
    AgentFocusEvent,
    AgentMessage,
    AgentRunRecord,
    AgentThread,
)
from app.contracts.errors import (
    ConflictError,
    ForbiddenError,
    IdempotencyConflictError,
)
from app.services.agent_communication.repository import AgentCommunicationRepository


def _project(repository: AgentCommunicationRepository, project_id: str) -> None:
    repository.raw_connection_for_tests().execute(
        """INSERT INTO projects(id, name, payload_json, created_at, updated_at)
           VALUES (?, ?, '{}', '2026-08-13T00:00:00Z', '2026-08-13T00:00:00Z')""",
        (project_id, project_id),
    )


def _thread(
    repository: AgentCommunicationRepository,
    project_id: str = "project-a",
    *,
    key: str = "create-thread-001",
) -> dict:
    return repository.create_thread(
        project_id,
        title="单焦点协作",
        created_by_role="leadership",
        idempotency_key=key,
        request_hash=(key[-1] * 64 if key[-1].isalnum() else "a" * 64),
    )


def _reserve(
    repository: AgentCommunicationRepository,
    project_id: str,
    thread: dict,
    *,
    key: str,
    role: str | None = None,
    fingerprint: str = "f" * 64,
    lease_seconds: float = 30,
) -> dict:
    selected = role or thread["focusRole"]
    return repository.reserve_turn(
        project_id,
        thread["id"],
        turn_id="agent-turn-" + key.replace("-", "")[:32].ljust(32, "0"),
        role=selected,
        mode="synthetic",
        idempotency_key=key,
        request_fingerprint=fingerprint,
        input_hash="1" * 64,
        context_version="2" * 64,
        expected_thread_version=thread["version"],
        provider_id="deterministic_agent_simulator",
        model_id="structured-single-focus-sim-v2",
        prompt_version="compare-agent-single-focus-synthetic-v2",
        lease_seconds=lease_seconds,
    )


def _execution(output_hash: str = "3" * 64) -> dict:
    return {
        "mode": "synthetic",
        "providerId": "deterministic_agent_simulator",
        "modelId": "structured-single-focus-sim-v2",
        "promptVersion": "compare-agent-single-focus-synthetic-v2",
        "inputHash": "1" * 64,
        "contextVersion": "2" * 64,
        "outputHash": output_hash,
        "advisoryOnly": True,
        "isSimulated": True,
        "dataStatus": "simulated",
        "source": "deterministic_agent_simulator",
        "disclaimer": "仅供 advisory Agent。",
    }


def test_natural_chat_message_persists_without_agent_run(tmp_path: Path) -> None:
    repository = AgentCommunicationRepository(tmp_path / "natural-chat.db")
    _project(repository, "project-a")
    thread = _thread(repository)

    message = repository.append_human_message(
        "project-a",
        thread["id"],
        role="business",
        content="这是普通群聊，不触发 Agent。",
        reply_to_message_id=None,
        idempotency_key="chat-message-0001",
        request_hash="c" * 64,
    )

    assert message["authorType"] == "human"
    assert message["role"] == "business"
    assert message["runId"] is None
    assert repository.raw_connection_for_tests().execute(
        "SELECT COUNT(*) FROM agent_runs"
    ).fetchone()[0] == 0
    assert repository.list_messages("project-a", thread["id"]) == [message]
    repository.close()


def test_human_chat_continues_while_agent_run_is_active(tmp_path: Path) -> None:
    repository = AgentCommunicationRepository(tmp_path / "natural-chat-active-run.db")
    _project(repository, "project-a")
    thread = _thread(repository)
    reserved = _reserve(
        repository,
        "project-a",
        thread,
        key="active-agent-turn-0001",
        role="risk",
    )

    message = repository.append_human_message(
        "project-a",
        thread["id"],
        role="business",
        content="Agent 回复期间继续补充这条业务说明。",
        reply_to_message_id=None,
        idempotency_key="chat-during-run-0001",
        request_hash="d" * 64,
    )

    assert message["runId"] is None
    assert repository.get_run("project-a", reserved["run"]["runId"])["status"] == "running"
    assert repository.list_messages("project-a", thread["id"])[0]["content"] == message["content"]
    repository.close()


def _finalize(
    repository: AgentCommunicationRepository,
    project_id: str,
    reserved: dict,
    *,
    role: str,
) -> dict:
    run_id = reserved["run"]["runId"]
    human_id = "agent-message-" + "a" * 31 + str(role == "business")
    agent_id = "agent-message-" + "b" * 31 + str(role == "business")
    generated = {
        "replyText": "当前输出仅供人工复核。",
        "observations": [],
        "questions": [],
        "citations": [],
        "scopeStatus": "in_scope",
        "disposition": "answer",
    }
    return repository.finalize_turn(
        project_id,
        run_id,
        lease_token=reserved["leaseToken"],
        status="completed",
        messages=[
            {
                "id": human_id,
                "role": role,
                "authorType": "human",
                "kind": "user_input",
                "content": "请复核",
                "citations": [],
                "generatedContent": None,
                "execution": None,
                "replyToMessageId": None,
                "isSimulated": False,
            },
            {
                "id": agent_id,
                "role": role,
                "authorType": "agent",
                "kind": "agent_reply",
                "content": generated["replyText"],
                "citations": [],
                "generatedContent": generated,
                "execution": _execution(),
                "replyToMessageId": human_id,
                "isSimulated": True,
            },
        ],
        step={
            "stepId": "agent-step-" + "c" * 32,
            "stepIndex": 1,
            "role": role,
            "status": "completed",
            "providerId": "deterministic_agent_simulator",
            "modelId": "structured-single-focus-sim-v2",
            "promptVersion": "compare-agent-single-focus-synthetic-v2",
            "inputHash": "1" * 64,
            "contextVersion": "2" * 64,
            "outputHash": "3" * 64,
            "error": None,
            "startedAt": "2026-08-13T00:00:00Z",
            "finishedAt": "2026-08-13T00:00:01Z",
        },
        output_hash="3" * 64,
    )


def test_new_schema_has_one_focus_no_legacy_governance_and_append_only_events(
    tmp_path: Path,
) -> None:
    repository = AgentCommunicationRepository(tmp_path / "single-focus.db")
    _project(repository, "project-a")
    thread = _thread(repository)
    assert AgentThread.model_validate(thread).focus_role.value == "business"
    events = repository.list_focus_events("project-a", thread["id"])
    assert [AgentFocusEvent.model_validate(item).kind.value for item in events] == [
        "thread_created"
    ]
    tables = {
        row[0]
        for row in repository.raw_connection_for_tests().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "agent_focus_events" in tables
    assert "agent_channel_access" not in tables
    assert "agent_governance_state" not in tables
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository.raw_connection_for_tests().execute(
            "UPDATE agent_focus_events SET reason='tampered'"
        )
    repository.close()


def test_global_idempotency_replays_same_payload_and_rejects_any_reuse(
    tmp_path: Path,
) -> None:
    repository = AgentCommunicationRepository(tmp_path / "idempotency.db")
    _project(repository, "project-a")
    first = repository.create_thread(
        "project-a",
        title="同一请求",
        created_by_role="business",
        idempotency_key="global-idem-001",
        request_hash="a" * 64,
    )
    replay = repository.create_thread(
        "project-a",
        title="同一请求",
        created_by_role="business",
        idempotency_key="global-idem-001",
        request_hash="a" * 64,
    )
    assert replay == first
    with pytest.raises(IdempotencyConflictError):
        repository.create_thread(
            "project-a",
            title="不同请求",
            created_by_role="business",
            idempotency_key="global-idem-001",
            request_hash="b" * 64,
        )
    with pytest.raises(IdempotencyConflictError):
        repository.transition_focus(
            "project-a",
            first["id"],
            actor_role="business",
            to_focus_role="risk",
            expected_version=1,
            reason="交给风控",
            idempotency_key="global-idem-001",
            request_hash="a" * 64,
        )
    repository.close()


def test_focus_transition_permissions_auto_return_and_readable_history(tmp_path: Path) -> None:
    repository = AgentCommunicationRepository(tmp_path / "focus.db")
    _project(repository, "project-a")
    thread = _thread(repository)
    with pytest.raises(ForbiddenError):
        repository.transition_focus(
            "project-a",
            thread["id"],
            actor_role="risk",
            to_focus_role="leadership",
            expected_version=1,
            reason="非法抢占",
            idempotency_key="focus-illegal-001",
            request_hash="a" * 64,
        )
    focused = repository.transition_focus(
        "project-a",
        thread["id"],
        actor_role="business",
        to_focus_role="risk",
        expected_version=1,
        reason="请求风控短暂复核",
        idempotency_key="focus-risk-0001",
        request_hash="b" * 64,
    )
    assert focused["focusRole"] == "risk" and focused["version"] == 2
    reserved = _reserve(
        repository,
        "project-a",
        focused,
        key="risk-turn-00001",
        role="risk",
    )
    completed = _finalize(repository, "project-a", reserved, role="risk")
    assert completed["thread"]["focusRole"] == "business"
    assert completed["thread"]["version"] == 3
    events = repository.list_focus_events("project-a", thread["id"])
    assert [item["kind"] for item in events] == [
        "thread_created",
        "focus_transferred",
        "focus_returned",
    ]
    assert "自动返回业务" in events[-1]["reason"]
    repository.close()


def test_single_active_run_failed_new_key_retry_and_expired_owner_fencing(
    tmp_path: Path,
) -> None:
    repository = AgentCommunicationRepository(tmp_path / "runs.db")
    _project(repository, "project-a")
    thread = _thread(repository)
    first = _reserve(
        repository,
        "project-a",
        thread,
        key="active-run-0001",
        lease_seconds=0.01,
    )
    same_request = _reserve(
        repository,
        "project-a",
        thread,
        key="active-run-0001",
    )
    assert same_request["action"] == "wait"
    assert same_request["run"]["runId"] == first["run"]["runId"]
    with pytest.raises(ConflictError) as active:
        _reserve(
            repository,
            "project-a",
            thread,
            key="active-run-0002",
            fingerprint="e" * 64,
        )
    assert active.value.code == "agent_run_active"
    time.sleep(0.02)
    with pytest.raises(ConflictError) as fenced:
        _finalize(repository, "project-a", first, role="business")
    assert fenced.value.code == "agent_run_fenced"
    retry = _reserve(
        repository,
        "project-a",
        thread,
        key="active-run-0003",
        fingerprint="d" * 64,
    )
    assert retry["action"] == "owner"
    assert repository.get_run("project-a", first["run"]["runId"])["status"] == "failed"
    failed = repository.fail_turn(
        "project-a",
        retry["run"]["runId"],
        lease_token=retry["leaseToken"],
        status="failed",
        error={"code": "provider_failed", "message": "失败", "retryable": True},
    )
    assert failed["status"] == "failed"
    new_key_retry = _reserve(
        repository,
        "project-a",
        thread,
        key="active-run-0004",
        fingerprint="c" * 64,
    )
    assert new_key_retry["action"] == "owner"
    repository.close()


def test_expired_run_is_reaped_before_focus_transition(tmp_path: Path) -> None:
    repository = AgentCommunicationRepository(tmp_path / "expired-focus.db")
    _project(repository, "project-a")
    thread = _thread(repository)
    expired_owner = _reserve(
        repository,
        "project-a",
        thread,
        key="expired-focus-run-001",
        lease_seconds=0.01,
    )
    time.sleep(0.02)
    focused = repository.transition_focus(
        "project-a",
        thread["id"],
        actor_role="business",
        to_focus_role="risk",
        expected_version=thread["version"],
        reason="过期 owner 不得永久阻断焦点切换。",
        idempotency_key="expired-focus-move-001",
        request_hash="9" * 64,
    )
    assert focused["focusRole"] == "risk"
    assert repository.get_run(
        "project-a", expired_owner["run"]["runId"]
    )["error"]["code"] == "agent_run_lease_expired"
    with pytest.raises(ConflictError) as fenced:
        _finalize(repository, "project-a", expired_owner, role="business")
    assert fenced.value.code == "agent_run_fenced"
    repository.close()


def test_database_forces_advisory_true_and_composite_foreign_keys(tmp_path: Path) -> None:
    repository = AgentCommunicationRepository(tmp_path / "fk.db")
    _project(repository, "project-a")
    _project(repository, "project-b")
    thread_a = _thread(repository, "project-a", key="create-a-00001")
    thread_b = _thread(repository, "project-b", key="create-b-00001")
    run_a = _reserve(repository, "project-a", thread_a, key="run-a-0000001")
    completed_a = _finalize(repository, "project-a", run_a, role="business")
    run_b = _reserve(repository, "project-b", thread_b, key="run-b-0000001")
    connection = repository.raw_connection_for_tests()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO agent_run_steps
               (id, run_id, project_id, thread_id, step_index, role, status,
                provider_id, model_id, prompt_version, input_hash,
                context_version, output_hash, error_json, started_at,
                finished_at, advisory_only)
               VALUES ('cross-step', ?, 'project-a', ?, 1, 'business', 'completed',
                       'p', 'm', 'v', ?, ?, ?, NULL, '2026', '2026', 1)""",
            (
                run_b["run"]["runId"],
                thread_a["id"],
                "1" * 64,
                "2" * 64,
                "3" * 64,
            ),
        )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO agent_messages
               (id, project_id, thread_id, sequence, role, author_type, kind,
                content, citations_json, generated_content_json, execution_json,
                reply_to_message_id, run_id, created_at, advisory_only, is_simulated)
               VALUES ('false-advisory', 'project-a', ?, 99, 'business', 'human',
                       'user_input', 'x', '[]', NULL, NULL, NULL, ?, '2026', 0, 0)""",
            (thread_a["id"], completed_a["run"]["runId"]),
        )
    for raw in completed_a["messages"]:
        assert AgentMessage.model_validate(raw).advisory_only is True
    assert AgentRunRecord.model_validate(completed_a["run"]).advisory_only is True
    repository.close()


def test_long_thread_context_reads_latest_messages_in_ascending_order(tmp_path: Path) -> None:
    repository = AgentCommunicationRepository(tmp_path / "recent.db")
    _project(repository, "project-a")
    thread = _thread(repository)
    connection = repository.raw_connection_for_tests()
    # Use one durable run as the parent for a long immutable advisory transcript.
    reserved = _reserve(repository, "project-a", thread, key="long-run-000001")
    run_id = reserved["run"]["runId"]
    connection.execute(
        "UPDATE agent_runs SET status='completed', finished_at='2026', lease_until=0 WHERE run_id=?",
        (run_id,),
    )
    for sequence in range(1, 81):
        connection.execute(
            """INSERT INTO agent_messages
               (id, project_id, thread_id, sequence, role, author_type, kind,
                content, citations_json, generated_content_json, execution_json,
                reply_to_message_id, run_id, created_at, advisory_only, is_simulated)
               VALUES (?, 'project-a', ?, ?, 'business', 'human', 'user_input',
                       ?, '[]', NULL, NULL, NULL, ?, '2026', 1, 0)""",
            (f"recent-{sequence}", thread["id"], sequence, f"消息 {sequence}", run_id),
        )
    recent = repository.list_recent_messages("project-a", thread["id"], limit=40)
    assert [item["sequence"] for item in recent] == list(range(41, 81))
    repository.close()


def _create_legacy_candidate(database: Path) -> None:
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT, payload_json TEXT, created_at TEXT, updated_at TEXT);
        INSERT INTO projects VALUES('project-a','A','{}','2026','2026');
        CREATE TABLE agent_threads(
            id TEXT PRIMARY KEY, project_id TEXT, title TEXT, status TEXT,
            version INTEGER, created_by_role TEXT, created_at TEXT, updated_at TEXT,
            UNIQUE(project_id,id));
        INSERT INTO agent_threads VALUES(
            'agent-thread-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','project-a','旧会话','active',4,
            'risk','2026','2026');
        CREATE TABLE agent_runs(
            run_id TEXT PRIMARY KEY, turn_id TEXT, project_id TEXT, thread_id TEXT,
            role TEXT, mode TEXT, status TEXT, idempotency_key TEXT,
            request_fingerprint TEXT, input_hash TEXT, expected_thread_version INTEGER,
            expected_policy_version INTEGER, provider_id TEXT, model_id TEXT,
            prompt_version TEXT, lease_token TEXT, lease_until REAL,
            attempt_count INTEGER, output_message_ids_json TEXT, error_json TEXT,
            started_at TEXT, finished_at TEXT);
        CREATE TABLE agent_messages(
            id TEXT PRIMARY KEY, project_id TEXT, thread_id TEXT, sequence INTEGER,
            channel_role TEXT, author_type TEXT, author_role TEXT, kind TEXT,
            content TEXT, addressed_to_roles_json TEXT, citations_json TEXT,
            generated_content_json TEXT, audience_snapshot_json TEXT,
            reply_to_message_id TEXT, run_id TEXT, created_at TEXT,
            advisory_only INTEGER, is_simulated INTEGER);
        CREATE TABLE agent_run_steps(
            id TEXT PRIMARY KEY, run_id TEXT, project_id TEXT, thread_id TEXT,
            step_index INTEGER, role TEXT, status TEXT, provider_id TEXT,
            model_id TEXT, prompt_version TEXT, input_hash TEXT, context_version TEXT,
            output_hash TEXT, error_json TEXT, started_at TEXT, finished_at TEXT);
        CREATE TABLE agent_governance_state(project_id TEXT PRIMARY KEY, version INTEGER, updated_at TEXT, updated_by_role TEXT);
        CREATE TABLE agent_channel_access(project_id TEXT, viewer_role TEXT, channel_role TEXT, can_read INTEGER, policy_version INTEGER, updated_at TEXT);
        CREATE TABLE agent_governance_events(id TEXT PRIMARY KEY, project_id TEXT, sequence INTEGER, expected_version INTEGER, action TEXT, actor_role TEXT, thread_id TEXT, viewer_role TEXT, channel_role TEXT, before_json TEXT, after_json TEXT, reason TEXT, created_at TEXT);
        CREATE TABLE agent_idempotency_records(project_id TEXT, key TEXT, operation TEXT, request_hash TEXT, response_json TEXT, status_code INTEGER, created_at TEXT, PRIMARY KEY(project_id,key));
        """
    )
    connection.close()


def test_restart_migrates_unpublished_multichannel_candidate_to_v8(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    _create_legacy_candidate(database)
    repository = AgentCommunicationRepository(database)
    thread = repository.get_thread(
        "project-a", "agent-thread-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    )
    assert thread["focusRole"] == "business"
    assert thread["version"] == 4
    events = repository.list_focus_events("project-a", thread["id"])
    assert events[0]["kind"] == "thread_migrated"
    tables = {
        row[0]
        for row in repository.raw_connection_for_tests().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "agent_channel_access" not in tables
    assert repository.raw_connection_for_tests().execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []
    repository.close()
    restarted = AgentCommunicationRepository(database)
    assert restarted.get_thread("project-a", thread["id"])["focusRole"] == "business"
    restarted.close()


def test_two_repository_instances_allow_exactly_one_active_run(tmp_path: Path) -> None:
    database = tmp_path / "concurrency.db"
    first = AgentCommunicationRepository(database)
    _project(first, "project-a")
    thread = _thread(first)
    second = AgentCommunicationRepository(database)
    barrier = threading.Barrier(2)
    results: list[str] = []

    def reserve(repository: AgentCommunicationRepository, key: str, fingerprint: str) -> None:
        barrier.wait()
        try:
            result = _reserve(
                repository,
                "project-a",
                thread,
                key=key,
                fingerprint=fingerprint,
            )
            results.append(result["action"])
        except ConflictError as exc:
            results.append(exc.code)

    threads = [
        threading.Thread(target=reserve, args=(first, "race-run-00001", "a" * 64)),
        threading.Thread(target=reserve, args=(second, "race-run-00002", "b" * 64)),
    ]
    for item in threads:
        item.start()
    for item in threads:
        item.join()
    assert sorted(results) == ["agent_run_active", "owner"]
    active = first.raw_connection_for_tests().execute(
        "SELECT COUNT(*) FROM agent_runs WHERE status='running'"
    ).fetchone()[0]
    assert active == 1
    second.close()
    first.close()
