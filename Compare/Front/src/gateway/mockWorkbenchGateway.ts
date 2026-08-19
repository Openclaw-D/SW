import type {
  ApprovalState,
  ApprovalTransitionInput,
  BusinessCorrection,
  BusinessCorrectionResult,
  BusinessCorrectionInput,
  BusinessAnswerInput,
  CollaborationSubmissionResult,
  CommonReviewEvent,
  DimensionSeriesRequest,
  DimensionSeriesResponse,
  HardConstraintResult,
  Material,
  ReviewEvidenceSelectionGroup,
  RiskAnswerInput,
  RiskQuestionInput,
  WorkbenchProject,
} from "../contracts/workbench";
import { PUBLIC_DEMO_PROJECT_COUNT, type ProjectCatalogItem } from "../contracts/projectSelection.ts";
import type { CandidateConfirmationInput, MaterialIntelligenceRunInput } from "../contracts/materialIntelligence";
import { mockWorkbenchProject } from "../mock/mockCase.ts";
import { mockDimensionTimeSeries } from "../mock/p3AdjustData.ts";
import { generateProjectCatalog } from "../mock/projectCatalog.ts";
import { aggregateDimensionTimeSeries, averageScore, resolveEvidenceSelectionGroup, scoreToGrade } from "../lib/workbenchLogic.ts";
import type { ProjectConclusionReport } from "../contracts/conclusion";
import { buildMockConclusionReport } from "../lib/conclusionReport.ts";
import type { AgentExecutionMetadata, AgentFocusEvent, AgentMessage, AgentRole, AgentThread, AgentTurnResult, CreateAgentThreadCommand, ExecuteAgentTurnCommand, PostAgentMessageCommand, TransitionAgentFocusCommand } from "../contracts/agentCommunication";
import { WorkbenchGatewayError, type ApprovalTransitionCommand, type BusinessAnswerCommand, type BusinessCorrectionCommand, type GatewayResponseMeta, type ResolvedEvidenceSelection, type RiskAnswerCommand, type RiskQuestionCommand, type WorkbenchGateway } from "./workbenchGateway.ts";

function clone<T>(value: T): T {
  return structuredClone(value);
}

function replaceTemplateIdentity<T>(value: T, catalogProject: ProjectCatalogItem): T {
  const relatedCompanyName = `${catalogProject.companyShortName}控股有限公司`;
  const projectName = `${catalogProject.companyShortName} ${catalogProject.financingType} · 统一脱敏核验模板`;
  const replacements = [
    ["华东精密制造有限公司", catalogProject.companyName],
    ["华东控股有限公司", relatedCompanyName],
    ["华东精密设备融资", projectName],
    ["华东精密制造", catalogProject.companyShortName],
    ["华东控股", `${catalogProject.companyShortName}控股`],
    ["精密制造", catalogProject.industry],
  ] as const;

  const visit = (current: unknown): unknown => {
    if (typeof current === "string") {
      return replacements.reduce((text, [source, target]) => text.replaceAll(source, target), current);
    }
    if (Array.isArray(current)) return current.map(visit);
    if (current && typeof current === "object") {
      return Object.fromEntries(Object.entries(current).map(([key, item]) => [key, visit(item)]));
    }
    return current;
  };

  return visit(value) as T;
}

function assertNoTemplateIdentityLeak(project: WorkbenchProject) {
  const serialized = JSON.stringify(project);
  const leakedName = ["华东精密制造有限公司", "华东控股有限公司", "华东精密设备融资"]
    .find((name) => serialized.includes(name));
  if (leakedName) {
    throw new WorkbenchGatewayError("validation", `统一脱敏模板仍残留基础项目身份：${leakedName}`);
  }
}

export class MockWorkbenchGateway implements WorkbenchGateway {
  private readonly projects: ProjectCatalogItem[];
  private readonly approvalStates = new Map<string, ApprovalState>();
  private readonly agentThreads = new Map<string, AgentThread>();
  private readonly agentMessages = new Map<string, AgentMessage[]>();
  private readonly agentFocusEvents = new Map<string, AgentFocusEvent[]>();
  private readonly meta: GatewayResponseMeta = { requestId: "mock-local", schemaVersion: "1.0", dataStatus: "simulated", source: "deterministic_business_rules", disclaimer: "local mock" };

  constructor(seed = 20260812, projects?: ProjectCatalogItem[]) {
    this.projects = clone(projects ?? generateProjectCatalog(seed, new Date(2026, 7, 12, 9, 0, 0)).slice(0, PUBLIC_DEMO_PROJECT_COUNT));
  }

  getLastResponseMeta(): GatewayResponseMeta { return { ...this.meta }; }

  async listProjects(): Promise<ProjectCatalogItem[]> {
    return clone(this.projects);
  }

  async loadProject(projectId: string): Promise<WorkbenchProject> {
    const catalogProject = this.projects.find((project) => project.projectId === projectId);
    if (!catalogProject) {
      throw new WorkbenchGatewayError("not_found", "项目不存在");
    }
    const project = replaceTemplateIdentity(clone(mockWorkbenchProject), catalogProject);
    const scoreGrade = scoreToGrade(averageScore(catalogProject.dimensions.map((dimension) => dimension.score)));
    const confidence = Math.round(averageScore(catalogProject.dimensions.map((dimension) => dimension.confidence)));

    project.project = {
      ...project.project,
      id: catalogProject.projectId,
      name: `${catalogProject.companyShortName} ${catalogProject.financingType} · 统一脱敏核验模板`,
      disclaimer: `${project.project.disclaimer} 当前项目使用唯一一套确定性脱敏演示材料，不代表真实客户材料。`,
    };
    project.dimensions = clone(catalogProject.dimensions);
    project.riskSummary = {
      ...project.riskSummary,
      level: catalogProject.riskLevel,
      scoreGrade,
      decisionGrade: catalogProject.decisionGrade,
      confidence,
      summary: `演示规则汇总：风险级别：${catalogProject.riskBand}；材料状态：${catalogProject.materialStatus}；决策等级：${catalogProject.decisionGrade}；置信度：${confidence}%。硬门槛仍以详情规则事实为准，最终认定由人工完成。`,
    };
    project.determinations = project.determinations.map((determination) => {
      const dimension = catalogProject.dimensions.find((item) => item.id === determination.dimensionId);
      return dimension ? {
        ...determination,
        score: dimension.score,
        scoreGrade: dimension.scoreGrade,
        confidence: dimension.confidence,
      } : determination;
    });
    project.corrections = project.corrections.map((correction) => ({ ...correction, projectId }));
    project.reviewEvents = project.reviewEvents.map((event) => ({ ...event, projectId }));
    assertNoTemplateIdentityLeak(project);
    return project;
  }

  async listMaterials(projectId: string): Promise<Material[]> {
    return clone((await this.loadProject(projectId)).materials);
  }

  async readMaterial(projectId: string, materialId: string): Promise<Material> {
    const material = (await this.loadProject(projectId)).materials.find((item) => item.id === materialId);
    if (!material) throw new WorkbenchGatewayError("not_found", "项目内不存在该材料。");
    return clone(material);
  }

  async uploadMaterialPackage(): Promise<never> {
    throw new WorkbenchGatewayError("validation", "Mock 模式不提供仓库外受控导入。");
  }

  async preflightMaterialImport(): Promise<never> {
    throw new WorkbenchGatewayError("validation", "Mock 模式不提供仓库外受控导入。");
  }

  async executeMaterialImport(): Promise<never> {
    throw new WorkbenchGatewayError("validation", "Mock 模式不提供仓库外受控导入。");
  }

  async listModelGatewayCapabilities(): Promise<never> {
    throw new WorkbenchGatewayError("not_found", "Mock 模式没有公共 Model Gateway capability。", { apiCode: "provider_not_configured" });
  }

  async readModelGatewayRun(): Promise<never> {
    throw new WorkbenchGatewayError("not_found", "Mock 模式没有 Model Gateway 运行记录。", { apiCode: "model_run_not_found" });
  }

  async runMaterialIntelligence(_input: MaterialIntelligenceRunInput): Promise<never> {
    throw new WorkbenchGatewayError("not_found", "Mock 模式没有服务端 Material Intelligence 结果。");
  }

  async readMaterialIntelligence(): Promise<never> {
    throw new WorkbenchGatewayError("not_found", "Mock 模式没有服务端 Material Intelligence 结果。");
  }

  async confirmMaterialCandidate(_input: CandidateConfirmationInput): Promise<never> {
    throw new WorkbenchGatewayError("validation", "Mock 模式不能人工确认服务端候选。");
  }

  async readMaterialSceneSpec(): Promise<never> {
    throw new WorkbenchGatewayError("not_found", "Mock 模式没有服务端 SceneSpec。");
  }

  async resolveEvidenceSelection(projectId: string, group: ReviewEvidenceSelectionGroup): Promise<ResolvedEvidenceSelection> {
    const project = await this.loadProject(projectId);
    const resolution = resolveEvidenceSelectionGroup(group, project.evidence, project.materials);
    if (resolution.status !== "located") throw new WorkbenchGatewayError("validation", resolution.message);
    return { status: "located", selectionGroup: resolution.selectionGroup, items: resolution.items.map(({ target, evidence }) => ({ target, evidence })) };
  }

  async queryDimensionSeries(request: DimensionSeriesRequest): Promise<DimensionSeriesResponse> {
    if (!this.projects.some((project) => project.projectId === request.projectId)) {
      throw new WorkbenchGatewayError("not_found", "项目不存在");
    }
    const series = mockDimensionTimeSeries.find((item) => item.dimensionId === request.dimensionId);
    return clone(aggregateDimensionTimeSeries(series, request));
  }

  async submitBusinessCorrection(input: BusinessCorrectionCommand): Promise<BusinessCorrectionResult> {
    this.validateMessage(input.reason);
    const correction: BusinessCorrection = {
      id: "mock-correction-preview",
      ...clone(input),
      status: "submitted",
      createdBy: "business",
      createdAt: new Date(0).toISOString(),
      isSimulated: true,
    };
    return {
      correction,
      factVersion: {
        ...(await this.loadProject(input.projectId)).facts.find((fact) => fact.id === input.fromFactVersionId)!,
        id: `mock-fact-${input.factKey}-${input.expectedVersion ?? 1}`,
        version: (input.expectedVersion ?? 1) + 1,
        value: clone(input.proposedValue),
      },
      event: {
        id: `mock-correction-event-${input.factKey}-${input.expectedVersion}`,
        projectId: input.projectId, sequence: input.expectedVersion, threadId: `fact::${input.factKey}`, replyToEventId: null,
        issueStatus: "answered", eventType: "business_correction_submitted", actor: "business", actorLabel: "业务人员", dimensionId: (await this.loadProject(input.projectId)).facts.find((fact) => fact.id === input.fromFactVersionId)!.dimensionId,
        evidenceTargets: [], reviewTargetId: input.factKey, title: "业务修正", summary: input.reason.trim(), factVersionIds: [], evidenceRefs: [], ruleRefs: [], createdAt: new Date(0).toISOString(), immutable: true, isSimulated: true,
      },
    };
  }

  async submitRiskQuestion(input: RiskQuestionCommand): Promise<CommonReviewEvent> {
    this.validateMessage(input.question);
    return {
      id: `mock-risk-question-${Date.now()}`,
      projectId: input.projectId,
      sequence: 99,
      threadId: input.threadId,
      replyToEventId: input.replyToEventId,
      issueStatus: "open",
      eventType: "risk_question_submitted",
      actor: "risk",
      actorLabel: "风控 AI 辅助",
      dimensionId: input.dimensionId,
      reviewTargetId: input.reviewTargetId,
      title: "风控问题",
      summary: input.question,
      factVersionIds: clone(input.factVersionIds),
      evidenceRefs: clone(input.evidenceRefs),
      ruleRefs: input.dimensionId === "compliance" ? ["H-03@policy-2026.08"] : [],
      createdAt: new Date().toISOString(),
      immutable: true,
      isSimulated: true,
    };
  }

  async submitBusinessAnswer(input: BusinessAnswerCommand): Promise<CollaborationSubmissionResult> {
    this.validateMessage(input.answer);
    return {
      event: this.collaborationEvent("business_answer_submitted", "business", "业务回答", input.answer, input),
      openIssueCount: Math.max(0, mockWorkbenchProject.project.collaborationIssueCount - 1),
    };
  }

  async submitRiskAnswer(input: RiskAnswerCommand): Promise<CollaborationSubmissionResult> {
    this.validateMessage(input.answer);
    return {
      event: this.collaborationEvent("risk_answer_submitted", "risk", "风控意见", input.answer, input),
      openIssueCount: mockWorkbenchProject.project.collaborationIssueCount,
    };
  }

  private validateMessage(message: string) {
    if (!message.trim()) throw new WorkbenchGatewayError("validation", "内容不能为空。");
    if (message.includes("触发失败")) throw new WorkbenchGatewayError("simulated_failure", "提交失败，请稍后重试。");
  }

  private collaborationEvent(
    eventType: "business_answer_submitted" | "risk_answer_submitted",
    actor: "business" | "risk",
    title: string,
    summary: string,
    input: BusinessAnswerInput | RiskAnswerInput,
  ): CommonReviewEvent {
    return {
      id: `mock-${eventType}-${Date.now()}`,
      projectId: input.projectId,
      sequence: 0,
      threadId: input.threadId,
      replyToEventId: input.replyToEventId,
      issueStatus: eventType === "business_answer_submitted" ? "answered" : "pending_gate",
      eventType,
      actor,
      actorLabel: actor === "business" ? "业务 AI 辅助" : "风控 AI 辅助",
      dimensionId: input.dimensionId,
      reviewTargetId: input.reviewTargetId,
      title,
      summary: summary.trim(),
      factVersionIds: clone(input.factVersionIds),
      evidenceRefs: clone(input.evidenceRefs),
      ruleRefs: input.dimensionId === "compliance" ? ["H-03@policy-2026.08"] : [],
      createdAt: new Date().toISOString(),
      immutable: true,
      isSimulated: true,
    };
  }

  async readPolicyResults(projectId: string): Promise<HardConstraintResult[]> {
    const project = await this.loadProjectOrNull(projectId);
    return project ? clone(project.determinations.flatMap((item) => item.hardConstraintResults)) : [];
  }

  async readReviewEvents(projectId: string): Promise<CommonReviewEvent[]> {
    const project = await this.loadProjectOrNull(projectId);
    return project ? clone(project.reviewEvents) : [];
  }

  async readApprovalState(projectId: string): Promise<ApprovalState> {
    if (!this.projects.some((project) => project.projectId === projectId)) throw new WorkbenchGatewayError("not_found", "项目不存在");
    return clone(this.approvalStates.get(projectId) ?? {
      projectId,
      version: 1,
      status: "draft",
      hardGateStatus: "manual_review",
      blockingRuleIds: ["H-03"],
      riskVeto: false,
      riskVetoRuleIds: [],
      updatedAt: new Date(0).toISOString(),
      isSimulated: true,
    });
  }

  async readConclusionReport(projectId: string): Promise<ProjectConclusionReport> {
    const [project, policies, approval, events] = await Promise.all([
      this.loadProject(projectId),
      this.readPolicyResults(projectId),
      this.readApprovalState(projectId),
      this.readReviewEvents(projectId),
    ]);
    return clone(buildMockConclusionReport(project, policies, approval, events));
  }

  async createAgentThread(input: CreateAgentThreadCommand): Promise<AgentThread> {
    if (!this.projects.some((project) => project.projectId === input.projectId)) throw new WorkbenchGatewayError("not_found", "项目不存在");
    const now = new Date().toISOString();
    const id = `agent-thread-${crypto.randomUUID().replaceAll("-", "")}`;
    const thread: AgentThread = { id, projectId: input.projectId, title: input.title, version: 1, status: "active", focusRole: "business", createdByRole: "business", closedReason: null, createdAt: now, updatedAt: now };
    const focusEvent: AgentFocusEvent = { id: `agent-focus-${crypto.randomUUID().replaceAll("-", "")}`, projectId: input.projectId, threadId: id, sequence: 1, kind: "thread_created", fromFocusRole: null, toFocusRole: "business", actorRole: "business", reason: "创建单焦点协作会话。", expectedVersion: 0, resultingVersion: 1, createdAt: now, immutable: true };
    this.agentThreads.set(input.projectId, thread);
    this.agentMessages.set(id, []);
    this.agentFocusEvents.set(id, [focusEvent]);
    return clone(thread);
  }

  async readAgentThread(projectId: string, threadId: string): Promise<AgentThread> {
    return clone(this.requireAgentThread(projectId, threadId));
  }

  async readAgentMessages(projectId: string, threadId: string): Promise<AgentMessage[]> {
    this.requireAgentThread(projectId, threadId);
    return clone(this.agentMessages.get(threadId) ?? []);
  }

  async readAgentFocusEvents(projectId: string, threadId: string): Promise<AgentFocusEvent[]> {
    this.requireAgentThread(projectId, threadId);
    return clone(this.agentFocusEvents.get(threadId) ?? []);
  }

  async transitionAgentFocus(input: TransitionAgentFocusCommand): Promise<AgentThread> {
    const current = this.requireAgentThread(input.projectId, input.threadId);
    if (current.version !== input.expectedVersion || current.focusRole !== input.principal) throw new WorkbenchGatewayError("conflict", "Agent 焦点或版本已变化。", { apiCode: "version_conflict" });
    const allowed = current.focusRole === "business" ? new Set<AgentRole>(["risk", "leadership"]) : new Set<AgentRole>(["business"]);
    if (!allowed.has(input.toFocusRole)) throw new WorkbenchGatewayError("conflict", "该单焦点切换路径不允许。", { apiCode: "agent_focus_transition_invalid" });
    const now = new Date().toISOString();
    const next: AgentThread = { ...current, focusRole: input.toFocusRole, version: current.version + 1, updatedAt: now };
    const focusEvents = this.agentFocusEvents.get(current.id) ?? [];
    focusEvents.push({ id: `agent-focus-${crypto.randomUUID().replaceAll("-", "")}`, projectId: current.projectId, threadId: current.id, sequence: focusEvents.length + 1, kind: input.toFocusRole === "business" ? "focus_returned" : "focus_transferred", fromFocusRole: current.focusRole, toFocusRole: input.toFocusRole, actorRole: input.principal, reason: input.reason, expectedVersion: current.version, resultingVersion: next.version, createdAt: now, immutable: true });
    this.agentThreads.set(input.projectId, next);
    this.agentFocusEvents.set(current.id, focusEvents);
    return clone(next);
  }

  async postAgentMessage(input: PostAgentMessageCommand): Promise<AgentMessage> {
    const current = this.requireAgentThread(input.projectId, input.threadId);
    const messages = this.agentMessages.get(current.id) ?? [];
    if (input.replyToMessageId && !messages.some((message) => message.id === input.replyToMessageId)) {
      throw new WorkbenchGatewayError("not_found", "引用消息不存在。", { apiCode: "agent_reply_message_not_found" });
    }
    const now = new Date().toISOString();
    const message: AgentMessage = {
      id: `agent-message-${crypto.randomUUID().replaceAll("-", "")}`,
      projectId: input.projectId,
      threadId: current.id,
      sequence: messages.length + 1,
      role: input.principal,
      authorType: "human",
      kind: "user_input",
      content: input.content,
      citations: input.evidenceTargets.map((target) => ({ evidenceRef: target.evidenceRef, dimensionId: target.dimensionId, reviewTargetId: target.reviewTargetId, factVersionId: target.factVersionId })),
      generatedContent: null,
      execution: null,
      replyToMessageId: input.replyToMessageId,
      runId: null,
      createdAt: now,
      immutable: true,
      advisoryOnly: true,
      isSimulated: false,
    };
    messages.push(message);
    this.agentMessages.set(current.id, messages);
    this.agentThreads.set(input.projectId, { ...current, updatedAt: now });
    return clone(message);
  }

  async executeAgentTurn(input: ExecuteAgentTurnCommand): Promise<AgentTurnResult> {
    const current = this.requireAgentThread(input.projectId, input.threadId);
    if (current.version !== input.expectedVersion) throw new WorkbenchGatewayError("conflict", "Agent 会话版本已变化。", { apiCode: "version_conflict" });
    const now = new Date().toISOString();
    const messages = this.agentMessages.get(current.id) ?? [];
    const source = messages.find((message) => message.id === input.sourceMessageId);
    if (!source || source.authorType !== "human" || source.role !== input.principal || source.content !== input.instruction) {
      throw new WorkbenchGatewayError("conflict", "Agent 来源消息不匹配。", { apiCode: "agent_source_message_mismatch" });
    }
    const runId = `agent-run-${crypto.randomUUID().replaceAll("-", "")}`;
    const citations = input.evidenceTargets.map((target) => ({ evidenceRef: target.evidenceRef, dimensionId: target.dimensionId, reviewTargetId: target.reviewTargetId, factVersionId: target.factVersionId }));
    const questions = /[?？]/u.test(input.instruction) ? ["请由项目人员结合引用材料确认该问题。"] : [];
    const execution: AgentExecutionMetadata = { mode: "synthetic", providerId: "synthetic_group_chat_agent", modelId: "deterministic-v1", promptVersion: "mock-group-chat-v1", inputHash: "0".repeat(64), contextVersion: "1".repeat(64), outputHash: "2".repeat(64), advisoryOnly: true, isSimulated: true, dataStatus: "simulated", source: "synthetic_group_chat_agent", disclaimer: "Mock Agent 仅用于前端开发测试，不构成正式判断。" };
    const reply = `辅助答复：${input.instruction}`;
    const agent: AgentMessage = { id: `agent-message-${crypto.randomUUID().replaceAll("-", "")}`, projectId: input.projectId, threadId: current.id, sequence: messages.length + 1, role: input.targetAgentRole, authorType: "agent", kind: "agent_reply", content: reply, citations, generatedContent: { replyText: reply, observations: [], questions, citations, scopeStatus: questions.length ? "needs_clarification" : "in_scope", disposition: questions.length ? "request_information" : "answer" }, execution, replyToMessageId: source.id, runId, createdAt: now, immutable: true, advisoryOnly: true, isSimulated: true };
    messages.push(agent);
    this.agentMessages.set(current.id, messages);
    const next: AgentThread = { ...current, version: current.version + 1, updatedAt: now };
    this.agentThreads.set(input.projectId, next);
    return clone({ turnId: `agent-turn-${crypto.randomUUID().replaceAll("-", "")}`, runId, status: questions.length ? "needs_review" : "completed", focusRole: input.targetAgentRole, currentFocusRole: next.focusRole, messages: [agent], nextExpectedVersion: next.version, execution, advisoryOnly: true, schemaVersion: "2.0" } satisfies AgentTurnResult);
  }

  private requireAgentThread(projectId: string, threadId: string) {
    const thread = this.agentThreads.get(projectId);
    if (!thread || thread.id !== threadId) throw new WorkbenchGatewayError("not_found", "Agent thread 不存在。", { apiCode: "agent_thread_not_found" });
    return thread;
  }

  async transitionApproval(projectId: string, input: ApprovalTransitionCommand): Promise<ApprovalState> {
    const current = await this.readApprovalState(projectId);
    if (input.expectedVersion !== current.version) throw new WorkbenchGatewayError("conflict", "审批版本已变化，请重新读取项目状态。");
    if (input.transition === "complete" && (current.hardGateStatus !== "pass" || current.riskVeto)) {
      throw new WorkbenchGatewayError("conflict", "hard_gate_blocked：制度 Gate 或风险否决尚未解除。");
    }
    const status = { save_draft: "draft", return: "returned", submit: "submitted", complete: "completed" }[input.transition] as ApprovalState["status"];
    const next: ApprovalState = { ...current, status, version: current.version + 1, updatedAt: new Date(0).toISOString() };
    this.approvalStates.set(projectId, next);
    return clone(next);
  }

  private async loadProjectOrNull(projectId: string) {
    try {
      return await this.loadProject(projectId);
    } catch (error) {
      if (error instanceof WorkbenchGatewayError && error.code === "not_found") return null;
      throw error;
    }
  }
}
