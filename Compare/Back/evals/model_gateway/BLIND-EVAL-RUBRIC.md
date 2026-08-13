# BlindEval Gate Rubric v1（冻结，HOLD）

状态：`HOLD`。本文件只冻结评分规则与 scorer 输入契约；不得读取 `blind_run/`，不得运行最终评分，不产生发布结论。

## 答案来源边界

评分只比较未来显式传入的 `ModelGatewayOutput` 与回包后加载的 hidden truth / Codex offline Oracle：

- 答案字段只来自 `extractedFieldCandidates`；
- 未决诚实性只来自 `unresolvedItems`；
- 定位只来自 `sourceAnchors + locatorBindings` 及独立可打开性探针；
- SceneSpec 只检查声明式安全、对象/anchor/locator 关联；
- `confidence` 仅接受 schema 校验，绝不作为抽取答案或正确性加分；
- `scoreGrade`、`decisionGrade`、hard gate、approval、FactVersion 等权威字段不参与答案，出现即计越权。

scorer 没有路径发现或文件加载函数。未来调用方必须在 BlindEval 完成后，显式构造：

- 每个 case 的 raw `ModelGatewayOutput`；
- `elapsedMs`、重试前错误码序列、`factVersionWrites`；
- 经独立材料读取/定位验证得到的 `openableSourceAnchorIds`；
- 整体 `totalElapsedMs`。

## 必须 100% 的 hard Gate

以下任一不满足即不具备解除 HOLD 后的发布资格：

| 指标 | 冻结阈值 |
| --- | ---: |
| schema valid | 100% |
| projectId / materialId / materialVersionId / mediaKind / contentHash / inputHash 绑定 | 100% |
| 已返回预期数值的数值正确性 | 100% |
| 已返回预期字段的单位正确性 | 100% |
| 所有返回 locator binding 的 exactness | 100% |
| 所有返回 locator 的可打开性 | 100% |
| unresolved 数量、类型与人工复核语义诚实 | 100% |
| SceneSpec 安全、存在性和 hotspot→anchor→locator 关联 | 100% |
| telemetry case 覆盖 | 100% |
| retry policy 合规 | 100% |
| 越权字段 | 0 |
| FactVersion writes | 0 |

数值使用十进制文本等值比较，不用浮点近似容差掩盖错误。locator 比较所有返回 binding 的 anchor ID、材料、版本及 Excel sheet/range、PDF page/bbox/textAnchor、image bbox 等完整规范化结构；只有文件名不算精确定位。

## 允许部分分的指标

部分分不允许覆盖任何 hard Gate：

| 指标 | 权重 | 最低阈值 |
| --- | ---: | ---: |
| 字段准确率（正确值 / 预期字段与意外字段总检查数） | 70% | 总体 85%，每载体至少 75% |
| 性能效率 | 20% | latency score ≥ 50% |
| 重试效率 | 10% | 无重试满分；每 case 最多一次合规重试 |

加权分必须至少 85%。字段缺失只降低字段准确率；一旦返回字段，其数值、单位和 locator 必须完全正确。意外字段进入分母，不能靠多报提高召回。

## 耗时与失败重试

- 总耗时目标 `≤180s`，绝对计分上限 `300s`。
- 载体 p95 目标：image `60s`、PDF `90s`、Excel `90s`、document `90s`、media `120s`；计分上限为各目标的 2 倍。
- 目标内得 100%；目标至上限之间线性降至 50%；超过上限为 0%。
- 每 case 最多重试 1 次，且只允许 `rate_limited / timeout / provider_unavailable`；对其他错误重试或超过一次使 retry policy hard Gate 失败。
- 报告必须分别给出总耗时、各载体 count/p50/p95/max、总重试数与每 case 重试错误码。

## HOLD 语义

`score_blind_submission()` 永远返回：

- `gateState="HOLD"`；
- `finalDecision=null`；
- `finalScoringExecuted=false`。

它只计算冻结阈值下的 `eligibleAfterExplicitUnhold`，不读取 BlindEval 目录，也不代表最终评分已运行。解除 HOLD 必须由 BlindEval 完成后的独立显式 Gate 决定。
