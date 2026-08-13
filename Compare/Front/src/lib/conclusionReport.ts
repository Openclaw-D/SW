import type { ProjectConclusionReport } from "../contracts/conclusion";
import type { ApprovalState, CommonReviewEvent, EvidenceReference, HardConstraintResult, WorkbenchProject } from "../contracts/workbench";
import { formatAgentRole, formatApprovalStatus, formatCanonicalLabel, formatCanonicalNarrative, formatDimensionName, formatEvidenceLocationStatus, formatEvidenceLocatorSummary, formatHardGateStatus, formatRiskLevel, type PublicLocale } from "./publicLocale.ts";

const unique = (values: string[]) => [...new Set(values.filter(Boolean))];

function locatorSummary(evidence: EvidenceReference) {
  if (!evidence.locator) {
    if (evidence.locationStatus === "pending") return "待定位";
    if (evidence.locationStatus === "unverifiable") return "无法核验";
    if (evidence.locationStatus === "version_mismatch") return "材料版本不匹配";
    return "未定位";
  }
  const locator = evidence.locator;
  if (locator.kind === "excel") return `${locator.sheet}!${locator.range}`;
  if (locator.kind === "pdf") return `第 ${locator.page} 页`;
  if (locator.kind === "image") return "图像区域";
  if (locator.kind === "media") return `${locator.startSeconds}–${locator.endSeconds} 秒`;
  return `场景点 ${locator.pointIds.length} 个`;
}

export function buildMockConclusionReport(project: WorkbenchProject, policies: HardConstraintResult[], approval: ApprovalState, events: CommonReviewEvent[]): ProjectConclusionReport {
  const determinationByDimension = new Map(project.determinations.map((item) => [item.dimensionId, item]));
  const latestEvents = new Map<string, CommonReviewEvent>();
  for (const event of events) {
    const current = latestEvents.get(event.threadId);
    if (!current || event.sequence > current.sequence) latestEvents.set(event.threadId, event);
  }
  const formalItems: ProjectConclusionReport["openItems"] = [...latestEvents.values()]
    .filter((event) => event.issueStatus === "open" || event.issueStatus === "pending_gate")
    .map((event) => ({
      id: event.id,
      source: "formal_review",
      title: event.title,
      detail: event.summary,
      status: event.issueStatus as "open" | "pending_gate",
      dimensionId: event.dimensionId,
      responsibleParty: event.eventType === "risk_question_submitted" ? "business" : "joint",
      nextAction: event.eventType === "risk_question_submitted" ? "业务补充证据或作出可追溯答复。" : "业务与风控按正式共同审查链处理。",
      evidenceRefs: unique(event.evidenceRefs),
    }));
  const riskItems: ProjectConclusionReport["openItems"] = project.riskSummary.pendingHumanDeterminations.map((item) => ({
    id: item.id,
    source: "risk_summary",
    title: item.title,
    detail: item.detail,
    status: "manual_review",
    dimensionId: item.evidenceTargets[0]?.dimensionId ?? null,
    responsibleParty: item.responsibleParty,
    nextAction: item.nextAction,
    evidenceRefs: unique(item.evidenceTargets.flatMap((target) => target.evidenceRefs ?? [target.evidenceRef])),
  }));
  const policyItems: ProjectConclusionReport["openItems"] = policies.flatMap((policy) => policy.result === "pass" ? [] : [{
      id: policy.id,
      source: "policy" as const,
      title: policy.title,
      detail: policy.explanation,
      status: policy.result,
      dimensionId: policy.primaryTarget?.dimensionId ?? null,
      responsibleParty: policy.responsibleParty,
      nextAction: policy.nextAction,
      evidenceRefs: unique(policy.evidenceTargets.flatMap((target) => target.evidenceRefs ?? [target.evidenceRef])),
    }]);
  const openItems = [...formalItems, ...riskItems, ...policyItems];
  const importantRefs = unique([...project.riskSummary.evidenceRefs, ...openItems.flatMap((item) => item.evidenceRefs)]);
  const selectedRefs = importantRefs.length ? importantRefs : project.evidence.map((item) => item.id);
  const keyEvidence = selectedRefs.slice(0, 20).flatMap((evidenceRef) => {
    const evidence = project.evidence.find((item) => item.id === evidenceRef);
    return evidence ? [{ evidenceRef, label: evidence.label, locationStatus: evidence.locationStatus, materialStatus: evidence.materialStatus, locatorSummary: locatorSummary(evidence) }] : [];
  });
  const evidenceStatusCounts = { located: 0, pending: 0, unverifiable: 0, version_mismatch: 0 };
  for (const evidence of project.evidence) evidenceStatusCounts[evidence.locationStatus] += 1;
  const policyCounts = {
    passed: policies.filter((item) => item.result === "pass").length,
    blocked: policies.filter((item) => item.result === "block").length,
    manualReview: policies.filter((item) => item.result === "manual_review").length,
  };
  const completionAllowed = approval.hardGateStatus === "pass" && !approval.blockingRuleIds.length && !approval.riskVeto && !approval.riskVetoRuleIds.length;
  const humanStatus = approval.status === "completed" ? "completed" : completionAllowed && !openItems.length ? "ready_for_human" : "human_action_required";
  return {
    schemaVersion: "1.0",
    projectId: project.project.id,
    projectName: project.project.name,
    generatedAt: new Date(0).toISOString(),
    overall: {
      riskLevel: project.riskSummary.level,
      scoreGrade: project.riskSummary.scoreGrade,
      decisionGrade: project.riskSummary.decisionGrade,
      confidence: project.riskSummary.confidence,
      summary: project.riskSummary.summary,
    },
    dimensions: project.dimensions.map((dimension) => ({
      dimensionId: dimension.id,
      name: dimension.name,
      score: dimension.score,
      scoreGrade: dimension.scoreGrade,
      decisionGrade: determinationByDimension.get(dimension.id)?.decisionGrade ?? dimension.scoreGrade,
      confidence: dimension.confidence,
      summary: dimension.summary,
      conclusion: determinationByDimension.get(dimension.id)?.conclusion ?? "待人工认定",
    })),
    evidenceTotal: project.evidence.length,
    evidenceStatusCounts,
    keyEvidence,
    openItems,
    gates: { approvalStatus: approval.status, approvalVersion: approval.version, hardGateStatus: approval.hardGateStatus, blockingRuleIds: approval.blockingRuleIds, riskVeto: approval.riskVeto, riskVetoRuleIds: approval.riskVetoRuleIds, policyCounts, completionAllowed },
    collaboration: { hasThread: false, threadId: null, threadTitle: null, threadStatus: null, focusRole: null, threadVersion: null, messageCount: 0, agentMessageCount: 0, focusEventCount: 0, focusTransitionCount: 0, latestAdvice: null },
    humanConfirmation: {
      required: true,
      status: humanStatus,
      checks: [`制度 Gate：${approval.hardGateStatus}；阻断规则 ${approval.blockingRuleIds.length} 条。`, `正式未决项：${openItems.length} 条；未完成定位证据：${project.evidence.length - evidenceStatusCounts.located} 条。`, "负责人须在正式审批链确认结论；Agent 建议不能写入事实、制度或审批状态。"],
      boundary: "系统仅整理与提示；最终结论、审批和制度 Gate 均由既有服务端规则与授权人员确认。",
    },
    aiValue: {
      sourceSectionsConsolidated: ["项目状态与六维认定", "关键证据定位", "正式共同审查未决项", "制度 Gate 与审批状态"],
      evidenceItemsOrganized: keyEvidence.length,
      openItemsSurfaced: openItems.length,
      followUpQuestionsSurfaced: 0,
      traceableReferenceCount: unique([...keyEvidence.map((item) => item.evidenceRef), ...openItems.flatMap((item) => item.evidenceRefs)]).length,
      advisoryMessagesAvailable: 0,
      focusTransitionsRecorded: 0,
      summary: "把分散在项目、证据、正式协同与制度 Gate 中的当前状态汇总到一个可追溯视图，减少人工整理、逐项追问和页面切换；以上数量来自当前本地模拟记录，不代表自动决策、模型准确率或已实现的时间/利润收益。",
    },
    advisoryOnly: true,
    isSimulated: true,
    dataStatus: "simulated",
    source: "server_conclusion_projection",
    disclaimer: "本报告是对当前项目状态、证据、正式协同、制度 Gate 与单焦点 Agent 建议的只读汇总。Agent 内容始终为 advisory-only；报告不执行审批、不替代人工判断，也不证明真实生产模型质量或外部网络核验结果。",
  };
}

export function buildConclusionMarkdown(report: ProjectConclusionReport, locale: PublicLocale = "zh-CN"): string {
  const advice = report.collaboration.latestAdvice;
  if (locale === "en") {
    const lines = [
      `# ${formatCanonicalNarrative(report.projectName, locale)} | Conclusion report`,
      "",
      `- Generated: ${report.generatedAt}`,
      `- Risk status: ${formatRiskLevel(report.overall.riskLevel, locale)}`,
      `- Score grade: ${report.overall.scoreGrade}`,
      `- Decision grade: ${report.overall.decisionGrade}`,
      `- Confidence: ${report.overall.confidence}%`,
      `- Approval state: ${formatApprovalStatus(report.gates.approvalStatus, locale)}`,
      `- Policy gate: ${formatHardGateStatus(report.gates.hardGateStatus, locale)}`,
      "",
      "## Current summary",
      "",
      formatCanonicalNarrative(report.overall.summary, locale),
      "",
      "## Six-dimension determinations",
      "",
      "| Dimension | Score | Score grade | Decision grade | Confidence | Current determination |",
      "| --- | ---: | --- | --- | ---: | --- |",
      ...report.dimensions.map((item) => `| ${formatDimensionName(item.dimensionId, locale, item.name)} | ${item.score} | ${item.scoreGrade} | ${item.decisionGrade} | ${item.confidence}% | ${formatCanonicalNarrative(item.conclusion, locale).replaceAll("|", "\\|")} |`),
      "",
      "## Policy gates and human confirmation",
      "",
      ...report.humanConfirmation.checks.map((item) => `- ${formatCanonicalNarrative(item, locale)}`),
      `- Human-confirmation boundary: ${formatCanonicalNarrative(report.humanConfirmation.boundary, locale)}`,
      "",
      "## Key evidence",
      "",
      ...(report.keyEvidence.length ? report.keyEvidence.map((item) => `- ${formatCanonicalLabel(item.label, locale)} (${formatEvidenceLocatorSummary(item.locatorSummary, item.locationStatus, locale)}; ${formatEvidenceLocationStatus(item.locationStatus, locale)}; ref: ${item.evidenceRef})`) : ["- No key evidence is available for display."]),
      "",
      "## Open items",
      "",
      ...(report.openItems.length ? report.openItems.map((item) => `- [${item.status}] ${formatCanonicalNarrative(item.title, locale)}: ${formatCanonicalNarrative(item.detail, locale)}; next step: ${formatCanonicalNarrative(item.nextAction, locale)}${item.evidenceRefs.length ? `; evidence: ${item.evidenceRefs.join(", ")}` : ""}`) : ["- The projection found no open items; the accountable owner must still complete formal confirmation."]),
      "",
      "## Single-focus collaboration advice",
      "",
      ...(advice ? [`- Current focus: ${report.collaboration.focusRole ? formatAgentRole(report.collaboration.focusRole, locale) : "None"}`, `- Advisory role: ${formatAgentRole(advice.role, locale)}`, `- Advice: ${formatCanonicalNarrative(advice.content, locale)}`, `- Provenance: provider=${advice.execution.providerId ?? "not configured"}; model=${advice.execution.modelId ?? "not configured"}; prompt=${advice.execution.promptVersion ?? "not configured"}; inputHash=${advice.execution.inputHash}`] : ["- No Agent session or advice exists; this report will not invent a collaboration conclusion."]),
      "",
      "## Verifiable AI-assistance value",
      "",
      `- Consolidated sources: ${report.aiValue.sourceSectionsConsolidated.map((item) => formatCanonicalNarrative(item, locale)).join(", ")}`,
      `- Key evidence items organized: ${report.aiValue.evidenceItemsOrganized}`,
      `- Open items surfaced: ${report.aiValue.openItemsSurfaced}`,
      `- Follow-up questions surfaced: ${report.aiValue.followUpQuestionsSurfaced}`,
      `- Traceable references: ${report.aiValue.traceableReferenceCount}`,
      `- Advisory messages available: ${report.aiValue.advisoryMessagesAvailable}`,
      `- Focus transitions recorded: ${report.aiValue.focusTransitionsRecorded}`,
      `- ${formatCanonicalNarrative(report.aiValue.summary, locale)}`,
      "",
      "## Use boundary",
      "",
      formatCanonicalNarrative(report.disclaimer, locale),
      "",
    ];
    return lines.join("\n");
  }
  const lines = [
    `# ${report.projectName}｜结论报告`,
    "",
    `- 生成时间：${report.generatedAt}`,
    `- 风险状态：${report.overall.riskLevel}`,
    `- 评分等级：${report.overall.scoreGrade}`,
    `- 决策等级：${report.overall.decisionGrade}`,
    `- 置信度：${report.overall.confidence}%`,
    `- 审批状态：${report.gates.approvalStatus}`,
    `- 制度 Gate：${report.gates.hardGateStatus}`,
    "",
    "## 当前摘要",
    "",
    report.overall.summary,
    "",
    "## 六维认定",
    "",
    "| 维度 | 分数 | 评分等级 | 决策等级 | 置信度 | 当前认定 |",
    "| --- | ---: | --- | --- | ---: | --- |",
    ...report.dimensions.map((item) => `| ${item.name} | ${item.score} | ${item.scoreGrade} | ${item.decisionGrade} | ${item.confidence}% | ${item.conclusion.replaceAll("|", "｜")} |`),
    "",
    "## 制度 Gate 与人工确认",
    "",
    ...report.humanConfirmation.checks.map((item) => `- ${item}`),
    `- 人工确认边界：${report.humanConfirmation.boundary}`,
    "",
    "## 关键证据",
    "",
    ...(report.keyEvidence.length ? report.keyEvidence.map((item) => `- ${item.label}（${item.locatorSummary}；${item.locationStatus}；ref: ${item.evidenceRef}）`) : ["- 当前无可列示的关键证据。"]),
    "",
    "## 未决项",
    "",
    ...(report.openItems.length ? report.openItems.map((item) => `- [${item.status}] ${item.title}：${item.detail}；下一步：${item.nextAction}${item.evidenceRefs.length ? `；证据：${item.evidenceRefs.join("、")}` : ""}`) : ["- 当前投影未发现未决项；仍须由负责人完成正式确认。"]),
    "",
    "## 单焦点协作建议",
    "",
    ...(advice ? [`- 当前焦点：${report.collaboration.focusRole}`, `- 建议角色：${advice.role}`, `- 建议：${advice.content}`, `- provenance：provider=${advice.execution.providerId ?? "未配置"}；model=${advice.execution.modelId ?? "未配置"}；prompt=${advice.execution.promptVersion ?? "未配置"}；inputHash=${advice.execution.inputHash}`] : ["- 尚无 Agent 会话或建议；本报告不会虚构协作结论。"]),
    "",
    "## 可核验的 AI 辅助价值",
    "",
    `- 汇总来源：${report.aiValue.sourceSectionsConsolidated.join("、")}`,
    `- 已整理关键证据：${report.aiValue.evidenceItemsOrganized} 项`,
    `- 已显式列出未决项：${report.aiValue.openItemsSurfaced} 项`,
    `- 已显式列出追问：${report.aiValue.followUpQuestionsSurfaced} 项`,
    `- 可追溯引用：${report.aiValue.traceableReferenceCount} 项`,
    `- 可用 advisory 消息：${report.aiValue.advisoryMessagesAvailable} 条`,
    `- 已记录焦点切换：${report.aiValue.focusTransitionsRecorded} 次`,
    `- ${report.aiValue.summary}`,
    "",
    "## 使用边界",
    "",
    report.disclaimer,
    "",
  ];
  return lines.join("\n");
}
