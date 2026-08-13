# AI Assist frozen contract

This C0 contract freezes a future information-processing assist surface at `POST /api/v1/projects/{projectId}/ai/assist`. C0 itself does not register the route, call a model, or implement a provider.

AI Assist may produce traceable material summaries, evidence-gap questions, review-text drafts, and indicator explanations. Every result is `advisoryOnly: true`. Humans and the existing authoritative chain retain final control of facts, risk, policy, and approval.

It may never create, modify, or replace a `FactVersion`, fact value, evidence/material/locator, `scoreGrade`, `decisionGrade`, confidence, policy/hard-gate result, approval state, or approval transition. Missing material, version conflict, or unverifiable input produces `needs_review`, an evidence gap, or a stable error—not automatic rejection or block. Provider failure is an error, not a fabricated successful downgrade.

## Frozen objects

| Object | Key contract |
| --- | --- |
| `AiAssistRequest` | Project, task type, actor, instruction, evidence targets, fact/policy IDs, context version, and locale; instruction is 1–4000 characters; 1–50 nonduplicate targets |
| `AiAssistContext` | Read-only project/version-scoped evidence, fact, and policy items; C0 accepts only de-identified simulated context |
| `AiAssistResult` | Task, status, advisory flag, summary, observations, questions, draft, citations, model info, input hash, schema, simulation flag, and disclaimer; no authoritative field |
| `AiAssistCitation` | Stable `evidenceRef`, dimension, review target, and fact-version tuple only; it does not copy a locator |
| `AiAssistProviderPort` | Provider-neutral async `assist(request, context) -> result`; no SDK, configuration, credential, or core-state dependency |

Fixed task types are `material_summary`, `evidence_gap_questions`, `review_draft`, and `indicator_explanation`. `completed` needs model information and at least one valid citation; `review_draft` also needs draft text. `needs_review` contains observations or missing-material questions. `unavailable` contains only an explanation and no fabricated observations, drafts, citations, or model metadata.

Stable errors are `ai_disabled`, `provider_unavailable`, `provider_timeout`, `invalid_model_output`, `context_version_conflict`, and `evidence_context_invalid`.

## Required caller sequence

1. Build a read-only context from one project and one `contextVersion`, without exposing credentials.
2. Validate the request/context relationship; stop on project, version, evidence, fact, or policy mismatch.
3. Invoke `AiAssistProviderPort.assist`.
4. Parse provider output through Pydantic; map invalid output to `invalid_model_output` without guessing repairs.
5. Cross-validate result task type and every citation tuple against the request.
6. Return temporary advisory text only; do not write fact, score, policy, approval, or evidence-core state.

The sample identifiers and Chinese locale values in the historical fixtures are de-identified contract examples, not a real model call or a provider claim. Future provider work requires an independent review of credentials, process isolation, timeout, log redaction, and failure containment.
