# Status

更新时间：2026-08-16

## 当前阶段

### GLM-5.3 迁移检查点（2026-08-16）

Compare 的可选真实 Agent 路径已从冻结的 `glm_5_2_coding_plan_cli / glm-5.2` 迁移到精确的 `glm_5_3_coding_plan_cli / glm-5.3[1m]`。CLI 命令直接传模型 ID，不再经 `sonnet` 别名；运行遥测必须只包含精确 `glm-5.3[1m]`，旧 5.2、前后缀代理、多模型或缺失身份均 fail closed。

隔离临时数据库中的真实 A2A 风控 turn 已通过：HTTP `200`、`mode=real`、`isSimulated=false`、`advisoryOnly=true`、`provider_generated_unverified`，输入/输出 `2910 / 657` tokens、记录成本约 `0.030975 USD`、permission denial 0、validation failure 0。与同版本空白基线相比，`fact_versions / evidence_references / policy_results / approval_transitions / review_events` 增量均为 0。Back provider 聚焦测试 `34/34`、Front 全套 `204/204` 通过；仍只有既有 Starlette/httpx 弃用警告。本 Gate 只证明本机当前接口、身份遥测、失败关闭和 advisory 边界，不证明模型内容质量、额度/SLA 或公网生产可用性。

### P6 三账号认证与 ACL Gate（2026-08-14）

signal-council 已实现固定 `business / risk / coordinator` 内网 Demo 登录，coordinator 在服务端映射为 `leadership`、界面显示协管。SQLite 增加 account、account session、project membership；当前全部项目以幂等方式建立三条 membership，不复制项目或流程数据。正式 API principal 只来自后端 session，客户端自报 `X-Compare-Role` 无法换角色。

2026-08-16 当前完整 Gate：Back `509 passed / 1 warning`；Front `217/217`、typecheck 与 vinext build 通过。应用内浏览器以物理 `1920×1080` override 复核现有 risk session，实际 CSS 视口 `1315×739`，入口与项目选择页横向溢出 0、console error/warning 0；页面明确显示 24 项固定一一绑定的脱敏模拟演示数据。权限契约固定为 business/risk 参与群聊并只调用业务或风控 Agent，coordinator 读取共享投影、管理系统设置并执行审批，不参与群聊且不是 Agent target。

一键脚本 `Preflight` 通过；默认 `Start` 正确拒绝复用本轮开始前已占用 8000 的旧 API（其 OpenAPI 无 `/auth/login`），并未终止该未知进程。因 4317 同时存在既有同目录 vinext，`Start / Check / Stop` 完整循环未在默认端口重跑，不能写成已通过。仓库外随机端口真实 HTTP Gate 已独立证明新 API、迁移、session 与 ACL 可运行。

三个账号初始密码 `123456` 只用于隔离内网 Demo；公网 Gate 尚未通过，必须先轮换密码并补 Secure Cookie/TLS、生产身份生命周期、限流/CSRF、进程托管、备份恢复、隐私留存和 Internet 安全审查。

### P6 轻量现场概览收敛（2026-08-14）

现场 WebGL Demo 已收敛为固定“材料｜设备｜成品”三区的轻量生产动画：工艺归入设备区，移除区域编号、人员独立区域和左上角运行说明；保留“材料就位→设备加工→成品转运”的循环及相对颜色/大小变化。一个高可见度的代表性模拟作业人员在设备区三台代表设备前往返巡看，停留时朝向对应设备，不再与设备作业关系割裂。设备数量和运行/维护/待机状态来自现有 `OperatingEquipmentStatus` 汇总；材料、成品和人员在缺少照片直接支持时仍只是动画示意，不冒充精确识别。

当前自动化边界仍是材料元数据归类、结构化设备事实和轻量相对模拟，不是像素级视觉模型、真实尺寸测量或照片三维重建。真实 `4317→8000` 项目若原件不可读会继续显示诚实空态；本轮未安装模型或依赖。Front 聚焦测试 `7/7`、全套 `193/193`、typecheck、vinext build 和 scoped `git diff --check` 通过；临时响应式验收页在 `876×493` CSS 视口无横向溢出，三区热点、人员跨设备移动和动画暂停均通过，验收页已移除。

### Windows 本机一键运行 Gate（2026-08-14）

根 `start-local.ps1` 已收束为单入口 `Start / Preflight / Status / Check / Stop`：不自动安装依赖，不终止未知进程，默认把数据库、日志、PID 状态和导入目录放在仓库外，并检查 Python/Node、固定端口、Back health、项目目录、Front 页面和 4317→8000 CORS。real Agent 模式显式检查 `claude.cmd`、仓库外认证、精确 `glm-5.3[1m]` 模型与人工预算声明；任何条件缺失都在启动前失败，不回退 synthetic。

本轮受控验收通过：默认 `4317/8000` readiness/status/check 通过，24 项可读；外置 Archive + 当前共享 SQLite 已通过受控追加导入形成匹配绑定，24 个项目各有 56 份原件可读，真实原件 Range 为 `206 / 32 bytes`。未配置 Archive 的隔离实例仍保持 health ok、24 项/每项 56 份，并统一投影 `not_configured`，原件 HTTP 返回 `503 material_root_not_configured`。新主机应使用仓库外新库或经过受控导入/迁移的匹配库，详见 `DEPLOYMENT.md`。这仍不是登录、TLS、Windows Service、自动备份或公网生产发布。

**以下为 P5 与早期 P6 的历史基线：本地脱敏演示、单焦点 Agent、三栏真实对话接线与只读最终结论投影 Gate 当时已通过。** 当时 Back 全套为 `455 passed`，Front 全套为 `193 passed`，尚未实现登录/认证；当前认证与 ACL 状态及本轮真实数字以前文新 Gate 为准。

24 个项目目录各含 56 份脱敏模拟业务原件和一个 ZIP，共 1344 份唯一 SHA-256：504 个 Excel、336 个 PDF、504 张 `2048×1152` PNG。每包另含 `derived/scene-spec.json`、`factory-layout.glb` 与图像 provenance，不冒充原件；最大项目目录 26.96 MiB、最大 ZIP 26.57 MiB，均低于 100 MiB Gate。导入、项目隔离原件读取、HTTP Range、Excel/PDF/image locator、SceneSpec 与 GLB 派生边界已有全新 SQLite 隔离运行证据；`Back/runtime/**` 继续只保留在本机并由 Git 忽略。

DataPack v1→v2 历史证据投影修复已通过 RuntimeQA：不可变 v1 evidence/SourceAnchor 不被重写；v2 导入后，当前工作台会把仍指向 v1 的旧 `located` locator 降为 `pending / review / locator=null`，重新核验和人工确认后才建立指向 v2 的当前证据。当前共享本机运行库的 24 个项目均已追加导入各 56 份 v2 外置原件并保留旧 v1 历史，共 1344 份原件可读取；每个项目另有 5 份无原件的系统材料保持 `not_imported`。Front 当前基线为 typecheck、`193/193`、vinext build；审批画布异常增高/抖动已修复，精确 `1920×1080` 为 `clientWidth/scrollWidth=1920/1920`。设备、现场和工艺原件预览保持 2048×1152 原比例，技术页脚裁切与 locator 映射一致；设备选择与同一 line 的 materialId 同步，无法证明对应关系的通用 3D 已撤下。

`Show/`、仓库根目录旧 Front/Back 与旧启动文档、Compare `Front/artifacts/legacy`、`original.html` 和两份研究文档已可恢复地封存到 `C:\Users\22673\Desktop\JW-Archive\P5-Core-Scope-20260812`；P5 收敛提交移除这些公开历史表面。3 张继续参与页面的公开参考图已清除元数据；公开参考图和全部 synthetic 素材仍不参与风险事实认定。未安装依赖、未部署。

## P6 单焦点 Agent 与最终结论层（2026-08-13）

### 当前状态：本地单焦点对话与只读投影闭环 complete

- 每个 thread 只有一个服务端 `focusRole`；新 thread 默认 business，risk/leadership 只临时接管，成功 turn 后自动返回 business。
- 公开 API 已删除 channel ACL、`turns/{role}`、governance version、协调模式、多步自动链与模型 `suggestedHandoffs`；焦点只经 `expectedVersion + Idempotency-Key` 的服务端接口变更，并留下 append-only event。
- 同一 thread 最多一个 active run；全局幂等冲突、失败新 key、lease fencing、复合 FK、v7→v8 migration/restart、最近 40 条上下文和双连接并发已有回归。
- 所有 Agent 输出固定 advisory-only。评测实测 Agent turn 对 `fact_versions/policy_results/approval_states/approval_transitions/review_events` 零写入；`reject` 只结束协作，不是正式拒绝。
- Agent 专项 `79 passed`；Back 全套 `449 passed`，仅 1 条既有 Starlette/httpx 弃用警告。Front 全套 `180/180`，单焦点 gateway/三栏 UI/协作流与旧布局聚焦组 `41/41`，typecheck 与 build 通过。
- OpenAI/GLM 的 tool、模型身份、越权 citation、非法结构和权威声明均 fail closed。正常 Agent chat 默认 `real + glm_cli + glm-5.2`；synthetic 仅为显式开发/测试 override，Provider 失败不会静默回退。
- `X-Compare-Role` 只是本地 simulated principal，不是登录、认证、用户身份或生产 RBAC。
- `GET /projects/{projectId}/conclusion` 只读聚合项目状态、六维认定、关键证据、正式未决项、制度 Gate、审批状态和最新单焦点建议；连续读取不改变事实、审查、审批或 Agent 表。
- Front 默认不再显示 TopBar 独立报告入口；报告代码只作为非入口回退。协同区为三栏：业务自由对话、可追溯协作事实流、风控自由对话。引用材料/维度/历史消息严格可选；中栏不自动收录左右草稿，只显示材料定位、明确问题、显式协调结论和焦点事件。
- 共享 `4317 → 8000` 已从业务输入框执行一条脱敏真实 GLM turn：provider/model 为 `glm_5_2_coding_plan_cli / glm-5.2`，input/output `2853 / 896` tokens、记录成本 `0.036665 USD`、permission denial 0、validation failure 0。刷新后消息与 provenance 恢复；中栏 13 项、5 条待回复、1 条焦点事件，用户普通输入不在中栏；SQLite `review_events` 保持 11 条不变，Agent 表均为 advisory-only。
- 应用内浏览器物理 `1920×1080` override 受 Windows `devicePixelRatio=1.46` 影响，实际 CSS 视口为 `1315×739`；横向 overflow 为 0，三栏全屏可用，Agent 历史引用/取消可操作，刷新后 console 0 error/warning。本轮不伪报 CSS 1920 实测，既有精确 1920 P5 基线不变。

## P5-MG-EvalRelease Gate（2026-08-12）

### 已实现与已自动测

- `Back/evals/model_gateway/` 与 `Back/tests/evals/` 将公开输入和 hidden golden truth/Oracle 物理分离；六行业 smoke 后进入 24 项标准集，每项只用一份代表材料。韧性覆盖 timeout、有限 retry、rate limit、budget ceiling、circuit breaker/recovery；真实调用默认 `0 calls / 0 budget`。
- 冻结评分不因结果调整：BlindEval v1 `76.3864` **FAIL**，R2 `30` **FAIL**。R3 只产出 `MaterialIntelligenceResult`，按相同 v2 语义/性能阈值得 `92.8596` **PASS**；字段准确率 92.8571%，最低载体 85.7143%，所有 hard Gate 通过，总耗时 282.735s，低于 300s absolute ceiling。
- R3 的 gateway envelope、canonical `inputHash`、材料绑定、`sourceAnchors`/`locatorBindings` 投影和脱敏记录由独立 ProviderReplay 负责，3/3 **PASS**；每 case 首执行 1 次、replay 0 次、`FactVersionWrites=0`。一次 `local_input_selection_error` 没有用于输出，属于 evaluator 流程质量记录，不计作 provider retry。
- ProductionWire real mode 已接线：无 `OPENAI_API_KEY` 时在材料读取和网络访问前返回 `provider_not_configured`；startup、health、capabilities、项目 seed 都是 0 次外调；显式 mock transport 的 real-mode 请求首执行恰好 1 次，幂等 replay 0 次。Provider 会核对 `contentHash`、材料/版本身份、`sourceAnchors` 并派生 `locatorBindings`，任何漂移或越权字段 fail closed。

### 未执行与真实性边界

- 以上全部是 offline Codex、deterministic fake 或 mock-direct production replay；`externalNetworkCalls=0`，不是 OpenAI 或其他外部 Provider API 实调。当前没有 `OPENAI_API_KEY`、真实预算/成本和真实响应证据。
- 当前不是统计验证模型，也不是生产部署；没有真实客户材料、认证/多租户、生产隐私与留存删除 Gate。
- 本轮 56 份材料已完成全新 SQLite/API Gate 和精确 `1920×1080` 浏览器复验；页面无整体横向 overflow，审批区内部滚动稳定。浏览器未发现产品 Fetch/HTTP 错误；DarkReader 扩展注入导致的一条 hydration mismatch 不属于产品代码。旧 36 份材料截图只保留为历史证据。

## P5-MVP 真实边界

- 已完成的是脱敏合成演示闭环、provider-neutral 受控材料导入和 ModelGateway real-mode 生产接线；默认演示识别仍是 deterministic synthetic provider。
- 尚未进行真实外部 Provider API 实调，也未接通用 OCR/Office、3DGS、真实客户材料、认证/权限或生产部署；没有统计模型验证。
- 候选必须由人工明确确认；未确认候选不写权威事实。缺失或不可核验只降低置信度或进入人工复核，不自动拒绝。
- SceneSpec 只允许声明式枚举和数值，不执行模型代码；当前图片原件流程和设备审查区不再把通用 SceneSpec/Canvas 冒充客户扫描、对应设备或真实资产重建。

## P2-Front 历史进度

### 已落盘

- 正文标题移除风险和六维数字前缀；左侧 1–6 双导航保留。六维扇区浅一档，A–E 仍由真实分数派生且可见颜色随对应维度。
- 风险改为禁止、风险、核实、关注、支持五级纵向分组；稳定风险项 ID 与逐证据目标消除共享 evidence 错亮和硬规则多证据错绑。
- 合规动态图谱具备节点拖动、空白画布平移、缩放/适配/恢复、键盘移动、双主体直接或最短路径，以及事实派生的主体材料状态矩阵。
- 交易以 `financedEquipment` 为单一事实源，完成交易链、直租融资构成、价格带、参数对比、合同/供应商报价、设备 ID 同步和按需 Canvas 参数化立体预览。
- 生产以 `operatingEquipment` 表达运营状态，完成原材料→工艺→成品三阶段、7 张本地公开参考图、右侧分组图集，以及明确 `kWh`/`件` 的月/季用电量与绝对产量图。
- 三方协同、调宽、折叠与审查/材料/审批全屏均保留；公开参考图和 Canvas/点云原型均有真实性边界说明。

### 自动检查与浏览器自检

- 最终标准 Gate 已先执行当前源码 `typecheck` 与 Sites 五阶段生产构建，再执行完整 `npm.cmd test`：44/44 通过。测试覆盖 Rank 身份基线、风险排序与共享 evidence、图谱坐标/路径/平移、设备单一事实源与正负零价差、价格 unavailable、参数 source/unit/fact/evidence 语义、生产聚合/状态和 pending 清旧高亮。
- 本地浏览器已实际设置并检查 `1280×720`、`1440×900`、`1920×1080`；三档整页横向溢出均为 0，控制台无 error/warn，键盘焦点可见。
- 已实际操作图谱节点拖动、空白平移、节点方向键与双主体路径；设备跨卡片/链路/报价/模型同步；模型加载/旋转/缩放/重置；生产阶段、图集缩略图、月/季聚合和完整审批全屏。
- 三档 CSS 视口值由页面运行时返回并非推算；但应用内浏览器截图接口只导出物理可见表面，PNG 分别受限为 965×720、1206×900、1327×990。尝试强制 1280/1440/1920 文件尺寸时出现表面平铺，已删除这些伪精确图并恢复真实截屏；P2-Control 必须把“布局视口验证”和“截图文件像素尺寸”分开验收。
- 原生交易链按钮已移除自定义 `onKeyDown`，普通 click 计数为 1；浏览器 CUA 能向焦点按钮发送单个可信 keydown，但该自动化后端不会合成 native button 默认 click，因此物理 Enter/Space 的“恰好一次激活”仍需主控人工按键确认，执行任务未伪报通过。
- 最终标准 Gate 已按 `typecheck → build → npm test → git diff --check` 执行；本次测试读取的是刚生成的当前 `dist`，没有使用旧构建替代源码验收，`git diff --check -- Compare` 通过（仅显示既有 LF→CRLF 工作树提示）。

### 主控待验收

- P2 执行任务已完成三档自动化视觉自检与截图，但 Compare 主控仍需逐屏确认信息密度、图片许可呈现、风险/图谱/交易/生产视觉以及协同链；自动检查通过不替代产品验收。
- Rank 项目入口与身份回归产物在 P2 中保持冻结；主控需合并审查共享工作树的全部既有未提交改动归属。

### 明确暂缓

- 营收、负债、流水只在 D-037 冻结历史复用映射，本轮不进一步重构。
- P2-Front 当时不做新 evidence locator 算法、材料反向定位精修、真实后端/AI/OCR/Office 解析、真实客户材料或真实 3DGS；后续 P4/P5 的当前接线状态以本文顶部为准。
- `ScenarioCompass`、仅存历史 CSS 的 debt sunburst、无可信行业基准的利润率比较均未实现；生产页对此显示诚实不可用状态。

## 已完成

- 锁定唯一工作地址和独立 Front/Back 边界。
- 明确极简、无重复、选择性复用原则。
- 明确三个 P0 检查点及先后顺序。
- 记录页面布局、调宽、全屏和材料状态规则。
- 锁定 `gpt-5.6-sol` + `xhigh`，不再分配其他模型。
- 将 P0 拆分为准备闸门、Front 基线、Adjacent Back 和 Integrated MVP。
- 为 Front、Back 和集成阶段定义工作包、验收闸门和完成标准。
- 明确当前 `Compare` 任务只做主控，执行拆分为 `P01-Front`、`P02-Back`、`P03-MVP`。
- 明确三个执行任务严格串行，同一时间只有一个写入者。
- 已创建 `P01-Front`，并完成原 Front 的只读复用盘点、最小依赖提案、文件级计划和浏览器验收清单。
- 六维短名称与顺序锁定为：合规、交易、生产、营收、负债、流水。
- 锁定左上角六维图以原 `MiniDimensionDial` 为基线近乎完整移植，不改成另一套等分数字饼图。
- 锁定原六个维度详情页纵向合并为一个连续页面，并保留原图标、图表、高亮、过渡特效和交互样式。
- 锁定最左侧为“顶部六维图 + 下方六栏目入口”，与中间滚动位置双向联动。
- 锁定每个业务数据必须与右侧材料准确区域双向关联；Excel、PDF、图片分别使用可复现 locator，定位失败不得伪造高亮。
- 锁定业务 AI 与风控 AI 两个角色、双方可见的共同审查链，以及独立非对话的制度硬约束引擎。
- 锁定底部三栏协同工作台：业务方、共同审查链、风控方；可收起、调高、全屏，两侧角色栏可折叠。
- 锁定中间独立纵向滚动、左右区域稳定可见、顶部四阶段可定位，以及模拟业务修正交互。
- 将 P03-MVP 内部工作包编号统一为 M1–M4。
- 已生成 `assets/compare-p01-low-fi-v1.png`，用于正式开发前确认整体布局、比例和信息关系。
- 用户确认低保真 v1 作为 P01 正式开发的结构基线。
- 将 P01-Front 拆为五个产品增量：F1 视觉基础与可运行全页、F2 六维内容与导航、F3 布局与材料预览、F4 数据证据链、F5 协同链与整体验收。
- 明确 F1 即建立整套前端基础：页面可运行，基础区域、间距、颜色、字体和通用组件可见，同时只为后端预留接口层和 mock gateway。
- 用户已批准 React + React DOM 与 TypeScript + Vite 的最小依赖安装。
- 已启动现有 `P01-Front` task 的 F1，并下达文件边界、排除项、验证命令和三分辨率截图要求。
- 用户要求 P01 基于 Sites 开发，以 localhost + HMR 实时更新组件并持续预览修正，暂不考虑部署或封装。
- 原 React/Vite 草稿曾按主控要求安全暂停，随后仅选择性迁入 Sites 路径，没有被误判为已完成产物。
- 已将原草稿原地迁入 Sites `vinext` 能力路径，没有建立第二套工程；D1、R2、认证、部署和发布均未启用。
- F1 页面已具备顶部、左侧、中间、右侧、底部五大区域，并在 localhost 中通过 HMR 实时更新验证。
- `typecheck`、3 项 Node 测试、Sites 五阶段生产构建、`git diff --check` 和 localhost HTTP 200 均通过。
- 1440×900、1680×945、1920×1080 三档视口均完成无整体横向溢出检查并保存截图；第三张截图受浏览器后端裁切为 1920×1065，但实际检查视口为 1920×1080。
- 用户接受 F1 基线，并要求取消 F2–F5 的中途等待，在原 task 中按顺序一口气完成 P01-Front。
- 已向 `P01-Front` 下达 F2–F5 完整实现、浏览器交互验证、最终截图和 P02 接口清单任务包。
- F2 已完成：原六维圆盘结构、唯一活动维度状态、1–6 导航、滚动联动和六个纵向详情板块落地。
- F3 已完成：左栏折叠、中右调宽与全屏、协同区调高/收起/全屏、角色栏折叠，以及 Excel/PDF/PNG 模拟预览落地。
- F4 已完成：主体合规四阶段链路、Excel/PDF/图片 locator、多证据、异常定位、双向证据跳转和本地事实版本更新落地。
- F5 已完成：业务 AI、风控 AI、共同审查链、制度硬约束、AI 软建议、本地提交状态和 `WorkbenchGateway` 契约冻结。
- 主控复跑 `typecheck`、8 项 Node 测试、Sites 五阶段构建、`git diff --check` 和 localhost HTTP 检查均通过。
- 主控在真实浏览器中复核六维跳转、材料切换、证据定位、材料全屏和业务提交进入共同链，控制台无错误，1440 宽度无整体横向溢出。
- 最终三档历史截图已封存到 `C:\Users\22673\Desktop\JW-Archive\P5-Core-Scope-20260812\Compare\Front\artifacts\p01-front\`；P02 接入清单仍位于 `Front/P02-INTEGRATION.md`。
- 已启动 `P01-Refactor`，旧 `P01-Front` 停止写入；当前 task 是唯一前端写入者。
- R1 已新增独立全局风险汇总契约，风险未加入六维常量、数组或圆盘数据。
- R1 已保持六维顺序不变，并按已冻结分类重写统一 mock；所有一级业务标题为两个字，排除项没有形成独立栏目。
- R1 已在原 `DimensionDetail` 上增加默认视图、可用视图和逐项证据引用；`metrics / series / breakdown` 仍是唯一数据源，没有第二套表格模型。
- R1 新增但没有准确 locator 的证据均显式标记为 `pending + null locator`；五色风险 token 与材料识别状态、六维导航色分离。
- R1 聚焦验证为 `typecheck` 通过、13 项 Node 测试全部通过、限定范围 `git diff --check` 通过。
- R2 已修复半成品 `onActiveReviewChange` 运行时契约不一致；风险置顶、六维顺序、圆盘/1–6/滚动联动及顶部/底部职责边界已在 localhost 复核。
- R3 已完成合规主体、交易关系、生产流程、营收趋势、负债结构和流水趋势平面；平面/表格共享 `metrics / series / breakdown` 与 `evidenceRefs`，切换后保持选中。
- R4 已完成 Excel、PDF、PNG、JPG 模拟预览；Excel 范围、PDF 页内区域和图片区域可精确高亮并反向返回，pending/不可核验会清除活动材料和旧高亮。
- R5 已将业务修正、业务/风控共享链、风控认定、制度硬约束、AI 软建议和暂存/退回/提交/完成模拟状态统一移入底部审批工作区；没有第三个制度聊天。
- R6 已完成 1440×900 无整体横向溢出、导航折叠、键盘调宽、三类全屏、可访问名称、减少动画和控制台新增错误检查；六张历史截图已转入本地可恢复封存目录的 `Compare\Front\artifacts\p01-refactor\final\`。
- R7-1 已建立可读性层级：业务正文/字段值不低于 13–14px，辅助说明和证据定位不低于 12px；风险五色只承担边框、图形和状态信号，小号说明统一使用深灰。
- R7-2 已收敛默认三栏：1280×720 为 `194 / 658 / 420`，1440×900 为 `194 / 788 / 450`，1680×945 为 `212 / 940 / 520`，1920×1080 为 `212 / 1180 / 520`；四档均无整体横向溢出，生产与负债常用节点不再碎裂换行。
- R7-3 已实现 Excel 材料内部自动定位；`C4:E4`、`C10:E10`、`C19:E19`、`C22:E22` 均准确高亮 3 个单元格并进入右侧内部视口，不调用全局 `scrollIntoView`。新增定位解析聚焦测试，完整测试为 18/18。
- R7-4 已压缩风险区约 158px 无效高度，材料标签支持两行完整短名与标题提示，普通审批展开改为三张摘要卡，详细三栏仅在审批全屏出现；可见版本和定位文案已改为业务中文。
- R7-5 已通过 `typecheck`、18 项 Node 测试、Sites 五阶段生产构建、`git diff --check`、localhost HTTP 200 和应用内浏览器控制台检查；八张历史返工截图已转入本地可恢复封存目录的 `Compare\Front\artifacts\p01-refactor\r7\`。
- R7 视觉 Gate 被主控正式退回：普通审批摘要弱化了完整三方协同、六维等级和颜色没有充分复用原逻辑、风险与合规表达偏离产品核心；R7 截图仅保留为历史证据，不代表当前验收版本。
- R8-1 已恢复正常展开态与全屏态均可阅读、滚动、继续输入的 `业务 AI / 制度认知 / 风控 AI` 三栏；制度栏只展示双方共同引用的硬约束和完整时间链，不提供第三个对话输入。动态事件分别保留真实事实版本、画布目标锚点、材料引用、线程与回复关系。
- R8-2 已统一六维评分派生：A `80–100`、B `60–79.9`、C `40–59.9`、D `20–39.9`、E `0–19.9`，输入先统一到一位小数；综合分为六维等权平均。左侧列表、圆盘扇区、分区标题与综合等级共享同一派生结果，维度固有色、等级色、风险五色分别使用独立 token。
- R8-3 已将全局风险改为独立横条，每条固定呈现等级/状态、标题、事实或制度依据、准确定位、责任方/下一步；同一风险的多份证据可逐项打开，风险不计入六维得分。
- R8-4 已建立 2 家公司与 3 名自然人的主体关系图谱，统一股权端点和材料口径；节点、关系与附件都显示明确定位状态，pending/unverifiable 会清除旧高亮，表格视图继续保留完整字段核查。
- R8-5 已补回设备合价核验：数量、单价、合价、供应商、报价来源、可比价、价差和合计均来自同一明细并可定位；明确该抽样与本次融资设备报价不是同一口径。
- R8-6 已补齐营收 `合同/订单 → 发票 → 回款/流水 → 确认收入` 来源链及差异定位，并为趋势、构成、金额比较、生产现场和交易融资使用可回证据的语义图表。现场清单覆盖图片、补图、视频、全景、设备点位与 3DGS 场景接口；本地 Canvas 点云近似仅为无依赖原型，明确不是客户真实 3DGS 数据。
- R8-7 已把审查、材料、审批全屏按钮放回各自面板，保持一热全屏、Escape 退出、导航折叠、键盘调宽和材料内部滚动。定位解析会校验材料类型、工作表/范围、PDF 页与区域、图片区域、媒体时间和场景点位；超界 locator 显式失败，不再伪造成功。未解除制度 Gate 时“完成”不可用。
- R8 最终自动验证为：`npm.cmd run typecheck` 通过，Node 测试 27/27 通过，Sites/vinext 五阶段生产构建通过。localhost 实页为 HTTP 200，当时 `1355×792` CSS 视口无整体横向溢出，控制台 error 0 / warning 0；历史截图已转入本地可恢复封存目录的 `Compare\Front\artifacts\p01-refactor\r8\`。
- 项目选择流程已改为 `Compare/Front` 的顶层入口：根页面先显示清单、分组、卡片三等宽入口，子页面提供顶部微型切换、24 个六行业演示项目、字段筛选排序、多选、五种自动分组和带原因的自定义拖放；项目目录与现有核验工作台共享 `WorkbenchGateway`，选中前后项目 ID 与六维数据保持一致。
- 项目选择接入验证为：`npm.cmd run typecheck` 通过，Sites/vinext 五阶段生产构建通过，完整 Node 测试 35/35 通过，`git diff --check -- Compare` 通过，`http://127.0.0.1:4317/` 返回 HTTP 200 且 SSR 已切换到 Compare 项目入口。

## 下一步

1. 后续如增加 leadership 协调操作，只能围绕唯一焦点与共享投影扩展；不得把中栏改成第三个普通聊天窗口，不得恢复多频道 ACL，也不得把 `X-Compare-Role` 包装成身份系统。
2. 后续信用页逻辑与前后端联调另开范围，不属于本 P6 Gate。
3. 在真实环境引入可信 principal、项目成员关系、租户隔离、生产审计、预算控制和 SLA 后，才能考虑非隔离网络或发布。

## 当前阻塞

- P6 本地 Gate 无代码阻塞。当前真实 smoke 只证明本机 CLI invocation/provenance/用量与失败关闭，不证明内容质量、外部核验、生产认证、SLA 或部署可用。

## 已知风险

- 当前没有认证与项目权限，服务只适合隔离本机演示；不得直接暴露到生产网络。
- P6 `X-Compare-Role` 可被客户端自报，只能验证本地行为权限；在真实认证 principal、项目成员关系和生产审计落地前，不构成安全边界。
- synthetic provider 的置信度不是统计验证；所有 24 项和工业视觉均为确定性脱敏合成演示。
- 36 张行业基础视觉只作为派生基底；24 项的 504 张原件 PNG 均有唯一文件哈希与项目 synthetic 标记，但它们仍不是 504 次真实拍摄。
- 导入 API 具备真实哈希与版本链能力，但未用真实敏感材料完成隐私、病毒扫描、权限、留存或删除 Gate。

## 工作区说明

- `Front/` 与 `Back/` 已通过真实 HTTP/SQLite 纵向联调；隔离自动测试使用仓库外临时数据库，共享 `4317 → 8000` smoke 按用户授权保留默认运行库，并只新增上述 Agent advisory 记录。
- 24 套原始材料包已迁出核心仓库并由外置归档根提供；`Back/runtime/**`、材料二进制、数据库、日志和上传目录继续保持 Git 忽略，不进入 V1 源码发布。
- `Show/`、仓库根目录旧 Front/Back 与旧启动文档、`Compare/Front/artifacts/legacy`、`Compare/original.html` 与两份研究文档已封存到 `C:\Users\22673\Desktop\JW-Archive\P5-Core-Scope-20260812`，并由 P5 收敛提交从公开主线移除；3 张参考图的原始带元数据版本保存在该封存目录的 `metadata-originals`，工作区版本已清除元数据。
- 原 JW 工作区及其他任务修改不属于本轮，不得覆盖、整理或回退。
