import { useEffect, useMemo, useRef, useState } from "react";
import type { AccountRole } from "../contracts/authentication";
import type { AgentActivityState, AgentMessage, AgentResponsePreferences, ChatAgentRole, CollaborationContextReference } from "../contracts/agentCommunication";
import type { MaterialImportPreflight, MaterialImportResult, MaterialUploadReceipt } from "../contracts/materialIntelligence";
import type { EvidenceReference, ReviewEvidenceTarget } from "../contracts/workbench";
import { copy, formatAgentRole, formatCanonicalLabel, formatCanonicalNarrative, formatServiceMessage, quotedSourceText, usePublicLocale } from "../lib/publicLocale";
import { sameReviewEvidenceTarget } from "../lib/workbenchLogic";
import { Icon } from "./icons";
import { Button, EmptyState } from "./ui";
import { AgentSettingsDashboard, DEFAULT_COLLABORATION_VIEW_SETTINGS, type CollaborationViewSettings } from "./AgentSettingsDashboard";

const MAX_MATERIAL_PACKAGE_BYTES = 100 * 1024 * 1024;

export interface A2ACollaborationPanelProps {
  accountRole: AccountRole;
  agentActivity: AgentActivityState | null;
  agentMessages: AgentMessage[];
  agentError: string | null;
  evidence: EvidenceReference[];
  selectedTarget: ReviewEvidenceTarget | null;
  annotationReference?: Extract<CollaborationContextReference, { kind: "material_annotation" }> | null;
  collapsed?: boolean;
  maximized?: boolean;
  onToggleMaximized?: () => void;
  onRequestAnnotation?: () => void;
  onAgentEvidenceActivate: (target: ReviewEvidenceTarget) => void;
  onSubmitMessage: (message: string, targetAgentRole: ChatAgentRole | null, reference: CollaborationContextReference | null, preferences: AgentResponsePreferences) => Promise<void>;
  onImportMaterialPackage: (file: File) => Promise<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight }>;
  onConfirmMaterialImport: (preflight: MaterialImportPreflight) => Promise<MaterialImportResult>;
}

function AgentActivity({ activity }: { activity: AgentActivityState }) {
  const locale = usePublicLocale();
  const roleLabel = formatAgentRole(activity.role, locale);
  const failed = activity.phase === "failed";
  return (
    <article aria-live="polite" className={`a2a-agent-activity ${failed ? "is-failed" : "is-thinking"}`} role={failed ? "alert" : "status"}>
      <span aria-hidden="true" className="a2a-avatar">AI</span>
      <div className="a2a-message-body">
        <div className="a2a-message-meta"><strong>{roleLabel} Agent</strong><span>{failed ? copy(locale, "Failed", "处理失败") : copy(locale, "Working", "处理中")}</span></div>
        <div className="a2a-agent-progress">
          <span className="is-complete">{copy(locale, "Message accepted", "消息已进入群聊")}</span>
          <span className={failed ? "is-failed" : "is-active"}>{activity.detail}</span>
        </div>
      </div>
    </article>
  );
}

function formatTime(createdAt: string) {
  const match = /T(\d{2}):(\d{2})/u.exec(createdAt);
  return match ? `${match[1]}:${match[2]}` : "--:--";
}

function citationTargets(message: AgentMessage): ReviewEvidenceTarget[] {
  return message.citations.map((citation) => ({ ...citation, evidenceRefs: [citation.evidenceRef] }));
}

function messageReference(message: AgentMessage, locale: "en" | "zh-CN"): CollaborationContextReference {
  const author = message.authorType === "agent" ? `${formatAgentRole(message.role, locale)} Agent` : formatAgentRole(message.role, locale);
  return { kind: "agent_message", id: message.id, label: `${author} · ${message.content}`, createdAt: message.createdAt };
}

function GroupMessage({ accountRole, message, referenced, evidenceLabels, selectedTarget, showProvenance, onReference, onEvidenceActivate }: {
  accountRole: AccountRole;
  message: AgentMessage;
  referenced: boolean;
  evidenceLabels: Map<string, string>;
  selectedTarget: ReviewEvidenceTarget | null;
  showProvenance: boolean;
  onReference: (reference: CollaborationContextReference) => void;
  onEvidenceActivate: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const targets = citationTargets(message);
  const roleLabel = formatAgentRole(message.role, locale);
  const author = message.authorType === "agent" ? `${roleLabel} Agent` : roleLabel;
  const isOwn = message.authorType === "human" && message.role === accountRole;
  const content = message.authorType === "human" ? quotedSourceText(message.content, locale) : formatCanonicalNarrative(message.content, locale);
  return (
    <article className={`a2a-group-message role-${message.role} author-${message.authorType} ${isOwn ? "is-own" : ""} ${referenced ? "is-referenced" : ""}`}>
      <span aria-hidden="true" className="a2a-avatar">{message.authorType === "agent" ? "AI" : roleLabel.slice(0, 1)}</span>
      <div className="a2a-message-body">
        <div className="a2a-message-meta"><strong>{author}</strong><time dateTime={message.createdAt}>{formatTime(message.createdAt)}</time><button aria-label={copy(locale, `Quote ${author} message`, `引用${author}消息`)} aria-pressed={referenced} onClick={() => onReference(messageReference(message, locale))} type="button">{copy(locale, "Quote", "引用")}</button></div>
        <p>{content}</p>
        {targets.length ? <div className="a2a-citations">{targets.map((target, index) => <button aria-label={copy(locale, `Open evidence reference ${index + 1}`, `打开证据引用 ${index + 1}`)} aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} key={`${message.id}-${target.evidenceRef}-${index}`} onClick={() => onEvidenceActivate(target)} type="button">{formatCanonicalLabel(evidenceLabels.get(target.evidenceRef) ?? target.evidenceRef, locale)}</button>)}</div> : null}
        {showProvenance && message.execution ? <small className="a2a-provenance">advisory-only · {message.execution.providerId}/{message.execution.modelId}</small> : null}
      </div>
    </article>
  );
}

function GroupComposer({ accountRole, agentBusy, reference, annotationReference, settings, onAttachAnnotation, onRequestAnnotation, onClearReference, onSubmit, onImportMaterialPackage, onConfirmMaterialImport }: {
  accountRole: AccountRole;
  agentBusy: boolean;
  reference: CollaborationContextReference | null;
  annotationReference: Extract<CollaborationContextReference, { kind: "material_annotation" }> | null;
  settings: CollaborationViewSettings;
  onAttachAnnotation: () => void;
  onRequestAnnotation?: () => void;
  onClearReference: () => void;
  onSubmit: A2ACollaborationPanelProps["onSubmitMessage"];
  onImportMaterialPackage: A2ACollaborationPanelProps["onImportMaterialPackage"];
  onConfirmMaterialImport: A2ACollaborationPanelProps["onConfirmMaterialImport"];
}) {
  const locale = usePublicLocale();
  const [message, setMessage] = useState("");
  const [target, setTarget] = useState<ChatAgentRole | null>(null);
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importPending, setImportPending] = useState(false);
  const [openTool, setOpenTool] = useState<"voice" | "mcp" | null>(null);
  const [importPreview, setImportPreview] = useState<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mentionPattern = /^@(业务|风控)\s*/u;
  const messageBody = message.replace(mentionPattern, "").trim();
  const chooseTarget = (nextTarget: ChatAgentRole | null, label: string) => {
    setTarget(nextTarget);
    setMessage((current) => {
      const body = current.replace(mentionPattern, "");
      return nextTarget ? `${label} ${body}` : body;
    });
    setStatus(null);
    setError(null);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  };
  const submit = async () => {
    if (!messageBody || pending) return;
    setPending(true); setError(null); setStatus(null);
    try {
      await onSubmit(message.trim(), target, reference, {
        responseDepth: settings.responseDepth,
        responseFocus: settings.responseFocus,
        customGuidance: settings.customGuidance.trim(),
      });
      setMessage(""); setTarget(null); onClearReference();
      setStatus(target ? copy(locale, `Message sent · ${formatAgentRole(target, locale)} Agent was notified`, `消息已发送 · 已通知${formatAgentRole(target, locale)} Agent`) : copy(locale, "Message sent · no Agent triggered", "消息已发送 · 未触发 Agent"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy(locale, "Send failed", "发送失败"));
    } finally {
      setPending(false);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
    }
  };
  const upload = async (file: File | null) => {
    if (!file || importPending || accountRole !== "business") return;
    if (file.size <= 0 || file.size > MAX_MATERIAL_PACKAGE_BYTES) { setError(file.size <= 0 ? copy(locale, "The material package is empty.", "材料包为空") : copy(locale, "The material package cannot exceed 100 MiB.", "材料包不能超过 100 MiB")); return; }
    setImportPending(true); setError(null);
    try { setImportPreview(await onImportMaterialPackage(file)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : copy(locale, "Upload failed", "上传失败")); }
    finally { setImportPending(false); }
  };
  const confirmImport = async () => {
    if (!importPreview || importPending) return;
    setImportPending(true); setError(null);
    try { await onConfirmMaterialImport(importPreview.preflight); setImportPreview(null); setStatus(copy(locale, "Material package imported", "材料包已导入")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : copy(locale, "Import failed", "导入失败")); }
    finally { setImportPending(false); }
  };
  const targets: Array<{ value: ChatAgentRole | null; label: string }> = [
    { value: null, label: copy(locale, "Chat", "普通聊天") },
    { value: "business", label: "@业务" },
    { value: "risk", label: "@风控" },
  ];
  return (
    <footer className="a2a-group-composer">
      {reference ? <div className={`a2a-reference ${reference.kind === "material_annotation" ? "is-material-annotation" : ""}`}>{reference.kind === "material_annotation" && reference.snapshotDataUrl ? <img alt={copy(locale, "Material annotation snapshot", "材料注释截图")} src={reference.snapshotDataUrl} /> : null}<span>{reference.kind === "material_annotation" ? copy(locale, `Material annotation · ${reference.matchStatus}`, `材料注释 · ${reference.matchStatus === "exact" ? "元素精确定位" : reference.matchStatus === "confirmed" ? "OCR 已匹配" : "OCR 待确认"}`) : copy(locale, "Quoted context", "引用")} · {reference.label}</span><button onClick={onClearReference} type="button">×</button></div> : null}
      <div className="a2a-routing-options" aria-label={copy(locale, "Choose whether to notify an Agent", "选择是否通知 Agent")}>{targets.map((item) => { const agentDisabled = item.value !== null && !settings.enabledAgents[item.value]; return <button aria-pressed={target === item.value} disabled={(agentBusy && item.value !== null) || agentDisabled} key={item.value ?? "chat"} onClick={() => chooseTarget(item.value, item.label)} title={agentDisabled ? copy(locale, "This Agent is paused in Settings.", "该 Agent 已在设置中暂停。") : agentBusy && item.value !== null ? copy(locale, "An Agent is already working. Normal chat remains available.", "已有 Agent 正在处理；仍可继续普通聊天。") : undefined} type="button">{item.label}</button>; })}</div>
      <div className="a2a-compact-tool-row">
        <input accept=".zip,application/zip" aria-label={copy(locale, "Choose a ZIP material package", "选择材料包 ZIP 文件")} hidden onChange={(event) => { void upload(event.target.files?.[0] ?? null); event.currentTarget.value = ""; }} ref={fileInputRef} type="file" />
        <button disabled={accountRole !== "business" || importPending} onClick={() => fileInputRef.current?.click()} type="button"><Icon name="link" />{copy(locale, "Material package", "材料包")}</button>
        <button aria-label={annotationReference ? copy(locale, "Attach the prepared annotation", "附加已生成的注释") : copy(locale, "Start a visual annotation", "开始框选注释")} onClick={() => annotationReference ? onAttachAnnotation() : onRequestAnnotation?.()} title={annotationReference ? copy(locale, "Attach the current exact or visual location", "附加当前精确定位或视觉区域") : copy(locale, "Open the source material and drag to select a region", "打开原始材料并拖动框选区域")} type="button"><Icon name="material" />{annotationReference ? copy(locale, "Attach annotation", "附加注释") : copy(locale, "Select annotation", "框选注释")}</button>
        <span className="a2a-tool-spacer" />
        <button aria-expanded={openTool === "voice"} aria-label={copy(locale, "Voice input placeholder", "语音输入预留")} onClick={() => setOpenTool((current) => current === "voice" ? null : "voice")} type="button"><Icon name="microphone" />{copy(locale, "Voice", "语音")}</button>
        <button aria-expanded={openTool === "mcp"} aria-label={copy(locale, "MCP tools placeholder", "MCP 工具预留")} onClick={() => setOpenTool((current) => current === "mcp" ? null : "mcp")} type="button"><Icon name="mcp" />MCP</button>
      </div>
      {openTool ? <div className="a2a-tool-reservation" role="status"><strong>{openTool === "voice" ? copy(locale, "Voice input", "语音输入") : "MCP"}</strong><span>{openTool === "voice" ? copy(locale, "The microphone entry is reserved. Recording permission is not requested in this version.", "已预留麦克风入口；当前版本不会请求录音权限。") : copy(locale, "The MCP tool entry is reserved. No project tool is configured yet.", "已预留 MCP 工具入口；当前项目尚未配置可调用工具。")}</span></div> : null}
      <div className="a2a-compose-row"><textarea aria-label={copy(locale, "Project group chat input", "项目群聊输入")} aria-busy={pending} disabled={pending || importPending} onChange={(event) => { setMessage(event.target.value); setStatus(null); setError(null); }} onKeyDown={(event) => { if (!settings.sendOnEnter || event.key !== "Enter" || event.nativeEvent.isComposing || event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return; event.preventDefault(); void submit(); }} placeholder={target ? copy(locale, `Send to the group and notify ${formatAgentRole(target, locale)} Agent…`, `发到群里，并通知${formatAgentRole(target, locale)} Agent…`) : copy(locale, "Write a group message…", "发送一条群消息…")} ref={textareaRef} rows={2} value={message} /><Button aria-busy={pending} aria-label={pending ? copy(locale, "Sending group message", "正在发送群消息") : copy(locale, "Send group message", "发送群消息")} disabled={pending || importPending || !messageBody} onClick={() => void submit()}>{pending ? <span aria-hidden="true" className="a2a-send-spinner" /> : <Icon name="send" />}</Button></div>
      {importPreview ? <div className="a2a-import-confirm"><span>{copy(locale, `${importPreview.preflight.items.length} items ready to import`, `${importPreview.preflight.items.length} 项待导入`)}</span><Button disabled={importPending} onClick={() => void confirmImport()} variant="primary">{copy(locale, "Confirm", "确认")}</Button><Button disabled={importPending} onClick={() => setImportPreview(null)}>{copy(locale, "Cancel", "取消")}</Button></div> : null}
      {pending ? <small className="a2a-submit-state is-sending" role="status">{copy(locale, "Sending message…", "正在发送消息…")}</small> : status ? <small className="a2a-submit-state is-success" role="status">{status}</small> : null}{error ? <small className="a2a-submit-state is-error" role="alert">{error}</small> : null}
    </footer>
  );
}

export function A2ACollaborationPanel({ accountRole, agentActivity, agentMessages, agentError, evidence, selectedTarget, annotationReference = null, collapsed = false, maximized = false, onToggleMaximized, onRequestAnnotation, onAgentEvidenceActivate, onSubmitMessage, onImportMaterialPackage, onConfirmMaterialImport }: A2ACollaborationPanelProps) {
  const locale = usePublicLocale();
  const [reference, setReference] = useState<CollaborationContextReference | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(accountRole === "leadership");
  const [viewSettings, setViewSettings] = useState(DEFAULT_COLLABORATION_VIEW_SETTINGS);
  const evidenceLabels = useMemo(() => new Map(evidence.map((item) => [item.id, item.label])), [evidence]);
  const messages = useMemo(() => agentMessages.filter((message) => message.role !== "leadership").sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id)), [agentMessages]);
  const feedRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const feed = feedRef.current;
    if (feed && viewSettings.autoScroll) feed.scrollTop = feed.scrollHeight;
  }, [messages.length, agentActivity?.phase, agentActivity?.sourceMessageId, viewSettings.autoScroll]);
  const toggleReference = (next: CollaborationContextReference) => setReference((current) => current?.kind === next.kind && current.id === next.id ? null : next);
  const canParticipate = accountRole === "business" || accountRole === "risk";
  return (
    <div className={`a2a-panel a2a-embedded-chat ${collapsed ? "is-collapsed" : ""} ${viewSettings.compactMessages ? "is-compact-messages" : ""}`} data-semantic-localized="true">
      <section className={`a2a-group-chat ${collapsed ? "is-collapsed" : ""}`}>
        <header className="a2a-section-header a2a-group-header">
          <div><strong>{settingsOpen ? copy(locale, "Agent settings", "Agent 设置") : copy(locale, `Project group chat · ${messages.length}`, `项目群聊 · ${messages.length}`)}</strong><small>{settingsOpen ? copy(locale, "Dashboard · Settings never speaks", "Dashboard · 设置不参与发言") : copy(locale, "Natural timeline · Business and Risk only", "自然时序 · 仅业务与风控")}</small></div>
          <div className="a2a-chat-header-actions"><div className="a2a-participants" aria-label={copy(locale, "Group participants and settings", "群聊成员与设置")}><span className={accountRole === "business" ? "is-me" : ""}>业务</span><span className={accountRole === "risk" ? "is-me" : ""}>风控</span><button aria-label={copy(locale, "Open Agent settings dashboard", "打开 Agent 设置 Dashboard")} aria-pressed={settingsOpen} onClick={() => setSettingsOpen((current) => !current)} title={copy(locale, "Agent settings", "Agent 设置")} type="button"><Icon name="settings" /></button></div>{onToggleMaximized ? <button aria-label={maximized ? copy(locale, "Exit project group chat fullscreen", "退出项目群聊全屏") : copy(locale, "Fullscreen project group chat", "全屏项目群聊")} aria-pressed={maximized} className="a2a-chat-toggle" onClick={onToggleMaximized} title={maximized ? copy(locale, "Exit fullscreen", "退出全屏") : copy(locale, "Fullscreen", "全屏")} type="button"><Icon name={maximized ? "collapse" : "expand"} /></button> : null}</div>
        </header>
        {!collapsed ? <>
          {settingsOpen ? <AgentSettingsDashboard messages={messages} onChange={setViewSettings} onClose={() => setSettingsOpen(false)} settings={viewSettings} /> : <>
            {agentError ? <div className="a2a-panel-error" role="alert">{formatServiceMessage(agentError, locale)}</div> : null}
            <div className="a2a-group-feed" aria-label={copy(locale, "Project group chat history", "项目群聊记录")} ref={feedRef}>{messages.length || agentActivity ? <>{messages.map((message) => <GroupMessage accountRole={accountRole} evidenceLabels={evidenceLabels} key={message.id} message={message} onEvidenceActivate={onAgentEvidenceActivate} onReference={toggleReference} referenced={reference?.kind === "agent_message" && reference.id === message.id} selectedTarget={selectedTarget} showProvenance={viewSettings.showProvenance} />)}{agentActivity ? <AgentActivity activity={agentActivity} /> : null}</> : <EmptyState detail={copy(locale, "Start with a normal message or explicitly mention Business or Risk.", "直接说话，或明确 @业务 / @风控。") } title={copy(locale, "No group messages yet", "群聊还没有消息")} />}</div>
            {canParticipate ? <GroupComposer accountRole={accountRole} agentBusy={agentActivity?.phase === "thinking"} annotationReference={annotationReference} onAttachAnnotation={() => annotationReference && setReference({ ...annotationReference, createdAt: new Date().toISOString() })} onRequestAnnotation={onRequestAnnotation} onClearReference={() => setReference(null)} onConfirmMaterialImport={onConfirmMaterialImport} onImportMaterialPackage={onImportMaterialPackage} onSubmit={onSubmitMessage} reference={reference} settings={viewSettings} /> : <div className="a2a-settings-only-note" role="status">{copy(locale, "This account manages settings and does not participate in group chat.", "当前账号用于管理设置，不参与群聊发言。")}</div>}
          </>}
        </> : null}
      </section>
    </div>
  );
}
