from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.contracts.errors import (
    IdempotencyConflictError,
    NotFoundError,
    VersionConflictError,
)
from app.contracts.workbench import BusinessCorrectionCommand
from app.core.config import Settings
from app.services.generator_adapter import NullGeneratorAdapter
from app.services.workbench import create_workbench_service
from app.repositories import SQLiteStateRepository
from app.repositories.schema import SCHEMA_VERSION
from tests.services.fixtures import StaticGenerator, make_bundle


def _settings(database_path: Path) -> Settings:
    return Settings(database_path=database_path)


def _correction(project_id: str = "project-a") -> BusinessCorrectionCommand:
    return BusinessCorrectionCommand(
        projectId=project_id,
        factKey="company.registration",
        fromFactVersionId=f"{project_id}-fact-v1",
        proposedValue="已复核",
        reason="业务人员按原始台账复核",
        evidenceRefs=[f"{project_id}-ev-excel"],
        expectedVersion=1,
    )


def test_schema_v4_migrates_p4_material_kind_check_without_losing_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "p4-material-kind.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE materials (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('excel', 'pdf', 'image', 'media', 'scene')),
            file_name TEXT NOT NULL,
            availability TEXT NOT NULL,
            current_version_id TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO projects VALUES (
            'project-old', 'P4 project', '{}', '2026-08-10T00:00:00Z', '2026-08-10T00:00:00Z'
        );
        INSERT INTO materials VALUES (
            'material-old', 'project-old', 'pdf', '旧合同.pdf', 'available', NULL,
            '{"isSimulated":true}', '2026-08-10T00:00:00Z'
        );
        """
    )
    connection.close()

    repository = SQLiteStateRepository(database)
    current = repository.raw_connection_for_tests()
    assert tuple(
        current.execute(
            "SELECT kind, file_name FROM materials WHERE id = 'material-old'"
        ).fetchone()
    ) == ("pdf", "旧合同.pdf")
    current.execute(
        """INSERT INTO materials
           (id, project_id, kind, file_name, availability, current_version_id,
            metadata_json, created_at)
           VALUES ('material-docx', 'project-old', 'document', '说明.docx',
                   'available', NULL, '{}', '2026-08-13T00:00:00Z')"""
    )
    assert current.execute("PRAGMA foreign_key_check").fetchall() == []
    assert current.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (SCHEMA_VERSION,),
    ).fetchone() is not None
    repository.close()

    restarted = SQLiteStateRepository(database)
    try:
        assert restarted.raw_connection_for_tests().execute(
            "SELECT COUNT(*) FROM materials WHERE project_id = 'project-old'"
        ).fetchone()[0] == 2
    finally:
        restarted.close()


def test_schema_contains_state_tables_and_immutable_triggers(tmp_path: Path) -> None:
    service = create_workbench_service(
        _settings(tmp_path / "state.db"),
        generator=StaticGenerator(make_bundle()),
    )
    try:
        connection = service.repository.raw_connection_for_tests()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "projects",
            "project_snapshots",
            "materials",
            "material_versions",
            "evidence_references",
            "fact_versions",
            "business_corrections",
            "review_events",
            "rule_versions",
            "policy_results",
            "approval_states",
            "approval_transitions",
            "idempotency_records",
            "audit_records",
        } <= tables

        with pytest.raises(sqlite3.IntegrityError, match="immutable table: material_versions"):
            connection.execute(
                "UPDATE material_versions SET mime_type = 'x' WHERE id = ?",
                ("project-a-excel-v1",),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable table: fact_versions"):
            connection.execute(
                "UPDATE fact_versions SET value_json = 'null' WHERE id = ?",
                ("project-a-fact-v1",),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable table: project_snapshots"):
            connection.execute("DELETE FROM project_snapshots")
    finally:
        service.close()


def test_restart_persists_state_and_seed_is_not_duplicated(tmp_path: Path) -> None:
    database = tmp_path / "persistent.db"
    generator = StaticGenerator(
        make_bundle(recalculable=True), identity="persistent-seed-v1"
    )
    first = create_workbench_service(_settings(database), generator=generator)
    try:
        created = first.submit_business_correction(
            "project-a",
            "company.registration",
            _correction(),
            idempotency_key="correction-persist-001",
        )
        assert created.fact_version.version == 2
    finally:
        first.close()

    second = create_workbench_service(_settings(database), generator=generator)
    try:
        assert [item.project_id for item in second.list_projects()] == ["project-a"]
        workbench = second.get_workbench("project-a")
        assert [
            fact.version
            for fact in workbench.facts
            if fact.fact_key == "company.registration"
        ] == [1, 2]
        assert len(workbench.corrections) == 1
        assert len(workbench.review_events) == 2
        assert len(second.list_policy_results("project-a")) == 3

        repeated = second.submit_business_correction(
            "project-a",
            "company.registration",
            _correction(),
            idempotency_key="correction-persist-001",
        )
        assert repeated.model_dump(mode="json") == created.model_dump(mode="json")
        connection = second.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0] == 1
    finally:
        second.close()


def test_profiled_generator_identity_reuses_legacy_seed_without_losing_state(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-profile-seed.db"
    bundle = make_bundle(recalculable=True)
    legacy = StaticGenerator(bundle, identity="fixture-v1:20260810:1")
    first = create_workbench_service(_settings(database), generator=legacy)
    try:
        first.submit_business_correction(
            "project-a",
            "company.registration",
            _correction(),
            idempotency_key="legacy-profile-correction-001",
        )
    finally:
        first.close()

    profiled = StaticGenerator(
        bundle, identity="fixture-v1:standard:20260810:1"
    )
    restarted = create_workbench_service(_settings(database), generator=profiled)
    try:
        assert [item.project_id for item in restarted.list_projects()] == ["project-a"]
        workbench = restarted.get_workbench("project-a")
        assert len(workbench.corrections) == 1
        connection = restarted.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0] == 1
    finally:
        restarted.close()


def test_empty_start_does_not_mark_seed_and_later_generator_is_consumed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "late-generator.db"
    empty = create_workbench_service(
        _settings(database), generator=NullGeneratorAdapter()
    )
    try:
        assert empty.list_projects() == []
        with pytest.raises(NotFoundError):
            empty.get_workbench("project-a")
        connection = empty.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0] == 0
    finally:
        empty.close()

    seeded = create_workbench_service(
        _settings(database),
        generator=StaticGenerator(make_bundle(), identity="late-generator-v1"),
    )
    try:
        assert [item.project_id for item in seeded.list_projects()] == ["project-a"]
        connection = seeded.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0] == 1
    finally:
        seeded.close()


def test_rule_versions_are_reproducible_shared_and_immutable(tmp_path: Path) -> None:
    service = create_workbench_service(
        _settings(tmp_path / "rule-version.db"),
        generator=StaticGenerator(
            make_bundle("project-a", policy_result="block"),
            make_bundle("project-b", policy_result="pass"),
            identity="rule-version-v1",
        ),
    )
    try:
        connection = service.repository.raw_connection_for_tests()
        row = connection.execute(
            "SELECT definition_json, definition_hash FROM rule_versions"
        ).fetchone()
        definition = json.loads(row["definition_json"])
        canonical = json.dumps(
            definition,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        assert row["definition_hash"] == hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
        assert definition["kind"] == "hard_constraint"
        assert definition["evidenceRequirement"] == "需核验权属"
        assert connection.execute("SELECT COUNT(*) FROM rule_versions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM policy_results").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="immutable table: rule_versions"):
            connection.execute("UPDATE rule_versions SET version = 'changed'")
    finally:
        service.close()


def test_changed_definition_under_same_rule_version_rolls_back_seed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "rule-version-conflict.db"
    first = make_bundle("project-a", policy_result="pass")
    second = make_bundle("project-b", policy_result="pass")
    second.workbench["riskSummary"]["hardConstraintResults"][0][
        "evidenceRequirement"
    ] = "同版本却改变证据要求"
    with pytest.raises(ValueError, match="changed definition"):
        create_workbench_service(
            _settings(database),
            generator=StaticGenerator(first, second, identity="rule-conflict-v1"),
        )

    repository = SQLiteStateRepository(database)
    try:
        connection = repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0] == 0
    finally:
        repository.close()


def test_failed_idempotent_result_survives_restart_without_recalculation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "failed-idempotency.db"
    generator = StaticGenerator(
        make_bundle(recalculable=True), identity="failed-idempotency-v1"
    )
    first_service = create_workbench_service(_settings(database), generator=generator)
    stale = _correction()
    try:
        first = first_service.submit_business_correction(
            "project-a",
            "company.registration",
            stale,
            idempotency_key="correction-first-001",
        )
        with pytest.raises(VersionConflictError) as original_error:
            first_service.submit_business_correction(
                "project-a",
                "company.registration",
                stale,
                idempotency_key="correction-failed-001",
            )
        assert original_error.value.details["actualVersion"] == 2
        first_service.submit_business_correction(
            "project-a",
            "company.registration",
            BusinessCorrectionCommand(
                projectId="project-a",
                factKey="company.registration",
                fromFactVersionId=first.fact_version.id,
                proposedValue="再次复核",
                reason="推进到第三版",
                evidenceRefs=["project-a-ev-excel"],
                expectedVersion=2,
            ),
            idempotency_key="correction-third-001",
        )
    finally:
        first_service.close()

    second_service = create_workbench_service(_settings(database), generator=generator)
    try:
        with pytest.raises(VersionConflictError) as replayed_error:
            second_service.submit_business_correction(
                "project-a",
                "company.registration",
                stale,
                idempotency_key="correction-failed-001",
            )
        # The current fact is now v3, but the original v2 conflict is replayed.
        assert replayed_error.value.details["actualVersion"] == 2
        with pytest.raises(IdempotencyConflictError):
            second_service.submit_business_correction(
                "project-a",
                "company.registration",
                stale.model_copy(update={"reason": "同 key 不同载荷"}),
                idempotency_key="correction-failed-001",
            )
    finally:
        second_service.close()


def test_concurrent_startup_consumes_one_seed_run(tmp_path: Path) -> None:
    database = tmp_path / "concurrent-startup.db"
    barrier = Barrier(3)

    def start() -> tuple[int, int]:
        barrier.wait()
        service = create_workbench_service(
            _settings(database),
            generator=StaticGenerator(
                make_bundle(), identity="concurrent-startup-v1"
            ),
        )
        try:
            connection = service.repository.raw_connection_for_tests()
            return (
                len(service.list_projects()),
                connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0],
            )
        finally:
            service.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(start) for _ in range(2)]
        barrier.wait()
        results = [future.result(timeout=10) for future in futures]
    assert results == [(1, 1), (1, 1)]

    repository = SQLiteStateRepository(database)
    try:
        connection = repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0] == 1
    finally:
        repository.close()
