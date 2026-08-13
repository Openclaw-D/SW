# Security Policy

## Supported version

Security fixes are currently evaluated for the latest V1 state on the default branch.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose credentials, local files, uploaded materials, user records, or authorization boundaries.

Use GitHub's private vulnerability reporting feature when it is available for this repository. Include:

- the affected component and version or commit;
- a minimal reproduction that contains no real customer or personal data;
- the expected security boundary;
- the observed impact;
- any safe mitigation you have already tested.

Do not include API keys, tokens, `.env` contents, databases, uploaded documents, personal data, IP addresses, or browser session data in the report.

## V1 deployment boundary

V1 is a local reference workbench. It does not include production authentication, multi-tenant authorization, TLS termination, public-network hardening, managed secret storage, backup and retention policies, or a production privacy program. Do not expose the default local service directly to the public internet.
