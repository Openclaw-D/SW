from __future__ import annotations

from pathlib import Path

from app.contracts.workbench import (
    DimensionSeriesRequest,
    ReviewEvidenceSelectionGroup,
)
from app.core.config import Settings
from app.services.workbench import create_workbench_service


def test_default_back3_provider_seeds_resolves_queries_and_restarts(
    tmp_path: Path,
) -> None:
    database = tmp_path / "back3-integration.db"
    settings = Settings(database_path=database, generator_seed=20260810)

    first = create_workbench_service(settings)
    try:
        projects = first.list_projects()
        assert len(projects) == 24
        project_id = projects[0].project_id
        workbench = first.get_workbench(project_id)
        assert workbench.project.id == project_id
        assert len(workbench.dimensions) == 6

        located = next(
            evidence
            for evidence in workbench.evidence
            if evidence.location_status == "located"
        )
        target = {
            "evidenceRef": located.id,
            "evidenceRefs": [located.id],
            "dimensionId": "compliance",
            "reviewTargetId": "integration-evidence",
            "factVersionId": None,
        }
        group = ReviewEvidenceSelectionGroup(
            id=f"compliance::integration-evidence::fact::{located.id}",
            dimensionId="compliance",
            reviewTargetId="integration-evidence",
            factVersionId=None,
            targets=[target],
        )
        assert first.resolve_evidence(project_id, group).status == "located"

        response = first.query_dimension_series(
            project_id,
            "production",
            DimensionSeriesRequest(
                projectId=project_id,
                dimensionId="production",
                metricIds=["electricity"],
                grain="month",
                startDate="2026-01-01",
                endDate="2026-12-31",
                timezone="Asia/Shanghai",
            ),
        )
        assert response.status == "available"
        assert response.points
    finally:
        first.close()

    second = create_workbench_service(settings)
    try:
        assert len(second.list_projects()) == 24
        connection = second.repository.raw_connection_for_tests()
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 24
        assert connection.execute("SELECT COUNT(*) FROM seed_runs").fetchone()[0] == 1
    finally:
        second.close()
