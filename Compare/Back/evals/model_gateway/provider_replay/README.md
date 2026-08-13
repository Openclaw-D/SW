# Provider replay harness

This harness replays a caller-supplied raw `MaterialIntelligenceResult` through
the production `OpenAIResponsesGatewayProvider`, `ModelGatewayOrchestrator` and
`RunRecorder` without network access.

Ownership is deliberately split as follows:

- the model seam returns only the raw material-intelligence result;
- the backend request supplies the canonical `inputHash`;
- the production adapter owns the `ModelGatewayOutput` envelope, including
  copied `sourceAnchors` and derived `locatorBindings`;
- the gateway owns validation, recording and idempotent replay;
- no provider output is an authoritative `FactVersion` or bypasses the human
  confirmation Gate.

There is no file discovery API. Callers must explicitly provide the request,
raw result, redacted provider-input mapping and SQLite path. In particular, this
package does not load blind-run artifacts.
