from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.contracts.errors import IdempotencyConflictError, NotFoundError, ServiceError
from app.contracts.material_intelligence import MaterialIntelligenceDataStatus
from app.contracts.model_gateway import (
    ModelGatewayError,
    ModelGatewayMode,
    ModelGatewayOutput,
    ModelGatewayRequest,
    ModelGatewayRunRecord,
    ModelGatewayRunStatus,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_gateway_runs_v1 (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    request_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_version_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'needs_review', 'failed')),
    output_json TEXT,
    error_code TEXT,
    error_message TEXT,
    error_retryable INTEGER,
    error_provider_status INTEGER,
    error_category TEXT,
    error_status_code INTEGER,
    lease_until REAL NOT NULL,
    attempt_count INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(project_id, idempotency_key)
);
"""


@dataclass(frozen=True, slots=True)
class Reservation:
    action: Literal["owner", "replay", "wait", "failure"]
    run_id: str
    output: ModelGatewayOutput | None = None
    error: ServiceError | None = None


class RunRecorder:
    """Persist redacted run state without prompts, bytes, paths or credentials."""

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        raw_path = str(database_path)
        if raw_path.startswith("sqlite:///"):
            raw_path = raw_path.removeprefix("sqlite:///")
        if raw_path != ":memory:":
            path = Path(raw_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            raw_path = str(path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            raw_path, check_same_thread=False, isolation_level=None, timeout=30.0
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout=30000")
        if raw_path != ":memory:":
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
        with self._lock:
            self._connection.executescript(_SCHEMA)

    def reserve(
        self,
        *,
        request: ModelGatewayRequest,
        idempotency_key: str,
        request_fingerprint: str,
        provider_id: str,
        lease_seconds: float,
    ) -> Reservation:
        now = time.time()
        started_at = datetime.now(UTC).isoformat()
        run_id = "mgr-" + uuid.uuid4().hex
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """SELECT * FROM model_gateway_runs_v1
                       WHERE project_id = ? AND idempotency_key = ?""",
                    (request.material.project_id, idempotency_key),
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        """INSERT INTO model_gateway_runs_v1(
                               run_id, project_id, idempotency_key, request_fingerprint,
                               request_id, capability_id, mode, material_id,
                               material_version_id, input_hash, provider_id, status,
                               lease_until, attempt_count, started_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, 1, ?)""",
                        (
                            run_id,
                            request.material.project_id,
                            idempotency_key,
                            request_fingerprint,
                            request.request_id,
                            request.capability_id,
                            request.mode.value,
                            request.material.material_id,
                            request.material.material_version_id,
                            request.input_hash,
                            provider_id,
                            now + lease_seconds,
                            started_at,
                        ),
                    )
                    result = Reservation("owner", run_id)
                else:
                    result = self._existing(
                        row,
                        fingerprint=request_fingerprint,
                        now=now,
                        lease_seconds=lease_seconds,
                    )
                self._connection.commit()
                return result
            except BaseException:
                self._connection.rollback()
                raise

    def _existing(
        self,
        row: sqlite3.Row,
        *,
        fingerprint: str,
        now: float,
        lease_seconds: float,
    ) -> Reservation:
        if row["request_fingerprint"] != fingerprint:
            raise IdempotencyConflictError()
        if row["status"] in {"succeeded", "needs_review"}:
            return Reservation(
                "replay",
                row["run_id"],
                output=ModelGatewayOutput.model_validate_json(row["output_json"]),
            )
        if row["status"] == "failed":
            return Reservation(
                "failure",
                row["run_id"],
                error=self._service_error(row),
            )
        if row["lease_until"] <= now:
            self._connection.execute(
                """UPDATE model_gateway_runs_v1
                   SET lease_until = ?, attempt_count = attempt_count + 1
                   WHERE run_id = ?""",
                (now + lease_seconds, row["run_id"]),
            )
            return Reservation("owner", row["run_id"])
        return Reservation("wait", row["run_id"])

    def record_success(self, run_id: str, output: ModelGatewayOutput) -> None:
        finished_at = datetime.now(UTC).isoformat()
        with self._lock:
            cursor = self._connection.execute(
                """UPDATE model_gateway_runs_v1
                   SET status = ?, output_json = ?, finished_at = ?
                   WHERE run_id = ? AND status = 'running'""",
                (
                    output.status.value,
                    output.model_dump_json(by_alias=True),
                    finished_at,
                    run_id,
                ),
            )
        if cursor.rowcount != 1:
            raise RuntimeError("model gateway run is no longer writable")

    def record_failure(
        self,
        run_id: str,
        error: ServiceError,
        gateway_error: ModelGatewayError,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """UPDATE model_gateway_runs_v1
                   SET status = 'failed', error_code = ?, error_message = ?,
                       error_retryable = ?, error_provider_status = ?,
                       error_category = ?, error_status_code = ?, finished_at = ?
                   WHERE run_id = ? AND status = 'running'""",
                (
                    gateway_error.code.value,
                    gateway_error.message,
                    int(gateway_error.retryable),
                    gateway_error.provider_status,
                    error.category,
                    error.status_code,
                    datetime.now(UTC).isoformat(),
                    run_id,
                ),
            )

    def wait_for_terminal(self, run_id: str) -> Reservation:
        row = self._row(run_id)
        if row["status"] in {"succeeded", "needs_review"}:
            return Reservation(
                "replay",
                run_id,
                output=ModelGatewayOutput.model_validate_json(row["output_json"]),
            )
        if row["status"] == "failed":
            return Reservation("failure", run_id, error=self._service_error(row))
        return Reservation("wait", run_id)

    def get_run(self, project_id: str, run_id: str) -> ModelGatewayRunRecord:
        row = self._row(run_id)
        if row["project_id"] != project_id:
            raise NotFoundError(
                "model_run_not_found",
                "Model Gateway 运行记录不存在于当前项目。",
            )
        error = None
        if row["status"] == "failed":
            error = ModelGatewayError(
                code=row["error_code"],
                message=row["error_message"],
                retryable=bool(row["error_retryable"]),
                provider_status=row["error_provider_status"],
            )
        status = {
            "running": ModelGatewayRunStatus.RUNNING,
            "succeeded": ModelGatewayRunStatus.SUCCEEDED,
            "needs_review": ModelGatewayRunStatus.NEEDS_REVIEW,
            "failed": ModelGatewayRunStatus.FAILED,
        }[row["status"]]
        mode = ModelGatewayMode(row["mode"])
        if mode is ModelGatewayMode.REAL:
            is_simulated = False
            data_status = MaterialIntelligenceDataStatus.PROVIDER_GENERATED_UNVERIFIED
            disclaimer = (
                "脱敏真实 Provider 运行元数据；结果由真实外部模型服务商生成且未经核验。"
                "不包含原件正文、绝对路径或凭据；使用前必须完成人工核验。"
            )
        else:
            is_simulated = True
            data_status = MaterialIntelligenceDataStatus.SIMULATED
            disclaimer = (
                "脱敏 Model Gateway 运行元数据；不包含原件正文、绝对路径或凭据。"
            )
        return ModelGatewayRunRecord(
            run_id=row["run_id"],
            request_id=row["request_id"],
            capability_id=row["capability_id"],
            mode=mode,
            status=status,
            material_id=row["material_id"],
            material_version_id=row["material_version_id"],
            input_hash=row["input_hash"],
            provider_id=row["provider_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=(
                datetime.fromisoformat(row["finished_at"])
                if row["finished_at"]
                else None
            ),
            error=error,
            advisory_only=True,
            is_simulated=is_simulated,
            data_status=data_status,
            source=row["provider_id"],
            disclaimer=disclaimer,
        )

    def _row(self, run_id: str) -> sqlite3.Row:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM model_gateway_runs_v1 WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("model_run_not_found", "Model Gateway 运行记录不存在。")
        return row

    @staticmethod
    def _service_error(row: sqlite3.Row) -> ServiceError:
        return ServiceError(
            code=row["error_code"],
            message=row["error_message"],
            category=row["error_category"],
            status_code=row["error_status_code"],
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()
