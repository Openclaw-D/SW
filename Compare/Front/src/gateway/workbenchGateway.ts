import type {
  ApprovalState,
  ApprovalTransitionInput,
  BusinessCorrection,
  BusinessCorrectionResult,
  BusinessCorrectionInput,
  BusinessAnswerInput,
  CollaborationSubmissionResult,
  CommonReviewEvent,
  DimensionSeriesRequest,
  DimensionSeriesResponse,
  EvidenceReference,
  HardConstraintResult,
  Material,
  ReviewEvidenceSelectionGroup,
  RiskAnswerInput,
  RiskQuestionInput,
  WorkbenchProject,
} from "../contracts/workbench";
import type { ProjectCatalogItem } from "../contracts/projectSelection";
import type {
  CandidateConfirmationInput,
  CandidateConfirmationResult,
  MaterialImportPreflight,
  MaterialImportResult,
  MaterialUploadReceipt,
  MaterialIntelligenceRunInput,
  StoredMaterialIntelligence,
  StoredSceneSpec,
} from "../contracts/materialIntelligence";
import type { ModelGatewayCapability, ModelGatewayRunRecord } from "../contracts/modelGateway";
import type { ProjectConclusionReport } from "../contracts/conclusion";
import type {
  AgentFocusEvent,
  AgentMessage,
  AgentRole,
  AgentThread,
  AgentTurnResult,
  CreateAgentThreadCommand,
  ExecuteAgentTurnCommand,
  PostAgentMessageCommand,
  TransitionAgentFocusCommand,
} from "../contracts/agentCommunication";

/** Successful HTTP resolve response. Material display data remains project-scoped. */
export interface ResolvedEvidenceSelection {
  status: "located";
  selectionGroup: ReviewEvidenceSelectionGroup;
  items: Array<{ target: ReviewEvidenceSelectionGroup["targets"][number]; evidence: EvidenceReference }>;
}

export interface GatewayReadOptions {
  signal?: AbortSignal;
}

export type MaterialUploadOptions = GatewayReadOptions;

export interface GatewayResponseMeta {
  requestId: string;
  schemaVersion: string;
  dataStatus: "simulated";
  source: string;
  disclaimer: string;
}

export type ApiErrorDetails = Record<string, unknown>;

export class WorkbenchGatewayError extends Error {
  public readonly code: "not_found" | "validation" | "conflict" | "simulated_failure" | "transport";
  public readonly requestId?: string;
  public readonly httpStatus?: number;
  public readonly apiCode?: string;
  public readonly field?: string | null;
  public readonly details?: ApiErrorDetails;

  constructor(
    code: "not_found" | "validation" | "conflict" | "simulated_failure" | "transport",
    message: string,
    options: { requestId?: string; httpStatus?: number; apiCode?: string; field?: string | null; details?: ApiErrorDetails } = {},
  ) {
    super(message);
    this.name = "WorkbenchGatewayError";
    this.code = code;
    this.requestId = options.requestId;
    this.httpStatus = options.httpStatus;
    this.apiCode = options.apiCode;
    this.field = options.field;
    this.details = options.details;
  }
}

type WriteMetadata = { expectedVersion: number; idempotencyKey: string };
export type BusinessCorrectionCommand = Omit<BusinessCorrectionInput, keyof WriteMetadata> & WriteMetadata;
export type RiskQuestionCommand = Omit<RiskQuestionInput, keyof WriteMetadata> & WriteMetadata;
export type BusinessAnswerCommand = Omit<BusinessAnswerInput, keyof WriteMetadata> & WriteMetadata;
export type RiskAnswerCommand = Omit<RiskAnswerInput, keyof WriteMetadata> & WriteMetadata;
export type ApprovalTransitionCommand = Omit<ApprovalTransitionInput, keyof WriteMetadata> & WriteMetadata;

export interface WorkbenchGateway {
  getLastResponseMeta(): GatewayResponseMeta | null;
  listProjects(options?: GatewayReadOptions): Promise<ProjectCatalogItem[]>;
  loadProject(projectId: string, options?: GatewayReadOptions): Promise<WorkbenchProject>;
  listMaterials(projectId: string, options?: GatewayReadOptions): Promise<Material[]>;
  readMaterial(projectId: string, materialId: string, options?: GatewayReadOptions): Promise<Material>;
  uploadMaterialPackage(projectId: string, file: File, options?: MaterialUploadOptions): Promise<MaterialUploadReceipt>;
  preflightMaterialImport(projectId: string, manifestRef: string, options?: GatewayReadOptions): Promise<MaterialImportPreflight>;
  executeMaterialImport(projectId: string, manifestRef: string, expectedVersion: number, idempotencyKey: string): Promise<MaterialImportResult>;
  listModelGatewayCapabilities(options?: GatewayReadOptions): Promise<ModelGatewayCapability[]>;
  readModelGatewayRun(projectId: string, runId: string, options?: GatewayReadOptions): Promise<ModelGatewayRunRecord>;
  runMaterialIntelligence(input: MaterialIntelligenceRunInput, options?: GatewayReadOptions): Promise<StoredMaterialIntelligence>;
  readMaterialIntelligence(projectId: string, materialId: string, options?: GatewayReadOptions): Promise<StoredMaterialIntelligence>;
  confirmMaterialCandidate(input: CandidateConfirmationInput): Promise<CandidateConfirmationResult>;
  readMaterialSceneSpec(projectId: string, materialId: string, options?: GatewayReadOptions): Promise<StoredSceneSpec>;
  resolveEvidenceSelection(projectId: string, group: ReviewEvidenceSelectionGroup, options?: GatewayReadOptions): Promise<ResolvedEvidenceSelection>;
  queryDimensionSeries(request: DimensionSeriesRequest, options?: GatewayReadOptions): Promise<DimensionSeriesResponse>;
  submitBusinessCorrection(input: BusinessCorrectionCommand): Promise<BusinessCorrectionResult>;
  submitRiskQuestion(input: RiskQuestionCommand): Promise<CommonReviewEvent>;
  submitBusinessAnswer(input: BusinessAnswerCommand): Promise<CollaborationSubmissionResult>;
  submitRiskAnswer(input: RiskAnswerCommand): Promise<CollaborationSubmissionResult>;
  readPolicyResults(projectId: string, options?: GatewayReadOptions): Promise<HardConstraintResult[]>;
  readReviewEvents(projectId: string, options?: GatewayReadOptions): Promise<CommonReviewEvent[]>;
  readApprovalState(projectId: string, options?: GatewayReadOptions): Promise<ApprovalState>;
  readConclusionReport(projectId: string, options?: GatewayReadOptions): Promise<ProjectConclusionReport>;
  createAgentThread(input: CreateAgentThreadCommand): Promise<AgentThread>;
  readAgentThread(projectId: string, threadId: string, principal?: AgentRole, options?: GatewayReadOptions): Promise<AgentThread>;
  readAgentMessages(projectId: string, threadId: string, principal?: AgentRole, options?: GatewayReadOptions): Promise<AgentMessage[]>;
  readAgentFocusEvents(projectId: string, threadId: string, principal?: AgentRole, options?: GatewayReadOptions): Promise<AgentFocusEvent[]>;
  transitionAgentFocus(input: TransitionAgentFocusCommand): Promise<AgentThread>;
  postAgentMessage(input: PostAgentMessageCommand): Promise<AgentMessage>;
  executeAgentTurn(input: ExecuteAgentTurnCommand): Promise<AgentTurnResult>;
  transitionApproval(projectId: string, input: ApprovalTransitionCommand): Promise<ApprovalState>;
}
