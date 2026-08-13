# Signal Council

**Signal Council · 见微** is an evidence-grounded human-AI collaboration workbench for high-stakes review and decision workflows.

It demonstrates how structured evidence, deterministic business rules, role-bounded AI assistance, human review gates, and an append-only audit trail can operate as one system. The included reference implementation applies the framework to a fully de-identified equipment-financing review scenario.

> Signal Council is a local reference workbench, not a production approval system, a statistically validated risk model, or a substitute for an authorized human decision-maker.

## What V1 demonstrates

- A real browser → HTTP API → FastAPI → SQLite workflow.
- Twenty-four isolated demo projects generated from one deterministic public standard profile.
- Six evidence-backed review dimensions with score, confidence, evidence status, policy results, and decision grade kept separate.
- Project-scoped materials, evidence locators, corrections, review events, policy gates, approvals, and audit records.
- Three role-bounded collaboration lanes for business, risk, and leadership assistance.
- Advisory-only AI output: agents cannot silently rewrite authoritative facts or approve a case.
- English and Chinese product surfaces, with English as the public default.
- Honest failure states when external materials, reconstruction engines, or real model providers are not configured.

## Architecture

```text
Browser
  -> Signal Council Front (React + TypeScript + vinext)
  -> HTTP gateway
  -> Signal Council API (FastAPI + Pydantic)
  -> domain services and human gates
  -> SQLite state, versions, and audit trail

Optional, explicitly configured integrations
  -> external material archive
  -> real model provider
  -> local reconstruction engine
```

The default public profile does not require credentials or the external material archive. It uses deterministic, fully de-identified data and synthetic agent responses so a fresh clone can exercise the complete core workflow.

## Quick start on Windows

### Prerequisites

- Node.js 22.13 or newer
- Python 3.11 or newer
- PowerShell 5.1 or PowerShell 7

### Install dependencies

```powershell
cd Compare\Front
npm.cmd ci

cd ..\Back
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### Start the public V1 profile

```powershell
cd ..
.\start-local.ps1 -AgentMode synthetic
```

Open <http://127.0.0.1:4317>. The API is available at <http://127.0.0.1:8000/api/v1>.

The launcher stores SQLite databases, logs, and imports outside the repository. It does not install dependencies, delete databases, or terminate unknown processes.

## Validation

```powershell
cd Compare\Front
npm.cmd run typecheck
npm.cmd run build
npm.cmd test

cd ..\Back
.\.venv\Scripts\python.exe -m pytest -q

cd ..\..
git diff --check -- Compare
```

## Repository layout

```text
Compare/
  Front/          React and TypeScript product surface
  Back/           FastAPI application, domain services, SQLite, and tests
  start-local.ps1 Safe local launcher and health checks
  DEPLOYMENT.md   Detailed local deployment boundaries
```

Runtime databases, uploaded documents, build output, dependency directories, credentials, and the optional external material archive are deliberately excluded from Git.

## Data and safety boundaries

- All bundled projects and business records are deterministic, synthetic, and de-identified.
- Missing or unverifiable evidence lowers confidence or requires manual review; it does not automatically become rejection.
- A higher score is better. The six dimensions are equally weighted and scored out of 100.
- AI and generated candidates remain advisory until an explicit human workflow formalizes a result.
- No production authentication, multi-tenant authorization, privacy program, backup policy, or public hosting configuration is included in V1.
- The 3D views are explanatory structured visualizations unless a separately configured and validated reconstruction engine proves otherwise.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports should follow [SECURITY.md](SECURITY.md).

## License

Signal Council source code and original documentation are licensed under the [Apache License 2.0](LICENSE).

Third-party reference images retain their original licenses and attribution requirements. See [`Compare/Front/public/reference-images/SOURCES.md`](Compare/Front/public/reference-images/SOURCES.md) before redistributing those assets.
