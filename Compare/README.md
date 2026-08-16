# signal-council — V1

signal-council is a local reference workbench for financing-lease material verification and business-rule evaluation. Its repository is [Openclaw-D/signal-council](https://github.com/Openclaw-D/signal-council). It is not a production service, an automated approval system, a statistically validated risk model, or a repository of real customer material.

The public V1 profile contains 24 isolated, deterministic, de-identified demonstration projects generated from one shared standard template. The live local path is:

```text
Browser → HTTP → FastAPI → SQLite
```

Core review flow:

```text
Original material → controlled advisory candidate → human confirmation or business correction → risk determination
```

Human gates are authoritative. AI output is advisory-only: it cannot write authoritative facts, evidence, scores, confidence, policy results, hard-gate results, or approvals.

## What V1 does

- Presents six equally weighted dimensions—compliance, transaction, production, revenue, debt, and cashflow—each scored from 0 to 100. A higher score is better. The global risk summary is not a seventh dimension.
- Keeps `scoreGrade`, `decisionGrade`, confidence, evidence, and hard-gate decisions separate.
- Supports project-scoped materials, evidence locations, versioned facts, business corrections, shared review events, policy results, and approval-state projections through HTTP and SQLite.
- Uses deterministic de-identified data by default. Missing or unverifiable material lowers confidence or creates a manual-review path; it does not automatically mean rejection.
- Provides three fixed intranet Demo accounts: `business`（业务）, `risk`（风控）, and `coordinator`（协管，server role `leadership`）. Every seeded project is shared through project membership, while private drafts and write actions remain role-scoped.
- Offers one chronological project group chat for the `business` and `risk` accounts. Plain messages do not trigger an Agent; only an explicit `@业务` or `@风控` route does. The `coordinator` account manages system settings and approval actions, can read the shared projection, and is not a chat sender or Agent target. Agent replies remain advisory and require formal human review before any authoritative action.
- Can optionally read validated originals from an external material archive. Without that archive, the core workbench remains available and original preview honestly reports unavailable.

## Limits that are deliberate

- V1 is local reference software, not an Internet-facing deployment.
- The public default is synthetic and deterministic. A locally configured provider path is not evidence of production readiness, provider quality, authentication security, SLA, or statistical validation.
- There is no real-customer dataset, multitenancy, public OCR/Office service, or verified image-to-3D reconstruction engine. Authentication and project-role authorization are implemented for the fixed intranet Demo accounts, not as a public identity platform.
- `SceneSpec` and any GLB attachment are derived, declarative artifacts; they are not surveys, CAD, scans, 3D Gaussian Splatting, or verified reconstructions of a real asset or site.

## Run locally on Windows

The supported local entry point is [DEPLOYMENT.md](DEPLOYMENT.md). It documents prerequisites, configuration, preflight, start, status, verification, stop, and rollback boundaries.

```powershell
cd .\Compare
.\start-local.ps1 -AgentMode synthetic
```

Use `npm.cmd` for Front commands on Windows. Build Python dependencies into `Back/.venv`; do not reuse environments or caches from another machine. Copy `Back/.env.example` to an untracked `Back/.env` only when local configuration is required. Never commit secrets, external archive paths, SQLite databases, uploads, logs, or session state.

The three intranet Demo accounts initially use password `123456`. This is a demonstration bootstrap value only. Before any Internet exposure, replace/rotate it, set secure cookies, add TLS and production process hosting, and pass the remaining public-security gates described in [DEPLOYMENT.md](DEPLOYMENT.md). Passwords are stored only as independently salted PBKDF2 hashes; sessions use an HttpOnly/SameSite cookie while SQLite stores only the token hash and necessary lifecycle timestamps.

## Verified V1 reference gates

- Front: `204/204` tests passed, plus typecheck and build.
- Back: the current authentication/ACL run passed `424`; `37` frozen offline/oracle modules were skipped because their external native packs are absent; one warning remained.
- UI: the bilingual interface passed the 1920×1080 acceptance gate.

These gates verify the local reference implementation only. They do not establish a production deployment, real-provider quality, real external API operation, statistical model validity, or real image-to-3D output.

## Repository map

```text
Compare/
├── Front/                         Browser application and HTTP gateway
├── Back/                          FastAPI application, contracts, and SQLite persistence
├── DEPLOYMENT.md                  Windows local-run guide
├── AGENTS.md                      Contributor operating constraints
├── ROADMAP.md / STATUS.md         Chinese historical engineering records and gate history
├── DECISIONS.md                   Chinese historical decision record
└── Back/evals/                    Frozen offline evaluation records, not a V1 user guide
```

Current integration details are in [Front/P02-INTEGRATION.md](Front/P02-INTEGRATION.md). Backend contracts and operational boundaries are in [Back/README.md](Back/README.md). Reference-image attribution is in [Front/public/reference-images/SOURCES.md](Front/public/reference-images/SOURCES.md).

## Historical records

`ROADMAP.md`, `STATUS.md`, `DECISIONS.md`, `P6-VOICE-HANDOFF.md`, and `Back/evals/` preserve Chinese historical engineering and evaluation evidence. They are not current English V1 installation or operating instructions. Their historical wording, snapshots, and evidence semantics are intentionally retained rather than retroactively rewritten.
