# Front HTTP adapter mapping

`Compare/Front` uses `HttpWorkbenchGateway` by default. `VITE_COMPARE_GATEWAY=mock` is an explicit mock override only; HTTP failure never silently falls back to simulated success.

## Transport rules

- API base: `http://127.0.0.1:8000/api/v1`; health is `/health`.
- Success is `{ data, meta, errors: [] }`. `meta` always contains `requestId`, `schemaVersion`, `dataStatus`, `source`, and `disclaimer`. The adapter unwraps `data` and preserves metadata for truthful UI labels.
- Front fields remain camelCase. `isSimulated` is a normal boolean and does not claim real customer data, supplier verification, statistical validation, or model accuracy.
- `404`, `409`, and `422` are enveloped errors. Map category `not_found`, `validation`, and `conflict` to the existing `WorkbenchGatewayError`, preserving stable code, field, and details.
- Network or 5xx failures are transport errors, not mock `simulated_failure`.
- Replaceable reads use `AbortController`; discarded `AbortError` does not alter UI state. Discard stale responses by sequence and current project. A sent write remains in flight across navigation.
- Every write requires `Idempotency-Key` and body `expectedVersion`. The client never increments a version itself.

## Route families

| Front capability | HTTP contract | Essential rule |
| --- | --- | --- |
| Project list and snapshot | `GET /projects`; `GET /projects/{projectId}/workbench` | Project ID drives all later paths; unknown project is explicit 404 |
| Materials | Project-scoped list/read/original routes | Cross-project material reads are explicit 404; original requires valid external binding |
| Evidence | `POST /projects/{projectId}/evidence/resolve` | Submit one complete selection group; success is all located, failure is never partial success |
| Series | `POST /projects/{projectId}/dimensions/{dimensionId}/series/query` | Path/body project and dimension must match; `empty` and `unavailable` are modeled data |
| Corrections and shared review | Project fact/review write routes | Back creates immutable versions/events and validates idempotency |
| Policy and approval | Project policy read and approval read/transition routes | Back is authoritative; a hard-gate block cannot be overridden by any role |

Same key and canonical body replay safely; key reuse with a different body is `409 idempotency_key_reused`; a stale version is `409 version_conflict`. `manual_review` is not rejection. The complete current integration detail is [../../Front/P02-INTEGRATION.md](../../Front/P02-INTEGRATION.md).
