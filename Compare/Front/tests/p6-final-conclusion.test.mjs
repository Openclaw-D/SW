import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { HttpWorkbenchGateway } from "../src/gateway/httpWorkbenchGateway.ts";
import { MockWorkbenchGateway } from "../src/gateway/mockWorkbenchGateway.ts";
import { buildConclusionMarkdown } from "../src/lib/conclusionReport.ts";
import { buildCollaborationStream } from "../src/lib/collaborationStream.ts";

const root = new URL("../", import.meta.url);
const meta = { requestId: "conclusion-request", schemaVersion: "1.0", dataStatus: "simulated", source: "server_conclusion_projection", disclaimer: "read only" };

function envelope(data) {
  return new Response(JSON.stringify({ data, meta, errors: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
}

test("conclusion HTTP read uses one project-scoped GET without a principal or write metadata", async () => {
  let call;
  const payload = { schemaVersion: "1.0", projectId: "project / 01" };
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1/", fetchImpl: async (url, init) => {
    call = { url: String(url), init };
    return envelope(payload);
  } });
  assert.deepEqual(await gateway.readConclusionReport("project / 01"), payload);
  assert.equal(call.url, "http://api.test/api/v1/projects/project%20%2F%2001/conclusion");
  assert.equal(call.init.method, "GET");
  assert.equal(call.init.body, undefined);
  assert.deepEqual(call.init.headers, { Accept: "application/json" });
});

test("conclusion HTTP errors remain explicit and never fall back to a local report", async () => {
  const response = new Response(JSON.stringify({ data: null, meta, errors: [{ code: "conclusion_unavailable", category: "internal", message: "结论投影暂不可用" }] }), { status: 503, headers: { "Content-Type": "application/json" } });
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async () => response });
  await assert.rejects(() => gateway.readConclusionReport("project-a"), (error) => error?.code === "transport" && error?.httpStatus === 503 && /结论投影暂不可用/.test(error.message));
});

test("Agent HTTP turn uses the session principal and idempotency without a role header", async () => {
  let call;
  const payload = { turnId: "turn", runId: "run", status: "completed", focusRole: "business", currentFocusRole: "business", messages: [], nextExpectedVersion: 2, execution: {}, advisoryOnly: true, schemaVersion: "2.0" };
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async (url, init) => {
    call = { url: String(url), init };
    return envelope(payload);
  } });
  await gateway.executeAgentTurn({ projectId: "project / 01", threadId: "agent-thread-01", principal: "business", targetAgentRole: "risk", sourceMessageId: "agent-message-01", instruction: "开放问题", replyToMessageId: null, evidenceTargets: [], expectedVersion: 1, locale: "zh-CN", responseDepth: "detailed", responseFocus: "evidence", customGuidance: "先列证据缺口", idempotencyKey: "agent-turn-0001" });
  assert.equal(call.url, "http://api.test/api/v1/projects/project%20%2F%2001/agents/threads/agent-thread-01/turns");
  assert.equal(call.init.method, "POST");
  assert.equal(call.init.headers["X-Compare-Role"], undefined);
  assert.equal(call.init.credentials, "include");
  assert.equal(call.init.headers["Idempotency-Key"], "agent-turn-0001");
  assert.deepEqual(JSON.parse(call.init.body), { instruction: "开放问题", targetAgentRole: "risk", sourceMessageId: "agent-message-01", replyToMessageId: null, evidenceTargets: [], expectedVersion: 1, locale: "zh-CN", responseDepth: "detailed", responseFocus: "evidence", customGuidance: "先列证据缺口" });
});

test("mock conclusion keeps grades, confidence, evidence and human Gate visibly separate", async () => {
  const gateway = new MockWorkbenchGateway();
  const [catalogProject] = await gateway.listProjects();
  const report = await gateway.readConclusionReport(catalogProject.projectId);
  assert.equal(report.dimensions.length, 6);
  assert.deepEqual(Object.keys(report.overall).sort(), ["confidence", "decisionGrade", "riskLevel", "scoreGrade", "summary"]);
  assert.equal(report.humanConfirmation.required, true);
  assert.equal(report.advisoryOnly, true);
  assert.equal(report.collaboration.hasThread, false);
  assert.equal(report.collaboration.latestAdvice, null);
  assert.equal(Object.values(report.evidenceStatusCounts).reduce((sum, count) => sum + count, 0), report.evidenceTotal);
  assert.match(report.aiValue.summary, /减少人工整理、逐项追问和页面切换/);
  assert.match(report.aiValue.summary, /不代表自动决策、模型准确率/);
});

test("downloadable Markdown carries the same decision boundary and traceable sections", async () => {
  const gateway = new MockWorkbenchGateway();
  const [catalogProject] = await gateway.listProjects();
  const report = await gateway.readConclusionReport(catalogProject.projectId);
  const markdown = buildConclusionMarkdown(report);
  assert.match(markdown, /## 六维认定/);
  assert.match(markdown, /评分等级 \| 决策等级 \| 置信度/);
  assert.match(markdown, /## 制度 Gate 与人工确认/);
  assert.match(markdown, /## 关键证据/);
  assert.match(markdown, /## 未决项/);
  assert.match(markdown, /尚无 Agent 会话或建议；本报告不会虚构协作结论/);
  assert.match(markdown, /## 可核验的 AI 辅助价值/);
  assert.match(markdown, /报告不执行审批、不替代人工判断/);
});

test("default workbench exposes the read-only report as an explicit action and keeps a compact non-navigation leadership context band", async () => {
  const [app, topBar, collaborationDock, reportView, css] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/TopBar.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/components/FinalConclusionReport.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  const contextBandSource = collaborationDock.slice(collaborationDock.indexOf("function CoordinationContextBand"), collaborationDock.indexOf("function SharedStreamEvent"));
  assert.match(app, /FinalConclusionReport/);
  assert.match(app, /conclusionOpen/);
  assert.match(app, /openConclusionReport/);
  assert.match(app, /gateway\.readConclusionReport\(projectAtRequest\)/);
  assert.match(topBar, /onOpenConclusionReport/);
  assert.match(topBar, /Open project conclusion report/);
  assert.match(app, /dimensions=\{data\.dimensions\}/);
  assert.doesNotMatch(app, /onDimensionNavigate/);
  assert.match(contextBandSource, /DIMENSION_IDS\.flatMap/);
  assert.match(contextBandSource, /领导协调六维状态摘要/);
  assert.match(contextBandSource, /data-grade=\{dimension\.scoreGrade\}/);
  assert.match(contextBandSource, /GRADE_COLOR_VARS\[dimension\.scoreGrade\]/);
  assert.match(contextBandSource, /latestItem\?\.createdAt/);
  assert.match(contextBandSource, /items\.filter\(\(item\) => item\.pending\)/);
  assert.match(contextBandSource, /待回复问题/);
  assert.match(contextBandSource, /暂无待回复协调问题/);
  assert.doesNotMatch(contextBandSource, /<button|onNavigate|dimension\.score(?!Grade)|decisionGrade|confidence|evidence|\bgate\b/i);
  assert.match(reportView, /aria-modal="true"/);
  assert.match(reportView, /刷新/);
  assert.match(reportView, /window\.print\(\)/);
  assert.match(reportView, /下载 Markdown/);
  assert.match(reportView, /document\.body\.append\(anchor\)/);
  assert.match(reportView, /setTimeout\(\(\) => URL\.revokeObjectURL/);
  assert.match(reportView, /关闭结论报告/);
  assert.match(reportView, /尚无 Agent 会话或建议；报告不会虚构协作结论/);
  assert.match(css, /grid-template-columns: repeat\(6, minmax\(0, 1fr\)\)/);
  assert.match(css, /\.shared-column \{ grid-template-rows: 42px auto minmax\(0, 1fr\); \}/);
  assert.match(css, /\.coordination-status-node > time/);
  assert.match(css, /\.coordination-pending-summary/);
  assert.match(css, /@media print/);
  assert.match(css, /height: min\(94dvh, 980px\)/);
  assert.match(css, /overflow: auto/);
});

test("Agent dialogue keeps context optional, uses P6 turns and formats compact timestamps", async () => {
  const [app, collaborationDock, collaborationStream] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/lib/collaborationStream.ts", root), "utf8"),
  ]);
  assert.match(collaborationDock, /left\.createdAt\.localeCompare\(right\.createdAt\) \|\| left\.sequence - right\.sequence/);
  assert.match(collaborationStream, /left\.createdAt\.localeCompare\(right\.createdAt\) \|\| left\.sequence - right\.sequence \|\| left\.id\.localeCompare\(right\.id\)/);
  assert.match(collaborationDock, /return `\$\{match\[2\]\}-\$\{match\[3\]\} \$\{match\[4\]\}:\$\{match\[5\]\}`/);
  assert.doesNotMatch(collaborationDock, /createdAt\.slice\(11, 16\)/);
  assert.match(collaborationDock, /aria-pressed=\{referenced\}/);
  assert.match(collaborationDock, /await onSubmit\(message\.trim\(\), reference\)/);
  assert.match(collaborationDock, /可不引用材料、维度或历史条目，直接提交项目开放问题/);
  assert.match(collaborationDock, /取消引用上下文/);
  assert.match(app, /agentSubmissionContext = \(reference: CollaborationContextReference \| null\)/);
  assert.match(app, /replyToMessageId: referencedMessage\?\.id \?\? null/);
  assert.match(app, /gateway\.executeAgentTurn/);
  assert.match(app, /gateway\.postAgentMessage/);
  assert.doesNotMatch(app, /prepareAgentFocus/);
  assert.doesNotMatch(app, /gateway\.submitBusinessAnswer|gateway\.submitRiskQuestion|gateway\.submitRiskAnswer/);
  assert.match(collaborationStream, /message\.authorType !== "agent"/);
  assert.match(collaborationStream, /if \(!targets\.length && !questions\.length\) return null/);
  assert.match(collaborationStream, /服务端焦点事件/);
});

test("collaboration stream excludes ordinary side drafts and keeps only traceable shared items in monotonic order", () => {
  const execution = { mode: "real", providerId: "glm_5_3_coding_plan_cli", modelId: "glm-5.3[1m]", promptVersion: "v3", inputHash: "0".repeat(64), contextVersion: "1".repeat(64), outputHash: "2".repeat(64), advisoryOnly: true, isSimulated: false, dataStatus: "provider_generated_unverified", source: "glm_5_3_coding_plan_cli", disclaimer: "advisory" };
  const message = (overrides) => ({ id: "m", projectId: "p", threadId: "t", sequence: 1, role: "business", authorType: "agent", kind: "agent_reply", content: "draft", citations: [], generatedContent: { replyText: "draft", observations: [], questions: [], citations: [], scopeStatus: "in_scope", disposition: "answer" }, execution, replyToMessageId: null, runId: "run", createdAt: "2026-08-13T08:20:00Z", immutable: true, advisoryOnly: true, isSimulated: false, ...overrides });
  const ordinaryHuman = message({ id: "human", authorType: "human", kind: "user_input", generatedContent: null, execution: null, isSimulated: false });
  const ordinaryAgent = message({ id: "draft-agent" });
  const citedAgent = message({ id: "cited", sequence: 2, createdAt: "2026-08-13T08:21:00Z", citations: [{ evidenceRef: "ev-1", dimensionId: "compliance", reviewTargetId: "r", factVersionId: null }], generatedContent: { replyText: "draft", observations: [], questions: [], citations: [{ evidenceRef: "ev-1", dimensionId: "compliance", reviewTargetId: "r", factVersionId: null }], scopeStatus: "in_scope", disposition: "answer" } });
  const questionAgent = message({ id: "question", sequence: 3, createdAt: "2026-08-13T08:22:00Z", generatedContent: { replyText: "draft", observations: [], questions: ["谁确认验收日期？"], citations: [], scopeStatus: "needs_clarification", disposition: "request_information" } });
  const focus = { id: "focus", projectId: "p", threadId: "t", sequence: 4, kind: "focus_transferred", fromFocusRole: "business", toFocusRole: "risk", actorRole: "business", reason: "复核", expectedVersion: 1, resultingVersion: 2, createdAt: "2026-08-13T08:23:00Z", immutable: true };
  const items = buildCollaborationStream([], [ordinaryHuman, ordinaryAgent, citedAgent, questionAgent], [focus]);
  assert.deepEqual(items.map((item) => item.id), ["agent:cited", "agent:question", "focus:focus"]);
  assert.equal(items[0].sourceLabel.includes("glm_5_3_coding_plan_cli/glm-5.3[1m]"), true);
  assert.equal(items[1].pending, true);
  assert.equal(items[2].kind, "focus_event");
});
