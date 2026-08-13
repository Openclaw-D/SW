import { useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { AgentFocusEvent, AgentMessage, AgentRole, CollaborationContextReference } from "../contracts/agentCommunication";
import type { MaterialImportPreflight, MaterialImportResult, MaterialUploadReceipt } from "../contracts/materialIntelligence";
import { DIMENSION_IDS } from "../contracts/workbench";
import type { DimensionDefinition, EvidenceReference, FactVersion, HardConstraintResult, MappedCommonReviewEvent, ReviewEvidenceTarget } from "../contracts/workbench";
import { buildCollaborationStream, compareCollaborationStreamItems, type CollaborationStreamItem } from "../lib/collaborationStream";
import { copy, formatAgentRole, formatCanonicalLabel, formatCanonicalNarrative, formatCollaborationKind, formatDimensionName, formatFactValue, formatServiceMessage, quotedSourceText, usePublicLocale } from "../lib/publicLocale";
import { sameReviewEvidenceTarget } from "../lib/workbenchLogic";
import { dimensionColorVar, Icon } from "./icons";
import { Button, EmptyState } from "./ui";

const MAX_MATERIAL_PACKAGE_BYTES = 100 * 1024 * 1024;

type AgentSubmit = (message: string, reference: CollaborationContextReference | null) => Promise<void>;

interface A2ACollaborationPanelProps {
  dimensions: DimensionDefinition[];
  events: MappedCommonReviewEvent[];
  agentMessages: AgentMessage[];
  agentFocusEvents: AgentFocusEvent[];
  agentError: string | null;
  evidence: EvidenceReference[];
  rules: HardConstraintResult[];
  selectedTarget: ReviewEvidenceTarget | null;
  facts: FactVersion[];
  correctionPending: boolean;
  correctionMessage: string | null;
  onCorrection: (factId: string, value: string, reason: string) => Promise<void>;
  onAgentEvidenceActivate: (target: ReviewEvidenceTarget) => void;
  onSubmitBusiness: AgentSubmit;
  onSubmitLeadership: AgentSubmit;
  onSubmitRisk: AgentSubmit;
  onImportMaterialPackage: (file: File) => Promise<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight }>;
  onConfirmMaterialImport: (preflight: MaterialImportPreflight) => Promise<MaterialImportResult>;
}

interface CoordinationEntry extends CollaborationStreamItem {
  messageRole?: AgentRole;
}

function formatShortDate(createdAt: string, locale: "en" | "zh-CN") {
  const match = /^(\d{4})-(\d{2})-(\d{2})/u.exec(createdAt);
  return match ? `${match[1].slice(2)}-${match[2]}-${match[3]}` : copy(locale, "Date unverified", "日期待核");
}

function formatTime(createdAt: string) {
  const match = /T(\d{2}):(\d{2})/u.exec(createdAt);
  return match ? `${match[1]}:${match[2]}` : "--:--";
}

function messageReference(message: AgentMessage, locale: "en" | "zh-CN"): CollaborationContextReference {
  return {
    kind: "agent_message",
    id: message.id,
    label: `${message.authorType === "human" ? copy(locale, "User", "用户") : `${formatAgentRole(message.role, locale)} Agent`} · ${message.authorType === "human" ? quotedSourceText(message.content, locale) : formatCanonicalNarrative(message.content, locale)}`,
    createdAt: message.createdAt,
  };
}

function citationTargets(message: AgentMessage): ReviewEvidenceTarget[] {
  return message.citations.map((citation) => ({ ...citation, evidenceRefs: [citation.evidenceRef] }));
}

function DialogueMessage({ message, referenced, evidenceLabels, selectedTarget, onReference, onEvidenceActivate }: {
  message: AgentMessage;
  referenced: boolean;
  evidenceLabels: Map<string, string>;
  selectedTarget: ReviewEvidenceTarget | null;
  onReference: (reference: CollaborationContextReference) => void;
  onEvidenceActivate: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const targets = citationTargets(message);
  const author = message.authorType === "human" ? copy(locale, "User", "用户") : `${formatAgentRole(message.role, locale)} Agent`;
  const content = message.authorType === "human" ? quotedSourceText(message.content, locale) : formatCanonicalNarrative(message.content, locale);
  return (
    <article className={`a2a-dialogue-message author-${message.authorType} ${referenced ? "is-referenced" : ""}`} data-semantic-localized="true">
      <span className="a2a-avatar" aria-hidden="true">{message.authorType === "human" ? copy(locale, "Me", "我") : formatAgentRole(message.role, locale).slice(0, 1)}</span>
      <div className="a2a-message-body">
        <div className="a2a-message-meta"><span>{author}</span><time dateTime={message.createdAt}>{formatTime(message.createdAt)}</time><button aria-label={copy(locale, `Quote ${author} message`, `引用${author}消息`)} aria-pressed={referenced} onClick={() => onReference(messageReference(message, locale))} type="button">{copy(locale, "Quote", "引用")}</button></div>
        <p>{content}</p>
        {targets.length ? <div className="a2a-citations">{targets.map((target, index) => <button aria-label={copy(locale, `Open evidence reference ${index + 1}`, `打开证据引用 ${index + 1}`)} aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} key={`${message.id}-${target.evidenceRef}-${index}`} onClick={() => onEvidenceActivate(target)} type="button">{formatCanonicalLabel(evidenceLabels.get(target.evidenceRef) ?? target.evidenceRef, locale)}</button>)}</div> : null}
      </div>
    </article>
  );
}

function ToolComposer({ role, reference, onClearReference, onPendingChange, onSubmit, onImportMaterialPackage, onConfirmMaterialImport }: {
  role: AgentRole;
  reference: CollaborationContextReference | null;
  onClearReference: () => void;
  onPendingChange: (pending: boolean) => void;
  onSubmit: AgentSubmit;
  onImportMaterialPackage?: A2ACollaborationPanelProps["onImportMaterialPackage"];
  onConfirmMaterialImport?: A2ACollaborationPanelProps["onConfirmMaterialImport"];
}) {
  const locale = usePublicLocale();
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [submitState, setSubmitState] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [importPending, setImportPending] = useState(false);
  const [importPreview, setImportPreview] = useState<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const label = formatAgentRole(role, locale);

  const submit = async () => {
    if (!message.trim() || pending) return;
    setPending(true);
    setSubmitState("sending");
    onPendingChange(true);
    setError(null);
    try {
      await onSubmit(message.trim(), reference);
      setMessage("");
      setSubmitState("success");
      onClearReference();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy(locale, "Send failed", "发送失败"));
      setSubmitState("error");
    } finally {
      setPending(false);
      onPendingChange(false);
    }
  };

  const upload = async (file: File | null) => {
    if (!file || !onImportMaterialPackage || importPending) return;
    if (file.size <= 0 || file.size > MAX_MATERIAL_PACKAGE_BYTES) {
      setError(file.size <= 0 ? copy(locale, "The material package is empty.", "材料包为空") : copy(locale, "The material package cannot exceed 100 MiB.", "材料包不能超过 100 MiB"));
      return;
    }
    setImportPending(true);
    setError(null);
    try {
      setImportPreview(await onImportMaterialPackage(file));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy(locale, "Upload failed", "上传失败"));
    } finally {
      setImportPending(false);
    }
  };

  const confirmImport = async () => {
    if (!importPreview || !onConfirmMaterialImport || importPending) return;
    setImportPending(true);
    setError(null);
    try {
      await onConfirmMaterialImport(importPreview.preflight);
      setImportPreview(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy(locale, "Import failed", "导入失败"));
    } finally {
      setImportPending(false);
    }
  };

  return (
    <footer aria-busy={pending} className="a2a-composer" data-semantic-localized="true">
      {reference ? <div className="a2a-reference"><span>{copy(locale, "Quoted context", "引用")} · {reference.label}</span><button aria-label={copy(locale, "Clear quoted context", "取消引用")} onClick={onClearReference} type="button">×</button></div> : null}
      <div className="a2a-tool-row" aria-label={copy(locale, `${label} conversation tools`, `${label}对话工具`)}>
        <input accept=".zip,application/zip" aria-label={copy(locale, "Choose a ZIP material package", "选择材料包 ZIP 文件")} hidden onChange={(event) => { void upload(event.target.files?.[0] ?? null); event.currentTarget.value = ""; }} ref={fileInputRef} type="file" />
        <button disabled={!onImportMaterialPackage || importPending} onClick={() => fileInputRef.current?.click()} type="button">{copy(locale, "Upload", "上传")}</button>
        <button disabled type="button">{copy(locale, "Voice", "语音")}</button>
        <button disabled type="button">MCP</button>
        <button disabled type="button">Skills</button>
      </div>
      <div className="a2a-compose-row">
        <textarea aria-label={copy(locale, `${label} conversation input`, `${label}对话输入`)} disabled={pending || importPending} onChange={(event) => { setMessage(event.target.value); if (submitState !== "sending") { setSubmitState("idle"); setError(null); } }} onKeyDown={(event) => {
          if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
          if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          void submit();
        }} placeholder={copy(locale, `Discuss this project with the ${label} Agent…`, `和${label} Agent 讨论…`)} rows={4} value={message} />
        <Button aria-label={copy(locale, `Send message to the ${label} Agent`, `发送${label}对话`)} disabled={pending || importPending || !message.trim()} onClick={() => void submit()}><Icon name="send" /></Button>
      </div>
      {importPreview ? <div className="a2a-import-confirm"><span>{copy(locale, `${importPreview.preflight.items.length} items ready to import`, `${importPreview.preflight.items.length} 项待导入`)}</span><Button disabled={importPending} onClick={() => void confirmImport()} variant="primary">{copy(locale, "Confirm", "确认")}</Button><Button disabled={importPending} onClick={() => setImportPreview(null)}>{copy(locale, "Cancel", "取消")}</Button></div> : null}
      {submitState !== "idle" ? <small className={`a2a-submit-state is-${submitState}`} role={submitState === "error" ? "alert" : "status"}>{submitState === "sending" ? copy(locale, "Sent · processing", "已发送 · 正在处理") : submitState === "success" ? copy(locale, "Response complete", "回复完成") : copy(locale, `Send failed · ${formatServiceMessage(error, locale)}`, `发送失败 · ${error ?? "请重试"}`)}</small> : null}
    </footer>
  );
}

function RoleHeader({ role, selected, replying, onSelect }: { role: AgentRole; selected: boolean; replying: boolean; onSelect: () => void }) {
  const locale = usePublicLocale();
  return (
    <header className="a2a-role-header">
      <button aria-label={copy(locale, `Select ${formatAgentRole(role, locale)} conversation`, `选择${formatAgentRole(role, locale)}对话`)} aria-pressed={selected} className="a2a-role-select" onClick={onSelect} type="button">{formatAgentRole(role, locale)}</button>
      <span className={`a2a-presence ${replying ? "is-replying" : ""}`}><i aria-hidden="true" />{replying ? copy(locale, "Replying", "回复中") : copy(locale, "Online", "在线")}</span>
    </header>
  );
}

function A2AFormalCorrection({ facts, pending, resultMessage, onSubmit }: { facts: FactVersion[]; pending: boolean; resultMessage: string | null; onSubmit: (factId: string, value: string, reason: string) => Promise<void> }) {
  const locale = usePublicLocale();
  const [factId, setFactId] = useState(facts[0]?.id ?? "");
  const selected = facts.find((fact) => fact.id === factId) ?? facts[0];
  const [value, setValue] = useState(selected ? String(selected.value) : "");
  const [reasonOverride, setReasonOverride] = useState<string | null>(null);
  const reason = reasonOverride ?? copy(locale, "Manually checked against supplemental material", "依据补充材料人工核对");
  return (
    <details className="approval-correction a2a-formal-correction" data-semantic-localized="true">
      <summary><Icon name="business" /><span>{copy(locale, "Formal business correction", "正式业务修正")}</span><small>{copy(locale, "Human Gate · creates a new fact version", "人工 Gate · 生成新事实版本")}</small></summary>
      <div className="correction-form">
        <label>{copy(locale, "Field", "字段")}<select aria-label={copy(locale, "Choose field to correct", "选择修正字段")} disabled={pending} onChange={(event) => { const next = facts.find((fact) => fact.id === event.target.value); setFactId(event.target.value); setValue(next ? String(next.value) : ""); }} value={selected?.id ?? ""}>{facts.map((fact) => <option key={fact.id} value={fact.id}>{formatCanonicalLabel(fact.label, locale)} · {copy(locale, `version ${fact.version}`, `版本 ${fact.version}`)} · {formatFactValue(fact.value, fact.unit, locale)}</option>)}</select></label>
        <label>{copy(locale, "Proposed value", "建议值")}<input aria-label={copy(locale, "Proposed correction value", "业务修正建议值")} disabled={pending} onChange={(event) => setValue(event.target.value)} value={value} /></label>
        <label>{copy(locale, "Reason", "原因")}<input aria-label={copy(locale, "Business correction reason", "业务修正原因")} disabled={pending} onChange={(event) => setReasonOverride(event.target.value)} value={reason} /></label>
        <Button disabled={pending || !selected || !value.trim() || !reason.trim()} onClick={() => selected && void onSubmit(selected.id, value, reason)} variant="primary">{pending ? copy(locale, "Submitting…", "提交中…") : copy(locale, "Submit correction", "提交修正")}</Button>
      </div>
      {resultMessage ? <p className="form-status" role="status">{formatServiceMessage(resultMessage, locale)}</p> : null}
    </details>
  );
}

function SideDialogue({ role, selected, replying, messages, reference, evidenceLabels, selectedTarget, facts, correctionPending, correctionMessage, onCorrection, onSelect, onReference, onClearReference, onPendingChange, onSubmit, onEvidenceActivate, onImportMaterialPackage, onConfirmMaterialImport }: {
  role: "business" | "risk";
  selected: boolean;
  replying: boolean;
  messages: AgentMessage[];
  reference: CollaborationContextReference | null;
  evidenceLabels: Map<string, string>;
  selectedTarget: ReviewEvidenceTarget | null;
  facts?: FactVersion[];
  correctionPending?: boolean;
  correctionMessage?: string | null;
  onCorrection?: A2ACollaborationPanelProps["onCorrection"];
  onSelect: () => void;
  onReference: (reference: CollaborationContextReference) => void;
  onClearReference: () => void;
  onPendingChange: (pending: boolean) => void;
  onSubmit: AgentSubmit;
  onEvidenceActivate: (target: ReviewEvidenceTarget) => void;
  onImportMaterialPackage?: A2ACollaborationPanelProps["onImportMaterialPackage"];
  onConfirmMaterialImport?: A2ACollaborationPanelProps["onConfirmMaterialImport"];
}) {
  const locale = usePublicLocale();
  const visible = messages.filter((message) => message.role === role).sort((left, right) => left.createdAt.localeCompare(right.createdAt) || left.sequence - right.sequence || left.id.localeCompare(right.id));
  return (
    <section className={`a2a-role-column a2a-${role} ${selected ? "is-selected" : ""}`}>
      <RoleHeader onSelect={onSelect} replying={replying} role={role} selected={selected} />
      <div className="a2a-dialogue-feed" aria-label={copy(locale, `${formatAgentRole(role, locale)} conversation history`, `${formatAgentRole(role, locale)}对话记录`)}>
        {visible.length ? visible.map((message) => <DialogueMessage evidenceLabels={evidenceLabels} key={message.id} message={message} onEvidenceActivate={onEvidenceActivate} onReference={onReference} referenced={reference?.kind === "agent_message" && reference.id === message.id} selectedTarget={selectedTarget} />) : <EmptyState detail="" title={copy(locale, "No conversation yet", "暂无对话")} />}
      </div>
      {role === "business" && facts?.length && onCorrection ? <A2AFormalCorrection facts={facts} onSubmit={onCorrection} pending={Boolean(correctionPending)} resultMessage={correctionMessage ?? null} /> : null}
      <ToolComposer onClearReference={onClearReference} onConfirmMaterialImport={onConfirmMaterialImport} onImportMaterialPackage={onImportMaterialPackage} onPendingChange={onPendingChange} onSubmit={onSubmit} reference={reference} role={role} />
    </section>
  );
}

function leadershipEntries(messages: AgentMessage[], stream: CollaborationStreamItem[]): CoordinationEntry[] {
  const existing = new Set(stream.map((item) => item.agentMessageId).filter(Boolean));
  const extra = messages.filter((message) => message.role === "leadership" && !existing.has(message.id)).map<CoordinationEntry>((message) => ({
    id: `leadership:${message.id}`,
    kind: message.generatedContent?.questions.length ? "pending_question" : "confirmed_conclusion",
    createdAt: message.createdAt,
    sequence: message.sequence,
    actorRole: "leadership",
    actorLabel: message.authorType === "human" ? "用户" : "协调 Agent",
    title: message.authorType === "human" ? "协调提问" : "协调回复",
    summary: message.content,
    sourceLabel: "协调对话",
    dimensionId: message.citations[0]?.dimensionId ?? null,
    evidenceTargets: citationTargets(message),
    pending: Boolean(message.generatedContent?.questions.length),
    reviewEventId: null,
    agentMessageId: message.id,
    messageRole: message.role,
  }));
  return [...stream.filter((item) => item.kind !== "focus_event"), ...extra].sort(compareCollaborationStreamItems);
}

function dimensionIssueCounts(dimensions: DimensionDefinition[], entries: CoordinationEntry[], rules: HardConstraintResult[]) {
  return new Map(DIMENSION_IDS.map((dimensionId) => {
    const issueIds = new Set<string>();
    for (const entry of entries) if (entry.pending && entry.dimensionId === dimensionId) issueIds.add(entry.id);
    for (const rule of rules) if (rule.result !== "pass" && rule.evidenceTargets.some((target) => target.dimensionId === dimensionId)) issueIds.add(`rule:${rule.id}`);
    return [dimensionId, { count: issueIds.size, definition: dimensions.find((item) => item.id === dimensionId) }] as const;
  }));
}

function CoordinationColumn({ selected, replying, dimensions, entries, rules, reference, evidenceLabels, selectedTarget, onSelect, onReference, onClearReference, onPendingChange, onSubmit, onEvidenceActivate }: {
  selected: boolean;
  replying: boolean;
  dimensions: DimensionDefinition[];
  entries: CoordinationEntry[];
  rules: HardConstraintResult[];
  reference: CollaborationContextReference | null;
  evidenceLabels: Map<string, string>;
  selectedTarget: ReviewEvidenceTarget | null;
  onSelect: () => void;
  onReference: (reference: CollaborationContextReference) => void;
  onClearReference: () => void;
  onPendingChange: (pending: boolean) => void;
  onSubmit: AgentSubmit;
  onEvidenceActivate: (target: ReviewEvidenceTarget) => void;
}) {
  const locale = usePublicLocale();
  const counts = dimensionIssueCounts(dimensions, entries, rules);
  const groups = entries.reduce<Array<{ date: string; items: CoordinationEntry[] }>>((result, item) => {
    const date = formatShortDate(item.createdAt, locale);
    const latest = result.at(-1);
    if (latest?.date === date) latest.items.push(item);
    else result.push({ date, items: [item] });
    return result;
  }, []);
  return (
    <section className={`a2a-role-column a2a-coordination ${selected ? "is-selected" : ""}`} data-semantic-localized="true">
      <RoleHeader onSelect={onSelect} replying={replying} role="leadership" selected={selected} />
      <div className="a2a-dimension-chain" aria-label={copy(locale, "Six-dimension issue chain", "六维问题链路")}>
        {DIMENSION_IDS.map((dimensionId) => {
          const item = counts.get(dimensionId);
          return <span className={item?.count ? "has-issue" : ""} key={dimensionId} style={{ "--a2a-dimension-color": dimensionColorVar[dimensionId] } as CSSProperties}><b>{item?.count ?? 0}</b><small>{formatDimensionName(dimensionId, locale, item?.definition?.name)}</small></span>;
        })}
      </div>
      <div className="a2a-coordination-feed" aria-label={copy(locale, "Coordination chain", "协调链路")}>
        {groups.length ? groups.map((group) => <section className="a2a-date-group" key={group.date}><time>{group.date}</time>{group.items.map((item) => {
          const contextActor = item.actorRole === "system" ? copy(locale, "System", "系统") : formatAgentRole(item.actorRole, locale);
          const contextLabel = `${contextActor} · ${formatCanonicalNarrative(item.title, locale)}`;
          const contextReference: CollaborationContextReference | null = item.agentMessageId ? { kind: "agent_message", id: item.agentMessageId, label: contextLabel, createdAt: item.createdAt } : item.reviewEventId ? { kind: "review_event", id: item.reviewEventId, label: contextLabel, createdAt: item.createdAt } : null;
          const referenced = Boolean(contextReference && reference?.kind === contextReference.kind && reference.id === contextReference.id);
          return <article className={`a2a-chain-item ${item.pending ? "is-pending" : ""} ${referenced ? "is-referenced" : ""}`} key={item.id}><div className="a2a-chain-meta"><time dateTime={item.createdAt}>{formatTime(item.createdAt)}</time><span>{item.actorRole === "system" ? copy(locale, "System", "系统") : formatAgentRole(item.actorRole, locale)}</span><em>{formatCollaborationKind(item.kind, locale)}</em>{item.dimensionId ? <b>{formatDimensionName(item.dimensionId, locale, counts.get(item.dimensionId)?.definition?.name)}</b> : null}{contextReference ? <button aria-label={copy(locale, "Quote coordination item", "引用协调条目")} aria-pressed={referenced} onClick={() => onReference(contextReference)} type="button">{copy(locale, "Quote", "引用")}</button> : null}</div><p>{formatCanonicalNarrative(item.summary, locale)}</p>{item.evidenceTargets.length ? <div className="a2a-citations">{item.evidenceTargets.map((target, index) => <button aria-label={copy(locale, `Open evidence reference ${index + 1}`, `打开证据引用 ${index + 1}`)} aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} key={`${item.id}-${target.evidenceRef}-${index}`} onClick={() => onEvidenceActivate(target)} type="button">{formatCanonicalLabel(evidenceLabels.get(target.evidenceRef) ?? target.evidenceRef, locale)}</button>)}</div> : null}</article>;
        })}</section>) : <EmptyState detail="" title={copy(locale, "No coordination records yet", "暂无协调记录")} />}
      </div>
      <ToolComposer onClearReference={onClearReference} onPendingChange={onPendingChange} onSubmit={onSubmit} reference={reference} role="leadership" />
    </section>
  );
}

export function A2ACollaborationPanel({ dimensions, events, agentMessages, agentFocusEvents, agentError, evidence, facts, correctionPending, correctionMessage, rules, selectedTarget, onAgentEvidenceActivate, onCorrection, onSubmitBusiness, onSubmitLeadership, onSubmitRisk, onImportMaterialPackage, onConfirmMaterialImport }: A2ACollaborationPanelProps) {
  const locale = usePublicLocale();
  const [selectedRole, setSelectedRole] = useState<AgentRole>("business");
  const [reference, setReference] = useState<CollaborationContextReference | null>(null);
  const [replying, setReplying] = useState<Record<AgentRole, boolean>>({ business: false, leadership: false, risk: false });
  const evidenceLabels = useMemo(() => new Map(evidence.map((item) => [item.id, item.label])), [evidence]);
  const entries = useMemo(() => leadershipEntries(agentMessages, buildCollaborationStream(events, agentMessages, agentFocusEvents)), [agentFocusEvents, agentMessages, events]);
  const toggleReference = (next: CollaborationContextReference) => setReference((current) => current?.kind === next.kind && current.id === next.id ? null : next);
  const setRoleReplying = (role: AgentRole, pending: boolean) => setReplying((current) => ({ ...current, [role]: pending }));
  return (
    <div className="a2a-panel" data-semantic-localized="true">
      {agentError ? <div className="a2a-panel-error" role="alert">{formatServiceMessage(agentError, locale)}</div> : null}
      <div className="a2a-panel-columns">
        <SideDialogue correctionMessage={correctionMessage} correctionPending={correctionPending} evidenceLabels={evidenceLabels} facts={facts} messages={agentMessages} onClearReference={() => setReference(null)} onConfirmMaterialImport={onConfirmMaterialImport} onCorrection={onCorrection} onEvidenceActivate={onAgentEvidenceActivate} onImportMaterialPackage={onImportMaterialPackage} onPendingChange={(pending) => setRoleReplying("business", pending)} onReference={toggleReference} onSelect={() => setSelectedRole("business")} onSubmit={onSubmitBusiness} reference={reference} replying={replying.business} role="business" selected={selectedRole === "business"} selectedTarget={selectedTarget} />
        <CoordinationColumn dimensions={dimensions} entries={entries} evidenceLabels={evidenceLabels} onClearReference={() => setReference(null)} onEvidenceActivate={onAgentEvidenceActivate} onPendingChange={(pending) => setRoleReplying("leadership", pending)} onReference={toggleReference} onSelect={() => setSelectedRole("leadership")} onSubmit={onSubmitLeadership} reference={reference} replying={replying.leadership} rules={rules} selected={selectedRole === "leadership"} selectedTarget={selectedTarget} />
        <SideDialogue evidenceLabels={evidenceLabels} messages={agentMessages} onClearReference={() => setReference(null)} onEvidenceActivate={onAgentEvidenceActivate} onPendingChange={(pending) => setRoleReplying("risk", pending)} onReference={toggleReference} onSelect={() => setSelectedRole("risk")} onSubmit={onSubmitRisk} reference={reference} replying={replying.risk} role="risk" selected={selectedRole === "risk"} selectedTarget={selectedTarget} />
      </div>
    </div>
  );
}
