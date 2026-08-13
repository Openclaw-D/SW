# P5 ModelGateway 离线评测

本目录只承载 `P5-MG-EvalRelease` 的离线、脱敏、合成评测，不被生产应用导入，不注册路由，不写 FactVersion、评分、decision、confidence、hard gate、审批或人工确认状态。

## 数据隔离

- `data/public_cases.json`：允许进入 fake provider 的 24 项标准 synthetic 输入；其中 6 项分别代表 6 个行业的前置 smoke Gate。
- `data/hidden/golden_truth.json`：回包后计分用的 hidden golden truth。`PublicEvalCase` 类型不含 truth 字段，runner 还会检查 provider 收到的序列化输入中没有 `expectedFields`、`goldenTruth` 或 `hiddenTruth`。
- 每个 case 只评测一份受控代表材料。runner 的 30 次调用由 6 次 smoke + 24 次标准 fake 调用组成，不读取或调用 1344 份原件。

所有数据都固定标记 `isSimulated=true`、`dataStatus=synthetic_demo`，并带 `source` 与 `disclaimer`。fake 输出是 `candidate`，不是权威事实；评测层没有 repository、route 或人工确认写入口。

## 指标与韧性

发布 Gate 要求以下离线指标全部为 `1.0`：字段准确性、locator 有效性、schema 通过率、SceneSpec 安全率、candidate/人工确认隔离率，以及失败降级率。

`resilience.py` 是独立夹具层，覆盖 timeout、最多 3 次的有限 retry、滑动窗口 rate limit、budget ceiling、circuit breaker 与 recovery。所有不可用、超时、限流、预算和熔断结果都显式要求人工复核，不伪造成完成或拒绝结果。

## 运行

从 `Compare/Back` 执行：

```powershell
..\..\Back\.venv\Scripts\python.exe -m evals.model_gateway
..\..\Back\.venv\Scripts\python.exe -m pytest -q tests\evals
```

`data/live_eval_policy.json` 默认且当前固定关闭真实 provider，调用数和预算均为 0。任何真实调用都必须由独立授权任务显式启用，提供正数 `maxCalls`、正数 `budgetCeilingUnits` 和确认值，并单独报告实际成本；本离线 runner 即使看到启用配置也会拒绝运行，避免 synthetic 与真实结果混淆。
