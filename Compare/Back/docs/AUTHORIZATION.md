# signal-council authentication and authorization matrix

The runtime principal comes only from the `signal_council_session` HttpOnly,
SameSite=Strict cookie. `X-Compare-Role` is not accepted as identity. Tests may
replace FastAPI dependencies, but the production composition root has no header
or request-body bypass.

| Surface | business | risk | coordinator (`leadership`) |
|---|---|---|---|
| Login, `me`, logout | own session | own session | own session |
| Project list and bound project reads | read | read | read full projection |
| Materials, originals, evidence, policy, conclusion | read | read | read |
| Upload/import/intelligence/candidate confirmation/model gateway/reconstruction writes | write | deny | deny |
| Business corrections and business answers | write | deny | deny |
| Risk questions and risk answers | deny | write | deny |
| Approval transitions | deny | deny | write, still subject to hard gates |
| Shared review and Agent transcript/focus-event reads | read | read | read |
| Create business-focus Agent thread | write | deny | deny |
| Post project group-chat messages | write | write | deny; settings only |
| Execute an Agent turn | route only to `business` or `risk` | same | deny; not an Agent |
| Legacy thread focus transition/control | subject to service rules | subject to service rules | administrative control only |

All project routes additionally require a stored `project_memberships` row.
Agent output remains advisory-only and cannot write facts, evidence, policy,
hard-gate, formal review, or approval authority tables.
