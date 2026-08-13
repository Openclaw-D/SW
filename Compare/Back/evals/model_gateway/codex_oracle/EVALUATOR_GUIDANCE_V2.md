# P5-MG BlindEval Evaluator Guidance v2

This is a design proposal for a future v2 evaluation. It does not rescore or
alter the formal v1 blind run. The v1 `blind_run/` files and
`BLIND-EVAL-SCORING-REPORT.{md,json}` remain immutable evidence of the first
attempt and its `FAIL` decision. The exact v1 prompt bytes are retained in
`prompt_template_v1.snapshot.md`; its SHA-256 must equal the v1 report's frozen
`promptSha256`.

## Scientific intent

The v2 rubric should preserve strict semantic and authority boundaries while
removing two brittle equality assumptions:

1. an image locator is a spatial prediction, not a canonical serialization;
2. an honest unresolved set may contain additional evidence-backed review
   questions beyond the Oracle's minimum critical set.

The model input must still exclude the Oracle output, golden values and scoring
rubric. Freeze the v2 prompt before the run. For the blind evaluation binding,
compute `inputHash = SHA256(promptV2Bytes || 0x00 || materialBytes)` and load the
Oracle/golden only after all case outputs and telemetry are sealed.

## Candidate semantic granularity

- A candidate passes only when the material entails its stated granularity.
- A visually supported generic category must not be expanded to a subtype,
  manufacturer, model, ownership or operating-state claim.
- More-specific wording is not treated as a synonym when the finer distinction
  is not visibly supported. This remains a field-accuracy failure even if the
  guess is plausible.
- Filenames, labels and manifest descriptions are not semantic answer sources.
  Authorized manifest regions may guide location only.

## Image locator rubric

Keep material/version/hash binding, openability and normalized bounds as 100%
hard Gates. Replace coordinate-by-coordinate bbox equality with semantic target
coverage:

- `intersection = area(predictedBBox ∩ referenceTargetBBox)`
- `targetCoverage = intersection / area(referenceTargetBBox)`
- `IoU = intersection / area(predictedBBox ∪ referenceTargetBBox)`
- a locator passes when it is openable, finite, in bounds, bound to the exact
  material/version/hash, and either reuses the matching controlled region or
  satisfies both `targetCoverage >= 0.80` and `IoU >= 0.50`;
- score focal-object and caption targets separately and map them by semantic
  role/candidate linkage, not by list position;
- an oversized whole-image box cannot pass merely by containing the target,
  because it will fail the IoU threshold;
- exact reuse of a matching manifest `focalArea` or controlled `captionRegion`
  is preferred and receives full locator credit, but literal float equality is
  not the only valid geometric outcome when no controlled region exists.

Excel sheet/range and PDF page/text-anchor remain exact. PDF bbox evaluation may
adopt the same overlap rule only in a separately frozen future rubric with
rendering-normalization evidence; v2 should not silently change it.

## Unresolved honesty rubric

Do not compare the returned unresolved set with the Oracle by exact set
equality. Split the Gate into two auditable rates:

- `criticalUnresolvedRecallRate = returned critical Oracle items / critical
  Oracle items`; required value is 100% when critical items exist;
- `supportedExtraUnresolvedRate = evidence-supported extra items / all extra
  items`; required value is 100%, with an empty-extra set defined as 100%.

An extra unresolved item is supported only when it:

- uses an allowed unresolved kind and `requiresHumanReview=true`;
- asks a specific, reviewable question and gives a verifiable reason;
- references an existing SourceAnchor bound to the same material/version/hash;
- points to an openable region relevant to the unreadable or ambiguous detail;
- does not smuggle a guessed value, rejection, hard gate or authority decision
  into the question or reason.

Therefore evidence-backed questions about an unreadable manufacturer, model or
nameplate are honest caution, not false positives. Unsupported or generic
boilerplate extras fail `supportedExtraUnresolvedRate`.

## Per-case telemetry and retry contract

Telemetry coverage remains a 100% hard Gate. Seal one record per case with:

| Field | Rule |
| --- | --- |
| `caseId`, `carrier` | Must bind the submitted case. |
| `startedAt`, `finishedAt`, `elapsedMs` | Monotonic, complete, and attributable to this case. |
| `attemptCount` | `1` or `2`; must equal `retryCount + 1`. |
| `retryCount` | `0` or `1`. |
| `retryErrorCodes` | Ordered list; length must equal `retryCount`. |
| `terminalStatus` | Explicit success, needs-review, failed, cancelled or unavailable state. |
| `stopReason` | Required when the case does not complete successfully. |

Retry-policy compliance remains a 100% hard Gate:

- at most one retry per case;
- retry only `rate_limited`, `timeout` or `provider_unavailable`;
- local discovery, missing tools/files, render/parse/schema errors, policy
  blocks and cleanup failures are evaluator failures, not provider retries;
- stop on any disallowed code, on a failed retry, on the case deadline, or when
  the remaining run budget cannot support another attempt plus validation;
- preserve the existing 180-second total target and enforce the 300-second
  absolute stop ceiling. Crossing the ceiling or continuing work after a stop
  condition fails execution-policy compliance.

Latency may remain a partial metric below the hard stop ceiling, but missing or
unattributed telemetry, retry-policy violations and ceiling violations cannot
be compensated by field accuracy.

## v2 hard Gates

Require 100% for:

- formal request/output schema validity;
- project/material/version/media/contentHash/inputHash binding;
- numeric and unit correctness for returned expected fields;
- locator material binding, openability, bounds and the frozen carrier-specific
  exact/overlap rule;
- critical unresolved recall and evidence support for every extra unresolved;
- SceneSpec declarative safety and hotspot-to-anchor-to-locator linkage;
- per-case telemetry completeness, retry-policy compliance and absolute stop
  compliance;
- advisory-only/simulated/not-provider truth metadata;
- zero unauthorized authority fields and zero `FactVersion` writes.

Field accuracy, carrier minimums and latency below the absolute ceiling may
retain partial scoring, but no weighted score may override a failed hard Gate.
