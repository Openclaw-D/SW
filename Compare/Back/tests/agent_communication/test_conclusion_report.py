from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.contracts.agent_communication import AgentMode
from app.core.config import Settings
from app.main import create_app


def _headers(role: str, key: str) -> dict[str, str]:
    return {"X-Compare-Role": role, "Idempotency-Key": key}


def _table_counts(database_path) -> dict[str, int]:
    tables = (
        "business_corrections",
        "fact_versions",
        "review_events",
        "policy_results",
        "approval_states",
        "approval_transitions",
        "agent_threads",
        "agent_runs",
        "agent_messages",
        "agent_focus_events",
    )
    with sqlite3.connect(database_path) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }


def test_conclusion_report_is_read_only_and_preserves_decision_boundaries(tmp_path) -> None:
    database = tmp_path / "conclusion-read-only.db"
    with TestClient(
        create_app(Settings(database_path=database, agent_mode=AgentMode.SYNTHETIC))
    ) as client:
        project_id = client.get("/api/v1/projects").json()["data"][0]["projectId"]
        endpoint = f"/api/v1/projects/{project_id}/conclusion"

        first = client.get(endpoint)
        assert first.status_code == 200, first.text
        report = first.json()["data"]
        assert report["schemaVersion"] == "1.0"
        assert report["projectId"] == project_id
        assert set(report["overall"]) >= {
            "riskLevel",
            "scoreGrade",
            "decisionGrade",
            "confidence",
        }
        assert len(report["dimensions"]) == 6
        assert all(
            set(item) >= {"score", "scoreGrade", "decisionGrade", "confidence"}
            for item in report["dimensions"]
        )
        assert report["collaboration"] == {
            "hasThread": False,
            "threadId": None,
            "threadTitle": None,
            "threadStatus": None,
            "focusRole": None,
            "threadVersion": None,
            "messageCount": 0,
            "agentMessageCount": 0,
            "focusEventCount": 0,
            "focusTransitionCount": 0,
            "latestAdvice": None,
        }
        assert report["humanConfirmation"]["required"] is True
        assert "不执行审批" in report["disclaimer"]
        assert report["advisoryOnly"] is True
        assert report["source"] == "server_conclusion_projection"
        assert sum(report["evidenceStatusCounts"].values()) == report["evidenceTotal"]

        before = _table_counts(database)
        second = client.get(endpoint)
        assert second.status_code == 200
        assert _table_counts(database) == before


def test_conclusion_report_projects_latest_single_focus_advice_and_provenance(tmp_path) -> None:
    database = tmp_path / "conclusion-agent.db"
    with TestClient(
        create_app(Settings(database_path=database, agent_mode=AgentMode.SYNTHETIC))
    ) as client:
        catalog = client.get("/api/v1/projects").json()["data"]
        project_id = catalog[0]["projectId"]
        other_project_id = catalog[1]["projectId"]
        created = client.post(
            f"/api/v1/projects/{project_id}/agents/threads",
            headers=_headers("business", "conclusion-thread-0001"),
            json={"title": "负责人结论准备"},
        ).json()["data"]
        business_turn = client.post(
            f"/api/v1/projects/{project_id}/agents/threads/{created['id']}/turns",
            headers=_headers("business", "conclusion-turn-00001"),
            json={
                "instruction": "整理当前证据缺口并提出追问。",
                "replyToMessageId": None,
                "evidenceTargets": [],
                "expectedVersion": created["version"],
                "locale": "zh-CN",
            },
        )
        assert business_turn.status_code == 200, business_turn.text
        version = business_turn.json()["data"]["nextExpectedVersion"]
        focused = client.post(
            f"/api/v1/projects/{project_id}/agents/threads/{created['id']}/focus-transitions",
            headers=_headers("business", "conclusion-focus-0001"),
            json={
                "toFocusRole": "risk",
                "expectedVersion": version,
                "reason": "请风控短暂复核。",
            },
        )
        assert focused.status_code == 200, focused.text
        risk_turn = client.post(
            f"/api/v1/projects/{project_id}/agents/threads/{created['id']}/turns",
            headers=_headers("risk", "conclusion-turn-00002"),
            json={
                "instruction": "复核证据充分性，保持建议属性。",
                "replyToMessageId": None,
                "evidenceTargets": [],
                "expectedVersion": focused.json()["data"]["version"],
                "locale": "zh-CN",
            },
        )
        assert risk_turn.status_code == 200, risk_turn.text

        report_response = client.get(f"/api/v1/projects/{project_id}/conclusion")
        assert report_response.status_code == 200, report_response.text
        report = report_response.json()["data"]
        collaboration = report["collaboration"]
        assert collaboration["threadId"] == created["id"]
        assert collaboration["focusRole"] == "business"
        assert collaboration["messageCount"] == 4
        assert collaboration["agentMessageCount"] == 2
        assert collaboration["focusEventCount"] == 3
        assert collaboration["focusTransitionCount"] == 2
        latest = collaboration["latestAdvice"]
        assert latest["role"] == "risk"
        assert latest["advisoryOnly"] is True
        assert latest["execution"]["advisoryOnly"] is True
        assert latest["execution"]["providerId"]
        assert latest["execution"]["modelId"]
        assert latest["execution"]["inputHash"]
        assert latest["execution"]["contextVersion"]
        assert latest["execution"]["outputHash"]
        assert "单焦点 Agent 建议与 provenance" in report["aiValue"]["sourceSectionsConsolidated"]
        assert report["aiValue"]["advisoryMessagesAvailable"] == 2
        assert report["aiValue"]["focusTransitionsRecorded"] == 2

        other = client.get(f"/api/v1/projects/{other_project_id}/conclusion").json()["data"]
        assert other["collaboration"]["hasThread"] is False
        assert other["collaboration"]["latestAdvice"] is None


def test_conclusion_openapi_contract_is_read_only() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/projects/{projectId}/conclusion"]["get"]
    assert operation["operationId"] == "readProjectConclusionReport"
    assert {"200", "404", "422", "503"} <= set(operation["responses"])
    assert "requestBody" not in operation
    assert not any(parameter["name"] == "X-Compare-Role" for parameter in operation["parameters"])
