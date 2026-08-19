import type { ReactNode } from "react";
import type { ApprovalState, ApprovalTransition, ProjectSummary } from "../contracts/workbench";
import { displayBusinessName } from "../lib/workbenchLogic";
import { Button } from "./ui";
import { copy, formatServiceMessage, type PublicLocale } from "../lib/publicLocale";
import type { AuthenticatedAccount } from "../contracts/authentication";
import type { AccountRole } from "../contracts/authentication";

function GlobalApprovalActions({ approval, pending, message, onTransition, locale }: { approval: ApprovalState | null; pending: boolean; message: string | null; onTransition: (transition: ApprovalTransition) => void; locale: PublicLocale }) {
  const status = approval?.status ?? "draft";
  const unresolvedGateCount = approval?.blockingRuleIds.length ?? 0;
  const blocked = !approval || approval.hardGateStatus !== "pass" || approval.riskVeto;
  const completionBlocked = pending || status !== "submitted";
  const statusText = blocked
    ? copy(locale, `${unresolvedGateCount} policy gates remain uncleared. Server rules: ${unresolvedGateCount ? approval?.blockingRuleIds.join(", ") : "not loaded"}. The server rechecks them on completion.`, `当前 ${unresolvedGateCount} 个制度 Gate 未解除；服务端规则：${unresolvedGateCount ? approval?.blockingRuleIds.join("、") : "待读取"}；完成将由服务端复核。`)
    : copy(locale, "The server gate passed. The final action still uses the server approval workflow.", "服务端 Gate 已通过；最终动作仍由服务端审批。");
  return <div aria-label={copy(locale, "Project approval actions", "项目审批操作")} className="global-approval-actions" data-semantic-localized="true"><span title={statusText}>{blocked ? copy(locale, `Gate not cleared · ${unresolvedGateCount}`, `Gate ${unresolvedGateCount} 未解除`) : copy(locale, "Gate passed", "Gate 已通过")}</span><div><Button aria-pressed={status === "draft"} disabled={pending || !approval || !["draft", "returned"].includes(status)} onClick={() => onTransition("save_draft")}>{copy(locale, "Save draft", "暂存")}</Button><Button aria-pressed={status === "returned"} disabled={pending || status !== "submitted"} onClick={() => onTransition("return")}>{copy(locale, "Return", "退回")}</Button><Button aria-pressed={status === "submitted"} disabled={pending || !["draft", "returned"].includes(status)} onClick={() => onTransition("submit")} variant="primary">{copy(locale, "Submit", "提交")}</Button><Button aria-label={blocked ? copy(locale, "Complete approval; the server will validate the hard gate", "完成审批，服务端将校验 hard gate") : copy(locale, "Complete approval", "完成审批")} aria-pressed={status === "completed"} disabled={completionBlocked} onClick={() => onTransition("complete")}>{pending ? copy(locale, "Submitting…", "提交中…") : copy(locale, "Complete", "完成")}</Button></div>{message ? <small className="composer-error" role="alert">{formatServiceMessage(message, locale)}</small> : null}</div>;
}

export function TopBar({ project, projectNo, hardConstraintCount, policyHitCount, approval, approvalPending, approvalMessage, onApprovalTransition, onOpenConclusionReport, onResetLayout, onBack, account, onLogout, onPrincipalRoleChange, principalRoleChangePending, locale, onLocaleChange, presentationMode = false, leadingContent = null, centerContent = null, actionContent = null }: { project: ProjectSummary; projectNo: string; hardConstraintCount: number; policyHitCount: number; approval: ApprovalState | null; approvalPending: boolean; approvalMessage: string | null; onApprovalTransition: (transition: ApprovalTransition) => void; onOpenConclusionReport: () => void; onResetLayout: () => void; onBack: () => void; account: AuthenticatedAccount; onLogout: () => void; onPrincipalRoleChange: (role: Extract<AccountRole, "business" | "risk">) => void; principalRoleChangePending: boolean; locale: PublicLocale; onLocaleChange?: (locale: PublicLocale) => void; presentationMode?: boolean; leadingContent?: ReactNode; centerContent?: ReactNode; actionContent?: ReactNode }) {
  const projectName = displayBusinessName(project.name, "项目名称待补");
  const presentationProjectName = projectName.replace(/\s*·\s*统一脱敏(?:核验|校验)模板$/u, "");
  return (
    <header className={`top-bar ${centerContent ? "has-center-content" : ""}`} data-semantic-localized="true">
      <div className="project-title">
        {leadingContent}
        {presentationMode ? null : <b className="project-number" data-project-id={project.id} title={copy(locale, `Internal project ID: ${project.id}`, `内部项目 ID：${project.id}`)}>{projectNo}</b>}
        <strong title={projectName}>{presentationMode ? presentationProjectName : locale === "en" ? "Finance lease evidence workbench — de-identified project" : projectName}</strong>
      </div>
      {centerContent ? <div className="topbar-center-content">{centerContent}</div> : null}
      {!presentationMode ? <div className="topbar-controls">
        {actionContent}
        {onLocaleChange ? <span className="topbar-language" data-language-control><button aria-label={copy(locale, "Switch to Chinese", "切换为中文")} aria-pressed={locale === "zh-CN"} onClick={() => onLocaleChange("zh-CN")} type="button">中</button><button aria-label="Switch to English" aria-pressed={locale === "en"} onClick={() => onLocaleChange("en")} type="button">EN</button></span> : null}
        {actionContent ? null : <details className="topbar-account">
          <summary aria-label={copy(locale, "Open identity menu", "打开身份菜单")}><small>{copy(locale, "Identity", "身份")}</small><b>{account.role === "leadership" ? copy(locale, "System settings", "系统设置") : account.displayName}</b></summary>
          <div className="topbar-account-menu">
            <label>
              <small>{copy(locale, "Current identity", "当前身份")}</small>
              <select
                aria-label={copy(locale, "Switch business or risk-control identity", "切换业务或风控身份")}
                disabled={principalRoleChangePending}
                onChange={(event) => {
                  const nextRole = event.target.value;
                  if (nextRole === "business" || nextRole === "risk") onPrincipalRoleChange(nextRole);
                }}
                value={account.role === "leadership" ? "system" : account.role}
              >
                <option value="business">{copy(locale, "Business", "业务")}</option>
                <option value="risk">{copy(locale, "Risk control", "风控")}</option>
                {account.role === "leadership" ? <option value="system">{copy(locale, "System settings", "系统设置")}</option> : null}
              </select>
            </label>
            <span><b>{account.displayName}</b><small>{account.role === "leadership" ? copy(locale, "System settings", "系统设置") : account.username}</small></span>
            <Button aria-label={copy(locale, "Back to project directory", "返回项目选择")} onClick={onBack}>{copy(locale, "Back", "返回")}</Button>
            <Button aria-label={copy(locale, "Open project conclusion report", "打开项目结论报告")} onClick={onOpenConclusionReport}>{copy(locale, "Conclusion", "结论")}</Button>
            <Button aria-label={copy(locale, "Restore layout", "恢复默认布局")} onClick={onResetLayout}>{copy(locale, "Reset", "恢复")}</Button>
            <Button disabled={principalRoleChangePending} onClick={onLogout}>{copy(locale, "Sign out", "退出")}</Button>
            {account.role === "leadership" ? <GlobalApprovalActions approval={approval} locale={locale} message={approvalMessage} onTransition={onApprovalTransition} pending={approvalPending} /> : <div className="global-approval-actions is-readonly" role="status">{copy(locale, "Approval actions are read-only for this role", "当前角色仅可查看审批状态")}</div>}
          </div>
        </details>}
      </div> : null}
    </header>
  );
}
