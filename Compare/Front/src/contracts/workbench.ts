export const DIMENSION_IDS = [
  "compliance",
  "transaction",
  "production",
  "revenue",
  "debt",
  "cashflow",
] as const;

export type DimensionId = (typeof DIMENSION_IDS)[number];
export type ScoreGrade = "A" | "B" | "C" | "D" | "E";
export type DecisionGrade = ScoreGrade;
export type DataStatus = "simulated" | "loading" | "empty" | "error";
export type LocalMaterialStatus = "confirmed" | "review" | "conflict";
export type MaterialAvailability = "available" | "processing" | "missing" | "error";
export type MaterialOriginalAccessStatus = "available" | "not_configured" | "invalid_root" | "not_imported" | "integrity_mismatch";
export const MATERIAL_BUSINESS_FOLDERS = ["基本证照", "经营证明", "现场照片", "增信", "租赁标的"] as const;
export type MaterialBusinessFolder = (typeof MATERIAL_BUSINESS_FOLDERS)[number];
export type MaterialRole = "original" | "derived";
export type EvidenceLocationStatus = "located" | "pending" | "unverifiable" | "version_mismatch";
export type RiskLevel = "support" | "attention" | "confirm" | "risk" | "forbid";

export interface MaterialOriginalAccess {
  status: MaterialOriginalAccessStatus;
  available: boolean;
}

export interface DimensionDefinition {
  id: DimensionId;
  index: 1 | 2 | 3 | 4 | 5 | 6;
  name: "合规" | "交易" | "生产" | "营收" | "负债" | "流水";
  fullName: string;
  score: number;
  scoreGrade: ScoreGrade;
  confidence: number;
  summary: string;
}

export type AssessmentTone = "positive" | "neutral" | "attention" | "critical";
export type DimensionViewMode = "visual" | "table";
export type DimensionVisualKind =
  | "subject-network"
  | "transaction-structure"
  | "production-series"
  | "revenue-series"
  | "debt-structure"
  | "cashflow-series";

export interface DimensionMetric {
  id: string;
  label: string;
  value: string;
  note: string;
  tone: AssessmentTone;
  evidenceRefs: string[];
}

export interface DimensionSeriesMeasure {
  id: string;
  label: string;
  value: number;
  unit: string;
  evidenceRefs: string[];
  comparisonEvidenceRefs?: string[];
}

export interface DimensionSeriesPoint {
  id: string;
  label: string;
  measures: DimensionSeriesMeasure[];
  note?: string;
}

export interface DimensionSeriesGroup {
  id: string;
  label: string;
  points: DimensionSeriesPoint[];
}

export type TimeGrain = "day" | "week" | "month" | "year";
export type TimeAggregation = "sum" | "average" | "last";

export interface DimensionSeriesRequest {
  projectId: string;
  dimensionId: DimensionId;
  metricIds: string[];
  grain: TimeGrain;
  startDate: string;
  endDate: string;
  timezone: string;
}

export interface DimensionTimeMetric {
  id: string;
  label: string;
  unit: string;
  aggregation: TimeAggregation;
}

export interface DimensionTimeObservation {
  id: string;
  date: string;
  metricId: string;
  value: number;
  evidenceRefs: string[];
  isSimulated: true;
}

export interface DimensionTimeSeries {
  dimensionId: DimensionId;
  supportedGrains: TimeGrain[];
  metrics: DimensionTimeMetric[];
  observations: DimensionTimeObservation[];
  sourceLabel: string;
  isSimulated: true;
}

export type DimensionSeriesResponse =
  | {
      status: "available";
      request: DimensionSeriesRequest;
      points: Array<DimensionSeriesPoint & { periodStart: string; periodEnd: string }>;
      sourceLabel: string;
      isSimulated: true;
    }
  | {
      status: "empty" | "invalid" | "unavailable";
      request: DimensionSeriesRequest;
      points: [];
      message: string;
      sourceLabel: string;
      isSimulated: true;
    };

export interface DimensionBreakdownItem {
  id: string;
  label: string;
  value: string;
  detail: string;
  tone: AssessmentTone;
  evidenceRefs: string[];
}

export interface DimensionCompositionSegment {
  id: string;
  label: string;
  value: number;
  unit: string;
  note?: string;
  evidenceRefs: string[];
  tone: AssessmentTone;
}

export interface DimensionComposition {
  id: string;
  label: string;
  segments: DimensionCompositionSegment[];
}

export interface DimensionDetail {
  dimensionId: DimensionId;
  visual: DimensionVisualKind;
  defaultView: DimensionViewMode;
  availableViews: DimensionViewMode[];
  unit: string;
  metrics: DimensionMetric[];
  series: DimensionSeriesPoint[];
  seriesGroups?: DimensionSeriesGroup[];
  compositions?: DimensionComposition[];
  breakdown: DimensionBreakdownItem[];
  conclusion: string;
  sourceLabel: string;
  isSimulated: true;
}

export interface NormalizedBBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface BaseMaterial {
  id: string;
  versionId: string;
  fileName: string;
  label: string;
  availability: MaterialAvailability;
  isSimulated: true;
  sourceLabel: string;
  /** 服务端对受控外置原件的只读可用性，不改变材料/事实记录。 */
  originalAccess?: MaterialOriginalAccess;
  /** 用户提交时保留的业务相对路径，例如“经营证明/纳税申报表/2026-06.pdf”。 */
  businessPath?: string;
  /** businessPath 的首级业务目录；旧快照允许缺省，由前端仅作兼容归类。 */
  folderPath?: MaterialBusinessFolder | string;
  /** original 才能进入右侧原始材料树；OCR/locator/SceneSpec/GLB 等均为 derived。 */
  role?: MaterialRole;
  /** 当前项目与材料版本绑定的后端原件读取地址；assetUrl 仅保留给旧本地快照。 */
  originalUrl?: string;
}

export interface ExcelMaterial extends BaseMaterial {
  kind: "excel";
  mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  sheets: Array<{
    name: string;
    columns: string[];
    rows: Array<Array<string | number | null>>;
  }>;
}

export interface PdfMaterial extends BaseMaterial {
  kind: "pdf";
  mimeType: "application/pdf";
  pageCount: number;
  pages: Array<{
    page: number;
    title: string;
    lines: string[];
  }>;
}

export interface DocumentMaterial extends BaseMaterial {
  kind: "document";
  mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  description: string;
}

export interface ImageMaterial extends BaseMaterial {
  kind: "image";
  mimeType: "image/png" | "image/jpeg" | "image/webp";
  assetUrl?: string;
  pixelWidth: number;
  pixelHeight: number;
  description: string;
  focalArea: NormalizedBBox;
}

export interface MediaMaterial extends BaseMaterial {
  kind: "media";
  mimeType: "video/mp4" | "image/vnd.compare.panorama";
  mediaKind: "video" | "panorama";
  durationSeconds: number | null;
  description: string;
  posterMaterialId: string;
  /** 仅在用户选中材料后消费的受控原始媒体地址。 */
  assetUrl?: string;
}

export interface ScenePoint {
  id: string;
  x: number;
  y: number;
  z: number;
  size: number;
  color: string;
}

export interface SceneMaterial extends BaseMaterial {
  kind: "scene";
  mimeType: "application/vnd.compare.gaussian-scene+json" | "model/gltf-binary";
  sceneFormat: "compare-gaussian-preview-v1" | "glb";
  points: ScenePoint[];
  fallbackMaterialId: string;
  description: string;
  /** GLB 只作为受控附件下载；页面仍只渲染声明式 SceneSpec。 */
  assetUrl?: string;
}

export type Material = ExcelMaterial | PdfMaterial | DocumentMaterial | ImageMaterial | MediaMaterial | SceneMaterial;

interface BaseEvidenceLocator {
  materialId: string;
  materialVersionId: string;
}

export interface ExcelEvidenceLocator extends BaseEvidenceLocator {
  kind: "excel";
  sheet: string;
  range: string;
}

export interface PdfEvidenceLocator extends BaseEvidenceLocator {
  kind: "pdf";
  page: number;
  bbox: NormalizedBBox;
  textAnchor?: string;
}

export interface ImageEvidenceLocator extends BaseEvidenceLocator {
  kind: "image";
  bbox: NormalizedBBox;
}

export interface MediaEvidenceLocator extends BaseEvidenceLocator {
  kind: "media";
  startSeconds: number;
  endSeconds: number;
}

export interface SceneEvidenceLocator extends BaseEvidenceLocator {
  kind: "scene";
  pointIds: string[];
}

export type EvidenceLocator =
  | ExcelEvidenceLocator
  | PdfEvidenceLocator
  | ImageEvidenceLocator
  | MediaEvidenceLocator
  | SceneEvidenceLocator;

export interface EvidenceReference {
  id: string;
  label: string;
  locator: EvidenceLocator | null;
  locationStatus: EvidenceLocationStatus;
  materialStatus: LocalMaterialStatus;
}

export type FactValue = string | number | boolean | null;

export interface FactVersion {
  id: string;
  factKey: string;
  dimensionId: DimensionId;
  version: number;
  label: string;
  value: FactValue;
  unit: string | null;
  source: "mock_material_extract" | "mock_business_correction";
  evidenceRefs: string[];
  createdAt: string;
  isSimulated: true;
}

/**
 * One evidence reference and the exact review destination it supports.
 * `reviewTargetId` is a stable UI anchor; `factVersionId` is populated only
 * when the caller can prove that the evidence supports that FactVersion.
 */
export interface ReviewEvidenceTarget {
  evidenceRef: string;
  /** All references selected as one atomic group. The first item remains evidenceRef for compatibility. */
  evidenceRefs?: string[];
  dimensionId: DimensionId;
  reviewTargetId: string | null;
  factVersionId: string | null;
  unavailableReason?: string;
}

export interface ReviewEvidenceSelectionGroup {
  id: string;
  dimensionId: DimensionId;
  reviewTargetId: string | null;
  factVersionId: string | null;
  targets: ReviewEvidenceTarget[];
}

export interface ComplianceSubjectNode {
  id: string;
  kind: "company" | "person";
  name: string;
  role: string;
  verificationStatus: LocalMaterialStatus;
  evidenceRefs: string[];
}

export interface ComplianceSubjectRelation {
  id: string;
  fromId: string;
  toId: string;
  relation: "shareholding" | "legal_representative" | "controller" | "affiliate" | "transaction";
  /** Numeric ownership supplied by the normalized fact source. Never parse it from label text. */
  sharePercent?: number;
  label: string;
  verificationStatus: LocalMaterialStatus;
  evidenceRefs: string[];
}

export interface ComplianceSubjectAttachment {
  id: string;
  subjectId: string;
  factVersionId: string;
  label: string;
  verificationStatus: LocalMaterialStatus;
  evidenceRefs: string[];
}

export interface ComplianceSubjectGraph {
  nodes: ComplianceSubjectNode[];
  relations: ComplianceSubjectRelation[];
  attachments: ComplianceSubjectAttachment[];
  sourceLabel: string;
  isSimulated: true;
}

export type EquipmentModelKind = "turning-center" | "sliding-head-lathe" | "machining-center";

export interface EquipmentModelPreset {
  kind: EquipmentModelKind;
  width: number;
  height: number;
  depth: number;
  spindleCount: number;
  axisCount: number;
  accent: string;
}

export type AvailabilityState = "available" | "missing" | "invalid" | "unavailable";

export interface EquipmentPriceBenchmark {
  status: AvailabilityState;
  priceBasis: "per_unit";
  low: number | null;
  median: number | null;
  high: number | null;
  sampleLabel: string;
  message: string;
  unit: "元/台";
  sourceLabel: string;
  factVersionId: string | null;
  evidenceRefs: string[];
}

export interface EquipmentConfigurationRow {
  id: string;
  factVersionId: string | null;
  label: string;
  unit: string;
  current: string;
  median: string;
  range: string;
  sourceLabel: string;
  tone: "positive" | "neutral" | "attention" | "risk";
  evidenceRefs: string[];
}

export interface EquipmentConfigurationComparison {
  status: AvailabilityState;
  message: string;
  rows: EquipmentConfigurationRow[];
}

export type TransactionRating = "A级" | "B级" | "C级" | "D级" | "E级";

export interface TransactionRepaymentPoint {
  id: string;
  period: number;
  principal: number;
  interest: number;
  rent: number;
  evidenceRefs: string[];
  isSimulated: true;
}

export interface TransactionRepaymentSchedule {
  status: AvailabilityState;
  termMonths: number;
  amountUnit: "元";
  points: TransactionRepaymentPoint[];
  firstPaymentEvidenceRefs: string[];
  firstTwelveEvidenceRefs: string[];
  totalRentEvidenceRefs: string[];
  termEvidenceRefs: string[];
  message: string;
  sourceLabel: string;
  isSimulated: true;
}

export interface FinancedEquipmentLine {
  id: string;
  equipment: string;
  brand: string;
  model: string;
  quantity: number;
  contractUnitPrice: number;
  supplier: string;
  contractQuoteSource: string;
  supplierQuoteSource: string;
  imageId: string;
  /** 当前设备多角度原件 Material.id；imageId 继续作为主图以兼容旧快照。 */
  imageIds?: string[];
  /** 铭牌原件 Material.id。 */
  nameplateMaterialId?: string | null;
  /** 后端派生的受控 3D 引用，不属于原始材料。 */
  derivedModelRef?: string | null;
  modelPreset: EquipmentModelPreset;
  priceBenchmark: EquipmentPriceBenchmark;
  configuration: EquipmentConfigurationComparison;
  supplierRating?: TransactionRating;
  supplierRatingEvidenceRefs?: string[];
  brandRating?: TransactionRating;
  brandRatingEvidenceRefs?: string[];
  contractEvidenceRefs: string[];
  supplierQuoteEvidenceRefs: string[];
}

export interface FinancedEquipmentLedger {
  currency: "CNY";
  amountUnit: "元";
  lines: FinancedEquipmentLine[];
  transactionStructure: "direct-lease" | "sale-and-leaseback";
  lessor: string;
  termMonths: number;
  downPaymentAmount: number;
  financingPlanEvidenceRefs: string[];
  projectAmountEvidenceRefs: string[];
  financingRatioEvidenceRefs: string[];
  partyRelationshipEvidenceRefs: string[];
  totalContractEvidenceRefs: string[];
  repaymentSchedule: TransactionRepaymentSchedule;
  sourceLabel: string;
  isSimulated: true;
}

export interface OperatingEquipmentStatus {
  id: string;
  equipment: string;
  model: string;
  operatingQuantity: number;
  status: "operating" | "maintenance" | "idle";
  utilization: string;
  ratedCapacity: string;
  processUse: string;
  evidenceRefs: string[];
  sourceLabel: string;
  isSimulated: true;
}

export type ProductionStageId = "raw-material" | "process" | "finished-product";

export interface ProductionStage {
  id: string;
  stage: ProductionStageId;
  title: string;
  summary: string;
  fields: Array<{ label: string; value: string }>;
  imageIds: string[];
  evidenceRefs: string[];
  sourceLabel: string;
  isSimulated: true;
}

export interface ProductionEnergyPoint {
  id: string;
  date: string;
  label: string;
  electricity: number;
  output: number;
  electricityEvidenceRefs: string[];
  outputEvidenceRefs: string[];
  isSimulated: true;
}

export interface ProductionEnergySeries {
  status: AvailabilityState;
  electricityMetric: "usage";
  electricityUnit: "kWh";
  outputMetric: "absolute";
  outputUnit: "件";
  aggregation: "sum";
  points: ProductionEnergyPoint[];
  message: string;
  sourceLabel: string;
  isSimulated: true;
}

export type PublicReferenceCategory = "equipment" | ProductionStageId;

export interface PublicReferenceImage {
  id: string;
  category: PublicReferenceCategory;
  src: string;
  title: string;
  description: string;
  author: string;
  originUrl: string;
  license: string;
  licenseUrl: string;
  usage: string;
  isEvidence: false;
}

export interface OnsiteAsset {
  id: string;
  label: string;
  kind: "image" | "supplement" | "video" | "panorama" | "equipment_point" | "scene_3dgs";
  collectionStatus: "collected" | "processing" | "pending" | "failed";
  materialId: string | null;
  sourceLabel: string;
  evidenceRefs: string[];
  lazyLoad: boolean;
  isSimulated: true;
}

export interface BusinessCorrection {
  id: string;
  projectId: string;
  factKey: string;
  fromFactVersionId: string;
  proposedValue: FactValue;
  reason: string;
  evidenceRefs: string[];
  status: "draft" | "submitted" | "accepted" | "rejected";
  createdBy: "business";
  createdAt: string;
  isSimulated: true;
}

/** The correction, immutable fact version and review event are one server transaction. */
export interface BusinessCorrectionResult {
  correction: BusinessCorrection;
  factVersion: FactVersion;
  event: CommonReviewEvent;
}

export interface HardConstraintResult {
  id: string;
  ruleId: string;
  ruleVersion: string;
  title: string;
  result: "pass" | "block" | "manual_review";
  evidenceTargets: ReviewEvidenceTarget[];
  primaryTarget: ReviewEvidenceTarget | null;
  scope: string;
  evidenceRequirement: string;
  gateTriggered: boolean;
  responsibleParty: "business" | "risk" | "joint";
  nextAction: string;
  explanation: string;
  evaluatedAt: string;
  isSimulated: true;
}

export interface RiskSummaryItem {
  id: string;
  title: string;
  detail: string;
  level: RiskLevel;
  evidenceTargets: ReviewEvidenceTarget[];
  primaryTarget: ReviewEvidenceTarget | null;
  responsibleParty: "business" | "risk" | "joint";
  nextAction: string;
  isSimulated: true;
}

export interface GlobalRiskSummary {
  id: string;
  name: "风险";
  level: RiskLevel;
  scoreGrade: ScoreGrade;
  decisionGrade: DecisionGrade;
  confidence: number;
  summary: string;
  evidenceRefs: string[];
  hardConstraintResults: HardConstraintResult[];
  keyAnomalies: RiskSummaryItem[];
  pendingHumanDeterminations: RiskSummaryItem[];
  isSimulated: true;
}

export interface SoftRecommendation {
  id: string;
  dimensionId: DimensionId;
  title: string;
  recommendation: string;
  confidence: number;
  evidenceRefs: string[];
  advisoryOnly: true;
  isSimulated: true;
}

export interface RiskDetermination {
  id: string;
  dimensionId: DimensionId;
  score: number;
  scoreGrade: ScoreGrade;
  decisionGrade: DecisionGrade;
  confidence: number;
  conclusion: string;
  evidenceRefs: string[];
  hardConstraintResults: HardConstraintResult[];
  softRecommendations: SoftRecommendation[];
  isSimulated: true;
}

export type ReviewActor = "business" | "risk" | "system";

export interface CommonReviewEvent {
  id: string;
  projectId: string;
  sequence: number;
  threadId: string;
  replyToEventId: string | null;
  issueStatus: "open" | "answered" | "pending_gate" | "resolved";
  eventType:
    | "fact_version_created"
    | "business_correction_submitted"
    | "risk_question_submitted"
    | "risk_answer_submitted"
    | "business_answer_submitted"
    | "issue_opened"
    | "policy_result_recorded";
  actor: ReviewActor;
  actorLabel: string;
  dimensionId: DimensionId;
  /**
   * Authoritative evidence-to-target mapping. It is optional only on the
   * frozen gateway transport; events stored in WorkbenchProject use
   * MappedCommonReviewEvent and always provide it.
   */
  evidenceTargets?: ReviewEvidenceTarget[];
  /** Compatibility projections derived from evidenceTargets. UI must not infer pairing from them. */
  reviewTargetId: string | null;
  title: string;
  summary: string;
  factVersionIds: string[];
  evidenceRefs: string[];
  ruleRefs: string[];
  createdAt: string;
  immutable: true;
  isSimulated: true;
}

export type MappedCommonReviewEvent = CommonReviewEvent & {
  evidenceTargets: ReviewEvidenceTarget[];
};

export interface LayoutState {
  navigationWidth: number;
  materialWidth: number;
  collaborationHeight: number;
  navigationCollapsed: boolean;
  middleCollapsed: boolean;
  materialCollapsed: boolean;
  collaborationCollapsed: boolean;
  businessCollapsed: boolean;
  policyCollapsed: boolean;
  riskCollapsed: boolean;
  activeDimensionId: DimensionId;
}

export interface ProjectSummary {
  id: string;
  name: string;
  materialCount: number;
  collaborationIssueCount: number;
  dataStatus: DataStatus;
  disclaimer: string;
  isSimulated: true;
}

export interface WorkbenchProject {
  project: ProjectSummary;
  riskSummary: GlobalRiskSummary;
  dimensions: DimensionDefinition[];
  dimensionDetails: DimensionDetail[];
  materials: Material[];
  evidence: EvidenceReference[];
  facts: FactVersion[];
  complianceGraph: ComplianceSubjectGraph;
  financedEquipment: FinancedEquipmentLedger;
  operatingEquipment: OperatingEquipmentStatus[];
  productionStages: ProductionStage[];
  productionEnergy: ProductionEnergySeries;
  referenceImages: PublicReferenceImage[];
  onsiteAssets: OnsiteAsset[];
  corrections: BusinessCorrection[];
  determinations: RiskDetermination[];
  reviewEvents: MappedCommonReviewEvent[];
  layout: LayoutState;
}

export interface BusinessCorrectionInput {
  projectId: string;
  factKey: string;
  fromFactVersionId: string;
  proposedValue: FactValue;
  reason: string;
  evidenceRefs: string[];
  /** M2 supplies the server version and idempotency key; M1 does not write. */
  expectedVersion?: number;
  idempotencyKey?: string;
}

export interface RiskQuestionInput {
  projectId: string;
  dimensionId: DimensionId;
  question: string;
  evidenceTargets: ReviewEvidenceTarget[];
  reviewTargetId: string | null;
  threadId: string;
  replyToEventId: string | null;
  factVersionIds: string[];
  evidenceRefs: string[];
  expectedVersion?: number;
  idempotencyKey?: string;
}

export interface BusinessAnswerInput {
  projectId: string;
  dimensionId: DimensionId;
  answer: string;
  evidenceTargets: ReviewEvidenceTarget[];
  reviewTargetId: string | null;
  threadId: string;
  replyToEventId: string | null;
  factVersionIds: string[];
  evidenceRefs: string[];
  expectedVersion?: number;
  idempotencyKey?: string;
}

export interface RiskAnswerInput {
  projectId: string;
  dimensionId: DimensionId;
  answer: string;
  evidenceTargets: ReviewEvidenceTarget[];
  reviewTargetId: string | null;
  threadId: string;
  replyToEventId: string | null;
  factVersionIds: string[];
  evidenceRefs: string[];
  expectedVersion?: number;
  idempotencyKey?: string;
}

export interface CollaborationSubmissionResult {
  event: CommonReviewEvent;
  openIssueCount: number;
}

export type ApprovalStatus = "draft" | "returned" | "submitted" | "completed";
export type ApprovalTransition = "save_draft" | "return" | "submit" | "complete";
export type ApprovalActorRole = "business" | "risk" | "leadership";

export interface ApprovalState {
  projectId: string;
  version: number;
  status: ApprovalStatus;
  hardGateStatus: "pass" | "block" | "manual_review";
  blockingRuleIds: string[];
  riskVeto: boolean;
  riskVetoRuleIds: string[];
  updatedAt: string;
  isSimulated: true;
}

export interface ApprovalTransitionInput {
  expectedVersion: number;
  transition: ApprovalTransition;
  requestedBy: ApprovalActorRole;
  reason?: string;
  idempotencyKey?: string;
}

export type GatewayErrorCode = "not_found" | "validation" | "conflict" | "simulated_failure";
