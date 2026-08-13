import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type { AgentFocusEvent, AgentMessage, AgentThread, CollaborationContextReference } from "../contracts/agentCommunication";
import type { MaterialImportPreflight, MaterialImportResult, MaterialUploadReceipt } from "../contracts/materialIntelligence";
import { DIMENSION_IDS } from "../contracts/workbench";
import type {
  ApprovalState,
  DimensionDefinition,
  EvidenceReference,
  FactVersion,
  HardConstraintResult,
  MappedCommonReviewEvent,
  ReviewEvidenceTarget,
} from "../contracts/workbench";
import { GRADE_COLOR_VARS, sameReviewEvidenceTarget } from "../lib/workbenchLogic";
import { buildCollaborationStream, type CollaborationStreamItem } from "../lib/collaborationStream";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatFactValue, formatServiceMessage, usePublicLocale } from "../lib/publicLocale";
import { A2ACollaborationPanel } from "./A2ACollaborationPanel";
import { Icon } from "./icons";
import { Button, EmptyState } from "./ui";

type ChainMode = "ready" | "loading" | "empty" | "error";
const approvalLabels: Record<ApprovalState["status"], string> = {
  draft: "暂存",
  returned: "已退回",
  submitted: "已提交",
  completed: "已完成",
};

const MAX_MATERIAL_PACKAGE_BYTES = 100 * 1024 * 1024;
const A2A_DEFAULT_SHARE = 30;
const A2A_MIN_SHARE = 22;
const A2A_MAX_SHARE = 55;
const A2A_SNAP_THRESHOLD = 24;
type A2AEdge = "business" | "coordination" | null;

function formatByteSize(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(bytes >= 10 * 1024 * 1024 ? 0 : 1)} MiB`;
}

function formatCompactTimestamp(createdAt: string | undefined) {
  if (!createdAt) return "暂无更新";
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/u.exec(createdAt);
  if (!match) return "时间待核";
  return `${match[2]}-${match[3]} ${match[4]}:${match[5]}`;
}

function Composer({ actor, onSubmit, onImportMaterialPackage, onConfirmMaterialImport, reference, onClearReference, showSimulationControls }: {
  actor: "business" | "risk";
  onSubmit: (message: string, reference: CollaborationContextReference | null) => Promise<void>;
  onImportMaterialPackage?: (file: File) => Promise<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight }>;
  onConfirmMaterialImport?: (preflight: MaterialImportPreflight) => Promise<MaterialImportResult>;
  reference: CollaborationContextReference | null;
  onClearReference: () => void;
  showSimulationControls: boolean;
}) {
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importPending, setImportPending] = useState(false);
  const [importPreview, setImportPreview] = useState<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight } | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const submit = async () => {
    if (!message.trim() || pending) return;
    setPending(true);
    setError(null);
    try {
      await onSubmit(message.trim(), reference);
      setMessage("");
      onClearReference();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提交失败，请稍后重试");
    } finally {
      setPending(false);
    }
  };
  const actorLabel = actor === "business" ? "业务" : "风控";
  const selectMaterialPackage = () => fileInputRef.current?.click();
  const uploadMaterialPackage = async (file: File | null) => {
    if (!file || importPending) return;
    if (file.size <= 0) { setImportMessage("材料包为空，请选择有效的 ZIP 文件。"); return; }
    if (file.size > MAX_MATERIAL_PACKAGE_BYTES) { setImportMessage("材料包不能超过 100 MiB。"); return; }
    setImportPending(true);
    setImportMessage(null);
    setImportPreview(null);
    try {
      if (!onImportMaterialPackage) return;
      setImportPreview(await onImportMaterialPackage(file));
    } catch (reason) {
      setImportMessage(reason instanceof Error ? reason.message : "材料包上传或预检失败，请稍后重试。");
    } finally {
      setImportPending(false);
    }
  };
  const confirmMaterialImport = async () => {
    if (!importPreview || importPending) return;
    setImportPending(true);
    setImportMessage(null);
    try {
      if (!onConfirmMaterialImport) return;
      const result = await onConfirmMaterialImport(importPreview.preflight);
      setImportPreview(null);
      setImportMessage(`已导入 ${result.importedCount} 项材料，权威数据已刷新。`);
    } catch (reason) {
      setImportMessage(reason instanceof Error ? reason.message : "材料导入失败，请稍后重试。");
    } finally {
      setImportPending(false);
    }
  };
  return (
    <div className="composer-wrap">
      {reference ? <div className="composer-reference-context" role="status"><span>引用 · {formatCompactTimestamp(reference.createdAt)} · {reference.label}</span><button aria-label="取消引用上下文" onClick={onClearReference} type="button">取消</button></div> : <small className="composer-reference-empty">可不引用材料、维度或历史条目，直接提交项目开放问题</small>}
      <div className="active-composer">
        {actor === "business" ? <><input accept=".zip,application/zip" aria-label="选择材料包 ZIP 文件" className="material-package-input" disabled={importPending} onChange={(event) => { void uploadMaterialPackage(event.target.files?.[0] ?? null); event.currentTarget.value = ""; }} ref={fileInputRef} type="file" /><Button aria-label="导入材料包" className="material-package-trigger" disabled={importPending} onClick={selectMaterialPackage} title="导入 ZIP 材料包" type="button"><span aria-hidden="true">+</span></Button></> : null}
        <input
          aria-label={`${actorLabel}对话输入`}
          disabled={pending || importPending}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void submit(); }}
          placeholder={actor === "business" ? "直接提项目问题，或补充业务说明…" : "直接提项目复核问题、判断或下一步…"}
          value={message}
        />
        <Button aria-label={`发送${actorLabel}对话`} disabled={pending || importPending || !message.trim()} onClick={() => void submit()}>
          <Icon name="send" />
        </Button>
      </div>
      <small className="composer-hint">{pending ? `正在等待${actorLabel} Agent…` : "普通讨论只留在左右对话；带引用或明确问题才投影到中栏"}</small>
      {!pending ? <small className="composer-note">{showSimulationControls ? "显式 synthetic 开发模式" : "真实 Provider 输出仍是 advisory-only，失败不会回退 synthetic"}</small> : null}
      {error ? <small className="composer-error" role="alert">{error}</small> : null}
      {importPreview ? <div className="material-import-preview" role="status"><span>已预检 {importPreview.preflight.items.length} 项 · {formatByteSize(importPreview.receipt.byteSize)}{importPreview.receipt.isSimulated || importPreview.preflight.isSimulated ? " · 模拟材料" : ""}</span><div><Button disabled={importPending} onClick={() => void confirmMaterialImport()} type="button" variant="primary">确认导入</Button><Button disabled={importPending} onClick={() => { setImportPreview(null); setImportMessage("已取消导入，材料尚未写入项目。"); }} type="button">取消</Button></div></div> : null}
      {importMessage ? <small className="composer-import-message" role="status">{importPending ? "正在上传或导入材料包…" : importMessage}</small> : null}
    </div>
  );
}

function AgentDialogueMessage({ message, referenced, evidenceLabels, selectedTarget, onContextToggle, onEvidenceActivate }: { message: AgentMessage; referenced: boolean; evidenceLabels: Map<string, string>; selectedTarget: ReviewEvidenceTarget | null; onContextToggle: (reference: CollaborationContextReference) => void; onEvidenceActivate: (target: ReviewEvidenceTarget) => void }) {
  const roleLabel = message.role === "business" ? "业务" : message.role === "risk" ? "风控" : "领导";
  const authorLabel = message.authorType === "human" ? "用户" : `${roleLabel} Agent`;
  const targets = message.citations.map((citation) => ({ ...citation, evidenceRefs: [citation.evidenceRef] }));
  const reference: CollaborationContextReference = { kind: "agent_message", id: message.id, label: `${authorLabel} · ${message.content}`, createdAt: message.createdAt };
  return (
    <article className={`dialogue-event agent-dialogue-message actor-${message.role} author-${message.authorType} ${referenced ? "is-context-referenced" : ""}`}>
      <span className="dialogue-avatar"><Icon name={message.authorType === "human" ? "business" : message.role === "leadership" ? "rule" : message.role} /></span>
      <span className="dialogue-body">
        <button aria-pressed={referenced} className={`dialogue-event-summary ${referenced ? "is-context-referenced" : ""}`} onClick={() => onContextToggle(reference)} type="button">
          <span className="dialogue-meta"><strong>{authorLabel}</strong><time dateTime={message.createdAt}>{formatCompactTimestamp(message.createdAt)}</time><b>{message.authorType === "human" ? "提问" : "辅助回复"}</b></span>
          <span className="dialogue-copy">{message.content}</span>
          {message.generatedContent?.observations.length ? <span className="agent-structured-line"><b>项目判断</b>{message.generatedContent.observations.join("；")}</span> : null}
          {message.generatedContent?.questions.length ? <span className="agent-structured-line"><b>未确定 / 下一步</b>{message.generatedContent.questions.join("；")}</span> : null}
        </button>
        {targets.length ? <span className="dialogue-references"><span className="dialogue-reference-list"><Icon name="material" /><span>事实引用：</span>{targets.map((target, index) => <button aria-label={`打开 Agent 引用材料 ${index + 1}：${evidenceLabels.get(target.evidenceRef) ?? "待定位材料"}`} aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""} key={`${message.id}-${target.evidenceRef}-${index}`} onClick={() => onEvidenceActivate(target)} type="button">{evidenceLabels.get(target.evidenceRef) ?? target.evidenceRef}</button>)}</span></span> : null}
        {message.execution ? <small className="agent-provenance">{message.execution.providerId}/{message.execution.modelId} · advisory-only · {message.execution.dataStatus}</small> : null}
      </span>
    </article>
  );
}

function BusinessCorrectionPanel({ facts, pending, resultMessage, onSubmit }: { facts: FactVersion[]; pending: boolean; resultMessage: string | null; onSubmit: (factId: string, value: string, reason: string) => Promise<void> }) {
  const locale = usePublicLocale();
  const [factId, setFactId] = useState(facts[0]?.id ?? "");
  const selected = facts.find((fact) => fact.id === factId) ?? facts[0];
  const [value, setValue] = useState(selected ? String(selected.value) : "");
  const [reasonOverride, setReasonOverride] = useState<string | null>(null);
  const reason = reasonOverride ?? copy(locale, "Manually checked against supplemental material", "依据补充材料人工核对");
  return (
    <details className="approval-correction" data-semantic-localized="true">
      <summary><Icon name="business" /><span>{copy(locale, "Business correction", "业务修正")}</span><small>{copy(locale, "Creates a new fact version", "生成新事实版本")}</small></summary>
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

function RoleColumn({
  actor,
  collapsed,
  messages,
  evidenceLabels,
  facts,
  correctionPending,
  correctionMessage,
  onToggle,
  onSubmit,
  onCorrection,
  onImportMaterialPackage,
  onConfirmMaterialImport,
  reference,
  onContextToggle,
  onClearContext,
  onAgentEvidenceActivate,
  selectedTarget,
  showSimulationControls,
}: {
  actor: "business" | "risk";
  collapsed: boolean;
  messages: AgentMessage[];
  evidenceLabels: Map<string, string>;
  facts: FactVersion[];
  correctionPending: boolean;
  correctionMessage: string | null;
  onToggle: () => void;
  onSubmit: (message: string, reference: CollaborationContextReference | null) => Promise<void>;
  reference: CollaborationContextReference | null;
  onContextToggle: (reference: CollaborationContextReference) => void;
  onClearContext: () => void;
  onAgentEvidenceActivate: (target: ReviewEvidenceTarget) => void;
  selectedTarget: ReviewEvidenceTarget | null;
  showSimulationControls: boolean;
  onCorrection: (factId: string, value: string, reason: string) => Promise<void>;
  onImportMaterialPackage: (file: File) => Promise<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight }>;
  onConfirmMaterialImport: (preflight: MaterialImportPreflight) => Promise<MaterialImportResult>;
}) {
  const business = actor === "business";
  const visibleMessages = messages.filter((message) => message.role === actor).sort((left, right) => left.createdAt.localeCompare(right.createdAt) || left.sequence - right.sequence);
  const label = business ? "业务" : "风控";
  return (
    <section className={`role-column role-column-${actor} ${collapsed ? "is-collapsed" : ""}`} id={`${actor}-dialogue-column`}>
      <header>
        <div><Icon name={actor} /><span><strong>{collapsed ? label : `用户 × ${label} Agent`}</strong>{!collapsed ? <small>自由项目对话 · 引用可选 · advisory-only</small> : null}</span></div>
        <Button aria-controls={`${actor}-dialogue-column`} aria-expanded={!collapsed} aria-label={`${collapsed ? "展开" : "折叠"}${label}对话`} className={`role-collapse-trigger direction-${business ? (collapsed ? "right" : "left") : (collapsed ? "left" : "right")}`} onClick={onToggle} title={`${collapsed ? "展开" : "折叠"}${label}对话`}><Icon name="chevron" /></Button>
      </header>
      {!collapsed ? (
        <>
          <div className="role-messages" aria-label={`${business ? "业务" : "风控"}对话记录`}>
            {visibleMessages.length ? visibleMessages.map((message) => <AgentDialogueMessage evidenceLabels={evidenceLabels} key={message.id} message={message} onContextToggle={onContextToggle} onEvidenceActivate={onAgentEvidenceActivate} referenced={reference?.kind === "agent_message" && reference.id === message.id} selectedTarget={selectedTarget} />) : <EmptyState detail="可直接提出项目全局问题；无需先选材料、维度或历史条目。" title="暂无 Agent 对话" />}
          </div>
          {business ? <BusinessCorrectionPanel facts={facts} onSubmit={onCorrection} pending={correctionPending} resultMessage={correctionMessage} /> : null}
          <Composer actor={actor} onClearReference={onClearContext} onConfirmMaterialImport={business ? onConfirmMaterialImport : undefined} onImportMaterialPackage={business ? onImportMaterialPackage : undefined} onSubmit={onSubmit} reference={reference} showSimulationControls={showSimulationControls} />
        </>
      ) : null}
    </section>
  );
}

function CoordinationContextBand({ dimensions, items }: { dimensions: DimensionDefinition[]; items: CollaborationStreamItem[] }) {
  const dimensionById = new Map(dimensions.map((dimension) => [dimension.id, dimension]));
  const latestItemByDimension = new Map<string, CollaborationStreamItem>();
  for (const item of items) {
    if (!item.dimensionId) continue;
    const dimensionItem = latestItemByDimension.get(item.dimensionId);
    if (!dimensionItem || dimensionItem.createdAt.localeCompare(item.createdAt) < 0 || (dimensionItem.createdAt === item.createdAt && dimensionItem.sequence < item.sequence)) latestItemByDimension.set(item.dimensionId, item);
  }
  const openIssues = items.filter((item) => item.pending).sort((left, right) => right.createdAt.localeCompare(left.createdAt) || right.sequence - left.sequence);
  const latestOpenIssue = openIssues[0];
  return (
    <section aria-label="领导协调六维状态摘要" className="coordination-context-band">
      <div className="coordination-dimension-strip">
        {DIMENSION_IDS.flatMap((id) => {
          const dimension = dimensionById.get(id);
          if (!dimension) return [];
          const latestItem = latestItemByDimension.get(id);
          const timestamp = formatCompactTimestamp(latestItem?.createdAt);
          return [
            <span className="coordination-status-node" data-grade={dimension.scoreGrade} key={dimension.id} style={{ "--score-color": GRADE_COLOR_VARS[dimension.scoreGrade] } as CSSProperties} title={latestItem ? `最近共享协作项：${timestamp}` : "该维度暂无共享协作项"}>
              <span className="coordination-status-mark"><i aria-hidden="true" /><strong>{dimension.scoreGrade}</strong><b>{dimension.name}</b></span>
              <time dateTime={latestItem?.createdAt}>{timestamp}</time>
            </span>,
          ];
        })}
      </div>
      <div aria-label="待回复问题" className="coordination-pending-summary">
        <strong>待回复问题</strong>
        <b>{openIssues.length}</b>
        <time dateTime={latestOpenIssue?.createdAt}>{latestOpenIssue ? formatCompactTimestamp(latestOpenIssue.createdAt) : "--"}</time>
        <span>{latestOpenIssue ? `${latestOpenIssue.title}：${latestOpenIssue.summary}` : "暂无待回复协调问题"}</span>
      </div>
    </section>
  );
}

function SharedStreamEvent({ item, evidenceLabels, selectedTarget, reference, onContextToggle, onEvidenceActivate }: { item: CollaborationStreamItem; evidenceLabels: Map<string, string>; selectedTarget: ReviewEvidenceTarget | null; reference: CollaborationContextReference | null; onContextToggle: (reference: CollaborationContextReference) => void; onEvidenceActivate: (target: ReviewEvidenceTarget) => void }) {
  const contextReference: CollaborationContextReference | null = item.agentMessageId
    ? { kind: "agent_message", id: item.agentMessageId, label: `${item.actorLabel} · ${item.title}`, createdAt: item.createdAt }
    : item.reviewEventId
      ? { kind: "review_event", id: item.reviewEventId, label: `${item.actorLabel} · ${item.title}`, createdAt: item.createdAt }
      : null;
  const referenced = Boolean(contextReference && reference?.kind === contextReference.kind && reference.id === contextReference.id);
  return (
    <article className={`shared-stream-event kind-${item.kind} ${referenced ? "is-context-referenced" : ""}`}>
      <span className="shared-stream-rail" aria-hidden="true"><i /></span>
      <div className="shared-stream-content">
        <button aria-pressed={contextReference ? referenced : undefined} className="shared-stream-summary" disabled={!contextReference} onClick={() => contextReference && onContextToggle(contextReference)} type="button">
          <span className="dialogue-meta"><strong>{item.actorLabel}</strong><time dateTime={item.createdAt}>{formatCompactTimestamp(item.createdAt)}</time><b>{item.kind === "pending_question" ? "待回复" : item.kind === "focus_event" ? "焦点事件" : item.kind === "confirmed_conclusion" ? "明确结论" : "材料引用"}</b></span>
          <span className="dialogue-title">{item.title}</span>
          <span className="dialogue-copy">{item.summary}</span>
          <small className="shared-stream-source">来源：{item.sourceLabel}</small>
        </button>
        {item.evidenceTargets.length ? <span className="dialogue-references"><span className="dialogue-reference-list"><Icon name="material" /><span>可回溯引用：</span>{item.evidenceTargets.map((target, index) => <button aria-label={`打开协作流引用 ${index + 1}：${evidenceLabels.get(target.evidenceRef) ?? "待定位材料"}`} aria-pressed={sameReviewEvidenceTarget(target, selectedTarget)} className={sameReviewEvidenceTarget(target, selectedTarget) ? "is-selected" : ""} key={`${item.id}-${target.evidenceRef}-${index}`} onClick={() => onEvidenceActivate(target)} type="button">{evidenceLabels.get(target.evidenceRef) ?? target.evidenceRef}</button>)}</span></span> : null}
      </div>
    </article>
  );
}

function PolicyColumn({ dimensions, events, agentMessages, focusEvents, evidenceLabels, mode, rules, selectedTarget, reference, collapsed, onContextToggle, onEvidenceActivate, onToggle }: { dimensions: DimensionDefinition[]; events: MappedCommonReviewEvent[]; agentMessages: AgentMessage[]; focusEvents: AgentFocusEvent[]; evidenceLabels: Map<string, string>; mode: ChainMode; rules: HardConstraintResult[]; selectedTarget: ReviewEvidenceTarget | null; reference: CollaborationContextReference | null; collapsed: boolean; onContextToggle: (reference: CollaborationContextReference) => void; onEvidenceActivate: (target: ReviewEvidenceTarget) => void; onToggle: () => void }) {
  const stream = buildCollaborationStream(events, agentMessages, focusEvents);
  const stateContent = mode === "loading"
    ? <EmptyState detail="正在读取可追溯协作流。" title="加载中" />
    : mode === "empty"
      ? <EmptyState detail="当前没有满足来源、引用或显式同步条件的共享项。" title="协作流为空" />
      : mode === "error"
        ? <EmptyState detail="协作流读取失败，可切回正常状态。" title="链路错误" />
        : null;
  return (
    <section className={`shared-column ${collapsed ? "is-collapsed" : ""}`} id="policy-review-column">
      <header><div><Icon name="rule" /><span><strong>{collapsed ? "协作流" : "制度认知 / 协作事实流"}</strong>{!collapsed ? <small>advisory-only 沉淀 · 不写正式事实、制度或审批</small> : null}</span></div>{!collapsed ? <b>协作流 {stream.length}</b> : null}<Button aria-controls="policy-review-column" aria-expanded={!collapsed} aria-label={collapsed ? "从中间展开协作事实流" : "向中间折叠协作事实流"} className={`policy-collapse-trigger direction-${collapsed ? "down" : "up"}`} onClick={onToggle} title={collapsed ? "从中间展开协作事实流" : "向中间折叠协作事实流"}><Icon name="chevron" /></Button></header>
      {!collapsed ? <CoordinationContextBand dimensions={dimensions} items={stream} /> : null}
      {!collapsed ? stateContent ?? (
        <div className="policy-and-chain">
          <div className="policy-boundary-summary"><Icon name="rule" /><span><strong>正式制度 Gate 仍走既有审批链</strong><small>{rules.length} 条当前制度结果不在此处改写；中栏只展示协作情境。</small></span></div>
          <div className="shared-chain-heading"><strong>协作事实流</strong><span>createdAt + sequence 从早到晚；左右普通草稿不自动进入</span></div>
          <div className="review-timeline shared-fact-stream" aria-label="可追溯协作事实流">
            {stream.length ? stream.map((item) => <SharedStreamEvent evidenceLabels={evidenceLabels} item={item} key={item.id} onContextToggle={onContextToggle} onEvidenceActivate={onEvidenceActivate} reference={reference} selectedTarget={selectedTarget} />) : <EmptyState detail="引用材料、明确问题、显式协调结论或焦点事件出现后才会沉淀。" title="暂无共享项" />}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function LegacyCollaborationDock({
  dimensions,
  events,
  agentThread,
  agentMessages,
  agentFocusEvents,
  agentError,
  evidence,
  facts,
  rules,
  correctionPending,
  correctionMessage,
  approval,
  collapsed,
  businessCollapsed,
  policyCollapsed,
  riskCollapsed,
  onToggleCollapsed,
  onToggleBusiness,
  onTogglePolicy,
  onToggleRisk,
  onAgentEvidenceActivate,
  onSubmitBusiness,
  onSubmitLeadership,
  onSubmitRisk,
  onCorrection,
  onImportMaterialPackage,
  onConfirmMaterialImport,
  selectedTarget,
  showSimulationControls,
  layoutResetVersion,
}: {
  dimensions: DimensionDefinition[];
  events: MappedCommonReviewEvent[];
  agentThread: AgentThread | null;
  agentMessages: AgentMessage[];
  agentFocusEvents: AgentFocusEvent[];
  agentError: string | null;
  evidence: EvidenceReference[];
  facts: FactVersion[];
  rules: HardConstraintResult[];
  correctionPending: boolean;
  correctionMessage: string | null;
  approval: ApprovalState | null;
  collapsed: boolean;
  businessCollapsed: boolean;
  policyCollapsed: boolean;
  riskCollapsed: boolean;
  onToggleCollapsed: () => void;
  onToggleBusiness: () => void;
  onTogglePolicy: () => void;
  onToggleRisk: () => void;
  selectedTarget: ReviewEvidenceTarget | null;
  showSimulationControls: boolean;
  layoutResetVersion: number;
  onAgentEvidenceActivate: (target: ReviewEvidenceTarget) => void;
  onSubmitBusiness: (message: string, reference: CollaborationContextReference | null) => Promise<void>;
  onSubmitLeadership: (message: string, reference: CollaborationContextReference | null) => Promise<void>;
  onSubmitRisk: (message: string, reference: CollaborationContextReference | null) => Promise<void>;
  onCorrection: (factId: string, value: string, reason: string) => Promise<void>;
  onImportMaterialPackage: (file: File) => Promise<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight }>;
  onConfirmMaterialImport: (preflight: MaterialImportPreflight) => Promise<MaterialImportResult>;
}) {
  const [chainMode, setChainMode] = useState<ChainMode>("ready");
  const [reference, setReference] = useState<CollaborationContextReference | null>(null);
  const [a2aShare, setA2aShare] = useState(A2A_DEFAULT_SHARE);
  const [a2aEdge, setA2aEdge] = useState<A2AEdge>(null);
  useEffect(() => { setA2aShare(A2A_DEFAULT_SHARE); setA2aEdge(null); }, [layoutResetVersion]);
  const evidenceLabels = useMemo(() => new Map(evidence.map((item) => [item.id, item.label])), [evidence]);
  const toggleReference = (next: CollaborationContextReference) => setReference((current) => current?.kind === next.kind && current.id === next.id ? null : next);
  const focusLabel = agentThread?.focusRole === "risk" ? "风控" : agentThread?.focusRole === "leadership" ? "领导" : "业务";
  const beginA2AResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const divider = event.currentTarget;
    const columns = divider.parentElement;
    if (!(columns instanceof HTMLElement)) return;
    const pointerId = event.pointerId;
    divider.setPointerCapture(pointerId);
    let nextShare = a2aShare;
    let nextEdge = a2aEdge;
    const apply = () => {
      columns.style.setProperty("--a2a-business-share", `${nextShare}%`);
      columns.dataset.a2aEdge = nextEdge ?? "none";
      divider.setAttribute("aria-valuenow", nextEdge === "coordination" ? "0" : nextEdge === "business" ? "100" : String(Math.round(nextShare)));
    };
    const move = (pointerEvent: PointerEvent) => {
      if (pointerEvent.pointerId !== pointerId) return;
      const rect = columns.getBoundingClientRect();
      if (pointerEvent.clientX <= rect.left + A2A_SNAP_THRESHOLD) {
        nextEdge = "coordination";
      } else if (pointerEvent.clientX >= rect.right - A2A_SNAP_THRESHOLD) {
        nextEdge = "business";
      } else {
        nextEdge = null;
        nextShare = Math.min(A2A_MAX_SHARE, Math.max(A2A_MIN_SHARE, ((pointerEvent.clientX - rect.left) / rect.width) * 100));
      }
      apply();
    };
    function cleanup() {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
      if (divider.hasPointerCapture(pointerId)) divider.releasePointerCapture(pointerId);
    }
    function stop(stopEvent?: Event) {
      if (stopEvent instanceof PointerEvent && stopEvent.pointerId !== pointerId) return;
      apply();
      setA2aShare(nextShare);
      setA2aEdge(nextEdge);
      cleanup();
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
  };
  const resizeA2AWithKeyboard = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") { setA2aEdge("coordination"); return; }
    if (event.key === "End") { setA2aEdge("business"); return; }
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const step = event.shiftKey ? 5 : 2;
    setA2aEdge(null);
    setA2aShare(Math.min(A2A_MAX_SHARE, Math.max(A2A_MIN_SHARE, (a2aEdge ? A2A_DEFAULT_SHARE : a2aShare) + direction * step)));
  };
  const a2aAriaValue = a2aEdge === "coordination" ? 0 : a2aEdge === "business" ? 100 : Math.round(a2aShare);
  const a2aResizable = !businessCollapsed && !policyCollapsed && !riskCollapsed;
  return (
    <section className={`collaboration-dock ${collapsed ? "is-collapsed" : ""}`} aria-label="审批协同工作区" id="collaboration-pane">
      <button aria-controls="collaboration-pane" aria-expanded={!collapsed} aria-label={collapsed ? "从右下角展开审批协同" : "收起审批协同至右下角"} className="legacy-collaboration-corner-anchor" onClick={onToggleCollapsed} title={collapsed ? "从右下角展开审批协同" : "收起审批协同至右下角"} type="button"><span aria-hidden="true" className="pane-corner-glyph">{collapsed ? "↖" : "↘"}</span></button>
      {!collapsed ? <header className="collaboration-heading"><div className="collaboration-heading-copy"><h2>审批协同</h2><span>业务自由讨论 · 协作事实流 · 风控自由讨论</span><strong className={`approval-status status-${approval?.status ?? "draft"}`} role="status">{approval ? `${approvalLabels[approval.status]} · 正式链 v${approval.version}` : "读取审批状态…"} · Agent 焦点 {focusLabel}</strong></div><div className="collaboration-heading-actions">{agentError ? <small className="agent-session-error" role="alert">{agentError}</small> : null}{showSimulationControls ? <label>协作流<select aria-label="切换协作流演示状态" onChange={(event) => setChainMode(event.target.value as ChainMode)} value={chainMode}><option value="ready">正常</option><option value="loading">加载</option><option value="empty">空</option><option value="error">错误</option></select></label> : null}</div></header> : null}
      {!collapsed ? (
        <div className="collaboration-content" id="collaboration-content">
          <div className={`collaboration-columns ${businessCollapsed ? "is-business-collapsed" : ""} ${policyCollapsed ? "is-policy-collapsed" : ""} ${riskCollapsed ? "is-risk-collapsed" : ""}`} data-a2a-edge={a2aResizable ? a2aEdge ?? "none" : "disabled"} style={{ "--a2a-business-share": `${a2aShare}%` } as CSSProperties}>
            <RoleColumn actor="business" collapsed={businessCollapsed} correctionMessage={correctionMessage} correctionPending={correctionPending} evidenceLabels={evidenceLabels} facts={facts} messages={agentMessages} onAgentEvidenceActivate={onAgentEvidenceActivate} onClearContext={() => setReference(null)} onConfirmMaterialImport={onConfirmMaterialImport} onContextToggle={toggleReference} onCorrection={onCorrection} onImportMaterialPackage={onImportMaterialPackage} onSubmit={onSubmitBusiness} onToggle={onToggleBusiness} reference={reference} selectedTarget={selectedTarget} showSimulationControls={showSimulationControls} />
            {a2aResizable ? <div aria-label="调整业务与制度风控协同区域宽度" aria-orientation="vertical" aria-valuemax={100} aria-valuemin={0} aria-valuenow={a2aAriaValue} aria-valuetext={a2aEdge === "coordination" ? "制度与风控协同区域占满" : a2aEdge === "business" ? "业务 Agent 区域占满" : `业务 Agent 宽度 ${Math.round(a2aShare)}%`} className="layout-divider divider-a2a" onKeyDown={resizeA2AWithKeyboard} onPointerDown={beginA2AResize} role="separator" tabIndex={0} /> : null}
            <PolicyColumn agentMessages={agentMessages} collapsed={policyCollapsed} dimensions={dimensions} events={events} evidenceLabels={evidenceLabels} focusEvents={agentFocusEvents} mode={showSimulationControls ? chainMode : "ready"} onContextToggle={toggleReference} onEvidenceActivate={onAgentEvidenceActivate} onToggle={onTogglePolicy} reference={reference} rules={rules} selectedTarget={selectedTarget} />
            <RoleColumn actor="risk" collapsed={riskCollapsed} correctionMessage={null} correctionPending={false} evidenceLabels={evidenceLabels} facts={[]} messages={agentMessages} onAgentEvidenceActivate={onAgentEvidenceActivate} onClearContext={() => setReference(null)} onConfirmMaterialImport={onConfirmMaterialImport} onContextToggle={toggleReference} onCorrection={onCorrection} onImportMaterialPackage={onImportMaterialPackage} onSubmit={onSubmitRisk} onToggle={onToggleRisk} reference={reference} selectedTarget={selectedTarget} showSimulationControls={showSimulationControls} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function CollaborationDock(props: Parameters<typeof LegacyCollaborationDock>[0]) {
  const locale = usePublicLocale();
  const {
    agentError,
    agentFocusEvents,
    agentMessages,
    collapsed,
    dimensions,
    events,
    evidence,
    facts,
    correctionPending,
    correctionMessage,
    onAgentEvidenceActivate,
    onConfirmMaterialImport,
    onImportMaterialPackage,
    onCorrection,
    onSubmitBusiness,
    onSubmitLeadership,
    onSubmitRisk,
    onToggleCollapsed,
    rules,
    selectedTarget,
  } = props;
  return (
    <section className={`collaboration-dock a2a-collaboration-dock ${collapsed ? "is-collapsed" : ""}`} aria-label={copy(locale, "Approval collaboration workspace", "审批协同工作区")} data-semantic-localized="true" id="collaboration-pane">
      <button aria-controls="collaboration-pane" aria-expanded={!collapsed} aria-label={collapsed ? copy(locale, "Expand approval collaboration from the lower-right corner", "从右下角展开审批协同") : copy(locale, "Collapse approval collaboration to the lower-right corner", "收起审批协同至右下角")} className="pane-corner-anchor collaboration-corner-anchor" onClick={onToggleCollapsed} title={collapsed ? copy(locale, "Expand approval collaboration", "展开审批协同") : copy(locale, "Collapse approval collaboration", "收起审批协同")} type="button"><span aria-hidden="true" className="pane-corner-glyph">{collapsed ? "↖" : "↘"}</span></button>
      {!collapsed ? <A2ACollaborationPanel agentError={agentError} agentFocusEvents={agentFocusEvents} agentMessages={agentMessages} correctionMessage={correctionMessage} correctionPending={correctionPending} dimensions={dimensions} events={events} evidence={evidence} facts={facts} onAgentEvidenceActivate={onAgentEvidenceActivate} onConfirmMaterialImport={onConfirmMaterialImport} onCorrection={onCorrection} onImportMaterialPackage={onImportMaterialPackage} onSubmitBusiness={onSubmitBusiness} onSubmitLeadership={onSubmitLeadership} onSubmitRisk={onSubmitRisk} rules={rules} selectedTarget={selectedTarget} /> : null}
    </section>
  );
}
