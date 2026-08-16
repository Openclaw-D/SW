from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.contracts.errors import (
    HardGateBlockedError,
    IdempotencyConflictError,
    NotFoundError,
    VersionConflictError,
)
from app.contracts.material_schema import build_material_field_schema
from app.contracts.workbench import ApprovalState
from app.main import create_app


NOW = datetime(2026, 8, 10, tzinfo=UTC)


class ContractService:
    def __init__(self) -> None:
        self.state = ApprovalState(
            project_id="project-ok",
            version=1,
            status="draft",
            hard_gate_status="pass",
            blocking_rule_ids=[],
            risk_veto=False,
            risk_veto_rule_ids=[],
            updated_at=NOW,
            is_simulated=True,
        )
        self.idempotency: dict[str, tuple[tuple[object, ...], ApprovalState]] = {}

    def close(self) -> None:
        return None

    def list_projects(self):
        return []

    def get_workbench(self, project_id: str):
        raise NotFoundError("project_not_found", "项目不存在。")

    def list_materials(self, project_id: str):
        if project_id == "project-ok":
            return []
        raise NotFoundError("project_not_found", "项目不存在。")

    def get_material_field_schema(self, project_id: str):
        if project_id != "project-ok":
            raise NotFoundError("project_not_found", "项目不存在。")
        return build_material_field_schema(project_id)

    def get_material(self, project_id: str, material_id: str):
        raise NotFoundError("material_not_found", "材料不存在或不属于该项目。")

    def list_review_events(self, project_id: str):
        if project_id != "project-ok":
            raise NotFoundError("project_not_found", "项目不存在。")
        return []

    def list_policy_results(self, project_id: str):
        if project_id != "project-ok":
            raise NotFoundError("project_not_found", "项目不存在。")
        return []

    def get_approval_state(self, project_id: str):
        if project_id == "project-gated":
            return self.state.model_copy(
                update={
                    "project_id": project_id,
                    "hard_gate_status": "block",
                    "blocking_rule_ids": ["HG-OWNERSHIP"],
                    "risk_veto": True,
                    "risk_veto_rule_ids": ["RV-001"],
                }
            )
        if project_id != "project-ok":
            raise NotFoundError("project_not_found", "项目不存在。")
        return self.state

    def transition_approval(self, project_id, command, *, idempotency_key: str):
        if project_id == "project-gated" and command.transition == "complete":
            raise HardGateBlockedError(["HG-OWNERSHIP", "RV-001"])
        if project_id != "project-ok":
            raise NotFoundError("project_not_found", "项目不存在。")
        signature = (command.transition, command.expected_version, command.requested_by, command.reason)
        previous = self.idempotency.get(idempotency_key)
        if previous is not None:
            if previous[0] != signature:
                raise IdempotencyConflictError()
            return previous[1]
        if command.expected_version != self.state.version:
            raise VersionConflictError(
                expected_version=command.expected_version,
                actual_version=self.state.version,
            )
        status = {
            "save_draft": "draft",
            "return": "returned",
            "submit": "submitted",
            "complete": "completed",
        }[command.transition]
        self.state = self.state.model_copy(
            update={"version": self.state.version + 1, "status": status}
        )
        self.idempotency[idempotency_key] = (signature, self.state)
        return self.state


def test_health_envelope_request_id_and_cors_4317() -> None:
    with TestClient(create_app(service=ContractService())) as client:
        response = client.get("/health", headers={"X-Request-ID": "request-health-001"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "request-health-001"
        body = response.json()
        assert body["data"]["status"] == "ok"
        assert body["meta"]["requestId"] == "request-health-001"
        assert body["meta"]["dataStatus"] == "simulated"
        assert body["meta"]["source"] == "deterministic_business_rules"
        assert body["meta"]["disclaimer"]
        assert body["errors"] == []

        preflight = client.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://127.0.0.1:4317",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:4317"


def test_empty_collection_is_200_but_missing_project_and_material_are_404() -> None:
    with TestClient(create_app(service=ContractService())) as client:
        empty = client.get("/api/v1/projects/project-ok/materials")
        assert empty.status_code == 200
        assert empty.json()["data"] == []

        missing_project = client.get("/api/v1/projects/project-missing/materials")
        assert missing_project.status_code == 404
        assert missing_project.json()["errors"][0]["code"] == "project_not_found"

        cross_project = client.get(
            "/api/v1/projects/project-ok/materials/foreign-material"
        )
        assert cross_project.status_code == 404
        assert cross_project.json()["errors"][0]["code"] == "material_not_found"


def test_material_field_schema_exposes_business_roots_processing_gate_and_reserved_fields() -> None:
    with TestClient(create_app(service=ContractService())) as client:
        response = client.get("/api/v1/projects/project-ok/material-field-schema")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["projectId"] == "project-ok"
        assert data["businessRoots"] == ["基本证照", "经营证明", "现场照片", "增信", "租赁标的"]
        assert [item["stage"] for item in data["processingChain"]] == [
            "original_version",
            "parse_candidate",
            "locator_validation",
            "business_rule",
            "human_confirmation",
            "fact_version",
        ]
        assert data["processingChain"][-1]["authority"] == "authoritative_fact"
        assert any(item["frontendVisibility"] == "backend_reserved" for item in data["fields"])
        assert all(item["sourceRoles"] for item in data["fields"])
        assert data["isSimulated"] is True
        assert data["dataStatus"] == "synthetic_demo"
        assert data["source"] == "p5_business_material_schema"
        assert "人工确认" in data["disclaimer"]

        missing = client.get("/api/v1/projects/project-missing/material-field-schema")
        assert missing.status_code == 404
        assert missing.json()["errors"][0]["code"] == "project_not_found"


def test_validation_and_unknown_route_use_the_same_error_envelope() -> None:
    with TestClient(create_app(service=ContractService())) as client:
        missing_header = client.post(
            "/api/v1/projects/project-ok/approval/transitions",
            json={
                "expectedVersion": 1,
                "transition": "submit",
                "requestedBy": "business",
                "reason": "",
            },
        )
        assert missing_header.status_code == 422
        assert missing_header.json()["data"] is None
        assert missing_header.json()["errors"][0]["code"] == "idempotency_key_required"

        invalid_body = client.post(
            "/api/v1/projects/project-ok/approval/transitions",
            headers={"Idempotency-Key": "approval-invalid-001"},
            json={
                "expectedVersion": 0,
                "transition": "submit",
                "requestedBy": "business",
            },
        )
        assert invalid_body.status_code == 422
        assert invalid_body.json()["errors"][0]["code"] == "validation_error"

        missing_route = client.get("/not-a-route")
        assert missing_route.status_code == 404
        assert missing_route.json()["errors"][0]["code"] == "route_not_found"


def test_expected_version_idempotency_and_hard_gate_conflicts_are_deterministic() -> None:
    service = ContractService()
    with TestClient(create_app(service=service)) as client:
        stale = client.post(
            "/api/v1/projects/project-ok/approval/transitions",
            headers={"Idempotency-Key": "approval-stale-001"},
            json={
                "expectedVersion": 9,
                "transition": "submit",
                "requestedBy": "business",
                "reason": "提交",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["errors"][0]["code"] == "version_conflict"

        command = {
            "expectedVersion": 1,
            "transition": "submit",
            "requestedBy": "business",
            "reason": "提交",
        }
        headers = {"Idempotency-Key": "approval-repeat-001"}
        first = client.post(
            "/api/v1/projects/project-ok/approval/transitions",
            headers=headers,
            json=command,
        )
        repeated = client.post(
            "/api/v1/projects/project-ok/approval/transitions",
            headers=headers,
            json=command,
        )
        assert first.status_code == repeated.status_code == 200
        assert first.json()["data"] == repeated.json()["data"]

        conflicting = client.post(
            "/api/v1/projects/project-ok/approval/transitions",
            headers=headers,
            json={**command, "transition": "return"},
        )
        assert conflicting.status_code == 409
        assert conflicting.json()["errors"][0]["code"] == "idempotency_key_reused"

        leadership_override = client.post(
            "/api/v1/projects/project-gated/approval/transitions",
            headers={"Idempotency-Key": "approval-leader-001"},
            json={
                "expectedVersion": 1,
                "transition": "complete",
                "requestedBy": "leadership",
                "reason": "领导要求完成",
            },
        )
        assert leadership_override.status_code == 409
        error = leadership_override.json()["errors"][0]
        assert error["code"] == "hard_gate_blocked"
        assert error["details"]["blockingRuleIds"] == ["HG-OWNERSHIP", "RV-001"]


def test_openapi_freezes_paths_headers_and_expected_version() -> None:
    schema = create_app(service=ContractService()).openapi()
    expected_paths = {
        "/health",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/api/v1/projects",
        "/api/v1/projects/{projectId}/workbench",
        "/api/v1/projects/{projectId}/materials",
        "/api/v1/projects/{projectId}/material-field-schema",
        "/api/v1/projects/{projectId}/materials/{materialId}",
        "/api/v1/projects/{projectId}/materials/{materialId}/original",
        "/api/v1/projects/{projectId}/materials/uploads",
        "/api/v1/projects/{projectId}/materials/imports/preflight",
        "/api/v1/projects/{projectId}/materials/imports",
        "/api/v1/projects/{projectId}/materials/{materialId}/intelligence",
        "/api/v1/projects/{projectId}/materials/{materialId}/intelligence/latest",
        "/api/v1/projects/{projectId}/materials/{materialId}/scene-spec",
        "/api/v1/projects/{projectId}/candidates/{candidateId}/confirm",
        "/api/v1/projects/{projectId}/evidence/resolve",
        "/api/v1/projects/{projectId}/dimensions/{dimensionId}/series/query",
        "/api/v1/projects/{projectId}/facts/{factKey}/corrections",
        "/api/v1/projects/{projectId}/review/risk/questions",
        "/api/v1/projects/{projectId}/review/business/answers",
        "/api/v1/projects/{projectId}/review/risk/answers",
        "/api/v1/projects/{projectId}/review/events",
        "/api/v1/projects/{projectId}/policy/results",
        "/api/v1/projects/{projectId}/approval",
        "/api/v1/projects/{projectId}/approval/transitions",
        "/api/v1/projects/{projectId}/conclusion",
        "/api/v1/model-gateway/capabilities",
        "/api/v1/projects/{projectId}/model-gateway/runs",
        "/api/v1/projects/{projectId}/model-gateway/runs/{runId}",
        "/api/v1/projects/{projectId}/agents/threads",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/messages",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/focus-transitions",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/focus-events",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/turns",
        "/api/v1/projects/{projectId}/agents/threads/{threadId}/controls",
        "/api/v1/projects/{projectId}/agents/runs/{runId}",
        "/api/v1/reconstruction/engine-status",
        "/api/v1/projects/{projectId}/reconstruction/jobs",
        "/api/v1/projects/{projectId}/reconstruction/jobs/{jobId}",
        "/api/v1/projects/{projectId}/reconstruction/jobs/{jobId}/retry",
        "/api/v1/projects/{projectId}/reconstruction/subjects/{subjectKind}/{subjectId}/latest",
        "/api/v1/projects/{projectId}/reconstruction/jobs/{jobId}/assets/{assetId}",
    }
    assert set(schema["paths"]) == expected_paths

    transition = schema["paths"][
        "/api/v1/projects/{projectId}/approval/transitions"
    ]["post"]
    idempotency = next(
        parameter
        for parameter in transition["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert idempotency["required"] is True
    body_ref = transition["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    body_name = body_ref.rsplit("/", 1)[-1]
    assert "expectedVersion" in schema["components"]["schemas"][body_name]["required"]
