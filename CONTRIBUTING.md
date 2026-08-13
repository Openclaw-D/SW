# Contributing to Signal Council

Thank you for helping improve Signal Council.

## Before opening a change

1. Keep generated, uploaded, runtime, and sensitive data out of Git.
2. Preserve the separation between facts, evidence, confidence, policy gates, advisory output, and formal human decisions.
3. Do not present synthetic data, procedural 3D, or local provider smoke tests as verified customer facts or production readiness.
4. Prefer a focused issue and a small, reviewable change.

## Local checks

Run the checks that match your change. A complete V1 gate is:

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

UI changes should also be reviewed at 1920x1080 with no horizontal overflow or product console errors.

## Pull requests

- Explain the user problem and the chosen boundary.
- List the exact validation performed.
- State any simulated, unverified, or unavailable integration honestly.
- Never include credentials, `.env` files, databases, uploads, user records, IP addresses, browser user-agent data, or external material archives.

By contributing, you agree that your contribution is licensed under Apache-2.0.
