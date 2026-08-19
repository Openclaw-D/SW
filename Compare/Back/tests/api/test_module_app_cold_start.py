from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_module_level_app_cold_starts_real_service_with_temp_sqlite(
    tmp_path: Path,
) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "module-app-cold-start.db"
    script = """
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app, raise_server_exceptions=False) as client:
    login = client.post('/api/v1/auth/login', json={'username': 'business', 'password': '123456'})
    assert login.status_code == 200, login.text
    projects = client.get('/api/v1/projects')
    assert projects.status_code == 200, projects.text
    data = projects.json()['data']
    assert len(data) == 1
    project_id = data[0]['projectId']
    workbench = client.get(f'/api/v1/projects/{project_id}/workbench')
    assert workbench.status_code == 200, workbench.text
    assert workbench.json()['data']['project']['id'] == project_id
"""
    environment = os.environ.copy()
    environment["COMPARE_DATABASE_PATH"] = str(database_path)
    environment["COMPARE_GENERATOR_SEED"] = "20260810"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert database_path.exists()
