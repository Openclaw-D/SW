# Material Intelligence and SceneSpec frozen contract

C1 freezes the minimal contract from authorised original material through a multimodal provider to review language, precise provenance, and declarative SceneSpec. Contract fixtures are de-identified simulations; C1 originally defined no route, provider, upload reader, cache, or Front wiring. Any current route must continue to obey these authority and validation limits.

The provider can produce only observations, extracted-field candidates, unresolved items, SourceAnchors, and SceneSpec. None is a `FactVersion` and none may write facts, scores, confidence, policy, hard gates, or approvals. Ambiguous, unreadable, or missing material becomes `needs_review` and a human-review question, never automatic rejection or block.

`MaterialIntelligenceRequest` binds nonempty project/material/material-version/context IDs, lowercase SHA-256 content hash, media kind, nonduplicate task goals, locale, classification, and an authorisation reference when classification is `authorized_customer`. Original bytes never appear in ordinary JSON, logs, or examples.

SourceAnchors bind material ID, material version, content hash, and media-specific location: normalized page/bbox/polygon/OCR range for image/PDF; sheet and A1 range for Excel; paragraph/run/rendered-page/bbox for documents; and time/frame/bbox for media. All normalized coordinates remain in `[0,1]`; every observation, candidate, unresolved item, and hotspot references a registered same-result anchor.

SceneSpec is declarative only: enumerated camera presets; finite `box`, `plane`, `marker`, or `label` objects with numeric vectors; and hotspots referencing known object, region, and SourceAnchor IDs. Strict nested Pydantic rejection prohibits `script`, JavaScript, HTML, shader, URL, code, or any executable/external-load field. It is not a Three.js runtime, scan, CAD model, 3DGS, or verified reconstruction.

A completed result has model information plus an observation, candidate, or SceneSpec. `needs_review` has model information, at least one unresolved item, and `requiresHumanReview=true`. `unavailable` has confidence 0 and no fabricated provider output or model metadata. A future harness validates authorisation, version/hash, scope, and canonical input hash before calling a provider; validates returned binding and requested scene goal after parsing; and only then exposes advisory candidates to a human-review UI. Caches never cross project/material boundaries and invalidate on authorisation, classification, hash, or context changes.
