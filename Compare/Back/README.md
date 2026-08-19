# signal-council V0.2 Back

The Back service is the local FastAPI and SQLite side of the signal-council reference workbench. Its default runtime provides exactly one deterministic, de-identified demonstration project and turns the frozen Front contract into checked Pydantic, HTTP, SQLite-state, authentication, membership, and error contracts.

It is a financing-lease first-pass material-verification and business-rule workbench—not a general risk platform, statistical model, automatic approval service, OCR/Office platform, or real-customer material store.

## Authority and data boundaries

```text
Front HTTP adapter
  → FastAPI routes and unified envelope
  → Workbench service (versions, idempotency, approval invariants)
  → SQLite repository (project isolation, immutable versions, audit chain)
  → deterministic generator and domain rules
```

- The six fixed dimensions are `compliance`, `transaction`, `production`, `revenue`, `debt`, and `cashflow`. Global `risk` is a five-level summary, not a seventh dimension.
- `scoreGrade`, `decisionGrade`, `confidence`, evidence, and hard gates are separate. A higher score is better; all six dimensions are equally weighted and each is 0–100.
- Missing or unverifiable material lowers confidence or produces `manual_review`; it does not automatically reject a project.
- Generated demonstration output is explicitly simulated. Response `meta` includes `dataStatus`, `source`, `disclaimer`, and `requestId`.
- Projects, materials, evidence, locators, and agent records are isolated by `projectId`. Empty collections and nonexistent projects are different states.
- Candidate and model output are advisory-only. A human confirmation is required before a new authoritative `FactVersion` is created. No agent output can write facts, evidence, policy results, scores, confidence, hard gates, or approvals.

## Material archive

The default public profile remains useful without an original-material archive. `COMPARE_MATERIAL_ROOT` is optional and must be an absolute external directory containing `native-material-packs/`. When it is absent, invalid, unimported, or fails SHA-256 validation, the service reports an honest unavailable state and never falls back to repository assets or import paths.

The public runtime project describes 56 materials (21 Excel, 14 PDF, and 21 PNG). They are de-identified deterministic demonstration records, not customer originals, public-company facts, training data, or statistical-validation samples. The separate 24-case generator and external evaluation packs remain available only for explicit offline engineering checks. Generated material packs, SQLite databases, uploads, and logs are runtime state and must remain untracked.

## Agent and model boundary

`COMPARE_AGENT_MODE` defaults to `synthetic`. Synthetic output is an explicit simulation, not a fallback that pretends to be a provider result. A locally configured provider path is optional and must fail closed; it is not proof of provider quality, authentication security, production SLA, deployment readiness, or automatic decision authority.

The current `glm_cli` real path is frozen to the exact `glm-5.3[1m]` model and `glm_5_3_coding_plan_cli` provenance. It passes that model ID directly to the CLI rather than relying on a mutable alias, and rejects any different or ambiguous `modelUsage` identity.

The fixed Demo accounts are `business`, `risk`, and `coordinator`; the last maps to server role `leadership` and is presented as the system-settings account. A backend session and project membership derive every production principal. The legacy `X-Compare-Role` header is ignored by production routes and exists only in test dependency overrides. Only `business` and `risk` may post project chat or explicitly route to their two advisory Agents. `coordinator` reads the shared projection and manages system settings and approval actions; it is neither a chat sender nor an Agent target. Routing never changes the sender identity or formal write permissions. See [the authorization matrix](docs/AUTHORIZATION.md) and [the collaboration contract](docs/AGENT-CONVERSATION-CONTRACT.md).

All three Demo accounts initially use `123456` only on an isolated intranet Demo. Passwords are independently salted and stored through standard-library PBKDF2; session tokens are high-entropy opaque values delivered only through an HttpOnly/SameSite cookie, while SQLite stores only their SHA-256 hashes and lifecycle timestamps. Repeated login revokes the prior active session. Public release must rotate the initial passwords and enable the remaining security gates.

## Local run

Use Python 3.11 or later. From `Compare/Back`, create a clean local environment from this repository’s requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The default API base is `http://127.0.0.1:8000/api/v1`; health is `http://127.0.0.1:8000/health`; OpenAPI is `http://127.0.0.1:8000/docs`. Default CORS permits only `http://127.0.0.1:4317` and `http://localhost:4317`.

For the supported Windows local-reference path, use [../DEPLOYMENT.md](../DEPLOYMENT.md). Do not borrow a Python environment or cache from another machine.

## Configuration

`.env.example` is a template. The application reads process environment variables and does not implicitly load `.env`.

| Variable | Default / purpose |
| --- | --- |
| `COMPARE_APP_NAME` | `signal-council API` |
| `COMPARE_ENVIRONMENT` | `development` |
| `COMPARE_API_PREFIX` | `/api/v1` |
| `COMPARE_DATABASE_PATH` | Repository-external `%LOCALAPPDATA%\CompareWorkbench\signal-council-demo.db` by default on Windows |
| `COMPARE_GENERATOR_SEED` | `20260810`; identical seed gives the same reference baseline |
| `COMPARE_CORS_ORIGINS` | Comma-separated permitted Front origins |
| `COMPARE_IMPORT_ROOT` | Authorised external import root; APIs accept safe `manifestRef` values and do not disclose raw paths |
| `COMPARE_MATERIAL_ROOT` | Optional absolute external archive root; no repository fallback when unavailable |
| `COMPARE_MATERIAL_INTELLIGENCE_ENABLED` | Enables provider-neutral material orchestration; default `true` |
| `COMPARE_MATERIAL_INTELLIGENCE_TIMEOUT_SECONDS` | Per-call timeout; default `5` seconds |
| `COMPARE_MODEL_GATEWAY_MODE` | `disabled`, `synthetic`, or `real`; default `synthetic`; `real` does not prove an external call occurred |
| `COMPARE_AGENT_MODE` | `disabled`, `synthetic`, or `real`; default `synthetic` |
| `COMPARE_AGENT_PROVIDER` / `COMPARE_AGENT_MODEL` | Optional provider configuration; `glm_cli` is frozen to `glm-5.3[1m]`; retain credentials outside source control |
| `SIGNAL_COUNCIL_SESSION_COOKIE_SECURE` | `false` for isolated HTTP Demo only; public TLS requires `true` |
| `SIGNAL_COUNCIL_SESSION_HOURS` | Session lifetime; default `8` hours |

The existing `COMPARE_*` environment names and `%LOCALAPPDATA%\CompareWorkbench` runtime path remain as a minimal V1 compatibility layer so an upgrade does not silently orphan a prior local database. New user-visible branding and new session settings use `signal-council` naming.

Do not put credentials, SQLite files, uploads, archives, session data, or real material paths in Git.

## HTTP contract

All success and error responses use one envelope:

```json
{
  "data": {},
  "meta": {
    "requestId": "request-...",
    "schemaVersion": "1.0",
    "dataStatus": "simulated",
    "source": "deterministic_business_rules",
    "disclaimer": "De-identified deterministic business-rule demonstration data; human review remains authoritative."
  },
  "errors": []
}
```

Core routes include project listing and workbench snapshots; project-scoped materials and originals; controlled ZIP upload and import preflight/execute; material-intelligence run/latest-result/SceneSpec; candidate confirmation; atomic evidence resolution; time-series query; business correction; shared review events; policy results; and approval state/transitions. Exact request and response mapping is maintained in [API adapter mapping](docs/API-ADAPTER-MAPPING.md) and [Front integration](../Front/P02-INTEGRATION.md).

Authoritative writes use `Idempotency-Key` plus `expectedVersion`. Same key and same canonical payload replay the stored result; same key with a different payload returns `409 idempotency_key_reused`; stale versions return `409 version_conflict`. Evidence resolution is all-or-nothing: a selection group is `located` only when all material, version, region, and locator targets are valid.

Stable error codes include project and material 404s, validation and path/body mismatch errors, version and idempotency conflicts, approval/hard-gate blocks, and material-root availability/integrity errors. The production API does not return mock-only `simulated_failure`.

## Verification

Use the repository venv:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Current configured local gate: `510 passed` and one existing dependency-deprecation warning. A fresh clone without the optional external evaluation packs skips only the asset-dependent offline/oracle modules; the one-project application runtime remains available and is not a production or provider claim.

Then run from the repository root:

```powershell
git diff --check -- Compare/Back
```

The Back gate verifies the local contract, project isolation, idempotency, version handling, evidence resolution, material-root failure boundary, and human-authority rules. It does not verify a production deployment, real customer data, real provider quality, statistical validation, or image-to-3D reconstruction.

## Further contract documents

- [Agent collaboration contract](docs/AGENT-CONVERSATION-CONTRACT.md)
- [AI Assist frozen contract](docs/AI-ASSIST-CONTRACT.md)
- [Material Intelligence and SceneSpec contract](docs/MATERIAL-INTELLIGENCE-CONTRACT.md)
- [External material-root guide](docs/EXTERNAL-MATERIAL-ROOT-MIGRATION.md)
- [DataPack mapping](docs/P5-DATAPACK-MAPPING.md)
- [Native-material pack specification](docs/P5-NATIVE-MATERIAL-PACKS.md)
- [Historical offline evaluation records](evals/model_gateway/README.md) — Chinese records, not a current V1 operating guide
