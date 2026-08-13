# SW project instructions

## Scope

- Treat `Front/`, `Back/`, and `Show/` as the complete active project.
- Do not search for, restore, or infer behavior from deleted V1/V2/Other history.
- Keep the Front homepage frozen unless the user explicitly authorizes homepage work.
- Prefer small, page-local, verifiable changes. Do not commit or push unless explicitly requested.

## Product truth

- A higher score is better. The six dimensions are equally weighted and each dimension is scored out of 100.
- Keep `scoreGrade`, `decisionGrade`, confidence, evidence, and hard-gate decisions separate.
- Without validated historical samples, describe outputs as business-rule evaluation and single-project fact checking, not a statistically validated risk model.
- Missing or unverifiable material lowers confidence or triggers manual review; it must not automatically become rejection.
- Concept images and demo text are not verified business facts.

## Architecture

- Frontend: `Front/`, default API base `http://127.0.0.1:8000/api/v1`.
- Backend: `Back/`, FastAPI entrypoint `app.main:app`.
- Local runtime databases and uploaded files are generated state and must remain untracked.
- Never rely on dependencies or caches copied from another computer; rebuild from lockfiles and requirements.

## Validation

- Frontend risk engine: `node --test tests/risk-engine.test.mjs`.
- Frontend build: `npm run build`.
- Backend: `python -m pytest` from `Back/` with its virtual environment active.
- Use `git diff --check` before accepting changes.
- Report build, focused tests, lint, and visual acceptance separately; do not call one a substitute for another.

## Security

- Never commit `.env`, SQLite runtime data, uploaded documents, credentials, tokens, session state, user records, IP addresses, or browser user-agent data.
- Default usernames/passwords in `Back/app/core/config.py` are local-development values only and must be overridden outside an isolated local demo.
