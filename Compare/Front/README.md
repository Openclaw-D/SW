# Signal Council · 见微 V1 Front

The Front application is the browser side of the local Signal Council · 见微 reference workbench. It presents the 24 isolated, deterministic, de-identified demonstration projects through the Back HTTP contract. It is not a production deployment or a source of real customer, model, or risk facts.

## Behaviour and boundaries

- The project selection, six-dimension review surface, materials, evidence, shared review flow, policy results, and approval projection all use one selected `projectId`.
- The Front defaults to `HttpWorkbenchGateway`. `VITE_COMPARE_GATEWAY=mock` is an explicit local compatibility override, never a silent fallback after HTTP failure.
- A project-scoped original URL is used only when Back reports `originalAccess.available=true`. If the optional external archive is absent, invalid, unimported, or fails integrity checks, the UI shows an honest unavailable state.
- `SceneSpec`, GLB, OCR, locators, and model output are Back-derived artifacts. They are not source materials, verified images, Office parsing, or real reconstruction output.
- AI messages and candidates are advisory-only. Formal corrections, risk determinations, policy outcomes, and approvals remain Back-authoritative and require human action.
- Scores, decision grade, confidence, evidence, and hard gates remain distinct. Six dimensions are equal 0–100 scores and a higher score is better. Missing material triggers lower confidence or manual review, not automatic rejection.

## Local development

Use Node.js `>=22.13.0` and `npm.cmd` on Windows. From `Compare/Front`:

```powershell
npm.cmd ci
npm.cmd run dev
```

The standard API base is `http://127.0.0.1:8000/api/v1`. For the combined local reference run, follow [../DEPLOYMENT.md](../DEPLOYMENT.md) and start with synthetic agent mode.

## Verification

Run the project’s current Front checks from `Compare/Front`:

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

The current V1 Front gate is `201/201` tests, typecheck, and build passed. The bilingual UI also passed its 1920×1080 acceptance gate. These results verify the local reference UI only; they do not establish production deployment, real-provider behavior, real customer material handling, model quality, or statistical validation.

## Integration

Components depend on `src/gateway/workbenchGateway.ts`; components must not issue direct `fetch` calls, compose Back URLs, or invent a second domain model. The full request, response, error, cancellation, idempotency, and evidence-resolution contract is in [P02-INTEGRATION.md](P02-INTEGRATION.md). Static reference-image attribution is in [public/reference-images/SOURCES.md](public/reference-images/SOURCES.md).

## Historical records

Any remaining P2–P6 names in test fixtures and historical documents are engineering-history identifiers. They are not public version labels; the public release name is V1.
