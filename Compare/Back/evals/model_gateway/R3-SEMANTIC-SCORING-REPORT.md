# P5 ModelGateway R3 Semantic Scoring Report

- semantic rubric: `blind-eval-rubric-v2`（threshold 未变）
- semantic Gate: **PASS**
- ProviderReplay Gate: **PASS**（3/3 production wrapper replay）
- finalDecision: **PASS**
- R3 raw results are synthetic/advisory-only/not a real external provider call; candidates remain subject to human confirmation.

## Semantic/content hard Gates

| Gate | Actual | Threshold | Result |
|---|---:|---:|---|
| `schemaValidRate` | 100.00% | 100% | PASS |
| `materialBindingHashRate` | 100.00% | 100% | PASS |
| `numericCorrectnessRate` | 100.00% | 100% | PASS |
| `unitCorrectnessRate` | 100.00% | 100% | PASS |
| `locatorBindingOpenBoundsRate` | 100.00% | 100% | PASS |
| `carrierLocatorRuleRate` | 100.00% | 100% | PASS |
| `criticalUnresolvedRecallRate` | 100.00% | 100% | PASS |
| `supportedExtraUnresolvedRate` | 100.00% | 100% | PASS |
| `sceneSpecSafetyLinkageRate` | 100.00% | 100% | PASS |
| `truthMetadataRate` | 100.00% | 100% | PASS |
| `unauthorizedFieldCount` | 0 | 0 | PASS |
| `factVersionWrites` | 0 | 0 | PASS |

## Execution/performance Gates

| Gate/metric | Actual | Threshold | Result |
|---|---:|---:|---|
| `telemetryCompletenessRate` | 100.00% | 100% | PASS |
| `retryPolicyComplianceRate` | 100.00% | 100% | PASS |
| `absoluteStopComplianceRate` | 100.00% | 100% | PASS |
| `fieldAccuracyRate` | 92.86% | 85.00% | PASS |
| `minimumCarrierFieldAccuracyRate` | 85.71% | 75.00% | PASS |
| `latencyScore` | 89.30% | 50.00% | PASS |
| `weightedScore` | 92.86% | 85.00% | PASS |

## Per carrier

| Carrier | Fields | Locator targets | Critical unresolved | Supported extras | SceneSpec | Telemetry | Retry | elapsed |
|---|---:|---:|---:|---:|---|---|---|---:|
| excel | 6/7 | 6/6 | 0/0 | 0/0 | PASS | PASS | PASS | 47.555s |
| image | 1/1 | 1/1 | 0/0 | 1/1 | PASS | PASS | PASS | 47.555s |
| pdf | 6/6 | 6/6 | 0/0 | 0/0 | PASS | PASS | PASS | 62.912s |

## Gate separation and findings

- Field accuracy: `92.86%`; carrier minimum `85.71%`. Excel omitted project number, so it receives partial field credit rather than a locator hard-Gate penalty.
- Image focal locator exactly reuses the controlled region: targetCoverage=100%, IoU=100%. PDF page/text-layer bbox and Excel sheet/range were independently opened against the originals.
- Raw inputHash and gateway envelope are excluded from semantic penalties. ProviderReplay independently proves canonical binding, semantic digest, wrapper projection and redacted record for 3/3 cases.
- ProviderReplay: kind=`production-real-mode-mock-direct-adapter-replay`, externalNetworkCalls=0, realExternalProviderCall=false, FactVersionWrites=0.
- `local_input_selection_error`: count=1, allExcludedFromOutput=true; classified as evaluator flow finding, provider retry impact=0.
- Total elapsed `282.735s`: above 180s target but below 300s absolute ceiling. Latency remains partial; absolute-stop Gate passes.
- weightedScore: `92.86%`; finalDecision: **PASS**.

## Authority boundary

- No scoreGrade, decisionGrade, confidence or hard gate was used as an extraction answer.
- Unauthorized authority fields=0 and FactVersionWrites=0.
- ProviderReplay is a mock-direct production seam replay, not a real external provider API call.
