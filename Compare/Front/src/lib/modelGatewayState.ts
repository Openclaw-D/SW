import type { StoredMaterialIntelligence } from "../contracts/materialIntelligence";
import type { ModelGatewayRuntimeState } from "../contracts/modelGateway";
import { WorkbenchGatewayError } from "../gateway/workbenchGateway.ts";

export const emptyModelGatewayRuntime = (): ModelGatewayRuntimeState => ({
  runId: null,
  provider: null,
  status: "idle",
  latencyMs: null,
  inputHash: null,
  error: null,
  retryable: false,
  advisoryOnly: true,
});

export function modelGatewayRuntimeFromResult(
  stored: StoredMaterialIntelligence,
  latencyMs: number | null = null,
): ModelGatewayRuntimeState {
  const { result } = stored;
  return {
    runId: stored.runId,
    provider: result.modelInfo?.provider ?? null,
    status: result.status === "completed" ? "succeeded" : result.status,
    latencyMs,
    inputHash: result.inputHash,
    error: null,
    retryable: false,
    advisoryOnly: true,
  };
}

export function isRetryableModelGatewayError(reason: unknown) {
  if (!(reason instanceof WorkbenchGatewayError)) return false;
  if (reason.httpStatus === 0 || reason.httpStatus === 408 || reason.httpStatus === 429 || (reason.httpStatus ?? 0) >= 500) return true;
  return /(?:timeout|rate_limit|provider_unavailable|temporar)/iu.test(reason.apiCode ?? "");
}

export function failedModelGatewayRuntime(
  reason: unknown,
  latencyMs: number,
  previous: ModelGatewayRuntimeState,
): ModelGatewayRuntimeState {
  return {
    ...previous,
    status: "failed",
    latencyMs,
    error: reason instanceof Error ? reason.message : "Model Gateway 运行失败。",
    retryable: isRetryableModelGatewayError(reason),
  };
}

export function cancelledModelGatewayRuntime(
  latencyMs: number,
  previous: ModelGatewayRuntimeState,
): ModelGatewayRuntimeState {
  return { ...previous, status: "cancelled", latencyMs, error: "本次运行已取消。", retryable: false };
}
