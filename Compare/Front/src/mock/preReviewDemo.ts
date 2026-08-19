import type { PreReviewDemoState, PreReviewDisposition, PreReviewSnapshot, PreReviewRiskLevel } from "../contracts/preReviewDemo";

const DIMENSIONS = [["compliance", "合规", 83, "support", "主体登记与合规材料总体一致"], ["transaction", "交易", 78, "confirm", "交易结构基本清晰，部分条款仍待核对"], ["production", "生产", 80, "support", "产能与订单线索相互印证"], ["revenue", "营收", 76, "attention", "收入与订单方向一致，仍需持续核验"], ["debt", "负债", 66, "risk", "负债口径存在待交叉核验材料"], ["cashflow", "流水", 71, "confirm", "经营流水可覆盖主要周期，需补充近期流水"]] as const;
const TENDENCIES: Record<PreReviewDisposition, number> = { 支持: 36, 退回: 14, 复核: 42, 否决: 8 };
const DISPOSITIONS: PreReviewDisposition[] = ["支持", "退回", "复核", "否决"];
const MIN_VISIBLE_TENDENCY_PERCENT = 5;

export function visibleTendencyWidths(tendencies: Record<PreReviewDisposition, number>) {
  const values = DISPOSITIONS.map((label) => tendencies[label]);
  if (values.every((value) => value >= MIN_VISIBLE_TENDENCY_PERCENT)) return tendencies;
  const excess = values.map((value) => Math.max(0, value - MIN_VISIBLE_TENDENCY_PERCENT));
  const excessTotal = excess.reduce((sum, value) => sum + value, 0);
  const distributable = 100 - MIN_VISIBLE_TENDENCY_PERCENT * DISPOSITIONS.length;
  return Object.fromEntries(DISPOSITIONS.map((label, index) => [
    label,
    MIN_VISIBLE_TENDENCY_PERCENT + (excessTotal === 0 ? distributable / DISPOSITIONS.length : distributable * excess[index] / excessTotal),
  ])) as Record<PreReviewDisposition, number>;
}

export function trafficLightTendencySegments(tendencies: Record<PreReviewDisposition, number>) {
  const segments = [
    { label: "通过", tone: "support", value: tendencies.支持 },
    { label: "复核", tone: "review", value: tendencies.退回 + tendencies.复核 },
    { label: "否决", tone: "deny", value: tendencies.否决 },
  ] as const;
  if (segments.every((segment) => segment.value >= MIN_VISIBLE_TENDENCY_PERCENT)) {
    return segments.map((segment) => ({ ...segment, visibleWidth: segment.value }));
  }
  const excess = segments.map((segment) => Math.max(0, segment.value - MIN_VISIBLE_TENDENCY_PERCENT));
  const excessTotal = excess.reduce((sum, value) => sum + value, 0);
  const distributable = 100 - MIN_VISIBLE_TENDENCY_PERCENT * segments.length;
  return segments.map((segment, index) => ({
    ...segment,
    visibleWidth: MIN_VISIBLE_TENDENCY_PERCENT + (excessTotal === 0 ? distributable / segments.length : distributable * excess[index] / excessTotal),
  }));
}

export function estimateRingPresentation(maxDays: number) {
  if (maxDays <= 2) return { tone: "support", arc: 40 } as const;
  if (maxDays <= 3) return { tone: "attention", arc: 55 } as const;
  if (maxDays <= 4) return { tone: "confirm", arc: 70 } as const;
  if (maxDays <= 5) return { tone: "risk", arc: 85 } as const;
  return { tone: "forbid", arc: 100 } as const;
}

export function createPreReviewDemoState(projectId: string): PreReviewDemoState {
  return { projectId, status: "not_started", versionLabel: "尚未开始", tendencies: { ...TENDENCIES }, disposition: "复核", estimate: { minDays: 2, maxDays: 2, label: "最多2个工作日" }, pendingCount: 3, sixDimensions: DIMENSIONS.map(([id, name, score, riskLevel, summary]) => ({ id, name, score, riskLevel: riskLevel as PreReviewRiskLevel, summary })), drivers: [{ id: "driver-cashflow", title: "经营流水可解释", detail: "近两期回款与订单线索方向一致。", dimensionId: "cashflow", evidenceRefs: ["evidence-transaction-plan", "evidence-credit-guarantee"] }, { id: "driver-compliance", title: "主体材料相互印证", detail: "主体登记与合规材料的关键字段一致。", dimensionId: "compliance", evidenceRefs: ["evidence-controller"] }], issues: [{ id: "issue-debt", title: "负债口径待交叉核验", detail: "缺少一份可直接定位的登记材料。", severity: "risk", status: "pending", evidenceRefs: ["evidence-credit-guarantee"] }, { id: "issue-transaction", title: "交易假设需人工确认", detail: "判断倾向不替代人工审核，也不会自动关闭问题。", severity: "confirm", status: "open", evidenceRefs: ["evidence-transaction-plan"] }], snapshots: [], diff: null };
}

export function rerunPreReviewDemo(state: PreReviewDemoState): PreReviewDemoState {
  if (state.status === "submitted") return { ...state };
  const firstRun = state.snapshots.length === 0;
  const snapshots: PreReviewSnapshot[] = firstRun ? [{ id: "baseline", label: "基线", version: "V1", createdAt: "2026-08-18T09:00:00Z", locked: true, note: "脱敏演示基线" }] : state.snapshots;
  const versionLabel = firstRun ? "V1 基线" : state.versionLabel;
  const fromVersion = state.snapshots.at(-1)?.version ?? "尚未开始";
  return { ...state, status: "working", versionLabel, snapshots, diff: { fromVersion, toVersion: "当前工作态", changedDimensions: ["cashflow", "debt"], summary: "规则型判断倾向已重算，待办仍需人工处理。" } };
}

export function savePreReviewDemoCheckpoint(state: PreReviewDemoState): PreReviewDemoState {
  if (state.status === "not_started" || state.status === "submitted" || state.snapshots.some((snapshot) => snapshot.label === "阶段版本")) return { ...state };
  const checkpoint: PreReviewSnapshot = { id: "checkpoint", label: "阶段版本", version: "V2", createdAt: "2026-08-18T10:00:00Z", locked: true, note: "阶段版本，最终槽位保留" };
  return { ...state, status: "working", versionLabel: "V2 阶段版本", snapshots: [...state.snapshots, checkpoint] };
}

export function submitPreReviewDemo(state: PreReviewDemoState): PreReviewDemoState {
  if (state.status === "not_started" || state.snapshots.some((snapshot) => snapshot.label === "最终")) return { ...state };
  const finalVersion = state.snapshots.some((snapshot) => snapshot.label === "阶段版本") ? "V3" : "V2";
  const finalSnapshot: PreReviewSnapshot = { id: "final", label: "最终", version: finalVersion, createdAt: "2026-08-18T11:00:00Z", locked: true, note: "正式送审前锁定的脱敏演示结果" };
  return { ...state, status: "submitted", versionLabel: `${finalVersion} 最终`, snapshots: [...state.snapshots, finalSnapshot], diff: { fromVersion: state.versionLabel, toVersion: `${finalVersion} 最终`, changedDimensions: [], summary: "最终版本已锁定；问题仍需按人工流程处理。" } };
}
