from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.models import (
    ApprovalState,
    ApprovalTransition,
    AuditRecord,
    BusinessCorrection,
    EvidenceReference,
    FactVersion,
    IdempotencyRecord,
    Material,
    MaterialVersion,
    PolicyResult,
    Project,
    ProjectSnapshot,
    ReviewEvent,
    ReviewEvidenceTarget,
    RuleVersion,
    locator_from_mapping,
    utc_now,
)

from .errors import RepositoryConflict, RepositoryNotFound, RepositoryProjectMismatch
from .schema import (
    IMMUTABLE_TABLES,
    SCHEMA_SQL,
    SCHEMA_VERSION,
    immutable_trigger_sql,
    migrate_agent_schema,
)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _targets_from_json(value: str) -> tuple[ReviewEvidenceTarget, ...]:
    return tuple(
        ReviewEvidenceTarget(
            evidence_ref=item["evidenceRef"],
            evidence_refs=tuple(item.get("evidenceRefs") or [item["evidenceRef"]]),
            dimension_id=item["dimensionId"],
            review_target_id=item.get("reviewTargetId"),
            fact_version_id=item.get("factVersionId"),
            unavailable_reason=item.get("unavailableReason"),
        )
        for item in _load(value, [])
    )


class SQLiteStateRepository:
    """Small, explicit SQLite state store for the local workbench.

    One connection is intentionally serialized by an RLock.  P4 is a local
    state layer and this keeps in-memory tests and multi-step transactions
    deterministic while SQLite still persists normally when a file path is used.
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
        self.initialize_schema()

    def _configure_connection(self) -> None:
        self._connection.execute("PRAGMA foreign_keys=ON")
        # A first 24-project seed is intentionally large enough to exceed five
        # seconds on the local Windows runtime.  Let a concurrent process wait
        # for that single writer instead of surfacing a spurious locked error.
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

    def initialize_schema(self) -> None:
        with self._lock:
            migrate_agent_schema(self._connection)
            self._connection.executescript(SCHEMA_SQL)
            # SQLite CREATE TABLE IF NOT EXISTS cannot evolve P5 databases.
            columns = {
                row["name"] for row in self._connection.execute(
                    "PRAGMA table_info(material_source_records)"
                )
            }
            if "source_file_ref" not in columns:
                self._connection.execute(
                    "ALTER TABLE material_source_records ADD COLUMN source_file_ref TEXT"
                )
            if "byte_size" not in columns:
                self._connection.execute(
                    "ALTER TABLE material_source_records ADD COLUMN byte_size INTEGER"
                )
            self._migrate_material_document_kind()
            for table in IMMUTABLE_TABLES:
                self._connection.executescript(immutable_trigger_sql(table))
            self._connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )

    def _migrate_material_document_kind(self) -> None:
        """Broaden the P4 material kind check without dropping stored state.

        SQLite cannot ALTER a CHECK constraint. Rebuilding this one parent
        table with foreign keys temporarily disabled keeps every id and current
        version pointer stable; all child declarations continue to reference
        the final `materials` table name.
        """

        table = self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'materials'"
        ).fetchone()
        if table is None or "'document'" in str(table["sql"]):
            return
        self._connection.execute("PRAGMA foreign_keys=OFF")
        try:
            self._connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE materials_p5_v4 (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK (
                        kind IN ('excel', 'pdf', 'document', 'image', 'media', 'scene')
                    ),
                    file_name TEXT NOT NULL,
                    availability TEXT NOT NULL,
                    current_version_id TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO materials_p5_v4
                    (id, project_id, kind, file_name, availability,
                     current_version_id, metadata_json, created_at)
                SELECT id, project_id, kind, file_name, availability,
                       current_version_id, metadata_json, created_at
                FROM materials;
                DROP TABLE materials;
                ALTER TABLE materials_p5_v4 RENAME TO materials;
                CREATE INDEX ix_materials_project ON materials(project_id);
                COMMIT;
                """
            )
        except BaseException:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise
        finally:
            self._connection.execute("PRAGMA foreign_keys=ON")
        violations = self._connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError("material document migration failed foreign key check")

    @contextmanager
    def transaction(self, *, write: bool = True) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def raw_connection_for_tests(self) -> sqlite3.Connection:
        """Expose the connection only for persistence/immutability assertions."""

        return self._connection

    @staticmethod
    def _scoped_row(
        connection: sqlite3.Connection,
        *,
        table: str,
        entity: str,
        entity_id: str,
        project_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            f"SELECT * FROM {table} WHERE id = ? AND project_id = ?",
            (entity_id, project_id),
        ).fetchone()
        if row is not None:
            return row
        owner = connection.execute(
            f"SELECT project_id FROM {table} WHERE id = ?", (entity_id,)
        ).fetchone()
        if owner is not None:
            raise RepositoryProjectMismatch(entity, entity_id, project_id)
        raise RepositoryNotFound(entity, entity_id)

    def create_project(self, project: Project, connection: sqlite3.Connection) -> None:
        try:
            connection.execute(
                """INSERT INTO projects(id, name, payload_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    project.id,
                    project.name,
                    _dump(project.payload),
                    project.created_at,
                    project.updated_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(f"project already exists: {project.id}") from exc

    def get_project(
        self, project_id: str, connection: sqlite3.Connection
    ) -> Project:
        row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise RepositoryNotFound("project", project_id)
        return Project(
            id=row["id"],
            name=row["name"],
            payload=_load(row["payload_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_projects(self, connection: sqlite3.Connection) -> tuple[Project, ...]:
        rows = connection.execute("SELECT * FROM projects ORDER BY created_at, id").fetchall()
        return tuple(
            Project(
                id=row["id"],
                name=row["name"],
                payload=_load(row["payload_json"], {}),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        )

    def create_project_snapshot(
        self, snapshot: ProjectSnapshot, connection: sqlite3.Connection
    ) -> None:
        connection.execute(
            """INSERT INTO project_snapshots
               (id, project_id, version, payload_json, created_at, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snapshot.id,
                snapshot.project_id,
                snapshot.version,
                _dump(snapshot.payload),
                snapshot.created_at,
                snapshot.created_by,
            ),
        )

    def next_snapshot_version(self, project_id: str, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS value FROM project_snapshots WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row["value"])

    def latest_project_snapshot(
        self, project_id: str, connection: sqlite3.Connection
    ) -> ProjectSnapshot | None:
        row = connection.execute(
            "SELECT * FROM project_snapshots WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return ProjectSnapshot(
            id=row["id"],
            project_id=row["project_id"],
            version=row["version"],
            payload=_load(row["payload_json"], {}),
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def create_material(self, material: Material, connection: sqlite3.Connection) -> None:
        connection.execute(
            """INSERT INTO materials
               (id, project_id, kind, file_name, availability, current_version_id,
                metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                material.id,
                material.project_id,
                material.kind,
                material.file_name,
                material.availability,
                material.current_version_id,
                _dump(material.metadata),
                material.created_at,
            ),
        )

    def set_current_material_version(
        self,
        project_id: str,
        material_id: str,
        version_id: str,
        connection: sqlite3.Connection,
    ) -> None:
        self._scoped_row(
            connection,
            table="materials",
            entity="material",
            entity_id=material_id,
            project_id=project_id,
        )
        version = self._scoped_row(
            connection,
            table="material_versions",
            entity="material_version",
            entity_id=version_id,
            project_id=project_id,
        )
        if version["material_id"] != material_id:
            raise RepositoryProjectMismatch("material_version", version_id, project_id)
        connection.execute(
            "UPDATE materials SET current_version_id = ? WHERE id = ? AND project_id = ?",
            (version_id, material_id, project_id),
        )

    def create_material_version(
        self, version: MaterialVersion, connection: sqlite3.Connection
    ) -> None:
        try:
            connection.execute(
                """INSERT INTO material_versions
                   (id, project_id, material_id, version, mime_type, content_hash,
                    payload_json, created_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version.id,
                    version.project_id,
                    version.material_id,
                    version.version,
                    version.mime_type,
                    version.content_hash,
                    _dump(version.payload),
                    version.created_at,
                    version.created_by,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(
                f"material version already exists: {version.material_id}/{version.version}"
            ) from exc

    @staticmethod
    def _material_from_row(row: sqlite3.Row) -> Material:
        return Material(
            id=row["id"],
            project_id=row["project_id"],
            kind=row["kind"],
            file_name=row["file_name"],
            availability=row["availability"],
            current_version_id=row["current_version_id"],
            metadata=_load(row["metadata_json"], {}),
            created_at=row["created_at"],
        )

    def get_material(
        self, project_id: str, material_id: str, connection: sqlite3.Connection
    ) -> Material:
        return self._material_from_row(
            self._scoped_row(
                connection,
                table="materials",
                entity="material",
                entity_id=material_id,
                project_id=project_id,
            )
        )

    def list_materials(
        self, project_id: str, connection: sqlite3.Connection
    ) -> tuple[Material, ...]:
        self.get_project(project_id, connection)
        rows = connection.execute(
            "SELECT * FROM materials WHERE project_id = ? ORDER BY created_at, id",
            (project_id,),
        ).fetchall()
        return tuple(self._material_from_row(row) for row in rows)

    @staticmethod
    def _material_version_from_row(row: sqlite3.Row) -> MaterialVersion:
        return MaterialVersion(
            id=row["id"],
            project_id=row["project_id"],
            material_id=row["material_id"],
            version=row["version"],
            mime_type=row["mime_type"],
            content_hash=row["content_hash"],
            payload=_load(row["payload_json"], {}),
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def get_material_version(
        self, project_id: str, version_id: str, connection: sqlite3.Connection
    ) -> MaterialVersion:
        return self._material_version_from_row(
            self._scoped_row(
                connection,
                table="material_versions",
                entity="material_version",
                entity_id=version_id,
                project_id=project_id,
            )
        )

    def create_evidence_reference(
        self, evidence: EvidenceReference, connection: sqlite3.Connection
    ) -> None:
        locator = evidence.locator
        connection.execute(
            """INSERT INTO evidence_references
               (id, project_id, label, material_id, material_version_id, locator_kind,
                locator_json, location_status, material_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.id,
                evidence.project_id,
                evidence.label,
                locator.material_id if locator else None,
                locator.material_version_id if locator else None,
                locator.kind if locator else None,
                _dump(locator.to_dict()) if locator else None,
                evidence.location_status,
                evidence.material_status,
                evidence.created_at,
            ),
        )

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> EvidenceReference:
        locator = locator_from_mapping(_load(row["locator_json"])) if row["locator_json"] else None
        return EvidenceReference(
            id=row["id"],
            project_id=row["project_id"],
            label=row["label"],
            locator=locator,
            location_status=row["location_status"],
            material_status=row["material_status"],
            created_at=row["created_at"],
        )

    def get_evidence_reference(
        self, project_id: str, evidence_id: str, connection: sqlite3.Connection
    ) -> EvidenceReference:
        return self._evidence_from_row(
            self._scoped_row(
                connection,
                table="evidence_references",
                entity="evidence",
                entity_id=evidence_id,
                project_id=project_id,
            )
        )

    def list_evidence_references(
        self, project_id: str, connection: sqlite3.Connection
    ) -> tuple[EvidenceReference, ...]:
        self.get_project(project_id, connection)
        rows = connection.execute(
            "SELECT * FROM evidence_references WHERE project_id = ? ORDER BY created_at, id",
            (project_id,),
        ).fetchall()
        return tuple(self._evidence_from_row(row) for row in rows)

    def create_fact_version(
        self, fact: FactVersion, connection: sqlite3.Connection
    ) -> None:
        try:
            connection.execute(
                """INSERT INTO fact_versions
                   (id, project_id, fact_key, dimension_id, version, label, value_json,
                    unit, source, evidence_refs_json, supersedes_version_id, created_at,
                    created_by, is_simulated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fact.id,
                    fact.project_id,
                    fact.fact_key,
                    fact.dimension_id,
                    fact.version,
                    fact.label,
                    _dump(fact.value),
                    fact.unit,
                    fact.source,
                    _dump(list(fact.evidence_refs)),
                    fact.supersedes_version_id,
                    fact.created_at,
                    fact.created_by,
                    int(fact.is_simulated),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(
                f"fact version conflict: {fact.fact_key}/{fact.version}"
            ) from exc

    @staticmethod
    def _fact_from_row(row: sqlite3.Row) -> FactVersion:
        return FactVersion(
            id=row["id"],
            project_id=row["project_id"],
            fact_key=row["fact_key"],
            dimension_id=row["dimension_id"],
            version=row["version"],
            label=row["label"],
            value=_load(row["value_json"]),
            unit=row["unit"],
            source=row["source"],
            evidence_refs=tuple(_load(row["evidence_refs_json"], [])),
            supersedes_version_id=row["supersedes_version_id"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            is_simulated=bool(row["is_simulated"]),
        )

    def get_fact_version(
        self, project_id: str, fact_version_id: str, connection: sqlite3.Connection
    ) -> FactVersion:
        return self._fact_from_row(
            self._scoped_row(
                connection,
                table="fact_versions",
                entity="fact_version",
                entity_id=fact_version_id,
                project_id=project_id,
            )
        )

    def latest_fact_version(
        self, project_id: str, fact_key: str, connection: sqlite3.Connection
    ) -> FactVersion | None:
        row = connection.execute(
            """SELECT * FROM fact_versions
               WHERE project_id = ? AND fact_key = ? ORDER BY version DESC LIMIT 1""",
            (project_id, fact_key),
        ).fetchone()
        return self._fact_from_row(row) if row else None

    def list_fact_versions(
        self, project_id: str, connection: sqlite3.Connection
    ) -> tuple[FactVersion, ...]:
        self.get_project(project_id, connection)
        rows = connection.execute(
            """SELECT * FROM fact_versions
               WHERE project_id = ? ORDER BY fact_key, version""",
            (project_id,),
        ).fetchall()
        return tuple(self._fact_from_row(row) for row in rows)

    def create_business_correction(
        self, correction: BusinessCorrection, connection: sqlite3.Connection
    ) -> None:
        connection.execute(
            """INSERT INTO business_corrections
               (id, project_id, fact_key, from_fact_version_id, to_fact_version_id,
                expected_version, proposed_value_json, reason, evidence_refs_json,
                status, created_by, created_at, is_simulated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                correction.id,
                correction.project_id,
                correction.fact_key,
                correction.from_fact_version_id,
                correction.to_fact_version_id,
                correction.expected_version,
                _dump(correction.proposed_value),
                correction.reason,
                _dump(list(correction.evidence_refs)),
                correction.status,
                correction.created_by,
                correction.created_at,
                int(correction.is_simulated),
            ),
        )

    @staticmethod
    def _correction_from_row(row: sqlite3.Row) -> BusinessCorrection:
        return BusinessCorrection(
            id=row["id"],
            project_id=row["project_id"],
            fact_key=row["fact_key"],
            from_fact_version_id=row["from_fact_version_id"],
            to_fact_version_id=row["to_fact_version_id"],
            expected_version=row["expected_version"],
            proposed_value=_load(row["proposed_value_json"]),
            reason=row["reason"],
            evidence_refs=tuple(_load(row["evidence_refs_json"], [])),
            status=row["status"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            is_simulated=bool(row["is_simulated"]),
        )

    def get_business_correction(
        self, project_id: str, correction_id: str, connection: sqlite3.Connection
    ) -> BusinessCorrection:
        row = self._scoped_row(
            connection,
            table="business_corrections",
            entity="business_correction",
            entity_id=correction_id,
            project_id=project_id,
        )
        return self._correction_from_row(row)

    def list_business_corrections(
        self, project_id: str, connection: sqlite3.Connection
    ) -> tuple[BusinessCorrection, ...]:
        self.get_project(project_id, connection)
        rows = connection.execute(
            """SELECT * FROM business_corrections
               WHERE project_id = ? ORDER BY created_at, id""",
            (project_id,),
        ).fetchall()
        return tuple(self._correction_from_row(row) for row in rows)

    def next_review_sequence(self, project_id: str, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM review_events WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row["value"])

    def create_review_event(self, event: ReviewEvent, connection: sqlite3.Connection) -> None:
        connection.execute(
            """INSERT INTO review_events
               (id, project_id, sequence, thread_id, reply_to_event_id, issue_status,
                event_type, actor, actor_label, dimension_id, evidence_targets_json,
                review_target_id, title, summary, fact_version_ids_json,
                evidence_refs_json, rule_refs_json, created_at, is_simulated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                event.project_id,
                event.sequence,
                event.thread_id,
                event.reply_to_event_id,
                event.issue_status,
                event.event_type,
                event.actor,
                event.actor_label,
                event.dimension_id,
                _dump([target.to_dict() for target in event.evidence_targets]),
                event.review_target_id,
                event.title,
                event.summary,
                _dump(list(event.fact_version_ids)),
                _dump(list(event.evidence_refs)),
                _dump(list(event.rule_refs)),
                event.created_at,
                int(event.is_simulated),
            ),
        )

    @staticmethod
    def _review_event_from_row(row: sqlite3.Row) -> ReviewEvent:
        return ReviewEvent(
            id=row["id"],
            project_id=row["project_id"],
            sequence=row["sequence"],
            thread_id=row["thread_id"],
            reply_to_event_id=row["reply_to_event_id"],
            issue_status=row["issue_status"],
            event_type=row["event_type"],
            actor=row["actor"],
            actor_label=row["actor_label"],
            dimension_id=row["dimension_id"],
            evidence_targets=_targets_from_json(row["evidence_targets_json"]),
            review_target_id=row["review_target_id"],
            title=row["title"],
            summary=row["summary"],
            fact_version_ids=tuple(_load(row["fact_version_ids_json"], [])),
            evidence_refs=tuple(_load(row["evidence_refs_json"], [])),
            rule_refs=tuple(_load(row["rule_refs_json"], [])),
            created_at=row["created_at"],
            immutable=True,
            is_simulated=bool(row["is_simulated"]),
        )

    def get_review_event(
        self, project_id: str, event_id: str, connection: sqlite3.Connection
    ) -> ReviewEvent:
        return self._review_event_from_row(
            self._scoped_row(
                connection,
                table="review_events",
                entity="review_event",
                entity_id=event_id,
                project_id=project_id,
            )
        )

    def list_review_events(
        self, project_id: str, connection: sqlite3.Connection
    ) -> tuple[ReviewEvent, ...]:
        self.get_project(project_id, connection)
        rows = connection.execute(
            "SELECT * FROM review_events WHERE project_id = ? ORDER BY sequence",
            (project_id,),
        ).fetchall()
        return tuple(self._review_event_from_row(row) for row in rows)

    def create_rule_version(self, rule: RuleVersion, connection: sqlite3.Connection) -> None:
        try:
            connection.execute(
                """INSERT INTO rule_versions
                   (id, rule_id, version, title, is_hard_gate, definition_json,
                    definition_hash, created_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule.id,
                    rule.rule_id,
                    rule.version,
                    rule.title,
                    int(rule.is_hard_gate),
                    _dump(rule.definition),
                    rule.definition_hash,
                    rule.created_at,
                    rule.created_by,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflict(
                f"rule version already exists: {rule.rule_id}/{rule.version}"
            ) from exc

    @staticmethod
    def _rule_from_row(row: sqlite3.Row) -> RuleVersion:
        return RuleVersion(
            id=row["id"],
            rule_id=row["rule_id"],
            version=row["version"],
            title=row["title"],
            is_hard_gate=bool(row["is_hard_gate"]),
            definition=_load(row["definition_json"], {}),
            definition_hash=row["definition_hash"],
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def get_rule_version(self, rule_version_id: str, connection: sqlite3.Connection) -> RuleVersion:
        row = connection.execute(
            "SELECT * FROM rule_versions WHERE id = ?", (rule_version_id,)
        ).fetchone()
        if row is None:
            raise RepositoryNotFound("rule_version", rule_version_id)
        return self._rule_from_row(row)

    def find_rule_version(
        self, rule_id: str, version: str, connection: sqlite3.Connection
    ) -> RuleVersion | None:
        row = connection.execute(
            "SELECT * FROM rule_versions WHERE rule_id = ? AND version = ?",
            (rule_id, version),
        ).fetchone()
        return self._rule_from_row(row) if row else None

    def create_policy_result(
        self, result: PolicyResult, connection: sqlite3.Connection
    ) -> None:
        connection.execute(
            """INSERT INTO policy_results
               (id, project_id, rule_version_id, rule_id, rule_version, title,
                result, evidence_targets_json, primary_target_json, scope,
                evidence_requirement, gate_triggered, responsible_party,
                next_action, explanation, evaluation_input_json, evaluated_at,
                is_simulated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.id,
                result.project_id,
                result.rule_version_id,
                result.rule_id,
                result.rule_version,
                result.title,
                result.result,
                _dump([target.to_dict() for target in result.evidence_targets]),
                _dump(result.primary_target.to_dict()) if result.primary_target else None,
                result.scope,
                result.evidence_requirement,
                int(result.gate_triggered),
                result.responsible_party,
                result.next_action,
                result.explanation,
                _dump(result.evaluation_input),
                result.evaluated_at,
                int(result.is_simulated),
            ),
        )

    @staticmethod
    def _policy_from_row(row: sqlite3.Row) -> PolicyResult:
        primary = _load(row["primary_target_json"])
        primary_target = _targets_from_json(_dump([primary]))[0] if primary else None
        return PolicyResult(
            id=row["id"],
            project_id=row["project_id"],
            rule_version_id=row["rule_version_id"],
            rule_id=row["rule_id"],
            rule_version=row["rule_version"],
            title=row["title"],
            result=row["result"],
            evidence_targets=_targets_from_json(row["evidence_targets_json"]),
            primary_target=primary_target,
            scope=row["scope"],
            evidence_requirement=row["evidence_requirement"],
            gate_triggered=bool(row["gate_triggered"]),
            responsible_party=row["responsible_party"],
            next_action=row["next_action"],
            explanation=row["explanation"],
            evaluation_input=_load(row["evaluation_input_json"], {}),
            evaluated_at=row["evaluated_at"],
            is_simulated=bool(row["is_simulated"]),
        )

    def list_policy_results(
        self, project_id: str, connection: sqlite3.Connection
    ) -> tuple[PolicyResult, ...]:
        self.get_project(project_id, connection)
        rows = connection.execute(
            "SELECT * FROM policy_results WHERE project_id = ? ORDER BY evaluated_at, rowid",
            (project_id,),
        ).fetchall()
        return tuple(self._policy_from_row(row) for row in rows)

    def get_policy_result(
        self, project_id: str, result_id: str, connection: sqlite3.Connection
    ) -> PolicyResult:
        return self._policy_from_row(
            self._scoped_row(
                connection,
                table="policy_results",
                entity="policy_result",
                entity_id=result_id,
                project_id=project_id,
            )
        )

    def get_approval_state(
        self, project_id: str, connection: sqlite3.Connection
    ) -> ApprovalState | None:
        row = connection.execute(
            "SELECT * FROM approval_states WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        return ApprovalState(
            project_id=row["project_id"],
            state=row["state"],
            version=row["version"],
            decision_grade=row["decision_grade"],
            updated_at=row["updated_at"],
            updated_by=row["updated_by"],
        )

    def put_approval_state(
        self, state: ApprovalState, connection: sqlite3.Connection
    ) -> None:
        connection.execute(
            """INSERT INTO approval_states
               (project_id, state, version, decision_grade, updated_at, updated_by)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id) DO UPDATE SET
                   state=excluded.state,
                   version=excluded.version,
                   decision_grade=excluded.decision_grade,
                   updated_at=excluded.updated_at,
                   updated_by=excluded.updated_by""",
            (
                state.project_id,
                state.state,
                state.version,
                state.decision_grade,
                state.updated_at,
                state.updated_by,
            ),
        )

    def next_approval_sequence(self, project_id: str, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            """SELECT COALESCE(MAX(sequence), 0) + 1 AS value
               FROM approval_transitions WHERE project_id = ?""",
            (project_id,),
        ).fetchone()
        return int(row["value"])

    def create_approval_transition(
        self, transition: ApprovalTransition, connection: sqlite3.Connection
    ) -> None:
        connection.execute(
            """INSERT INTO approval_transitions
               (id, project_id, sequence, from_state, to_state, actor_role, reason,
                policy_result_ids_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                transition.id,
                transition.project_id,
                transition.sequence,
                transition.from_state,
                transition.to_state,
                transition.actor_role,
                transition.reason,
                _dump(list(transition.policy_result_ids)),
                transition.created_at,
            ),
        )

    def get_idempotency_record(
        self, key: str, connection: sqlite3.Connection
    ) -> IdempotencyRecord | None:
        row = connection.execute(
            "SELECT * FROM idempotency_records WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return IdempotencyRecord(
            key=row["key"],
            operation=row["operation"],
            request_hash=row["request_hash"],
            response=_load(row["response_json"], {}),
            status_code=row["status_code"],
            created_at=row["created_at"],
        )

    def create_idempotency_record(
        self, record: IdempotencyRecord, connection: sqlite3.Connection
    ) -> None:
        connection.execute(
            """INSERT INTO idempotency_records
               (key, operation, request_hash, response_json, status_code, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                record.key,
                record.operation,
                record.request_hash,
                _dump(record.response),
                record.status_code,
                record.created_at,
            ),
        )

    def next_audit_sequence(self, project_id: str, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM audit_records WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row["value"])

    def latest_audit_hash(self, project_id: str, connection: sqlite3.Connection) -> str | None:
        row = connection.execute(
            "SELECT event_hash FROM audit_records WHERE project_id = ? ORDER BY sequence DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return row["event_hash"] if row else None

    def create_audit_record(self, record: AuditRecord, connection: sqlite3.Connection) -> None:
        connection.execute(
            """INSERT INTO audit_records
               (id, project_id, sequence, action, aggregate_type, aggregate_id,
                actor, payload_json, previous_hash, event_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.id,
                record.project_id,
                record.sequence,
                record.action,
                record.aggregate_type,
                record.aggregate_id,
                record.actor,
                _dump(record.payload),
                record.previous_hash,
                record.event_hash,
                record.created_at,
            ),
        )

    def list_audit_records(
        self, project_id: str, connection: sqlite3.Connection
    ) -> tuple[AuditRecord, ...]:
        self.get_project(project_id, connection)
        rows = connection.execute(
            "SELECT * FROM audit_records WHERE project_id = ? ORDER BY sequence",
            (project_id,),
        ).fetchall()
        return tuple(
            AuditRecord(
                id=row["id"],
                project_id=row["project_id"],
                sequence=row["sequence"],
                action=row["action"],
                aggregate_type=row["aggregate_type"],
                aggregate_id=row["aggregate_id"],
                actor=row["actor"],
                payload=_load(row["payload_json"], {}),
                previous_hash=row["previous_hash"],
                event_hash=row["event_hash"],
                created_at=row["created_at"],
            )
            for row in rows
        )

    def seed_run_exists(self, seed_key: str, connection: sqlite3.Connection) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM seed_runs WHERE seed_key = ?", (seed_key,)
            ).fetchone()
            is not None
        )

    def create_seed_run(
        self,
        *,
        seed_key: str,
        source: str,
        project_count: int,
        connection: sqlite3.Connection,
    ) -> None:
        connection.execute(
            "INSERT INTO seed_runs(seed_key, source, project_count, created_at) VALUES (?, ?, ?, ?)",
            (seed_key, source, project_count, utc_now()),
        )
