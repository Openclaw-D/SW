# Lightweight project group-chat and Agent-routing contract

## Status and boundary

This is a local Back contract for an advisory collaboration session. The default mode is deterministic `synthetic`; an optional locally configured provider path must fail closed and does not establish provider quality, authentication security, SLA, deployment readiness, or decision authority.

The current optional `glm_cli` real path invokes the exact model ID `glm-5.3[1m]` and records `glm_5_3_coding_plan_cli` as its provider identity. It does not use a mutable Claude model alias. The CLI result must report exactly one `modelUsage` key equal to `glm-5.3[1m]`; the former `glm-5.2` identity, missing telemetry, extra identities, and prefixed or suffixed proxies are rejected before an Agent reply is stored.

The shared thread is a natural chronological group chat for the authenticated `business` and `risk` participants. A human message does not trigger an Agent by itself. An explicit `targetAgentRole` may only be `business` or `risk`; `leadership` is a settings/administration principal and is neither a routable Agent nor a chat participant.

New group-chat clients first persist the human message, then optionally start a turn with the matching `sourceMessageId`. If the provider fails, the human message remains and no Agent reply is fabricated. A thread has at most one running Agent run; normal human messages may continue while that run is active. There is no public channel ACL, model-suggested handoff, or autonomous multi-step coordination. The existing `focusRole` and focus-transition routes remain a compatibility/control surface, not the normal chat router.

The runtime principal comes only from the authenticated `signal_council_session` and a stored project membership. `X-Compare-Role` is ignored by production composition and cannot select or change a role; tests construct principals only through FastAPI dependency overrides.

## Authority boundary

Agent records contain only advisory messages, focus events, and run provenance. Every output has `advisoryOnly=true`; no agent route can write `fact_versions`, evidence/SourceAnchor/material versions, policy results, scores, confidence, hard gates, approval states/transitions, or formal `review_events`.

`reject` ends only a collaboration thread with status `rejected`; it is not a project rejection or approval decision. A human must validate, edit when needed, and explicitly call an existing formal API before advisory text reaches an authoritative chain.

## Public HTTP surface

All routes are below `/api/v1`:

| Method | Path | Meaning |
| --- | --- | --- |
| POST | `/projects/{projectId}/agents/threads` | Create a `focusRole=business` thread |
| GET | `/projects/{projectId}/agents/threads/{threadId}` | Read thread state and version |
| GET | `/projects/{projectId}/agents/threads/{threadId}/messages` | Read the shared transcript with sequence pagination |
| POST | `/projects/{projectId}/agents/threads/{threadId}/messages` | Persist one authenticated human message; never triggers an Agent |
| POST | `/projects/{projectId}/agents/threads/{threadId}/focus-transitions` | Current focus principal requests a server focus transition |
| GET | `/projects/{projectId}/agents/threads/{threadId}/focus-events` | Read append-only focus/session events |
| POST | `/projects/{projectId}/agents/threads/{threadId}/turns` | Execute one advisory turn for explicit `targetAgentRole` and `sourceMessageId` |
| POST | `/projects/{projectId}/agents/threads/{threadId}/controls` | `close`, `reject`, or `reopen` collaboration state |
| GET | `/projects/{projectId}/agents/runs/{runId}` | Read run, one step, error, and provenance |
| GET | `/projects/{projectId}/conclusion` | Read-only projection of formal project state, human/policy gates, and latest advisory output |

`/conclusion` accepts no role header, creates no thread, runs no agent, and writes nothing. It remains a projection even when it shows advice; final conclusions require human confirmation.

## State, concurrency, and output

Human messages and Agent turns use separate idempotency records. A human message has `runId=null`; it does not create a hidden run or mutate formal authority. A routed turn verifies that `sourceMessageId` is the same-content human message authored by the authenticated principal, while its Agent reply carries the selected `business` or `risk` target role. The settings principal can read the auditable thread but cannot post a message or execute an Agent turn.

Every Agent write requires `Idempotency-Key`. Same key plus same operation/payload replays the saved result; same key with different payload, thread, or operation returns `409 idempotency_key_reused`; a different key while a thread has a live run returns `409 agent_run_active`. Failed runs replay their stored failure under the same key; a new key is required to retry.

A provider may return only `replyText`, `observations`, `questions`, `citations`, `scopeStatus`, and `disposition`. It cannot propose role changes, approvals, governance controls, or authoritative outcomes. The server validates project-scoped citations and rejects authority claims. Real-mode failure, absent credentials, timeout, rate limit, CLI error, or invalid output returns explicit `503`; it never falls back to synthetic or writes an Agent reply.

Provenance is consistent across a run, step, and successful Agent message: provider/model/prompt identity; canonical input/context/output hashes; mode; `advisoryOnly`; `isSimulated`; data status; source; and disclaimer. Stable errors include source-message mismatch, version conflict, key reuse, active/fenced run, unavailable provider, provider CLI failure, and invalid provider output.

## Verification scope

The Back test suite verifies authenticated role binding, project isolation, idempotency, lease fencing, append-only records, zero authoritative writes, OpenAPI errors, and provider-boundary rejection paths. It proves local code and intranet Demo contract gates—not content quality, public identity lifecycle, production provider SLA, production deployment, or automatic decision making.
