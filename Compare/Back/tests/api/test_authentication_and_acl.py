from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient

import pytest

from app.contracts.agent_communication import AgentMode
from app.core.config import Settings
from app.main import create_app
from app.services.authentication import AuthenticationService, PASSWORD_ITERATIONS, SESSION_COOKIE_NAME


def _client(database: Path, *, environment: str = "development") -> TestClient:
    return TestClient(
        create_app(Settings(database_path=database, environment=environment, agent_mode=AgentMode.SYNTHETIC)),
        raise_server_exceptions=False,
    )

def _login(client: TestClient, username: str) -> dict[str, object]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    assert response.status_code == 200, response.text
    assert SESSION_COOKIE_NAME in response.cookies
    return response.json()["data"]

def test_seed_kdf_memberships_and_migration_are_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "auth.db"
    with _client(database) as client:
        _login(client, "business")
        assert len(client.get("/api/v1/projects").json()["data"]) == 24
    with _client(database) as client:
        _login(client, "risk")
    with sqlite3.connect(database) as db:
        accounts = db.execute("SELECT username, password_salt, password_hash, password_iterations FROM accounts ORDER BY username").fetchall()
        assert [row[0] for row in accounts] == ["business", "coordinator", "risk"]
        assert all(row[3] == PASSWORD_ITERATIONS and row[1] != row[2] and row[2] != "123456" for row in accounts)
        assert len({row[1] for row in accounts}) == 3
        assert db.execute("SELECT COUNT(*) FROM project_memberships").fetchone()[0] == 72
        assert db.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=9").fetchone()[0] == 1


def test_memberships_reconcile_when_projects_are_seeded_after_authentication(tmp_path: Path) -> None:
    database = tmp_path / "late-project-memberships.db"
    AuthenticationService(database).seed()

    with _client(database) as client:
        _login(client, "business")
        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200, projects.text
        project_id = projects.json()["data"][0]["projectId"]
        assert client.get(f"/api/v1/projects/{project_id}/workbench").status_code == 200
        # Reconciliation is idempotent across authenticated requests.
        assert client.get(f"/api/v1/projects/{project_id}/workbench").status_code == 200

    with sqlite3.connect(database) as db:
        project_count = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        assert db.execute(
            "SELECT COUNT(*) FROM project_memberships WHERE project_id=?",
            (project_id,),
        ).fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM project_memberships").fetchone()[0] == project_count * 3

def test_login_me_logout_hash_only_and_expiry(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    with _client(database) as client:
        failed = client.post("/api/v1/auth/login", json={"username": "missing", "password": "wrong"})
        assert failed.status_code == 401
        assert failed.json()["errors"][0]["message"] == "账号或密码错误。"
        account = _login(client, "coordinator")
        assert account == {"accountId": "account-coordinator", "username": "coordinator", "displayName": "协管", "role": "leadership"}
        token = client.cookies.get(SESSION_COOKIE_NAME)
        assert token
        assert client.get("/api/v1/auth/me").status_code == 200
        with sqlite3.connect(database) as db:
            stored = db.execute("SELECT token_hash FROM account_sessions WHERE revoked_at IS NULL").fetchone()[0]
            assert stored == hashlib.sha256(token.encode("ascii")).hexdigest()
            assert token not in stored
        with sqlite3.connect(database) as db:
            db.execute(
                "UPDATE account_sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE token_hash=?",
                (stored,),
            )
            db.commit()
        assert client.get("/api/v1/auth/me").status_code == 401
        _login(client, "coordinator")
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401


def test_repeat_login_allows_local_sessions_but_production_revokes_the_old_session(tmp_path: Path) -> None:
    development_database = tmp_path / "development-sessions.db"
    with _client(development_database) as old_session, _client(development_database) as new_session:
        _login(old_session, "business")
        _login(new_session, "business")
        assert old_session.get("/api/v1/auth/me").status_code == 200
        assert new_session.get("/api/v1/auth/me").status_code == 200
    with sqlite3.connect(development_database) as db:
        assert db.execute("SELECT COUNT(*) FROM account_sessions WHERE revoked_at IS NULL").fetchone()[0] == 2

    production_database = tmp_path / "production-sessions.db"
    with (
        _client(production_database, environment="production") as old_session,
        _client(production_database, environment="production") as new_session,
    ):
        _login(old_session, "business")
        _login(new_session, "business")
        assert old_session.get("/api/v1/auth/me").status_code == 401
        assert new_session.get("/api/v1/auth/me").status_code == 200
    with sqlite3.connect(production_database) as db:
        assert db.execute("SELECT COUNT(*) FROM account_sessions WHERE revoked_at IS NULL").fetchone()[0] == 1

def test_project_membership_roles_and_header_spoof_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "acl.db"
    with _client(database) as anonymous:
        assert anonymous.get("/api/v1/projects", headers={"X-Compare-Role": "leadership"}).status_code == 401
    for username in ("business", "risk", "coordinator"):
        with _client(database) as client:
            account = _login(client, username)
            projects = client.get("/api/v1/projects")
            assert projects.status_code == 200
            project_id = projects.json()["data"][0]["projectId"]
            assert client.get(f"/api/v1/projects/{project_id}/workbench").status_code == 200
            # Empty payload reaches 422 only when the role gate permits the route.
            business_write = client.post(f"/api/v1/projects/{project_id}/facts/x/corrections", json={}, headers={"Idempotency-Key": "auth-test-business", "X-Compare-Role": "business"})
            risk_write = client.post(f"/api/v1/projects/{project_id}/review/risk/questions", json={}, headers={"Idempotency-Key": "auth-test-risk", "X-Compare-Role": "risk"})
            approval_write = client.post(f"/api/v1/projects/{project_id}/approval/transitions", json={}, headers={"Idempotency-Key": "auth-test-leadership", "X-Compare-Role": "leadership"})
            expected = account["role"]
            assert business_write.status_code == (422 if expected == "business" else 403)
            assert risk_write.status_code == (422 if expected == "risk" else 403)
            assert approval_write.status_code == (422 if expected == "leadership" else 403)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM project_memberships WHERE account_id='account-risk'")
        db.commit()
    with _client(database) as risk:
        _login(risk, "risk")
        project_id = risk.app.state.workbench_service.list_projects()[0].project_id
        assert risk.get(f"/api/v1/projects/{project_id}/workbench").status_code == 403

def test_agent_role_is_bound_to_session_and_formal_tables_stay_unchanged(tmp_path: Path) -> None:
    database = tmp_path / "agent-acl.db"
    with _client(database) as business, _client(database) as coordinator:
        _login(business, "business")
        project_id = business.get("/api/v1/projects").json()["data"][0]["projectId"]
        created = business.post(f"/api/v1/projects/{project_id}/agents/threads", json={"title": "权限测试"}, headers={"Idempotency-Key": "auth-agent-create"})
        assert created.status_code == 200, created.text
        thread = created.json()["data"]
        before = {}
        with sqlite3.connect(database) as db:
            for table in ("fact_versions", "evidence_references", "policy_results", "approval_transitions", "review_events"):
                before[table] = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        _login(coordinator, "coordinator")
        denied = coordinator.post(
            f"/api/v1/projects/{project_id}/agents/threads/{thread['id']}/turns",
            json={"instruction": "冒充业务", "expectedVersion": thread["version"], "locale": "zh-CN"},
            headers={"Idempotency-Key": "auth-agent-spoof", "X-Compare-Role": "business"},
        )
        assert denied.status_code == 403
        assert denied.json()["errors"][0]["code"] == "chat_principal_forbidden"
        with sqlite3.connect(database) as db:
            after = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
        assert after == before


def test_seed_runs_once_per_service_and_authenticated_requests_skip_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "auth-seed-once.db"
    with _client(database) as client:
        _login(client, "business")
        monkeypatch.setattr("app.services.authentication.SCHEMA_SQL", "DEFINITELY NOT VALID SQL")
        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200, projects.text
        assert len(projects.json()["data"]) == 24


def test_session_lifetime_defaults_to_eight_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNAL_COUNCIL_SESSION_HOURS", raising=False)
    assert Settings().session_hours == 8
    assert Settings.from_environment().session_hours == 8
