# R3 Provider Replay Report

Overall Gate: **PASS**

This report replays caller-supplied R3 raw `MaterialIntelligenceResult` payloads through the production real-mode adapter/Gateway/recorder seam. The transport is a mock direct-provider seam: it performs no external network call and makes no semantic repair.

Source-result provenance remains `codex_isolated_blind_eval_v3`, `isSimulated=true`, `notAProviderCall=true`. The adapted real-mode gateway truth is only a production contract projection and is not evidence of a real provider API call.

Canonical input hash: `sha256(utf8(canonical-json(formal ModelGatewayRequest without inputHash)))`.

| Case | Carrier | Gate | Anchors / locators | First / replay calls | Record redacted | FactVersion writes | Failure reasons |
| --- | --- | --- | ---: | ---: | --- | ---: | --- |
| image-equipment-overview | image | PASS | 2 / 2 | 1 / 0 | True | 0 | none |
| pdf-purchase-contract | pdf | PASS | 6 / 6 | 1 / 0 | True | 0 | none |
| excel-operations | excel | PASS | 7 / 7 | 1 / 0 | True | 0 | none |

## Source-run telemetry

- Source run: `P5-BlindEval-R3` by `codex_isolated_blind_eval_v3`.
- Is an external provider call: `False`.
- Source FactVersion writes: `0`.
- Elapsed target met: `False`; absolute stop met: `True`.
- A missed source-generation target is reported separately and does not change the provider-ownership replay Gate.
