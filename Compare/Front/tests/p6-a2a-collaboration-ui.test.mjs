import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("collaboration embeds one chronological group chat under original materials", async () => {
  const [panel, material, app, css] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(panel, /a2a-group-chat/);
  assert.match(panel, /自然时序 · 仅业务与风控/);
  assert.match(panel, /agentMessages\.filter\(\(message\) => message\.role !== "leadership"\)/);
  assert.doesNotMatch(panel, /a2a-project-board|ProjectBoard|DIMENSION_IDS/);
  assert.match(material, /material-chat-slot/);
  assert.match(material, /<A2ACollaborationPanel/);
  assert.match(material, /chatCollapsed/);
  assert.match(material, /material-split-divider/);
  assert.doesNotMatch(material, /material-split-toggle/);
  assert.match(material, /LAYOUT_LIMITS\.collaborationRatio/);
  assert.match(app, /has-embedded-chat/);
  assert.doesNotMatch(app, /<CollaborationDock/);
  assert.match(css, /\.material-pane\.has-project-chat[\s\S]*var\(--layout-source-share\)[\s\S]*var\(--layout-chat-share\)/);
  assert.match(css, /\.workbench-body\.has-embedded-chat[\s\S]*44px minmax\(0, 1fr\)/);
  assert.match(css, /\.material-pane\.has-project-chat\.is-chat-maximized/);
  assert.doesNotMatch(css, /\.material-split-toggle/);
});

test("group composer defaults to plain chat and exposes only Business and Risk Agent routes", async () => {
  const [panel, app] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
  ]);
  assert.match(panel, /useState<ChatAgentRole \| null>\(null\)/);
  for (const option of ["普通聊天", "@业务", "@风控"]) assert.match(panel, new RegExp(option));
  assert.doesNotMatch(panel, /@系统/);
  assert.doesNotMatch(app, /submitChatMessage\("leadership"/);
  assert.match(panel, /消息已发送 · 未触发 Agent/);
  assert.match(app, /gateway\.postAgentMessage/);
  assert.match(app, /if \(!targetAgentRole\) return/);
  assert.match(app, /targetAgentRole, sourceMessageId: postedMessage\.id/);
  assert.doesNotMatch(app, /prepareAgentFocus/);
});

test("the project board is removed while formal business correction remains a review Human Gate", async () => {
  const [panel, review] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
  ]);
  assert.doesNotMatch(panel, /DIMENSION_IDS|issueCounts|a2a-project-board/);
  assert.match(review, /FormalBusinessCorrection/);
  assert.match(review, /Human Gate/);
  assert.match(review, /onCorrection/);
});

test("composer supports configurable Enter sending and keeps Voice and MCP placeholders", async () => {
  const panel = await readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8");
  assert.match(panel, /!settings\.sendOnEnter \|\| event\.key !== "Enter"/);
  assert.match(panel, /event\.preventDefault\(\); void submit\(\);/);
  assert.match(panel, /Material package/);
  for (const tool of ["Voice input placeholder", "MCP tools placeholder"]) assert.match(panel, new RegExp(tool));
  assert.doesNotMatch(panel, /Agent settings placeholder/);
  assert.match(panel, /a2a-send-spinner/);
  assert.match(panel, /正在发送消息/);
  assert.match(panel, /reference \? <div className=\{`a2a-reference/);
  assert.match(panel, /mentionPattern = \/\^@\(业务\|风控\)/);
  assert.match(panel, /chooseTarget\(item\.value, item\.label\)/);
  assert.match(panel, /ref=\{textareaRef\}/);
  assert.match(panel, /requestAnimationFrame\(\(\) => textareaRef\.current\?\.focus\(\)\)/);
  assert.match(panel, /disabled=\{pending \|\| importPending \|\| !messageBody\}/);
});

test("settings is a visual dashboard and never a third Agent", async () => {
  const [panel, dashboard, css, contracts] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/AgentSettingsDashboard.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
    readFile(new URL("src/contracts/agentCommunication.ts", root), "utf8"),
  ]);
  assert.match(contracts, /ChatAgentRole = Exclude<AgentRole, "leadership">/);
  assert.match(panel, /打开 Agent 设置 Dashboard/);
  assert.match(panel, /<Icon name="settings" \/><\/button>/);
  assert.doesNotMatch(panel, /<Icon name="settings" \/>\{copy\(locale, "Settings", "设置"\)\}/);
  assert.match(panel, /全屏项目群聊/);
  assert.match(panel, /退出项目群聊全屏/);
  assert.match(panel, /<Icon name=\{maximized \? "collapse" : "expand"\} \/>/);
  assert.match(panel, /设置不参与发言/);
  assert.match(panel, /canParticipate = accountRole === "business" \|\| accountRole === "risk"/);
  assert.match(dashboard, /双 Agent 协作 Dashboard/);
  for (const setting of ["回车发送", "自动滚动", "紧凑消息", "显示技术来源"]) assert.match(dashboard, new RegExp(setting));
  for (const metric of ["可见消息", "业务回复", "风控回复", "证据引用"]) assert.match(dashboard, new RegExp(metric));
  assert.match(dashboard, /正式审批与 hard Gate/);
  assert.match(css, /\.agent-settings-dashboard/);
  assert.match(css, /\.agent-settings-metrics/);
});

test("explicit Agent mentions map truthful in-flight and failed states without exposing hidden reasoning", async () => {
  const [contracts, app, panel, css] = await Promise.all([
    readFile(new URL("src/contracts/agentCommunication.ts", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(contracts, /phase: "thinking" \| "failed"/);
  assert.match(app, /setAgentActivity\(\{ sourceMessageId: postedMessage\.id/);
  assert.match(app, /Agent 回复已生成，但群聊刷新失败/);
  assert.doesNotMatch(panel, /这里显示处理状态，不展示隐藏推理/);
  assert.match(panel, /agentBusy=\{agentActivity\?\.phase === "thinking"\}/);
  assert.match(css, /\.a2a-agent-activity/);
  assert.match(css, /prefers-reduced-motion/);
});

test("material annotations prefer exact evidence elements and keep OCR regions pending until human confirmation", async () => {
  const [contracts, app, material, panel, http] = await Promise.all([
    readFile(new URL("src/contracts/agentCommunication.ts", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/gateway/httpWorkbenchGateway.ts", root), "utf8"),
  ]);
  assert.match(contracts, /kind: "material_annotation"/);
  assert.match(contracts, /locatorMethod: "element" \| "ocr_region"/);
  assert.match(material, /annotation-element-/);
  assert.match(material, /bboxOverlapScore/);
  assert.match(material, /anchor\.ocrTokenIds\.length > 0/);
  assert.match(material, /canvas\.toDataURL\("image\/jpeg", 0\.82\)/);
  assert.match(material, /Confirm OCR match/);
  assert.match(material, /matchStatus: "confirmed"/);
  assert.match(panel, /Attach annotation/);
  assert.match(panel, /onRequestAnnotation\?\.\(\)/);
  assert.match(panel, /annotationReference \? onAttachAnnotation\(\) : onRequestAnnotation\?\.\(\)/);
  assert.doesNotMatch(panel, /disabled=\{!annotationReference\}/);
  assert.match(material, /requestVisualAnnotation/);
  assert.match(material, /annotationRequestKey/);
  assert.match(material, /onRequestAnnotation=\{requestVisualAnnotation\}/);
  assert.match(panel, /Material annotation snapshot/);
  assert.match(app, /reference\.matchStatus === "pending" \? \[\] : reference\.evidenceTargets/);
  assert.match(app, /messagePayload = \{[^}]*evidenceTargets: context\.evidenceTargets/);
  assert.match(http, /body: \{ content: input\.content, replyToMessageId: input\.replyToMessageId, evidenceTargets: input\.evidenceTargets/);
});

test("settings console pairs a vertical left navigation with a right detail pane", async () => {
  const [dashboard, css] = await Promise.all([
    readFile(new URL("src/components/AgentSettingsDashboard.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(dashboard, /className="agent-settings-console"/);
  assert.match(dashboard, /className="agent-settings-nav"/);
  assert.match(dashboard, /className="agent-settings-detail"/);
  for (const section of ["overview", "routing", "response", "interface", "safety"]) {
    assert.match(dashboard, new RegExp(`"${section}"`));
  }
  for (const label of ["总览", "Agent 路由", "回复偏好", "界面行为", "安全边界"]) {
    assert.match(dashboard, new RegExp(label));
  }
  assert.match(css, /\.agent-settings-console \{[^}]*grid-template-columns: 176px minmax\(0, 1fr\)[^}]*\}/);
  assert.match(css, /\.agent-settings-nav \{[^}]*flex-direction: column[^}]*\}/);
  assert.match(css, /\.agent-settings-nav button\.is-active/);
  assert.match(css, /\.agent-settings-detail \{/);
});

test("overview renders accessible donut, bars, and cumulative sparkline with visible values", async () => {
  const [dashboard, css] = await Promise.all([
    readFile(new URL("src/components/AgentSettingsDashboard.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(dashboard, /agent-chart-donut/);
  assert.match(dashboard, /消息构成环形图：人工消息/);
  assert.match(dashboard, /agent-chart-bars/);
  assert.match(dashboard, /Agent 回复条形图：业务 Agent 回复/);
  assert.match(dashboard, /agent-chart-line/);
  assert.match(dashboard, /Agent 消息累计折线图：按消息序号/);
  assert.ok((dashboard.match(/role="img"/g) ?? []).length >= 3, "all three charts must expose role=img with Chinese aria-labels");
  assert.match(dashboard, /strokeDasharray/);
  assert.match(dashboard, /<polyline/);
  assert.match(dashboard, /cumulativeAgentMessages/);
  assert.match(dashboard, /\{businessReplies\}/);
  assert.match(dashboard, /\{riskReplies\}/);
  assert.match(dashboard, /\{latestCumulative\}/);
  assert.match(css, /\.agent-chart \{/);
  assert.match(css, /\.agent-chart-line \.agent-line-path/);
  assert.match(css, /\.agent-bar-row/);
});

test("response preferences keep a fixed concise three-step format", async () => {
  const [dashboard, contract] = await Promise.all([
    readFile(new URL("src/components/AgentSettingsDashboard.tsx", root), "utf8"),
    readFile(new URL("src/contracts/agentCommunication.ts", root), "utf8"),
  ]);
  assert.match(contract, /AgentResponseDepth = "brief" \| "balanced" \| "detailed"/);
  assert.match(contract, /AgentResponseFocus = "balanced" \| "risk" \| "evidence" \| "next_steps"/);
  assert.match(dashboard, /responseDepth: AgentResponseDepth/);
  assert.match(dashboard, /responseFocus: AgentResponseFocus/);
  assert.match(dashboard, /responseDepth: "brief",/);
  assert.match(dashboard, /responseFocus: "balanced",/);
  assert.match(dashboard, /customGuidance: "",/);
  assert.match(dashboard, /className="agent-settings-fixed-format"/);
  assert.match(dashboard, /最多 220 字/);
  for (const step of ["定位类别", "核心数据与判断", "一个下一步动作"]) assert.match(dashboard, new RegExp(step));
  assert.doesNotMatch(dashboard, /id="agent-response-depth"/);
  assert.match(dashboard, /id="agent-response-focus"/);
  assert.match(dashboard, /maxLength=\{500\}/);
  assert.match(dashboard, /\{customGuidance\.length\}\/500/);
  assert.match(dashboard, /每条 Agent 回复固定三步/);
  assert.match(dashboard, /不能突破短答与权限边界/);
});

test("Agent messages render one concise body without duplicate machine appendices", async () => {
  const [panel, dashboard] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/AgentSettingsDashboard.tsx", root), "utf8"),
  ]);
  assert.doesNotMatch(panel, /a2a-structured-line/);
  assert.doesNotMatch(panel, /项目判断/);
  assert.match(panel, /showProvenance && message\.execution/);
  assert.match(dashboard, /showProvenance: false/);
});

test("routing stays limited to business and risk while existing settings remain", async () => {
  const dashboard = await readFile(new URL("src/components/AgentSettingsDashboard.tsx", root), "utf8");
  assert.match(dashboard, /enabledAgents: \{ business: true, risk: true \}/);
  assert.match(dashboard, /toggleAgent\("business", checked\)/);
  assert.match(dashboard, /toggleAgent\("risk", checked\)/);
  assert.doesNotMatch(dashboard, /leadership/);
  for (const metric of ["可见消息", "业务回复", "风控回复", "证据引用"]) assert.match(dashboard, new RegExp(metric));
  for (const setting of ["回车发送", "自动滚动", "紧凑消息", "显示技术来源"]) assert.match(dashboard, new RegExp(setting));
  assert.match(dashboard, /update\("sendOnEnter", checked\)/);
  assert.match(dashboard, /update\("autoScroll", checked\)/);
  assert.match(dashboard, /update\("compactMessages", checked\)/);
  assert.match(dashboard, /update\("showProvenance", checked\)/);
});
