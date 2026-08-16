import { DIMENSION_IDS } from "../contracts/workbench.ts";
import type {
  BusinessCorrectionInput,
  CommonReviewEvent,
  ComplianceSubjectGraph,
  DimensionDefinition,
  DimensionId,
  DimensionSeriesRequest,
  DimensionSeriesResponse,
  DimensionTimeSeries,
  EquipmentPriceBenchmark,
  EvidenceReference,
  FactVersion,
  FinancedEquipmentLedger,
  FinancedEquipmentLine,
  GlobalRiskSummary,
  LayoutState,
  MappedCommonReviewEvent,
  Material,
  ProductionEnergyPoint,
  ProductionEnergySeries,
  RiskLevel,
  ReviewEvidenceSelectionGroup,
  ReviewEvidenceTarget,
  ScoreGrade,
  TransactionRepaymentSchedule,
} from "../contracts/workbench";

export const LAYOUT_LIMITS = {
  navigationWidth: [64, 292],
  materialRatio: [10, 90],
  collaborationRatio: [10, 90],
} as const;

export const DEFAULT_LAYOUT_RATIOS = {
  materialRatio: 50,
  collaborationRatio: 50,
} as const;

export const PERSISTED_LAYOUT_KEY = "compare-front-layout-v1";
export const DEFAULT_TIME_SERIES_RANGE = { startDate: "2025-08-01", endDate: "2026-08-01" } as const;
export const DEFAULT_TIME_SERIES_TIMEZONE = "Asia/Shanghai";
export const INDUSTRY_DISPLAY_ORDER = ["金属精密加工", "塑料制品加工", "纺织制造", "印刷包装", "玻璃深加工", "电子制造"] as const;

const INDUSTRY_DISPLAY_NAMES: Record<string, string> = {
  金属精密加工: "金属",
  塑料制品加工: "注塑",
  纺织制造: "纺织",
  印刷包装: "印包",
  玻璃深加工: "玻璃",
  电子制造: "电子",
};

export function defaultTimeSeriesRange(): { startDate: string; endDate: string } {
  return { ...DEFAULT_TIME_SERIES_RANGE };
}

export function catalogProjectIdentity<T extends { projectId: string; projectNo: string }>(projects: readonly T[], projectId: string) {
  const project = projects.find((item) => item.projectId === projectId);
  return project ? { requestProjectId: project.projectId, projectNo: project.projectNo } : null;
}

/**
 * 服务端保留原始名称；页面主视觉不把“系统生成/规则生成”当作客户名称的一部分。
 * 这只影响展示，不能把脱敏模拟数据伪装成真实客户材料。
 */
export function displayBusinessText(value: string, fallback = "待核验") {
  const visible = value
    .trim()
    .replaceAll("业务规则生成数据", "业务模拟数据")
    .replaceAll("规则生成核验", "模拟核验")
    .replace(/(?:系统|规则)生成[·:：\s\-—_]*/gu, "")
    .replace(/\s{2,}/gu, " ")
    .trim();
  return visible || fallback;
}

export function displayBusinessName(value: string, fallback = "待核验主体") {
  return displayBusinessText(value, fallback);
}

export function displayIndustryName(value: string) {
  return INDUSTRY_DISPLAY_NAMES[value] ?? value;
}

export function resolveTimeSeriesRange(candidate?: { startDate: string; endDate: string }) {
  if (candidate && /^\d{4}-\d{2}-\d{2}$/.test(candidate.startDate) && /^\d{4}-\d{2}-\d{2}$/.test(candidate.endDate) && candidate.startDate <= candidate.endDate) {
    return { ...candidate };
  }
  return defaultTimeSeriesRange();
}

export function createTimeSeriesRequest(input: Omit<DimensionSeriesRequest, "timezone">): DimensionSeriesRequest {
  return { ...input, timezone: DEFAULT_TIME_SERIES_TIMEZONE };
}

export const RISK_LEVEL_ORDER = ["forbid", "risk", "confirm", "attention", "support"] as const satisfies readonly RiskLevel[];

export interface RiskDisplayItem {
  id: string;
  title: string;
  detail: string;
  level: RiskLevel;
  sourceLabel: "制度规则" | "关键异常" | "人工认定";
  evidenceTargets: ReviewEvidenceTarget[];
  primaryTarget: ReviewEvidenceTarget | null;
  responsibleParty: "business" | "risk" | "joint";
  nextAction: string;
}

export interface RiskDisplayGroup {
  level: RiskLevel;
  items: RiskDisplayItem[];
}

export function riskItemCount(summary: GlobalRiskSummary) {
  return groupRiskItems(summary).reduce((total, group) => total + group.items.length, 0);
}

export interface GraphPoint {
  x: number;
  y: number;
}

export interface RelationshipPath {
  nodeIds: string[];
  relationIds: string[];
}

export interface GraphEdgePoints {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export function relationshipEdgePoints(from: GraphPoint, to: GraphPoint, diameter: number, offset = 0): GraphEdgePoints {
  const radius = diameter / 2;
  const fromCenter = { x: from.x + radius, y: from.y + radius };
  const toCenter = { x: to.x + radius, y: to.y + radius };
  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  const ux = dx / length;
  const uy = dy / length;
  const px = -uy * offset;
  const py = ux * offset;
  return {
    x1: fromCenter.x + ux * radius + px,
    y1: fromCenter.y + uy * radius + py,
    x2: toCenter.x - ux * radius + px,
    y2: toCenter.y - uy * radius + py,
  };
}

export function hardConstraintEvidenceRefs(rule: GlobalRiskSummary["hardConstraintResults"][number]) {
  return rule.evidenceTargets.map((target) => target.evidenceRef);
}

export function sameReviewEvidenceTarget(left: ReviewEvidenceTarget | null, right: ReviewEvidenceTarget | null) {
  if (!left || !right) return false;
  return left.evidenceRef === right.evidenceRef
    && left.dimensionId === right.dimensionId
    && left.reviewTargetId === right.reviewTargetId
    && left.factVersionId === right.factVersionId;
}

export function createEvidenceSelectionGroup(target: ReviewEvidenceTarget): ReviewEvidenceSelectionGroup {
  const evidenceRefs = [...new Set((target.evidenceRefs?.length ? target.evidenceRefs : [target.evidenceRef]).filter(Boolean))];
  const normalizedRefs = evidenceRefs.length ? evidenceRefs : [target.evidenceRef];
  return {
    id: [target.dimensionId, target.reviewTargetId ?? "review", target.factVersionId ?? "fact", ...normalizedRefs].join("::"),
    dimensionId: target.dimensionId,
    reviewTargetId: target.reviewTargetId,
    factVersionId: target.factVersionId,
    targets: normalizedRefs.map((evidenceRef) => ({
      ...target,
      evidenceRef,
      evidenceRefs: [...normalizedRefs],
    })),
  };
}

export function reviewTargetForEvidence(group: ReviewEvidenceSelectionGroup | null, evidenceRef: string) {
  return group?.targets.find((target) => target.evidenceRef === evidenceRef) ?? null;
}

export function projectReviewEvidenceTargets(evidenceTargets: readonly ReviewEvidenceTarget[]) {
  const factVersionIds = [...new Set(evidenceTargets.flatMap((target) => target.factVersionId ? [target.factVersionId] : []))];
  return {
    reviewTargetId: evidenceTargets[0]?.reviewTargetId ?? null,
    factVersionIds,
    evidenceRefs: [...new Set(evidenceTargets.map((target) => target.evidenceRef))],
  };
}

export function attachReviewEvidenceTargets(
  event: CommonReviewEvent,
  evidenceTargets: readonly ReviewEvidenceTarget[],
): MappedCommonReviewEvent {
  const targets = evidenceTargets.map((target) => ({ ...target }));
  return {
    ...event,
    ...projectReviewEvidenceTargets(targets),
    evidenceTargets: targets,
  };
}

export function reviewEvidenceTargetAt(event: Pick<CommonReviewEvent, "evidenceTargets">, index: number) {
  return event.evidenceTargets?.[index] ?? null;
}

export function moveGraphNode(
  positions: Readonly<Record<string, GraphPoint>>,
  nodeId: string,
  next: GraphPoint,
  bounds = { width: 900, height: 520, nodeWidth: 194, nodeHeight: 118 },
) {
  if (!positions[nodeId]) return { ...positions };
  return {
    ...positions,
    [nodeId]: {
      x: clamp(next.x, 0, Math.max(0, bounds.width - bounds.nodeWidth)),
      y: clamp(next.y, 0, Math.max(0, bounds.height - bounds.nodeHeight)),
    },
  };
}

export function shortestRelationshipPath(graph: ComplianceSubjectGraph, startId: string, endId: string): RelationshipPath | null {
  const nodeIds = new Set(graph.nodes.map((node) => node.id));
  if (!nodeIds.has(startId) || !nodeIds.has(endId)) return null;
  if (startId === endId) return { nodeIds: [startId], relationIds: [] };
  const queue: RelationshipPath[] = [{ nodeIds: [startId], relationIds: [] }];
  const visited = new Set([startId]);
  while (queue.length) {
    const current = queue.shift()!;
    const currentNodeId = current.nodeIds.at(-1)!;
    for (const relation of graph.relations) {
      const nextNodeId = relation.fromId === currentNodeId
        ? relation.toId
        : relation.toId === currentNodeId
          ? relation.fromId
          : null;
      if (!nextNodeId || visited.has(nextNodeId)) continue;
      const nextPath = {
        nodeIds: [...current.nodeIds, nextNodeId],
        relationIds: [...current.relationIds, relation.id],
      };
      if (nextNodeId === endId) {
        return {
          nodeIds: nextPath.nodeIds,
          relationIds: nextPath.nodeIds.slice(0, -1).flatMap((nodeId, index) => {
            const followingNodeId = nextPath.nodeIds[index + 1];
            return graph.relations
              .filter((item) => (item.fromId === nodeId && item.toId === followingNodeId) || (item.fromId === followingNodeId && item.toId === nodeId))
              .map((item) => item.id);
          }),
        };
      }
      visited.add(nextNodeId);
      queue.push(nextPath);
    }
  }
  return null;
}

export function groupRiskItems(summary: GlobalRiskSummary): RiskDisplayGroup[] {
  const ruleItems: RiskDisplayItem[] = summary.hardConstraintResults.map((rule) => ({
      id: `risk-rule-${rule.id}`,
      title: rule.title,
      detail: rule.explanation,
      level: rule.result === "block" ? "forbid" : rule.result === "pass" ? "support" : "confirm",
      sourceLabel: "制度规则",
      evidenceTargets: rule.evidenceTargets.map((target) => ({ ...target })),
      primaryTarget: rule.primaryTarget ? { ...rule.primaryTarget } : null,
      responsibleParty: rule.responsibleParty,
      nextAction: rule.nextAction,
    }));
  const anomalyItems: RiskDisplayItem[] = summary.keyAnomalies.map((item) => ({
    ...item,
    sourceLabel: "关键异常",
    evidenceTargets: item.evidenceTargets.map((target) => ({ ...target })),
    primaryTarget: item.primaryTarget ? { ...item.primaryTarget } : null,
  }));
  const determinationItems: RiskDisplayItem[] = summary.pendingHumanDeterminations.map((item) => ({
    ...item,
    sourceLabel: "人工认定",
    evidenceTargets: item.evidenceTargets.map((target) => ({ ...target })),
    primaryTarget: item.primaryTarget ? { ...item.primaryTarget } : null,
  }));
  const items = [...ruleItems, ...anomalyItems, ...determinationItems];
  return RISK_LEVEL_ORDER.map((level) => ({ level, items: items.filter((item) => item.level === level) }));
}

export type ResponsiveLayoutState = LayoutState & {
  materialRatio: number;
  collaborationRatio: number;
};

export type PersistedLayout = Pick<
  LayoutState,
  | "navigationWidth"
  | "materialWidth"
  | "collaborationHeight"
  | "navigationCollapsed"
  | "middleCollapsed"
  | "materialCollapsed"
  | "collaborationCollapsed"
  | "businessCollapsed"
  | "policyCollapsed"
  | "riskCollapsed"
  | "activeDimensionId"
> & Pick<ResponsiveLayoutState, "materialRatio" | "collaborationRatio">;

export function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function round1(value: number) {
  return Math.round((value + Number.EPSILON) * 10) / 10;
}

export function normalizeScore(score: number) {
  return round1(clamp(Number.isFinite(score) ? score : 0, 0, 100));
}

function normalizedScoreToGrade(normalizedScore: number): ScoreGrade {
  const normalized = normalizeScore(normalizedScore);
  if (normalized >= 80) return "A";
  if (normalized >= 60) return "B";
  if (normalized >= 40) return "C";
  if (normalized >= 20) return "D";
  return "E";
}

export function scoreToGrade(score: number): ScoreGrade {
  return normalizedScoreToGrade(normalizeScore(score));
}

export function averageScore(scores: readonly number[]) {
  if (scores.length === 0) return 0;
  return round1(scores.reduce((total, score) => total + clamp(score, 0, 100), 0) / scores.length);
}

export function scoreRadius(score: number) {
  return round1(clamp(18 + normalizeScore(score) * 0.82, 18, 100));
}

export const GRADE_COLOR_VARS: Record<ScoreGrade, string> = {
  A: "var(--grade-a)",
  B: "var(--grade-b)",
  C: "var(--grade-c)",
  D: "var(--grade-d)",
  E: "var(--grade-e)",
};

export interface ScoreVisual {
  normalizedScore: number;
  grade: ScoreGrade;
  colorVar: string;
  radiusPercent: number;
  progressPercent: number;
}

export function deriveScoreVisual(score: number): ScoreVisual {
  const normalizedScore = normalizeScore(score);
  const grade = normalizedScoreToGrade(normalizedScore);
  return {
    normalizedScore,
    grade,
    colorVar: GRADE_COLOR_VARS[grade],
    radiusPercent: scoreRadius(normalizedScore),
    progressPercent: normalizedScore,
  };
}

export function deriveScoreSummary(dimensions: readonly DimensionDefinition[]) {
  const dimensionById = new Map(dimensions.map((dimension) => [dimension.id, dimension]));
  if (dimensions.length !== DIMENSION_IDS.length || dimensionById.size !== DIMENSION_IDS.length || DIMENSION_IDS.some((id) => !dimensionById.has(id))) {
    throw new Error("六维评分必须包含合规、交易、生产、营收、负债、流水且不得重复。");
  }
  const normalizedDimensions = DIMENSION_IDS.map((id) => {
    const dimension = dimensionById.get(id)!;
    return { ...dimension, scoreGrade: scoreToGrade(dimension.score) };
  });
  const overallScore = averageScore(normalizedDimensions.map((dimension) => dimension.score));
  return {
    dimensions: normalizedDimensions,
    overallScore,
    overallGrade: scoreToGrade(overallScore),
  };
}

export function calculateFinancedEquipmentLedger(ledger: FinancedEquipmentLedger) {
  const lines = ledger.lines.map((line) => {
    const contractTotal = line.quantity * line.contractUnitPrice;
    const comparableUnitPrice = line.priceBenchmark.status === "available" && line.priceBenchmark.median !== null
      ? line.priceBenchmark.median
      : null;
    const comparableTotal = comparableUnitPrice === null ? null : line.quantity * comparableUnitPrice;
    return {
      ...line,
      contractTotal,
      comparableUnitPrice,
      comparableTotal,
      variance: comparableTotal === null ? null : contractTotal - comparableTotal,
    };
  });
  const comparableAvailable = lines.every((line) => line.comparableTotal !== null);
  const comparableTotal = comparableAvailable
    ? lines.reduce((total, line) => total + (line.comparableTotal ?? 0), 0)
    : null;
  const contractTotal = lines.reduce((total, line) => total + line.contractTotal, 0);
  return {
    lines,
    totalQuantity: lines.reduce((total, line) => total + line.quantity, 0),
    contractTotal,
    comparableStatus: comparableAvailable ? "available" as const : "unavailable" as const,
    comparableTotal,
    variance: comparableTotal === null ? null : contractTotal - comparableTotal,
  };
}

export type RepaymentStructure = "front_loaded" | "balanced" | "back_loaded";
export type RepaymentStructureDisplayValue = "前高后低" | "均衡" | "前低后高";
export type RepaymentStructureRiskLabel = "低风险" | "中风险" | "高风险";

export type RepaymentScheduleAnalysis =
  | { status: "available"; structure: RepaymentStructure; displayValue: RepaymentStructureDisplayValue; riskLabel: RepaymentStructureRiskLabel; firstSegmentShare: number; lastSegmentShare: number; firstHalfPrincipalRecoveryRatio: number; principalTotal: number; evidenceRefs: string[] }
  | { status: "missing" | "unavailable" | "invalid"; message: string; evidenceRefs: string[] };

const REPAYMENT_TOLERANCE = 0.01;

function scheduleEvidenceRefs(schedule: TransactionRepaymentSchedule) {
  return [...new Set([
    ...schedule.points.flatMap((point) => point.evidenceRefs),
    ...schedule.firstPaymentEvidenceRefs,
    ...schedule.firstTwelveEvidenceRefs,
    ...schedule.totalRentEvidenceRefs,
    ...schedule.termEvidenceRefs,
  ])];
}

/** Mirrors Back/app/domain/repayment.py: compare first/last thirds of principal with an 8pp threshold. */
export function analyzeRepaymentSchedule(schedule: TransactionRepaymentSchedule, expectedTermMonths = schedule.termMonths): RepaymentScheduleAnalysis {
  const evidenceRefs = scheduleEvidenceRefs(schedule);
  if (schedule.status !== "available") return { status: schedule.status, message: schedule.message || "还款计划不可用。", evidenceRefs };
  if (!Number.isInteger(schedule.termMonths) || schedule.termMonths < 3 || schedule.termMonths !== expectedTermMonths || schedule.points.length !== schedule.termMonths) {
    return { status: "invalid", message: "还款计划期数与期限不一致。", evidenceRefs };
  }
  const validPoints = schedule.points.every((point, index) => point.period === index + 1
    && [point.principal, point.interest, point.rent].every(Number.isFinite)
    && point.principal >= 0
    && point.interest >= 0
    && point.rent >= 0
    && Math.abs(point.rent - (point.principal + point.interest)) <= REPAYMENT_TOLERANCE);
  if (!validPoints) return { status: "invalid", message: "还款计划逐期金额、期号或租金勾稽无效。", evidenceRefs };
  const principalTotal = schedule.points.reduce((total, point) => total + point.principal, 0);
  if (!Number.isFinite(principalTotal) || principalTotal <= 0) return { status: "invalid", message: "还款计划本金合计必须大于零。", evidenceRefs };
  const segmentSize = Math.max(1, Math.floor(schedule.points.length / 3));
  const firstSegmentShare = schedule.points.slice(0, segmentSize).reduce((total, point) => total + point.principal, 0) / principalTotal;
  const lastSegmentShare = schedule.points.slice(-segmentSize).reduce((total, point) => total + point.principal, 0) / principalTotal;
  const firstHalfCount = Math.ceil(schedule.points.length / 2);
  const firstHalfPrincipalRecoveryRatio = schedule.points.slice(0, firstHalfCount).reduce((total, point) => total + point.principal, 0) / principalTotal;
  const structure: RepaymentStructure = firstSegmentShare - lastSegmentShare >= .08
    ? "front_loaded"
    : lastSegmentShare - firstSegmentShare >= .08 ? "back_loaded" : "balanced";
  const presentation = {
    front_loaded: { displayValue: "前高后低", riskLabel: "低风险" },
    balanced: { displayValue: "均衡", riskLabel: "中风险" },
    back_loaded: { displayValue: "前低后高", riskLabel: "高风险" },
  } as const satisfies Record<RepaymentStructure, { displayValue: RepaymentStructureDisplayValue; riskLabel: RepaymentStructureRiskLabel }>;
  return { status: "available", structure, ...presentation[structure], firstSegmentShare, lastSegmentShare, firstHalfPrincipalRecoveryRatio, principalTotal, evidenceRefs };
}

export function repaymentChartLabelPeriods(termMonths: number) {
  if (!Number.isInteger(termMonths) || termMonths <= 0) return [];
  return [...new Set(Array.from({ length: Math.min(7, termMonths) }, (_, index) => index === 0 ? 1 : Math.round(termMonths * index / Math.min(6, termMonths - 1))))];
}

export interface TransactionTopParameter {
  id: string;
  label: "供应商评级" | "品牌评级" | "项目金额" | "融资成数" | "融资金额" | "期限" | "还款结构风险";
  value: string;
  status: string;
  context: string;
  evidenceRefs: string[];
  available: boolean;
}

export function formatFinancingRatio(value: number | null) {
  return value === null || !Number.isFinite(value) ? "待核验" : `${value.toFixed(1)}%`;
}

export function deriveTransactionTopParameters(ledger: FinancedEquipmentLedger, current: FinancedEquipmentLine): TransactionTopParameter[] {
  const calculated = calculateFinancedEquipmentLedger(ledger);
  const financingAmount = calculated.contractTotal - ledger.downPaymentAmount;
  const financingRatio = calculated.contractTotal > 0 ? financingAmount / calculated.contractTotal * 100 : null;
  const repayment = analyzeRepaymentSchedule(ledger.repaymentSchedule, ledger.termMonths);
  const money = (value: number) => `${(value / 10_000).toFixed(1)} 万元`;
  return [
    { id: `transaction-core-supplier-rating-${current.id}`, label: "供应商评级", value: current.supplierRating ?? "待核验", status: "", context: current.supplier, evidenceRefs: current.supplierRatingEvidenceRefs ?? [], available: !!current.supplierRating },
    { id: `transaction-core-brand-rating-${current.id}`, label: "品牌评级", value: current.brandRating ?? "待核验", status: "", context: current.brand, evidenceRefs: current.brandRatingEvidenceRefs ?? [], available: !!current.brandRating },
    { id: "transaction-core-project-amount", label: "项目金额", value: money(calculated.contractTotal), status: "", context: "合同设备合计", evidenceRefs: ledger.projectAmountEvidenceRefs, available: calculated.contractTotal > 0 },
    { id: "transaction-core-financing-ratio", label: "融资成数", value: formatFinancingRatio(financingRatio), status: "", context: "融资额 / 项目金额", evidenceRefs: ledger.financingRatioEvidenceRefs, available: financingRatio !== null },
    { id: "transaction-core-financing-amount", label: "融资金额", value: Number.isFinite(financingAmount) && financingAmount >= 0 ? money(financingAmount) : "待核验", status: "", context: "项目金额 - 首付款", evidenceRefs: [...new Set([...ledger.projectAmountEvidenceRefs, ...ledger.financingPlanEvidenceRefs])], available: Number.isFinite(financingAmount) && financingAmount >= 0 },
    { id: "transaction-core-term", label: "期限", value: `${ledger.repaymentSchedule.termMonths} 期`, status: "", context: "完整还款计划期限", evidenceRefs: ledger.repaymentSchedule.termEvidenceRefs, available: repayment.status === "available" },
    { id: "transaction-core-repayment-structure", label: "还款结构风险", value: repayment.status === "available" ? repayment.displayValue : "待核验", status: repayment.status === "available" ? repayment.riskLabel : "", context: repayment.status === "available" ? `前半期本金回收 ${(repayment.firstHalfPrincipalRecoveryRatio * 100).toFixed(1)}%` : repayment.message, evidenceRefs: repayment.evidenceRefs, available: repayment.status === "available" },
  ];
}

export function selectEquipmentId(currentId: string | null, candidateId: string, validIds: readonly string[]) {
  return validIds.includes(candidateId) ? candidateId : currentId;
}

export interface DetailFocusState {
  panelId: string | null;
  itemId: string | null;
}

export function deriveDetailFocus(panelId: string, itemId: string | null, focus: DetailFocusState) {
  return {
    panelActive: focus.panelId === panelId,
    panelMuted: focus.panelId !== null && focus.panelId !== panelId,
    itemActive: itemId !== null && focus.panelId === panelId && focus.itemId === itemId,
    itemMuted: itemId !== null && focus.panelId === panelId && focus.itemId !== null && focus.itemId !== itemId,
  };
}

export function isActivationKey(key: string) {
  return key === "Enter" || key === " ";
}

export function canStartGraphPan(hasInteractiveAncestor: boolean) {
  return !hasInteractiveAncestor;
}

export function terminatePointerSession<T extends { pointerId: number }>(session: T | null, pointerId: number) {
  return session?.pointerId === pointerId ? null : session;
}

export function selectedRiskItemId(
  groups: readonly RiskDisplayGroup[],
  selectedTarget: ReviewEvidenceTarget | null,
  currentId: string | null,
) {
  if (!selectedTarget) return null;
  const items = groups.flatMap((group) => group.items);
  const current = items.find((item) => item.id === currentId);
  if (current?.evidenceTargets.some((target) => sameReviewEvidenceTarget(target, selectedTarget))) return current.id;
  return items.find((item) => item.evidenceTargets.some((target) => sameReviewEvidenceTarget(target, selectedTarget)))?.id ?? null;
}

export function toggledRiskLevel(current: RiskLevel | null, requested: RiskLevel, itemCount: number) {
  if (itemCount <= 0) return current;
  return current === requested ? null : requested;
}

export type PriceBenchmarkResult =
  | { status: "available"; lowPosition: 0; medianPosition: number; currentPosition: number; highPosition: 100; deviationPercent: number; tone: "positive" | "attention" | "risk"; message: string }
  | { status: "missing" | "invalid" | "unavailable"; message: string };

export function derivePriceBenchmark(benchmark: EquipmentPriceBenchmark, currentUnitPrice: number): PriceBenchmarkResult {
  if (benchmark.status !== "available") return { status: benchmark.status, message: benchmark.message || "可比价格暂不可用。" };
  const { low, median, high } = benchmark;
  if (
    benchmark.priceBasis !== "per_unit"
    || low === null
    || median === null
    || high === null
    || ![low, median, high, currentUnitPrice].every(Number.isFinite)
    || low < 0
    || currentUnitPrice < 0
    || !(low <= median && median <= high)
    || high <= low
    || median <= 0
  ) return { status: "invalid", message: "可比价格口径、单位或区间顺序无效。" };
  const range = high - low;
  const deviationPercent = round1((currentUnitPrice - median) / median * 100);
  const absoluteDeviation = Math.abs(deviationPercent);
  return {
    status: "available",
    lowPosition: 0,
    medianPosition: round1((median - low) / range * 100),
    currentPosition: round1(clamp((currentUnitPrice - low) / range * 100, 0, 100)),
    highPosition: 100,
    deviationPercent,
    tone: absoluteDeviation > 10 ? "risk" : absoluteDeviation > 5 ? "attention" : "positive",
    message: benchmark.message,
  };
}

export interface TransactionPriceVerificationItem {
  id: string;
  label: "合同价" | "供应商报价" | "可比价" | "报价偏离";
  value: string;
  context: string;
  evidenceRefs: string[];
  factVersionId: string | null;
  sourceLabel?: string;
}

export function deriveTransactionPriceVerification(current: FinancedEquipmentLine): TransactionPriceVerificationItem[] {
  const price = derivePriceBenchmark(current.priceBenchmark, current.contractUnitPrice);
  const amount = (value: number) => `${value.toLocaleString("zh-CN")} 元`;
  return [
    { id: `${current.id}-contract-price`, label: "合同价", value: amount(current.contractUnitPrice), context: current.contractQuoteSource, evidenceRefs: current.contractEvidenceRefs, factVersionId: null },
    { id: `${current.id}-supplier-quote`, label: "供应商报价", value: "待结构化", context: current.supplierQuoteEvidenceRefs.length ? "已关联报价材料" : "材料待补", evidenceRefs: current.supplierQuoteEvidenceRefs, factVersionId: null, sourceLabel: current.supplierQuoteSource },
    { id: `${current.id}-comparable-price`, label: "可比价", value: current.priceBenchmark.median === null ? "待核验" : amount(current.priceBenchmark.median), context: current.priceBenchmark.sampleLabel, evidenceRefs: current.priceBenchmark.evidenceRefs, factVersionId: current.priceBenchmark.factVersionId },
    { id: `${current.id}-price-deviation`, label: "报价偏离", value: price.status === "available" ? `${price.deviationPercent > 0 ? "+" : ""}${price.deviationPercent}%` : "待核验", context: price.message, evidenceRefs: current.priceBenchmark.evidenceRefs, factVersionId: current.priceBenchmark.factVersionId },
  ];
}

export function materialTabPresentation(material: Pick<Material, "kind" | "fileName">) {
  const extension = /(?:\.([^.]+))?$/u.exec(material.fileName)?.[1]?.toUpperCase() ?? "";
  const label = material.kind === "excel" ? "业务数据"
    : material.kind === "image" ? "设备图片"
      : material.kind === "pdf" ? "主体核验" : "原始材料";
  return { label, extension: extension ? `.${extension}` : "" };
}

export type FinancingBreakdown =
  | { status: "available"; contractTotal: number; downPaymentAmount: number; financedAmount: number; downPaymentPercent: number; financedPercent: number }
  | { status: "invalid"; message: string };

export function deriveFinancingBreakdown(contractTotal: number, downPaymentAmount: number): FinancingBreakdown {
  if (!Number.isFinite(contractTotal) || !Number.isFinite(downPaymentAmount) || contractTotal <= 0 || downPaymentAmount < 0 || downPaymentAmount > contractTotal) {
    return { status: "invalid", message: "融资构成金额口径无效，无法形成比例。" };
  }
  const financedAmount = contractTotal - downPaymentAmount;
  return {
    status: "available",
    contractTotal,
    downPaymentAmount,
    financedAmount,
    downPaymentPercent: round1(downPaymentAmount / contractTotal * 100),
    financedPercent: round1(financedAmount / contractTotal * 100),
  };
}

export function variancePresentation(value: number) {
  if (!Number.isFinite(value)) return { sign: "", tone: "invalid" as const, label: "不可用" };
  if (value > 0) return { sign: "+", tone: "higher" as const, label: `+${value.toLocaleString("zh-CN")} 元` };
  if (value < 0) return { sign: "−", tone: "lower" as const, label: `−${Math.abs(value).toLocaleString("zh-CN")} 元` };
  return { sign: "", tone: "equal" as const, label: "0 元" };
}

export type ProductionGranularity = "week" | "month" | "quarter";

function isoDate(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`));
}

function timeBucket(dateText: string, grain: DimensionSeriesRequest["grain"]) {
  const date = new Date(`${dateText}T00:00:00Z`);
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth();
  const day = date.getUTCDate();
  const iso = (value: Date) => value.toISOString().slice(0, 10);
  if (grain === "day") return { id: dateText, label: dateText.slice(5), start: dateText, end: dateText };
  if (grain === "week") {
    const mondayOffset = (date.getUTCDay() + 6) % 7;
    const start = new Date(Date.UTC(year, month, day - mondayOffset));
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + 6);
    return { id: iso(start), label: `${iso(start).slice(5)}周`, start: iso(start), end: iso(end) };
  }
  if (grain === "month") {
    const start = new Date(Date.UTC(year, month, 1));
    const end = new Date(Date.UTC(year, month + 1, 0));
    return { id: `${year}-${String(month + 1).padStart(2, "0")}`, label: `${year}年${month + 1}月`, start: iso(start), end: iso(end) };
  }
  return { id: String(year), label: String(year), start: `${year}-01-01`, end: `${year}-12-31` };
}

export function aggregateDimensionTimeSeries(series: DimensionTimeSeries | undefined, request: DimensionSeriesRequest): DimensionSeriesResponse {
  const unavailable = (status: "empty" | "invalid" | "unavailable", message: string): DimensionSeriesResponse => ({
    status,
    request: { ...request, metricIds: [...request.metricIds] },
    points: [],
    message,
    sourceLabel: series?.sourceLabel ?? "统一脱敏时序数据",
    isSimulated: true,
  });
  if (!series || series.dimensionId !== request.dimensionId) return unavailable("unavailable", "当前维度没有可用的时序接口。");
  if (!series.supportedGrains.includes(request.grain)) return unavailable("unavailable", `当前维度不适用${request.grain}粒度。`);
  if (!request.timezone.trim()) return unavailable("invalid", "时区不能为空。");
  if ((request.startDate && !isoDate(request.startDate)) || (request.endDate && !isoDate(request.endDate)) || (request.startDate && request.endDate && request.startDate > request.endDate)) {
    return unavailable("invalid", "起止日期范围无效。");
  }
  const metricById = new Map(series.metrics.map((metric) => [metric.id, metric]));
  const metricIds = [...new Set(request.metricIds)];
  if (!metricIds.length || metricIds.some((metricId) => !metricById.has(metricId))) return unavailable("invalid", "请求包含未知或空指标。");
  const validObservations = series.observations.every((item) => isoDate(item.date)
    && metricById.has(item.metricId)
    && Number.isFinite(item.value)
    && item.evidenceRefs.length > 0);
  if (!validObservations) return unavailable("invalid", "时序记录缺少合法日期、数值或证据引用。");
  const observations = [...series.observations]
    .filter((item) => metricIds.includes(item.metricId)
      && (!request.startDate || item.date >= request.startDate)
      && (!request.endDate || item.date <= request.endDate))
    .sort((left, right) => left.date.localeCompare(right.date) || left.metricId.localeCompare(right.metricId));
  if (!observations.length) return unavailable("empty", "所选日期范围没有可验证记录。");
  const buckets = new Map<string, { label: string; start: string; end: string; observations: typeof observations }>();
  for (const observation of observations) {
    const bucket = timeBucket(observation.date, request.grain);
    const current = buckets.get(bucket.id) ?? { label: bucket.label, start: bucket.start, end: bucket.end, observations: [] };
    current.observations.push(observation);
    buckets.set(bucket.id, current);
  }
  const points = [...buckets.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([bucketId, bucket]) => ({
    id: `timeseries-${series.dimensionId}-${request.grain}-${bucketId}`,
    label: bucket.label,
    note: `${bucket.start} 至 ${bucket.end} · ${series.sourceLabel}`,
    periodStart: bucket.start,
    periodEnd: bucket.end,
    measures: metricIds.map((metricId) => {
      const metric = metricById.get(metricId)!;
      const records = bucket.observations.filter((item) => item.metricId === metricId);
      const value = metric.aggregation === "sum"
        ? records.reduce((total, item) => total + item.value, 0)
        : metric.aggregation === "average"
          ? records.reduce((total, item) => total + item.value, 0) / Math.max(records.length, 1)
          : records.at(-1)?.value ?? 0;
      return {
        id: `timeseries-${series.dimensionId}-${request.grain}-${bucketId}-${metricId}`,
        label: metric.label,
        value: round1(value),
        unit: metric.unit,
        evidenceRefs: [...new Set(records.flatMap((item) => item.evidenceRefs))],
      };
    }),
  }));
  return {
    status: "available",
    request: { ...request, metricIds },
    points,
    sourceLabel: series.sourceLabel,
    isSimulated: true,
  };
}

export function productionSeriesStatus(series: ProductionEnergySeries): { status: "available" | "missing" | "invalid" | "unavailable"; message: string } {
  if (series.status !== "available") return { status: series.status, message: series.message || "生产序列不可用。" };
  if (!series.points.length) return { status: "missing", message: series.message || "生产序列没有记录。" };
  if (series.electricityMetric !== "usage" || series.electricityUnit !== "kWh" || series.outputMetric !== "absolute" || series.outputUnit !== "件" || series.aggregation !== "sum") {
    return { status: "invalid", message: "生产序列的字段、单位或聚合口径无效。" };
  }
  return { status: "available", message: series.message };
}

export interface AggregatedProductionPoint {
  id: string;
  label: string;
  electricity: number;
  output: number;
  electricityEvidenceRefs: string[];
  outputEvidenceRefs: string[];
}

export type ProductionAggregation =
  | { status: "available"; points: AggregatedProductionPoint[] }
  | { status: "empty" | "missing" | "invalid" | "unavailable"; message: string; points: [] };

function productionBucket(date: Date, granularity: Exclude<ProductionGranularity, "week">) {
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth() + 1;
  if (granularity === "month") return { id: `${year}-${String(month).padStart(2, "0")}`, label: `${year}年${month}月` };
  const quarter = Math.floor((month - 1) / 3) + 1;
  return { id: `${year}-Q${quarter}`, label: `${year}年Q${quarter}` };
}

export function aggregateProductionEnergy(
  points: readonly ProductionEnergyPoint[],
  granularity: ProductionGranularity,
  startDate = "",
  endDate = "",
): ProductionAggregation {
  if (granularity === "week") return { status: "unavailable", message: "当前材料仅有月度记录，周粒度不可用。", points: [] };
  if (startDate && endDate && startDate > endDate) return { status: "invalid", message: "起止日期范围无效。", points: [] };
  const valid = points.every((point) => /^\d{4}-\d{2}-\d{2}$/.test(point.date)
    && Number.isFinite(Date.parse(`${point.date}T00:00:00Z`))
    && Number.isFinite(point.electricity)
    && Number.isFinite(point.output)
    && point.electricity >= 0
    && point.output >= 0
    && point.electricityEvidenceRefs.length > 0
    && point.outputEvidenceRefs.length > 0);
  if (!valid) return { status: "invalid", message: "生产序列缺少合法日期、单位数值或证据引用。", points: [] };
  const filtered = points.filter((point) => (!startDate || point.date >= startDate) && (!endDate || point.date <= endDate));
  if (!filtered.length) return { status: "empty", message: "所选日期范围没有可验证的用电与产量记录。", points: [] };
  const grouped = new Map<string, AggregatedProductionPoint>();
  for (const point of filtered) {
    const bucket = productionBucket(new Date(`${point.date}T00:00:00Z`), granularity);
    const current = grouped.get(bucket.id) ?? { id: `production-${granularity}-${bucket.id}`, label: bucket.label, electricity: 0, output: 0, electricityEvidenceRefs: [], outputEvidenceRefs: [] };
    current.electricity += point.electricity;
    current.output += point.output;
    current.electricityEvidenceRefs.push(...point.electricityEvidenceRefs.filter((id) => !current.electricityEvidenceRefs.includes(id)));
    current.outputEvidenceRefs.push(...point.outputEvidenceRefs.filter((id) => !current.outputEvidenceRefs.includes(id)));
    grouped.set(bucket.id, current);
  }
  return { status: "available", points: [...grouped.values()] };
}

export function sanitizePersistedLayout(value: unknown, fallback: LayoutState | ResponsiveLayoutState): PersistedLayout {
  const input = value && typeof value === "object" ? value as Partial<ResponsiveLayoutState> : {};
  const dimension = typeof input.activeDimensionId === "string" && DIMENSION_IDS.includes(input.activeDimensionId as DimensionId)
    ? input.activeDimensionId as DimensionId
    : fallback.activeDimensionId;
  const navigationWidth = typeof input.navigationWidth === "number" && Number.isFinite(input.navigationWidth)
    ? clamp(input.navigationWidth, ...LAYOUT_LIMITS.navigationWidth)
    : fallback.navigationWidth;
  const ratio = (key: "materialRatio" | "collaborationRatio") => {
    const candidate = input[key];
    const responsiveFallback = fallback as Partial<ResponsiveLayoutState>;
    const fallbackRatio = typeof responsiveFallback[key] === "number"
      ? responsiveFallback[key]
      : DEFAULT_LAYOUT_RATIOS[key];
    return typeof candidate === "number" && Number.isFinite(candidate)
      ? clamp(candidate, ...LAYOUT_LIMITS[key])
      : fallbackRatio;
  };
  return {
    navigationWidth,
    materialWidth: fallback.materialWidth,
    collaborationHeight: fallback.collaborationHeight,
    materialRatio: ratio("materialRatio"),
    collaborationRatio: ratio("collaborationRatio"),
    navigationCollapsed: input.navigationCollapsed === true,
    middleCollapsed: input.middleCollapsed === true,
    materialCollapsed: input.materialCollapsed === true,
    collaborationCollapsed: input.collaborationCollapsed === true,
    businessCollapsed: input.businessCollapsed === true,
    policyCollapsed: input.policyCollapsed === true,
    riskCollapsed: input.riskCollapsed === true,
    activeDimensionId: dimension,
  };
}

export function persistedLayoutFrom(state: ResponsiveLayoutState): PersistedLayout {
  return sanitizePersistedLayout(state, state);
}

export interface SectionPosition {
  id: DimensionId;
  top: number;
}

export function activeDimensionFromPositions(positions: SectionPosition[], threshold = 136): DimensionId {
  if (positions.length === 0) return "compliance";
  const sorted = [...positions].sort((left, right) => left.top - right.top);
  return sorted.reduce((active, candidate) => candidate.top <= threshold ? candidate.id : active, sorted[0].id);
}

export interface ExcelRangeBounds {
  startColumn: number;
  endColumn: number;
  startRow: number;
  endRow: number;
}

function excelColumnIndex(letters: string) {
  return [...letters.toUpperCase()].reduce(
    (value, character) => value * 26 + character.charCodeAt(0) - 64,
    0,
  );
}

export function parseExcelRange(range: string): ExcelRangeBounds | null {
  const match = /^([A-Z]+)(\d+):([A-Z]+)(\d+)$/i.exec(range.trim());
  if (!match) return null;
  const firstColumn = excelColumnIndex(match[1]);
  const secondColumn = excelColumnIndex(match[3]);
  const firstRow = Number(match[2]);
  const secondRow = Number(match[4]);
  if (firstColumn < 1 || secondColumn < 1 || firstRow < 1 || secondRow < 1) return null;
  return {
    startColumn: Math.min(firstColumn, secondColumn),
    endColumn: Math.max(firstColumn, secondColumn),
    startRow: Math.min(firstRow, secondRow),
    endRow: Math.max(firstRow, secondRow),
  };
}

export function excelRangeContains(range: string, columnIndex: number, rowNumber: number) {
  const bounds = parseExcelRange(range);
  return !!bounds
    && columnIndex >= bounds.startColumn
    && columnIndex <= bounds.endColumn
    && rowNumber >= bounds.startRow
    && rowNumber <= bounds.endRow;
}

export function excelRangeScrollTarget(range: string) {
  const bounds = parseExcelRange(range);
  return bounds ? { column: bounds.startColumn, row: bounds.startRow } : null;
}

export type EvidenceResolution =
  | { status: "located"; evidence: EvidenceReference; material: Material }
  | { status: "pending" | "unverifiable" | "version_mismatch" | "missing_evidence" | "missing_material" | "invalid_locator"; evidence: EvidenceReference | null; material: Material | null; message: string };

export type EvidenceSelectionResolution =
  | {
      status: "located";
      selectionGroup: ReviewEvidenceSelectionGroup;
      items: Array<{ target: ReviewEvidenceTarget; evidence: EvidenceReference; material: Material }>;
    }
  | {
      status: "pending" | "unverifiable" | "version_mismatch" | "missing_evidence" | "missing_material" | "invalid_locator";
      selectionGroup: ReviewEvidenceSelectionGroup;
      items: [];
      failedTarget: ReviewEvidenceTarget;
      evidence: EvidenceReference | null;
      material: Material | null;
      message: string;
    };

export function materialIdForEvidenceResolution(resolution: EvidenceResolution) {
  return resolution.status === "located" ? resolution.material.id : "";
}

export function resolveEvidenceSelectionGroup(
  selectionGroup: ReviewEvidenceSelectionGroup,
  evidenceList: EvidenceReference[],
  materials: Material[],
): EvidenceSelectionResolution {
  const located: Array<{ target: ReviewEvidenceTarget; evidence: EvidenceReference; material: Material }> = [];
  for (const target of selectionGroup.targets) {
    const resolution = resolveEvidence(target.evidenceRef, evidenceList, materials);
    if (resolution.status !== "located") {
      return {
        status: resolution.status,
        selectionGroup,
        items: [],
        failedTarget: target,
        evidence: resolution.evidence,
        material: resolution.material,
        message: `选择组定位失败：${resolution.message}`,
      };
    }
    located.push({ target, evidence: resolution.evidence, material: resolution.material });
  }
  return { status: "located", selectionGroup, items: located };
}

export function materialHitCounts(resolution: EvidenceSelectionResolution | null) {
  if (!resolution || resolution.status !== "located") return {} as Record<string, number>;
  return resolution.items.reduce<Record<string, number>>((counts, item) => {
    counts[item.material.id] = (counts[item.material.id] ?? 0) + 1;
    return counts;
  }, {});
}

function validNormalizedBBox(bbox: { x: number; y: number; width: number; height: number }) {
  return [bbox.x, bbox.y, bbox.width, bbox.height].every(Number.isFinite)
    && bbox.x >= 0
    && bbox.y >= 0
    && bbox.width > 0
    && bbox.height > 0
    && bbox.x + bbox.width <= 1
    && bbox.y + bbox.height <= 1;
}

export function validEvidenceLocator(evidence: EvidenceReference, material: Material) {
  const locator = evidence.locator;
  if (!locator || locator.materialId !== material.id || locator.materialVersionId !== material.versionId || material.availability !== "available") return false;
  if (locator.kind === "excel") {
    if (material.kind !== "excel") return false;
    const sheet = material.sheets.find((item) => item.name === locator.sheet);
    const bounds = parseExcelRange(locator.range);
    if (!sheet || !bounds || bounds.startRow < 4 || bounds.endRow > sheet.rows.length + 3 || bounds.endColumn > sheet.columns.length) return false;
    return sheet.rows
      .slice(bounds.startRow - 4, bounds.endRow - 3)
      .every((row) => row.length >= bounds.endColumn);
  }
  if (locator.kind === "pdf") {
    return material.kind === "pdf"
      && locator.page >= 1
      && locator.page <= material.pageCount
      && material.pages.some((page) => page.page === locator.page)
      && validNormalizedBBox(locator.bbox);
  }
  if (locator.kind === "image") return material.kind === "image" && validNormalizedBBox(locator.bbox);
  if (locator.kind === "media") {
    return material.kind === "media"
      && Number.isFinite(locator.startSeconds)
      && Number.isFinite(locator.endSeconds)
      && locator.startSeconds >= 0
      && locator.endSeconds >= locator.startSeconds
      && (material.durationSeconds === null
        ? locator.startSeconds === 0 && locator.endSeconds === 0
        : locator.endSeconds <= material.durationSeconds);
  }
  if (material.kind !== "scene" || locator.pointIds.length === 0 || new Set(locator.pointIds).size !== locator.pointIds.length) return false;
  const availablePoints = new Set(material.points.map((point) => point.id));
  return locator.pointIds.every((pointId) => availablePoints.has(pointId));
}

export function resolveEvidence(
  evidenceId: string,
  evidenceList: EvidenceReference[],
  materials: Material[],
): EvidenceResolution {
  const evidence = evidenceList.find((item) => item.id === evidenceId) ?? null;
  if (!evidence) return { status: "missing_evidence", evidence: null, material: null, message: "未找到对应证据引用。" };
  if (!evidence.locator) return { status: evidence.locationStatus === "pending" ? "pending" : "unverifiable", evidence, material: null, message: evidence.locationStatus === "pending" ? "证据尚未完成定位。" : "证据无法可靠定位。" };
  const material = materials.find((item) => item.id === evidence.locator?.materialId) ?? null;
  if (!material) return { status: "missing_material", evidence, material: null, message: "证据所指材料不存在。" };
  if (material.versionId !== evidence.locator.materialVersionId || evidence.locationStatus === "version_mismatch") {
    return { status: "version_mismatch", evidence, material, message: "证据与当前材料版本不一致。" };
  }
  if (evidence.locationStatus !== "located") return { status: evidence.locationStatus, evidence, material, message: "证据无法可靠定位。" };
  if (!validEvidenceLocator(evidence, material)) return { status: "invalid_locator", evidence, material, message: "定位范围超出当前材料可核验边界。" };
  return { status: "located", evidence, material };
}

export function createCorrectedFact(
  current: FactVersion,
  input: BusinessCorrectionInput,
  sequence: number,
): FactVersion {
  return {
    ...current,
    id: `${current.factKey.replaceAll(".", "-")}-v${current.version + 1}-${sequence}`,
    version: current.version + 1,
    value: input.proposedValue,
    source: "mock_business_correction",
    evidenceRefs: [...input.evidenceRefs],
    createdAt: new Date().toISOString(),
    isSimulated: true,
  };
}

export function appendImmutableEvent<T extends CommonReviewEvent>(events: T[], event: T): T[] {
  const nextSequence = Math.max(0, ...events.map((item) => item.sequence)) + 1;
  return [{ ...event, sequence: nextSequence, immutable: true as const }, ...events] as T[];
}
