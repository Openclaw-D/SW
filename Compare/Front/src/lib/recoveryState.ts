import type { ReviewEvidenceTarget } from "../contracts/workbench";

export type ReviewConflictError = { apiCode?: string };

export async function retryOnceAfterVersionConflict<T, E>(options: {
  submit: (attempt: number) => Promise<T>;
  refresh: () => Promise<E>;
  isCurrent: () => boolean;
  onRefresh: (events: E) => void;
}): Promise<T | null> {
  try { return await options.submit(0); }
  catch (error) {
    if ((error as ReviewConflictError)?.apiCode !== "version_conflict") throw error;
    const events = await options.refresh();
    if (!options.isCurrent()) return null;
    options.onRefresh(events);
    try { return await options.submit(1); }
    catch (retryError) {
      if ((retryError as ReviewConflictError)?.apiCode === "version_conflict") throw new Error("并发冲突仍存在，请重新提交。");
      throw retryError;
    }
  }
}

/**
 * 局部读取失败不能升级为工作台致命错误：工作台数据保持可见，只有材料区
 * 进入可重试错误态。
 */
export type MaterialRecoveryState = {
  error: string | null;
  retryable: boolean;
  fatal: null;
  operation: MaterialRecoveryOperation | null;
};

export type MaterialRecoveryOperation =
  | { kind: "material"; materialId: string }
  | { kind: "evidence"; target: ReviewEvidenceTarget };

export const materialRecoveryFailed = (message: string, operation: MaterialRecoveryOperation): MaterialRecoveryState => ({ error: message, retryable: true, fatal: null, operation });
export const materialRecoverySucceeded = (): MaterialRecoveryState => ({ error: null, retryable: false, fatal: null, operation: null });

/** The core workbench is ready even when its initial material preview cannot load. */
export function initialMaterialLoadFailed(message: string, materialId: string) {
  return { workbench: "ready" as const, recovery: materialRecoveryFailed(message, { kind: "material", materialId }) };
}

export function replayMaterialRecovery(
  state: MaterialRecoveryState,
  replay: { material: (materialId: string) => void; evidence: (target: ReviewEvidenceTarget) => void },
) {
  if (!state.operation) return;
  if (state.operation.kind === "material") return replay.material(state.operation.materialId);
  return replay.evidence(state.operation.target);
}
