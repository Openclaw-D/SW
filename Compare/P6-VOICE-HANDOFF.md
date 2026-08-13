# P6 Voice Handoff

更新时间：2026-08-13

## 当前结论

P6 已把未提交的多频道/多焦点三 Agent 候选替换为可上线演进的“单焦点协作会话”，并完成真实 Front 对话接线与只读最终结论投影。一个 thread 任意时刻只有一个 `focusRole`；新 thread 默认 business，risk/leadership 只临时接管，成功 turn 后由服务端自动返回 business。

服务端保留 `GET /projects/{projectId}/conclusion` 只读聚合 API 与非默认入口的报告实现；产品默认界面不再在 TopBar 展开独立大报告。协同区改为三栏：左侧用户与业务 Agent 自由对话，右侧用户与风控 Agent 自由对话，中栏是唯一按 `createdAt + sequence` 沉淀的可追溯协作事实流。没有修改 P5 素材，没有实现登录/认证，没有安装依赖、commit、push、deploy；信用页逻辑未开始。

## 可上报的真实 AI 价值

- 把当前项目、证据白名单、制度当前态、审批只读摘要和最近 40 条协作消息装配成有 hash 的受控上下文。
- business、risk、leadership 在同一 transcript 中按唯一焦点生成结构化辅助答复；服务端保留 provider/model/prompt/input/context/output provenance。
- Provider tool attempt、模型身份不符、越权引用、非法结构和权威声明 fail closed；real 失败不回退 synthetic。
- SQLite 对项目/thread/run 使用复合外键，焦点事件、消息、run-step 和幂等记录不可修改；并发、重启、重放和 lease fencing 有回归证据。
- Agent-only 流程对事实、制度、审批和正式共同审查表保持零写入。
- 左右栏允许不选任何材料、维度或历史条目直接提项目开放问题；历史 Agent 消息和中栏共享项可选为引用上下文，绝不作为提交前置条件。
- 中栏只投影材料定位、明确待回复问题、显式确认的协调结论与焦点事件；左右普通探索、假设和草稿不会自动沉淀，也不会写入正式事实或审批链。
- 中栏顶部只显示六维 grade 色、短名称、`MM-DD HH:mm` 更新时间与待回复摘要；全局风险不作为第七维，状态带也不替代左侧导航。

这些能力减少的是材料梳理、争点汇总、补件提示和协作追踪成本，不是自动授信、自动拒绝、风险预测模型或对人工判断的替代。

## 人工确认边界

- 全部 Agent 输出固定 `advisoryOnly=true`；real 输出也只是 `provider_generated_unverified`。
- evidence、FactVersion、评分、confidence、PolicyResult、hard gate、approval 和正式 `review_events` 仍只能由既有人工/服务端权威链改变。
- thread `reject` 只表示本次协作结束，不表示项目正式拒绝。
- `X-Compare-Role` 仅是隔离本机 simulated principal，不是登录、认证、用户身份或生产 RBAC。

## 验收证据

- 首次 P6 `compileall`：通过。
- Agent 专项：`79 passed`；Back 全套：`449 passed`；Front 全套：`180 passed`；Front 聚焦接线组 `41 passed`，typecheck、vinext build 与 compileall 通过。Back 仅 1 条既有 Starlette/httpx 弃用警告。
- 覆盖：v7→v8 migration/restart、双连接并发、同 key 不同 payload/operation/thread 冲突、失败后新 key、过期 lease fencing、复合 FK、最近 40 条、append-only focus events、零权威写、统一 ErrorEnvelope、OpenAI/GLM tool/model/authority 拒绝和 provenance 一致性。
- 共享 `4317 → 8000` 已从业务输入框真实执行一条脱敏项目 turn：`glm_5_2_coding_plan_cli / glm-5.2`、`provider_generated_unverified`、`advisory-only`，input/output 为 `2853 / 896` tokens、费用记录 `0.036665 USD`、permission denial 0、validation failure 0。刷新后消息与 provenance 可恢复，中栏为 13 项且不含用户普通草稿；SQLite 正式 `review_events` 仍为原有 11 条。
- 真实 UI 还覆盖三栏、六维非导航状态带、5 条待回复项、1 条焦点事件、全部来源标识、短时间戳、Agent 历史可选引用与取消、两个输入框无强制引用、刷新后 console 0 error/warning 和横向 overflow 0。应用内浏览器设置物理 `1920×1080` 后受 Windows `devicePixelRatio=1.46` 影响，CSS 视口为 `1315×739`；不把它伪写成 CSS 1920 实测。

## 未完成与发布边界

- 当前单焦点 v3 已在本机通过 CLI 做真实调用与共享 UI smoke；这只证明 invocation、provenance、用量与失败关闭路径，不证明内容质量、外部网络核验、生产认证、SLA 或生产发布。
- 未完成可信 principal、项目成员关系、多租户、生产隐私审计、监控/SLA、预算与生产部署。
- 已接业务/风控自由对话与中栏共享投影；领导不是第三个普通聊天窗口，后续不得恢复多频道 ACL、双焦点或把中栏改成无来源的混合 timeline。
- 后续信用页逻辑与前后端联调另行立项。

## Git 与共享工作区

- 本交接文件随 P6 受控本地 Git 收束；是否推送仍须另行明确授权。
- 保留所有无关工作区改动，尤其 Front/P5 图片、组件与运行时资产；未 reset/clean/覆盖。
- 如后续获 Git 授权，必须重新做精确 P6 scope、敏感信息与 staged diff 检查。
