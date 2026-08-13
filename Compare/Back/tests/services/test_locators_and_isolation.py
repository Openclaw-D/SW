from __future__ import annotations

from pathlib import Path

import pytest

from app.contracts.errors import NotFoundError
from app.contracts.workbench import ReviewEvidenceSelectionGroup
from app.core.config import Settings
from app.models import EvidenceReference, ExcelLocator, MaterialVersion, utc_now
from app.services.errors import EvidenceSelectionError
from app.services.workbench import create_workbench_service
from tests.services.fixtures import StaticGenerator, make_bundle


def _group(
    evidence_refs: list[str],
    *,
    project_id: str = "project-a",
    review_target_id: str = "target-1",
    fact_version_id: str | None = None,
) -> ReviewEvidenceSelectionGroup:
    return ReviewEvidenceSelectionGroup(
        id="::".join(
            [
                "compliance",
                review_target_id,
                fact_version_id or "fact",
                *evidence_refs,
            ]
        ),
        dimensionId="compliance",
        reviewTargetId=review_target_id,
        factVersionId=fact_version_id,
        targets=[
            {
                "evidenceRef": evidence_ref,
                "evidenceRefs": evidence_refs,
                "dimensionId": "compliance",
                "reviewTargetId": review_target_id,
                "factVersionId": fact_version_id,
            }
            for evidence_ref in evidence_refs
        ],
    )


def test_material_and_evidence_reads_are_project_scoped(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "scope.db"),
        generator=StaticGenerator(make_bundle("project-a"), make_bundle("project-b")),
    )
    try:
        assert service.get_material("project-a", "project-a-excel").id == "project-a-excel"
        with pytest.raises(NotFoundError) as error:
            service.get_material("project-a", "project-b-excel")
        assert error.value.code == "material_not_found"

        foreign = _group(["project-b-ev-excel"])
        with pytest.raises(EvidenceSelectionError) as evidence_error:
            service.resolve_evidence("project-a", foreign)
        assert evidence_error.value.details["status"] == "missing_evidence"
        assert evidence_error.value.details["failedTarget"]["evidenceRef"] == "project-b-ev-excel"
    finally:
        service.close()


def test_selection_group_is_all_or_error_and_reports_failed_target(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "selection.db"),
        generator=StaticGenerator(make_bundle()),
    )
    try:
        located_refs = ["project-a-ev-excel", "project-a-ev-pdf"]
        located = service.resolve_evidence("project-a", _group(located_refs))
        assert located.status == "located"
        assert [item.evidence.id for item in located.items] == located_refs

        connection = service.repository.raw_connection_for_tests()
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("review_events", "audit_records", "idempotency_records")
        }
        pending_refs = ["project-a-ev-excel", "project-a-ev-pending"]
        with pytest.raises(EvidenceSelectionError) as error:
            service.resolve_evidence("project-a", _group(pending_refs))
        assert error.value.details["status"] == "pending"
        assert error.value.details["failedTarget"]["evidenceRef"] == "project-a-ev-pending"
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        assert after == before
    finally:
        service.close()


def test_current_material_version_change_returns_version_mismatch(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "version.db"),
        generator=StaticGenerator(make_bundle()),
    )
    try:
        with service.repository.transaction(write=True) as connection:
            current = service.repository.get_material_version(
                "project-a", "project-a-excel-v1", connection
            )
            payload = dict(current.payload)
            payload["versionId"] = "project-a-excel-v2"
            next_version = MaterialVersion(
                id="project-a-excel-v2",
                project_id="project-a",
                material_id="project-a-excel",
                version=2,
                mime_type=current.mime_type,
                content_hash="v2-content-hash",
                payload=payload,
                created_at="2026-08-11T00:00:00+00:00",
                created_by="test",
            )
            service.repository.create_material_version(next_version, connection)
            service.repository.set_current_material_version(
                "project-a", "project-a-excel", next_version.id, connection
            )

        with pytest.raises(EvidenceSelectionError) as error:
            service.resolve_evidence(
                "project-a", _group(["project-a-ev-excel"])
            )
        assert error.value.details["status"] == "version_mismatch"
        assert error.value.details["failedTarget"]["evidenceRef"] == "project-a-ev-excel"
    finally:
        service.close()


def test_single_cell_excel_locator_is_rejected_like_frozen_front(tmp_path: Path) -> None:
    service = create_workbench_service(
        Settings(database_path=tmp_path / "invalid-excel.db"),
        generator=StaticGenerator(make_bundle()),
    )
    try:
        with service.repository.transaction(write=True) as connection:
            service.repository.create_evidence_reference(
                EvidenceReference(
                    id="project-a-ev-invalid-excel",
                    project_id="project-a",
                    label="不符合冻结前端格式的单格定位",
                    locator=ExcelLocator(
                        material_id="project-a-excel",
                        material_version_id="project-a-excel-v1",
                        sheet="Sheet1",
                        range="A4",
                    ),
                    location_status="located",
                    material_status="review",
                    created_at=utc_now(),
                ),
                connection,
            )
        with pytest.raises(EvidenceSelectionError) as error:
            service.resolve_evidence(
                "project-a", _group(["project-a-ev-invalid-excel"])
            )
        assert error.value.details["status"] == "invalid_locator"
        assert (
            error.value.details["failedTarget"]["evidenceRef"]
            == "project-a-ev-invalid-excel"
        )
    finally:
        service.close()


@pytest.mark.parametrize(
    "evidence_id",
    [
        "project-a-ev-excel",
        "project-a-ev-pdf",
        "project-a-ev-image",
        "project-a-ev-media",
        "project-a-ev-scene",
    ],
)
def test_all_frozen_locator_kinds_resolve(evidence_id: str, tmp_path: Path) -> None:
    database = tmp_path / f"{evidence_id}.db"
    service = create_workbench_service(
        Settings(database_path=database),
        generator=StaticGenerator(make_bundle(), identity=evidence_id),
    )
    try:
        result = service.resolve_evidence("project-a", _group([evidence_id]))
        assert result.items[0].evidence.id == evidence_id
    finally:
        service.close()
