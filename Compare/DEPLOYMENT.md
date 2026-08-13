# Signal Council · 见微 V1: Windows Local Reference Run

This guide describes a local reference run on an isolated Windows host. It is not an Internet deployment or a production-release guide. V1 has no login, trusted identity, multitenancy, production privacy, backup, or external-network security gate; do not expose it directly to the Internet.

## Topology and scope

```text
Browser
  → Front: http://127.0.0.1:4317
  → Back:  http://127.0.0.1:8000/api/v1
  → SQLite, logs, and imports outside the repository
  → optional external material archive
```

The path does not use Docker and does not install dependencies automatically. Front runs with the existing vinext development server and Back runs with Uvicorn. Cloud hosting, Windows Service hosting, reverse proxying, TLS, authentication, and automated backups are outside V1.

## Prerequisites

- Windows PowerShell 5.1 or PowerShell 7.
- Node.js `>=22.13.0`, `npm.cmd`, and Front dependencies installed from `Front/package-lock.json`.
- Python `>=3.11`, preferably `Back/.venv/Scripts/python.exe`, with dependencies installed from `Back/requirements-dev.txt`. `COMPARE_PYTHON_PATH` may point to a prepared interpreter.
- An external material archive is optional. If configured, it must be an absolute directory containing `native-material-packs/`. Without it, the core workbench starts and original-material reads accurately report unavailable.

Create a Git-ignored `Back/.env` from `Back/.env.example` only if configuration is needed. The script can import simple `KEY=VALUE` entries; the application itself reads process environment variables. Never commit secrets, real archive locations, runtime databases, uploads, or logs.

## Start

From `Compare/`:

```powershell
.\start-local.ps1 -AgentMode synthetic
```

The script performs preflight, safe port handling, starts Back and Front, and checks health, project listing, CORS, and page identity. It does not install dependencies, clear or migrate a database, or terminate an unknown process on ports 4317 or 8000. An existing process is reused only after its readiness check succeeds.

## Preflight, status, and readiness

```powershell
.\start-local.ps1 -Action Preflight -AgentMode synthetic
.\start-local.ps1 -Action Status
.\start-local.ps1 -Action Check
```

`Preflight` does not start services. It checks Python and Node versions, installed dependencies, repository-external runtime paths, the optional material root, and port availability. `Check` requires Back health `ok`, a non-empty project directory, correct CORS for the active Front origin, and a Front HTTP 200 response identifiable as Signal Council.

By default, the database is outside the repository at `%LOCALAPPDATA%\CompareWorkbench\compare.db`; deployment state and logs are under `%LOCALAPPDATA%\CompareWorkbench\deployment\`. `COMPARE_DATABASE_PATH`, `COMPARE_IMPORT_ROOT`, `COMPARE_MATERIAL_ROOT`, and `COMPARE_DEPLOY_RUNTIME_ROOT` may override them, but must remain outside the repository.

## Stop and diagnose

```powershell
.\start-local.ps1 -Action Stop
```

Stop acts only on a process proven by the state file to have been launched by this script and whose PID and command still match. Reused services, changed PIDs, and mismatched commands are left untouched with a warning.

For a failed start, inspect the log directory printed by the script:

- `back.stderr.log`: Python, configuration, database, or port failures.
- `front.stderr.log`: Node, dependency, build, or port failures.
- A material-root `WARN` means originals are optional and unavailable; it does not block the core workbench.

## Rollback boundary

Stopping services does not delete SQLite data, logs, imports, or materials. Use ordinary Git review for code rollback; do not use the script to delete or reset user data. To select an earlier local database, stop the services, change the repository-external `COMPARE_DATABASE_PATH`, and start again.

Production release would require separate gates for authentication, TLS, process hosting, backup and recovery, privacy and retention, real-provider SLA, and Internet security.
