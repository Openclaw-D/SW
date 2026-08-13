import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type {
  CommonReviewEvent,
  ApprovalState,
  ApprovalTransition,
  FactValue,
  FactVersion,
  HardConstraintResult,
  LayoutState,
  MappedCommonReviewEvent,
  ReviewEvidenceSelectionGroup,
  ReviewEvidenceTarget,
  WorkbenchProject,
} from "./contracts/workbench";
import { evidenceRefForSourceAnchor, type ExtractedFieldCandidate, type MaterialImportPreflight, type MaterialUploadReceipt, type StoredMaterialIntelligence, type StoredSceneSpec } from "./contracts/materialIntelligence";
import { WorkbenchGatewayError, type WorkbenchGateway } from "./gateway/workbenchGateway";
import type { ModelGatewayRuntimeState } from "./contracts/modelGateway";
import type { ProjectConclusionReport } from "./contracts/conclusion";
import type { AgentFocusEvent, AgentMessage, AgentRole, AgentThread, CollaborationContextReference } from "./contracts/agentCommunication";
import { cancelledModelGatewayRuntime, emptyModelGatewayRuntime, failedModelGatewayRuntime, modelGatewayRuntimeFromResult } from "./lib/modelGatewayState";
import {
  attachReviewEvidenceTargets,
  clamp,
  displayBusinessText,
  deriveScoreSummary,
  LAYOUT_LIMITS,
  createEvidenceSelectionGroup,
  persistedLayoutFrom,
  PERSISTED_LAYOUT_KEY,
  riskItemCount,
  resolveEvidenceSelectionGroup,
  sanitizePersistedLayout,
  scoreToGrade,
  type EvidenceSelectionResolution,
} from "./lib/workbenchLogic";
import { CollaborationDock } from "./components/CollaborationDock";
import { MaterialPane } from "./components/MaterialPane";
import { NavigationRail } from "./components/NavigationRail";
import { ReviewCanvas, type ReviewSectionId } from "./components/ReviewCanvas";
import { TopBar } from "./components/TopBar";
import { FinalConclusionReport } from "./components/FinalConclusionReport";
import { EmptyState } from "./components/ui";
import { initialMaterialLoadFailed, materialRecoveryFailed, materialRecoverySucceeded, replayMaterialRecovery, retryOnceAfterVersionConflict } from "./lib/recoveryState";
import { isOriginalMaterial } from "./lib/materialBusinessFolders";
import { copy, type PublicLocale } from "./lib/publicLocale";

type ResizeAxis = "material" | "collaboration";
type MaterialEdge = "review" | "material" | null;
type CollaborationEdge = "review" | "collaboration" | null;

const DIVIDER_SNAP_THRESHOLD = 24;
const DEFAULT_COLLABORATION_HEIGHT = 400;
const LEGACY_DEFAULT_COLLABORATION_HEIGHT = 175;
const PERSISTED_LAYOUT_VERSION = 2;
const PERSISTED_LAYOUT_VERSION_KEY = `${PERSISTED_LAYOUT_KEY}-schema`;

async function retryAgentRead<T>(request: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  try {
    return await request();
  } catch (reason) {
    if (signal?.aborted) throw reason;
    return request();
  }
}

async function readAgentSessionSnapshot(gateway: WorkbenchGateway, projectId: string, threadId: string, signal?: AbortSignal) {
  const options = signal ? { signal } : undefined;
  const [thread, messages, focusEvents] = await Promise.allSettled([
    retryAgentRead(() => gateway.readAgentThread(projectId, threadId, "business", options), signal),
    retryAgentRead(() => gateway.readAgentMessages(projectId, threadId, "business", options), signal),
    retryAgentRead(() => gateway.readAgentFocusEvents(projectId, threadId, "business", options), signal),
  ]);
  return { thread, messages, focusEvents };
}

function agentReadError(result: PromiseSettledResult<unknown>) {
  if (result.status === "fulfilled") return null;
  return result.reason instanceof Error ? result.reason.message : "Agent 会话同步失败。";
}

function parseEditedValue(current: FactValue, next: string): FactValue {
  if (typeof current === "number") return Number.isFinite(Number(next)) ? Number(next) : next;
  if (typeof current === "boolean") return ["是", "true", "1"].includes(next.trim().toLowerCase());
  return next;
}

function authoritativeEvents(items: CommonReviewEvent[]): MappedCommonReviewEvent[] {
  return [...items].sort((left, right) => left.sequence - right.sequence).map((event) => attachReviewEvidenceTargets(event, event.evidenceTargets ?? []));
}

function confirmedCandidateIdsFromEvents(items: CommonReviewEvent[]) {
  return new Set(items.flatMap((item) => item.threadId.startsWith("candidate::") ? [item.threadId.slice("candidate::".length)] : []));
}

const TECHNICAL_STRING_KEYS = new Set(["id", "projectId", "factKey", "versionId", "materialId", "evidenceRef", "reviewTargetId", "threadId", "eventType", "dimensionId", "ruleId", "ruleVersion", "kind", "status", "locationStatus", "actor", "actorLabel", "source", "url", "mimeType"]);

function presentationCopy<T>(value: T): T {
  if (typeof value === "string") return displayBusinessText(value) as T;
  if (Array.isArray(value)) return value.map((item) => presentationCopy(item)) as T;
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, TECHNICAL_STRING_KEYS.has(key) ? item : presentationCopy(item)])) as T;
}

export function openIssueCountFromEvents(items: CommonReviewEvent[]): number {
  const latest = new Map<string, CommonReviewEvent>();
  for (const item of items) {
    const current = latest.get(item.threadId);
    if (!current || item.sequence > current.sequence) latest.set(item.threadId, item);
  }
  return [...latest.values()].filter((item) => item.issueStatus === "open").length;
}

export function latestFactVersionsByFactKey(items: FactVersion[]): FactVersion[] {
  const latest = new Map<string, FactVersion>();
  for (const item of items) {
    const current = latest.get(item.factKey);
    if (!current || item.version > current.version || (item.version === current.version && item.id.localeCompare(current.id) > 0)) latest.set(item.factKey, item);
  }
  return [...latest.values()].sort((left, right) => left.factKey.localeCompare(right.factKey));
}

function idempotencyKey(operation: string, payload: unknown, store: Map<string, { fingerprint: string; key: string }>) {
  const fingerprint = JSON.stringify(payload);
  const previous = store.get(operation);
  if (previous?.fingerprint === fingerprint) return previous.key;
  const key = `p4m2-${crypto.randomUUID().replaceAll("-", "")}`;
  store.set(operation, { fingerprint, key });
  return key;
}

function clearIdempotencyKey(operation: string, store: Map<string, { fingerprint: string; key: string }>) { store.delete(operation); }

function materialVersionNumber(versionId: string) {
  const parsed = Number(/-v(\d+)$/i.exec(versionId)?.[1] ?? "1");
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

export function App({ gateway, projectId, projectNo, onBack, showSimulationControls = false, locale = "en", onLocaleChange }: { gateway: WorkbenchGateway; projectId: string; projectNo: string; onBack: () => void; showSimulationControls?: boolean; locale?: PublicLocale; onLocaleChange?: (locale: PublicLocale) => void }) {
  const [data, setData] = useState<WorkbenchProject | null>(null);
  const [layout, setLayout] = useState<LayoutState | null>(null);
  const [materialEdge, setMaterialEdge] = useState<MaterialEdge>(null);
  const [collaborationEdge, setCollaborationEdge] = useState<CollaborationEdge>(null);
  const [layoutResetVersion, setLayoutResetVersion] = useState(0);
  const [facts, setFacts] = useState<FactVersion[]>([]);
  const [events, setEvents] = useState<MappedCommonReviewEvent[]>([]);
  const [agentThread, setAgentThread] = useState<AgentThread | null>(null);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const [agentFocusEvents, setAgentFocusEvents] = useState<AgentFocusEvent[]>([]);
  const [agentSessionError, setAgentSessionError] = useState<string | null>(null);
  const [policyRules, setPolicyRules] = useState<HardConstraintResult[]>([]);
  const [openIssueCount, setOpenIssueCount] = useState(0);
  const [approvalState, setApprovalState] = useState<ApprovalState | null>(null);
  const [approvalPending, setApprovalPending] = useState(false);
  const [approvalMessage, setApprovalMessage] = useState<string | null>(null);
  const [conclusionOpen, setConclusionOpen] = useState(false);
  const [conclusionReport, setConclusionReport] = useState<ProjectConclusionReport | null>(null);
  const [conclusionStatus, setConclusionStatus] = useState<"loading" | "ready" | "error">("loading");
  const [conclusionError, setConclusionError] = useState<string | null>(null);
  const [selectedMaterialId, setSelectedMaterialId] = useState("");
  const [selectedProductionStageId, setSelectedProductionStageId] = useState("");
  const [, setSelectedReferenceImageId] = useState<string | null>(null);
  const [selectedReviewTarget, setSelectedReviewTarget] = useState<ReviewEvidenceTarget | null>(null);
  const [evidenceSelectionGroup, setEvidenceSelectionGroup] = useState<ReviewEvidenceSelectionGroup | null>(null);
  const [activeReviewId, setActiveReviewId] = useState<ReviewSectionId>("risk");
  const [evidenceSelectionResolution, setEvidenceSelectionResolution] = useState<EvidenceSelectionResolution | null>(null);
  const selectionRequestRef = useRef(0);
  const [correctionPending, setCorrectionPending] = useState(false);
  const [correctionMessage, setCorrectionMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [materialRecovery, setMaterialRecovery] = useState(materialRecoverySucceeded);
  const [materialIntelligence, setMaterialIntelligence] = useState<StoredMaterialIntelligence | null>(null);
  const [modelGatewayRuntime, setModelGatewayRuntime] = useState<ModelGatewayRuntimeState>(emptyModelGatewayRuntime);
  const [materialSceneSpec, setMaterialSceneSpec] = useState<StoredSceneSpec | null>(null);
  const [intelligenceStatus, setIntelligenceStatus] = useState<"idle" | "loading" | "ready" | "empty" | "error">("idle");
  const [intelligenceMessage, setIntelligenceMessage] = useState<string | null>(null);
  const [confirmingCandidateId, setConfirmingCandidateId] = useState<string | null>(null);
  const [confirmedCandidateIds, setConfirmedCandidateIds] = useState<Set<string>>(() => new Set());
  const [activeIntelligenceAnchorId, setActiveIntelligenceAnchorId] = useState<string | null>(null);
  const materialRequestRef = useRef(0);
  const selectionAbortRef = useRef<AbortController | null>(null);
  const materialAbortRef = useRef<AbortController | null>(null);
  const writeKeysRef = useRef(new Map<string, { fingerprint: string; key: string }>());
  const agentThreadRef = useRef<AgentThread | null>(null);
  const agentThreadCreationRef = useRef<Promise<AgentThread> | null>(null);
  const activeProjectRef = useRef(projectId);
  const intelligenceRequestRef = useRef(0);
  const intelligenceRunAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    activeProjectRef.current = projectId;
    setConclusionOpen(false);
    setConclusionReport(null);
    setConclusionStatus("loading");
    setConclusionError(null);
    const controller = new AbortController();
    setData(null);
    setLayout(null);
    setMaterialEdge(null);
    setCollaborationEdge(null);
    setError(null);
    setMaterialRecovery(materialRecoverySucceeded());
    setMaterialIntelligence(null);
    intelligenceRunAbortRef.current?.abort();
    intelligenceRunAbortRef.current = null;
    setModelGatewayRuntime(emptyModelGatewayRuntime());
    setMaterialSceneSpec(null);
    setIntelligenceStatus("idle");
    setIntelligenceMessage(null);
    setConfirmedCandidateIds(new Set());
    setActiveIntelligenceAnchorId(null);
    agentThreadRef.current = null;
    agentThreadCreationRef.current = null;
    setAgentThread(null);
    setAgentMessages([]);
    setAgentFocusEvents([]);
    setAgentSessionError(null);
    Promise.all([gateway.loadProject(projectId, { signal: controller.signal }), gateway.listMaterials(projectId, { signal: controller.signal }), gateway.readReviewEvents(projectId, { signal: controller.signal }), gateway.readPolicyResults(projectId, { signal: controller.signal }), gateway.readApprovalState(projectId, { signal: controller.signal })]).then(async ([project, materials, reviewEvents, policies, approval]) => {
      if (!active) return;
      let firstMaterial = null;
      let initialMaterialFailure: ReturnType<typeof initialMaterialLoadFailed> | null = null;
      const firstOriginalMaterial = materials.find(isOriginalMaterial);
      if (firstOriginalMaterial) {
        try {
          firstMaterial = await gateway.readMaterial(projectId, firstOriginalMaterial.id, { signal: controller.signal });
        } catch (reason) {
          if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
          initialMaterialFailure = initialMaterialLoadFailed(reason instanceof Error ? reason.message : "读取首份材料失败；请重试。", firstOriginalMaterial.id);
        }
      }
      if (!active) return;
      const presentedProject = presentationCopy(project);
      const scoreSummary = deriveScoreSummary(presentedProject.dimensions);
      const scoredProject: WorkbenchProject = {
        ...presentedProject,
        layout: { ...presentedProject.layout, collaborationHeight: DEFAULT_COLLABORATION_HEIGHT },
        materials: firstMaterial ? materials.map((item) => item.id === firstMaterial.id ? firstMaterial : item) : materials,
        dimensions: scoreSummary.dimensions,
        riskSummary: { ...presentedProject.riskSummary, scoreGrade: scoreSummary.overallGrade },
        determinations: presentedProject.determinations.map((item) => ({ ...item, scoreGrade: scoreToGrade(item.score) })),
      };
      let stored: unknown = null;
      let storedLayoutVersion = 0;
      try {
        stored = JSON.parse(localStorage.getItem(PERSISTED_LAYOUT_KEY) ?? "null");
        storedLayoutVersion = Number(localStorage.getItem(PERSISTED_LAYOUT_VERSION_KEY) ?? "0");
      } catch { stored = null; }
      const persisted = { ...sanitizePersistedLayout(stored, scoredProject.layout) };
      if (storedLayoutVersion < PERSISTED_LAYOUT_VERSION && persisted.collaborationHeight === LEGACY_DEFAULT_COLLABORATION_HEIGHT) {
        persisted.collaborationHeight = DEFAULT_COLLABORATION_HEIGHT;
      }
      setData(scoredProject);
      setFacts(latestFactVersionsByFactKey(scoredProject.facts));
      setEvents(presentationCopy(authoritativeEvents(reviewEvents)));
      setConfirmedCandidateIds(confirmedCandidateIdsFromEvents(reviewEvents));
      setPolicyRules(presentationCopy(policies));
      setOpenIssueCount(project.project.collaborationIssueCount);
      setApprovalState(approval);
      setApprovalMessage(null);
      setSelectedMaterialId(firstMaterial?.id ?? scoredProject.materials.find(isOriginalMaterial)?.id ?? "");
      setSelectedProductionStageId(scoredProject.productionStages[0]?.id ?? "");
      setSelectedReferenceImageId(null);
      setSelectedReviewTarget(null);
      setEvidenceSelectionGroup(null);
      setEvidenceSelectionResolution(null);
      setMaterialRecovery(initialMaterialFailure?.recovery ?? materialRecoverySucceeded());
      setLayout({ ...scoredProject.layout, ...persisted });
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      if (active) setError(reason instanceof Error ? reason.message : "无法加载项目");
    });
    return () => { active = false; controller.abort(); };
  }, [gateway, projectId]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setAgentSessionError(null);
    void retryAgentRead(() => gateway.readConclusionReport(projectId, { signal: controller.signal }), controller.signal).then(async (report) => {
      if (!active || !report.collaboration.hasThread || !report.collaboration.threadId) return;
      const threadId = report.collaboration.threadId;
      const snapshot = await readAgentSessionSnapshot(gateway, projectId, threadId, controller.signal);
      if (!active) return;
      if (snapshot.thread.status === "fulfilled") {
        agentThreadRef.current = snapshot.thread.value;
        setAgentThread(snapshot.thread.value);
      }
      if (snapshot.messages.status === "fulfilled") setAgentMessages(snapshot.messages.value);
      if (snapshot.focusEvents.status === "fulfilled") setAgentFocusEvents(snapshot.focusEvents.value);
      const primaryError = agentReadError(snapshot.thread) ?? agentReadError(snapshot.messages);
      setAgentSessionError(primaryError ? `对话同步失败，可继续重试：${primaryError}` : null);
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      if (active) setAgentSessionError(reason instanceof Error ? reason.message : "读取 Agent 会话失败。当前不会回退 synthetic。");
    });
    return () => { active = false; controller.abort(); };
  }, [gateway, projectId]);

  useEffect(() => {
    const activeProjectId = data?.project.id;
    intelligenceRunAbortRef.current?.abort();
    intelligenceRunAbortRef.current = null;
    if (!activeProjectId || !selectedMaterialId) {
      setMaterialIntelligence(null);
      setModelGatewayRuntime(emptyModelGatewayRuntime());
      setMaterialSceneSpec(null);
      setIntelligenceStatus("idle");
      setIntelligenceMessage(null);
      return;
    }
    const requestId = intelligenceRequestRef.current + 1;
    intelligenceRequestRef.current = requestId;
    const controller = new AbortController();
    setMaterialIntelligence(null);
    setModelGatewayRuntime(emptyModelGatewayRuntime());
    setMaterialSceneSpec(null);
    setActiveIntelligenceAnchorId(null);
    setIntelligenceStatus("loading");
    setIntelligenceMessage(null);
    void Promise.allSettled([
      gateway.readMaterialIntelligence(activeProjectId, selectedMaterialId, { signal: controller.signal }),
      gateway.readMaterialSceneSpec(activeProjectId, selectedMaterialId, { signal: controller.signal }),
    ]).then(([intelligenceResult, sceneResult]) => {
      if (intelligenceRequestRef.current !== requestId) return;
      if (intelligenceResult.status === "fulfilled") {
        setMaterialIntelligence(intelligenceResult.value);
        setModelGatewayRuntime(modelGatewayRuntimeFromResult(intelligenceResult.value));
        setIntelligenceStatus("ready");
      } else if (intelligenceResult.reason instanceof WorkbenchGatewayError && intelligenceResult.reason.code === "not_found") {
        setIntelligenceStatus("empty");
        setIntelligenceMessage("当前材料尚无 intelligence 结果；可由人工触发受控合成识别。");
      } else if (!(intelligenceResult.reason instanceof DOMException && intelligenceResult.reason.name === "AbortError")) {
        setIntelligenceStatus("error");
        setIntelligenceMessage(intelligenceResult.reason instanceof Error ? intelligenceResult.reason.message : "读取材料智能结果失败。");
      }
      if (sceneResult.status === "fulfilled") setMaterialSceneSpec(sceneResult.value);
    });
    return () => controller.abort();
  }, [data?.project.id, gateway, selectedMaterialId]);

  useEffect(() => {
    if (!layout) return;
    localStorage.setItem(PERSISTED_LAYOUT_KEY, JSON.stringify(persistedLayoutFrom(layout)));
    localStorage.setItem(PERSISTED_LAYOUT_VERSION_KEY, String(PERSISTED_LAYOUT_VERSION));
  }, [layout]);

  const rules = policyRules;

  if (error) return <div className="full-page-state"><EmptyState detail={error} title="工作台加载失败" /></div>;
  if (!data || !layout) return <div className="full-page-state"><EmptyState detail="正在读取项目数据。" title="加载工作台" /></div>;

  const updateLayout = (change: Partial<LayoutState>) => setLayout((current) => current ? { ...current, ...change } : current);
  const scrollReviewElementIntoView = (target: HTMLElement | null, align: "start" | "center" = "start") => {
    const pane = document.getElementById("review-pane");
    if (!(pane instanceof HTMLElement) || !(target instanceof HTMLElement)) return;
    const paneRect = pane.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const inset = align === "center"
      ? Math.max(0, (pane.clientHeight - targetRect.height) / 2)
      : 44;
    const top = pane.scrollTop + targetRect.top - paneRect.top - inset;
    pane.scrollTo({ top: Math.max(0, top), behavior: "auto" });
  };
  const scrollReviewPaneTo = (elementId: string, align: "start" | "center" = "start") => {
    scrollReviewElementIntoView(document.getElementById(elementId), align);
  };
  const navigateReview = (id: ReviewSectionId) => {
    setActiveReviewId(id);
    if (id !== "risk") {
      updateLayout({ activeDimensionId: id });
      setSelectedReviewTarget(null);
      setEvidenceSelectionGroup(null);
      setEvidenceSelectionResolution(null);
      if (id !== "production") setSelectedReferenceImageId(null);
    } else {
      setSelectedReviewTarget(null);
      setEvidenceSelectionGroup(null);
      setEvidenceSelectionResolution(null);
      setSelectedMaterialId(data.materials.find(isOriginalMaterial)?.id ?? "");
      setSelectedReferenceImageId(null);
    }
    scrollReviewPaneTo(id === "risk" || id === "compliance" ? "review-risk" : `dimension-${id}`);
  };
  const scrollToFact = (factId: string | null) => {
    if (!factId) return;
    setTimeout(() => {
      const target = document.getElementById(`fact-${factId}`)
        ?? Array.from(document.querySelectorAll<HTMLElement>("#review-pane [data-target-id]")).find((item) => item.dataset.targetId === factId)
        ?? null;
      scrollReviewElementIntoView(target, "center");
    }, 0);
  };

  const selectEvidenceGroup = async (target: ReviewEvidenceTarget) => {
    selectionAbortRef.current?.abort();
    const controller = new AbortController();
    selectionAbortRef.current = controller;
    const requestId = selectionRequestRef.current + 1;
    selectionRequestRef.current = requestId;
    const selectionGroup = createEvidenceSelectionGroup(target);
    const primaryTarget = selectionGroup.targets[0] ?? target;
    setSelectedReferenceImageId(null);
    setSelectedReviewTarget(primaryTarget);
    setEvidenceSelectionGroup(selectionGroup);
    setEvidenceSelectionResolution(null);
    setActiveReviewId(primaryTarget.dimensionId);
    updateLayout({ activeDimensionId: primaryTarget.dimensionId });
    try {
      const transportResolution = await gateway.resolveEvidenceSelection(data.project.id, selectionGroup, { signal: controller.signal });
      if (selectionRequestRef.current !== requestId) return;
      const resolution = resolveEvidenceSelectionGroup(selectionGroup, transportResolution.items.map((item) => item.evidence), data.materials);
      setEvidenceSelectionResolution(resolution);
      setSelectedMaterialId(resolution.status === "located" ? resolution.items[0]?.material.id ?? "" : "");
      setMaterialRecovery(materialRecoverySucceeded());
      scrollToFact(primaryTarget.reviewTargetId);
    } catch (reason) {
      if (selectionRequestRef.current !== requestId) return;
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setEvidenceSelectionResolution(null);
      setSelectedMaterialId("");
      setMaterialRecovery(materialRecoveryFailed(reason instanceof Error ? reason.message : "证据定位失败；请重试当前证据定位。", { kind: "evidence", target }));
    }
  };

  const activateSelectedEvidence = (target: ReviewEvidenceTarget | null = selectedReviewTarget) => scrollToFact(target?.reviewTargetId ?? null);

  const refreshP5Authority = async () => {
    const activeId = data.project.id;
    const [project, materials, reviewEvents, policies, approval] = await Promise.all([
      gateway.loadProject(activeId),
      gateway.listMaterials(activeId),
      gateway.readReviewEvents(activeId),
      gateway.readPolicyResults(activeId),
      gateway.readApprovalState(activeId),
    ]);
    if (activeProjectRef.current !== activeId) return;
    setData(presentationCopy({ ...project, materials }));
    setFacts(latestFactVersionsByFactKey(project.facts));
    setEvents(presentationCopy(authoritativeEvents(reviewEvents)));
    setConfirmedCandidateIds(confirmedCandidateIdsFromEvents(reviewEvents));
    setPolicyRules(presentationCopy(policies));
    setApprovalState(approval);
    setOpenIssueCount(project.project.collaborationIssueCount);
  };

  const onImportMaterialPackage = async (file: File): Promise<{ receipt: MaterialUploadReceipt; preflight: MaterialImportPreflight }> => {
    const activeId = data.project.id;
    const receipt = await gateway.uploadMaterialPackage(activeId, file);
    const preflight = await gateway.preflightMaterialImport(activeId, receipt.manifestRef);
    if (activeProjectRef.current !== activeId) throw new WorkbenchGatewayError("conflict", "当前项目已切换，请重新选择材料包。");
    return { receipt, preflight };
  };

  const onConfirmMaterialImport = async (preflight: MaterialImportPreflight) => {
    const activeId = data.project.id;
    if (preflight.projectId !== activeId) throw new WorkbenchGatewayError("validation", "材料预检不属于当前项目，请重新上传。");
    const operation = `material-import:${activeId}:${preflight.manifestRef}:${preflight.projectVersion}`;
    const payload = { manifestRef: preflight.manifestRef, projectVersion: preflight.projectVersion };
    const result = await gateway.executeMaterialImport(activeId, preflight.manifestRef, preflight.projectVersion, idempotencyKey(operation, payload, writeKeysRef.current));
    if (activeProjectRef.current !== activeId) return result;
    clearIdempotencyKey(operation, writeKeysRef.current);
    await refreshP5Authority();
    return result;
  };

  const runSelectedMaterialIntelligence = async () => {
    const material = data.materials.find((item) => item.id === selectedMaterialId);
    if (!material || material.kind === "scene") return;
    const expectedVersion = materialVersionNumber(material.versionId);
    const taskGoals = ["observe", "extract_field_candidates", "identify_unresolved"] as const;
    const shouldCreateScene = (material.kind === "image" || material.kind === "media") && /production-site|equipment-line|process/i.test(material.id);
    const input = {
      projectId: data.project.id,
      materialId: material.id,
      materialVersionId: material.versionId,
      contextVersion: "p5-front-mvp-v1",
      taskGoals: [...taskGoals, ...(shouldCreateScene ? ["scene_spec" as const] : [])],
      expectedVersion,
    };
    const operation = `material-intelligence:${data.project.id}:${material.id}`;
    const controller = new AbortController();
    intelligenceRunAbortRef.current?.abort();
    intelligenceRunAbortRef.current = controller;
    const startedAt = performance.now();
    setIntelligenceStatus("loading");
    setModelGatewayRuntime({ runId: null, provider: null, status: "running", latencyMs: null, inputHash: null, error: null, retryable: false, advisoryOnly: true });
    setIntelligenceMessage("人工动作已提交，正在等待 Model Gateway；结果仍是 advisory candidate。");
    try {
      const stored = await gateway.runMaterialIntelligence({ ...input, idempotencyKey: idempotencyKey(operation, input, writeKeysRef.current) }, { signal: controller.signal });
      if (activeProjectRef.current !== data.project.id) return;
      clearIdempotencyKey(operation, writeKeysRef.current);
      setMaterialIntelligence(stored);
      setModelGatewayRuntime(modelGatewayRuntimeFromResult(stored, Math.max(0, Math.round(performance.now() - startedAt))));
      setIntelligenceStatus("ready");
      setIntelligenceMessage("已生成可溯源辅助候选；尚未写入权威事实。");
      await refreshP5Authority();
      try { setMaterialSceneSpec(await gateway.readMaterialSceneSpec(data.project.id, material.id)); } catch (reason) {
        if (!(reason instanceof WorkbenchGatewayError && reason.code === "not_found")) throw reason;
        setMaterialSceneSpec(null);
      }
    } catch (reason) {
      if (activeProjectRef.current !== data.project.id) return;
      clearIdempotencyKey(operation, writeKeysRef.current);
      const latencyMs = Math.max(0, Math.round(performance.now() - startedAt));
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setIntelligenceStatus("idle");
        setModelGatewayRuntime((current) => cancelledModelGatewayRuntime(latencyMs, current));
        setIntelligenceMessage("本次 Model Gateway 运行已取消；没有候选写入权威事实。");
        return;
      }
      setIntelligenceStatus("error");
      setModelGatewayRuntime((current) => failedModelGatewayRuntime(reason, latencyMs, current));
      setIntelligenceMessage(reason instanceof Error ? reason.message : "材料智能运行失败。");
    } finally {
      if (intelligenceRunAbortRef.current === controller) intelligenceRunAbortRef.current = null;
    }
  };

  const cancelSelectedMaterialIntelligence = () => intelligenceRunAbortRef.current?.abort();

  const confirmCandidate = async (candidate: ExtractedFieldCandidate, reason: string) => {
    const source = facts.find((fact) => fact.factKey === candidate.fieldKey);
    if (!source || confirmingCandidateId) {
      setIntelligenceMessage(source ? "已有候选正在确认。" : "候选缺少当前权威 FactVersion，已停止确认。");
      return;
    }
    const input = { projectId: data.project.id, candidateId: candidate.id, fromFactVersionId: source.id, expectedVersion: source.version, reason, proposedValue: candidate.value };
    const operation = `candidate-confirm:${data.project.id}:${candidate.id}`;
    setConfirmingCandidateId(candidate.id);
    setIntelligenceMessage("正在执行明确的人工确认；候选本身不会自动写入。");
    try {
      const result = await gateway.confirmMaterialCandidate({ ...input, idempotencyKey: idempotencyKey(operation, input, writeKeysRef.current) });
      if (activeProjectRef.current !== data.project.id) return;
      clearIdempotencyKey(operation, writeKeysRef.current);
      setFacts((items) => [result.factVersion, ...items.filter((item) => item.factKey !== result.factVersion.factKey)]);
      setEvents((items) => authoritativeEvents([...items, result.event]));
      setPolicyRules(result.policyResults);
      setApprovalState(result.approval);
      setConfirmedCandidateIds((items) => new Set(items).add(candidate.id));
      setIntelligenceMessage(`人工确认完成：服务端 FactVersion v${result.factVersion.version}、制度结果与审批状态已刷新。`);
      await refreshP5Authority();
    } catch (reason) {
      if (activeProjectRef.current !== data.project.id) return;
      setIntelligenceMessage(reason instanceof Error ? reason.message : "候选人工确认失败。");
      if (reason instanceof WorkbenchGatewayError && reason.apiCode === "version_conflict") await refreshP5Authority();
    } finally {
      if (activeProjectRef.current === data.project.id) setConfirmingCandidateId(null);
    }
  };

  const activateIntelligenceAnchor = (sourceAnchorId: string) => {
    const stored = materialIntelligence;
    if (!stored) return;
    const anchor = stored.result.sourceAnchors.find((item) => item.id === sourceAnchorId);
    const evidenceRef = evidenceRefForSourceAnchor(sourceAnchorId);
    if (!anchor || !stored.evidenceRefs.includes(evidenceRef)) {
      setIntelligenceMessage("该 SourceAnchor 尚无可解析 evidence locator，保持 pending。");
      return;
    }
    const candidate = stored.result.extractedFieldCandidates.find((item) => item.sourceAnchorIds.includes(sourceAnchorId));
    const fact = candidate ? facts.find((item) => item.factKey === candidate.fieldKey) : null;
    setActiveIntelligenceAnchorId(sourceAnchorId);
    void selectEvidenceGroup({ evidenceRef, evidenceRefs: [evidenceRef], dimensionId: fact?.dimensionId ?? layout.activeDimensionId, reviewTargetId: candidate?.fieldKey ?? sourceAnchorId, factVersionId: null });
  };

  const submitCorrection = async (factId: string, value: string, reason: string) => {
    const current = facts.find((fact) => fact.id === factId);
    if (!current) return;
    setCorrectionPending(true);
    setCorrectionMessage(null);
    try {
      const input = {
        projectId: data.project.id,
        factKey: current.factKey,
        fromFactVersionId: current.id,
        proposedValue: parseEditedValue(current.value, value),
        reason,
        evidenceRefs: [...current.evidenceRefs],
        expectedVersion: current.version,
      };
      const operation = `correction:${data.project.id}:${current.factKey}`;
      const result = await gateway.submitBusinessCorrection({ ...input, idempotencyKey: idempotencyKey(operation, input, writeKeysRef.current) });
      if (activeProjectRef.current !== data.project.id) return;
      clearIdempotencyKey(operation, writeKeysRef.current);
      setFacts((items) => [result.factVersion, ...items.filter((item) => item.factKey !== result.factVersion.factKey)]);
      const mappedEvent = authoritativeEvents([result.event])[0];
      setEvents((items) => authoritativeEvents([...items, result.event]));
      const correctionTarget = mappedEvent?.evidenceTargets[0]
        ? { ...mappedEvent.evidenceTargets[0], evidenceRefs: mappedEvent.evidenceTargets.flatMap((target) => target.evidenceRefs ?? [target.evidenceRef]) }
        : null;
      setSelectedReviewTarget(correctionTarget);
      setEvidenceSelectionGroup(correctionTarget ? createEvidenceSelectionGroup(correctionTarget) : null);
      setEvidenceSelectionResolution(null);
      setCorrectionMessage(`已生成服务端事实版本 ${result.factVersion.version}，并写入共同审查链。`);
      try {
        const [project, reviewEvents, policies, approval] = await Promise.all([gateway.loadProject(data.project.id), gateway.readReviewEvents(data.project.id), gateway.readPolicyResults(data.project.id), gateway.readApprovalState(data.project.id)]);
        if (activeProjectRef.current !== data.project.id) return;
        setFacts(latestFactVersionsByFactKey(project.facts));
        setEvents(authoritativeEvents(reviewEvents));
        setPolicyRules(policies);
        setApprovalState(approval);
        setOpenIssueCount(project.project.collaborationIssueCount);
      } catch {
        if (activeProjectRef.current === data.project.id) setCorrectionMessage("修正已成功、权威状态刷新失败");
      }
    } catch (reasonValue) {
      if (activeProjectRef.current !== data.project.id) return;
      const detail = reasonValue instanceof Error ? reasonValue.message : "业务修正提交失败";
      const apiCode = reasonValue instanceof WorkbenchGatewayError ? reasonValue.apiCode : undefined;
      setCorrectionMessage(apiCode === "version_conflict" ? `${detail} 已重新读取权威项目状态。` : detail);
      if (apiCode === "version_conflict") {
        void Promise.all([gateway.loadProject(data.project.id), gateway.readReviewEvents(data.project.id), gateway.readPolicyResults(data.project.id), gateway.readApprovalState(data.project.id)]).then(([project, reviewEvents, policies, approval]) => {
          if (activeProjectRef.current !== data.project.id) return;
          setFacts(latestFactVersionsByFactKey(project.facts)); setEvents(authoritativeEvents(reviewEvents)); setPolicyRules(policies); setApprovalState(approval); setOpenIssueCount(project.project.collaborationIssueCount);
        }).catch(() => { if (activeProjectRef.current === data.project.id) setCorrectionMessage("版本冲突，且权威状态刷新失败"); });
      }
    } finally {
      if (activeProjectRef.current === data.project.id) setCorrectionPending(false);
    }
  };

  const currentComplianceFacts = facts.filter((fact) => fact.dimensionId === "compliance");
  const sharedTargets = evidenceSelectionGroup?.dimensionId === layout.activeDimensionId
    ? evidenceSelectionGroup.targets
    : selectedReviewTarget?.dimensionId === layout.activeDimensionId ? [selectedReviewTarget] : [];
  const rememberAgentThread = (thread: AgentThread) => {
    agentThreadRef.current = thread;
    setAgentThread(thread);
    return thread;
  };
  const refreshAgentSession = async (threadId: string) => {
    const projectAtRequest = data.project.id;
    const snapshot = await readAgentSessionSnapshot(gateway, projectAtRequest, threadId);
    if (activeProjectRef.current !== projectAtRequest) return;
    if (snapshot.thread.status === "fulfilled") rememberAgentThread(snapshot.thread.value);
    if (snapshot.messages.status === "fulfilled") setAgentMessages(snapshot.messages.value);
    if (snapshot.focusEvents.status === "fulfilled") setAgentFocusEvents(snapshot.focusEvents.value);
    const primaryError = agentReadError(snapshot.thread) ?? agentReadError(snapshot.messages);
    if (primaryError) throw new Error(primaryError);
    setAgentSessionError(null);
  };
  const ensureAgentThread = async () => {
    const current = agentThreadRef.current;
    if (current?.projectId === data.project.id && current.status === "active") return current;
    if (agentThreadCreationRef.current) return agentThreadCreationRef.current;
    const creation = (async () => {
      const report = await gateway.readConclusionReport(data.project.id);
      if (report.collaboration.hasThread && report.collaboration.threadId) {
        const existing = await gateway.readAgentThread(data.project.id, report.collaboration.threadId, "business");
        if (existing.status === "active") return rememberAgentThread(existing);
      }
      const payload = { projectId: data.project.id, title: "项目单焦点协作会话", principal: "business" as const };
      const operation = `agent-thread:create:${data.project.id}`;
      try {
        const created = await gateway.createAgentThread({ ...payload, idempotencyKey: idempotencyKey(operation, payload, writeKeysRef.current) });
        clearIdempotencyKey(operation, writeKeysRef.current);
        return rememberAgentThread(created);
      } catch (reason) {
        clearIdempotencyKey(operation, writeKeysRef.current);
        throw reason;
      }
    })();
    agentThreadCreationRef.current = creation;
    try {
      return await creation;
    } finally {
      agentThreadCreationRef.current = null;
    }
  };
  const prepareAgentFocus = async (role: AgentRole) => {
    let thread = await ensureAgentThread();
    while (thread.focusRole !== role) {
      const toFocusRole: AgentRole = thread.focusRole === "business" ? role : "business";
      const payload = { projectId: data.project.id, threadId: thread.id, principal: thread.focusRole, toFocusRole, expectedVersion: thread.version, reason: toFocusRole === "business" ? "用户返回业务主对话。" : "用户请求风控短暂复核。" };
      const operation = `agent-focus:${thread.id}:${thread.focusRole}:${toFocusRole}`;
      try {
        thread = rememberAgentThread(await gateway.transitionAgentFocus({ ...payload, idempotencyKey: idempotencyKey(operation, payload, writeKeysRef.current) }));
        clearIdempotencyKey(operation, writeKeysRef.current);
      } catch (reason) {
        clearIdempotencyKey(operation, writeKeysRef.current);
        throw reason;
      }
    }
    return thread;
  };
  const agentSubmissionContext = (reference: CollaborationContextReference | null) => {
    const referencedMessage = reference?.kind === "agent_message" ? agentMessages.find((message) => message.id === reference.id) : undefined;
    const referencedEvent = reference?.kind === "review_event" ? events.find((event) => event.id === reference.id) : undefined;
    const targets = referencedMessage?.citations.map((citation) => ({ ...citation, evidenceRefs: [citation.evidenceRef] }))
      ?? referencedEvent?.evidenceTargets
      ?? sharedTargets;
    const uniqueTargets = [...new Map(targets.map((target) => [`${target.evidenceRef}|${target.dimensionId}|${target.reviewTargetId ?? ""}|${target.factVersionId ?? ""}`, target])).values()];
    return { evidenceTargets: uniqueTargets, replyToMessageId: referencedMessage?.id ?? null };
  };
  const submitAgent = async (role: AgentRole, message: string, reference: CollaborationContextReference | null) => {
    setAgentSessionError(null);
    let thread: AgentThread;
    try {
      thread = await prepareAgentFocus(role);
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Agent 焦点准备失败。";
      setAgentSessionError(detail);
      throw reason;
    }
    const context = agentSubmissionContext(reference);
    const payload = { projectId: data.project.id, threadId: thread.id, principal: role, instruction: message, ...context, expectedVersion: thread.version, locale: "zh-CN" as const };
    const operation = `agent-turn:${thread.id}:${role}`;
    try {
      const result = await gateway.executeAgentTurn({ ...payload, idempotencyKey: idempotencyKey(operation, payload, writeKeysRef.current) });
      clearIdempotencyKey(operation, writeKeysRef.current);
      rememberAgentThread({ ...thread, version: result.nextExpectedVersion, focusRole: result.currentFocusRole, updatedAt: new Date().toISOString() });
      try {
        await refreshAgentSession(thread.id);
      } catch (refreshReason) {
        setAgentMessages((items) => [...items, ...result.messages].sort((left, right) => left.createdAt.localeCompare(right.createdAt) || left.sequence - right.sequence));
        setAgentSessionError(refreshReason instanceof Error ? `Agent 已回复，但会话刷新失败：${refreshReason.message}` : "Agent 已回复，但会话刷新失败。");
      }
    } catch (reason) {
      clearIdempotencyKey(operation, writeKeysRef.current);
      const detail = reason instanceof Error ? reason.message : "真实 Agent run failed。";
      setAgentSessionError(detail);
      throw reason;
    }
  };
  const submitBusiness = (message: string, reference: CollaborationContextReference | null) => submitAgent("business", message, reference);
  const submitLeadership = (message: string, reference: CollaborationContextReference | null) => submitAgent("leadership", message, reference);
  const submitRisk = (message: string, reference: CollaborationContextReference | null) => submitAgent("risk", message, reference);
  const loadConclusionReport = async () => {
    const projectAtRequest = data.project.id;
    setConclusionStatus("loading");
    setConclusionError(null);
    try {
      const report = await gateway.readConclusionReport(projectAtRequest);
      if (activeProjectRef.current !== projectAtRequest) return;
      setConclusionReport(report);
      setConclusionStatus("ready");
    } catch (reason) {
      if (activeProjectRef.current !== projectAtRequest) return;
      setConclusionStatus("error");
      setConclusionError(reason instanceof Error ? reason.message : "结论报告读取失败");
    }
  };
  const openConclusionReport = () => {
    setConclusionOpen(true);
    void loadConclusionReport();
  };
  const transitionApproval = async (transition: ApprovalTransition) => {
    if (!approvalState || approvalPending) return;
    setApprovalPending(true);
    setApprovalMessage(null);
    const input = { expectedVersion: approvalState.version, transition, requestedBy: transition === "complete" ? "leadership" as const : "risk" as const };
    try {
      const operation = `approval:${data.project.id}`;
      const next = await gateway.transitionApproval(data.project.id, { ...input, idempotencyKey: idempotencyKey(operation, input, writeKeysRef.current) });
      if (activeProjectRef.current !== data.project.id) return;
      clearIdempotencyKey(operation, writeKeysRef.current);
      setApprovalState(next);
    } catch (reasonValue) {
      if (activeProjectRef.current !== data.project.id) return;
      const apiError = reasonValue instanceof WorkbenchGatewayError ? reasonValue : undefined;
      const blockedRules = apiError?.apiCode === "hard_gate_blocked" ? apiError.details?.blockingRuleIds : null;
      setApprovalMessage(blockedRules ? `${reasonValue instanceof Error ? reasonValue.message : "审批被阻断"}：${Array.isArray(blockedRules) ? blockedRules.join("、") : ""}` : reasonValue instanceof Error ? reasonValue.message : "审批写入失败");
      if (apiError?.apiCode === "version_conflict" || apiError?.apiCode === "hard_gate_blocked") {
        void gateway.readApprovalState(data.project.id).then(setApprovalState);
      }
    } finally { if (activeProjectRef.current === data.project.id) setApprovalPending(false); }
  };
  const handleMaterialSelect = (materialId: string) => {
    materialAbortRef.current?.abort();
    const controller = new AbortController();
    materialAbortRef.current = controller;
    const requestId = materialRequestRef.current + 1;
    materialRequestRef.current = requestId;
    setSelectedReferenceImageId(null);
    void gateway.readMaterial(data.project.id, materialId, { signal: controller.signal }).then((material) => {
      if (materialRequestRef.current !== requestId) return;
      setData((current) => current ? { ...current, materials: current.materials.map((item) => item.id === material.id ? material : item) } : current);
      setSelectedMaterialId(material.id);
      setMaterialRecovery(materialRecoverySucceeded());
    }).catch((reason: unknown) => {
      if (materialRequestRef.current !== requestId) return;
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setMaterialRecovery(materialRecoveryFailed(reason instanceof Error ? reason.message : "读取材料失败；请重新选择该材料。", { kind: "material", materialId }));
    });
  };

  const handleProductionStageSelect = (stageId: string, imageId: string) => {
    setSelectedProductionStageId(stageId);
    setSelectedReferenceImageId(null);
    const original = data.materials.find((material) => material.id === imageId && material.kind !== "scene" && material.role !== "derived");
    if (original) handleMaterialSelect(original.id);
    setSelectedReviewTarget(null);
    setEvidenceSelectionGroup(null);
    setEvidenceSelectionResolution(null);
    setActiveReviewId("production");
    updateLayout({ activeDimensionId: "production" });
  };

  const retryMaterialRecovery = () => {
    replayMaterialRecovery(materialRecovery, {
      material: handleMaterialSelect,
      evidence: (target) => { void selectEvidenceGroup(target); },
    });
  };

  const beginResize = (axis: ResizeAxis, event: ReactPointerEvent<HTMLDivElement>) => {
    const divider = event.currentTarget;
    const workbench = divider.closest<HTMLElement>(".workbench-app");
    const body = divider.closest<HTMLElement>(".workbench-body");
    if (!workbench || !body) return;
    const pointerId = event.pointerId;
    divider.setPointerCapture(pointerId);
    const [minimum, maximum] = axis === "material" ? LAYOUT_LIMITS.materialWidth : LAYOUT_LIMITS.collaborationHeight;
    const property = axis === "material" ? "--layout-material-width" : "--layout-collaboration-height";
    let nextValue = axis === "material" ? layout.materialWidth : layout.collaborationHeight;
    let nextEdge: MaterialEdge | CollaborationEdge = axis === "material" ? materialEdge : collaborationEdge;
    let frameId: number | null = null;
    const applyResize = () => {
      frameId = null;
      workbench.style.setProperty(property, `${nextValue}px`);
      if (axis === "material") body.dataset.materialEdge = nextEdge ?? "none";
      else body.dataset.collaborationEdge = nextEdge ?? "none";
      divider.setAttribute("aria-valuenow", nextEdge === "review" ? "0" : nextEdge === (axis === "material" ? "material" : "collaboration") ? "100" : String(Math.round((nextValue / maximum) * 100)));
    };
    const move = (pointerEvent: PointerEvent) => {
      if (pointerEvent.pointerId !== pointerId) return;
      const bodyRect = body.getBoundingClientRect();
      const navigationRight = body.querySelector<HTMLElement>(".navigation-rail")?.getBoundingClientRect().right ?? bodyRect.left;
      if (axis === "material") {
        if (pointerEvent.clientX >= bodyRect.right - DIVIDER_SNAP_THRESHOLD) {
          nextEdge = "review";
        } else if (pointerEvent.clientX <= navigationRight + DIVIDER_SNAP_THRESHOLD) {
          nextEdge = "material";
        } else {
          nextEdge = null;
          const readableMaximum = Math.min(maximum, Math.max(minimum, bodyRect.right - navigationRight - 420 - 8));
          nextValue = clamp(bodyRect.right - pointerEvent.clientX, minimum, readableMaximum);
        }
      } else if (pointerEvent.clientY >= bodyRect.bottom - DIVIDER_SNAP_THRESHOLD) {
        nextEdge = "review";
      } else if (pointerEvent.clientY <= bodyRect.top + DIVIDER_SNAP_THRESHOLD) {
        nextEdge = "collaboration";
      } else {
        nextEdge = null;
        const readableMaximum = Math.min(maximum, Math.max(minimum, bodyRect.height - 220 - 8));
        nextValue = clamp(bodyRect.bottom - pointerEvent.clientY, minimum, readableMaximum);
      }
      if (frameId === null) frameId = window.requestAnimationFrame(applyResize);
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
      if (frameId !== null) window.cancelAnimationFrame(frameId);
      applyResize();
      if (axis === "material") {
        setMaterialEdge(nextEdge as MaterialEdge);
        if (!nextEdge) updateLayout({ materialWidth: nextValue });
      } else {
        setCollaborationEdge(nextEdge as CollaborationEdge);
        if (!nextEdge) updateLayout({ collaborationHeight: nextValue });
      }
      cleanup();
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
  };

  const resizeWithKeyboard = (axis: ResizeAxis, event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const step = event.shiftKey ? 32 : 12;
    if (axis === "material") {
      if (event.key === "Home") { setMaterialEdge("review"); return; }
      if (event.key === "End") { setMaterialEdge("material"); return; }
      const direction = event.key === "ArrowLeft" ? 1 : event.key === "ArrowRight" ? -1 : 0;
      if (!direction) return;
      setMaterialEdge(null);
      updateLayout({ materialWidth: clamp((materialEdge ? data.layout.materialWidth : layout.materialWidth) + direction * step, ...LAYOUT_LIMITS.materialWidth) });
    } else {
      if (event.key === "Home") { setCollaborationEdge("review"); return; }
      if (event.key === "End") { setCollaborationEdge("collaboration"); return; }
      const direction = event.key === "ArrowUp" ? 1 : event.key === "ArrowDown" ? -1 : 0;
      if (!direction) return;
      setCollaborationEdge(null);
      updateLayout({ collaborationHeight: clamp((collaborationEdge ? data.layout.collaborationHeight : layout.collaborationHeight) + direction * step, ...LAYOUT_LIMITS.collaborationHeight) });
    }
  };

  const materialAriaValue = materialEdge === "review" ? 0 : materialEdge === "material" ? 100 : Math.round((layout.materialWidth / LAYOUT_LIMITS.materialWidth[1]) * 100);
  const collaborationAriaValue = collaborationEdge === "review" ? 0 : collaborationEdge === "collaboration" ? 100 : Math.round((layout.collaborationHeight / LAYOUT_LIMITS.collaborationHeight[1]) * 100);

  const style = {
    "--layout-navigation-width": `${layout.navigationCollapsed ? 64 : layout.navigationWidth}px`,
    "--layout-material-width": `${layout.materialWidth}px`,
    "--layout-collaboration-height": `${layout.collaborationHeight}px`,
  } as CSSProperties;

  return (
    <div className="workbench-app" data-semantic-localized="true" style={style}>
      <TopBar approval={approvalState} approvalMessage={approvalMessage} approvalPending={approvalPending} hardConstraintCount={rules.length} locale={locale} onApprovalTransition={transitionApproval} onBack={onBack} onLocaleChange={onLocaleChange} onOpenConclusionReport={openConclusionReport} onResetLayout={() => { setLayout({ ...data.layout }); setMaterialEdge(null); setCollaborationEdge(null); setLayoutResetVersion((value) => value + 1); setActiveReviewId("risk"); }} policyHitCount={rules.filter((rule) => rule.result !== "pass").length} project={{ ...data.project, collaborationIssueCount: openIssueCount }} projectNo={projectNo} />
      <div className={`workbench-body ${layout.middleCollapsed ? "is-middle-collapsed" : ""} ${layout.materialCollapsed ? "is-material-collapsed" : ""} ${layout.collaborationCollapsed ? "is-collaboration-collapsed" : ""}`} data-collaboration-edge={collaborationEdge ?? "none"} data-material-edge={materialEdge ?? "none"}>
        <NavigationRail activeId={layout.activeDimensionId} collapsed={layout.navigationCollapsed} dimensions={data.dimensions} onNavigate={navigateReview} onOverview={() => navigateReview("risk")} onRiskNavigate={() => navigateReview("risk")} onToggleCollapsed={() => updateLayout({ navigationCollapsed: !layout.navigationCollapsed })} riskActive={activeReviewId === "risk"} riskItemCount={riskItemCount(data.riskSummary)} />
        <ReviewCanvas activeReviewId={activeReviewId} collapsed={layout.middleCollapsed} data={data} facts={facts} onActiveReviewChange={(id) => { setActiveReviewId(id); if (id !== "risk") updateLayout({ activeDimensionId: id }); }} onEvidenceSelect={(target) => void selectEvidenceGroup(target)} onProductionStageSelect={handleProductionStageSelect} onTimeSeriesRequest={(request) => gateway.queryDimensionSeries(request)} onToggleCollapsed={() => { setMaterialEdge(null); updateLayout({ middleCollapsed: !layout.middleCollapsed }); }} selectedProductionStageId={selectedProductionStageId} selectedTarget={selectedReviewTarget} />
        {!layout.middleCollapsed && !layout.materialCollapsed ? <div aria-label={copy(locale, "Resize the review and original-material areas", "调整中间与材料区域宽度")} aria-orientation="vertical" aria-valuemax={100} aria-valuemin={0} aria-valuenow={materialAriaValue} aria-valuetext={materialEdge === "review" ? copy(locale, "Review area fills the workspace", "审查区域占满") : materialEdge === "material" ? copy(locale, "Original materials fill the workspace", "原始材料占满") : copy(locale, `Original-material width: ${layout.materialWidth} pixels`, `原始材料宽度 ${layout.materialWidth} 像素`)} className="layout-divider divider-vertical" onKeyDown={(event) => resizeWithKeyboard("material", event)} onPointerDown={(event) => beginResize("material", event)} role="separator" tabIndex={0} /> : null}
        <MaterialPane activeIntelligenceAnchorId={activeIntelligenceAnchorId} collapsed={layout.materialCollapsed} confirmedCandidateIds={confirmedCandidateIds} confirmingCandidateId={confirmingCandidateId} errorMessage={materialRecovery.error} evidence={data.evidence} evidenceSelectionResolution={evidenceSelectionResolution} facts={facts} intelligence={materialIntelligence} intelligenceMessage={intelligenceMessage} intelligenceStatus={intelligenceStatus} locale={locale} materials={data.materials} modelGatewayRuntime={modelGatewayRuntime} onCancelIntelligence={cancelSelectedMaterialIntelligence} onConfirmCandidate={(candidate, reason) => void confirmCandidate(candidate, reason)} onEvidenceActivate={activateSelectedEvidence} onIntelligenceAnchorActivate={activateIntelligenceAnchor} onMaterialSelect={handleMaterialSelect} onRetry={retryMaterialRecovery} onRunIntelligence={() => void runSelectedMaterialIntelligence()} onToggleCollapsed={() => { setMaterialEdge(null); updateLayout({ materialCollapsed: !layout.materialCollapsed }); }} sceneSpec={materialSceneSpec} selectedMaterialId={selectedMaterialId} selectionGroup={evidenceSelectionGroup} />
        {!layout.collaborationCollapsed && !(layout.middleCollapsed && layout.materialCollapsed) ? <div aria-label={copy(locale, "Resize the collaboration workspace", "调整协同工作台高度")} aria-orientation="horizontal" aria-valuemax={100} aria-valuemin={0} aria-valuenow={collaborationAriaValue} aria-valuetext={collaborationEdge === "review" ? copy(locale, "Review area fills the workspace", "审查区域占满") : collaborationEdge === "collaboration" ? copy(locale, "Approval collaboration fills the workspace", "审批协同占满") : copy(locale, `Approval-collaboration height: ${layout.collaborationHeight} pixels`, `审批协同高度 ${layout.collaborationHeight} 像素`)} className="layout-divider divider-horizontal" onKeyDown={(event) => resizeWithKeyboard("collaboration", event)} onPointerDown={(event) => beginResize("collaboration", event)} role="separator" tabIndex={0} /> : null}
        <CollaborationDock agentError={agentSessionError} agentFocusEvents={agentFocusEvents} agentMessages={agentMessages} agentThread={agentThread} approval={approvalState} businessCollapsed={layout.businessCollapsed} collapsed={layout.collaborationCollapsed} correctionMessage={correctionMessage} correctionPending={correctionPending} dimensions={data.dimensions} events={events} evidence={data.evidence} facts={currentComplianceFacts} layoutResetVersion={layoutResetVersion} onAgentEvidenceActivate={(target) => { void selectEvidenceGroup(target); }} onConfirmMaterialImport={onConfirmMaterialImport} onCorrection={submitCorrection} onImportMaterialPackage={onImportMaterialPackage} onSubmitBusiness={submitBusiness} onSubmitLeadership={submitLeadership} onSubmitRisk={submitRisk} onToggleBusiness={() => updateLayout({ businessCollapsed: !layout.businessCollapsed })} onToggleCollapsed={() => { setCollaborationEdge(null); updateLayout({ collaborationCollapsed: !layout.collaborationCollapsed }); }} onTogglePolicy={() => updateLayout({ policyCollapsed: !layout.policyCollapsed })} onToggleRisk={() => updateLayout({ riskCollapsed: !layout.riskCollapsed })} policyCollapsed={layout.policyCollapsed} riskCollapsed={layout.riskCollapsed} rules={rules} selectedTarget={selectedReviewTarget} showSimulationControls={showSimulationControls} />
      </div>
      {conclusionOpen ? <FinalConclusionReport error={conclusionError} onClose={() => setConclusionOpen(false)} onRefresh={() => void loadConclusionReport()} report={conclusionReport} status={conclusionStatus} /> : null}
    </div>
  );
}
