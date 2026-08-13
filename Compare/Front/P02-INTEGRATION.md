# Front-to-Back integration contract

This document started as the handoff boundary between the original Front and Back checkpoints. It now records the live V1 integration contract. Components depend only on `src/gateway/workbenchGateway.ts`; an HTTP gateway adapter must not make components call `fetch`, compose Back URLs, or know Back routes directly.

## Material and candidate integration

`Material` may contain `businessPath`, `folderPath`, and `role`. The Front shows only non-derived Excel, PDF, DOCX, image, and `mediaKind=video` items as originals, grouped by the canonical Chinese business folders `基本证照` (credentials), `经营证明` (operating evidence), `现场照片` (site photographs), `增信` (credit enhancement), and `租赁标的` (leased assets). The Chinese folder terms are canonical data labels, not untranslated UI guidance.

`SceneSpec`, GLB, pseudo-panorama descriptions, OCR, locators, and model results are derived artifacts and must not enter the original-material count. DOCX is retained and opened as a controlled original; V1 does not promise online Office parsing. In HTTP mode, `originalUrl` is project-scoped:

```text
GET /projects/{projectId}/materials/{materialId}/original
```

It is usable only when `originalAccess.available=true`. `assetUrl` is legacy-snapshot/mock compatibility only. Production and transaction image links remain frozen as `OnsiteAsset.materialId`, `ProductionStage.imageIds`, and `FinancedEquipmentLine.imageId/imageIds/nameplateMaterialId`, each pointing to a same-project `Material.id`. `derivedModelRef` is a derived reference, not a material ID.

| Gateway method | FastAPI route | Constraint |
| --- | --- | --- |
| `preflightMaterialImport` | `POST /projects/{projectId}/materials/imports/preflight` | Authorised external manifest; never returns a raw path |
| `executeMaterialImport` | `POST /projects/{projectId}/materials/imports` | `expectedVersion` plus `Idempotency-Key` |
| `runMaterialIntelligence` | `POST /projects/{projectId}/materials/{materialId}/intelligence` | Human-triggered; strictly checked output; candidates cannot write facts directly |
| `readMaterialIntelligence` | `GET /projects/{projectId}/materials/{materialId}/intelligence/latest` | Latest server result; explicit empty state on not found |
| `confirmMaterialCandidate` | `POST /projects/{projectId}/candidates/{candidateId}/confirm` | Explicit human rationale; creates FactVersion, policy, event, and approval projections |
| `readMaterialSceneSpec` | `GET /projects/{projectId}/materials/{materialId}/scene-spec` | Read-only declarative SceneSpec; explicit empty state when absent |

All writes use the unified envelope/error model, project isolation, `expectedVersion`, and `Idempotency-Key`. `SourceAnchor` never maps `evidenceRefs` by array position: the frozen mapping is `ev-mi-${sourceAnchorId}` and must first verify membership in the server-returned set. A regression test covers unordered multiple anchors.

After confirmation, Front reloads the workbench, common review events, latest policy results, and approval state from Back. It restores confirmed UI from the server `candidate::{candidateId}` event. SceneSpec exposes only enumerated `cameraPreset`, `objects`, and `hotspots` values to controlled rendering; `eval`, `Function`, HTML injection, and model-code execution are forbidden.

## Core data flow

1. `loadProject(projectId)` returns one workbench snapshot: project, six dimensions, materials, evidence, fact versions, corrections, determinations, shared events, and default layout.
2. `readMaterial(projectId, materialId)` returns a material within that project. Missing and cross-project access are explicit 404s; no approximate material is returned.
3. `resolveEvidence(projectId, selectionGroup)` resolves all selected evidence atomically. Excel uses `sheet + range`; PDF and images use page/bbox; media and scenes use time ranges and point IDs.
4. `queryDimensionSeries(request)` distinguishes `available`, `empty`, and `unavailable`.
5. `submitBusinessCorrection` creates a new `FactVersion` and immutable shared event; Back never silently overwrites an original fact.
6. `submitRiskQuestion`, `submitBusinessAnswer`, and `submitRiskAnswer` append shared-chain events. They are `immutable: true`; Front has no delete path.
7. Policy, review-event, and approval reads are Back-authoritative; leadership cannot override a hard gate.

## Gateway and error rules

The Front contract remains in `src/contracts/workbench.ts`; Back Pydantic/OpenAPI owns the HTTP envelope, writes, idempotency, and stable errors. Mapping must be proven by contract tests, not by creating a second synonymous component model.

- `not_found`: project, material, or evidence does not exist.
- `validation`: required field, locator, or content validation failed.
- `conflict`: fact or material version conflict; Front must refresh rather than overwrite.
- `simulated_failure`: mock-gateway demonstration error only; the production FastAPI contract never returns it.

Replaceable reads use `AbortController`; `AbortError` neither updates UI state nor becomes `WorkbenchGatewayError`. Ignore stale results by request sequence/current `projectId`. A dispatched write is not treated as failed merely because the view changes. Same idempotency key plus same body is safe to retry.

On shared-review `version_conflict`, allow one authoritative `review/events` refresh and one new-key retry. Stop after a second conflict or failed refresh and preserve a recoverable error. Material/evidence failures remain local to the material pane and must not replace an already loaded workbench.

## Score and authority boundary

- `scoreGrade`, `decisionGrade`, `confidence`, `evidenceRefs`, and `hardConstraintResults` are separate fields.
- Six dimensions are equally weighted, each 0–100, and a higher score is better.
- Missing material may lower confidence or trigger `manual_review`; it cannot alone derive `block`.
- `SoftRecommendation.advisoryOnly` is literally `true` and cannot override hard results.
- Policy hard constraints are system events; there is no chat-input path for them.

## Acceptance expectations

- Replacing mock with HTTP does not rewrite the page structure; it may change gateway signatures, startup wiring, and dynamic evidence references only.
- Contract tests cover requests, responses, errors, and event sequencing.
- Excel/PDF/PNG locators resolve precisely for the same material version; mismatch is explicit.
- Corrections create a new fact version and shared event; an old concurrent submission returns `conflict`.
- Back failure never silently falls back to `MockWorkbenchGateway` or local success data.
- Network requests only reach the configured approved API and do not disclose material or credentials to third parties.
