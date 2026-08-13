# Optional local GLM CLI provider boundary

This document describes an optional local provider boundary for the single-focus advisory collaboration contract. The public V1 default is deterministic `synthetic`; an explicitly configured `real` local CLI mode fails closed. It does not make the API external A2A, does not prove model content quality, authentication security, provider SLA, production deployment, or automatic decision authority.

The current API is internal REST, not an external A2A protocol: it has no Agent Card, `A2A-Version`, JSON-RPC, Task/Artifact, or `contextId` surface. A provider may produce advisory text only and cannot write a formal review event, fact, evidence, score, confidence, policy outcome, hard gate, or approval.

If real mode is explicitly selected, the local CLI must be prepared outside the repository, receive no credentials in logs or request payloads, use the exact configured model identity, run without tools/MCP/browser/session state, have strict input/path/command validation, and return an explicit provider error on absent credential, timeout, invalid output, or identity mismatch. It never falls back to synthetic after a provider failure.

Any local smoke proves only invocation provenance and failure boundaries for that one de-identified local run. It must not be presented as a production provider, external API, content-quality, or SLA verification.
