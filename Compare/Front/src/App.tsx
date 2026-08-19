import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type {
  CommonReviewEvent,
  ApprovalState,
  ApprovalTransition,
  FactValue,
  FactVersion,
  HardConstraintResult,
  MappedCommonReviewEvent,
  ReviewEvidenceSelectionGroup,
  ReviewEvidenceTarget,
  WorkbenchProject,
} from "./contracts/workbench";
import { evidenceRefForSourceAnchor, type ExtractedFieldCandidate, type MaterialImportPreflight, type MaterialUploadReceipt, type StoredMaterialIntelligence, type StoredSceneSpec } from "./contracts/materialIntelligence";
import { WorkbenchGatewayError, type WorkbenchGateway } from "./gateway/workbenchGateway";
import type { ModelGatewayRuntimeState } from "./contracts/modelGateway";
import type { ProjectConclusionReport } from "./contracts/conclusion";
import type { AgentActivityState, AgentFocusEvent, AgentMessage, AgentResponsePreferences, AgentRole, AgentThread, ChatAgentRole, CollaborationContextReference } from "./contracts/agentCommunication";
import { cancelledModelGatewayRuntime, emptyModelGatewayRuntime, failedModelGatewayRuntime, modelGatewayRuntimeFromResult } from "./lib/modelGatewayState";
import {
  attachReviewEvidenceTargets,
  clamp,
  displayBusinessText,
  deriveScoreSummary,
  DEFAULT_LAYOUT_RATIOS,
  LAYOUT_LIMITS,
  PRESENTATION_LAYOUT_RATIOS,
  createEvidenceSelectionGroup,
  persistedLayoutFrom,
  PERSISTED_LAYOUT_KEY,
  riskItemCount,
  resolveEvidenceSelectionGroup,
  sanitizePersistedLayout,
  snapLayoutRatio,
  scoreToGrade,
  type EvidenceSelectionResolution,
  type ResponsiveLayoutState,
} from "./lib/workbenchLogic";
import { MaterialPane } from "./components/MaterialPane";
import { NavigationRail } from "./components/NavigationRail";
import { ReviewCanvas, type ReviewSectionId } from "./components/ReviewCanvas";
import { TopBar } from "./components/TopBar";
import { FinalConclusionReport } from "./components/FinalConclusionReport";
import { EmptyState } from "./components/ui";
import { initialMaterialLoadFailed, materialRecoveryFailed, materialRecoverySucceeded, replayMaterialRecovery, retryOnceAfterVersionConflict } from "./lib/recoveryState";
import { isOriginalMaterial } from "./lib/materialBusinessFolders";
import { copy, type PublicLocale } from "./lib/publicLocale";
import type { AccountRole, AuthenticatedAccount } from "./contracts/authentication";
import type { PreReviewDemoState } from "./contracts/preReviewDemo";
import { createPreReviewDemoState, rerunPreReviewDemo, submitPreReviewDemo } from "./mock/preReviewDemo";
import { PreReviewActionBar, PreReviewSummaryBar } from "./components/PreReviewSummaryBar";
import "./styles/pre-review.css";

const PERSISTED_LAYOUT_VERSION = 3;
const PERSISTED_LAYOUT_VERSION_KEY = `${PERSISTED_LAYOUT_KEY}-schema`;
const PERSISTED_PRESENTATION_LAYOUT_KEY = "compare-front-presentation-layout-v2";

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

export function App({ gateway, projectId, projectNo, onBack, account, onLogout, onPrincipalRoleChange, principalRoleChangePending = false, showSimulationControls = false, locale = "en", onLocaleChange, presentationMode = false }: { gateway: WorkbenchGateway; projectId: string; projectNo: string; onBack: () => void; account: AuthenticatedAccount; onLogout: () => void; onPrincipalRoleChange: (role: Extract<AccountRole, "business" | "risk">) => void; principalRoleChangePending?: boolean; showSimulationControls?: boolean; locale?: PublicLocale; onLocaleChange?: (locale: PublicLocale) => void; presentationMode?: boolean }) {
  // 正式工作台只在服务端预审状态接通后展示判断条；展示包才允许使用显式 mock。
  const preReviewEnabled = showSimulationControls;
  const [data, setData] = useState<WorkbenchProject | null>(null);
  const [layout, setLayout] = useState<ResponsiveLayoutState | null>(null);
  const [chatMaximized, setChatMaximized] = useState(false);
  const [layoutResetVersion, setLayoutResetVersion] = useState(0);
  const [facts, setFacts] = useState<FactVersion[]>([]);
  const [events, setEvents] = useState<MappedCommonReviewEvent[]>([]);
  const [agentThread, setAgentThread] = useState<AgentThread | null>(null);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const [agentActivity, setAgentActivity] = useState<AgentActivityState | null>(null);
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
  const [preReviewState, setPreReviewState] = useState<PreReviewDemoState | null>(null);
  const [preReviewPending, setPreReviewPending] = useState(false);
  const [preReviewShowDiff, setPreReviewShowDiff] = useState(false);
  const materialRequestRef = useRef(0);
  const selectionAbortRef = useRef<AbortController | null>(null);
  const materialAbortRef = useRef<AbortController | null>(null);
  const writeKeysRef = useRef(new Map<string, { fingerprint: string; key: string }>());
  const agentThreadRef = useRef<AgentThread | null>(null);
  const agentThreadCreationRef = useRef<Promise<AgentThread> | null>(null);
  const activeProjectRef = useRef(projectId);
  const intelligenceRequestRef = useRef(0);
  const intelligenceRunAbortRef = useRef<AbortController | null>(null);
  const lastExpandedMaterialRatioRef = useRef<number>(PRESENTATION_LAYOUT_RATIOS.materialRatio);

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
    setChatMaximized(false);
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
    setPreReviewState(preReviewEnabled ? createPreReviewDemoState(projectId) : null);
    setPreReviewShowDiff(false);
    agentThreadRef.current = null;
    agentThreadCreationRef.current = null;
    setAgentThread(null);
    setAgentMessages([]);
    setAgentActivity(null);
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
        layout: { ...presentedProject.layout },
        materials: firstMaterial ? materials.map((item) => item.id === firstMaterial.id ? firstMaterial : item) : materials,
        dimensions: scoreSummary.dimensions,
        riskSummary: { ...presentedProject.riskSummary, scoreGrade: scoreSummary.overallGrade },
        determinations: presentedProject.determinations.map((item) => ({ ...item, scoreGrade: scoreToGrade(item.score) })),
      };
      let stored: unknown = null;
      try {
      stored = JSON.parse(localStorage.getItem(presentationMode ? PERSISTED_PRESENTATION_LAYOUT_KEY : PERSISTED_LAYOUT_KEY) ?? "null");
      } catch { stored = null; }
      const layoutFallback = presentationMode
        ? { ...scoredProject.layout, ...PRESENTATION_LAYOUT_RATIOS }
        : scoredProject.layout;
      const persisted = { ...sanitizePersistedLayout(stored, layoutFallback) };
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
  }, [gateway, projectId, preReviewEnabled, presentationMode]);

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
    const storageKey = presentationMode ? PERSISTED_PRESENTATION_LAYOUT_KEY : PERSISTED_LAYOUT_KEY;
    localStorage.setItem(storageKey, JSON.stringify(persistedLayoutFrom(layout)));
    localStorage.setItem(PERSISTED_LAYOUT_VERSION_KEY, String(PERSISTED_LAYOUT_VERSION));
  }, [layout, presentationMode]);

  const rules = policyRules;

  if (error) return <div className="full-page-state"><EmptyState detail={error} title="工作台加载失败" /></div>;
  if (!data || !layout) return <div className="full-page-state"><EmptyState detail="正在读取项目数据。" title="加载工作台" /></div>;

  const updateLayout = (change: Partial<ResponsiveLayoutState>) => setLayout((current) => current ? { ...current, ...change } : current);
  const toggleMaterialPane = () => {
    if (layout?.materialCollapsed) {
      updateLayout({ materialCollapsed: false, materialRatio: lastExpandedMaterialRatioRef.current });
      return;
    }
    if (layout && layout.materialRatio > 12) lastExpandedMaterialRatioRef.current = layout.materialRatio;
    updateLayout({ materialCollapsed: true });
  };
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
  const focusRiskReview = (showDiff = false) => {
    setChatMaximized(false);
    updateLayout({ middleCollapsed: false });
    setActiveReviewId("risk");
    setPreReviewShowDiff(showDiff);
    setTimeout(() => {
      const riskSection = document.getElementById("review-risk");
      if (riskSection) { riskSection.tabIndex = -1; riskSection.focus(); }
      scrollReviewElementIntoView(riskSection);
    }, 0);
  };
  const runPreReview = () => {
    setPreReviewPending(true);
    setPreReviewState((current) => current ? rerunPreReviewDemo(current) : createPreReviewDemoState(data.project.id));
    setPreReviewPending(false);
  };
  const submitPreReview = () => setPreReviewState((current) => current ? submitPreReviewDemo(current) : current);
  const setPreReviewDisposition = (disposition: "退回" | "复核" | "否决") => {
    setPreReviewState((current) => current ? { ...current, disposition } : current);
  };
  const presentationTargetForDimension = (id: ReviewSectionId): ReviewEvidenceTarget | null => {
    if (id === "risk") return null;
    const evidenceById = new Map(data.evidence.map((reference) => [reference.id, reference]));
    const fact = facts.find((candidate) => candidate.dimensionId === id && candidate.evidenceRefs.some((referenceId) => evidenceById.get(referenceId)?.locator));
    if (!fact) return null;
    const evidenceRefs = fact.evidenceRefs.filter((referenceId) => evidenceById.get(referenceId)?.locator);
    const evidenceRef = evidenceRefs[0];
    return evidenceRef ? { evidenceRef, evidenceRefs, dimensionId: id, reviewTargetId: fact.id, factVersionId: fact.id } : null;
  };
  const navigateReview = (id: ReviewSectionId) => {
    setActiveReviewId(id);
    if (id !== "risk") {
      updateLayout({ activeDimensionId: id });
      const presentationTarget = presentationMode ? presentationTargetForDimension(id) : null;
      if (presentationTarget) void selectEvidenceGroup(presentationTarget);
      else {
        setSelectedReviewTarget(null);
        setEvidenceSelectionGroup(null);
        setEvidenceSelectionResolution(null);
      }
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
      const payload = { projectId: data.project.id, title: "项目群聊", principal: "business" as const };
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
  const agentSubmissionContext = (reference: CollaborationContextReference | null) => {
    const referencedMessage = reference?.kind === "agent_message" ? agentMessages.find((message) => message.id === reference.id) : undefined;
    const referencedEvent = reference?.kind === "review_event" ? events.find((event) => event.id === reference.id) : undefined;
    const targets = referencedMessage?.citations.map((citation) => ({ ...citation, evidenceRefs: [citation.evidenceRef] }))
      ?? referencedEvent?.evidenceTargets
      ?? (reference?.kind === "material_annotation" ? reference.matchStatus === "pending" ? [] : reference.evidenceTargets : undefined)
      ?? sharedTargets;
    const uniqueTargets = [...new Map(targets.map((target) => [`${target.evidenceRef}|${target.dimensionId}|${target.reviewTargetId ?? ""}|${target.factVersionId ?? ""}`, target])).values()];
    return { evidenceTargets: uniqueTargets, replyToMessageId: referencedMessage?.id ?? null };
  };
  const submitChatMessage = async (targetAgentRole: ChatAgentRole | null, message: string, reference: CollaborationContextReference | null, responsePreferences: AgentResponsePreferences) => {
    setAgentSessionError(null);
    let thread: AgentThread;
    try {
      thread = await ensureAgentThread();
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "项目群聊准备失败。";
      throw new Error(detail);
    }
    const context = agentSubmissionContext(reference);
    const principal = account.role;
    const messagePayload = { projectId: data.project.id, threadId: thread.id, principal, content: message, replyToMessageId: context.replyToMessageId, evidenceTargets: context.evidenceTargets, locale: "zh-CN" as const };
    const messageOperation = `agent-message:${thread.id}:${principal}`;
    let postedMessage: AgentMessage;
    try {
      postedMessage = await gateway.postAgentMessage({ ...messagePayload, idempotencyKey: idempotencyKey(messageOperation, messagePayload, writeKeysRef.current) });
      clearIdempotencyKey(messageOperation, writeKeysRef.current);
      setAgentMessages((items) => [...items.filter((item) => item.id !== postedMessage.id), postedMessage].sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id)));
    } catch (reason) {
      clearIdempotencyKey(messageOperation, writeKeysRef.current);
      const detail = reason instanceof Error ? reason.message : "消息发送失败。";
      throw new Error(detail);
    }
    if (!targetAgentRole) return;

    const payload = { projectId: data.project.id, threadId: thread.id, principal, targetAgentRole, sourceMessageId: postedMessage.id, instruction: message, ...context, ...responsePreferences, expectedVersion: thread.version, locale: "zh-CN" as const };
    const operation = `agent-turn:${thread.id}:${postedMessage.id}:${targetAgentRole}`;
    const roleLabel = targetAgentRole === "risk" ? "风控" : "业务";
    setAgentActivity({ sourceMessageId: postedMessage.id, role: targetAgentRole, phase: "thinking", startedAt: new Date().toISOString(), detail: `${roleLabel} Agent 正在读取项目上下文与引用，并生成辅助建议。` });
    void (async () => {
      try {
        const result = await gateway.executeAgentTurn({ ...payload, idempotencyKey: idempotencyKey(operation, payload, writeKeysRef.current) });
        clearIdempotencyKey(operation, writeKeysRef.current);
        rememberAgentThread({ ...thread, version: result.nextExpectedVersion, focusRole: result.currentFocusRole, updatedAt: new Date().toISOString() });
        setAgentMessages((items) => [...items, ...result.messages].filter((item, index, all) => all.findIndex((candidate) => candidate.id === item.id) === index).sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id)));
        setAgentActivity((current) => current?.sourceMessageId === postedMessage.id ? null : current);
      } catch (runReason) {
        clearIdempotencyKey(operation, writeKeysRef.current);
        const detail = runReason instanceof Error ? runReason.message : "Agent 未回复。";
        setAgentActivity((current) => current?.sourceMessageId === postedMessage.id ? { ...current, phase: "failed", detail: `${roleLabel} Agent 未回复：${detail}` } : current);
        return;
      }
      try {
        await refreshAgentSession(thread.id);
      } catch (refreshReason) {
        setAgentSessionError(refreshReason instanceof Error ? `Agent 回复已生成，但群聊刷新失败：${refreshReason.message}` : "Agent 回复已生成，但群聊刷新失败。");
      }
    })();
  };
  const submitNaturalChat = (message: string, targetAgentRole: ChatAgentRole | null, reference: CollaborationContextReference | null, preferences: AgentResponsePreferences) => submitChatMessage(targetAgentRole, message, reference, preferences);
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

  const beginMaterialResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const divider = event.currentTarget;
    const body = divider.closest<HTMLElement>(".workbench-body");
    if (!body) return;
    const pointerId = event.pointerId;
    divider.setPointerCapture(pointerId);
    let nextRatio = layout.materialRatio;
    let frameId: number | null = null;
    const applyResize = () => {
      frameId = null;
      body.style.setProperty("--layout-review-share", `${100 - nextRatio}fr`);
      body.style.setProperty("--layout-material-share", `${nextRatio}fr`);
      divider.setAttribute("aria-valuenow", String(Math.round(nextRatio)));
    };
    const move = (pointerEvent: PointerEvent) => {
      if (pointerEvent.pointerId !== pointerId) return;
      const bodyRect = body.getBoundingClientRect();
      const navigationRight = body.querySelector<HTMLElement>(".navigation-rail")?.getBoundingClientRect().right ?? bodyRect.left;
      const availableWidth = Math.max(1, bodyRect.right - navigationRight);
      const rawRatio = ((bodyRect.right - pointerEvent.clientX) / availableWidth) * 100;
      nextRatio = snapLayoutRatio(rawRatio, PRESENTATION_LAYOUT_RATIOS.materialRatio, LAYOUT_LIMITS.materialRatio);
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
      if (presentationMode && nextRatio <= 12) {
        if ((layout?.materialRatio ?? 0) > 12) lastExpandedMaterialRatioRef.current = layout?.materialRatio ?? PRESENTATION_LAYOUT_RATIOS.materialRatio;
        updateLayout({ materialRatio: LAYOUT_LIMITS.materialRatio[0], materialCollapsed: true });
      } else {
        lastExpandedMaterialRatioRef.current = nextRatio;
        updateLayout({ materialRatio: nextRatio, materialCollapsed: false });
      }
      cleanup();
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    window.addEventListener("blur", stop);
  };

  const resizeMaterialWithKeyboard = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") {
      if (layout.materialRatio > 12) lastExpandedMaterialRatioRef.current = layout.materialRatio;
      updateLayout({ materialRatio: LAYOUT_LIMITS.materialRatio[0], materialCollapsed: presentationMode });
      return;
    }
    if (event.key === "End") { updateLayout({ materialRatio: LAYOUT_LIMITS.materialRatio[1] }); return; }
    const direction = event.key === "ArrowLeft" ? 1 : -1;
    const step = event.shiftKey ? 5 : 2;
    updateLayout({ materialRatio: snapLayoutRatio(layout.materialRatio + direction * step, PRESENTATION_LAYOUT_RATIOS.materialRatio, LAYOUT_LIMITS.materialRatio) });
  };

  const materialAriaValue = Math.round(layout.materialRatio);

  const style = {
    "--layout-navigation-width": presentationMode ? "0px" : `${layout.navigationCollapsed ? 64 : layout.navigationWidth}px`,
    "--layout-review-share": `${100 - layout.materialRatio}fr`,
    "--layout-material-share": `${layout.materialRatio}fr`,
  } as CSSProperties;

  return (
    <div className={`workbench-app ${presentationMode ? "is-presentation-workbench" : ""}`} data-semantic-localized="true" style={style}>
      <TopBar account={account} actionContent={preReviewEnabled && preReviewState ? <PreReviewActionBar onDisposition={setPreReviewDisposition} onSubmit={submitPreReview} pending={preReviewPending} state={preReviewState} /> : null} approval={approvalState} approvalMessage={approvalMessage} approvalPending={approvalPending} centerContent={preReviewEnabled && preReviewState ? <PreReviewSummaryBar onOpenDiff={() => focusRiskReview(true)} onRun={runPreReview} pending={preReviewPending} state={preReviewState} /> : null} hardConstraintCount={rules.length} leadingContent={presentationMode ? <div className="topbar-dial"><NavigationRail activeId={layout.activeDimensionId} collapsed={false} dimensions={data.dimensions} onNavigate={navigateReview} onOverview={() => navigateReview("risk")} onRiskNavigate={() => navigateReview("risk")} onToggleCollapsed={() => undefined} presentationMode riskActive={activeReviewId === "risk"} riskItemCount={riskItemCount(data.riskSummary)} /></div> : null} locale={locale} onApprovalTransition={transitionApproval} onBack={onBack} onLocaleChange={onLocaleChange} onLogout={onLogout} onOpenConclusionReport={openConclusionReport} onPrincipalRoleChange={onPrincipalRoleChange} onResetLayout={() => { setLayout({ ...data.layout, ...(presentationMode ? PRESENTATION_LAYOUT_RATIOS : DEFAULT_LAYOUT_RATIOS), materialCollapsed: false }); lastExpandedMaterialRatioRef.current = PRESENTATION_LAYOUT_RATIOS.materialRatio; setChatMaximized(false); setLayoutResetVersion((value) => value + 1); setActiveReviewId("risk"); }} policyHitCount={rules.filter((rule) => rule.result !== "pass").length} principalRoleChangePending={principalRoleChangePending} project={{ ...data.project, collaborationIssueCount: openIssueCount }} projectNo={projectNo} presentationMode={presentationMode} />
      <div className={`workbench-body has-embedded-chat ${presentationMode ? "is-presentation-layout" : ""} ${layout.middleCollapsed ? "is-middle-collapsed" : ""} ${layout.materialCollapsed ? "is-material-collapsed" : ""} ${chatMaximized ? "is-chat-maximized" : ""}`}>
        {presentationMode ? null : <NavigationRail activeId={layout.activeDimensionId} collapsed={layout.navigationCollapsed} dimensions={data.dimensions} onNavigate={navigateReview} onOverview={() => navigateReview("risk")} onRiskNavigate={() => navigateReview("risk")} onToggleCollapsed={() => updateLayout({ navigationCollapsed: !layout.navigationCollapsed })} presentationMode={presentationMode} riskActive={activeReviewId === "risk"} riskItemCount={riskItemCount(data.riskSummary)} />}
            <ReviewCanvas activeReviewId={activeReviewId} canCorrect={account.role === "business"} collapsed={layout.middleCollapsed} correctionMessage={correctionMessage} correctionPending={correctionPending} data={data} facts={facts} onActiveReviewChange={(id) => { setActiveReviewId(id); if (id !== "risk") updateLayout({ activeDimensionId: id }); }} onCorrection={submitCorrection} onEvidenceSelect={(target) => void selectEvidenceGroup(target)} onProductionStageSelect={handleProductionStageSelect} onTimeSeriesRequest={(request) => gateway.queryDimensionSeries(request)} onToggleCollapsed={() => updateLayout({ middleCollapsed: !layout.middleCollapsed })} presentationMode={presentationMode} riskChangeSummary={preReviewShowDiff && preReviewState?.diff ? `${preReviewState.diff.fromVersion} → ${preReviewState.diff.toVersion} · ${preReviewState.diff.summary}` : null} selectedProductionStageId={selectedProductionStageId} selectedTarget={selectedReviewTarget} />
        {!layout.middleCollapsed && !layout.materialCollapsed && !chatMaximized ? <div aria-label={copy(locale, "Resize the review and original-material areas", "调整审批画布与右侧区域宽度")} aria-orientation="vertical" aria-valuemax={LAYOUT_LIMITS.materialRatio[1]} aria-valuemin={LAYOUT_LIMITS.materialRatio[0]} aria-valuenow={materialAriaValue} aria-valuetext={copy(locale, `Right-side width: ${materialAriaValue}%`, `右侧区域宽度 ${materialAriaValue}%`)} className="layout-divider divider-vertical" onKeyDown={resizeMaterialWithKeyboard} onPointerDown={beginMaterialResize} role="separator" tabIndex={0} /> : null}
        <MaterialPane activeIntelligenceAnchorId={activeIntelligenceAnchorId} canEditIntelligence={account.role === "business"} chatMaximized={chatMaximized} chatRatio={layout.collaborationRatio} collapsed={layout.materialCollapsed} confirmedCandidateIds={confirmedCandidateIds} confirmingCandidateId={confirmingCandidateId} errorMessage={materialRecovery.error} evidence={data.evidence} evidenceSelectionResolution={evidenceSelectionResolution} facts={facts} groupChat={{ accountRole: account.role, agentActivity, agentError: agentSessionError, agentMessages, onConfirmMaterialImport, onImportMaterialPackage, onSubmitMessage: submitNaturalChat, selectedTarget: selectedReviewTarget }} intelligence={materialIntelligence} intelligenceMessage={intelligenceMessage} intelligenceStatus={intelligenceStatus} locale={locale} materials={data.materials} modelGatewayRuntime={modelGatewayRuntime} onCancelIntelligence={cancelSelectedMaterialIntelligence} onChatMaximizedChange={setChatMaximized} onChatRatioChange={(collaborationRatio) => updateLayout({ collaborationRatio })} onConfirmCandidate={(candidate, reason) => void confirmCandidate(candidate, reason)} onEvidenceActivate={activateSelectedEvidence} onIntelligenceAnchorActivate={activateIntelligenceAnchor} onMaterialSelect={handleMaterialSelect} onRetry={retryMaterialRecovery} onRunIntelligence={() => void runSelectedMaterialIntelligence()} onToggleCollapsed={toggleMaterialPane} presentationMode={presentationMode} sceneSpec={materialSceneSpec} selectedMaterialId={selectedMaterialId} selectionGroup={evidenceSelectionGroup} />
      </div>
      {conclusionOpen ? <FinalConclusionReport error={conclusionError} onClose={() => setConclusionOpen(false)} onRefresh={() => void loadConclusionReport()} report={conclusionReport} status={conclusionStatus} /> : null}
    </div>
  );
}
