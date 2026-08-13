from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _selection_group(target: dict[str, object]) -> dict[str, object]:
    refs = list(target.get("evidenceRefs") or [target["evidenceRef"]])
    dimension_id = str(target["dimensionId"])
    review_target_id = target.get("reviewTargetId")
    fact_version_id = target.get("factVersionId")
    return {
        "id": "::".join(
            [
                dimension_id,
                str(review_target_id or "review"),
                str(fact_version_id or "fact"),
                *(str(ref) for ref in refs),
            ]
        ),
        "dimensionId": dimension_id,
        "reviewTargetId": review_target_id,
        "factVersionId": fact_version_id,
        "targets": [
            {
                **target,
                "evidenceRef": ref,
                "evidenceRefs": refs,
            }
            for ref in refs
        ],
    }


def test_real_generator_repository_service_and_http_loop(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "compare-api-integration.db",
        generator_seed=20260810,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        catalog_response = client.get("/api/v1/projects")
        assert catalog_response.status_code == 200, catalog_response.text
        catalog = catalog_response.json()["data"]
        assert len(catalog) == 24
        project_id = catalog[0]["projectId"]

        workbench_response = client.get(
            f"/api/v1/projects/{project_id}/workbench"
        )
        assert workbench_response.status_code == 200, workbench_response.text
        workbench = workbench_response.json()["data"]
        assert workbench["project"]["id"] == project_id
        assert [item["id"] for item in workbench["dimensions"]] == [
            "compliance",
            "transaction",
            "production",
            "revenue",
            "debt",
            "cashflow",
        ]
        assert workbench_response.json()["meta"]["dataStatus"] == "simulated"
        assert workbench_response.json()["meta"]["source"]
        assert workbench_response.json()["meta"]["disclaimer"]

        initial_events = client.get(
            f"/api/v1/projects/{project_id}/review/events"
        )
        initial_policies = client.get(
            f"/api/v1/projects/{project_id}/policy/results"
        )
        assert initial_events.status_code == initial_policies.status_code == 200
        assert initial_policies.json()["data"] == workbench["riskSummary"][
            "hardConstraintResults"
        ]

        materials = client.get(
            f"/api/v1/projects/{project_id}/materials"
        ).json()["data"]
        assert materials
        material = client.get(
            f"/api/v1/projects/{project_id}/materials/{materials[0]['id']}"
        )
        assert material.status_code == 200
        assert material.json()["data"]["versionId"] == materials[0]["versionId"]
        cross_project_material = client.get(
            f"/api/v1/projects/{catalog[1]['projectId']}/materials/{materials[0]['id']}"
        )
        assert cross_project_material.status_code == 404
        assert cross_project_material.json()["errors"][0]["code"] == "material_not_found"

        evidence_by_id = {item["id"]: item for item in workbench["evidence"]}
        located = next(
            item for item in workbench["evidence"] if item["locationStatus"] == "located"
        )
        target = {
            "evidenceRef": located["id"],
            "evidenceRefs": [located["id"]],
            "dimensionId": "compliance",
            "reviewTargetId": "api-integration-evidence",
            "factVersionId": None,
        }
        resolved = client.post(
            f"/api/v1/projects/{project_id}/evidence/resolve",
            json=_selection_group(target),
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["data"]["status"] == "located"
        assert [
            item["evidence"]["id"] for item in resolved.json()["data"]["items"]
        ] == [located["id"]]
        invalid_group = _selection_group(target)
        invalid_group["id"] = "client-invented-selection-id"
        invalid_resolution = client.post(
            f"/api/v1/projects/{project_id}/evidence/resolve",
            json=invalid_group,
        )
        assert invalid_resolution.status_code == 422
        assert invalid_resolution.json()["errors"][0]["code"] == "validation_error"

        series = client.post(
            f"/api/v1/projects/{project_id}/dimensions/production/series/query",
            json={
                "projectId": project_id,
                "dimensionId": "production",
                "metricIds": ["electricity"],
                "grain": "month",
                "startDate": "2026-01-01",
                "endDate": "2026-12-31",
                "timezone": "Asia/Shanghai",
            },
        )
        assert series.status_code == 200, series.text
        assert series.json()["data"]["status"] == "available"
        assert series.json()["data"]["points"]
        empty_series = client.post(
            f"/api/v1/projects/{project_id}/dimensions/production/series/query",
            json={
                "projectId": project_id,
                "dimensionId": "production",
                "metricIds": ["electricity"],
                "grain": "month",
                "startDate": "2030-01-01",
                "endDate": "2030-12-31",
                "timezone": "Asia/Shanghai",
            },
        )
        assert empty_series.status_code == 200
        assert empty_series.json()["data"]["status"] == "empty"
        assert empty_series.json()["data"]["points"] == []

        source_fact = next(
            fact
            for fact in workbench["facts"]
            if fact["evidenceRefs"]
            and all(ref in evidence_by_id for ref in fact["evidenceRefs"])
        )
        correction_payload = {
            "projectId": project_id,
            "factKey": source_fact["factKey"],
            "fromFactVersionId": source_fact["id"],
            "proposedValue": source_fact["value"],
            "reason": "API 集成测试中的同值业务复核。",
            "evidenceRefs": source_fact["evidenceRefs"],
            "expectedVersion": source_fact["version"],
        }
        correction_path = (
            f"/api/v1/projects/{project_id}/facts/{source_fact['factKey']}/corrections"
        )
        correction_headers = {"Idempotency-Key": "real-correction-0001"}
        corrected = client.post(
            correction_path,
            headers=correction_headers,
            json=correction_payload,
        )
        repeated_correction = client.post(
            correction_path,
            headers=correction_headers,
            json=correction_payload,
        )
        assert corrected.status_code == repeated_correction.status_code == 200
        assert corrected.json()["data"] == repeated_correction.json()["data"]
        correction_data = corrected.json()["data"]
        assert correction_data["factVersion"]["version"] == source_fact["version"] + 1
        assert correction_data["event"]["evidenceTargets"]
        assert correction_data["event"]["immutable"] is True

        idempotency_conflict = client.post(
            correction_path,
            headers=correction_headers,
            json={**correction_payload, "reason": "同 key 的不同载荷。"},
        )
        assert idempotency_conflict.status_code == 409
        assert idempotency_conflict.json()["errors"][0]["code"] == "idempotency_key_reused"

        stale = client.post(
            correction_path,
            headers={"Idempotency-Key": "real-correction-stale-0001"},
            json=correction_payload,
        )
        assert stale.status_code == 409
        assert stale.json()["errors"][0]["code"] == "version_conflict"

        event_target = correction_data["event"]["evidenceTargets"][0]
        events = client.get(
            f"/api/v1/projects/{project_id}/review/events"
        ).json()["data"]
        next_sequence = max(item["sequence"] for item in events) + 1
        thread_id = "api-review-thread-0001"
        shared = {
            "projectId": project_id,
            "dimensionId": event_target["dimensionId"],
            "evidenceTargets": correction_data["event"]["evidenceTargets"],
            "reviewTargetId": correction_data["event"]["reviewTargetId"],
            "threadId": thread_id,
            "replyToEventId": None,
            "factVersionIds": correction_data["event"]["factVersionIds"],
            "evidenceRefs": correction_data["event"]["evidenceRefs"],
            "expectedVersion": next_sequence,
        }
        question = client.post(
            f"/api/v1/projects/{project_id}/review/risk/questions",
            headers={"Idempotency-Key": "real-risk-question-0001"},
            json={**shared, "question": "请业务确认该修正证据。"},
        )
        assert question.status_code == 200, question.text
        question_event = question.json()["data"]
        assert question_event["sequence"] == next_sequence
        assert question_event["evidenceTargets"] == shared["evidenceTargets"]

        business_answer = client.post(
            f"/api/v1/projects/{project_id}/review/business/answers",
            headers={"Idempotency-Key": "real-business-answer-0001"},
            json={
                **shared,
                "answer": "业务已复核，证据与修正保持一致。",
                "replyToEventId": question_event["id"],
                "expectedVersion": next_sequence + 1,
            },
        )
        assert business_answer.status_code == 200, business_answer.text
        business_event = business_answer.json()["data"]["event"]
        assert business_event["actor"] == "business"

        risk_answer = client.post(
            f"/api/v1/projects/{project_id}/review/risk/answers",
            headers={"Idempotency-Key": "real-risk-answer-0001"},
            json={
                **shared,
                "answer": "风控已记录，保留制度 Gate 结果。",
                "replyToEventId": business_event["id"],
                "expectedVersion": next_sequence + 2,
            },
        )
        assert risk_answer.status_code == 200, risk_answer.text
        assert risk_answer.json()["data"]["event"]["actor"] == "risk"
        assert risk_answer.json()["data"]["event"]["evidenceTargets"]
        final_events = client.get(
            f"/api/v1/projects/{project_id}/review/events"
        ).json()["data"]
        assert [event["sequence"] for event in final_events] == sorted(
            event["sequence"] for event in final_events
        )
        assert final_events[-1]["id"] == risk_answer.json()["data"]["event"]["id"]

        gated: tuple[str, dict[str, object]] | None = None
        for project in catalog:
            approval = client.get(
                f"/api/v1/projects/{project['projectId']}/approval"
            ).json()["data"]
            if approval["hardGateStatus"] != "pass":
                gated = (project["projectId"], approval)
                break
        assert gated is not None
        gated_project_id, gated_state = gated
        submitted = client.post(
            f"/api/v1/projects/{gated_project_id}/approval/transitions",
            headers={"Idempotency-Key": "real-approval-submit-0001"},
            json={
                "expectedVersion": gated_state["version"],
                "transition": "submit",
                "requestedBy": "business",
                "reason": "提交人工审批。",
            },
        )
        assert submitted.status_code == 200, submitted.text
        complete_payload = {
            "expectedVersion": submitted.json()["data"]["version"],
            "transition": "complete",
            "requestedBy": "leadership",
            "reason": "尝试领导覆盖。",
        }
        complete_headers = {"Idempotency-Key": "real-approval-complete-0001"}
        blocked = client.post(
            f"/api/v1/projects/{gated_project_id}/approval/transitions",
            headers=complete_headers,
            json=complete_payload,
        )
        blocked_repeat = client.post(
            f"/api/v1/projects/{gated_project_id}/approval/transitions",
            headers=complete_headers,
            json=complete_payload,
        )
        assert blocked.status_code == blocked_repeat.status_code == 409
        assert blocked.json()["errors"] == blocked_repeat.json()["errors"]
        assert blocked.json()["errors"][0]["code"] == "hard_gate_blocked"

        missing = client.get("/api/v1/projects/not-a-project/workbench")
        assert missing.status_code == 404
        assert missing.json()["errors"][0]["code"] == "project_not_found"
