# P5 ModelGateway BlindEval 正式评分报告

- Rubric: `blind-eval-rubric-v1`（threshold 未修改）
- Gate: `UNHELD`（冻结态 `HOLD` 已由用户显式解除）
- finalDecision: **FAIL**
- 分类：完整脱敏 synthetic、`advisoryOnly=true`、`notAProviderCall=true`；候选不是权威事实，仍须人工确认。
- 答案来源仅为 candidates / unresolved / locators / SceneSpec；`scoreGrade`、`decisionGrade`、`confidence`、`hardGate` 未作为答案。

## Hard Gates

| Gate | 实际 | 冻结阈值 | 结果 |
|---|---:|---:|---|
| `schemaValidRate` | 100.00% | 100% | PASS |
| `materialBindingHashRate` | 100.00% | 100% | PASS |
| `numericCorrectnessRate` | 100.00% | 100% | PASS |
| `unitCorrectnessRate` | 100.00% | 100% | PASS |
| `locatorExactnessRate` | 77.78% | 100% | FAIL |
| `locatorOpenabilityRate` | 100.00% | 100% | PASS |
| `unresolvedHonestyRate` | 66.67% | 100% | FAIL |
| `sceneSpecSafetyLinkageRate` | 100.00% | 100% | PASS |
| `telemetryCompletenessRate` | 0.00% | 100% | FAIL |
| `retryPolicyComplianceRate` | 0.00% | 100% | FAIL |
| `unauthorizedFieldCount` | 0 | 0 | PASS |
| `factVersionWrites` | 0 | 0 | PASS |

## Partial metrics

| Metric | 实际 | 冻结阈值 | 结果 |
|---|---:|---:|---|
| `fieldAccuracyRate` | 90.91% | 85.00% | PASS |
| `minimumCarrierFieldAccuracyRate` | 0.00% | 75.00% | FAIL |
| `latencyScore` | 63.75% | 50.00% | PASS |
| `weightedScore` | 76.39% | 85.00% | FAIL |

## 每载体

| 载体 | 字段 | 数值 | 单位 | locator exact/openable | unresolved | SceneSpec | 耗时 | retry* |
|---|---:|---:|---:|---:|---|---|---:|---:|
| excel | 100.00% | 100.00% | 100.00% | 100.00%/100.00% | PASS | PASS | 102.000s | 3 |
| image | 0.00% | N/A | 100.00% | 0.00%/100.00% | FAIL | PASS | 96.000s | 3 |
| pdf | 100.00% | 100.00% | 100.00% | 100.00%/100.00% | PASS | PASS | 105.000s | 2 |

## 评分结论与阻断

- 字段：`10/11`，总准确率 `90.91%`。image 采用既有 Oracle 的“数控加工设备”作为隐藏答案并仅做 field-key 别名适配；blind 候选“车铣复合中心”不按 confidence 或文本合理性放宽，故 image 为 0/1。
- locator：exact `14/18`，openable `18/18`。PDF/Excel 与源材料精确区域一致；image 的 4 个 bbox 均可打开，但均不等于既有 Oracle 的 focal/caption 精确区域。
- unresolved：`66.67%`；image 多报 `ambiguous_content`，与冻结 Oracle 的空 unresolved 集合不一致。
- 耗时：总计 `782.232s`，超过 300s ceiling；冻结 latencyScore 仍按总耗时和各载体分量平均，结果 `63.75%`。
- 失败/重试：`8/8`。原始 metrics 没有逐 case 归属和 provider error code；不得伪装为有限 retry，故 telemetry 与 retry policy hard Gate 均失败。
- `retry*` 为保持全局 8 次计数而进行的保守确定性分摊，不是原始 metrics 的逐载体事实。
- 越权字段：`0`；FactVersionWrites：`0`。两项均满足零容忍。
- Hard Gate 阻断：`locatorExactnessRate`, `unresolvedHonestyRate`, `telemetryCompletenessRate`, `retryPolicyComplianceRate`。
- Partial 阻断：`minimumCarrierFieldAccuracyRate`, `weightedScore`。
- 总分（frozen weightedScore）：`76.39%`；正式判定：**FAIL**。

## 证据边界

- schema：3/3 request、3/3 output 由正式 Pydantic contract 解析。
- hash：prompt、3 个计分载体的 contentHash 与 `sha256(promptBytes || 0x00 || materialBytes)` inputHash 已从原始字节重算；scene 仅作为受控 declarative 关联材料，不进入独立答案 case。
- SceneSpec：仅检查 declarative 安全键和 hotspot→sourceAnchor linkage；不执行 provider/scene 内容。
- 本报告没有修改 BlindEval 产物、生产 contracts/routes/provider/Front，也没有把候选写入 FactVersion。
