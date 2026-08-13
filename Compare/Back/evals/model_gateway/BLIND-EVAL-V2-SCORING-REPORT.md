# P5 ModelGateway BlindEval R2 正式评分报告

- Rubric: `blind-eval-rubric-v2`（冻结后未修改）
- Gate: `UNHELD`（`HOLD` 已显式解除）
- finalDecision: **FAIL**
- 分类：完整脱敏 synthetic、`advisoryOnly=true`、`notAProviderCall=true`；候选仍须人工确认。

## 内容质量与正式契约 Hard Gates

| Gate | 实际 | 阈值 | 结果 |
|---|---:|---:|---|
| `schemaValidRate` | 33.33% | 100% | FAIL |
| `materialBindingHashRate` | 0.00% | 100% | FAIL |
| `numericCorrectnessRate` | 100.00% | 100% | PASS |
| `unitCorrectnessRate` | 100.00% | 100% | PASS |
| `locatorBindingOpenBoundsRate` | 33.33% | 100% | FAIL |
| `carrierLocatorRuleRate` | 7.14% | 100% | FAIL |
| `criticalUnresolvedRecallRate` | 100.00% | 100% | PASS |
| `supportedExtraUnresolvedRate` | 100.00% | 100% | PASS |
| `sceneSpecSafetyLinkageRate` | 33.33% | 100% | FAIL |
| `truthMetadataRate` | 33.33% | 100% | FAIL |
| `unauthorizedFieldCount` | 0 | 0 | PASS |
| `factVersionWrites` | 0 | 0 | PASS |

## 执行、Telemetry 与绝对时间 Hard Gates

| Gate | 实际 | 阈值 | 结果 |
|---|---:|---:|---|
| `telemetryCompletenessRate` | 100.00% | 100% | PASS |
| `retryPolicyComplianceRate` | 100.00% | 100% | PASS |
| `absoluteStopComplianceRate` | 0.00% | 100% | FAIL |

## Partial score

| Metric | 实际 | 阈值 | 结果 |
|---|---:|---:|---|
| `fieldAccuracyRate` | 7.14% | 85.00% | FAIL |
| `minimumCarrierFieldAccuracyRate` | 0.00% | 75.00% | FAIL |
| `latencyScore` | 75.00% | 50.00% | PASS |
| `weightedScore` | 30.00% | 85.00% | FAIL |

## Case 证据

| Case | schema | binding/hash | 字段 | locator targets | unresolved extras | SceneSpec | telemetry | retry | elapsed |
|---|---|---|---:|---:|---:|---|---|---|---:|
| excel | FAIL | FAIL | 0/7 | 0/7 | 0/0 | FAIL | PASS | PASS | 25.169s |
| image | PASS | FAIL | 1/1 | 1/1 | 3/3 | PASS | PASS | PASS | 20.702s |
| pdf | FAIL | FAIL | 0/6 | 0/6 | 0/0 | FAIL | PASS | PASS | 54.204s |

## 正式阻断与诊断

- request schema：3/3 由正式 `ModelGatewayRequest` 解析。output schema：image 1/1；PDF/Excel 因 envelope `sourceAnchors/locatorBindings` 未复述 result anchors 而失败。因此正式 schema rate 为 33.33%，PDF/Excel 内容按 frozen scorer fail-closed。
- binding/hash：三 request/output 把 `inputHash` 设为材料 SHA-256；按 v2 冻结算法重新计算后均不等于 `SHA256(promptV2Bytes || 0x00 || materialBytes)`，故 0/3。
- PDF/Excel 在正式 envelope 中的 locatorBindings 均为 0；hard Gate 证据已足够，未继续扩展 result-only 原件分析。
- image：通用候选“机床类设备”由像素支持；精确复用受控 focalArea；3 个额外 unresolved 均具体、anchor-backed、可打开且经独立语义审计支持。
- telemetry：3/3 可归属，case 耗时 image/pdf/excel 分别为 `20.702s` / `54.204s` / `25.169s`；attempt 均为 1，retry 均为 0。
- absolute ceiling：总耗时 `422.273s` > `300.000s`，run 终态为 failed；Hard Gate FAIL，任何内容分不得补偿。
- artifact hygiene：`_pdf_page.png` 遗留存在=true；这是 evaluator artifact finding，不计作 provider retry。
- weightedScore：`30.00%`；正式判定：**FAIL**。

## 证据边界

- v2 scorer/rubric、R2 sealed 文件、v1 rubric/report/result 均未为本结果修改。
- `scoreGrade`、`decisionGrade`、`confidence`、`hardGate` 未作为抽取答案。
- 未执行 SceneSpec/provider 内容，未写入 FactVersion。
