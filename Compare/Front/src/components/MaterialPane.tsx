import { useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type { AccountRole } from "../contracts/authentication";
import type { AgentActivityState, AgentMessage, AgentResponsePreferences, ChatAgentRole, CollaborationContextReference } from "../contracts/agentCommunication";
import { DIMENSION_IDS, MATERIAL_BUSINESS_FOLDERS } from "../contracts/workbench";
import type { DimensionId, DocumentMaterial, EvidenceReference, ExcelMaterial, FactVersion, ImageMaterial, Material, MaterialBusinessFolder, MediaMaterial, PdfMaterial, ReviewEvidenceSelectionGroup, ReviewEvidenceTarget } from "../contracts/workbench";
import { evidenceRefForSourceAnchor, type ExtractedFieldCandidate, type MaterialImportPreflight, type MaterialImportResult, type MaterialUploadReceipt, type SourceAnchor, type StoredMaterialIntelligence, type StoredSceneSpec } from "../contracts/materialIntelligence";
import type { ModelGatewayRuntimeState } from "../contracts/modelGateway";
import { useLockedWheel } from "../lib/useLockedWheel";
import { materialDimensionIndex } from "../lib/materialIndex";
import { businessFolderFor, isOriginalMaterial, materialPreviewUrl, materialRelativePath } from "../lib/materialBusinessFolders";
import type { OriginalMaterial } from "../lib/materialBusinessFolders";
import type { EvidenceSelectionResolution } from "../lib/workbenchLogic";
import { clamp, excelRangeContains, excelRangeScrollTarget, LAYOUT_LIMITS, materialHitCounts, materialTabPresentation } from "../lib/workbenchLogic";
import { Icon } from "./icons";
import { Button, EmptyState } from "./ui";
import { MaterialSceneSpecPreview } from "./MaterialSceneSpecPreview";
import { A2ACollaborationPanel } from "./A2ACollaborationPanel";
import { copy, formatCanonicalLabel, formatCanonicalNarrative, formatCanonicalText, formatDataStatus, formatServiceMessage, formatUnit, IMAGE_TO_3D_BOUNDARY, usePublicLocale, type PublicLocale } from "../lib/publicLocale";

type LocatedSelectionItem = Extract<EvidenceSelectionResolution, { status: "located" }>["items"][number];
type MaterialKindFilter = "all" | OriginalMaterial["kind"];
type MaterialDimensionFilter = "all" | "unassigned" | DimensionId;

export interface MaterialPaneGroupChat {
  accountRole: AccountRole;
  agentMessages: AgentMessage[];
  agentActivity: AgentActivityState | null;
  agentError: string | null;
  selectedTarget: ReviewEvidenceTarget | null;
  onSubmitMessage: (message: string, targetAgentRole: ChatAgentRole | null, reference: CollaborationContextReference | null, preferences: AgentResponsePreferences) => Promise<void>;
  onImportMaterialPackage: (file: File) => Promise<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight }>;
  onConfirmMaterialImport: (preflight: MaterialImportPreflight) => Promise<MaterialImportResult>;
}

const DIMENSION_LABELS: Record<DimensionId, string> = {
  compliance: "合规",
  transaction: "交易",
  production: "生产",
  revenue: "营收",
  debt: "负债",
  cashflow: "流水",
};

const MATERIAL_KIND_LABELS: Record<OriginalMaterial["kind"], string> = {
  excel: "表格",
  pdf: "PDF",
  document: "Word",
  image: "图片",
  media: "影像",
};

const EXCEL_RENDER_WINDOW = 200;
const PROJECT_PHOTO_VISIBLE_RATIO = 0.885;

function cleanVisualFileName(fileName: string) {
  const withoutExtension = fileName.replace(/\.[^.]+$/u, "");
  return withoutExtension
    .replace(/\s*[（(][^）)]*(?:本地合成|适配|模拟|脱敏|派生)[^）)]*[）)]/gu, "")
    .replace(/[_-]+/gu, " ")
    .replace(/\s+/gu, " ")
    .trim() || "原始图片";
}

function isProjectPhoto(material: ImageMaterial) {
  const descriptor = `${material.businessPath ?? ""} ${material.folderPath ?? ""} ${material.fileName}`;
  const excluded = /证照|执照|身份证|授权|产权|房产|征信|business[ _-]?license|identity|authorization|property/iu;
  const photo = /现场照片|租赁标的|现场|厂区|厂房|设备|铭牌|工艺|原材料|成品|site|factory|equipment|nameplate|process|raw[ _-]?material|finished[ _-]?product/iu;
  return photo.test(descriptor) && !excluded.test(descriptor);
}

function useManagedVideo(videoUrl: string | undefined) {
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => () => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.removeAttribute("src");
    video.load();
  }, [videoUrl]);
  return videoRef;
}

function materialIcon(material: Material) {
  if (material.kind === "excel") return "material" as const;
  if (material.kind === "pdf") return "pdf" as const;
  if (material.kind === "document") return "material" as const;
  return "image" as const;
}

function materialVersionLabel(versionId: string, locale: PublicLocale) {
  return /-v(\d+)$/i.exec(versionId)?.[1] ?? copy(locale, "Current", "当前");
}

function archivedOriginalUnavailable(material: Material, locale: PublicLocale) {
  switch (material.originalAccess?.status) {
    case "not_configured":
      return { title: copy(locale, "External original not configured", "外置原件未配置"), detail: copy(locale, "No controlled external-material root is configured for this runtime; the preview will not fall back to a repository copy.", "当前运行时未配置受控外置材料根目录；不会回退到仓库内预览。") };
    case "invalid_root":
      return { title: copy(locale, "External original unavailable", "外置原件不可用"), detail: copy(locale, "The controlled external-material root is invalid or unreadable; no substitute preview will be shown.", "受控外置材料根目录无效或无法读取；不会显示替代预览。") };
    case "not_imported":
      return { title: copy(locale, "Original not imported", "原件尚未导入"), detail: copy(locale, "This project version has not been imported into the controlled external-material root.", "该项目版本尚未导入受控外置材料根目录。") };
    case "integrity_mismatch":
      return { title: copy(locale, "Original failed integrity check", "原件校验未通过"), detail: copy(locale, "The external file SHA-256 does not match the current material version; preview has been stopped.", "外置文件与当前材料版本 SHA-256 不一致，已停止预览。") };
    default:
      return null;
  }
}

function anchorLabel(anchor: SourceAnchor, locale: PublicLocale) {
  if (anchor.kind === "excel") return `${anchor.sheet}!${anchor.range}`;
  if (anchor.kind === "pdf") return copy(locale, `Page ${anchor.page} · ${(anchor.bbox.x * 100).toFixed(0)}%, ${(anchor.bbox.y * 100).toFixed(0)}%`, `第 ${anchor.page} 页 · ${(anchor.bbox.x * 100).toFixed(0)}%, ${(anchor.bbox.y * 100).toFixed(0)}%`);
  if (anchor.kind === "image") return copy(locale, `Image region · ${(anchor.bbox.x * 100).toFixed(0)}%, ${(anchor.bbox.y * 100).toFixed(0)}%`, `图片区域 · ${(anchor.bbox.x * 100).toFixed(0)}%, ${(anchor.bbox.y * 100).toFixed(0)}%`);
  if (anchor.kind === "media") return `${anchor.startSeconds.toFixed(1)}s–${anchor.endSeconds.toFixed(1)}s`;
  return copy(locale, `Page ${anchor.renderedPage} · ${anchor.paragraphId}/${anchor.runId}`, `第 ${anchor.renderedPage} 页 · ${anchor.paragraphId}/${anchor.runId}`);
}

const MODEL_GATEWAY_STATUS_LABEL: Record<ModelGatewayRuntimeState["status"], string> = {
  idle: "未运行",
  accepted: "已受理",
  running: "运行中",
  succeeded: "已完成",
  needs_review: "待人工复核",
  failed: "失败",
  cancelled: "已取消",
  unavailable: "不可用",
};

function ModelGatewayStatus({ runtime, onCancel, onRetry }: { runtime: ModelGatewayRuntimeState; onCancel: () => void; onRetry: () => void }) {
  const locale = usePublicLocale();
  return <section aria-label={copy(locale, "Model Gateway runtime status", "Model Gateway 运行状态")} className={`model-gateway-status status-${runtime.status}`} data-semantic-localized>
    <header><strong>Model Gateway</strong><span>{copy(locale, formatDataStatus(runtime.status, locale), MODEL_GATEWAY_STATUS_LABEL[runtime.status])}</span></header>
    <dl>
      <div><dt>provider</dt><dd>{runtime.provider ?? copy(locale, "Not returned", "未返回")}</dd></div>
      <div><dt>status</dt><dd>{runtime.status}</dd></div>
      <div><dt>latency</dt><dd>{runtime.latencyMs === null ? copy(locale, "Not returned", "未返回") : copy(locale, `${runtime.latencyMs} ms (client measured)`, `${runtime.latencyMs} ms（客户端）`)}</dd></div>
      <div><dt>inputHash</dt><dd title={runtime.inputHash ?? undefined}>{runtime.inputHash ?? copy(locale, "Not returned", "未返回")}</dd></div>
      <div><dt>error</dt><dd>{runtime.error ? formatServiceMessage(runtime.error, locale) : copy(locale, "None", "无")}</dd></div>
      <div><dt>retryable</dt><dd>{String(runtime.retryable)}</dd></div>
    </dl>
    <p>{copy(locale, "advisoryOnly: true. Model output creates candidates only; a human confirmation Gate is required before any candidate can enter the authoritative facts.", "advisoryOnly: true；模型输出只形成 candidate，必须经过人工确认 Gate 才能进入权威事实。")}</p>
    {runtime.status === "running" ? <Button onClick={onCancel}>{copy(locale, "Cancel this run", "取消本次运行")}</Button> : null}
    {runtime.status === "failed" && runtime.retryable ? <Button onClick={onRetry}>{copy(locale, "Retry Model Gateway", "重试 Model Gateway")}</Button> : null}
  </section>;
}

function MaterialIntelligencePanel({ intelligence, scene, status, message, runtime, confirmingCandidateId, confirmedCandidateIds, activeAnchorId, canEdit, onRun, onCancel, onConfirm, onAnchorActivate }: {
  intelligence: StoredMaterialIntelligence | null;
  scene: StoredSceneSpec | null;
  status: "idle" | "loading" | "ready" | "empty" | "error";
  message: string | null;
  runtime: ModelGatewayRuntimeState;
  confirmingCandidateId: string | null;
  confirmedCandidateIds: Set<string>;
  activeAnchorId: string | null;
  canEdit: boolean;
  onRun: () => void;
  onCancel: () => void;
  onConfirm: (candidate: ExtractedFieldCandidate, reason: string) => void;
  onAnchorActivate: (sourceAnchorId: string) => void;
}) {
  const locale = usePublicLocale();
  const [reason, setReason] = useState("");
  if (status === "loading") return <section className="material-intelligence-panel" aria-busy="true" data-semantic-localized><header><strong>{copy(locale, "Material intelligence assistance", "材料智能辅助")}</strong><span>{copy(locale, "Reading the server result…", "正在读取服务端结果…")}</span></header><ModelGatewayStatus onCancel={onCancel} onRetry={onRun} runtime={runtime} /></section>;
  if (!intelligence) return <section className={`material-intelligence-panel status-${status}`} data-semantic-localized><header><div><strong>{copy(locale, "Material intelligence assistance", "材料智能辅助")}</strong><span>{copy(locale, "Candidates never write authoritative facts automatically", "候选不会自动写入权威事实")}</span></div>{canEdit ? <Button onClick={onRun}>{copy(locale, "Run recognition manually", "人工触发识别")}</Button> : <span className="role-readonly-status">{copy(locale, "Business-only action · read-only", "仅业务可操作 · 当前只读")}</span>}</header><p>{message ? formatServiceMessage(message, locale) : copy(locale, "This material has no intelligence result. The configured provider is called only after an explicit human action.", "当前材料尚无 intelligence 结果；只会在明确人工动作后调用已配置 provider。")}</p>{canEdit ? <ModelGatewayStatus onCancel={onCancel} onRetry={onRun} runtime={runtime} /> : null}</section>;
  const { result } = intelligence;
  return <section className="material-intelligence-panel" aria-label={copy(locale, "Material intelligence candidates and provenance", "材料智能候选与来源")} data-semantic-localized>
    <header><div><strong>{copy(locale, "Material intelligence assistance", "材料智能辅助")}</strong><span>{result.modelInfo?.provider ?? copy(locale, "provider unavailable", "provider 不可用")} · {result.modelInfo?.model ?? copy(locale, "No model", "无模型")}</span></div><span className="simulation-pill">{result.isSimulated ? copy(locale, "Synthetic simulation", "合成模拟") : copy(locale, "Controlled material", "受控材料")}</span></header>
    {message ? <p aria-live="polite" className="intelligence-status-message">{formatServiceMessage(message, locale)}</p> : null}
    {canEdit ? <ModelGatewayStatus onCancel={onCancel} onRetry={onRun} runtime={runtime} /> : <p className="role-readonly-status">{copy(locale, "Business-only action · read-only", "仅业务可操作 · 当前只读")}</p>}
    <div className="intelligence-provenance">
      <dl><div><dt>{copy(locale, "Material version", "材料版本")}</dt><dd>{result.materialVersionId}</dd></div><div><dt>SHA-256</dt><dd title={result.contentHash}>{result.contentHash}</dd></div><div><dt>{copy(locale, "Classification", "分类")}</dt><dd>{formatCanonicalLabel(result.dataClassification, locale)}</dd></div><div><dt>{copy(locale, "Confidence", "置信")}</dt><dd>{Math.round(result.confidence * 100)}%</dd></div></dl>
      <p>{copy(locale, `This is a traceable advisory candidate only; isSimulated: ${String(result.isSimulated)}. It is not statistically validated model output.`, `结果仅是可溯源辅助候选；isSimulated: ${String(result.isSimulated)}，不得解释为真实模型统计验证。`)}</p>
    </div>
    <div className="intelligence-grid">
      <section><h3>SourceAnchor</h3>{result.sourceAnchors.map((anchor) => <button aria-pressed={activeAnchorId === anchor.id} className={activeAnchorId === anchor.id ? "is-active" : ""} key={anchor.id} onClick={() => onAnchorActivate(anchor.id)} type="button"><b>{anchor.kind}</b><span>{anchorLabel(anchor, locale)}</span><small>{anchor.id}</small></button>)}</section>
      <section><h3>Observation</h3>{result.observations.length ? result.observations.map((item) => <article key={item.id}><b>{formatCanonicalLabel(item.kind, locale)}</b><p>{formatCanonicalNarrative(item.text, locale)}</p><small>{item.sourceAnchorIds.join(" · ")}</small></article>) : <p className="intelligence-empty">{copy(locale, "No observations.", "没有 Observation。")}</p>}</section>
    </div>
    <section className="candidate-list"><h3>{copy(locale, "Candidates · human confirmation required", "候选 · 必须人工确认")}</h3>{result.extractedFieldCandidates.length ? result.extractedFieldCandidates.map((candidate) => {
      const confirmed = confirmedCandidateIds.has(candidate.id);
      return <article className={confirmed ? "is-confirmed" : ""} key={candidate.id}><header><span><b>{formatCanonicalLabel(candidate.label, locale)}</b><small>{candidate.fieldKey}</small></span><em>{formatDataStatus(candidate.status, locale)}</em></header><p>{candidate.value === null ? copy(locale, "Empty value", "空值") : formatCanonicalNarrative(String(candidate.value), locale)}{candidate.unit ? ` ${formatUnit(candidate.unit, locale)}` : ""}</p><small>{copy(locale, "Anchors", "锚点")}：{candidate.sourceAnchorIds.join(" · ")}</small>{confirmed ? <strong className="candidate-confirmed">{copy(locale, "Human-confirmed; the authoritative workbench has been refreshed", "已由人工确认并刷新权威工作台")}</strong> : canEdit ? <div className="candidate-action"><label><span>{copy(locale, "Human confirmation reason", "人工确认理由")}</span><input aria-label={copy(locale, `Reason for confirming ${formatCanonicalLabel(candidate.label, locale)}`, `确认${candidate.label}的理由`)} onChange={(event) => setReason(event.target.value)} placeholder={copy(locale, "Describe the original material and locator you checked", "说明已核对的原材料与定位")} value={reason} /></label><Button disabled={reason.trim().length < 4 || confirmingCandidateId !== null} onClick={() => onConfirm(candidate, reason.trim())}>{confirmingCandidateId === candidate.id ? copy(locale, "Confirming…", "确认中…") : copy(locale, "Confirm candidate", "人工确认候选")}</Button></div> : <strong className="role-readonly-status">{copy(locale, "Business-only confirmation · read-only", "仅业务可确认 · 当前只读")}</strong>}</article>;
    }) : <p className="intelligence-empty">{copy(locale, "This result contains no field candidates.", "当前结果没有字段候选。")}</p>}</section>
    {scene ? <MaterialSceneSpecPreview activeAnchorId={activeAnchorId} onHotspotActivate={onAnchorActivate} scene={scene} /> : <div className="scene-spec-empty"><strong>{copy(locale, "No SceneSpec", "无 SceneSpec")}</strong><span>{copy(locale, "This material has no controlled spatial preview. No 3D content will be generated or guessed.", "当前材料没有受控空间示意；不会生成或猜测三维内容。")}</span><small>{IMAGE_TO_3D_BOUNDARY[locale]}</small></div>}
  </section>;
}

function SpreadsheetPreview({ material, selectionItems, onEvidenceActivate }: { material: ExcelMaterial; selectionItems: LocatedSelectionItem[]; onEvidenceActivate: (target: ReviewEvidenceTarget) => void }) {
  const locale = usePublicLocale();
  const excelItems = selectionItems.filter((item) => item.evidence.locator?.kind === "excel" && item.evidence.locator.materialId === material.id);
  const hitSheets = [...new Set(excelItems.flatMap((item) => item.evidence.locator?.kind === "excel" ? [item.evidence.locator.sheet] : []))];
  const [selectedSheetName, setSelectedSheetName] = useState(hitSheets[0] ?? material.sheets[0]?.name ?? "");
  useEffect(() => {
    if (hitSheets[0]) setSelectedSheetName(hitSheets[0]);
  }, [hitSheets.join("|")]);
  const sheet = material.sheets.find((item) => item.name === selectedSheetName) ?? material.sheets[0];
  const activeItems = excelItems.filter((item) => item.evidence.locator?.kind === "excel" && item.evidence.locator.sheet === sheet?.name);
  const locator = activeItems[0]?.evidence.locator?.kind === "excel" ? activeItems[0].evidence.locator : null;
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const targetRowRef = useRef<HTMLDivElement>(null);
  const scrollTarget = locator ? excelRangeScrollTarget(locator.range) : null;
  const rowStart = Math.max(0, (scrollTarget?.row ?? 4) - 4 - Math.floor(EXCEL_RENDER_WINDOW / 2));
  const visibleRows = sheet.rows.slice(rowStart, rowStart + EXCEL_RENDER_WINDOW);
  useEffect(() => {
    const container = scrollContainerRef.current;
    const targetRow = targetRowRef.current;
    if (!container || !targetRow || !locator || !scrollTarget) return;
    const frame = window.requestAnimationFrame(() => {
      const highlightedCells = targetRow.querySelectorAll<HTMLElement>(".sheet-evidence-cell");
      const firstCell = highlightedCells.item(0);
      const lastCell = highlightedCells.item(highlightedCells.length - 1);
      const containerBounds = container.getBoundingClientRect();
      const rowBounds = targetRow.getBoundingClientRect();
      const rangeCenter = firstCell && lastCell
        ? (firstCell.getBoundingClientRect().left + lastCell.getBoundingClientRect().right) / 2
          - containerBounds.left
          + container.scrollLeft
        : targetRow.offsetWidth / 2;
      const rowContentTop = rowBounds.top - containerBounds.top + container.scrollTop;
      container.scrollTo({
        left: Math.max(0, rangeCenter - container.clientWidth / 2),
        top: Math.max(0, rowContentTop - (container.clientHeight - rowBounds.height) / 2),
        behavior: "auto",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [locator?.materialId, locator?.materialVersionId, locator?.range, locator?.sheet, scrollTarget?.column, scrollTarget?.row]);
  if (!sheet) return <EmptyState detail={copy(locale, "This file contains no worksheet data.", "该文件没有工作表数据。")} title={copy(locale, "Empty worksheet", "空工作表")} />;
  return (
    <div className="sheet-foundation">
      <div className="sheet-toolbar" aria-label={copy(locale, "Excel toolbar", "Excel 工具栏")}><span>Excel · 100%</span><span>{activeItems.length ? copy(locale, `${activeItems.length} located regions`, `已定位 ${activeItems.length} 个区域`) : copy(locale, "No evidence selected", "未选证据")}</span>{material.originalUrl ? <a className="material-original-file-link" href={material.originalUrl} rel="noreferrer" target="_blank">{copy(locale, "Open original XLSX", "打开 XLSX 原件")}</a> : null}</div>
      {hitSheets.length > 1 ? <div aria-label={copy(locale, "Worksheets with evidence hits", "命中工作表")} className="sheet-hit-tabs">{hitSheets.map((name) => <button aria-pressed={name === sheet?.name} key={name} onClick={() => setSelectedSheetName(name)} type="button">{formatCanonicalText(name, locale)}<b>{excelItems.filter((item) => item.evidence.locator?.kind === "excel" && item.evidence.locator.sheet === name).length}</b></button>)}</div> : null}
      <div className="sheet-scroll" ref={scrollContainerRef}>
        <div className="sheet-grid" role="table" aria-label={copy(locale, `${formatCanonicalText(material.label, locale)} table`, `${material.label}表格`)}>
          <div className="sheet-title" role="row">{formatCanonicalText(material.label, locale)}</div>
          <div className="sheet-date" role="row">{copy(locale, "De-identified simulated material · material index version", "脱敏模拟材料 · 材料索引版本")} {materialVersionLabel(material.versionId, locale)}</div>
          <div className="sheet-row sheet-head" role="row">{sheet.columns.map((column) => <strong key={column} role="columnheader">{formatCanonicalText(column, locale)}</strong>)}</div>
          {visibleRows.map((row, visibleRowIndex) => {
            const rowIndex = rowStart + visibleRowIndex;
            return <div className="sheet-row" data-sheet-row={rowIndex + 4} key={`${sheet.name}-${rowIndex}`} ref={scrollTarget?.row === rowIndex + 4 ? targetRowRef : undefined} role="row">
              {row.map((cell, cellIndex) => {
                const matchedItem = activeItems.find((item) => item.evidence.locator?.kind === "excel" && excelRangeContains(item.evidence.locator.range, cellIndex + 1, rowIndex + 4));
                return matchedItem ? (
                  <button aria-label={copy(locale, `Locate ${formatCanonicalText(matchedItem.evidence.label, locale)} in the review`, `反向定位${matchedItem.evidence.label}`)} className="sheet-evidence-cell evidence-highlight" data-evidence-id={matchedItem.evidence.id} key={`${rowIndex}-${cellIndex}`} onClick={() => onEvidenceActivate(matchedItem.target)} role="cell" type="button">{cell === null ? "" : formatCanonicalText(String(cell), locale)}</button>
                ) : <span key={`${rowIndex}-${cellIndex}`} role="cell">{cell === null ? "" : formatCanonicalText(String(cell), locale)}</span>;
              })}
            </div>;
          })}
          {Array.from({ length: 8 }, (_, index) => <div aria-hidden="true" className="sheet-empty-row" key={index} />)}
        </div>
      </div>
      <div className="sheet-tabs"><strong>{formatCanonicalText(sheet.name, locale)}</strong><span>{activeItems.length ? copy(locale, `${activeItems.length} persistently highlighted regions`, `${activeItems.length} 个持续高亮区域`) : copy(locale, "Worksheet", "工作表")}</span></div>
    </div>
  );
}

function LocatorBox({ item, onEvidenceActivate, visibleHeightRatio = 1 }: { item: LocatedSelectionItem; onEvidenceActivate: (target: ReviewEvidenceTarget) => void; visibleHeightRatio?: number }) {
  const locale = usePublicLocale();
  const { evidence, target } = item;
  const locator = evidence.locator;
  if (!locator || (locator.kind !== "pdf" && locator.kind !== "image")) return null;
  const visibleTop = Math.max(0, locator.bbox.y);
  const visibleBottom = Math.min(visibleHeightRatio, locator.bbox.y + locator.bbox.height);
  if (visibleBottom <= visibleTop || visibleTop >= visibleHeightRatio) return null;
  return (
    <button
      aria-label={copy(locale, `Locate ${formatCanonicalText(evidence.label, locale)} in the review`, `反向定位${evidence.label}`)}
      className="locator-box evidence-highlight"
      data-evidence-id={evidence.id}
      data-image-interactive="true"
      onClick={() => onEvidenceActivate(target)}
      style={{ left: `${locator.bbox.x * 100}%`, top: `${visibleTop / visibleHeightRatio * 100}%`, width: `${locator.bbox.width * 100}%`, height: `${(visibleBottom - visibleTop) / visibleHeightRatio * 100}%` } as CSSProperties}
      title={copy(locale, "Selected evidence uses a neutral outline", "证据选中使用中性描边")}
      type="button"
    ><span>{formatCanonicalText(evidence.label, locale)}</span></button>
  );
}

type VisualAnnotationDraft = {
  bbox: { x: number; y: number; width: number; height: number };
  snapshotDataUrl: string | null;
  sourceAnchor: Extract<SourceAnchor, { kind: "image" }> | null;
};

function bboxOverlapScore(left: { x: number; y: number; width: number; height: number }, right: { x: number; y: number; width: number; height: number }) {
  const width = Math.max(0, Math.min(left.x + left.width, right.x + right.width) - Math.max(left.x, right.x));
  const height = Math.max(0, Math.min(left.y + left.height, right.y + right.height) - Math.max(left.y, right.y));
  const intersection = width * height;
  return intersection / Math.max(0.000001, Math.min(left.width * left.height, right.width * right.height));
}

function PdfPreview({ material, selectionItems, onEvidenceActivate }: { material: PdfMaterial; selectionItems: LocatedSelectionItem[]; onEvidenceActivate: (target: ReviewEvidenceTarget) => void }) {
  const locale = usePublicLocale();
  const pdfItems = selectionItems.filter((item) => item.evidence.locator?.kind === "pdf" && item.evidence.locator.materialId === material.id);
  const hitPages = [...new Set(pdfItems.flatMap((item) => item.evidence.locator?.kind === "pdf" ? [item.evidence.locator.page] : []))];
  const [activePageNumber, setActivePageNumber] = useState(hitPages[0] ?? material.pages[0]?.page ?? 1);
  useEffect(() => setActivePageNumber(hitPages[0] ?? material.pages[0]?.page ?? 1), [material.id, hitPages.join("|")]);
  const activePage = material.pages.find((page) => page.page === activePageNumber) ?? material.pages[0];
  if (!activePage) return <EmptyState detail={copy(locale, "This PDF has no displayable pages.", "该 PDF 没有可展示页面。")} title={copy(locale, "Empty PDF", "PDF 为空")} />;
  return (
    <div className="document-preview">
      <div className="document-toolbar"><span>PDF</span><strong>{pdfItems.length ? copy(locale, `${hitPages.length} pages · ${pdfItems.length} regions`, `${hitPages.length} 页 · ${pdfItems.length} 个区域`) : copy(locale, `${material.pageCount} pages`, `${material.pageCount} 页`)}</strong>{material.originalUrl ? <a className="material-original-file-link" href={material.originalUrl} rel="noreferrer" target="_blank">{copy(locale, "Open original PDF", "打开 PDF 原件")}</a> : null}</div>
      <nav aria-label={copy(locale, "PDF pages", "PDF 页面")} className="pdf-page-tabs">{material.pages.map((page) => <button aria-current={page.page === activePage.page ? "page" : undefined} className={page.page === activePage.page ? "is-active" : ""} key={page.page} onClick={() => setActivePageNumber(page.page)} type="button">{page.page}{hitPages.includes(page.page) ? <b>{copy(locale, "Located", "定位")}</b> : null}</button>)}</nav>
      <div className="document-scroll pdf-hit-pages"><article className="pdf-page" data-pdf-page={activePage.page}><header><small>{copy(locale, "Quoted source document", "企业征信报告")}</small><h3>{formatCanonicalText(activePage.title, locale)}</h3></header>{activePage.lines.map((line, index) => <p key={`${activePage.page}-${index}`}>{formatCanonicalText(line, locale)}</p>)}<div className="pdf-filler" />{pdfItems.filter((item) => item.evidence.locator?.kind === "pdf" && item.evidence.locator.page === activePage.page).map((item) => <LocatorBox item={item} key={item.evidence.id} onEvidenceActivate={onEvidenceActivate} />)}</article></div>
    </div>
  );
}

function DocumentPreview({ material }: { material: DocumentMaterial }) {
  const locale = usePublicLocale();
  return <div className="document-preview word-document">
    <div className="document-toolbar"><span>Word · DOCX</span><strong>{copy(locale, "Controlled original", "受控原件")}</strong></div>
    <div className="image-source-empty" role="status"><Icon name="material" /><strong>{formatCanonicalText(material.label, locale)}</strong><span>{material.description ? formatCanonicalText(material.description, locale) : copy(locale, "Online Office parsing is not provided. The original remains in the project-isolated backend file state.", "当前不建设 Office 在线解析；原件保留在项目隔离的后端文件状态中。")}</span>{material.originalUrl ? <a className="material-original-file-link" href={material.originalUrl} rel="noreferrer" target="_blank">{copy(locale, "Open original Word document", "打开 Word 原件")}</a> : <small>{copy(locale, "Word original pending", "Word 原件待接入")}</small>}</div>
  </div>;
}

function ImagePreview({ material, selectionItems, intelligence, annotationRequestKey, onAnnotationModeChange, onEvidenceActivate, onVisualAnnotation }: { material: ImageMaterial; selectionItems: LocatedSelectionItem[]; intelligence: StoredMaterialIntelligence | null; annotationRequestKey: number; onAnnotationModeChange: (active: boolean) => void; onEvidenceActivate: (target: ReviewEvidenceTarget) => void; onVisualAnnotation: (draft: VisualAnnotationDraft) => void }) {
  const locale = usePublicLocale();
  const imageItems = selectionItems.filter((item) => item.evidence.locator?.kind === "image" && item.evidence.locator.materialId === material.id);
  const viewportRef = useRef<HTMLDivElement>(null);
  const layerRef = useRef<HTMLElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const panRef = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const annotationDragRef = useRef<{ pointerId: number; startX: number; startY: number; imageRect: DOMRect; viewportRect: DOMRect; bbox: VisualAnnotationDraft["bbox"] } | null>(null);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [annotationMode, setAnnotationMode] = useState(false);
  const [annotationPixels, setAnnotationPixels] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const sourceUrl = materialPreviewUrl(material);
  const projectPhoto = isProjectPhoto(material);
  const visibleHeightRatio = projectPhoto ? PROJECT_PHOTO_VISIBLE_RATIO : 1;
  const [imageLoadState, setImageLoadState] = useState<"loading" | "ready" | "error">(sourceUrl ? "loading" : "error");
  const imageName = cleanVisualFileName(material.fileName);
  useEffect(() => {
    setView({ scale: 1, x: 0, y: 0 });
    setImageLoadState(sourceUrl ? "loading" : "error");
    const frame = window.requestAnimationFrame(() => {
      const image = imageRef.current;
      if (image?.complete) setImageLoadState(image.naturalWidth > 0 ? "ready" : "error");
    });
    return () => window.cancelAnimationFrame(frame);
  }, [material.id, sourceUrl]);
  useEffect(() => {
    if (!annotationRequestKey || !sourceUrl) return;
    setAnnotationMode(true);
    onAnnotationModeChange(true);
    setAnnotationPixels(null);
  }, [annotationRequestKey, onAnnotationModeChange, sourceUrl]);
  const zoom = (delta: number) => setView((current) => ({ ...current, scale: Math.max(1, Math.min(8, current.scale + delta)) }));
  useLockedWheel(viewportRef, (event) => zoom(event.deltaY < 0 ? .2 : -.2));
  const reset = () => setView({ scale: 1, x: 0, y: 0 });
  const showOriginalSize = () => {
    const layer = layerRef.current;
    if (!layer) return;
    const scale = Math.max(1, Math.min(8, Math.max(material.pixelWidth / layer.offsetWidth, material.pixelHeight / layer.offsetHeight)));
    setView({ scale, x: 0, y: 0 });
  };
  const beginPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest("[data-image-interactive='true']")) return;
    if (annotationMode) {
      const image = imageRef.current;
      const viewport = viewportRef.current;
      if (!image || !viewport) return;
      const imageRect = image.getBoundingClientRect();
      const viewportRect = viewport.getBoundingClientRect();
      if (event.clientX < imageRect.left || event.clientX > imageRect.right || event.clientY < imageRect.top || event.clientY > imageRect.bottom) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      const startX = clamp(event.clientX, imageRect.left, imageRect.right);
      const startY = clamp(event.clientY, imageRect.top, imageRect.bottom);
      annotationDragRef.current = { pointerId: event.pointerId, startX, startY, imageRect, viewportRect, bbox: { x: 0, y: 0, width: 0, height: 0 } };
      setAnnotationPixels({ left: startX - viewportRect.left, top: startY - viewportRect.top, width: 0, height: 0 });
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    panRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, originX: view.x, originY: view.y };
  };
  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const annotation = annotationDragRef.current;
    if (annotation?.pointerId === event.pointerId) {
      const endX = clamp(event.clientX, annotation.imageRect.left, annotation.imageRect.right);
      const endY = clamp(event.clientY, annotation.imageRect.top, annotation.imageRect.bottom);
      const left = Math.min(annotation.startX, endX);
      const top = Math.min(annotation.startY, endY);
      annotation.bbox = {
        x: (left - annotation.imageRect.left) / annotation.imageRect.width,
        y: (top - annotation.imageRect.top) / annotation.imageRect.height,
        width: Math.abs(endX - annotation.startX) / annotation.imageRect.width,
        height: Math.abs(endY - annotation.startY) / annotation.imageRect.height,
      };
      setAnnotationPixels({ left: left - annotation.viewportRect.left, top: top - annotation.viewportRect.top, width: Math.abs(endX - annotation.startX), height: Math.abs(endY - annotation.startY) });
      return;
    }
    const pan = panRef.current;
    if (!pan || pan.pointerId !== event.pointerId) return;
    setView((current) => ({ ...current, x: pan.originX + event.clientX - pan.startX, y: pan.originY + event.clientY - pan.startY }));
  };
  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const annotation = annotationDragRef.current;
    if (annotation?.pointerId === event.pointerId) {
      annotationDragRef.current = null;
      const bbox = annotation.bbox;
      if (bbox.width >= 0.01 && bbox.height >= 0.01) {
        const anchors = (intelligence?.result.sourceAnchors ?? []).filter((anchor): anchor is Extract<SourceAnchor, { kind: "image" }> => anchor.kind === "image" && anchor.materialId === material.id && anchor.materialVersionId === material.versionId && anchor.ocrTokenIds.length > 0);
        const ranked = anchors.map((anchor) => ({ anchor, score: bboxOverlapScore(bbox, anchor.bbox) })).sort((left, right) => right.score - left.score);
        const sourceAnchor = ranked[0]?.score >= 0.15 ? ranked[0].anchor : null;
        let snapshotDataUrl: string | null = null;
        const image = imageRef.current;
        if (image?.naturalWidth && image.naturalHeight) {
          try {
            const canvas = document.createElement("canvas");
            canvas.width = Math.max(1, Math.round(bbox.width * image.naturalWidth));
            canvas.height = Math.max(1, Math.round(bbox.height * image.naturalHeight));
            canvas.getContext("2d")?.drawImage(image, bbox.x * image.naturalWidth, bbox.y * image.naturalHeight, bbox.width * image.naturalWidth, bbox.height * image.naturalHeight, 0, 0, canvas.width, canvas.height);
            snapshotDataUrl = canvas.toDataURL("image/jpeg", 0.82);
          } catch { snapshotDataUrl = null; }
        }
        onVisualAnnotation({ bbox, snapshotDataUrl, sourceAnchor });
        setAnnotationMode(false);
        onAnnotationModeChange(false);
      }
      if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      return;
    }
    if (panRef.current?.pointerId !== event.pointerId) return;
    panRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return (
    <div className="document-preview image-document">
      <div className="document-toolbar image-document-toolbar">
        <span>{material.mimeType === "image/jpeg" ? "JPG" : material.mimeType === "image/webp" ? "WebP" : "PNG"} · v{materialVersionLabel(material.versionId, locale)}</span>
        <strong>{material.pixelWidth} × {material.pixelHeight}</strong>
        {sourceUrl ? <div className="image-view-controls" role="group" aria-label={copy(locale, "Original-image zoom and reset controls", "原始图片缩放与重置")}>
          <Button aria-label={copy(locale, "Zoom out original image", "缩小原始图片")} onClick={() => zoom(-.25)} title={copy(locale, "Zoom out", "缩小")}>−</Button>
          <span>{Math.round(view.scale * 100)}%</span>
          <Button aria-label={copy(locale, "Zoom in original image", "放大原始图片")} onClick={() => zoom(.25)} title={copy(locale, "Zoom in", "放大")}>＋</Button>
          <Button aria-label={copy(locale, "View image at original pixels", "按原始像素查看图片")} onClick={showOriginalSize} title={copy(locale, "View at 1:1", "一比一查看")}>1:1</Button>
          <Button aria-label={copy(locale, "Reset original-image view", "重置原始图片视图")} onClick={reset} title={copy(locale, "Reset view", "重置视图")}>{copy(locale, "Reset", "重置")}</Button>
          <a className="material-original-file-link" href={sourceUrl} rel="noreferrer" target="_blank">{copy(locale, "Original size", "原尺寸")}</a>
          <Button aria-pressed={annotationMode} onClick={() => { setAnnotationMode((value) => { const next = !value; onAnnotationModeChange(next); return next; }); setAnnotationPixels(null); }} title={copy(locale, "Select an image region and match OCR anchors", "框选图片区域并匹配 OCR 锚点")}>{copy(locale, "Annotate", "框选注释")}</Button>
        </div> : null}
      </div>
      {sourceUrl ? <div
        aria-label={copy(locale, "Original image; drag to pan and use the wheel to zoom", "原始图片；可拖动平移、滚轮缩放")}
        aria-busy={imageLoadState === "loading"}
        className={`image-original-viewport ${annotationMode ? "is-annotating" : ""}`}
        onPointerCancel={endPan}
        onPointerDown={beginPan}
        onPointerMove={movePan}
        onPointerUp={endPan}
        ref={viewportRef}
      >
        <figure className={`image-original-layer ${projectPhoto ? "photo-frame" : ""}`} data-orientation={material.pixelWidth >= material.pixelHeight ? "landscape" : "portrait"} ref={layerRef} style={{ aspectRatio: `${material.pixelWidth} / ${material.pixelHeight * visibleHeightRatio}`, transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}>
          <img alt={formatCanonicalText(imageName, locale)} decoding="async" draggable={false} loading="lazy" onError={() => setImageLoadState("error")} onLoad={() => setImageLoadState("ready")} ref={imageRef} src={sourceUrl} />
          {imageItems.map((item) => <LocatorBox item={item} key={item.evidence.id} onEvidenceActivate={onEvidenceActivate} visibleHeightRatio={visibleHeightRatio} />)}
          {imageLoadState !== "ready" ? <span className={`image-load-state status-${imageLoadState}`} role="status">{imageLoadState === "error" ? copy(locale, "Failed to read source image", "原图读取失败") : copy(locale, "Reading source image…", "正在读取原图")}</span> : null}
        </figure>
        {annotationPixels ? <span aria-hidden="true" className="material-annotation-selection" style={annotationPixels} /> : null}
      </div> : <div className="image-source-empty" role="status"><strong>{copy(locale, "Source image pending", "原图待接入")}</strong><span>{formatCanonicalText(material.fileName, locale)}</span></div>}
    </div>
  );
}

function MediaPreview({ material, posterUrl }: { material: MediaMaterial; posterUrl?: string }) {
  const locale = usePublicLocale();
  const sourceUrl = materialPreviewUrl(material);
  const videoRef = useManagedVideo(sourceUrl);
  if (material.mediaKind !== "video") return <div className="image-source-empty" role="status"><strong>{copy(locale, "Panoramic original pending", "全景原件待接入")}</strong><span>{formatCanonicalText(material.fileName, locale)} · {copy(locale, "Only lightweight metadata and locator ranges are retained; panoramic content is never guessed.", "当前只保留轻量元数据和定位范围；不会猜测全景内容。")}</span></div>;
  if (!sourceUrl) return <div className="image-source-empty" role="status"><strong>{copy(locale, "MP4 original pending", "MP4 原件待接入")}</strong><span>{formatCanonicalText(material.fileName, locale)} · {material.durationSeconds ?? copy(locale, "Duration unavailable", "未知")} {copy(locale, "seconds · loaded only after selection", "秒 · 仅在选中后加载")}</span></div>;
  return <div className="document-preview media-document"><div className="document-toolbar"><span>{copy(locale, "MP4 · native player", "MP4 · 原生播放器")}</span><strong>{material.durationSeconds ?? copy(locale, "Duration unavailable", "未知")} {copy(locale, "seconds", "秒")}</strong></div><div className="media-viewport"><video controls playsInline poster={posterUrl} preload="metadata" ref={videoRef} src={sourceUrl}>{copy(locale, "This browser cannot play the controlled MP4 file.", "当前浏览器无法播放此受控 MP4 文件。")}</video></div></div>;
}

export function MaterialPane({
  materials,
  facts,
  evidence,
  selectedMaterialId,
  evidenceSelectionResolution,
  selectionGroup,
  collapsed,
  onMaterialSelect,
  onEvidenceActivate,
  onToggleCollapsed,
  errorMessage,
  onRetry,
  intelligence,
  sceneSpec,
  intelligenceStatus,
  intelligenceMessage,
  modelGatewayRuntime,
  confirmingCandidateId,
  confirmedCandidateIds,
  activeIntelligenceAnchorId,
  onRunIntelligence,
  onCancelIntelligence,
  onConfirmCandidate,
  onIntelligenceAnchorActivate,
  canEditIntelligence,
  locale,
  groupChat,
  chatRatio,
  chatMaximized,
  onChatRatioChange,
  onChatMaximizedChange,
}: {
  materials: Material[];
  facts: FactVersion[];
  evidence: EvidenceReference[];
  selectedMaterialId: string;
  evidenceSelectionResolution: EvidenceSelectionResolution | null;
  selectionGroup: ReviewEvidenceSelectionGroup | null;
  collapsed: boolean;
  onMaterialSelect: (id: string) => void;
  onEvidenceActivate: (target: ReviewEvidenceTarget | null) => void;
  onToggleCollapsed: () => void;
  errorMessage?: string | null;
  onRetry?: () => void;
  intelligence: StoredMaterialIntelligence | null;
  sceneSpec: StoredSceneSpec | null;
  intelligenceStatus: "idle" | "loading" | "ready" | "empty" | "error";
  intelligenceMessage: string | null;
  modelGatewayRuntime: ModelGatewayRuntimeState;
  confirmingCandidateId: string | null;
  confirmedCandidateIds: Set<string>;
  activeIntelligenceAnchorId: string | null;
  onRunIntelligence: () => void;
  onCancelIntelligence: () => void;
  onConfirmCandidate: (candidate: ExtractedFieldCandidate, reason: string) => void;
  onIntelligenceAnchorActivate: (sourceAnchorId: string) => void;
  canEditIntelligence: boolean;
  locale: PublicLocale;
  groupChat: MaterialPaneGroupChat;
  chatRatio: number;
  chatMaximized: boolean;
  onChatRatioChange: (ratio: number) => void;
  onChatMaximizedChange: (maximized: boolean) => void;
}) {
  const [dimensionFilter, setDimensionFilter] = useState<MaterialDimensionFilter>("all");
  const [kindFilter, setKindFilter] = useState<MaterialKindFilter>("all");
  const [collapsedFolders, setCollapsedFolders] = useState<Set<MaterialBusinessFolder>>(() => new Set());
  const [sourceCollapsed, setSourceCollapsed] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [visualAnnotation, setVisualAnnotation] = useState<Extract<CollaborationContextReference, { kind: "material_annotation" }> | null>(null);
  const [annotationRequestKey, setAnnotationRequestKey] = useState(0);
  const [annotationRequestNotice, setAnnotationRequestNotice] = useState<string | null>(null);
  const [annotationWorkspaceMode, setAnnotationWorkspaceMode] = useState(false);
  const originalMaterials = materials.filter(isOriginalMaterial);
  const dimensionsByMaterial = materialDimensionIndex(facts, evidence);
  const resolving = !!selectionGroup && !evidenceSelectionResolution;
  const unresolved = evidenceSelectionResolution && evidenceSelectionResolution.status !== "located";
  const selectionTargets = selectionGroup?.targets ?? [];
  const rawHitCounts = materialHitCounts(evidenceSelectionResolution);
  const hitCounts = Object.fromEntries(Object.entries(rawHitCounts).filter(([materialId]) => {
    const material = originalMaterials.find((item) => item.id === materialId);
    return material?.kind !== "image" || Boolean(materialPreviewUrl(material));
  }));
  const displayHitCount = Object.values(hitCounts).reduce((sum, count) => sum + count, 0);
  const locatedItems = evidenceSelectionResolution?.status === "located" ? evidenceSelectionResolution.items : [];
  const firstHitMaterialId = locatedItems[0]?.material.id ?? "";
  const lastSelectedMaterialIdRef = useRef(originalMaterials.find((item) => item.id === selectedMaterialId)?.id ?? originalMaterials[0]?.id ?? "");
  const previewScrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (originalMaterials.some((item) => item.id === selectedMaterialId)) lastSelectedMaterialIdRef.current = selectedMaterialId;
  }, [originalMaterials, selectedMaterialId]);
  useEffect(() => {
    previewScrollRef.current?.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [selectedMaterialId]);
  const selected = (resolving ? undefined : originalMaterials.find((item) => item.id === selectedMaterialId))
    ?? originalMaterials.find((item) => item.id === firstHitMaterialId)
    ?? originalMaterials.find((item) => item.id === lastSelectedMaterialIdRef.current)
    ?? (unresolved || resolving ? undefined : originalMaterials[0]);
  useEffect(() => setVisualAnnotation(null), [selected?.id, selected?.versionId]);
  const selectedEvidence = groupChat.selectedTarget ? evidence.find((item) => item.id === groupChat.selectedTarget?.evidenceRef) : undefined;
  const selectedSourceAnchor = selectedEvidence ? intelligence?.result.sourceAnchors.find((anchor) => evidenceRefForSourceAnchor(anchor.id) === selectedEvidence.id) : undefined;
  const exactAnnotation = selected && groupChat.selectedTarget && selectedEvidence?.locator?.materialId === selected.id
    ? {
        kind: "material_annotation" as const,
        id: `annotation-element-${selected.versionId}-${selectedEvidence.id}`,
        label: `${selected.fileName} · ${selectedEvidence.label}`,
        createdAt: new Date(0).toISOString(),
        materialId: selected.id,
        materialVersionId: selected.versionId,
        locatorMethod: "element" as const,
        matchStatus: "exact" as const,
        sourceAnchorId: selectedSourceAnchor?.id ?? null,
        region: selectedEvidence.locator.kind === "image" || selectedEvidence.locator.kind === "pdf" ? selectedEvidence.locator.bbox : null,
        snapshotDataUrl: null,
        evidenceTargets: [groupChat.selectedTarget],
      }
    : null;
  const annotationReference = visualAnnotation ?? exactAnnotation;
  const acceptVisualAnnotation = ({ bbox, snapshotDataUrl, sourceAnchor }: VisualAnnotationDraft) => {
    if (!selected) return;
    const evidenceRef = sourceAnchor ? evidenceRefForSourceAnchor(sourceAnchor.id) : null;
    const matchedEvidence = evidenceRef ? evidence.find((item) => item.id === evidenceRef) : undefined;
    const matchedFact = evidenceRef ? facts.find((item) => item.evidenceRefs.includes(evidenceRef)) : undefined;
    const selectedTarget = groupChat.selectedTarget?.evidenceRef === evidenceRef ? groupChat.selectedTarget : null;
    const target = matchedEvidence && (matchedFact || selectedTarget) ? {
      evidenceRef: matchedEvidence.id,
      evidenceRefs: matchedFact?.evidenceRefs ?? selectedTarget?.evidenceRefs ?? [matchedEvidence.id],
      dimensionId: matchedFact?.dimensionId ?? selectedTarget!.dimensionId,
      reviewTargetId: matchedFact?.id ?? selectedTarget!.reviewTargetId,
      factVersionId: matchedFact?.id ?? selectedTarget!.factVersionId,
    } satisfies ReviewEvidenceTarget : null;
    setVisualAnnotation({
      kind: "material_annotation",
      id: `annotation-ocr-${selected.versionId}-${Date.now()}`,
      label: sourceAnchor ? `${selected.fileName} · OCR ${sourceAnchor.ocrTokenIds.length} tokens` : `${selected.fileName} · OCR 待匹配区域`,
      createdAt: new Date(0).toISOString(),
      materialId: selected.id,
      materialVersionId: selected.versionId,
      locatorMethod: "ocr_region",
      matchStatus: "pending",
      sourceAnchorId: sourceAnchor?.id ?? null,
      region: bbox,
      snapshotDataUrl,
      evidenceTargets: target ? [target] : [],
    });
    setAnnotationRequestNotice(copy(locale, "The region is ready. Attach the annotation in the group composer, then add your question.", "区域已生成；请在群聊中点击“附加注释”，再输入你的问题。"));
    setAnnotationWorkspaceMode(false);
  };
  const requestVisualAnnotation = () => {
    setSourceCollapsed(false);
    setChatCollapsed(false);
    onChatMaximizedChange(false);
    if (chatRatio > 30) onChatRatioChange(30);
    const imageMaterial = selected?.kind === "image" && materialPreviewUrl(selected)
      ? selected
      : originalMaterials.find((item): item is ImageMaterial => item.kind === "image" && Boolean(materialPreviewUrl(item)));
    if (!imageMaterial) {
      setAnnotationWorkspaceMode(false);
      setAnnotationRequestNotice(copy(locale, "No displayable source image is available. Select a located evidence element first to attach its exact location.", "当前没有可框选的原始图片；请先选择带定位的证据元素，再附加其精确位置。"));
      return;
    }
    if (selected?.id !== imageMaterial.id) onMaterialSelect(imageMaterial.id);
    setVisualAnnotation(null);
    setAnnotationWorkspaceMode(true);
    setAnnotationRequestNotice(copy(locale, "Drag a box on the source image. OCR matching remains pending until a human confirms it.", "已进入框选模式：请在原始图片上拖出区域；OCR 匹配需人工确认。"));
    setAnnotationRequestKey((current) => current + 1);
  };
  const filteredMaterials = originalMaterials.filter((material) => {
    const dimensions = dimensionsByMaterial.get(material.id);
    const matchesDimension = dimensionFilter === "all"
      || (dimensionFilter === "unassigned" ? !dimensions?.size : dimensions?.has(dimensionFilter));
    return matchesDimension && (kindFilter === "all" || material.kind === kindFilter);
  });
  const visibleMaterials = selected && !filteredMaterials.some((material) => material.id === selected.id)
    ? [selected, ...filteredMaterials]
    : filteredMaterials;
  const retainingSelectedOutsideFilter = Boolean(selected && !filteredMaterials.some((material) => material.id === selected.id));
  const presentDimensions = DIMENSION_IDS.filter((dimensionId) => [...dimensionsByMaterial.values()].some((items) => items.has(dimensionId)));
  const selectedItems = selected ? locatedItems.filter((item) => item.material.id === selected.id) : [];
  const selectedOriginalUnavailable = selected ? archivedOriginalUnavailable(selected, locale) : null;
  const selectedAssetUnavailable = selected?.kind === "image" && !materialPreviewUrl(selected);
  const selectedRawAssetUnsupported = selected?.kind === "media";
  const groupedMaterials = MATERIAL_BUSINESS_FOLDERS.map((folder) => ({ folder, materials: visibleMaterials.filter((material) => businessFolderFor(material) === folder) }));
  const toggleFolder = (folder: MaterialBusinessFolder) => setCollapsedFolders((current) => {
    const next = new Set(current);
    if (next.has(folder)) next.delete(folder); else next.add(folder);
    return next;
  });
  const beginChatResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const divider = event.currentTarget;
    const pane = divider.closest<HTMLElement>(".material-pane");
    if (!pane) return;
    setSourceCollapsed(false);
    setChatCollapsed(false);
    const pointerId = event.pointerId;
    divider.setPointerCapture(pointerId);
    let nextRatio = chatRatio;
    let frameId: number | null = null;
    const applyResize = () => {
      frameId = null;
      pane.style.setProperty("--layout-source-share", `${100 - nextRatio}fr`);
      pane.style.setProperty("--layout-chat-share", `${nextRatio}fr`);
      divider.setAttribute("aria-valuenow", String(Math.round(nextRatio)));
    };
    const move = (pointerEvent: PointerEvent) => {
      if (pointerEvent.pointerId !== pointerId) return;
      const rect = pane.getBoundingClientRect();
      nextRatio = clamp(((rect.bottom - pointerEvent.clientY) / Math.max(1, rect.height)) * 100, ...LAYOUT_LIMITS.collaborationRatio);
      if (frameId === null) frameId = window.requestAnimationFrame(applyResize);
    };
    const cleanup = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      window.removeEventListener("blur", stop);
      if (divider.hasPointerCapture(pointerId)) divider.releasePointerCapture(pointerId);
    };
    function stop(stopEvent?: Event) {
      if (stopEvent instanceof PointerEvent && stopEvent.pointerId !== pointerId) return;
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      applyResize();
      onChatRatioChange(nextRatio);
      cleanup();
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
  };
  const resizeChatWithKeyboard = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    setSourceCollapsed(false);
    setChatCollapsed(false);
    if (event.key === "Home") { onChatRatioChange(LAYOUT_LIMITS.collaborationRatio[0]); return; }
    if (event.key === "End") { onChatRatioChange(LAYOUT_LIMITS.collaborationRatio[1]); return; }
    const direction = event.key === "ArrowUp" ? 1 : -1;
    onChatRatioChange(clamp(chatRatio + direction * (event.shiftKey ? 5 : 2), ...LAYOUT_LIMITS.collaborationRatio));
  };
  const showPreview = () => {
    if (errorMessage) return <div><EmptyState detail={formatServiceMessage(errorMessage, locale)} title={copy(locale, "Material read failed", "材料读取失败")} />{onRetry ? <Button onClick={onRetry}>{copy(locale, "Retry", "重试")}</Button> : null}</div>;
    if (resolving) return <EmptyState detail={copy(locale, "The selection group was saved. Material versions and all locator regions are being verified in the background.", "选择组已保存，正在后台核对材料版本与全部定位区域。")} title={copy(locale, "Resolving in background", "后台解析中")} />;
    if (unresolved) return <EmptyState detail={formatServiceMessage(evidenceSelectionResolution.message, locale)} title={evidenceSelectionResolution.status === "pending" ? copy(locale, "Evidence awaiting location", "证据待定位") : evidenceSelectionResolution.status === "version_mismatch" ? copy(locale, "Material version mismatch", "材料版本不符") : copy(locale, "Evidence unverifiable", "证据不可核验")} />;
    if (!selected) return <EmptyState detail={copy(locale, "Select a material.", "请选择一份材料。")} title={copy(locale, "No material selected", "暂无材料")} />;
    if (selectedOriginalUnavailable) return <EmptyState detail={selectedOriginalUnavailable.detail} title={selectedOriginalUnavailable.title} />;
    if (selected.kind === "excel") return <SpreadsheetPreview material={selected} onEvidenceActivate={onEvidenceActivate} selectionItems={selectedItems} />;
    if (selected.kind === "pdf") return <PdfPreview material={selected} onEvidenceActivate={onEvidenceActivate} selectionItems={selectedItems} />;
    if (selected.kind === "document") return <DocumentPreview material={selected} />;
    if (selected.kind === "image") return <ImagePreview annotationRequestKey={annotationRequestKey} intelligence={intelligence} material={selected} onAnnotationModeChange={setAnnotationWorkspaceMode} onEvidenceActivate={onEvidenceActivate} onVisualAnnotation={acceptVisualAnnotation} selectionItems={selectedItems} />;
    if (selected.kind === "media") { const poster = materials.find((item): item is ImageMaterial => item.id === selected.posterMaterialId && item.kind === "image"); return <MediaPreview material={selected} posterUrl={poster ? materialPreviewUrl(poster) : undefined} />; }
    return <EmptyState detail={copy(locale, "Derived analysis is not displayed as an original. Select an original file from one of the five business folders.", "派生分析不会作为原件显示；请从五类业务目录选择原始文件。")} title={copy(locale, "Not an original material", "非原始材料")} />;
  };

  return (
    <aside className={`material-pane has-project-chat ${collapsed ? "is-collapsed" : ""} ${sourceCollapsed ? "is-source-collapsed" : ""} ${chatCollapsed ? "is-chat-collapsed" : ""} ${chatMaximized ? "is-chat-maximized" : ""} ${annotationWorkspaceMode ? "is-annotation-workspace" : ""}`} aria-label={copy(locale, "Original materials and project group chat", "原始材料与项目群聊区域")} data-semantic-localized id="material-pane" style={{ "--layout-source-share": `${100 - chatRatio}fr`, "--layout-chat-share": `${chatRatio}fr` } as CSSProperties}>
      {collapsed ? (
        <button aria-controls="material-pane" aria-expanded={false} aria-label={copy(locale, "Expand original materials from the upper-right corner", "从右上角展开原始材料")} className="pane-corner-anchor material-corner-anchor" onClick={onToggleCollapsed} title={copy(locale, "Expand original materials from the upper-right corner", "从右上角展开原始材料")} type="button"><span aria-hidden="true" className="pane-corner-glyph">↙</span></button>
      ) : (
        <>
          <section className="material-source-workspace">
          <header className="pane-heading">
            <div><h2>{copy(locale, "Original materials", "原始材料")}</h2></div>
            <div className="pane-actions"><Button aria-controls="material-pane" aria-expanded aria-label={copy(locale, "Collapse original materials to the upper-right corner", "收起原始材料至右上角")} className="pane-corner-anchor material-corner-anchor" onClick={onToggleCollapsed} title={copy(locale, "Collapse original materials to the upper-right corner", "收起原始材料至右上角")}><span aria-hidden="true" className="pane-corner-glyph">↗</span></Button></div>
          </header>
          <div className="material-tabs" aria-label={copy(locale, "Material list", "材料列表")}>
            <div className="material-index-controls">
              <label><span>{copy(locale, "Business dimension", "业务维度")}</span><select aria-label={copy(locale, "Filter materials by business dimension", "按业务维度筛选材料")} onChange={(event) => setDimensionFilter(event.target.value as MaterialDimensionFilter)} value={dimensionFilter}><option value="all">{copy(locale, "All", "全部")}</option>{presentDimensions.map((dimensionId) => <option key={dimensionId} value={dimensionId}>{copy(locale, ({ compliance: "Compliance", transaction: "Transaction", production: "Operations", revenue: "Revenue", debt: "Debt", cashflow: "Cash flow" } as const)[dimensionId], DIMENSION_LABELS[dimensionId])}</option>)}<option value="unassigned">{copy(locale, "General / awaiting classification", "通用 / 待归类")}</option></select></label>
              <label><span>{copy(locale, "Material type", "材料类型")}</span><select aria-label={copy(locale, "Filter materials by type", "按材料类型筛选材料")} onChange={(event) => setKindFilter(event.target.value as MaterialKindFilter)} value={kindFilter}><option value="all">{copy(locale, "All", "全部")}</option>{Object.entries(MATERIAL_KIND_LABELS).map(([kind, label]) => <option key={kind} value={kind}>{copy(locale, ({ excel: "Spreadsheet", pdf: "PDF", document: "Word document", image: "Image", media: "Media" } as const)[kind as OriginalMaterial["kind"]], label)}</option>)}</select></label>
              <strong aria-live="polite">{filteredMaterials.length} / {originalMaterials.length}{retainingSelectedOutsideFilter ? copy(locale, " · current material retained", " · 保留当前") : ""}</strong>
            </div>
            <div className="material-folder-tree">
              {groupedMaterials.map(({ folder, materials: folderMaterials }) => <section className="material-folder" data-folder={folder} key={folder}>
                <button aria-controls={`material-folder-${folder}`} aria-expanded={!collapsedFolders.has(folder)} className="material-folder-heading" onClick={() => toggleFolder(folder)} type="button"><Icon name="chevron" /><strong>{formatCanonicalText(folder, locale)}</strong><small>{folderMaterials.length} {copy(locale, "items", "项")}</small></button>
                <div className="material-tab-list" hidden={collapsedFolders.has(folder)} id={`material-folder-${folder}`}>
              {folderMaterials.map((material) => {
                const presentation = materialTabPresentation(material);
                const displayLabel = formatCanonicalText(material.kind === "image" ? cleanVisualFileName(material.fileName) : presentation.label, locale);
                const dimensionLabel = [...(dimensionsByMaterial.get(material.id) ?? new Set<DimensionId>())].map((dimensionId) => copy(locale, DIMENSION_LABELS[dimensionId].replace("合规", "Compliance").replace("交易", "Transaction").replace("生产", "Operations").replace("营收", "Revenue").replace("负债", "Debt").replace("流水", "Cash flow"), DIMENSION_LABELS[dimensionId])).join("/") || copy(locale, "General", "通用");
                const outsideFilter = !filteredMaterials.some((item) => item.id === material.id);
                const originalFile = formatCanonicalText(material.fileName, locale);
                const kindLabel = copy(locale, ({ excel: "Spreadsheet", pdf: "PDF", document: "Word document", image: "Image", media: "Media" } as const)[material.kind], MATERIAL_KIND_LABELS[material.kind]);
                return <button aria-current={material.id === selected?.id ? "page" : undefined} aria-label={copy(locale, `Open material: ${displayLabel}; business folder ${formatCanonicalText(folder, locale)}; material type ${kindLabel}; original file ${originalFile}${hitCounts[material.id] ? `, ${hitCounts[material.id]} evidence hits` : ""}`, `打开材料：${displayLabel}；业务目录 ${folder}；材料类型 ${MATERIAL_KIND_LABELS[material.kind]}；原文件 ${material.fileName}${hitCounts[material.id] ? `，命中${hitCounts[material.id]}处` : ""}`)} className={`${material.id === selected?.id ? "is-active" : ""} ${hitCounts[material.id] ? "has-evidence-hits" : ""} ${outsideFilter ? "is-outside-filter" : ""}`} data-material-id={material.id} key={material.id} onClick={() => onMaterialSelect(material.id)} title={`${formatCanonicalText(materialRelativePath(material), locale)} · ${dimensionLabel} · ${kindLabel}`} type="button">
                  <Icon name={materialIcon(material)} /><span><strong>{displayLabel}</strong><small>{formatCanonicalText(materialRelativePath(material), locale)} · {presentation.extension || kindLabel}</small></span>{hitCounts[material.id] ? <b className="material-hit-count">{hitCounts[material.id]}</b> : null}
                </button>;
              })}
                </div>
              </section>)}
              {visibleMaterials.length === 0 ? <p className="material-index-empty">{copy(locale, "No original materials match the current filters.", "当前筛选没有原始材料。")}</p> : null}
            </div>
          </div>
          <div className="material-preview" ref={previewScrollRef}>{showPreview()}<MaterialIntelligencePanel activeAnchorId={activeIntelligenceAnchorId} canEdit={canEditIntelligence} confirmedCandidateIds={confirmedCandidateIds} confirmingCandidateId={confirmingCandidateId} intelligence={intelligence} message={intelligenceMessage} onAnchorActivate={onIntelligenceAnchorActivate} onCancel={onCancelIntelligence} onConfirm={onConfirmCandidate} onRun={onRunIntelligence} runtime={modelGatewayRuntime} scene={selected?.kind === "image" ? null : sceneSpec} status={intelligenceStatus} /></div>
          <footer className={`material-note resolution-${resolving ? "pending" : selectedOriginalUnavailable || selectedAssetUnavailable || selectedRawAssetUnsupported ? "unverifiable" : evidenceSelectionResolution?.status ?? "idle"}`}><Icon name="link" /><span>{visualAnnotation ? <><b>{copy(locale, "Visual annotation", "视觉注释")}</b> · {visualAnnotation.evidenceTargets.length ? copy(locale, "OCR anchor candidate found; human confirmation required", "已找到 OCR 锚点候选，需人工确认") : copy(locale, "No OCR anchor match; keep pending", "未匹配到 OCR 锚点，保持待确认")}</> : annotationRequestNotice ? <><b>{copy(locale, "Annotation", "注释")}</b> · {annotationRequestNotice}</> : resolving ? <><b>{copy(locale, "Resolving in background", "后台解析")}</b> · {copy(locale, "previous highlights cleared", "旧高亮已清除")}</> : selectedOriginalUnavailable ? <><b>{selectedOriginalUnavailable.title}</b> · {selectedOriginalUnavailable.detail}</> : selectedAssetUnavailable ? <><b>{copy(locale, "Location incomplete", "定位未完成")}</b> · {copy(locale, "site source image pending", "现场原图待接入")}</> : selectedRawAssetUnsupported ? <><b>{copy(locale, "Location incomplete", "定位未完成")}</b> · {copy(locale, "original asset pending", "原始资产待接入")}</> : evidenceSelectionResolution ? evidenceSelectionResolution.status === "located" ? <b>{displayHitCount} {copy(locale, "regions", "个区域")}</b> : <><b>{copy(locale, "Location incomplete", "定位未完成")}</b> · {formatServiceMessage(evidenceSelectionResolution.message.replace(/[。；]+$/u, ""), locale)}</> : <b>{copy(locale, "Original material", "原始材料")}</b>}</span>{visualAnnotation ? <div className="material-annotation-actions">{visualAnnotation.matchStatus === "pending" && visualAnnotation.evidenceTargets.length ? <Button onClick={() => setVisualAnnotation({ ...visualAnnotation, matchStatus: "confirmed" })}>{copy(locale, "Confirm OCR match", "确认 OCR 匹配")}</Button> : null}<Button onClick={() => { setVisualAnnotation(null); setAnnotationRequestNotice(null); setAnnotationWorkspaceMode(false); }}>{copy(locale, "Clear", "清除")}</Button></div> : null}</footer>
          </section>
          <div aria-label={copy(locale, "Resize original materials and project group chat", "调整原始材料与项目群聊高度")} aria-orientation="horizontal" aria-valuemax={LAYOUT_LIMITS.collaborationRatio[1]} aria-valuemin={LAYOUT_LIMITS.collaborationRatio[0]} aria-valuenow={Math.round(chatRatio)} aria-valuetext={copy(locale, `Project chat height: ${Math.round(chatRatio)}%`, `项目群聊高度 ${Math.round(chatRatio)}%`)} className="material-split-divider" onKeyDown={resizeChatWithKeyboard} onPointerDown={beginChatResize} role="separator" tabIndex={0}>
          </div>
          <div className="material-chat-slot"><A2ACollaborationPanel accountRole={groupChat.accountRole} agentActivity={groupChat.agentActivity} agentError={groupChat.agentError} agentMessages={groupChat.agentMessages} annotationReference={annotationReference} collapsed={chatCollapsed} evidence={evidence} maximized={chatMaximized} onAgentEvidenceActivate={(target) => onEvidenceActivate(target)} onConfirmMaterialImport={groupChat.onConfirmMaterialImport} onImportMaterialPackage={groupChat.onImportMaterialPackage} onRequestAnnotation={requestVisualAnnotation} onSubmitMessage={groupChat.onSubmitMessage} onToggleMaximized={() => { setChatCollapsed(false); onChatMaximizedChange(!chatMaximized); }} selectedTarget={groupChat.selectedTarget} /></div>
        </>
      )}
    </aside>
  );
}
