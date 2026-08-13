# P6 单焦点协作 Eval

本目录是单焦点 Agent 协作的固定、脱敏、离线流程与安全评测基线。它不注册路由、不读取 `runtime/`、不依赖 P5 材料包，也不被生产应用导入。

## 评什么

- business、risk、leadership 的辅助职责；
- 焦点切换只能产生于服务端事件，risk/leadership 成功后返回 business；
- citation 必须属于当前 case 的 allowlist；
- 缺件只能进入补件或人工复核，不自动拒绝；
- hard gate、风险否决和审批不变量不能被 Agent 覆盖；
- Agent-only 流程对 `fact_versions`、`policy_results`、`approval_states`、`approval_transitions`、`review_events` 保持零写入；
- synthetic 的 `isSimulated/dataStatus/disclaimer/advisoryOnly` 真实性；
- real provider 失败必须显式失败，不生成回复、不落消息，也不回落 synthetic。

`fixtures/baseline-v2.json` 是冻结的脱敏单焦点 case 集，schema 为 `compare-agent-communication-eval-v2`。`baseline.py` 只读取 observation 并判定契约，可供 synthetic、mock real 或后续经授权的 provider 使用同一套 Gate。完整 observation 必须包含焦点事件和权威表写入前后差量，缺失证据本身会导致评测失败。

## 明确不评什么

本基线不是模型内容智识、融资判断正确率、事实抽取准确率、风险预测能力、人工审批质量或真实 provider 排名评测。synthetic 通过只表示确定性流程符合当前安全契约，不能据此宣称模型具有真实智识能力。

## 运行

从 `Compare/Back` 执行：

```powershell
..\..\Back\.venv\Scripts\python.exe -m pytest -q tests\agent_communication\test_eval_baseline.py
..\..\Back\.venv\Scripts\python.exe -m compileall -q evals\agent_communication tests\agent_communication
```
