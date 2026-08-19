# Roadmap

## 默认单项目脱敏演示（2026-08-16，complete）

默认网站、模块冷启动、真实 HTTP 项目目录、Mock Gateway 和新仓库外运行库均固定为 1 套脱敏演示项目，入口直接进入该项目；三个账号只为该项目建立 3 条 membership。旧 `compare.db` 完整保留，默认改用 `signal-council-demo.db`，不做删除或破坏性裁剪。24 项生成器、外置材料矩阵和 hidden truth/Oracle 继续只服务显式离线回归与评测，不进入默认网站或运行库，也不表述为训练数据。Back `510 passed`、Front `217/217`、typecheck、vinext build 与部署 Preflight 通过。

## GLM-5.3 迁移检查点（2026-08-16，complete）

Compare 的可选真实 A2A provider 已冻结为 `glm_5_3_coding_plan_cli / glm-5.3[1m]`，CLI 直接传精确模型 ID，旧 `glm-5.2` 遥测必须拒绝。隔离真实风控 turn、精确 provenance、正式表零增量、Back provider `34/34` 与 Front `204/204` 已通过。该检查点不扩展 Agent 权限、不改变 synthetic 默认值，也不声称生产 SLA 或模型质量已验证。

## P6 三账号认证、会话与角色权限（2026-08-14，complete）

signal-council 已完成三个固定内网 Demo 账号、HttpOnly 会话、项目成员关系和后端强制 ACL。所有现有项目各绑定 business、risk、coordinator 三个账号；业务、风控与协管共享项目和共同协调链，但角色专属写操作、私有草稿及 Agent 调用隔离。`X-Compare-Role` 不再参与正式 principal 推导，测试只通过 FastAPI dependency override 构造主体。

- Back：SQLite schema v9、PBKDF2 独立 salt、opaque session token/hash、过期/撤销/重复登录策略、幂等 seed/membership 与完整 endpoint 权限矩阵。
- Front：登录恢复、退出、过期处理、账号角色显示、三角色流程投影、同源 `/api/v1` Cookie 请求及受限控件只读状态。
- 发布收束：产品名统一为 `signal-council`；旧 `COMPARE_*` 环境键、磁盘目录和 `%LOCALAPPDATA%\CompareWorkbench` 只作为 V1 无损升级兼容标识保留。
- 公网仍未放行：Demo 初始密码必须轮换，并补 TLS、Secure Cookie、生产身份生命周期、限流/CSRF、进程托管、备份恢复、隐私留存与安全审查。

## 最终结论层与负责人上报视图（2026-08-13，complete）

P6 单焦点后端 Gate 通过后，Compare 已增加一个最小、可运行的只读结论闭环。服务端 `GET /projects/{projectId}/conclusion` 从现有工作台、正式共同审查、制度结果、审批状态和最新单焦点会话生成同一份投影；报告实现保留为非默认入口的回退能力，不在 TopBar 扩张为独立大报告。

- 报告分别呈现全局风险、`scoreGrade`、`decisionGrade`、confidence、六维认定、证据定位、未决项、制度 Gate 和审批状态，不把它们合成一个 AI 结论。
- 最新 Agent 建议保留 role、provider/model/prompt 与 input/context/output hash provenance；无 thread 时显示诚实空态。任何 Agent 内容仍为 advisory-only，报告本身不写事实、证据、制度、正式 review 或审批。
- AI 价值只按当前服务端记录列出已整理关键证据、已显式未决项/追问、可追溯引用、advisory 消息和焦点切换数；只描述减少人工整理、逐项追问和页面切换，不声明自动审批、替代人工、模型准确率、外部网络核验或已实现的时间/利润收益。
- 自动 Gate：Back `449 passed`，Front `180 passed`，Agent 专项 `79 passed`，Front 接线聚焦组 `41 passed`，`compileall`、typecheck、vinext build 和 OpenAPI/只读表计数回归通过。
- 共享 `4317 → 8000` 已执行真实 business turn 并在刷新后恢复 `glm_5_2_coding_plan_cli / glm-5.2` provenance；物理 1920×1080 override 在 Windows `devicePixelRatio=1.46` 下对应 CSS `1315×739`，横向 overflow 为 0、刷新后 console 0 error/warning。不得将该结果改写为 CSS 1920 实测；既有精确 1920×1080 P5 基线与响应式自动守卫仍保持通过。

该层不实现登录/认证，不改变既有审批 API，也不覆盖后续信用页、可信 principal、生产 Provider SLA 或生产发布 Gate。

## P6 单焦点 Agent 协作后端（2026-08-13，complete）

P6 基础 Gate 已把未发布的多频道/多焦点三 Agent 候选替换为一个简单、可审计的单焦点协作会话。后续已将 Front 左右自由对话接到该 API，并以中栏共享投影替换旧 review answer/question 聊天接线。全程未新增登录/认证，也未做生产部署。

```text
new thread（focusRole=business）
  → 服务端显式切换到 risk 或 leadership
  → 当前唯一焦点执行一轮 advisory-only turn
  → 成功后服务端自动返回 business
  → 人工确认后另行调用既有正式 API
```

### P6-1 · 单焦点契约与权威边界（通过）

- thread 只有一个 `focusRole`；删除公开 channel ACL、角色专属 turn、governance version、协调模式、模型 handoff 与多步自动链。
- 新 thread 默认 business；只有服务端 `focus-transitions` 可切焦。risk/leadership 成功后自动返回 business，close/reject 除外。
- `X-Compare-Role` 仍只是本地 simulated principal，不是登录、认证或生产 RBAC。
- Agent 输出和存储全部 `advisoryOnly=true`，对事实、证据、制度、hard gate、审批和正式 review 表零写入。

### P6-2 · SQLite、并发与幂等（通过）

- schema v8 保存 thread/run/唯一 step/message/focus event/idempotency；复合外键阻止跨项目或跨 thread 关联。
- 所有写操作使用 `Idempotency-Key + expectedVersion`；同 key 不同 payload/operation/thread 冲突，失败后新 key 可重试。
- 同一 thread 最多一个 active run；lease 过期自动回收，旧 owner 被 fencing；长 transcript 只装配最近 40 条并保持升序。
- 未发布 v7 多频道候选可启动迁移到 v8，删除虚假 ACL/governance 表并留下 `thread_migrated` 事件。

### P6-3 · Provider 与审计（通过）

- 单次 turn 只有一次 Provider 调用和一个 step；Provider 只产六字段辅助内容，不能切焦或写权威状态。
- OpenAI adapter 显式无 tools，并拒绝 tool item、模型身份不符、越权 citation、非法结构和权威声明。
- GLM CLI v3 adapter 固定无 tools/MCP/Chrome/session，输入路径/命令/二进制 fail closed；CLI 失败保留稳定 `agent_provider_cli_error`。
- run/step/message/turn 的 provider/model/prompt/input/context/output hash、simulation truth、source 与 disclaimer 一致。

### P6-4 · Gate 证据（通过）

- Agent 专项历史 Gate 为 `79 passed`；当前 Back 全套为 `455 passed`，仍仅 1 条既有 Starlette/httpx 弃用警告。
- Front 当前为 `193 passed`，其中单焦点 gateway、三栏 UI、协作流投影与旧布局聚焦组历史 Gate 为 `41 passed`；typecheck 与 vinext build 通过。
- `compileall`、当前 OpenAPI 冻结、SQLite migration/restart/concurrency/idempotency、错误 envelope 与 scope diff 分别验收。

P6 的真实能力是本地、可追踪的辅助协作，不是自动判断或替代人工。当前 Front 左右栏分别承载业务/风控项目级自由对话，引用可选；中栏只沉淀带来源的材料定位、明确问题、显式协调结论和焦点事件。真实本机 GLM-5.2 smoke 证明调用、provenance 与用量路径，但可信身份/项目成员关系、生产审计、内容质量/SLA 与后续信用页逻辑仍为后续独立范围。

## P5-MVP 收敛（2026-08-12）

P5-MVP 已在 P5-DataPack 与 P5-FrontDemo 基础上完成本地纵向集成，并完成 24 套实体原始材料、raw ZIP 上传、默认 v1 原件绑定与重复同包安全导入。未迁移或删除旧默认运行库，未安装依赖、部署、提交或发布。

```text
P5-DataPack + P5-FrontDemo
  ↓ 上传/原件 + 六条材料智能与导入路径接入
P5-MVP HTTP / SQLite / Front 纵向闭环
  ↓ 24×56 实体原件、唯一哈希与浏览器导入实测
P5-Control 本地演示 Gate（通过）
  ↓
后续真实 Provider 小批外调、精确视觉与发布 Gate（未启动）
```

### P5-MVP 已完成范围

- Front 通过既有 gateway 接入 raw ZIP 上传、导入预检/执行、intelligence 运行/最新读取、候选人工确认和 SceneSpec；写入遵守项目隔离、`expectedVersion` 与 `Idempotency-Key`。
- 右侧原材料区展示版本、SHA-256、SourceAnchor、Observation、候选、置信度和 simulated 标记；候选只能由明确人工动作确认，完成后刷新服务端 FactVersion、制度结果、共同事件和审批状态。
- SourceAnchor 与 evidence 使用稳定 ID 映射，不做位置映射；多锚点乱序有回归测试。
- SceneSpec 仍保留为受控派生契约；由于当前 `derivedModelRef/modelPreset` 无法证明与同一设备实拍、型号和配置一一对应，P5 设备审查区不再渲染通用 Canvas，也不在图片原件流程中直显 SceneSpec。
- 24 项每项 56 份材料、分类覆盖、版本、locator、SourceAnchor 和 SceneSpec 由程序化 HTTP/SQLite loop 验证；项目刷新不再生成随机数据。
- 24 项各有 56 个实体业务原件和一个 ZIP；共 504 个 Excel、336 个 PDF、504 张项目级唯一 `2048×1152` PNG。SceneSpec、GLB 和图像 provenance 固定在 `derived/`，不进入原件 manifest。目录与 ZIP 均逐项目低于 100 MiB，上传层同时限制压缩包、解压总量和单原件；全新数据库首次 seed 以 manifest SHA-256 绑定 v1 MaterialVersion，旧库不静默改写。
- 前端仅在选中材料后读取高清原件；图片支持原比例适配、1:1、原尺寸新窗口和 8× 缩放。项目照片预览只裁去源图底部 11.5% 技术页脚并同步重映射 locator，不拉伸内容。PDF 单页、Excel 定位窗口和 MP4 metadata 预载控制笔记本内存占用；GLB 仍不伪称已接 Three.js 或真实重建。

### P5 后续边界（未启动）

- 认证、角色、项目/材料权限、脱敏视图、生产审计、真实外部 Provider 小批实调、OCR/Office、部署、备份恢复和隐私 Gate 仍需独立任务与授权；ProductionWire 的 real mode 已接线，但没有外部调用证据。
- 当前没有真实客户数据或统计模型验证；合成素材、synthetic provider 与声明式场景不得改口为真实事实、真实拍摄或真实三维扫描。
- P5-Control 精制材料包、媒体运行时、模型纵切、可见体验和公开范围 Gate 已通过；核心收敛提交 `449194d` 已推送 `main`，当前未部署。

## P5-MG-EvalRelease（2026-08-12）

本检查点已完成离线评测、ProductionWire、Provider 严格绑定、DataPack v1→v2 历史投影修复与 RuntimeQA。代码链路不再有先前 OpenAPI 断言阻断；发布仍受真实外调、精确视觉复验和 Git 授权约束。

```text
公开 synthetic case（不含答案）
  → 6 行业 smoke：6 项
  → smoke 全指标通过后，24 项标准集
  → provider 回包完成后才加载 hidden golden truth 计分
  → 字段 / locator / schema / SceneSpec / 人工 Gate 隔离
  → timeout / 有限 retry / rate limit / budget / circuit recovery
  → Back + Front + compileall + Git Gate
```

### 已实现并自动验证

- `Back/evals/model_gateway/` 与 `Back/tests/evals/`：24 项合成 case、hidden truth 物理分离、两阶段 runner、deterministic fake、质量评分与失败/恢复夹具；真实调用默认关闭且预算为 0。
- BlindEval v1 `76.3864` **FAIL**、R2 `30` **FAIL** 作为冻结失败基线保留；R3 只提交 `MaterialIntelligenceResult`，语义/性能得分 `92.8596` **PASS**。独立 ProviderReplay 负责生产 envelope、canonical input hash、材料绑定、锚点/locator 投影和脱敏记录，3/3 **PASS**，不对同一职责重复惩罚。
- ProductionWire real mode 已接线：无 key fail-before-read；startup/health/capabilities/seed 0 外调；显式 mock transport 的 real-mode 请求首执行恰好 1 次、幂等 replay 0 次。Provider 对 `contentHash`、材料/版本、`sourceAnchors` 与派生 `locatorBindings` fail closed。
- DataPack v1→v2 当前态投影不改写不可变历史：旧版 `located` locator 在新版本工作台中降为待复核，重新运行 intelligence 和人工确认后才建立 v2 权威链；RuntimeQA **PASS**。
- 24 套本地脱敏模拟包完整性已升级为 24×56、1344 份唯一 hash，逐包低于 100 MiB，并覆盖导入、Range、locator、SceneSpec 和受控 GLB 派生边界。Front 基线为 typecheck、`193/193`、vinext build；审批画布异常增高/抖动已修复，精确 `1920×1080` 页面宽度为 `1920/1920`，设备 line/material、现场十视角和工艺三阶段原件绑定已完成实页复验。旧 36 份材料截图只作为历史证据。

### 进入发布的剩余 Gate

1. 真实 Provider 实调保持独立显式授权：必须提供凭据、正数调用上限与预算、授权脱敏输入、成本记录和失败停止条件；当前无 `OPENAI_API_KEY`，全部证据仅为 offline Codex/fake/mock replay。
2. `Show/`、仓库根目录旧 Front/Back 与旧启动文档、Compare Front artifacts/legacy、`original.html` 和两份研究文档已可恢复地封存到 `C:\Users\22673\Desktop\JW-Archive\P5-Core-Scope-20260812`；P5 收敛提交移除这些公开历史表面，runtime 继续仅本地保留。

## P0 发布目标

用最少代码完成一个可运行、可验证的材料核验工作台闭环。三个检查点属于同一个 P0，严格按顺序推进。

```text
准备闸门
  ↓
P0-1 Front 基线
  ↓ 用户确认页面与交互
P0-2 Adjacent Back
  ↓ 前后端契约冻结
P0-3 Integrated MVP
  ↓ 完整验收
P0 完成
```

## 准备闸门

目标：开始写代码前消除技术路线和复用范围的不确定性。

1. 只读盘点原 `JW/Front`、`JW/Back` 中与 Compare 直接相关的代码。
2. 输出三类清单：直接复用、整理后复用、P0 不复用。
3. 确认目标栈：Front 默认采用 React + TypeScript + Vite；Back 默认采用 FastAPI + Pydantic + pytest。
4. 列出需要安装的生产/开发依赖、无新增依赖替代方案和影响，取得确认后再安装。
5. 锁定 P0-1 的页面草图、模拟数据字段和浏览器验收清单。

产物：复用清单、依赖提案、P0-1 文件级计划。准备闸门不产生业务代码。

### P0-1 · Front 基线

目标：用稳定的模拟数据确认产品形态，不依赖新后端。

#### F1 · 前端视觉基础与可运行全页

目标：以 `assets/compare-p01-low-fi-v1.png` 为基线，先把整套前端页面真实运行起来，锁定页面骨架、间距、颜色、字体和基础组件语言；同时建立与后端解耦的接口层，但不连接真实后端。

- 只在 `Compare/Front` 建立 Sites `vinext + React + TypeScript + Vite` 本地应用、npm lockfile，以及 `dev`、`typecheck`、`test`、`build` 命令；保留 Sites 的 `.openai/hosting.json` 和 Worker-compatible ESM 结构，但 F1 不部署。
- 以 localhost 开发服务和 HMR 作为主要迭代界面；开发期间保持服务运行，组件修改后实时更新，用户通过本地页面连续预览和纠正。
- 建立集中设计变量：黑白灰基础色、六维保留色、风险浅色、字体层级、间距、圆角、边框、阴影、动效时长和主要布局尺寸；禁止在组件中散落重复魔法值。
- 建立标题栏、左侧六维区、中间六维长页面、右侧材料区和底部协同区的完整静态页面；六个维度都保留稳定 section 和基础占位，不只画单一局部。
- 建立通用的按钮、状态标记、面板、分隔线、标签和空状态样式，确定整体为克制的 GPT 式黑白灰视觉，并保留既有风险浅色语义。
- 定义六维、材料、证据 locator、事实版本、业务修正、风控认定、共同审查事件、硬约束、软建议和布局状态的 TypeScript 类型。
- 建立前端 `WorkbenchGateway` 接口与本地 mock 实现；组件只调用接口，不直接拼接 URL 或依赖后端。预留加载项目、读取材料、定位证据、提交业务修正、提交风控问题和读取制度结果等能力。
- F1 中所有内容显式标注为模拟数据或模拟交互；预留接口不等于后端已经接通。

F1 Gate：页面可通过 localhost 独立启动并实时更新，且生产构建通过；三种 PC 分辨率下五大区域比例、字体、间距和颜色通过截图检查；控制台无错误；不访问原 JW 运行时模块或任何后端。F1 通过后，基础视觉不再随意改版，只允许后续功能所需的小范围调整。

#### F2 · 六维内容与导航移植

目标：把原系统六个分页面合并为一个从上到下连续浏览的六维页面，并恢复原六维导航的视觉与状态逻辑。

- 六维名称和顺序固定为：合规、交易、生产、营收、负债、流水。
- 左上角近乎完整移植原 `MiniDimensionDial` 的几何、颜色、半径/等级、图标、高亮、淡化和过渡效果。
- 六维图、左侧 1–6 栏目入口和中间滚动位置共享同一活动维度状态；点击可定位，手动滚动可反向更新导航。
- 将原六个维度详情页的字段、图表、图标、短结论和判断表达迁入对应 section；只做连续页面和新证据结构所需的适配。
- 所有可见内容由统一 mock 案例派生，不在各组件内建立互相矛盾的演示数据。

F2 Gate：六个维度均可连续阅读和准确导航；六维图的样式、高亮及淡化逻辑与原系统基线一致；F1 的布局与视觉基线没有被破坏。

#### F3 · 工作台布局与材料预览交互

目标：让低保真图中的多区域工作台成为可调整、可聚焦的真实前端界面，并完成材料预览的模拟能力。

- 左侧导航支持折叠与恢复；中间和右侧支持拖动调宽、分别全屏、退出全屏和恢复默认比例。
- 右侧提供 Excel、PDF、PNG 等材料列表与模拟预览，支持材料切换、页签状态、独立滚动、加载、空和错误状态。
- 底部协同工作台支持收起、调高和全屏；业务方与风控方两侧角色栏可折叠，中间共同审查链保持可见且只读。
- 主内容、中右分栏和协同工作台统一使用布局状态与 CSS 变量；只持久化布局宽度、面板状态和当前维度。
- 六个维度 section 始终保留稳定 DOM 锚点，不因性能优化破坏导航和后续证据反向定位。

F3 Gate：折叠、调宽、全屏、恢复默认、材料切换和长页面滚动均可操作；在三种 PC 分辨率下不存在失控遮挡或整体横向溢出。

#### F4 · 业务数据与材料证据链

目标：完成中间数据与右侧原始材料的准确双向关系，使页面能够说明每一个判断来自哪里。

- “主体合规”完整展示：原始材料 → AI 识别 → 业务修正 → 风控认定；业务修正先使用明确标注的本地模拟交互。
- 每个模拟业务数据使用稳定 `evidenceRefs`；Excel 使用 sheet/range，PDF 使用 page/bbox 或可验证文本锚点，图片使用归一化 bbox。
- 点击业务数据后自动切换材料并准确高亮证据区域；点击证据可反向定位关联数据。
- 多证据、缺失 locator、定位失败和材料版本不匹配都有明确状态，不得用近似高亮冒充成功。
- 绿色 `✓`、黄色 `?`、紫色 `×` 只表达材料识别状态；证据选中使用独立中性高亮，不能混用风险颜色。
- 其他五维保留已迁移的原详情内容，不伪造尚未建立的完整四阶段材料链路。

F4 Gate：主体合规至少完成一条可复现的正向与反向证据链；异常定位状态可见；所有交互仍通过 mock gateway，不产生隐藏后端依赖。

#### F5 · 协同链、接口冻结与前端验收

目标：补齐业务方、风控方、制度硬约束的前端协同表达，冻结提供给 P02-Back 的接口契约，并验收整个 P01-Front。

- 业务 AI 与风控 AI 分栏呈现；双方正式提交都进入同一条可见、不可直接删除的共同审查链。
- `AI 识别` 作为后台抽取结果展示，不形成第三个对话；制度硬约束作为版本化系统事件展示，也不形成聊天角色。
- 共同链记录事实版本、业务修正、风控追问、待解决问题和制度事件；点击记录同步定位中间数据与右侧证据。
- 硬约束结果与 AI 软建议使用不同数据类型和视觉结构；软建议显示辅助属性和置信度，不能覆盖硬约束。
- 完成 mock gateway 的正常、加载、空、错误和提交失败状态；冻结 P02 所需的请求、响应、错误和事件契约，但不在 P01 内实现真实 API。
- 分别完成类型检查、聚焦测试、生产构建、控制台检查，以及 1440×900、1680×945、1920×1080 浏览器视觉验收。

F5 Gate：整个页面可独立运行，核心交互完整，模拟状态诚实，无隐藏后端依赖；输出接口契约和 P02-Back 接入清单，经用户确认后 P01-Front 完成。

#### P01-Refactor · R1–R6 收敛改版（已完成实现）

- R1：全局风险契约、六维栏目映射、五色语义和双视图单一数据源。
- R2：风险置顶、六维连续区、左中右布局和顶部/底部职责边界。
- R3：六维平面/表格切换，同一 `metrics / series / breakdown` 与 `evidenceRefs` 驱动两种视图。
- R4：Excel、PDF、PNG/JPG 精确定位、反向返回，以及 pending/不可核验清除旧高亮。
- R5：底部审批抽屉、业务与风控共享链、硬约束高于 AI 软建议、模拟审批状态。
- R6：折叠、调宽、全屏、键盘、减少动画、1440×900 实页验收、截图和文档收敛。

R1–R6 仍属于 P01 前端，不启动或替代 P02-Back/P03-MVP。P01-Refactor 完成后必须由 Compare 主控复核实际 diff、测试、构建、浏览器证据和截图，再决定后续 Gate。

#### P2-Front · P1 退场后的业务纠偏 Gate

P2-Front 位于 P01-Refactor 与 P0-2 Adjacent Back 之间，由独立业务前端任务串行完成；即使 P2 Gate 通过，也不得自动启动 P02-Back 或 P03-MVP。

1. F1：正文移除 00/01–06 前缀，保留左侧 1–6；六维圆盘浅一档，评级字母随维度固有色。
2. F2：风险严格改为禁止→风险→核实→关注→支持五类纵向分组，稳定风险项 ID 与逐证据目标支持准确联动。
3. F3：合规保留平面图谱/表格；图谱可拖动、平移、缩放、适配、恢复默认并支持双主体直接或最短关系路径。
4. F4：合同设备、供应商报价、可比价与融资构成只归交易；同一设备 ID 同步交易链、价格带、参数、台账和轻量立体预览。
5. F5：生产只保留运营设备、产能与工艺；补齐原材料→工艺→成品公开参考图片链、右侧图集，以及带明确单位和证据的用电量/完工产量交互图。
6. F6：保持左右/协同折叠、调宽与三类全屏、完整业务 AI/制度认知/风控 AI 链；按 `typecheck → build → test → diff-check` 回归，并完成三档真实浏览器验收。

P2 最低历史图表迁入清单为：成熟六维 hover/focus/selected/muted、五级风险、合规 active/muted 与关系路径、交易链/融资构成/价格配置、生产流程/时间控制/用电量与绝对产量。营收、负债、流水仅冻结后续映射，不在本轮进一步重构；`ScenarioCompass`、无 live 组件的 debt sunburst 和无可信基准的利润率比较不迁入。

P2 浏览器 Gate 固定检查 `1280×720`、`1440×900`、`1920×1080`：无整页横向溢出、焦点可见、控制台 0 error/warn，并截图六维颜色、五级风险、动态图谱路径、交易模型和报价、生产三阶段/图集、用电量与产量、完整三方协同。自动检查与主控人工视觉验收分开记录。

P01 文件边界：Sites 工程、源码、测试和前端契约全部保留在 `Compare/Front`。不得修改原 `JW/Front` 或 `JW/Back`，不得接真实 AI 或真实后端，不得复制原系统整页或整份 CSS；只按已确认的组件和业务逻辑选择性移植。P01 开发期以 localhost 实时预览为准，暂不进行部署、发布或独立封装。

验收闸门 A：用户确认布局比例、信息密度、六维导航和材料预览方式。未通过前不启动 Back 实现。

完成标准：页面可独立运行；核心交互可操作；无隐藏后端依赖；视觉通过人工确认。

### P0-2 · Adjacent Back

目标：根据已确认的前端链路建立最小后端契约。

#### B1 · 契约先行

- 以前端已验证的模拟数据为样本，定义项目、维度、材料、证据引用、识别结果、业务修正和风控认定的最小字段。
- 明确 `scoreGrade`、`decisionGrade`、`confidence`、`evidence` 和 hard gate 的独立字段。
- 每个值保留来源、单位、状态和模拟标记；前后端不得使用位置顺序隐式映射维度。
- `evidenceRefs` 必须使用材料稳定 ID，并按材料类型提供准确 locator：Excel 的 sheet/range，PDF 的 page/bbox 或可验证文本锚点，图片的归一化 bbox；同时保留材料版本标识。
- 定义业务消息、风控消息、共同审查事件、事实快照、制度规则结果和软建议的独立结构；正式记录绑定稳定 actor、时间、事实版本与证据引用。

#### B2 · 最小服务

- 只在 `Compare/Back` 建立独立 FastAPI 应用。
- 提供 P0 MVP 所需的工作台读取、业务修正提交和风险认定能力。
- P0 使用受控的本地模拟材料和生成状态；不建设通用上传、OCR 或 Office 解析平台。
- 运行时数据放入未跟踪目录，不写入源码和测试夹具。

#### B3 · 选择性抽取

- 从原 Back 抽取六维规则、字段映射和纯计算逻辑。
- 不复制认证、项目管理、审计、部署和本任务无关的基础设施。
- 抽取后的逻辑以 Compare 内测试为准，不形成跨目录依赖。

#### B4 · 后端验证

- 覆盖正常、缺失材料、无法核验、业务修正和 hard gate。
- 验证缺失材料只降低置信度或进入人工复核，不自动拒绝。
- 验证接口错误不会返回伪造成功结果。
- 验证 locator 越界、材料版本不匹配和无法定位时返回明确错误状态，不返回虚假证据位置。

验收闸门 B：冻结 P0 接口字段和错误语义。冻结后 Front 与 Back 只能通过明确变更记录调整契约。

完成标准：接口契约稳定；测试通过；错误和缺失材料不会静默伪造结果。

### P0-3 · Integrated MVP

目标：完成一条真实可运行的前后端闭环。

#### M1 · 替换数据源

- 保持 UI 组件不变，用 API adapter 替换 P0-1 模拟数据源。
- 禁止把后端失败静默替换为本地成功数据。
- 页面明确区分加载、空、错误、模拟和真实响应。

#### M2 · 完整主体合规链

- 一个项目能够加载并进入 Compare 工作台。
- 六维导航全部可用。
- “主体合规”完成材料、识别、业务修正、风控认定和证据定位的完整闭环。
- 其余五维使用统一节结构承载已复用图表，但不伪装成已经完成全部材料链路。

#### M3 · 联动与恢复

- 左侧导航、中间判断和右侧材料引用保持同步。
- 中间数据与右侧材料证据保持双向精确定位；切换文件、工作表、页码或缩放后仍能恢复正确高亮范围。
- 业务与风控正式提交进入共同审查链，事实变更触发制度规则重新计算并追加不可编辑的系统事件。
- 刷新后保留合理的布局宽度和当前维度，不保留敏感材料内容。
- 前端全屏、折叠和拖动状态不影响后端数据语义。

#### M4 · P0 验收

- Front：静态检查、测试、构建、浏览器视觉验收。
- Back：pytest、接口契约和关键业务测试。
- Integration：启动、请求链、错误链和刷新恢复。
- Repository：只改 Compare；无跨目录 import；`git diff --check` 通过；文档与真实状态一致。

完成标准：本地可启动；主体合规链可重复验证；无隐藏回退；用户确认 P0 可进入下一轮。

## 执行纪律

- 每次只推进一个工作包，例如 F2 完成并验证后再进入 F3。
- 每个工作包开始前列出目标、文件、排除项和验证命令。
- 遇到需要新增依赖、改变契约或扩大 P0 范围时停止并确认。
- 不用长对话替代代码证据；构建、测试和浏览器检查分别记录。
- 不为了“未来可能需要”创建共享框架、空模块或重复适配层。

## P0 不做

- 不实现通用 Office 编辑器或复杂 OCR 平台。
- 不把模拟操作描述为真实 AI 执行。
- 不做多租户、生产部署或大规模权限系统。
- 不重构原 JW 首页和原后端。
- 不为未来假设建立大型抽象或重复数据层。

## P1 候选

- 六个维度全部完成材料—识别—修正—认定链路。
- 真实 PDF、Excel、图片预览和定位引用。
- 业务修订历史、审计轨迹与多人协作。
- 更完整的项目列表、权限和报告输出。
