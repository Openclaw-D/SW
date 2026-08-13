from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.contracts.reconstruction import ReconstructionJob


RECONSTRUCTION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reconstruction_jobs (
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    pipeline TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    request_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, id)
);

CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_subject
ON reconstruction_jobs(project_id, subject_kind, subject_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_request_hash
ON reconstruction_jobs(project_id, request_hash);

CREATE TABLE IF NOT EXISTS reconstruction_job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    job_version INTEGER NOT NULL CHECK (job_version >= 1),
    event_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, job_id, sequence),
    FOREIGN KEY (project_id, job_id)
        REFERENCES reconstruction_jobs(project_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS reconstruction_idempotency (
    project_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    job_id TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_id, operation, idempotency_key),
    FOREIGN KEY (project_id, job_id)
        REFERENCES reconstruction_jobs(project_id, id) ON DELETE RESTRICT
);
"""


class ReconstructionRepositoryError(RuntimeError):
    pass


class ReconstructionNotFoundError(ReconstructionRepositoryError):
    pass


class ReconstructionVersionConflictError(ReconstructionRepositoryError):
    def __init__(self, *, expected_version: int, current_version: int) -> None:
        super().__init__(
            f"reconstruction version conflict: expected {expected_version}, "
            f"current {current_version}"
        )
        self.expected_version = expected_version
        self.current_version = current_version


class ReconstructionIdempotencyConflictError(ReconstructionRepositoryError):
    pass


class ReconstructionJobConflictError(ReconstructionRepositoryError):
    pass


class SqliteReconstructionRepository:
    """Isolated SQLite persistence for reconstruction orchestration.

    The module owns only ``reconstruction_*`` tables and intentionally does not
    alter the shared workbench schema/bootstrap. A future integration may point
    it at a dedicated runtime database or add an explicitly reviewed migration.
    """

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
        with self._lock:
            self._connection.executescript(RECONSTRUCTION_SCHEMA_SQL)

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

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def raw_connection_for_tests(self) -> sqlite3.Connection:
        return self._connection

    def create_job(
        self,
        job: ReconstructionJob,
        *,
        idempotency_key: str,
    ) -> tuple[ReconstructionJob, bool]:
        _validate_operation_value(idempotency_key, "idempotencyKey")
        with self._write_transaction() as connection:
            replay = self._idempotency_replay(
                connection,
                project_id=job.project_id,
                operation="create_job",
                idempotency_key=idempotency_key,
                request_hash=job.request_hash,
            )
            if replay is not None:
                return replay, True
            payload = job.model_dump_json(by_alias=True)
            try:
                connection.execute(
                    """INSERT INTO reconstruction_jobs
                       (id, project_id, subject_kind, subject_id, pipeline, status,
                        version, request_hash, payload_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job.job_id,
                        job.project_id,
                        job.request.subject.subject_kind,
                        job.request.subject.subject_id,
                        job.request.pipeline,
                        job.status,
                        job.version,
                        job.request_hash,
                        payload,
                        job.created_at.isoformat(),
                        job.updated_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ReconstructionJobConflictError(
                    "reconstruction job or canonical request already exists"
                ) from exc
            self._append_event(connection, job, event_kind="job_created")
            self._store_idempotency(
                connection,
                project_id=job.project_id,
                operation="create_job",
                idempotency_key=idempotency_key,
                request_hash=job.request_hash,
                job=job,
            )
            return job, False

    def get_job(self, project_id: str, job_id: str) -> ReconstructionJob:
        _validate_operation_value(project_id, "projectId")
        _validate_operation_value(job_id, "jobId")
        with self._read_transaction() as connection:
            row = connection.execute(
                """SELECT payload_json FROM reconstruction_jobs
                   WHERE project_id = ? AND id = ?""",
                (project_id, job_id),
            ).fetchone()
            if row is None:
                raise ReconstructionNotFoundError("reconstruction job not found")
            return ReconstructionJob.model_validate_json(row["payload_json"])

    def get_idempotency_replay(
        self,
        *,
        project_id: str,
        operation: str,
        idempotency_key: str,
        request_hash: str,
    ) -> ReconstructionJob | None:
        _validate_operation_value(project_id, "projectId")
        _validate_operation_value(operation, "operation")
        _validate_operation_value(idempotency_key, "idempotencyKey")
        _validate_operation_value(request_hash, "requestHash")
        with self._read_transaction() as connection:
            return self._idempotency_replay(
                connection,
                project_id=project_id,
                operation=operation,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )

    def transition_job(
        self,
        job: ReconstructionJob,
        *,
        expected_version: int,
        event_kind: str,
        idempotency_key: str | None = None,
        operation_hash: str | None = None,
    ) -> tuple[ReconstructionJob, bool]:
        _validate_operation_value(event_kind, "eventKind")
        if job.version != expected_version + 1:
            raise ValueError("transition job version must equal expectedVersion + 1")
        if (idempotency_key is None) != (operation_hash is None):
            raise ValueError("idempotencyKey and operationHash must be supplied together")
        if idempotency_key is not None:
            _validate_operation_value(idempotency_key, "idempotencyKey")
            _validate_operation_value(operation_hash or "", "operationHash")

        operation = f"transition:{event_kind}"
        with self._write_transaction() as connection:
            if idempotency_key is not None and operation_hash is not None:
                replay = self._idempotency_replay(
                    connection,
                    project_id=job.project_id,
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=operation_hash,
                )
                if replay is not None:
                    return replay, True

            payload = job.model_dump_json(by_alias=True)
            cursor = connection.execute(
                """UPDATE reconstruction_jobs
                   SET status = ?, version = ?, payload_json = ?, updated_at = ?
                   WHERE project_id = ? AND id = ? AND version = ?""",
                (
                    job.status,
                    job.version,
                    payload,
                    job.updated_at.isoformat(),
                    job.project_id,
                    job.job_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    """SELECT version FROM reconstruction_jobs
                       WHERE project_id = ? AND id = ?""",
                    (job.project_id, job.job_id),
                ).fetchone()
                if row is None:
                    raise ReconstructionNotFoundError("reconstruction job not found")
                raise ReconstructionVersionConflictError(
                    expected_version=expected_version,
                    current_version=int(row["version"]),
                )
            self._append_event(connection, job, event_kind=event_kind)
            if idempotency_key is not None and operation_hash is not None:
                self._store_idempotency(
                    connection,
                    project_id=job.project_id,
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=operation_hash,
                    job=job,
                )
            return job, False

    def list_events(self, project_id: str, job_id: str) -> list[dict[str, object]]:
        self.get_job(project_id, job_id)
        with self._read_transaction() as connection:
            rows = connection.execute(
                """SELECT sequence, job_version, event_kind, status, created_at
                   FROM reconstruction_job_events
                   WHERE project_id = ? AND job_id = ? ORDER BY sequence""",
                (project_id, job_id),
            ).fetchall()
            return [
                {
                    "sequence": int(row["sequence"]),
                    "jobVersion": int(row["job_version"]),
                    "eventKind": row["event_kind"],
                    "status": row["status"],
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]

    def list_interrupted_jobs(self) -> list[ReconstructionJob]:
        """Return jobs whose in-process worker vanished before a terminal state."""

        with self._read_transaction() as connection:
            rows = connection.execute(
                """SELECT payload_json FROM reconstruction_jobs
                   WHERE status IN ('running', 'quality_review')
                   ORDER BY updated_at, id"""
            ).fetchall()
            return [ReconstructionJob.model_validate_json(row["payload_json"]) for row in rows]

    def get_latest_succeeded_job(
        self,
        project_id: str,
        subject_kind: str,
        subject_id: str,
    ) -> ReconstructionJob | None:
        _validate_operation_value(project_id, "projectId")
        _validate_operation_value(subject_kind, "subjectKind")
        _validate_operation_value(subject_id, "subjectId")
        with self._read_transaction() as connection:
            row = connection.execute(
                """SELECT payload_json FROM reconstruction_jobs
                   WHERE project_id = ? AND subject_kind = ? AND subject_id = ?
                     AND status = 'succeeded'
                   ORDER BY updated_at DESC, id DESC LIMIT 1""",
                (project_id, subject_kind, subject_id),
            ).fetchone()
            return (
                ReconstructionJob.model_validate_json(row["payload_json"])
                if row is not None
                else None
            )

    def _idempotency_replay(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        operation: str,
        idempotency_key: str,
        request_hash: str,
    ) -> ReconstructionJob | None:
        row = connection.execute(
            """SELECT request_hash, response_json
               FROM reconstruction_idempotency
               WHERE project_id = ? AND operation = ? AND idempotency_key = ?""",
            (project_id, operation, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ReconstructionIdempotencyConflictError(
                "idempotency key was already used with a different payload"
            )
        return ReconstructionJob.model_validate_json(row["response_json"])

    def _store_idempotency(
        self,
        connection: sqlite3.Connection,
        *,
        project_id: str,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        job: ReconstructionJob,
    ) -> None:
        connection.execute(
            """INSERT INTO reconstruction_idempotency
               (project_id, operation, idempotency_key, request_hash, job_id,
                response_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                operation,
                idempotency_key,
                request_hash,
                job.job_id,
                job.model_dump_json(by_alias=True),
                _utc_now().isoformat(),
            ),
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        job: ReconstructionJob,
        *,
        event_kind: str,
    ) -> None:
        row = connection.execute(
            """SELECT COALESCE(MAX(sequence), 0) AS sequence
               FROM reconstruction_job_events
               WHERE project_id = ? AND job_id = ?""",
            (job.project_id, job.job_id),
        ).fetchone()
        sequence = int(row["sequence"]) + 1
        connection.execute(
            """INSERT INTO reconstruction_job_events
               (project_id, job_id, sequence, job_version, event_kind, status,
                snapshot_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.project_id,
                job.job_id,
                sequence,
                job.version,
                event_kind,
                job.status,
                job.model_dump_json(by_alias=True),
                job.updated_at.isoformat(),
            ),
        )

    @contextmanager
    def _read_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            yield self._connection

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")


def _validate_operation_value(value: str, label: str) -> str:
    if not value or value != value.strip() or len(value) > 500:
        raise ValueError(f"{label} must be non-blank, trimmed, and bounded")
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "RECONSTRUCTION_SCHEMA_SQL",
    "ReconstructionIdempotencyConflictError",
    "ReconstructionJobConflictError",
    "ReconstructionNotFoundError",
    "ReconstructionRepositoryError",
    "ReconstructionVersionConflictError",
    "SqliteReconstructionRepository",
]
