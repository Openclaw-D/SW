# Single-focus Agent collaboration contract

## Status and boundary

This is a local Back contract for an advisory collaboration session. The default mode is deterministic `synthetic`; an optional locally configured provider path must fail closed and does not establish provider quality, authentication security, SLA, deployment readiness, or decision authority.

At any time, one thread has exactly one server-authoritative `focusRole`: `business`, `risk`, or `leadership`. A new thread starts at `business`; a request body cannot choose another initial role. Business may hand focus to risk or leadership. After a successful risk or leadership turn, the server returns focus to business in the same transaction. Provider failure does not finish a turn or move focus.

There is no dual focus, parallel role context, public channel ACL, model-suggested handoff, or autonomous multi-step coordination. A thread has at most one running run; an expired lease is reclaimed and its old owner cannot submit a result.

`X-Compare-Role` is a simulated local principal only. It is not sign-in, authentication, project membership, or production RBAC and must never be used as an Internet security boundary.

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
| POST | `/projects/{projectId}/agents/threads/{threadId}/focus-transitions` | Current focus principal requests a server focus transition |
| GET | `/projects/{projectId}/agents/threads/{threadId}/focus-events` | Read append-only focus/session events |
| POST | `/projects/{projectId}/agents/threads/{threadId}/turns` | Execute one turn for the server’s current focus role |
| POST | `/projects/{projectId}/agents/threads/{threadId}/controls` | `close`, `reject`, or `reopen` collaboration state |
| GET | `/projects/{projectId}/agents/runs/{runId}` | Read run, one step, error, and provenance |
| GET | `/projects/{projectId}/conclusion` | Read-only projection of formal project state, human/policy gates, and latest advisory output |

`/conclusion` accepts no role header, creates no thread, runs no agent, and writes nothing. It remains a projection even when it shows advice; final conclusions require human confirmation.

## State, concurrency, and output

Explicit transitions are only `business → risk`, `business → leadership`, `risk → business`, and `leadership → business`. The current principal supplies `Idempotency-Key`, `expectedVersion`, and a readable reason. Every create, transition, automatic return, close, rejection, and reopen appends an immutable event.

Every Agent write requires `Idempotency-Key`. Same key plus same operation/payload replays the saved result; same key with different payload, thread, or operation returns `409 idempotency_key_reused`; a different key while a thread has a live run returns `409 agent_run_active`. Failed runs replay their stored failure under the same key; a new key is required to retry.

A provider may return only `replyText`, `observations`, `questions`, `citations`, `scopeStatus`, and `disposition`. It cannot propose role changes, approvals, governance controls, or authoritative outcomes. The server validates project-scoped citations and rejects authority claims. Real-mode failure, absent credentials, timeout, rate limit, CLI error, or invalid output returns explicit `503`; it never falls back to synthetic or writes an Agent reply.

Provenance is consistent across a run, step, and successful message: provider/model/prompt identity; canonical input/context/output hashes; mode; `advisoryOnly`; `isSimulated`; data status; source; and disclaimer. Stable errors include focus mismatch, version conflict, key reuse, active/fenced run, unavailable provider, provider CLI failure, and invalid provider output.

## Verification scope

The Back test suite verifies project isolation, idempotency, lease fencing, append-only records, zero authoritative writes, OpenAPI errors, and provider-boundary rejection paths. It proves local code and contract gates—not content quality, production provider SLA, authentication, production deployment, or automatic decision making.
