import type {
  ApprovalState,
  ApprovalTransitionInput,
  BusinessCorrection,
  BusinessCorrectionResult,
  BusinessCorrectionInput,
  BusinessAnswerInput,
  CollaborationSubmissionResult,
  CommonReviewEvent,
  DimensionId,
  DimensionSeriesRequest,
  DimensionSeriesResponse,
  HardConstraintResult,
  Material,
  ReviewEvidenceSelectionGroup,
  RiskAnswerInput,
  RiskQuestionInput,
  WorkbenchProject,
} from "../contracts/workbench";
import type { ProjectCatalogItem } from "../contracts/projectSelection";
import type { CandidateConfirmationInput, CandidateConfirmationResult, MaterialImportPreflight, MaterialImportResult, MaterialIntelligenceRunInput, MaterialUploadReceipt, StoredMaterialIntelligence, StoredSceneSpec } from "../contracts/materialIntelligence";
import type { ModelGatewayCapability, ModelGatewayRunRecord } from "../contracts/modelGateway";
import type { ProjectConclusionReport } from "../contracts/conclusion";
import type { AgentFocusEvent, AgentMessage, AgentRole, AgentThread, AgentTurnResult, CreateAgentThreadCommand, ExecuteAgentTurnCommand, TransitionAgentFocusCommand } from "../contracts/agentCommunication";
import { WorkbenchGatewayError, type ApprovalTransitionCommand, type BusinessAnswerCommand, type BusinessCorrectionCommand, type GatewayReadOptions, type GatewayResponseMeta, type MaterialUploadOptions, type ResolvedEvidenceSelection, type RiskAnswerCommand, type RiskQuestionCommand, type WorkbenchGateway } from "./workbenchGateway.ts";

export const DEFAULT_WORKBENCH_API_BASE = "http://127.0.0.1:8000/api/v1";

type ApiError = {
  code?: string;
  category?: "not_found" | "validation" | "conflict" | "internal";
  message?: string;
  field?: string | null;
  details?: Record<string, unknown>;
};

type ApiEnvelope<T> = {
  data: T | null;
  meta?: Partial<GatewayResponseMeta>;
  errors?: ApiError[];
};

export type HttpWorkbenchGatewayOptions = {
  apiBase?: string;
  fetchImpl?: typeof fetch;
};

function normalizedApiBase(apiBase: string) {
  return apiBase.replace(/\/+$/, "");
}

function transportError(message: string, options: { requestId?: string; httpStatus?: number } = {}) {
  return new WorkbenchGatewayError("transport", message, options);
}

function isEnvelope(value: unknown): value is ApiEnvelope<unknown> {
  return value !== null && typeof value === "object" && "data" in value && "errors" in value;
}

/**
 * HTTP transport only: it unwraps the frozen API envelope and never creates
 * local mock data when an HTTP request fails.
 */
export class HttpWorkbenchGateway implements WorkbenchGateway {
  private readonly apiBase: string;
  private readonly fetchImpl: typeof fetch;
  private lastMeta: GatewayResponseMeta | null = null;

  constructor(options: HttpWorkbenchGatewayOptions = {}) {
    const previewApiBase = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("apiBase");
    this.apiBase = normalizedApiBase(options.apiBase ?? previewApiBase ?? import.meta.env.VITE_COMPARE_API_BASE ?? DEFAULT_WORKBENCH_API_BASE);
    this.fetchImpl = options.fetchImpl ?? ((input, init) => window.fetch(input, init));
  }

  getLastResponseMeta(): GatewayResponseMeta | null { return this.lastMeta ? { ...this.lastMeta } : null; }

  async listProjects(options?: GatewayReadOptions) {
    return this.request<ProjectCatalogItem[]>("/projects", options);
  }

  async loadProject(projectId: string, options?: GatewayReadOptions) {
    const project = await this.request<WorkbenchProject>(`/projects/${encodeURIComponent(projectId)}/workbench`, options);
    return { ...project, materials: project.materials.map((material) => this.withOriginalUrl(projectId, material)) };
  }

  async listMaterials(projectId: string, options?: GatewayReadOptions) {
    const materials = await this.request<Material[]>(`/projects/${encodeURIComponent(projectId)}/materials`, options);
    return materials.map((material) => this.withOriginalUrl(projectId, material));
  }

  async readMaterial(projectId: string, materialId: string, options?: GatewayReadOptions) {
    const material = await this.request<Material>(`/projects/${encodeURIComponent(projectId)}/materials/${encodeURIComponent(materialId)}`, options);
    return this.withOriginalUrl(projectId, material);
  }

  async uploadMaterialPackage(projectId: string, file: File, options?: MaterialUploadOptions) {
    const fileName = file.name.split(/[\\/]/u).filter(Boolean).at(-1) || "materials.zip";
    return this.requestRaw<MaterialUploadReceipt>(`/projects/${encodeURIComponent(projectId)}/materials/uploads`, file, {
      headers: { "Content-Type": "application/zip", "X-File-Name": fileName },
      signal: options?.signal,
    });
  }

  async preflightMaterialImport(projectId: string, manifestRef: string, options?: GatewayReadOptions) {
    return this.request<MaterialImportPreflight>(`/projects/${encodeURIComponent(projectId)}/materials/imports/preflight`, {
      method: "POST",
      body: { projectId, manifestRef },
      ...options,
    });
  }

  async executeMaterialImport(projectId: string, manifestRef: string, expectedVersion: number, idempotencyKey: string) {
    return this.request<MaterialImportResult>(`/projects/${encodeURIComponent(projectId)}/materials/imports`, {
      method: "POST",
      body: { projectId, manifestRef, expectedVersion },
      headers: this.idempotencyHeaders(idempotencyKey),
    });
  }

  async listModelGatewayCapabilities(options?: GatewayReadOptions) {
    return this.request<ModelGatewayCapability[]>("/model-gateway/capabilities", options);
  }

  async readModelGatewayRun(projectId: string, runId: string, options?: GatewayReadOptions) {
    return this.request<ModelGatewayRunRecord>(`/projects/${encodeURIComponent(projectId)}/model-gateway/runs/${encodeURIComponent(runId)}`, options);
  }

  async runMaterialIntelligence(input: MaterialIntelligenceRunInput, options?: GatewayReadOptions) {
    return this.request<StoredMaterialIntelligence>(`/projects/${encodeURIComponent(input.projectId)}/materials/${encodeURIComponent(input.materialId)}/intelligence`, {
      method: "POST",
      body: this.writeBody(input),
      headers: this.writeHeaders(input),
      ...options,
    });
  }

  async readMaterialIntelligence(projectId: string, materialId: string, options?: GatewayReadOptions) {
    return this.request<StoredMaterialIntelligence>(`/projects/${encodeURIComponent(projectId)}/materials/${encodeURIComponent(materialId)}/intelligence/latest`, options);
  }

  async confirmMaterialCandidate(input: CandidateConfirmationInput) {
    return this.request<CandidateConfirmationResult>(`/projects/${encodeURIComponent(input.projectId)}/candidates/${encodeURIComponent(input.candidateId)}/confirm`, {
      method: "POST",
      body: this.writeBody(input),
      headers: this.writeHeaders(input),
    });
  }

  async readMaterialSceneSpec(projectId: string, materialId: string, options?: GatewayReadOptions) {
    return this.request<StoredSceneSpec>(`/projects/${encodeURIComponent(projectId)}/materials/${encodeURIComponent(materialId)}/scene-spec`, options);
  }

  async resolveEvidenceSelection(projectId: string, group: ReviewEvidenceSelectionGroup, options?: GatewayReadOptions) {
    return this.request<ResolvedEvidenceSelection>(`/projects/${encodeURIComponent(projectId)}/evidence/resolve`, {
      method: "POST",
      body: group,
      ...options,
    });
  }

  async queryDimensionSeries(request: DimensionSeriesRequest, options?: GatewayReadOptions) {
    return this.request<DimensionSeriesResponse>(`/projects/${encodeURIComponent(request.projectId)}/dimensions/${encodeURIComponent(request.dimensionId)}/series/query`, {
      method: "POST",
      body: request,
      ...options,
    });
  }

  // These mappings deliberately do not update UI state. M2 owns write-chain integration.
  async submitBusinessCorrection(input: BusinessCorrectionCommand): Promise<BusinessCorrectionResult> {
    return this.request<BusinessCorrectionResult>(`/projects/${encodeURIComponent(input.projectId)}/facts/${encodeURIComponent(input.factKey)}/corrections`, {
      method: "POST",
      body: this.writeBody(input),
      headers: this.writeHeaders(input),
    });
  }

  async submitRiskQuestion(input: RiskQuestionCommand): Promise<CommonReviewEvent> {
    return this.request<CommonReviewEvent>(`/projects/${encodeURIComponent(input.projectId)}/review/risk/questions`, { method: "POST", body: this.writeBody(input), headers: this.writeHeaders(input) });
  }

  async submitBusinessAnswer(input: BusinessAnswerCommand): Promise<CollaborationSubmissionResult> {
    return this.request<CollaborationSubmissionResult>(`/projects/${encodeURIComponent(input.projectId)}/review/business/answers`, { method: "POST", body: this.writeBody(input), headers: this.writeHeaders(input) });
  }

  async submitRiskAnswer(input: RiskAnswerCommand): Promise<CollaborationSubmissionResult> {
    return this.request<CollaborationSubmissionResult>(`/projects/${encodeURIComponent(input.projectId)}/review/risk/answers`, { method: "POST", body: this.writeBody(input), headers: this.writeHeaders(input) });
  }

  async readPolicyResults(projectId: string, options?: GatewayReadOptions) {
    return this.request<HardConstraintResult[]>(`/projects/${encodeURIComponent(projectId)}/policy/results`, options);
  }

  async readReviewEvents(projectId: string, options?: GatewayReadOptions) {
    return this.request<CommonReviewEvent[]>(`/projects/${encodeURIComponent(projectId)}/review/events`, options);
  }

  async readApprovalState(projectId: string, options?: GatewayReadOptions) {
    return this.request<ApprovalState>(`/projects/${encodeURIComponent(projectId)}/approval`, options);
  }

  async readConclusionReport(projectId: string, options?: GatewayReadOptions) {
    return this.request<ProjectConclusionReport>(`/projects/${encodeURIComponent(projectId)}/conclusion`, options);
  }

  async createAgentThread(input: CreateAgentThreadCommand) {
    return this.request<AgentThread>(`/projects/${encodeURIComponent(input.projectId)}/agents/threads`, {
      method: "POST",
      body: { title: input.title },
      headers: this.agentHeaders(input.principal, input.idempotencyKey),
    });
  }

  async readAgentThread(projectId: string, threadId: string, principal: AgentRole = "business", options?: GatewayReadOptions) {
    return this.request<AgentThread>(`/projects/${encodeURIComponent(projectId)}/agents/threads/${encodeURIComponent(threadId)}`, {
      ...options,
      headers: this.agentHeaders(principal),
    });
  }

  async readAgentMessages(projectId: string, threadId: string, principal: AgentRole = "business", options?: GatewayReadOptions) {
    return this.request<AgentMessage[]>(`/projects/${encodeURIComponent(projectId)}/agents/threads/${encodeURIComponent(threadId)}/messages?afterSequence=0&limit=500`, {
      ...options,
      headers: this.agentHeaders(principal),
    });
  }

  async readAgentFocusEvents(projectId: string, threadId: string, principal: AgentRole = "business", options?: GatewayReadOptions) {
    return this.request<AgentFocusEvent[]>(`/projects/${encodeURIComponent(projectId)}/agents/threads/${encodeURIComponent(threadId)}/focus-events?afterSequence=0&limit=500`, {
      ...options,
      headers: this.agentHeaders(principal),
    });
  }

  async transitionAgentFocus(input: TransitionAgentFocusCommand) {
    return this.request<AgentThread>(`/projects/${encodeURIComponent(input.projectId)}/agents/threads/${encodeURIComponent(input.threadId)}/focus-transitions`, {
      method: "POST",
      body: { toFocusRole: input.toFocusRole, expectedVersion: input.expectedVersion, reason: input.reason },
      headers: this.agentHeaders(input.principal, input.idempotencyKey),
    });
  }

  async executeAgentTurn(input: ExecuteAgentTurnCommand) {
    return this.request<AgentTurnResult>(`/projects/${encodeURIComponent(input.projectId)}/agents/threads/${encodeURIComponent(input.threadId)}/turns`, {
      method: "POST",
      body: {
        instruction: input.instruction,
        replyToMessageId: input.replyToMessageId,
        evidenceTargets: input.evidenceTargets,
        expectedVersion: input.expectedVersion,
        locale: input.locale,
      },
      headers: this.agentHeaders(input.principal, input.idempotencyKey),
    });
  }

  async transitionApproval(projectId: string, input: ApprovalTransitionCommand) {
    return this.request<ApprovalState>(`/projects/${encodeURIComponent(projectId)}/approval/transitions`, {
      method: "POST",
      body: this.writeBody(input),
      headers: this.writeHeaders(input),
    });
  }

  private async request<T>(path: string, options: { method?: string; body?: unknown; headers?: HeadersInit; signal?: AbortSignal } = {}): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.apiBase}${path}`, {
        method: options.method ?? "GET",
        headers: { Accept: "application/json", ...(options.body === undefined ? {} : { "Content-Type": "application/json" }), ...options.headers },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options.signal,
      });
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
      const detail = reason instanceof Error && reason.message ? `（${reason.message}）` : "";
      throw transportError(`无法连接 Compare HTTP 服务。${detail}`, { httpStatus: 0 });
    }
    return this.unwrapResponse<T>(response);
  }

  private async unwrapResponse<T>(response: Response): Promise<T> {
    let payload: unknown;
    try { payload = await response.json(); } catch { throw transportError("HTTP 服务返回了非 JSON 响应。", { httpStatus: response.status }); }
    if (!isEnvelope(payload)) throw transportError("HTTP 服务响应不符合冻结 envelope 契约。", { httpStatus: response.status });
    const meta = payload.meta;
    if (!meta || typeof meta.requestId !== "string" || typeof meta.schemaVersion !== "string" || typeof meta.dataStatus !== "string" || typeof meta.source !== "string" || typeof meta.disclaimer !== "string") {
      throw transportError("HTTP 服务响应缺少冻结 meta。", { httpStatus: response.status });
    }
    if (meta.dataStatus !== "simulated") throw transportError("HTTP 服务 meta.dataStatus 不符合冻结契约。", { httpStatus: response.status });
    this.lastMeta = { requestId: meta.requestId, schemaVersion: meta.schemaVersion, dataStatus: meta.dataStatus, source: meta.source, disclaimer: meta.disclaimer };
    const requestId = meta.requestId;
    if (!response.ok) {
      const apiError = payload.errors?.[0];
      if (apiError?.category === "not_found" || apiError?.category === "validation" || apiError?.category === "conflict") {
        throw new WorkbenchGatewayError(apiError.category, apiError.message ?? "HTTP 请求失败。", { requestId, httpStatus: response.status, apiCode: apiError.code, field: apiError.field, details: apiError.details });
      }
      throw transportError(apiError?.message ?? "HTTP 服务请求失败。", { requestId, httpStatus: response.status });
    }
    if (payload.data === null) throw transportError("HTTP 成功响应缺少 data。", { requestId, httpStatus: response.status });
    return payload.data as T;
  }

  private async requestRaw<T>(path: string, body: Blob, options: { headers: HeadersInit; signal?: AbortSignal }): Promise<T> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.apiBase}${path}`, {
        method: "POST",
        headers: { Accept: "application/json", ...options.headers },
        body,
        signal: options.signal,
      });
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") throw reason;
      const detail = reason instanceof Error && reason.message ? `（${reason.message}）` : "";
      throw transportError(`无法连接 Compare HTTP 服务。${detail}`, { httpStatus: 0 });
    }
    return this.unwrapResponse<T>(response);
  }

  private writeBody(input: BusinessCorrectionCommand | RiskQuestionCommand | BusinessAnswerCommand | RiskAnswerCommand | ApprovalTransitionCommand | MaterialIntelligenceRunInput | CandidateConfirmationInput) {
    if (!Number.isInteger(input.expectedVersion) || input.expectedVersion < 1) {
      throw new WorkbenchGatewayError("validation", "M2 写入尚未提供服务端 expectedVersion。");
    }
    const { idempotencyKey: _idempotencyKey, ...body } = input;
    return { ...body, expectedVersion: input.expectedVersion };
  }

  private writeHeaders(input: BusinessCorrectionCommand | RiskQuestionCommand | BusinessAnswerCommand | RiskAnswerCommand | ApprovalTransitionCommand | MaterialIntelligenceRunInput | CandidateConfirmationInput) {
    return this.idempotencyHeaders(input.idempotencyKey);
  }

  private idempotencyHeaders(idempotencyKey: string) {
    if (!/^[A-Za-z0-9._:-]{8,128}$/.test(idempotencyKey)) {
      throw new WorkbenchGatewayError("validation", "M2 写入尚未提供有效 Idempotency-Key。");
    }
    return { "Idempotency-Key": idempotencyKey };
  }

  private agentHeaders(principal: AgentRole, idempotencyKey?: string) {
    return {
      "X-Compare-Role": principal,
      ...(idempotencyKey ? this.idempotencyHeaders(idempotencyKey) : {}),
    };
  }

  private withOriginalUrl(projectId: string, material: Material): Material {
    const runtimeOriginal = material.role === "original" || Boolean(material.businessPath || material.folderPath);
    if (!runtimeOriginal || material.role === "derived" || material.kind === "scene" || !material.originalAccess?.available) return material;
    return {
      ...material,
      originalUrl: `${this.apiBase}/projects/${encodeURIComponent(projectId)}/materials/${encodeURIComponent(material.id)}/original`,
    };
  }
}
