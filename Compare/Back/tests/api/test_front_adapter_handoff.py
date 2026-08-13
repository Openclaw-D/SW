from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _selection_group(evidence_refs: list[str]) -> dict[str, object]:
    """Build the frozen all-or-clear selection group without inventing IDs."""
    return {
        "id": "::".join(["transaction", "adapter-rent", "fact", *evidence_refs]),
        "dimensionId": "transaction",
        "reviewTargetId": "adapter-rent",
        "factVersionId": None,
        "targets": [
            {
                "evidenceRef": reference,
                "evidenceRefs": evidence_refs,
                "dimensionId": "transaction",
                "reviewTargetId": "adapter-rent",
                "factVersionId": None,
            }
            for reference in evidence_refs
        ],
    }


def _series_payload(project_id: str) -> dict[str, object]:
    return {
        "projectId": project_id,
        "dimensionId": "production",
        "metricIds": ["electricity"],
        "grain": "month",
        "startDate": "2030-01-01",
        "endDate": "2030-12-31",
        "timezone": "Asia/Shanghai",
    }


def test_front_adapter_mapping_uses_envelopes_and_actionable_errors(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "adapter-mapping.db", generator_seed=20260810)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        schema = client.get("/openapi.json").json()
        projects_path = schema["paths"]["/api/v1/projects"]
        assert projects_path["get"]["operationId"] == "listProjects"
        correction = schema["paths"][
            "/api/v1/projects/{projectId}/facts/{factKey}/corrections"
        ]["post"]
        key_parameter = next(
            item for item in correction["parameters"] if item["name"] == "Idempotency-Key"
        )
        assert key_parameter["required"] is True
        assert set(correction["responses"]) >= {"200", "404", "409", "422"}

        catalog = client.get("/api/v1/projects")
        assert catalog.status_code == 200
        assert catalog.headers["X-Request-ID"] == catalog.json()["meta"]["requestId"]
        assert catalog.json()["meta"]["dataStatus"] == "simulated"
        assert catalog.json()["errors"] == []
        projects = catalog.json()["data"]
        assert len(projects) == 24

        first_id, other_id = projects[0]["projectId"], projects[1]["projectId"]
        first_workbench = client.get(f"/api/v1/projects/{first_id}/workbench").json()["data"]
        material_id = first_workbench["materials"][0]["id"]
        cross_project = client.get(
            f"/api/v1/projects/{other_id}/materials/{material_id}"
        )
        assert cross_project.status_code == 404
        assert cross_project.json()["data"] is None
        assert cross_project.json()["errors"][0]["category"] == "not_found"
        assert cross_project.json()["errors"][0]["code"] == "material_not_found"

        malformed = client.post(
            f"/api/v1/projects/{first_id}/evidence/resolve",
            json={"id": "bad", "dimensionId": "transaction", "reviewTargetId": None, "factVersionId": None, "targets": []},
        )
        assert malformed.status_code == 422
        assert malformed.json()["errors"][0]["category"] == "validation"

        empty_series = client.post(
            f"/api/v1/projects/{first_id}/dimensions/production/series/query",
            json=_series_payload(first_id),
        )
        assert empty_series.status_code == 200
        assert empty_series.json()["data"]["status"] == "empty"
        assert empty_series.json()["data"]["points"] == []

        fact = next(item for item in first_workbench["facts"] if item["evidenceRefs"])
        correction_path = f"/api/v1/projects/{first_id}/facts/{fact['factKey']}/corrections"
        command = {
            "projectId": first_id,
            "factKey": fact["factKey"],
            "fromFactVersionId": fact["id"],
            "proposedValue": fact["value"],
            "reason": "Adapter handoff header and version validation.",
            "evidenceRefs": fact["evidenceRefs"],
            "expectedVersion": fact["version"],
        }
        missing_key = client.post(correction_path, json=command)
        assert missing_key.status_code == 422
        assert missing_key.json()["errors"][0]["code"] == "idempotency_key_required"
        stale = client.post(
            correction_path,
            headers={"Idempotency-Key": "adapter-stale-correction-001"},
            json={**command, "expectedVersion": fact["version"] + 9},
        )
        assert stale.status_code == 409
        error = stale.json()["errors"][0]
        assert error["code"] == "version_conflict"
        assert error["details"]["actualVersion"] == fact["version"]


def test_all_projects_expose_project_scoped_dynamic_rent_evidence(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "adapter-rent.db", generator_seed=20260810)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        projects = client.get("/api/v1/projects").json()["data"]
        all_references: set[str] = set()
        assert len(projects) == 24

        for project in projects:
            project_id = project["projectId"]
            response = client.get(f"/api/v1/projects/{project_id}/workbench")
            assert response.status_code == 200, response.text
            schedule = response.json()["data"]["financedEquipment"]["repaymentSchedule"]
            references = schedule["firstTwelveEvidenceRefs"]
            assert schedule["status"] == "available"
            assert len(references) == 12
            assert len(set(references)) == len(references)
            assert all(reference not in all_references for reference in references)
            all_references.update(references)

            resolution = client.post(
                f"/api/v1/projects/{project_id}/evidence/resolve",
                json=_selection_group(references),
            )
            assert resolution.status_code == 200, resolution.text
            resolved = resolution.json()["data"]
            assert resolved["status"] == "located"
            assert [item["evidence"]["id"] for item in resolved["items"]] == references

        assert len(all_references) == 24 * 12
