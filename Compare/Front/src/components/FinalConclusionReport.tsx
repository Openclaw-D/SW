import { useEffect } from "react";
import type { ProjectConclusionReport } from "../contracts/conclusion";
import { buildConclusionMarkdown } from "../lib/conclusionReport";
import {
  copy,
  formatAgentRole,
  formatApprovalStatus,
  formatCanonicalLabel,
  formatCanonicalNarrative,
  formatDataStatus,
  formatDimensionName,
  formatEvidenceLocationStatus,
  formatEvidenceLocatorSummary,
  formatHardGateStatus,
  formatMaterialStatus,
  formatRiskLevel,
  formatServiceMessage,
  usePublicLocale,
  type PublicLocale,
} from "../lib/publicLocale";
import { Button } from "./ui";

const humanStatusLabel = {
  human_action_required: ["Human action required", "待人工处理"],
  ready_for_human: ["Ready for human confirmation", "可进入人工确认"],
  completed: ["Human approval completed", "人工审批已完成"],
} as const;

const sourceLabel = {
  formal_review: ["Formal review", "正式协同"],
  risk_summary: ["Risk summary", "风险摘要"],
  policy: ["Policy gate", "制度 Gate"],
} as const;

function downloadMarkdown(report: ProjectConclusionReport, locale: PublicLocale) {
  const blob = new Blob([buildConclusionMarkdown(report, locale)], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${report.projectName.replace(/[\\/:*?"<>|]/g, "-")}-${copy(locale, "conclusion-report", "结论报告")}.md`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function FinalConclusionReport({ report, status, error, onClose, onRefresh }: { report: ProjectConclusionReport | null; status: "loading" | "ready" | "error"; error: string | null; onClose: () => void; onRefresh: () => void }) {
  const locale = usePublicLocale();
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="conclusion-report-overlay" data-semantic-localized="true" data-testid="conclusion-report-overlay">
      <section aria-busy={status === "loading"} aria-label={copy(locale, "Project conclusion report", "项目结论报告")} aria-modal="true" className="conclusion-report" role="dialog">
        <header className="conclusion-report-header">
          <div>
            <span className="conclusion-report-kicker">{copy(locale, "Accountable-owner / leadership reporting view", "负责人 / 领导上报视图")}</span>
            <h1>{report ? formatCanonicalNarrative(report.projectName, locale) : copy(locale, "Project conclusion report", "项目结论报告")}</h1>
            <p>{copy(locale, "Read-only server projection · score grade, decision grade, confidence, evidence, and policy gates remain separate", "服务端只读投影 · 评分、决策、置信度、证据与制度 Gate 分开呈现")}</p>
          </div>
          <div className="conclusion-report-actions">
            <Button disabled={status === "loading"} onClick={onRefresh}>{copy(locale, "Refresh", "刷新")}</Button>
            <Button disabled={!report} onClick={() => window.print()}>{copy(locale, "Print", "打印")}</Button>
            <Button disabled={!report} onClick={() => report && downloadMarkdown(report, locale)}>{copy(locale, "Download Markdown", "下载 Markdown")}</Button>
            <Button aria-label={copy(locale, "Close conclusion report", "关闭结论报告")} onClick={onClose} variant="primary">{copy(locale, "Close", "关闭")}</Button>
          </div>
        </header>

        {status === "loading" && !report ? <div className="conclusion-report-state" role="status">{copy(locale, "Organizing the current conclusion from server records…", "正在从服务端整理当前结论…")}</div> : null}
        {status === "error" ? <div className="conclusion-report-state is-error" role="alert"><strong>{copy(locale, "Could not load the conclusion report", "结论报告读取失败")}</strong><span>{formatServiceMessage(error, locale)}</span><Button onClick={onRefresh}>{copy(locale, "Retry", "重试")}</Button></div> : null}

        {report ? <div className="conclusion-report-content">
          <aside className="conclusion-boundary" role="note">
            <strong>{copy(locale, "Human-confirmation boundary", "人工确认边界")}</strong>
            <span>{formatCanonicalNarrative(report.humanConfirmation.boundary, locale)}</span>
            <small>{formatCanonicalNarrative(report.disclaimer, locale)}</small>
          </aside>

          <section aria-label={copy(locale, "Project conclusion summary", "项目结论摘要")} className="conclusion-section">
            <div className="conclusion-section-heading"><h2>{copy(locale, "Current conclusion summary", "当前结论摘要")}</h2><span>{new Date(report.generatedAt).toLocaleString(locale === "en" ? "en-GB" : "zh-CN", { hour12: false })}</span></div>
            <div className="conclusion-metrics">
              <article><span>{copy(locale, "Risk status", "风险状态")}</span><strong>{formatRiskLevel(report.overall.riskLevel, locale)}</strong></article>
              <article><span>{copy(locale, "Score grade", "评分等级")}</span><strong>{report.overall.scoreGrade}</strong><small>{copy(locale, "Mapped from six-dimension scores", "六维分数映射")}</small></article>
              <article><span>{copy(locale, "Decision grade", "决策等级")}</span><strong>{report.overall.decisionGrade}</strong><small>{copy(locale, "Formal risk determination", "正式风险认定")}</small></article>
              <article><span>{copy(locale, "Confidence", "置信度")}</span><strong>{report.overall.confidence}%</strong><small>{copy(locale, "Not an approval probability", "不等同通过概率")}</small></article>
              <article><span>{copy(locale, "Approval state", "审批状态")}</span><strong>{formatApprovalStatus(report.gates.approvalStatus, locale)}</strong><small>{copy(locale, `Server v${report.gates.approvalVersion}`, `服务端 v${report.gates.approvalVersion}`)}</small></article>
              <article className={report.gates.hardGateStatus === "pass" ? "is-pass" : "is-attention"}><span>{copy(locale, "Policy gate", "制度 Gate")}</span><strong>{formatHardGateStatus(report.gates.hardGateStatus, locale)}</strong><small>{copy(locale, `${report.gates.blockingRuleIds.length} blocking rules`, `${report.gates.blockingRuleIds.length} 条阻断规则`)}</small></article>
            </div>
            <p className="conclusion-overall-copy">{formatCanonicalNarrative(report.overall.summary, locale)}</p>
          </section>

          <div className="conclusion-two-column">
            <section aria-label={copy(locale, "Policy gates and human confirmation", "制度 Gate 与人工确认")} className="conclusion-section">
              <div className="conclusion-section-heading"><h2>{copy(locale, "Policy gates and human confirmation", "制度 Gate 与人工确认")}</h2><strong>{copy(locale, humanStatusLabel[report.humanConfirmation.status][0], humanStatusLabel[report.humanConfirmation.status][1])}</strong></div>
              <ul className="conclusion-check-list">{report.humanConfirmation.checks.map((item) => <li key={item}>{formatCanonicalNarrative(item, locale)}</li>)}</ul>
              <div className="conclusion-gate-counts"><span>{copy(locale, `Passed ${report.gates.policyCounts.passed}`, `通过 ${report.gates.policyCounts.passed}`)}</span><span>{copy(locale, `Blocked ${report.gates.policyCounts.blocked}`, `阻断 ${report.gates.policyCounts.blocked}`)}</span><span>{copy(locale, `Manual review ${report.gates.policyCounts.manualReview}`, `人工复核 ${report.gates.policyCounts.manualReview}`)}</span></div>
            </section>

            <section aria-label={copy(locale, "Verifiable AI-assistance value", "可核验的 AI 辅助价值")} className="conclusion-section">
              <div className="conclusion-section-heading"><h2>{copy(locale, "Verifiable AI-assistance value", "可核验的 AI 辅助价值")}</h2><span>{copy(locale, "Current records only", "仅计当前记录")}</span></div>
              <div className="conclusion-value-grid">
                <span><b>{report.aiValue.evidenceItemsOrganized}</b>{copy(locale, "key evidence items organized", "关键证据已整理")}</span>
                <span><b>{report.aiValue.openItemsSurfaced}</b>{copy(locale, "open items surfaced", "未决项已显式列出")}</span>
                <span><b>{report.aiValue.followUpQuestionsSurfaced}</b>{copy(locale, "follow-up questions consolidated", "追问已集中呈现")}</span>
                <span><b>{report.aiValue.traceableReferenceCount}</b>{copy(locale, "traceable references", "可追溯引用")}</span>
              </div>
              <p>{formatCanonicalNarrative(report.aiValue.summary, locale)}</p>
              <small>{copy(locale, "Consolidated sources: ", "汇总来源：")}{report.aiValue.sourceSectionsConsolidated.map((item) => formatCanonicalNarrative(item, locale)).join(" · ")}</small>
            </section>
          </div>

          <section aria-label={copy(locale, "Six-dimension determinations", "六维认定")} className="conclusion-section">
            <div className="conclusion-section-heading"><h2>{copy(locale, "Six-dimension determinations", "六维认定")}</h2><span>{copy(locale, "Higher scores are better; decision grades remain independent", "分数越高越好；决策等级独立保留")}</span></div>
            <div className="conclusion-dimension-table" role="table">
              <div className="is-header" role="row"><span>{copy(locale, "Dimension", "维度")}</span><span>{copy(locale, "Score", "分数")}</span><span>{copy(locale, "Score grade", "评分等级")}</span><span>{copy(locale, "Decision grade", "决策等级")}</span><span>{copy(locale, "Confidence", "置信度")}</span><span>{copy(locale, "Current determination", "当前认定")}</span></div>
              {report.dimensions.map((item) => <div key={item.dimensionId} role="row"><strong>{formatDimensionName(item.dimensionId, locale, item.name)}</strong><span>{item.score}</span><span>{item.scoreGrade}</span><span>{item.decisionGrade}</span><span>{item.confidence}%</span><p>{formatCanonicalNarrative(item.conclusion, locale)}</p></div>)}
            </div>
          </section>

          <div className="conclusion-two-column conclusion-detail-columns">
            <section aria-label={copy(locale, "Key evidence", "关键证据")} className="conclusion-section">
              <div className="conclusion-section-heading"><h2>{copy(locale, "Key evidence", "关键证据")}</h2><span>{report.keyEvidence.length} / {report.evidenceTotal}</span></div>
              {report.keyEvidence.length ? <ul className="conclusion-evidence-list">{report.keyEvidence.map((item) => <li key={item.evidenceRef}><strong>{formatCanonicalLabel(item.label, locale)}</strong><span>{formatEvidenceLocatorSummary(item.locatorSummary, item.locationStatus, locale)}</span><small>{formatEvidenceLocationStatus(item.locationStatus, locale)} · {formatMaterialStatus(item.materialStatus, locale)} · {item.evidenceRef}</small></li>)}</ul> : <p className="conclusion-empty">{copy(locale, "No key evidence is available for display.", "当前无可列示的关键证据。")}</p>}
            </section>

            <section aria-label={copy(locale, "Open items", "未决项")} className="conclusion-section">
              <div className="conclusion-section-heading"><h2>{copy(locale, "Open items and next steps", "未决项与下一步")}</h2><span>{copy(locale, `${report.openItems.length} items`, `${report.openItems.length} 项`)}</span></div>
              {report.openItems.length ? <ul className="conclusion-open-list">{report.openItems.map((item) => <li key={`${item.source}-${item.id}`}><div><span>{copy(locale, sourceLabel[item.source][0], sourceLabel[item.source][1])}</span><b>{formatDataStatus(item.status, locale)}</b></div><strong>{formatCanonicalNarrative(item.title, locale)}</strong><p>{formatCanonicalNarrative(item.detail, locale)}</p><small>{copy(locale, "Owner: ", "负责人：")}{item.responsibleParty === "joint" ? copy(locale, "Business / Risk control", "业务 / 风控") : formatAgentRole(item.responsibleParty, locale)} · {copy(locale, "Next step: ", "下一步：")}{formatCanonicalNarrative(item.nextAction, locale)}</small></li>)}</ul> : <p className="conclusion-empty">{copy(locale, "The projection found no open items; the accountable owner must still complete formal confirmation.", "当前投影未发现未决项；仍须由负责人完成正式确认。")}</p>}
            </section>
          </div>

          <section aria-label={copy(locale, "Single-focus collaboration advice", "单焦点协作建议")} className="conclusion-section conclusion-advice">
            <div className="conclusion-section-heading"><h2>{copy(locale, "Single-focus collaboration advice", "单焦点协作建议")}</h2><span>{report.collaboration.hasThread ? copy(locale, `${formatAgentRole(report.collaboration.focusRole!, locale)} focus · ${report.collaboration.agentMessageCount} advisory messages`, `${formatAgentRole(report.collaboration.focusRole!, locale)}焦点 · ${report.collaboration.agentMessageCount} 条建议`) : copy(locale, "No session", "暂无会话")}</span></div>
            {report.collaboration.latestAdvice ? <>
              <div className="conclusion-advice-copy"><span>{formatAgentRole(report.collaboration.latestAdvice.role, locale)} Agent · advisory-only</span><p>{formatCanonicalNarrative(report.collaboration.latestAdvice.content, locale)}</p></div>
              {report.collaboration.latestAdvice.generatedContent.questions.length ? <div className="conclusion-questions"><strong>{copy(locale, "Consolidated follow-up questions", "集中追问")}</strong><ul>{report.collaboration.latestAdvice.generatedContent.questions.map((item) => <li key={item}>{formatCanonicalNarrative(item, locale)}</li>)}</ul></div> : null}
              <dl className="conclusion-provenance">
                <div><dt>provider</dt><dd>{report.collaboration.latestAdvice.execution.providerId ?? copy(locale, "Not configured", "未配置")}</dd></div>
                <div><dt>model</dt><dd>{report.collaboration.latestAdvice.execution.modelId ?? copy(locale, "Not configured", "未配置")}</dd></div>
                <div><dt>prompt</dt><dd>{report.collaboration.latestAdvice.execution.promptVersion ?? copy(locale, "Not configured", "未配置")}</dd></div>
                <div><dt>inputHash</dt><dd title={report.collaboration.latestAdvice.execution.inputHash}>{report.collaboration.latestAdvice.execution.inputHash.slice(0, 16)}…</dd></div>
              </dl>
            </> : <p className="conclusion-empty">{copy(locale, "No Agent session or advice exists; the report will not invent a collaboration conclusion. The accountable owner can proceed through the formal open items above.", "尚无 Agent 会话或建议；报告不会虚构协作结论。负责人可先按上方正式未决项推进。")}</p>}
          </section>
        </div> : null}
      </section>
    </div>
  );
}
