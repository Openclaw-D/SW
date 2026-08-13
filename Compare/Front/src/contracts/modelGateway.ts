import type { MaterialMediaKind } from "./materialIntelligence";

export type ModelGatewayMode = "disabled" | "synthetic" | "real";
export type ModelGatewayRunStatus = "idle" | "accepted" | "running" | "succeeded" | "needs_review" | "failed" | "cancelled" | "unavailable";

export interface ModelGatewayCapability {
  capabilityId: string;
  providerId: string;
  supportedModes: Array<Exclude<ModelGatewayMode, "disabled">>;
  inputKinds: MaterialMediaKind[];
  outputKinds: Array<"observations" | "field_candidates" | "source_anchors" | "scene_spec">;
  advisoryOnly: true;
  schemaVersion: "1.0";
}

export interface ModelGatewayError {
  code: "gateway_disabled" | "capability_not_supported" | "request_invalid" | "authorization_required" | "provider_not_configured" | "content_unsupported" | "safety_blocked" | "invalid_output" | "rate_limited" | "timeout" | "provider_unavailable";
  message: string;
  retryable: boolean;
  providerStatus: number | null;
}

export interface ModelGatewayRunRecord {
  runId: string;
  requestId: string;
  capabilityId: string;
  mode: ModelGatewayMode;
  status: Exclude<ModelGatewayRunStatus, "idle">;
  materialId: string;
  materialVersionId: string;
  inputHash: string;
  providerId: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  error: ModelGatewayError | null;
  advisoryOnly: true;
  isSimulated: boolean;
  dataStatus: "simulated" | "provider_generated_unverified" | "unavailable";
  source: string;
  disclaimer: string;
  schemaVersion: "1.0";
}

export interface ModelGatewayRuntimeState {
  runId: string | null;
  provider: string | null;
  status: ModelGatewayRunStatus;
  latencyMs: number | null;
  inputHash: string | null;
  error: string | null;
  retryable: boolean;
  advisoryOnly: true;
}
