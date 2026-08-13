from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

from app.contracts.agent_communication import (
    AGENT_COMMUNICATION_DISCLAIMER,
    AgentMessage,
    AgentRole,
)
from app.contracts.errors import (
    BusinessValidationError,
    ConflictError,
    ForbiddenError,
    IdempotencyConflictError,
    NotFoundError,
    VersionConflictError,
)
from app.models import utc_now
from app.repositories.schema import (
    IMMUTABLE_TABLES,
    SCHEMA_SQL,
    SCHEMA_VERSION,
    immutable_trigger_sql,
    migrate_agent_schema,
)


RunMode = Literal["disabled", "synthetic", "real"]
RunTerminalStatus = Literal[
    "completed", "needs_review", "out_of_scope", "failed", "unavailable"
]
ROLES = {role.value for role in AgentRole}


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any = None) -> Any:
    return default if value is None else json.loads(value)


def _hash(value: Any) -> str:
    return hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class AgentCommunicationRepository:
    """SQLite boundary for one-focus advisory collaboration sessions."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        raw_path = str(database_path)
        if raw_path.startswith("sqlite:///"):
            raw_path = raw_path.removeprefix("sqlite:///")
        if raw_path != ":memory:":
            path = Path(raw_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            raw_path = str(path)
        self.database_path = raw_path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            raw_path,
            check_same_thread=False,
            isolation_level=None,
            timeout=30.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._configure_connection()
        self._initialize_schema()

    def _configure_connection(self) -> None:
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=30000")
        if self.database_path != ":memory:":
            deadline = time.monotonic() + 30
            while True:
                try:
                    self._connection.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            self._connection.execute("PRAGMA synchronous=NORMAL")

    def _initialize_schema(self) -> None:
        with self._lock:
            migrate_agent_schema(self._connection)
            self._connection.executescript(SCHEMA_SQL)
            for table in IMMUTABLE_TABLES:
                self._connection.executescript(immutable_trigger_sql(table))
            self._connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def raw_connection_for_tests(self) -> sqlite3.Connection:
        return self._connection

    def create_thread(
        self,
        project_id: str,
        *,
        title: str,
        created_by_role: str,
        idempotency_key: str,
        request_hash: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_role(created_by_role)
        title = title.strip()
        if not title:
            raise BusinessValidationError("agent_thread_title_required", "title 不能为空。")
        with self._write_transaction() as connection:
            self._require_project(connection, project_id)
            replay = self._idempotency_replay(
                connection, project_id, idempotency_key, "create_thread", request_hash
            )
            if replay is not None:
                return replay
            now = utc_now()
            thread_id = thread_id or _new_id("agent-thread")
            try:
                connection.execute(
                    """INSERT INTO agent_threads
                       (id, project_id, title, status, focus_role, version,
                        created_by_role, closed_reason, created_at, updated_at)
                       VALUES (?, ?, ?, 'active', 'business', 1, ?, NULL, ?, ?)""",
                    (thread_id, project_id, title, created_by_role, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("agent_thread_conflict", "Agent thread 已存在。") from exc
            self._append_focus_event(
                connection,
                project_id=project_id,
                thread_id=thread_id,
                kind="thread_created",
                from_role=None,
                to_role="business",
                actor_role=created_by_role,
                reason="新建会话默认由业务焦点开始。",
                expected_version=0,
                resulting_version=1,
                created_at=now,
            )
            result = self._thread_from_row(
                self._thread_row(connection, project_id, thread_id)
            )
            self._store_idempotency(
                connection,
                project_id,
                idempotency_key,
                "create_thread",
                request_hash,
                result,
            )
            return result

    def get_thread(self, project_id: str, thread_id: str) -> dict[str, Any]:
        with self._read_transaction() as connection:
            return self._thread_from_row(self._thread_row(connection, project_id, thread_id))

    def get_latest_conclusion_snapshot(self, project_id: str) -> dict[str, Any]:
        """Return the newest single-focus session without mutating any authority table."""

        with self._read_transaction() as connection:
            self._require_project(connection, project_id)
            thread_row = connection.execute(
                """SELECT * FROM agent_threads
                   WHERE project_id = ?
                   ORDER BY updated_at DESC, created_at DESC, id DESC
                   LIMIT 1""",
                (project_id,),
            ).fetchone()
            if thread_row is None:
                return {
                    "thread": None,
                    "latestAgentMessage": None,
                    "messageCount": 0,
                    "agentMessageCount": 0,
                    "focusEventCount": 0,
                    "focusTransitionCount": 0,
                }

            thread_id = thread_row["id"]
            message_counts = connection.execute(
                """SELECT COUNT(*) AS message_count,
                          SUM(CASE WHEN author_type = 'agent' THEN 1 ELSE 0 END)
                              AS agent_message_count
                   FROM agent_messages
                   WHERE project_id = ? AND thread_id = ?""",
                (project_id, thread_id),
            ).fetchone()
            focus_counts = connection.execute(
                """SELECT COUNT(*) AS event_count,
                          SUM(CASE WHEN kind IN ('focus_transferred', 'focus_returned')
                              THEN 1 ELSE 0 END) AS transition_count
                   FROM agent_focus_events
                   WHERE project_id = ? AND thread_id = ?""",
                (project_id, thread_id),
            ).fetchone()
            latest_message_row = connection.execute(
                """SELECT * FROM agent_messages
                   WHERE project_id = ? AND thread_id = ? AND author_type = 'agent'
                   ORDER BY sequence DESC LIMIT 1""",
                (project_id, thread_id),
            ).fetchone()
            return {
                "thread": self._thread_from_row(thread_row),
                "latestAgentMessage": (
                    None
                    if latest_message_row is None
                    else self._message_from_row(latest_message_row)
                ),
                "messageCount": int(message_counts["message_count"] or 0),
                "agentMessageCount": int(message_counts["agent_message_count"] or 0),
                "focusEventCount": int(focus_counts["event_count"] or 0),
                "focusTransitionCount": int(focus_counts["transition_count"] or 0),
            }

    def list_messages(
        self,
        project_id: str,
        thread_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        self._validate_limit(limit)
        with self._read_transaction() as connection:
            self._thread_row(connection, project_id, thread_id)
            rows = connection.execute(
                """SELECT * FROM agent_messages
                   WHERE project_id = ? AND thread_id = ? AND sequence > ?
                   ORDER BY sequence LIMIT ?""",
                (project_id, thread_id, after_sequence, limit),
            ).fetchall()
            return [self._message_from_row(row) for row in rows]

    def list_recent_messages(
        self, project_id: str, thread_id: str, *, limit: int = 40
    ) -> list[dict[str, Any]]:
        self._validate_limit(limit)
        with self._read_transaction() as connection:
            self._thread_row(connection, project_id, thread_id)
            rows = connection.execute(
                """SELECT * FROM (
                       SELECT * FROM agent_messages
                       WHERE project_id = ? AND thread_id = ?
                       ORDER BY sequence DESC LIMIT ?
                   ) recent ORDER BY sequence""",
                (project_id, thread_id, limit),
            ).fetchall()
            return [self._message_from_row(row) for row in rows]

    def require_message(
        self, project_id: str, thread_id: str, message_id: str
    ) -> dict[str, Any]:
        with self._read_transaction() as connection:
            self._thread_row(connection, project_id, thread_id)
            row = connection.execute(
                """SELECT * FROM agent_messages
                   WHERE project_id = ? AND thread_id = ? AND id = ?""",
                (project_id, thread_id, message_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "agent_reply_message_not_found",
                    "replyToMessageId 不存在或不属于当前 project/thread。",
                )
            return self._message_from_row(row)

    def list_focus_events(
        self,
        project_id: str,
        thread_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        self._validate_limit(limit)
        with self._read_transaction() as connection:
            self._thread_row(connection, project_id, thread_id)
            rows = connection.execute(
                """SELECT * FROM agent_focus_events
                   WHERE project_id = ? AND thread_id = ? AND sequence > ?
                   ORDER BY sequence LIMIT ?""",
                (project_id, thread_id, after_sequence, limit),
            ).fetchall()
            return [self._focus_event_from_row(row) for row in rows]

    def transition_focus(
        self,
        project_id: str,
        thread_id: str,
        *,
        actor_role: str,
        to_focus_role: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        request_hash: str,
    ) -> dict[str, Any]:
        self._validate_role(actor_role)
        self._validate_role(to_focus_role)
        with self._write_transaction() as connection:
            self._require_project(connection, project_id)
            replay = self._idempotency_replay(
                connection, project_id, idempotency_key, "transition_focus", request_hash
            )
            if replay is not None:
                return replay
            thread = self._thread_from_row(
                self._thread_row(connection, project_id, thread_id)
            )
            if thread["status"] != "active":
                raise ConflictError("agent_thread_not_active", "非 active 会话不能切换焦点。")
            self._check_version(expected_version, thread["version"])
            if actor_role != thread["focusRole"]:
                raise ForbiddenError(
                    "agent_focus_transition_forbidden",
                    "只有当前焦点角色可请求服务端切换焦点。",
                )
            if to_focus_role == thread["focusRole"]:
                raise ConflictError("agent_focus_unchanged", "目标焦点与当前焦点相同。")
            allowed = {
                "business": {"risk", "leadership"},
                "risk": {"business"},
                "leadership": {"business"},
            }
            if to_focus_role not in allowed[thread["focusRole"]]:
                raise ConflictError(
                    "agent_focus_transition_invalid", "该单焦点切换路径不允许。"
                )
            self._require_no_active_run(connection, project_id, thread_id)
            now = utc_now()
            next_version = thread["version"] + 1
            cursor = connection.execute(
                """UPDATE agent_threads SET focus_role = ?, version = ?, updated_at = ?
                   WHERE project_id = ? AND id = ? AND version = ? AND status = 'active'""",
                (
                    to_focus_role,
                    next_version,
                    now,
                    project_id,
                    thread_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("agent_focus_race", "焦点已被其他请求更新。")
            self._append_focus_event(
                connection,
                project_id=project_id,
                thread_id=thread_id,
                kind=("focus_returned" if to_focus_role == "business" else "focus_transferred"),
                from_role=thread["focusRole"],
                to_role=to_focus_role,
                actor_role=actor_role,
                reason=reason,
                expected_version=expected_version,
                resulting_version=next_version,
                created_at=now,
            )
            result = self._thread_from_row(
                self._thread_row(connection, project_id, thread_id)
            )
            self._store_idempotency(
                connection,
                project_id,
                idempotency_key,
                "transition_focus",
                request_hash,
                result,
            )
            return result

    def control_thread(
        self,
        project_id: str,
        thread_id: str,
        *,
        actor_role: str,
        action: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        request_hash: str,
    ) -> dict[str, Any]:
        self._validate_role(actor_role)
        if action not in {"close", "reject", "reopen"}:
            raise BusinessValidationError("agent_control_invalid", "会话控制动作无效。")
        with self._write_transaction() as connection:
            self._require_project(connection, project_id)
            replay = self._idempotency_replay(
                connection, project_id, idempotency_key, "control_thread", request_hash
            )
            if replay is not None:
                return replay
            thread = self._thread_from_row(
                self._thread_row(connection, project_id, thread_id)
            )
            self._check_version(expected_version, thread["version"])
            self._require_no_active_run(connection, project_id, thread_id)
            if action == "reopen":
                if thread["status"] == "active":
                    raise ConflictError("agent_thread_already_active", "会话已经是 active。")
                if actor_role != "leadership":
                    raise ForbiddenError(
                        "agent_reopen_forbidden", "只有本地 leadership principal 可请求重开会话。"
                    )
                status = "active"
                focus_role = "business"
                closed_reason = None
                event_kind = "thread_reopened"
            else:
                if thread["status"] != "active":
                    raise ConflictError("agent_thread_not_active", "会话已经结束。")
                if actor_role != thread["focusRole"]:
                    raise ForbiddenError(
                        "agent_control_forbidden", "只有当前焦点角色可结束协作会话。"
                    )
                if action == "reject" and thread["focusRole"] != "risk":
                    raise ForbiddenError(
                        "agent_reject_forbidden",
                        "只有 risk 获得焦点时可结束为 collaboration rejected；它不是正式拒绝。",
                    )
                status = "rejected" if action == "reject" else "closed"
                focus_role = thread["focusRole"]
                closed_reason = reason
                event_kind = "thread_rejected" if action == "reject" else "thread_closed"
            next_version = thread["version"] + 1
            now = utc_now()
            cursor = connection.execute(
                """UPDATE agent_threads
                   SET status = ?, focus_role = ?, closed_reason = ?, version = ?, updated_at = ?
                   WHERE project_id = ? AND id = ? AND version = ?""",
                (
                    status,
                    focus_role,
                    closed_reason,
                    next_version,
                    now,
                    project_id,
                    thread_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("agent_control_race", "会话已被其他请求更新。")
            self._append_focus_event(
                connection,
                project_id=project_id,
                thread_id=thread_id,
                kind=event_kind,
                from_role=thread["focusRole"],
                to_role=focus_role,
                actor_role=actor_role,
                reason=reason,
                expected_version=expected_version,
                resulting_version=next_version,
                created_at=now,
            )
            result = self._thread_from_row(
                self._thread_row(connection, project_id, thread_id)
            )
            self._store_idempotency(
                connection,
                project_id,
                idempotency_key,
                "control_thread",
                request_hash,
                result,
            )
            return result

    def reserve_turn(
        self,
        project_id: str,
        thread_id: str,
        *,
        turn_id: str,
        role: str,
        mode: RunMode,
        idempotency_key: str,
        request_fingerprint: str,
        input_hash: str,
        context_version: str,
        expected_thread_version: int,
        provider_id: str | None,
        model_id: str | None,
        prompt_version: str | None,
        lease_seconds: float,
    ) -> dict[str, Any]:
        self._validate_role(role)
        if mode not in {"disabled", "synthetic", "real"}:
            raise BusinessValidationError("agent_mode_invalid", "mode 无效。")
        if lease_seconds <= 0:
            raise BusinessValidationError("agent_lease_invalid", "leaseSeconds 必须大于 0。")
        with self._write_transaction() as connection:
            thread = self._thread_from_row(
                self._thread_row(connection, project_id, thread_id)
            )
            if thread["status"] != "active":
                raise ConflictError("agent_thread_not_active", "非 active 会话不能创建 turn。")
            if thread["focusRole"] != role:
                raise ForbiddenError(
                    "agent_focus_mismatch", "请求 principal 不是服务端当前焦点角色。"
                )
            foreign_idempotency = connection.execute(
                """SELECT operation, request_hash FROM agent_idempotency_records
                   WHERE project_id = ? AND key = ?""",
                (project_id, idempotency_key),
            ).fetchone()
            if foreign_idempotency is not None:
                if (
                    foreign_idempotency["operation"] != "turn"
                    or foreign_idempotency["request_hash"] != request_fingerprint
                ):
                    raise IdempotencyConflictError()
            existing = connection.execute(
                "SELECT * FROM agent_runs WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            ).fetchone()
            now_epoch = time.time()
            if existing is not None:
                return self._existing_reservation(
                    connection,
                    existing,
                    request_fingerprint=request_fingerprint,
                    now_epoch=now_epoch,
                )
            self._check_version(expected_thread_version, thread["version"])
            active = connection.execute(
                """SELECT * FROM agent_runs WHERE project_id = ? AND thread_id = ?
                   AND status = 'running'""",
                (project_id, thread_id),
            ).fetchone()
            if active is not None:
                if active["lease_until"] > now_epoch:
                    raise ConflictError(
                        "agent_run_active",
                        "会话存在其他 active run，请在其完成后使用新的请求重试。",
                    )
                self._expire_run(connection, active)
            run_id = _new_id("agent-run")
            lease_token = uuid.uuid4().hex
            started_at = utc_now()
            try:
                connection.execute(
                    """INSERT INTO agent_runs
                       (run_id, turn_id, project_id, thread_id, role, mode, status,
                        idempotency_key, request_fingerprint, input_hash,
                        expected_thread_version, context_version, provider_id,
                        model_id, prompt_version, lease_token, lease_until,
                        attempt_count, output_message_ids_json, output_hash,
                        error_json, started_at, finished_at, advisory_only)
                       VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               1, '[]', NULL, NULL, ?, NULL, 1)""",
                    (
                        run_id,
                        turn_id,
                        project_id,
                        thread_id,
                        role,
                        mode,
                        idempotency_key,
                        request_fingerprint,
                        input_hash,
                        expected_thread_version,
                        context_version,
                        provider_id,
                        model_id,
                        prompt_version,
                        lease_token,
                        now_epoch + lease_seconds,
                        started_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    "agent_run_conflict", "同一会话已有 active run 或幂等键冲突。"
                ) from exc
            return {
                "action": "owner",
                "leaseToken": lease_token,
                "run": self._run_from_row(
                    self._run_row(connection, project_id, run_id)
                ),
            }

    def lookup_turn(
        self,
        project_id: str,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> dict[str, Any] | None:
        """Resolve a turn replay before stale expectedVersion/context checks."""

        with self._write_transaction() as connection:
            self._require_project(connection, project_id)
            record = connection.execute(
                """SELECT operation, request_hash FROM agent_idempotency_records
                   WHERE project_id = ? AND key = ?""",
                (project_id, idempotency_key),
            ).fetchone()
            if record is not None and (
                record["operation"] != "turn"
                or record["request_hash"] != request_fingerprint
            ):
                raise IdempotencyConflictError()
            row = connection.execute(
                """SELECT * FROM agent_runs
                   WHERE project_id = ? AND idempotency_key = ?""",
                (project_id, idempotency_key),
            ).fetchone()
            if row is None:
                if record is not None:
                    raise ConflictError(
                        "agent_idempotency_corrupt",
                        "turn 幂等记录缺少对应 run。",
                    )
                return None
            if row["request_fingerprint"] != request_fingerprint:
                raise IdempotencyConflictError()
            if row["status"] == "running" and row["lease_until"] <= time.time():
                self._expire_run(connection, row)
                row = self._run_row(connection, project_id, row["run_id"])
            return self._run_from_row(row)

    def finalize_turn(
        self,
        project_id: str,
        run_id: str,
        *,
        lease_token: str,
        status: Literal["completed", "needs_review", "out_of_scope"],
        messages: Sequence[Mapping[str, Any]],
        step: Mapping[str, Any],
        output_hash: str,
    ) -> dict[str, Any]:
        with self._write_transaction() as connection:
            run_row = self._run_row(connection, project_id, run_id)
            if run_row["status"] in {"completed", "needs_review", "out_of_scope"}:
                return self._completed_payload(connection, project_id, run_row)
            if run_row["status"] != "running":
                raise ConflictError("agent_run_fenced", "Agent run 已被其他 owner 终结。")
            self._check_lease(run_row, lease_token)
            thread = self._thread_from_row(
                self._thread_row(connection, project_id, run_row["thread_id"])
            )
            self._check_version(run_row["expected_thread_version"], thread["version"])
            if thread["status"] != "active" or thread["focusRole"] != run_row["role"]:
                raise ConflictError("agent_focus_race", "会话状态或焦点已变化。")
            self._insert_run_step(connection, project_id, run_row, step)
            sequence = int(
                connection.execute(
                    """SELECT COALESCE(MAX(sequence), 0) FROM agent_messages
                       WHERE project_id = ? AND thread_id = ?""",
                    (project_id, run_row["thread_id"]),
                ).fetchone()[0]
            )
            created: list[dict[str, Any]] = []
            for payload in messages:
                sequence += 1
                created.append(
                    self._insert_message(
                        connection,
                        project_id=project_id,
                        thread_id=run_row["thread_id"],
                        run_id=run_id,
                        sequence=sequence,
                        payload=payload,
                    )
                )
            next_version = thread["version"] + 1
            next_focus = (
                "business"
                if run_row["role"] in {"risk", "leadership"}
                else thread["focusRole"]
            )
            finished_at = utc_now()
            cursor = connection.execute(
                """UPDATE agent_threads SET version = ?, focus_role = ?, updated_at = ?
                   WHERE project_id = ? AND id = ? AND version = ?
                     AND status = 'active' AND focus_role = ?""",
                (
                    next_version,
                    next_focus,
                    finished_at,
                    project_id,
                    run_row["thread_id"],
                    run_row["expected_thread_version"],
                    run_row["role"],
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("agent_focus_race", "会话焦点在 finalize 前已变化。")
            if next_focus != run_row["role"]:
                self._append_focus_event(
                    connection,
                    project_id=project_id,
                    thread_id=run_row["thread_id"],
                    kind="focus_returned",
                    from_role=run_row["role"],
                    to_role="business",
                    actor_role=run_row["role"],
                    reason="临时焦点 turn 完成，服务端自动返回业务主工作区。",
                    expected_version=run_row["expected_thread_version"],
                    resulting_version=next_version,
                    created_at=finished_at,
                )
            cursor = connection.execute(
                """UPDATE agent_runs
                   SET status = ?, output_message_ids_json = ?, output_hash = ?,
                       finished_at = ?, lease_until = 0
                   WHERE project_id = ? AND run_id = ? AND status = 'running'
                     AND lease_token = ? AND lease_until >= ?""",
                (
                    status,
                    _dump([item["id"] for item in created]),
                    output_hash,
                    finished_at,
                    project_id,
                    run_id,
                    lease_token,
                    time.time(),
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("agent_run_fenced", "Agent run lease 已失效。")
            self._store_idempotency(
                connection,
                project_id,
                run_row["idempotency_key"],
                "turn",
                run_row["request_fingerprint"],
                {"runId": run_id},
            )
            return {
                "action": "completed",
                "run": self._run_from_row(
                    self._run_row(connection, project_id, run_id)
                ),
                "messages": created,
                "thread": self._thread_from_row(
                    self._thread_row(connection, project_id, run_row["thread_id"])
                ),
            }

    def fail_turn(
        self,
        project_id: str,
        run_id: str,
        *,
        lease_token: str,
        status: Literal["failed", "unavailable"],
        error: Mapping[str, Any],
        step: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._write_transaction() as connection:
            row = self._run_row(connection, project_id, run_id)
            if row["status"] != "running":
                if row["status"] in {"failed", "unavailable"}:
                    return self._run_from_row(row)
                raise ConflictError("agent_run_fenced", "Agent run 已由其他 owner 终结。")
            self._check_lease(row, lease_token)
            if step is not None:
                self._insert_run_step(connection, project_id, row, step)
            finished_at = utc_now()
            cursor = connection.execute(
                """UPDATE agent_runs SET status = ?, error_json = ?, finished_at = ?,
                       lease_until = 0
                   WHERE project_id = ? AND run_id = ? AND status = 'running'
                     AND lease_token = ? AND lease_until >= ?""",
                (
                    status,
                    _dump(dict(error)),
                    finished_at,
                    project_id,
                    run_id,
                    lease_token,
                    time.time(),
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("agent_run_fenced", "Agent run lease 已失效。")
            self._store_idempotency(
                connection,
                project_id,
                row["idempotency_key"],
                "turn",
                row["request_fingerprint"],
                {"runId": run_id},
            )
            return self._run_from_row(self._run_row(connection, project_id, run_id))

    def get_run(self, project_id: str, run_id: str) -> dict[str, Any]:
        with self._read_transaction() as connection:
            return self._run_from_row(self._run_row(connection, project_id, run_id))

    def _completed_payload(
        self, connection: sqlite3.Connection, project_id: str, run_row: sqlite3.Row
    ) -> dict[str, Any]:
        ids = _load(run_row["output_message_ids_json"], [])
        messages: list[dict[str, Any]] = []
        for message_id in ids:
            row = connection.execute(
                """SELECT * FROM agent_messages
                   WHERE project_id = ? AND thread_id = ? AND id = ?""",
                (project_id, run_row["thread_id"], message_id),
            ).fetchone()
            if row is not None:
                messages.append(self._message_from_row(row))
        return {
            "action": "replay",
            "run": self._run_from_row(run_row),
            "messages": messages,
            "thread": self._thread_from_row(
                self._thread_row(connection, project_id, run_row["thread_id"])
            ),
        }

    def _insert_message(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        thread_id: str,
        run_id: str,
        sequence: int,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        raw = {
            "id": payload.get("id") or _new_id("agent-message"),
            "projectId": project_id,
            "threadId": thread_id,
            "sequence": sequence,
            "role": payload["role"],
            "authorType": payload["authorType"],
            "kind": payload["kind"],
            "content": payload["content"],
            "citations": payload.get("citations", []),
            "generatedContent": payload.get("generatedContent"),
            "execution": payload.get("execution"),
            "replyToMessageId": payload.get("replyToMessageId"),
            "runId": run_id,
            "createdAt": payload.get("createdAt") or utc_now(),
            "advisoryOnly": True,
            "isSimulated": bool(payload.get("isSimulated", False)),
        }
        message = AgentMessage.model_validate(raw).model_dump(
            mode="json", by_alias=True
        )
        connection.execute(
            """INSERT INTO agent_messages
               (id, project_id, thread_id, sequence, role, author_type, kind,
                content, citations_json, generated_content_json, execution_json,
                reply_to_message_id, run_id, created_at, advisory_only, is_simulated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                message["id"],
                project_id,
                thread_id,
                sequence,
                message["role"],
                message["authorType"],
                message["kind"],
                message["content"],
                _dump(message["citations"]),
                (
                    None
                    if message["generatedContent"] is None
                    else _dump(message["generatedContent"])
                ),
                None if message["execution"] is None else _dump(message["execution"]),
                message["replyToMessageId"],
                run_id,
                message["createdAt"],
                int(message["isSimulated"]),
            ),
        )
        return message

    def _insert_run_step(
        self,
        connection: sqlite3.Connection,
        project_id: str,
        run_row: sqlite3.Row,
        step: Mapping[str, Any],
    ) -> None:
        if int(step.get("stepIndex", 1)) != 1:
            raise BusinessValidationError(
                "agent_step_invalid", "单焦点 run 只能写入 step 1。"
            )
        for key, expected in (
            ("role", run_row["role"]),
            ("providerId", run_row["provider_id"]),
            ("modelId", run_row["model_id"]),
            ("promptVersion", run_row["prompt_version"]),
            ("inputHash", run_row["input_hash"]),
            ("contextVersion", run_row["context_version"]),
        ):
            if step.get(key) != expected:
                raise ConflictError(
                    "agent_provenance_mismatch", "run 与 step provenance 不一致。"
                )
        connection.execute(
            """INSERT INTO agent_run_steps
               (id, run_id, project_id, thread_id, step_index, role, status,
                provider_id, model_id, prompt_version, input_hash,
                context_version, output_hash, error_json, started_at,
                finished_at, advisory_only)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                step.get("stepId") or _new_id("agent-step"),
                run_row["run_id"],
                project_id,
                run_row["thread_id"],
                step["role"],
                step["status"],
                step["providerId"],
                step["modelId"],
                step["promptVersion"],
                step["inputHash"],
                step["contextVersion"],
                step.get("outputHash"),
                None if step.get("error") is None else _dump(step["error"]),
                step["startedAt"],
                step["finishedAt"],
            ),
        )

    def _existing_reservation(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        request_fingerprint: str,
        now_epoch: float,
    ) -> dict[str, Any]:
        if row["request_fingerprint"] != request_fingerprint:
            raise IdempotencyConflictError()
        if row["status"] == "running":
            if row["lease_until"] > now_epoch:
                return {"action": "wait", "run": self._run_from_row(row)}
            self._expire_run(connection, row)
            row = self._run_row(connection, row["project_id"], row["run_id"])
        return {"action": "replay", "run": self._run_from_row(row)}

    @staticmethod
    def _expire_run(connection: sqlite3.Connection, row: sqlite3.Row) -> None:
        now = utc_now()
        connection.execute(
            """UPDATE agent_runs
               SET status = 'failed', error_json = ?, finished_at = ?, lease_until = 0
               WHERE project_id = ? AND run_id = ? AND status = 'running'""",
            (
                _dump(
                    {
                        "code": "agent_run_lease_expired",
                        "message": "Agent run lease 已过期。",
                        "retryable": True,
                    }
                ),
                now,
                row["project_id"],
                row["run_id"],
            ),
        )

    def _run_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        mode = row["mode"]
        execution = {
            "mode": mode,
            "providerId": row["provider_id"],
            "modelId": row["model_id"],
            "promptVersion": row["prompt_version"],
            "inputHash": row["input_hash"],
            "contextVersion": row["context_version"],
            "outputHash": row["output_hash"],
            "advisoryOnly": True,
            "isSimulated": mode == "synthetic",
            "dataStatus": {
                "disabled": "unavailable",
                "synthetic": "simulated",
                "real": "provider_generated_unverified",
            }[mode],
            "source": "agent_disabled" if mode == "disabled" else row["provider_id"],
            "disclaimer": AGENT_COMMUNICATION_DISCLAIMER,
        }
        steps = self._connection.execute(
            """SELECT * FROM agent_run_steps
               WHERE project_id = ? AND run_id = ? ORDER BY step_index""",
            (row["project_id"], row["run_id"]),
        ).fetchall()
        return {
            "runId": row["run_id"],
            "turnId": row["turn_id"],
            "projectId": row["project_id"],
            "threadId": row["thread_id"],
            "role": row["role"],
            "status": row["status"],
            "requestFingerprint": row["request_fingerprint"],
            "attemptCount": row["attempt_count"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
            "error": _load(row["error_json"]),
            "execution": execution,
            "steps": [self._run_step_from_row(item) for item in steps],
            "advisoryOnly": True,
        }

    @staticmethod
    def _run_step_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "stepId": row["id"],
            "runId": row["run_id"],
            "stepIndex": row["step_index"],
            "role": row["role"],
            "status": row["status"],
            "providerId": row["provider_id"],
            "modelId": row["model_id"],
            "promptVersion": row["prompt_version"],
            "inputHash": row["input_hash"],
            "contextVersion": row["context_version"],
            "outputHash": row["output_hash"],
            "startedAt": row["started_at"],
            "finishedAt": row["finished_at"],
            "error": _load(row["error_json"]),
            "advisoryOnly": True,
        }

    @staticmethod
    def _thread_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "projectId": row["project_id"],
            "title": row["title"],
            "version": row["version"],
            "status": row["status"],
            "focusRole": row["focus_role"],
            "createdByRole": row["created_by_role"],
            "closedReason": row["closed_reason"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "projectId": row["project_id"],
            "threadId": row["thread_id"],
            "sequence": row["sequence"],
            "role": row["role"],
            "authorType": row["author_type"],
            "kind": row["kind"],
            "content": row["content"],
            "citations": _load(row["citations_json"], []),
            "generatedContent": _load(row["generated_content_json"]),
            "execution": _load(row["execution_json"]),
            "replyToMessageId": row["reply_to_message_id"],
            "runId": row["run_id"],
            "createdAt": row["created_at"],
            "immutable": True,
            "advisoryOnly": True,
            "isSimulated": bool(row["is_simulated"]),
        }

    @staticmethod
    def _focus_event_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "projectId": row["project_id"],
            "threadId": row["thread_id"],
            "sequence": row["sequence"],
            "kind": row["kind"],
            "fromFocusRole": row["from_focus_role"],
            "toFocusRole": row["to_focus_role"],
            "actorRole": row["actor_role"],
            "reason": row["reason"],
            "expectedVersion": row["expected_version"],
            "resultingVersion": row["resulting_version"],
            "createdAt": row["created_at"],
            "immutable": True,
        }

    def _append_focus_event(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        thread_id: str,
        kind: str,
        from_role: str | None,
        to_role: str,
        actor_role: str,
        reason: str,
        expected_version: int,
        resulting_version: int,
        created_at: str,
    ) -> None:
        sequence = int(
            connection.execute(
                """SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_focus_events
                   WHERE project_id = ? AND thread_id = ?""",
                (project_id, thread_id),
            ).fetchone()[0]
        )
        connection.execute(
            """INSERT INTO agent_focus_events
               (id, project_id, thread_id, sequence, kind, from_focus_role,
                to_focus_role, actor_role, reason, expected_version,
                resulting_version, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _new_id("agent-focus"),
                project_id,
                thread_id,
                sequence,
                kind,
                from_role,
                to_role,
                actor_role,
                reason,
                expected_version,
                resulting_version,
                created_at,
            ),
        )

    @staticmethod
    def _require_no_active_run(
        connection: sqlite3.Connection, project_id: str, thread_id: str
    ) -> None:
        row = connection.execute(
            """SELECT project_id, run_id, lease_until FROM agent_runs
               WHERE project_id = ? AND thread_id = ? AND status = 'running'""",
            (project_id, thread_id),
        ).fetchone()
        if row is None:
            return
        if row["lease_until"] <= time.time():
            AgentCommunicationRepository._expire_run(connection, row)
            return
        raise ConflictError(
            "agent_run_active",
            "会话存在 active run，完成或过期回收前不能切换焦点或结束会话。",
        )

    @staticmethod
    def _check_lease(row: sqlite3.Row, lease_token: str) -> None:
        if row["lease_token"] != lease_token or row["lease_until"] < time.time():
            raise ConflictError("agent_run_fenced", "Agent run lease 已失效。")

    @staticmethod
    def _check_version(expected: int, actual: int) -> None:
        if expected != actual:
            raise VersionConflictError(expected_version=expected, actual_version=actual)

    @staticmethod
    def _validate_role(role: str) -> None:
        if role not in ROLES:
            raise BusinessValidationError("agent_role_invalid", "Agent role 无效。")

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if limit < 1 or limit > 1000:
            raise BusinessValidationError("agent_limit_invalid", "limit 必须为 1..1000。")

    @staticmethod
    def _require_project(connection: sqlite3.Connection, project_id: str) -> None:
        if connection.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone() is None:
            raise NotFoundError("project_not_found", "项目不存在。")

    @staticmethod
    def _thread_row(
        connection: sqlite3.Connection, project_id: str, thread_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM agent_threads WHERE project_id = ? AND id = ?",
            (project_id, thread_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("agent_thread_not_found", "Agent thread 不存在。")
        return row

    @staticmethod
    def _run_row(
        connection: sqlite3.Connection, project_id: str, run_id: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM agent_runs WHERE project_id = ? AND run_id = ?",
            (project_id, run_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("agent_run_not_found", "Agent run 不存在。")
        return row

    @staticmethod
    def _idempotency_replay(
        connection: sqlite3.Connection,
        project_id: str,
        key: str,
        operation: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """SELECT * FROM agent_idempotency_records
               WHERE project_id = ? AND key = ?""",
            (project_id, key),
        ).fetchone()
        if row is None:
            return None
        if row["operation"] != operation or row["request_hash"] != request_hash:
            raise IdempotencyConflictError()
        return _load(row["response_json"])

    @staticmethod
    def _store_idempotency(
        connection: sqlite3.Connection,
        project_id: str,
        key: str,
        operation: str,
        request_hash: str,
        response: Mapping[str, Any],
    ) -> None:
        try:
            connection.execute(
                """INSERT INTO agent_idempotency_records
                   (project_id, key, operation, request_hash, response_json,
                    status_code, created_at)
                   VALUES (?, ?, ?, ?, ?, 200, ?)""",
                (project_id, key, operation, request_hash, _dump(response), utc_now()),
            )
        except sqlite3.IntegrityError as exc:
            row = connection.execute(
                """SELECT operation, request_hash FROM agent_idempotency_records
                   WHERE project_id = ? AND key = ?""",
                (project_id, key),
            ).fetchone()
            if row is None or row["operation"] != operation or row["request_hash"] != request_hash:
                raise IdempotencyConflictError() from exc

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @contextmanager
    def _read_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()


__all__ = ["AgentCommunicationRepository"]
