# Decisions

## 2026-08-08

### D-001 · 唯一项目地址

所有新建内容保留在 `C:\Users\22673\Desktop\JW\Compare`。

### D-002 · 独立运行

Compare 拥有新的 `Front/` 与 `Back/`。原 JW 系统只作为只读来源；Compare 不通过跨目录 import 形成运行依赖。

### D-003 · 选择性复用

复用顺序为：业务规则和数据契约 → 可视化组件 → 页面元素。禁止整目录复制和保留两套同义逻辑。

### D-004 · P0 顺序

P0 由三个连续检查点组成：Front 基线 → Adjacent Back → Integrated MVP。前端先用于锁定产品形态，随后以后端契约消除临时数据结构，最后集成。

### D-005 · 页面结构

左侧双重六维导航，中间纵向系统内容，右侧材料预览。左侧可折叠；中间和右侧可调宽、可分别全屏。

### D-006 · 极简信息密度

增加空间不等于增加长文本。默认只显示字段、图表、状态和短结论，详细依据按需展开。

### D-007 · 状态语义

绿色 `✓`、黄色 `?`、紫色 `×` 表示局部材料识别或证据状态，不直接替代最终风险结论。

### D-008 · 开发模型

Compare 全程使用 `gpt-5.6-sol`，推理强度为 `xhigh`。主 Codex 保持单一写入者；除非用户明确改变决定，不切换 Spark、GLM-5.2 或其他执行模型。

### D-009 · P0 目标技术栈

Front 默认采用 React + TypeScript + Vite，Back 默认采用 FastAPI + Pydantic + pytest。选择理由是与原系统核心代码兼容，同时保持独立项目的构建和运行简单。具体依赖和版本必须在准备闸门完成后获得确认再安装。

### D-010 · P0 完成边界

P0 要求六维导航可用，并将原系统六个维度详情页的既有字段、图表和判断纵向合并到一个连续页面；“主体合规”额外完成一条材料到风控认定的端到端闭环。其余五维在 P0 保留原详情内容和交互，不伪装成已经补齐新的四阶段材料链路；完整材料链路进入后续迭代。

### D-011 · 主控与执行任务分离

当前 `Compare` 任务保持主控和默认只读，不直接实施 Front、Back 或集成代码。实现拆为 `P01-Front`、`P02-Back`、`P03-MVP` 三个用户可见的独立 Codex 任务，按顺序串行执行；问题退回原任务修正，主控只做审查和最终验收。

### D-012 · 六维名称与顺序

六维导航严格沿用原 JW 系统的短名称与顺序，仅将“金流”改为“流水”：`合规 → 交易 → 生产 → 营收 → 负债 → 流水`。不得改成经营稳定性、财务健康度等另一套维度，也不得按数组位置之外的隐式规则重排。

### D-013 · 左上角六维图近完整移植

Compare 左上角六维图以原 `MiniDimensionDial` 为基线，近乎完整保留其扇区几何、维度顺序、颜色、半径与等级表达、图标、短名称、CSS 视觉样式和过渡特效，以及 hover、focus、选中和其余扇区淡化逻辑。允许的变化仅限：适配左上角容器尺寸；将“金流”改为“流水”；点击维度后改为滚动到中间对应板块；中心操作改为返回六维总览状态。不得重画成另一套等分数字饼图，也不得用功能近似但视觉不同的新组件替代。

### D-014 · 六页合一与最左栏目导航

Compare 不是重新设计六个维度详情，而是把原系统分开的六个维度详情页按 `合规 → 交易 → 生产 → 营收 → 负债 → 流水` 合并为中间区域从上到下的连续长页面。最左侧导航由顶部六维图和下方六个栏目入口组成；圆盘、栏目入口与中间滚动位置使用同一活动维度状态。点击任一入口滚动到对应栏目，手动滚动反向更新两个导航的高亮。原详情页的图标、图表、字段表达和交互样式优先迁移，只为连续页面布局、材料引用和新业务链做必要适配。

### D-015 · 数据与材料证据精确定位

中间区域的每个业务数据必须通过稳定 `evidenceRefs` 关联右侧一份或多份原始材料，并包含能够准确复现位置的 locator：Excel 使用工作表与单元格/区域，PDF 使用页码与文本框或区域坐标，图片使用归一化区域坐标。点击数据时，右侧自动切换材料、定位并高亮证据范围；点击证据区域时应能反向识别关联数据。证据选中高亮使用独立的中性描边或遮罩，不借用绿、黄、紫状态色表达风险。只有文件级来源不算完成。证据缺失、定位失败或材料版本不匹配时必须显示待定位或无法核验，不得用近似区域或模拟成功静默替代。

### D-016 · 两个角色 AI、共同审查链与制度硬约束

Compare 只有业务 AI 与风控 AI 两个对话角色；后台 `AI 识别` 是材料抽取能力，不构成第三个对话。业务与风控保留各自输入和角色提示，但正式提交的问题、回答、修正与追问全部进入同一条双方可见、不可直接删除的共同审查链，并关联事实版本、维度、字段和材料证据。制度不是对话角色：硬约束由独立、版本化、可复现的规则引擎执行，结果为通过、阻断或必须人工复核。软指标和 AI 建议必须标注为辅助意见，可由人工采纳或不采纳，但不得覆盖硬约束。

### D-017 · 底部三栏协同工作台

保留左侧六维导航、中间六维长页面和右侧材料预览作为主布局。在中间与右侧下方增加可收起、可调高、可全屏的协同工作台，内部映射为 `业务方 / 共同审查链 / 风控方` 三栏。左右栏承载两个角色 AI，可折叠为窄角色条；中间栏始终是只读的事实版本、正式协同记录、待解决问题和制度事件，不提供第三个聊天输入。协同记录点击后必须同步定位中间业务数据与右侧材料证据。

### D-018 · P01 布局与交互默认值

P01 采用单一中间纵向滚动容器，左侧导航和右侧材料预览保持稳定可见；右侧材料拥有独立滚动。左侧展开宽度、中右比例、最小宽度和协同工作台高度全部通过集中布局状态与 CSS 变量实现，可拖动、恢复默认并在不同 PC 宽度下调整，不把参考图像素写死。顶部四阶段可点击并定位对应内容；业务修正使用明确标注的本地模拟编辑与提交。P0 只持久化布局宽度、协同工作台状态和当前维度，不持久化模拟材料内容或对话草稿。

### D-019 · P01 低保真 v1 作为布局基线

用户已确认 `assets/compare-p01-low-fi-v1.png` 作为 P01 正式开发的低保真布局基线。F1 先实现可运行页面、完整静态区域和视觉基础；F2–F5 在此基础上依次完成六维移植、布局与预览交互、证据链、协同链和整体前端验收。低保真图是结构与信息关系基线，不是逐像素限制；真实页面仍需满足多分辨率、可访问性和内容滚动要求。

### D-020 · P01 保留 F1–F5 五个前端增量

`P01-Front` 负责交付整个前端页面，内部保留 F1–F5 五个有顺序、可观看、可验收的产品增量：F1 为视觉基础与可运行全页，F2 为六维内容与导航移植，F3 为工作台布局与材料预览交互，F4 为业务数据与材料证据链，F5 为协同链、接口冻结和整体前端验收。五个 F 均在同一个 `P01-Front` task 内推进，不再创建五个用户可见 task。每一阶段完成后提供页面证据并接受纠正，但 P02-Back 只在整个 P01 Gate 通过后启动。P01 只建立 TypeScript 接口、mock gateway 和契约样例，不连接或实现真实后端。

### D-021 · Sites 与 localhost 作为 P01 开发界面

P01-Front 必须基于 Sites 的 `vinext + React + TypeScript + Vite` 结构开发，并保留 `.openai/hosting.json` 与 Worker-compatible ESM 基础。敏捷阶段以 localhost 开发服务器和 HMR 为主要预览方式：组件修改后实时更新，用户直接在本地页面查看并纠正。当前不考虑部署、发布、持久化、认证或独立封装；这些能力不得妨碍 F1–F5 的快速迭代。此前已生成但尚未验证的 React/Vite 草稿仅可选择性迁入 Sites 页面，不得反向决定 Sites 架构。

### D-022 · F2–F5 连续完成 P01-Front

用户已接受 F1 基线，并授权在同一个 `P01-Front` task 中按 `F2 → F3 → F4 → F5` 连续完成整个 P0-Front，不再在每个 F 后暂停等待确认。连续执行不改变依赖顺序、写入边界或最终 Gate：各阶段仍需按顺序落地和内部验证，最终统一提交完整页面、交互、测试、浏览器证据和 P02 接口清单。P01-Front 通过主控最终验收前，不创建或启动 P02-Back。

### D-023 · 风险独立于六维

改版后的一级业务顺序固定为 `风险 → 合规 → 交易 → 生产 → 营收 → 负债 → 流水`，一级标题均为两个字。`风险` 是全局汇总，不是第七维，不进入六维常量、六维数组或六维圆盘；全局风险分别保留五色等级、`scoreGrade`、`decisionGrade`、`confidence`、证据、制度硬约束、关键异常和待人工认定。

### D-024 · 六维业务分类与排除项

六维栏目固定映射为：合规承载营业执照、身份证、章程、外部工商、主体涉诉、个人涉诉；交易承载交易结构、交易方案、交易关系；生产承载行业标签、设备、工艺、现场、用电、打卡；营收承载收入、订单、发票、经营表现；负债承载征信、借款、中登、担保、其他偿债义务；流水承载收支真实性、经营匹配、异常流水。五选二、后续风险关注、OCR、房产、车辆和项目不建立独立业务栏目；项目信息仅作为顶部案件上下文，OCR 仅作为识别来源与状态，资产只有形成偿债义务时才进入负债事实。

### D-025 · 图形与表格共享单一事实来源

`DimensionDetail` 继续以 `metrics`、`series`、`breakdown` 作为唯一业务数据源，只增加默认视图、可用视图和逐项 `evidenceRefs`。关系、结构、流程、趋势和异常分布默认使用图形；逐笔、逐条和完整字段使用表格；两者均有独立信息价值时才声明双视图。禁止增加 `tableRows`、`tableData` 或另一套同义数据模型。新增业务证据没有准确 locator 时必须显式使用 `pending + null locator`。

### D-026 · 三套颜色语义隔离

五色风险固定为 `support #22c55e`、`attention #2563eb`、`confirm #f59e0b`、`risk #dc2626`、`forbid #7c3aed`。五色风险、六维导航色和材料识别 `confirmed / review / conflict` 使用不同类型与 token 命名，不互相替代。

### D-027 · 风险导航与六维当前态并存

进入全局风险时，六维圆盘恢复全色，1–6 栏目仍保留最近活动维度的颜色；风险本身只使用独立置顶入口。点击风险卡会进入其 `dimensionId + targetId + evidenceRef` 对应的六维字段和材料。直接返回风险总览时清除旧证据选中，避免右侧残留无关高亮。

### D-028 · 待定位与不可核验必须清空预览高亮

证据解析只有 `located` 才能显示材料高亮。`pending`、`unverifiable`、版本不符、证据缺失或材料缺失时，右侧取消活动材料与旧范围，显示明确空态及失败原因；不得保留上一条成功高亮。平面和表格只切换表达方式，不改变 `evidenceRefs`。

### D-029 · 最终审批动作只在底部

顶部仅承载项目上下文、布局和材料显示操作。业务提问/修正、共享链路、风控认定、制度硬约束、AI 软建议以及暂存、退回、提交、完成等审批动作统一位于底部审批工作区。制度硬约束位于 AI 软建议之前且不可被对话覆盖；页面仍只有业务和风控两个对话角色。

### D-030 · R7 可读性与窄屏布局基线

业务正文和字段值使用 13–14px 以上字号，辅助说明、证据定位和状态说明不低于 12px；只有六维圆盘内极短且非关键的等级标记可以更小。风险五色用于边框、图形、徽标或较粗状态字，小号业务说明统一使用可读深灰。1280px 以上桌面视口优先保证中间审查画布至少 600px，窄屏时先压缩左栏与右侧材料栏。Excel 定位只滚动右侧材料内部容器。普通审批展开保持摘要态，完整业务、共享链和风控三栏只在审批全屏显示。

## 2026-08-09

### D-031 · R8 覆盖 R7 的审批摘要取舍

R7 的普通审批摘要态被主控退回。自 R8 起，正常展开与全屏都必须呈现可阅读、可滚动、可继续输入的 `业务 AI / 制度认知 / 风控 AI` 完整三栏；全屏只增加空间，不改变信息结构。制度认知是双方共同引用的只读硬约束层，不具备第三个对话输入。未解除的人工 Gate 必须阻止“完成”，对话或软建议不得绕过。

### D-032 · 六维评分与三套颜色分别派生

六维原始分在展示和分级入口统一到一位小数，再按 A `80–100`、B `60–79.9`、C `40–59.9`、D `20–39.9`、E `0–19.9` 派生字母；综合分为六维等权平均并使用同一规则。圆盘扇区使用原 Front 等级色，维度图标保留固有色，风险条只使用冻结的五色风险；三套 token 不互相替代。评级字母的可见颜色取舍已由 D-037 覆盖为“随维度固有色”，等级计算本身不变。

### D-033 · 关系、合价与现场资产使用独立规范化来源

`metrics / series / breakdown` 继续作为营收、负债、流水等通用维度平面与表格的单一数据源；P2 的交易与生产由专用规范化事实源覆盖旧通用演示指标。主体关系图、融资设备、运营设备和现场资产清单分别使用 `ComplianceSubjectGraph`、`FinancedEquipmentLedger`、`OperatingEquipmentStatus`、`OnsiteAsset` 契约，它们不是同一表格的重复副本。融资设备合计必须由价格基准与合同明细派生，图谱端点必须引用稳定主体 ID，现场重资产默认按需读取。

### D-034 · 精确证据定位必须通过材料边界校验

`located` 不只代表 locator 非空：解析时必须同时校验材料 ID/版本/类型，以及 Excel 工作表与行列范围、PDF 页和归一化区域、图片区域、媒体时间范围、场景点位。任一范围越界或类型不符均返回显式定位失败并清除旧高亮。协同事件另外保存 `reviewTargetId` 作为画布锚点，`factVersionIds` 只允许真实事实版本 ID，禁止把图表点或关系节点冒充事实版本。

### D-035 · 现场空间原型的真实性边界

P01 在无新增依赖条件下使用本地 Canvas 点云近似验证旋转、缩放、重置、加载/空/错和静态图降级接口。该原型不是 3DGS 重建、不是远程资产、不是客户真实现场数据；后续后端只能通过现有 `SceneMaterial` 与来源清单替换资产，不得把当前模拟点位描述成真实采集成果。

### D-036 · 项目选择属于 Compare 顶层入口

清单、分组、卡片三种项目选择方式位于 `Compare/Front` 的工作台之前，并与材料核验工作台共享同一个 `WorkbenchGateway`：入口通过 `listProjects()` 获取项目目录，选中后以原项目 ID 调用 `loadProject(projectId)`，禁止再由详情页随机生成或硬编码另一个项目。根地址正常进入三等宽选择入口；项目页返回上一次查看方式。P01 继续使用明确标注的本地演示数据，不因新增项目目录而提前接入真实 Back、数据库或 AI。六维缩略图严格按冻结顺序和现有颜色/图标绘制，只显示认定等级，不显示 A–E 外围尺度或数值评分。

### D-037 · P2-Front 历史图表语义复用矩阵与事实边界

P2-Front 只从当前 `JW/Front` 的五个冻结文件整理业务语义、计算、交互状态和必要局部样式，所有运行数据改接 Compare 的 `WorkbenchProject`、`FactVersion` 与 `evidenceRefs`，不跨目录 import、不整页复制、不用旧演示 profile 反推事实。矩阵冻结如下：

| 业务面 | 本轮实际迁入或重建 | 本轮明确不迁 / 后续边界 |
| --- | --- | --- |
| 六维总览 | 复用 `MiniDimensionDial` 的冻结顺序、扇区半径、hover/focus/selected/muted 与单一键盘焦点；扇区整体浅一档。A–E 仍由真实分数派生，但可见字母改用对应维度固有色，覆盖 D-032 的旧视觉取舍。 | Rank 的 `CompactDimensionDial` 只服务项目入口缩略图，不复制进工作台。`ScenarioCompass` 只适用于后续场景生成/比较，本轮不放入风险或六维总览。 |
| 风险 | 规则、异常、人工认定统一映射为 `禁止 → 风险 → 核实 → 关注 → 支持` 五级纵向清单；复用 active/muted/focus 视觉模式，并补稳定风险项 ID、逐证据目标、点击与 Enter/Space 可达定位。 | 风险仍是全局汇总，不成为第七维；风险色不得参与六维评级字母着色。 |
| 合规 | 保留新的可拖动主体图谱；只复用历史 `SubjectVisual` 的材料状态矩阵、active/muted/focus 与诚实空态语义，并增加平移、缩放、复位、双主体最短路径、方向/比例和稳定证据锚点。 | 不退回历史静态四角关系图；UI 节点不是 `FactVersion`，缺失定位不得伪装成功。 |
| 交易 | 整理迁入 `TransactionChain`、`PriceConfiguration` 和 transaction config table：链路、低/中/高/本次位置、偏离、不可用、本次参数/历史中位/同类范围都保留明确 `source / unit / factVersionId / evidenceRefs`；价格区间与配置行已写入同一脱敏材料表并各自绑定真实 `FactVersion`，UI `reviewTargetId` 仍与事实 ID 分离。以 Compare 单一 `financedEquipment` 事实源同步链路、卡片、报价、价格带、参数表和轻量 Canvas 模型。融资构成 donut 是基于当前 Front 成熟 pie/donut helper 几何与 Compare 直租事实重建，并非直接迁移旧组件。 | 合同、供应商报价、合价和可比价只在交易。没有 live 的旧 lease-finance-donut 组件，不得声称直接移植；多设备不得复制旧单设备 ledger。本轮没有真实还款计划，`repaymentTrend` 不渲染并冻结后续映射；只有日期、金额、期限口径和逐点证据齐全时才能迁入，禁止用旧估算或随机曲线。 |
| 生产 | 整理迁入 `ProductionProcess` 的原材料→工艺→成品状态模式；`ElectricityChart` 按数据单位纠偏后整理迁入，不沿用旧 Front 将电费/用电量混称的口径。当前以明确单位的月度用电量 `kWh` 与完工产量绝对值 `件` 实现双轴交互、月/季聚合、空区间和逐点证据；阶段图片与右侧本地图集共用阶段 ID。 | 生产只保留 operating equipment、产能、状态和工艺使用。公开参考图不是客户现场、不是证据、不参与风险事实认定。`PayrollChart` 本轮不迁，等待工资、人员与考勤形成统一可验证事实；`MarginComparison` 因无可信企业利润率与行业基准而显示不可用；不以旧随机 profile 补数据。 |
| 营收 | 冻结后续映射：`RevenueChart → 收入趋势`、`InvoiceChart → 已开票/已回款及回款率`、`CompositionDonuts → 上下游构成`、`CollectionChart → 回款/账龄`。 | 历史 live `InvoiceChart` 不是销项/进项；只有未来重新定义且取得真实销项/进项数据时才允许改口径。本轮不进一步重构；后续必须补时间控制、空态和 evidenceRefs。 |
| 负债 | 冻结后续映射：`CreditSubjectPie → 债权人拆分`（如需企业/个人层次，必须另有对应事实）；`CreditComboChart → 负债历史、到期负债与偿债能力`。`liability history` 与 `maturity schedule` 等待后续接入，并必须与负债结构共享一套事实。 | 当前只有 debt-sunburst 遗留 CSS、没有 live 组件；本轮不迁。缺少债权人拆分、完整层级债务和到期计划口径时不生成假比例。 |
| 流水 | 冻结后续映射：`FlowChart → 月度流入/流出/净额`、`PartyPiePair → 主要对手方`、`ProfitabilityPanel → 利润/费用`、`RepaymentCoveragePanel → 偿债覆盖`。 | 本轮不进一步重构；旧 `guarantee` 内部名必须归流水，不恢复为第七维。 |

公共交互按需整理 `PanelHeading`、`useDetailFocus/panelClass/itemClass`、`TimeGranularitySwitch`、`TimeSeriesControls`、`YAxisGrid` 与 `TrendAxis`：本轮实际复用标题层级、pointer/focus active/muted、月/季粒度、日期区间、双轴网格和趋势轴计算，未为缺少口径的图表强行挂载公共控件。旧 `itemProps` 只有 tabIndex/role/aria-label 与 hover/focus，没有 click、Enter/Space 或 evidenceRefs；Compare 另外为 native button 和 SVG 图形补齐单次真实激活、稳定 `targetId + evidenceRefs`、`aria-pressed/aria-current` 和 pending/unverifiable 清旧高亮。设备融资使用 `direct-lease`，首付款与融资额从合同总额单一事实派生；若交易结构改为售后回租，必须先冻结转让价、租赁本金、保证金等新口径，不能只换标签。

全局同样冻结 `repaymentTrend` 的真实性门槛：只有真实还款计划的日期、金额、单位和逐点 evidenceRefs 完整时，才能映射到交易融资节奏或后续到期压力；否则保持 pending/unavailable，不用旧估算或随机曲线补齐。

## 2026-08-11

### D-038 · P4 后端基础基线与职责归属

P4 基础后端与 B4.1 契约交接以 `152 passed`、15 条 OpenAPI 路径、24 个确定性脱敏项目和真实 SQLite service 接线作为冻结基线。Back-1 继续拥有 HTTP、Pydantic 契约、统一 envelope/error 与 API 集成；Back-2 拥有 SQLite、项目隔离、幂等、乐观并发、不可变审查链和重启持久化；Back-3 拥有六维领域规则、设备/行业 fixtures、确定性 generator、时序与证据覆盖。后续只有真实联调缺陷命中对应所有权时才续接该 task，不以并行开发扩大功能。

### D-039 · P4 后续采用单纵切、小步串行 Gate

后续固定顺序为文档同步、adapter 契约样本、只读链、写入链和 24 项 MVP Gate。Front 未替换 `MockWorkbenchGateway` 前，只能称后端可运行，不能称前后端已联调。每个小包完成后由 Control 检查实际 diff、聚焦测试、全量回归和运行证据；发现需要改变字段、错误语义、项目隔离或产品流程的卡点时停止并由用户确认。

### D-040 · 模型接口与确定性核心后端隔离

未来模型信息处理接口另立 `P4-AI-Back`。模型只可输出有来源、可追踪的结构化建议或草稿，不直接生成已核验事实，不修改 `scoreGrade / decisionGrade / confidence / evidence / hard gate` 的权威状态，也不绕过共同审查或审批 Gate。该任务不得与当前 Front adapter 或 P4 核心后端修复混包。

### D-041 · P4 以本地 MVP、AI 前置与文档 Gate 收敛

P4 的功能与 Gate 已在核心本地 MVP 基线 `919d72c47b9817b4d409093a038246207b6de80c` 后完成，待最终 Git 冻结。AI 前置共 8 个正式文件：AI Assist C0 契约、Material Intelligence C1（精确 SourceAnchor、声明式 SceneSpec）契约，以及内部 AI Assist Harness 和测试。它们没有公开路由、真实 provider、模型调用、OCR/3D runtime、SQLite 核心写入或 Front AI 入口；不得把这些前置产物表述为已接入真实模型或已完成 AI 业务纵切。

### D-042 · P5 采用权限、受控 AI 与部署准备的单写入者纵切

P5 在 P4 最终 Git 冻结后，由 Control 串行拆分最终 Front 小范围收束、认证/角色/项目与材料权限、脱敏视图与审计对齐、复用既有契约与 Harness 的受控 AI provider/API 纵切，以及独立环境、配置/密钥、运行存储、健康/日志、备份恢复、启动与部署说明。真实 provider 必须受权限、超时、结构校验和日志脱敏约束；失败只能进入稳定失败或人工复核，不得静默回退为权威结果。

### D-043 · P5 保持产品真相与平台边界

P5 默认不大改页面，不改变六维、全局风险、评分、证据、confidence、制度结果、hard gate 或审批权威链；AI 只产生可溯源辅助内容。P5 不建设通用 OCR/Office/3DGS 平台，不把公开素材冒充客户原件，也不在未单独授权时安装依赖、真实部署或接入真实客户材料。

### D-044 · P5-MVP 候选必须经过显式人工 Gate

Material Intelligence 只产生 SourceAnchor、Observation、未决项和字段候选。Front 只能在用户填写人工核对理由并点击确认后调用候选确认路径；服务端负责生成 FactVersion、制度结果、共同事件和审批状态。缺失、不可核验或 provider 失败只降低置信度或进入人工复核，不自动拒绝，也不静默写入权威事实。

### D-045 · SourceAnchor 与 evidence 采用稳定 ID 映射

Material Intelligence 的 evidence ref 冻结为 `ev-mi-${sourceAnchorId}`。Front 必须按 SourceAnchor ID 直接构造并校验 ref，不得用 `sourceAnchors` 与 `evidenceRefs` 的数组位置建立关系；后端查询排序变化不能改变精确 locator。多锚点乱序是正式回归场景。

### D-046 · 工业演示视觉采用六行业派生基底与项目级唯一原件

P5 保留六行业、每行业覆盖现场、设备产线、铭牌、工艺、原材料、成品的高信息合成基底；交付给项目的 7 张 `2048×1152` PNG（含设备总览）按项目确定性构图、色度和显式 synthetic 标识生成。24 项共 168 个项目 URL 和 168 个唯一 SHA-256，不再把同一文件复制给四个项目。项目 01 使用独立 ImageGen 金属精密加工基底，其余项目使用六行业基底的确定性项目变体；不得把这一交付描述为 24 次独立真实拍摄。所有图像都是脱敏合成演示，不是客户现场、厂商照片或事实证据。

### D-047 · SceneSpec 只能声明式受控渲染

Front 只消费 SceneSpec 的 `cameraPreset / objects / hotspots` 枚举与数值，通过现有 Canvas/CSS 绘制并让 hotspot 联动 SourceAnchor/evidence；无 spec 显式空态。禁止执行 provider 返回代码或注入 HTML，也不得将示意称为测绘、CAD、真实三维扫描或 3DGS。

### D-048 · 24 套原始材料是后端输入，不进入 Git

P5 为固定 24 项各生成 36 个项目级业务原件和一个可上传 ZIP，统一位于已忽略的 `Back/runtime/native-material-packs`。Excel、PDF、图片、媒体清单和 SceneSpec 的文件 SHA-256 写入 manifest；每包另含一个由 SceneSpec/媒体清单引用的 GLB 伴随资产，但不计作第 37 份权威业务原件。ZIP、解压项目总量和单原件分别受 100 MiB Gate；100 MiB 是上限而不是体积目标，禁止用随机噪声或无意义填充撑包。全新 SQLite seed 只有在项目 ID、材料 ID 和文件哈希一致时才把 v1 MaterialVersion 绑定到原件。上传只暂存，preflight 只读，人工确认后才执行版本化导入；相同项目、材料 ID 和内容哈希复用既有版本，只有内容改变才创建 vNext。模型/规则候选仍须人工确认才能进入 FactVersion。旧数据库不删除、不静默重写，也不冒充已绑定原件。

### D-049 · ModelGateway golden truth 后置加载，真实评测默认硬关闭

ModelGateway 评测把公开 synthetic provider 输入与 hidden golden truth 物理分离；provider 调用全部结束后才加载 truth 计分，公开 case 类型不含答案字段。标准顺序固定为六行业各一项 smoke，通过后再运行 24 项标准集；每项只选择一份代表材料，不对 864 份原件进行无边界模型调用。

发布指标必须分别报告字段准确性、locator 有效性、schema 通过率、SceneSpec 安全、candidate/人工确认隔离和失败降级，不能合成一个模糊总分，更不能与 `scoreGrade`、`decisionGrade`、confidence、evidence 或 hard gate 混用。synthetic fake、adapter fake transport 和真实 provider 实调是三种不同证据；真实评测默认 `0 calls / 0 budget`，只有独立显式授权、凭据、正数预算与停止条件齐备时才能开启。候选始终 advisory-only，任何评测通过都不越过人工确认 Gate 或写入权威事实。

### D-050 · 材料换版只投影当前态，不改写历史证据

DataPack 从 v1 导入到 v2 时，v1 evidence、SourceAnchor 和 locator 作为不可变审计历史保留；当前 workbench 不能把针对旧原件验证的 locator 复制到新版本。若现有 `located` evidence 的 `materialVersionId` 不等于材料当前版本，当前态统一投影为 `pending / review / locator=null`，重新运行 intelligence 并经人工确认后才建立 v2 证据与 FactVersion 链。该规则已由完整 ZIP rollover RuntimeQA 验证通过。

### D-051 · real mode 接线与真实外部调用必须分开陈述

ProductionWire 的 real mode 表示生产 adapter/Gateway/recorder 路径已接线，不等于发生过外部 Provider API 调用。无 `OPENAI_API_KEY` 时必须在材料读取和网络访问前返回 `provider_not_configured`；startup、health、capabilities 和 seed 不得触发外调。显式 mock transport 可验证首执行恰好 1 次与幂等 replay 0 次，但仍属于 mock 证据。Provider 必须严格校验 `contentHash`、材料/版本身份和 `sourceAnchors`，再派生 `locatorBindings`；绑定漂移、身份伪造或权威字段一律 fail closed。

### D-052 · R3 语义职责与生产包装职责分别过 Gate

BlindEval v1 `76.3864` **FAIL** 和 R2 `30` **FAIL** 保留为不可改写基线。R3 模型职责只产 advisory-only 的 `MaterialIntelligenceResult`，不因缺少 gateway envelope 或 `inputHash` 被重复惩罚；冻结 v2 rubric 下 semantic `92.8596` **PASS**。canonical input hash、生产 envelope、材料绑定、`sourceAnchors`/`locatorBindings` 投影、脱敏记录和幂等调用由独立 ProviderReplay Gate 验证，3/3 **PASS**。这两项均为 offline Codex/mock replay，不能表述为真实外部 API 实调、统计验证模型或生产部署；候选仍须人工确认，`FactVersionWrites` 必须为 0。

### D-053 · 非核心历史资产采用本地可恢复封存

`Show/`、`Compare/Front/artifacts/`、`Compare/Front/legacy/`、`Compare/original.html`、`Compare/deep-research-report.md` 和 `Compare/JW-Deep-Research-VNext-交接包.md` 从核心产品工作区移出，统一可恢复地封存到 `C:\Users\22673\Desktop\JW-Archive\P5-Core-Scope-20260812`。Git 删除必须通过用户授权后的正常 commit/push 收敛，不用 reset/clean 隐藏。`Back/runtime/**` 继续只在本机保留且不进入 Git；3 张公开参考图的带元数据原件保存在封存目录，工作区版本使用已清元数据副本。

### D-054 · 公开仓库只保留 Compare 核心

仓库根目录旧 `Front/`、旧 `Back/`、旧 `README/HANDOFF/scripts` 与 `Show/` 均属于 Compare 形成前的历史交付面；当前运行链只使用 `Compare/Front` 与 `Compare/Back`。P5 收敛提交从公开主线移除这些历史源码和演示 HTML，并在本机封存目录保留可恢复副本。本机未跟踪的 Python 虚拟环境、依赖缓存和 Compare runtime 可以继续用于验证，但不得进入 Git。

## 2026-08-13

### D-055 · 三辅助角色共享一个服务端单焦点协作会话

Compare 保留 `business / risk / leadership` 三个项目内辅助角色，但不采用多频道、双焦点或并行 Agent。一个 thread 任意时刻只有一个服务端 `focusRole`；新 thread 固定从 business 开始，business 可短暂交给 risk 或 leadership，后二者成功完成 turn 后服务端自动返回 business。该决定覆盖本日早期未发布的多频道 ACL、领导治理 version、模型 handoff 和最多三步自动协调候选，不把这些已删除能力继续写成治理控制。

焦点只能通过服务端 `focus-transitions` 修改，并携带 `expectedVersion + Idempotency-Key`；每次创建、迁移、切换、自动返回、关闭、协作拒绝和重开都写入 append-only focus event。同一 thread 最多一个 active run，一次 turn 最多一个 Provider call 和一个 step。risk 的 `reject` 只结束协作会话，不产生正式项目拒绝或审批结论。

Agent 域只保存 thread、message、run、run-step、focus event 与幂等记录。输出固定 `advisoryOnly=true`，不得写入或伪装成 evidence、FactVersion、评分、confidence、PolicyResult、hard gate、approval 或正式 `review_events`。只有人工复核、必要编辑并显式调用既有正式 API 后，内容才可能进入权威链。

本地 API 的 `X-Compare-Role` 只是 simulated principal，不是登录、认证、真实用户、项目成员关系或生产 RBAC。正常 Agent chat 默认 `real + glm_cli + glm-5.2`；`synthetic` 只保留为显式开发/测试 override。real 模式不回退 synthetic，tool attempt、模型身份不符、非法结构、越权 citation、权威声明、超时或不可用均 fail closed。当前单焦点 v3 已通过本机 CLI 与共享 `4317 → 8000` 脱敏 smoke，证明 invocation、provenance、用量和失败关闭路径；该证据不等于内容质量、外部网络核验、SLA 或生产发布验证。冻结契约与证据见 `Back/docs/AGENT-CONVERSATION-CONTRACT.md`。

### D-056 · P5 v2 原件矩阵覆盖旧 36 份技术目录口径

当前 P5 输入固定为 24 项 × 56 份业务原件，共 1344 份唯一 SHA-256；每项为 21 个 Excel、14 个 PDF、21 张 `2048×1152` PNG，按 `基本证照 / 经营证明 / 现场照片 / 增信 / 租赁标的` 五类 Windows 业务目录组织。该决定覆盖 D-046、D-048 和 D-049 中 7 图、36 份、864 份及 `images/pdf/excel/media/scene` 技术目录口径，但保留它们作为历史演进记录。

`manifest.json` 只登记 `originals/` 下的输入原件；`derived/scene-spec.json`、`factory-layout.glb` 与图像 provenance 是后端处理结果或渲染伴随资产，不进入原件计数、业务目录或权威事实。原始材料仍为完整脱敏的 synthetic demo，不得描述为真实客户、真实拍摄、真实三维扫描或统计验证样本。单 ZIP、解压项目总量和单原件继续分别受 100 MiB 上限；真实外部 Provider、认证权限、生产隐私审计和二进制资产发布策略仍须独立 Gate。

### D-057 · 原始图片与设备可视化分层，真实 3GS 移交 P6

右侧“原始材料”和设备流程中的图片只展示同一项目、同一设备或同一现场的原始文件；图片通过 `originalUrl`、`materialId` 与 locator 绑定。视觉层不在图面或紧邻区覆盖 synthetic、脱敏、派生等技术说明，但底层分类、审计和项目文档继续保留真实性边界。项目照片预览可裁去源图底部固定技术页脚，必须保持原始宽高比例，并按相同可见高度比例重映射图片 locator。

现有 `derivedModelRef/modelPreset` 不能证明与同一设备的实拍、型号和配置一一对应，P5 不得把通用 Canvas/SceneSpec 表现为该设备的 3D。P6 设备可视化采用两层互补能力：3GS 只由同一设备或现场的真实多视角实拍形成外观/现场重建，并只呈现有实拍证据支持的可观测面；结构化设备模型/SceneSpec 只由已确认型号和配置生成，用于尺寸比例、关键部件、点击展开和受控运行动画。两层必须共享 `equipmentLineId/configId` 和证据回跳，但使用独立版本、覆盖率、置信度和未知面；无足够视角不得虚构俯视/仰视，配置不明不得假装精确。

### D-058 · 最终结论层是只读投影，不是新的权威结论表

负责人/领导上报视图只能从现有工作台、正式共同审查、制度结果、审批状态和最新单焦点 Agent 会话生成服务端只读投影，不新增可被 AI 写入的“最终结论”权威表。报告必须并列保留 risk level、`scoreGrade`、`decisionGrade`、confidence、evidence、hard gate 和 approval，不以摘要或一个等级覆盖它们。

Agent 建议只可作为带 role、provider/model/prompt 与 input/context/output hash 的 advisory-only 附件出现；无会话时必须明确空态。报告可打印或导出 Markdown，但不会自动提交、完成、退回或拒绝项目。AI 价值只使用当前记录可复核的整理数、未决项/追问数、引用数、消息数和焦点切换数，表达减少人工整理、追问和界面切换；禁止宣称自动审批、替代人工、真实模型质量、外部网络核验、统计收益或已兑现的时间/利润。

### D-059 · 三栏协作界面以中栏共享投影替代第三个聊天窗口

协同区固定为三栏：左侧用户与 business Agent 自由项目对话，右侧用户与 risk Agent 自由项目对话；业务仍是默认主会话，risk 仅在需要时短暂接管服务端焦点。材料、维度、历史业务/风控条目都是可选引用上下文，用户不选择任何上下文也可以提交项目开放问题。

中栏不是 leadership 普通聊天，也不是新的权威事实链。它只按真实 `createdAt + sequence` 从早到晚投影材料定位、明确待回复问题、用户或角色显式确认的协调结论与服务端焦点事件；左右探索、假设和草稿不得自动进入。共享项必须有明确来源或引用，且永远保持 advisory-only，不生成 FactVersion、PolicyResult、hard gate、approval 或正式 `review_events`。

中栏顶部的领导协调摘要只包含六维 grade 色、短名称、`MM-DD HH:mm` 更新时间和待回复摘要；全局风险不进入六标，状态带不可点击跳转，不与左侧六维导航重复，也不把 score、decision、confidence、evidence 或 Gate 混为一个状态。
