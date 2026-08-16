from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _client() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def _request(
    client: urllib.request.OpenerDirector,
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object] | None]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with client.open(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _login(base_url: str, username: str) -> urllib.request.OpenerDirector:
    client = _client()
    status, _ = _request(
        client,
        "POST",
        f"{base_url}/api/v1/auth/login",
        {"username": username, "password": "123456"},
    )
    assert status == 200
    return client


def test_real_http_sessions_memberships_and_role_acl(tmp_path: Path) -> None:
    database_path = tmp_path / "real-http-gate.db"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "COMPARE_DATABASE_PATH": str(database_path),
            "COMPARE_ENVIRONMENT": "production",
            "COMPARE_AGENT_MODE": "synthetic",
            "SIGNAL_COUNCIL_SESSION_HOURS": "8",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        for _ in range(80):
            try:
                status, payload = _request(_client(), "GET", f"{base_url}/health")
                if status == 200 and payload and payload["data"]["status"] == "ok":
                    break
            except OSError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("temporary Uvicorn server did not become ready")

        anonymous = _client()
        assert _request(anonymous, "GET", f"{base_url}/api/v1/projects")[0] == 401
        assert (
            _request(
                anonymous,
                "GET",
                f"{base_url}/api/v1/projects",
                headers={"X-Compare-Role": "leadership"},
            )[0]
            == 401
        )

        sessions = {role: _login(base_url, role) for role in ("business", "risk", "coordinator")}
        project_counts: dict[str, int] = {}
        project_id = ""
        for role, client in sessions.items():
            status, payload = _request(client, "GET", f"{base_url}/api/v1/projects")
            assert status == 200 and payload
            projects = payload["data"]
            assert isinstance(projects, list)
            project_counts[role] = len(projects)
            project_id = str(projects[0]["projectId"])
        assert project_counts == {"business": 24, "risk": 24, "coordinator": 24}

        thread_url = f"{base_url}/api/v1/projects/{project_id}/agents/threads"
        assert _request(
            sessions["business"], "POST", thread_url, {"title": "HTTP ACL gate"},
            {"Idempotency-Key": "real-http-business-thread"},
        )[0] == 200
        assert _request(
            sessions["risk"], "POST", thread_url, {"title": "forbidden"},
            {"Idempotency-Key": "real-http-risk-thread"},
        )[0] == 403
        assert _request(
            sessions["coordinator"], "POST", thread_url, {"title": "forbidden"},
            {"Idempotency-Key": "real-http-coordinator-thread"},
        )[0] == 403

        approval_url = f"{base_url}/api/v1/projects/{project_id}/approval"
        assert _request(sessions["coordinator"], "GET", approval_url)[0] == 200
        assert _request(
            sessions["risk"], "POST", f"{approval_url}/transitions", {},
            {"Idempotency-Key": "real-http-risk-approval"},
        )[0] == 403

        old_session = _login(base_url, "business")
        new_session = _login(base_url, "business")
        assert _request(old_session, "GET", f"{base_url}/api/v1/auth/me")[0] == 401
        assert _request(new_session, "GET", f"{base_url}/api/v1/auth/me")[0] == 200

        assert _request(sessions["risk"], "POST", f"{base_url}/api/v1/auth/logout")[0] == 200
        assert _request(sessions["risk"], "GET", f"{base_url}/api/v1/auth/me")[0] == 401

        expiry_session = _login(base_url, "coordinator")
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE account_sessions SET expires_at = ? WHERE revoked_at IS NULL",
                ("2000-01-01T00:00:00+00:00",),
            )
            connection.commit()
        assert _request(expiry_session, "GET", f"{base_url}/api/v1/auth/me")[0] == 401

        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 3
            assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 24
            assert connection.execute("SELECT COUNT(*) FROM project_memberships").fetchone()[0] == 72
            hash_lengths = connection.execute(
                "SELECT MIN(length(token_hash)), MAX(length(token_hash)) FROM account_sessions"
            ).fetchone()
            assert hash_lengths == (64, 64)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(account_sessions)")}
            assert not columns.intersection({"token", "password", "ip", "user_agent"})
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
