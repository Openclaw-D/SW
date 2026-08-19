from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any

from app.contracts.errors import (
    BusinessValidationError,
    ConflictError,
    IdempotencyConflictError,
    NotFoundError,
    VersionConflictError,
)
from app.contracts.pre_review import PreReviewProjection
from app.contracts.pre_review_runtime import (
    JudgmentDiff,
    PreReviewBindings,
    PreReviewCheckpointCommand,
    PreReviewDimensionChange,
    PreReviewExecutionProvenance,
    PreReviewIssueActionCommand,
    PreReviewRunCommand,
    PreReviewRunRecord,
    PreReviewStateView,
    PreReviewSubmitCommand,
    PreReviewTendencyChange,
    PreReviewVisibleSnapshot,
    StoredPreReviewIssueAction,
)
from app.models import IdempotencyRecord, new_id, utc_now


WORKING_STATE_LABEL = "当前工作态"
HARD_SNAPSHOT_LIMIT = 5

_PROJECT_SCOPED_BINDINGS: tuple[tuple[str, str, str], ...] = (
    ("project_snapshot_id", "project_snapshots", "项目快照"),
    ("material_version_ids", "material_versions", "材料版本"),
    ("evidence_ref_ids", "evidence_references", "证据引用"),
    ("fact_version_ids", "fact_versions", "事实版本"),
    ("policy_result_ids", "policy_results", "制度结果"),
    ("review_event_ids", "review_events", "评审事件"),
    ("issue_action_ids", "pre_review_issue_actions", "问题动作"),
)


def _dump(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(by_alias=True, mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any = None) -> Any:
    return default if value is None else json.loads(value)


class PreReviewStore:
    """Persistence boundary for deterministic working runs and visible snapshots.

    Runs and their provenance are append-only audit rows and never become a
    visible version by themselves.  Visible snapshots are only the baseline on
    the first explicit start, explicit manual checkpoints, and the one locked
    final submission snapshot.
    """

    def __init__(self, repository: Any) -> None:
        self.repository = repository

    # ------------------------------------------------------------------ reads

    @staticmethod
    def _run(row: sqlite3.Row) -> PreReviewRunRecord:
        return PreReviewRunRecord(
            id=row["id"],
            project_id=row["project_id"],
            sequence=row["sequence"],
            trigger=row["trigger"],
            projection=_load(row["projection_json"], {}),
            bindings=_load(row["bindings_json"], {}),
            provenance=_load(row["provenance_json"], {}),
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> PreReviewVisibleSnapshot:
        version = int(row["visible_version"])
        return PreReviewVisibleSnapshot(
            id=row["id"],
            project_id=row["project_id"],
            visible_version=version,
            label=f"V{version}",
            kind=row["kind"],
            run_id=row["run_id"],
            projection=_load(row["projection_json"], {}),
            bindings=_load(row["bindings_json"], {}),
            created_at=row["created_at"],
            created_by=row["created_by"],
            locked_at=row["locked_at"],
            immutable=True,
        )

    def latest_run(
        self, project_id: str, connection: sqlite3.Connection
    ) -> PreReviewRunRecord | None:
        row = connection.execute(
            "SELECT * FROM pre_review_runs WHERE project_id = ? "
            "ORDER BY sequence DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return None if row is None else self._run(row)

    def list_snapshots(
        self, project_id: str, connection: sqlite3.Connection
    ) -> list[PreReviewVisibleSnapshot]:
        rows = connection.execute(
            "SELECT * FROM pre_review_snapshots WHERE project_id = ? "
            "ORDER BY visible_version",
            (project_id,),
        ).fetchall()
        return [self._snapshot(row) for row in rows]

    def list_issue_actions(
        self, project_id: str, connection: sqlite3.Connection
    ) -> list[StoredPreReviewIssueAction]:
        rows = connection.execute(
            "SELECT * FROM pre_review_issue_actions WHERE project_id = ? "
            "ORDER BY created_at, id",
            (project_id,),
        ).fetchall()
        return [StoredPreReviewIssueAction(**dict(row)) for row in rows]

    @staticmethod
    def _state_row(
        project_id: str, connection: sqlite3.Connection
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM pre_review_state WHERE project_id = ?", (project_id,)
        ).fetchone()

    @staticmethod
    def _require_project(project_id: str, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("project_not_found", "项目不存在或已删除。")

    def state_view(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        current_input_hash: str,
    ) -> PreReviewStateView:
        self._require_project(project_id, connection)
        state = self._state_row(project_id, connection)
        snapshots = self.list_snapshots(project_id, connection)
        run = self.latest_run(project_id, connection)
        if state is None or run is None:
            return PreReviewStateView(
                project_id=project_id,
                started=False,
                version=0,
                snapshot_limit=3,
                visible_snapshots=[],
                current_run=None,
                current_projection=None,
                current_bindings=None,
                stale=False,
                can_save_checkpoint=False,
                can_submit=False,
                submitted=False,
                submitted_snapshot_id=None,
            )
        submitted = state["submitted_snapshot_id"] is not None
        limit = int(state["snapshot_limit"])
        return PreReviewStateView(
            project_id=project_id,
            started=True,
            version=int(state["version"]),
            snapshot_limit=limit,
            visible_snapshots=snapshots,
            current_run=run,
            current_projection=run.projection,
            current_bindings=run.bindings,
            stale=run.provenance.input_hash != current_input_hash,
            can_save_checkpoint=not submitted and len(snapshots) < limit - 1,
            can_submit=not submitted and len(snapshots) < limit,
            submitted=submitted,
            submitted_snapshot_id=state["submitted_snapshot_id"],
        )

    # --------------------------------------------------------------- bindings

    def _validate_bindings(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        bindings: PreReviewBindings,
    ) -> None:
        """Reject dangling and cross-project references before any capture."""

        for field_name, table, label in _PROJECT_SCOPED_BINDINGS:
            value = getattr(bindings, field_name)
            ids = [value] if isinstance(value, str) else list(value)
            for ref_id in ids:
                row = connection.execute(
                    f"SELECT project_id FROM {table} WHERE id = ?", (ref_id,)
                ).fetchone()
                if row is None:
                    raise BusinessValidationError(
                        "pre_review_binding_not_found",
                        f"预审绑定引用的{label}不存在。",
                        details={"entity": table, "id": ref_id},
                    )
                if row["project_id"] != project_id:
                    raise BusinessValidationError(
                        "pre_review_cross_project_reference",
                        f"预审绑定引用了其他项目的{label}。",
                        details={"entity": table, "id": ref_id},
                    )
        snapshot = connection.execute(
            "SELECT version FROM project_snapshots WHERE id = ?",
            (bindings.project_snapshot_id,),
        ).fetchone()
        if snapshot is not None and int(snapshot["version"]) != (
            bindings.project_snapshot_version
        ):
            raise BusinessValidationError(
                "pre_review_binding_inconsistent",
                "项目快照版本绑定与权威快照不一致。",
                details={
                    "projectSnapshotId": bindings.project_snapshot_id,
                    "boundVersion": bindings.project_snapshot_version,
                    "actualVersion": int(snapshot["version"]),
                },
            )
        for ref_id in bindings.rule_version_ids:
            if connection.execute(
                "SELECT 1 FROM rule_versions WHERE id = ?", (ref_id,)
            ).fetchone() is None:
                raise BusinessValidationError(
                    "pre_review_binding_not_found",
                    "预审绑定引用的规则版本不存在。",
                    details={"entity": "rule_versions", "id": ref_id},
                )
        if bindings.review_event_ids:
            row = connection.execute(
                "SELECT MAX(sequence) AS value FROM review_events WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            max_sequence = int(row["value"] or 0)
            if bindings.review_event_sequence > max_sequence:
                raise BusinessValidationError(
                    "pre_review_binding_inconsistent",
                    "评审事件水位超过了当前项目实际存在的评审事件。",
                    details={
                        "reviewEventSequence": bindings.review_event_sequence,
                        "maxReviewEventSequence": max_sequence,
                    },
                )
        approval = connection.execute(
            "SELECT version, state FROM approval_states WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if approval is not None and (
            bindings.approval_version != int(approval["version"])
            or bindings.approval_status != approval["state"]
        ):
            raise BusinessValidationError(
                "pre_review_binding_inconsistent",
                "审批绑定与权威审批状态不一致。",
                details={
                    "approvalVersion": int(approval["version"]),
                    "approvalStatus": approval["state"],
                },
            )

    # ------------------------------------------------------------ idempotency

    @staticmethod
    def _command_payload(command: Any, extra: Mapping[str, Any]) -> dict[str, Any]:
        payload = command.model_dump(
            by_alias=True,
            mode="json",
            exclude={"idempotency_key", "idempotencyKey"},
        )
        payload.update(extra)
        return payload

    def _idempotent(
        self,
        connection: sqlite3.Connection,
        *,
        key: str,
        operation: str,
        request_payload: Mapping[str, Any],
        response_model: type[Any],
        write: Callable[[], Any],
    ) -> Any:
        """Replay successful command results; never persist partial failures."""

        request_hash = hashlib.sha256(
            _dump({"operation": operation, "payload": request_payload}).encode("utf-8")
        ).hexdigest()
        previous = self.repository.get_idempotency_record(key, connection)
        if previous is not None:
            if previous.operation != operation or previous.request_hash != request_hash:
                raise IdempotencyConflictError()
            return response_model.model_validate(previous.response)
        connection.execute("SAVEPOINT pre_review_idempotent_write")
        try:
            result = write()
        except BaseException:
            connection.execute("ROLLBACK TO SAVEPOINT pre_review_idempotent_write")
            connection.execute("RELEASE SAVEPOINT pre_review_idempotent_write")
            raise
        connection.execute("RELEASE SAVEPOINT pre_review_idempotent_write")
        self.repository.create_idempotency_record(
            IdempotencyRecord(
                key=key,
                operation=operation,
                request_hash=request_hash,
                response=result.model_dump(by_alias=True, mode="json"),
                status_code=200,
                created_at=utc_now(),
            ),
            connection,
        )
        return result

    # ----------------------------------------------------------------- writes

    @staticmethod
    def _next_run_sequence(project_id: str, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS value "
            "FROM pre_review_runs WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row["value"])

    @staticmethod
    def _next_visible_version(
        project_id: str, connection: sqlite3.Connection
    ) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(visible_version), 0) + 1 AS value "
            "FROM pre_review_snapshots WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row["value"])

    def _insert_run(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        trigger: str,
        projection: PreReviewProjection,
        bindings: PreReviewBindings,
        provenance: PreReviewExecutionProvenance,
        actor: str,
        now: str,
    ) -> str:
        run_id = new_id("pre-review-run")
        sequence = self._next_run_sequence(project_id, connection)
        connection.execute(
            """INSERT INTO pre_review_runs
               (id, project_id, sequence, trigger, input_hash, calculation_version,
                projection_json, bindings_json, provenance_json, created_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                project_id,
                sequence,
                trigger,
                provenance.input_hash,
                provenance.calculation_version,
                _dump(projection),
                _dump(bindings),
                _dump(provenance),
                now,
                actor,
            ),
        )
        return run_id

    def create_run(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewRunCommand,
        projection: PreReviewProjection,
        bindings: PreReviewBindings,
        provenance: PreReviewExecutionProvenance,
        actor: str,
    ) -> PreReviewStateView:
        if command.idempotency_key is None:
            return self._create_run(
                project_id,
                connection,
                command=command,
                projection=projection,
                bindings=bindings,
                provenance=provenance,
                actor=actor,
            )
        return self._idempotent(
            connection,
            key=command.idempotency_key,
            operation="pre_review:run",
            request_payload=self._command_payload(
                command,
                {
                    "projection": _dump(projection),
                    "bindings": _dump(bindings),
                    "provenance": _dump(provenance),
                    "actor": actor,
                },
            ),
            response_model=PreReviewStateView,
            write=lambda: self._create_run(
                project_id,
                connection,
                command=command,
                projection=projection,
                bindings=bindings,
                provenance=provenance,
                actor=actor,
            ),
        )

    def _create_run(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewRunCommand,
        projection: PreReviewProjection,
        bindings: PreReviewBindings,
        provenance: PreReviewExecutionProvenance,
        actor: str,
    ) -> PreReviewStateView:
        if command.trigger not in ("start", "rejudge"):
            raise BusinessValidationError(
                "pre_review_trigger_invalid",
                "预审运行触发器必须是 start 或 rejudge。",
                field="trigger",
            )
        if not 2 <= command.snapshot_limit <= HARD_SNAPSHOT_LIMIT:
            raise BusinessValidationError(
                "pre_review_snapshot_limit_invalid",
                f"可见快照上限必须在 2 到 {HARD_SNAPSHOT_LIMIT} 之间。",
                field="snapshotLimit",
                details={"hardSnapshotLimit": HARD_SNAPSHOT_LIMIT},
            )
        self._require_project(project_id, connection)
        self._validate_bindings(project_id, connection, bindings)
        state = self._state_row(project_id, connection)
        now = utc_now()
        if state is None:
            if command.trigger != "start":
                raise BusinessValidationError("pre_review_not_started", "请先开始预审。")
            if command.expected_version != 0:
                raise VersionConflictError(
                    expected_version=command.expected_version, actual_version=0
                )
            run_id = self._insert_run(
                connection,
                project_id=project_id,
                trigger="start",
                projection=projection,
                bindings=bindings,
                provenance=provenance,
                actor=actor,
                now=now,
            )
            connection.execute(
                """INSERT INTO pre_review_state
                   (project_id, version, snapshot_limit, latest_run_id,
                    submitted_snapshot_id, started_at, started_by, updated_at, updated_by)
                   VALUES (?, 1, ?, ?, NULL, ?, ?, ?, ?)""",
                (
                    project_id,
                    command.snapshot_limit,
                    run_id,
                    now,
                    actor,
                    now,
                    actor,
                ),
            )
            self._create_snapshot(
                project_id,
                connection,
                run_id=run_id,
                kind="baseline",
                projection=projection,
                bindings=bindings,
                actor=actor,
                locked=False,
            )
        else:
            actual = int(state["version"])
            if command.expected_version != actual:
                raise VersionConflictError(
                    expected_version=command.expected_version, actual_version=actual
                )
            if state["submitted_snapshot_id"] is not None:
                raise ConflictError(
                    "pre_review_submitted_locked",
                    "最终提交快照已锁定，不能再次运行预审。",
                )
            if command.trigger != "rejudge":
                raise BusinessValidationError(
                    "pre_review_already_started", "项目已经开始预审，请使用再次预审。"
                )
            if command.snapshot_limit != int(state["snapshot_limit"]):
                raise BusinessValidationError(
                    "pre_review_snapshot_limit_immutable",
                    "预审开始后不能改变可见快照上限。",
                    field="snapshotLimit",
                )
            run_id = self._insert_run(
                connection,
                project_id=project_id,
                trigger="rejudge",
                projection=projection,
                bindings=bindings,
                provenance=provenance,
                actor=actor,
                now=now,
            )
            connection.execute(
                """UPDATE pre_review_state
                   SET version = ?, latest_run_id = ?, updated_at = ?, updated_by = ?
                   WHERE project_id = ?""",
                (actual + 1, run_id, now, actor, project_id),
            )
        return self.state_view(
            project_id, connection, current_input_hash=provenance.input_hash
        )

    def _create_snapshot(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        kind: str,
        projection: PreReviewProjection,
        bindings: PreReviewBindings,
        actor: str,
        locked: bool,
    ) -> PreReviewVisibleSnapshot:
        version = self._next_visible_version(project_id, connection)
        now = utc_now()
        snapshot_id = new_id("pre-review-snapshot")
        connection.execute(
            """INSERT INTO pre_review_snapshots
               (id, project_id, visible_version, kind, run_id, projection_json,
                bindings_json, created_at, created_by, locked_at, immutable)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                snapshot_id,
                project_id,
                version,
                kind,
                run_id,
                _dump(projection),
                _dump(bindings),
                now,
                actor,
                now if locked else None,
            ),
        )
        row = connection.execute(
            "SELECT * FROM pre_review_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        return self._snapshot(row)

    def save_checkpoint(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewCheckpointCommand,
        actor: str,
        current_input_hash: str,
    ) -> PreReviewStateView:
        if command.idempotency_key is None:
            return self._save_checkpoint(
                project_id,
                connection,
                command=command,
                actor=actor,
                current_input_hash=current_input_hash,
            )
        return self._idempotent(
            connection,
            key=command.idempotency_key,
            operation="pre_review:checkpoint",
            request_payload=self._command_payload(
                command, {"actor": actor, "currentInputHash": current_input_hash}
            ),
            response_model=PreReviewStateView,
            write=lambda: self._save_checkpoint(
                project_id,
                connection,
                command=command,
                actor=actor,
                current_input_hash=current_input_hash,
            ),
        )

    def _save_checkpoint(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewCheckpointCommand,
        actor: str,
        current_input_hash: str,
    ) -> PreReviewStateView:
        self._require_project(project_id, connection)
        state = self._state_row(project_id, connection)
        if state is None:
            raise BusinessValidationError("pre_review_not_started", "请先开始预审。")
        actual = int(state["version"])
        if command.expected_version != actual:
            raise VersionConflictError(
                expected_version=command.expected_version, actual_version=actual
            )
        if state["submitted_snapshot_id"] is not None:
            raise ConflictError("pre_review_submitted_locked", "最终提交快照已锁定。")
        snapshots = self.list_snapshots(project_id, connection)
        limit = int(state["snapshot_limit"])
        if len(snapshots) >= limit - 1:
            raise ConflictError(
                "pre_review_checkpoint_limit",
                "已达到阶段版本上限，必须为最终提交保留一个槽位。",
                details={"snapshotLimit": limit, "visibleCount": len(snapshots)},
            )
        run = self.latest_run(project_id, connection)
        if run is None:
            raise BusinessValidationError("pre_review_not_started", "请先开始预审。")
        if run.provenance.input_hash != current_input_hash:
            raise ConflictError(
                "pre_review_working_state_stale",
                "当前权威状态已有变化，请再次预审后保存阶段版本。",
            )
        self._create_snapshot(
            project_id,
            connection,
            run_id=run.id,
            kind="checkpoint",
            projection=run.projection,
            bindings=run.bindings,
            actor=actor,
            locked=False,
        )
        now = utc_now()
        connection.execute(
            """UPDATE pre_review_state
               SET version = ?, updated_at = ?, updated_by = ? WHERE project_id = ?""",
            (actual + 1, now, actor, project_id),
        )
        return self.state_view(
            project_id, connection, current_input_hash=current_input_hash
        )

    def record_issue_action(
        self,
        project_id: str,
        issue_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewIssueActionCommand,
        actor: str,
        current_input_hash: str,
    ) -> PreReviewStateView:
        if command.idempotency_key is None:
            return self._record_issue_action(
                project_id,
                issue_id,
                connection,
                command=command,
                actor=actor,
                current_input_hash=current_input_hash,
            )
        return self._idempotent(
            connection,
            key=command.idempotency_key,
            operation="pre_review:issue_action",
            request_payload=self._command_payload(
                command,
                {
                    "issueId": issue_id,
                    "actor": actor,
                    "currentInputHash": current_input_hash,
                },
            ),
            response_model=PreReviewStateView,
            write=lambda: self._record_issue_action(
                project_id,
                issue_id,
                connection,
                command=command,
                actor=actor,
                current_input_hash=current_input_hash,
            ),
        )

    def _record_issue_action(
        self,
        project_id: str,
        issue_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewIssueActionCommand,
        actor: str,
        current_input_hash: str,
    ) -> PreReviewStateView:
        self._require_project(project_id, connection)
        state = self._state_row(project_id, connection)
        if state is None:
            raise BusinessValidationError("pre_review_not_started", "请先开始预审。")
        actual = int(state["version"])
        if command.expected_version != actual:
            raise VersionConflictError(
                expected_version=command.expected_version, actual_version=actual
            )
        if state["submitted_snapshot_id"] is not None:
            raise ConflictError("pre_review_submitted_locked", "最终提交快照已锁定。")
        run = self.latest_run(project_id, connection)
        if run is None:
            raise BusinessValidationError("pre_review_not_started", "请先开始预审。")
        if not any(item.id == issue_id for item in run.projection.issues):
            raise BusinessValidationError(
                "pre_review_issue_not_open", "该待办已不存在或不再处于未决状态。"
            )
        if command.action_type == "link_evidence":
            evidence = connection.execute(
                "SELECT project_id FROM evidence_references WHERE id = ?",
                (command.evidence_ref,),
            ).fetchone()
            if evidence is None:
                raise BusinessValidationError(
                    "pre_review_evidence_not_found",
                    "关联的证据不存在。",
                    field="evidenceRef",
                    details={"evidenceRef": command.evidence_ref},
                )
            if evidence["project_id"] != project_id:
                raise BusinessValidationError(
                    "pre_review_cross_project_reference",
                    "不能关联其他项目的证据。",
                    field="evidenceRef",
                    details={"evidenceRef": command.evidence_ref},
                )
        now = utc_now()
        connection.execute(
            """INSERT INTO pre_review_issue_actions
               (id, project_id, issue_id, action_type, evidence_ref, note,
                created_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("pre-review-action"),
                project_id,
                issue_id,
                command.action_type,
                command.evidence_ref,
                command.note.strip() if command.note else None,
                now,
                actor,
            ),
        )
        connection.execute(
            """UPDATE pre_review_state
               SET version = ?, updated_at = ?, updated_by = ? WHERE project_id = ?""",
            (actual + 1, now, actor, project_id),
        )
        # Actions change the deterministic source; the last run intentionally
        # becomes stale until the next explicit rejudge.
        return self.state_view(
            project_id, connection, current_input_hash=current_input_hash
        )

    def create_final_snapshot(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewSubmitCommand,
        projection: PreReviewProjection,
        bindings: PreReviewBindings,
        provenance: PreReviewExecutionProvenance,
        actor: str,
    ) -> PreReviewVisibleSnapshot:
        if command.idempotency_key is None:
            return self._create_final_snapshot(
                project_id,
                connection,
                command=command,
                projection=projection,
                bindings=bindings,
                provenance=provenance,
                actor=actor,
            )
        return self._idempotent(
            connection,
            key=command.idempotency_key,
            operation="pre_review:submit",
            request_payload=self._command_payload(
                command,
                {
                    "projection": _dump(projection),
                    "bindings": _dump(bindings),
                    "provenance": _dump(provenance),
                    "actor": actor,
                },
            ),
            response_model=PreReviewVisibleSnapshot,
            write=lambda: self._create_final_snapshot(
                project_id,
                connection,
                command=command,
                projection=projection,
                bindings=bindings,
                provenance=provenance,
                actor=actor,
            ),
        )

    def _create_final_snapshot(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        command: PreReviewSubmitCommand,
        projection: PreReviewProjection,
        bindings: PreReviewBindings,
        provenance: PreReviewExecutionProvenance,
        actor: str,
    ) -> PreReviewVisibleSnapshot:
        self._require_project(project_id, connection)
        state = self._state_row(project_id, connection)
        if state is None:
            raise BusinessValidationError(
                "pre_review_not_started", "正式送审前必须先开始预审。"
            )
        actual = int(state["version"])
        submitted_snapshot_id = state["submitted_snapshot_id"]
        if submitted_snapshot_id is not None:
            # Retrying a locked submission replays the same immutable final
            # snapshot; it is not a working mutation and never creates V+1.
            if command.expected_version not in (actual, actual - 1):
                raise VersionConflictError(
                    expected_version=command.expected_version, actual_version=actual
                )
            row = connection.execute(
                "SELECT * FROM pre_review_snapshots WHERE id = ?",
                (submitted_snapshot_id,),
            ).fetchone()
            return self._snapshot(row)
        if command.expected_version != actual:
            raise VersionConflictError(
                expected_version=command.expected_version, actual_version=actual
            )
        count = len(self.list_snapshots(project_id, connection))
        limit = int(state["snapshot_limit"])
        if count >= limit:
            raise ConflictError(
                "pre_review_snapshot_limit",
                "可见快照已达到上限，无法创建最终提交版本。",
                details={"snapshotLimit": limit, "visibleCount": count},
            )
        self._validate_bindings(project_id, connection, bindings)
        now = utc_now()
        run_id = self._insert_run(
            connection,
            project_id=project_id,
            trigger="submit",
            projection=projection,
            bindings=bindings,
            provenance=provenance,
            actor=actor,
            now=now,
        )
        snapshot = self._create_snapshot(
            project_id,
            connection,
            run_id=run_id,
            kind="final",
            projection=projection,
            bindings=bindings,
            actor=actor,
            locked=True,
        )
        connection.execute(
            """UPDATE pre_review_state
               SET version = version + 1, latest_run_id = ?, submitted_snapshot_id = ?,
                   updated_at = ?, updated_by = ? WHERE project_id = ?""",
            (run_id, snapshot.id, now, actor, project_id),
        )
        return snapshot

    # ------------------------------------------------------------------- diff

    def judgment_diff(
        self,
        project_id: str,
        connection: sqlite3.Connection,
        *,
        from_snapshot_id: str | None,
        to_snapshot_id: str | None,
    ) -> JudgmentDiff:
        self._require_project(project_id, connection)
        snapshots = self.list_snapshots(project_id, connection)
        if not snapshots:
            raise BusinessValidationError(
                "pre_review_snapshot_not_found", "项目尚无可比较的预审快照。"
            )
        by_id = {item.id: item for item in snapshots}
        if from_snapshot_id:
            before = by_id.get(from_snapshot_id)
        else:
            # Default comparison: the previous key snapshot -> current working
            # state, so unsaved rejudgments are explained against the last key.
            before = snapshots[-1]
        if before is None:
            raise BusinessValidationError(
                "pre_review_snapshot_not_found", "起始快照不存在或不属于当前项目。"
            )
        if to_snapshot_id:
            after_snapshot = by_id.get(to_snapshot_id)
            if after_snapshot is None:
                raise BusinessValidationError(
                    "pre_review_snapshot_not_found", "目标快照不存在或不属于当前项目。"
                )
            after_projection = after_snapshot.projection
            after_bindings = after_snapshot.bindings
            after_label = after_snapshot.label
            after_id: str | None = after_snapshot.id
        else:
            run = self.latest_run(project_id, connection)
            if run is None:
                raise BusinessValidationError(
                    "pre_review_run_not_found", "项目尚无当前预审判断。"
                )
            after_projection = run.projection
            after_bindings = run.bindings
            after_label = WORKING_STATE_LABEL
            after_id = None
        before_tendencies = before.projection.tendencies
        after_tendencies = after_projection.tendencies
        before_dimensions = {
            item.dimension_id: item for item in before.projection.dimensions
        }
        # The six frozen dimensions are always reported, including zero deltas,
        # so consumers get a stable six-dimension/grade view of the change.
        dimension_changes = [
            PreReviewDimensionChange(
                dimension_id=item.dimension_id,
                from_score=before_dimensions[item.dimension_id].score,
                to_score=item.score,
                score_delta=round(
                    item.score - before_dimensions[item.dimension_id].score, 1
                ),
                from_score_grade=before_dimensions[item.dimension_id].score_grade,
                to_score_grade=item.score_grade,
                from_decision_grade=(
                    before_dimensions[item.dimension_id].decision_grade
                ),
                to_decision_grade=item.decision_grade,
                confidence_delta=round(
                    item.confidence - before_dimensions[item.dimension_id].confidence,
                    1,
                ),
            )
            for item in after_projection.dimensions
        ]
        before_issues = {item.id for item in before.projection.issues}
        after_issues = {item.id for item in after_projection.issues}
        before_rules = set(before.bindings.policy_result_ids)
        after_rules = set(after_bindings.policy_result_ids)
        hard_gate_change = (
            "未变化"
            if before.projection.hard_gate.status == after_projection.hard_gate.status
            else (
                f"{before.projection.hard_gate.status} → "
                f"{after_projection.hard_gate.status}"
            )
        )
        return JudgmentDiff(
            project_id=project_id,
            from_snapshot_id=before.id,
            from_label=before.label,
            to_snapshot_id=after_id,
            to_label=after_label,
            tendency_change=PreReviewTendencyChange(
                support=after_tendencies.support - before_tendencies.support,
                return_value=(
                    after_tendencies.return_value - before_tendencies.return_value
                ),
                review=after_tendencies.review - before_tendencies.review,
                deny=after_tendencies.deny - before_tendencies.deny,
            ),
            disposition_change=(
                f"{before.projection.disposition} → {after_projection.disposition}"
            ),
            dimension_changes=dimension_changes,
            new_evidence_ref_ids=sorted(
                set(after_bindings.evidence_ref_ids)
                - set(before.bindings.evidence_ref_ids)
            ),
            new_fact_version_ids=sorted(
                set(after_bindings.fact_version_ids)
                - set(before.bindings.fact_version_ids)
            ),
            resolved_issue_ids=sorted(before_issues - after_issues),
            unchanged_issue_ids=sorted(before_issues & after_issues),
            new_issue_ids=sorted(after_issues - before_issues),
            rule_changes=sorted(
                [
                    *(f"新增 {item}" for item in after_rules - before_rules),
                    *(f"移除 {item}" for item in before_rules - after_rules),
                ]
            ),
            hard_gate_change=hard_gate_change,
            next_actions=[
                item.description
                for item in after_projection.actions
                if not item.completed
            ][:3],
        )


__all__ = ["PreReviewStore"]
