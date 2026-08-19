import type { CSSProperties } from "react";
import type { PreReviewDemoState } from "../contracts/preReviewDemo";
import { estimateRingPresentation, trafficLightTendencySegments } from "../mock/preReviewDemo";

export interface PreReviewSummaryBarProps {
  state: PreReviewDemoState;
  pending: boolean;
  onRun: () => void;
  onOpenDiff: () => void;
}

export interface PreReviewActionBarProps {
  state: PreReviewDemoState;
  pending: boolean;
  onSubmit: () => void;
  onDisposition: (disposition: "复核" | "否决") => void;
}

const DISPOSITION_STYLES: Record<"通过" | "复核" | "否决", CSSProperties> = {
  通过: { background: "#dcfce7", color: "#14532d" },
  复核: { background: "#fef3c7", color: "#78350f" },
  否决: { background: "#fee2e2", color: "#991b1b" },
};

export function PreReviewSummaryBar({ state, pending, onRun, onOpenDiff }: PreReviewSummaryBarProps) {
  const version = state.status === "not_started" ? "V0" : state.versionLabel.split(" ")[0];
  const runLabel = state.status === "not_started" ? "开始预审" : state.status === "submitted" ? "已送审" : "再次预审";
  const segments = trafficLightTendencySegments(state.tendencies);
  const estimateRing = estimateRingPresentation(state.estimate.maxDays);
  return <section className="pre-review-summary" aria-label="预审摘要">
    <div className="pre-review-summary__bar" aria-label="红绿灯判断分布">{segments.map((segment) => <span key={segment.label} className={`pre-review-segment pre-review-segment--${segment.tone}`} style={{ ...DISPOSITION_STYLES[segment.label], width: `${segment.visibleWidth}%` }} title={`${segment.label} ${segment.value}%`}><small>{segment.value}%</small><b>{segment.label}</b></span>)}</div>
    <button aria-label={`${version} ${runLabel}`} className="pre-review-version" data-version={version} type="button" onClick={onRun} disabled={pending || state.status === "submitted"} title={`${version} ${runLabel}`}><span aria-hidden="true" className="pre-review-version-dot" /></button>
    <button className="pre-review-diff-trigger" type="button" onClick={onOpenDiff} disabled={!state.diff}>差异</button>
    <span aria-label={`预计时效 ${state.estimate.minDays}至${state.estimate.maxDays}日 ${state.pendingCount}项待办`} className={`pre-review-estimate pre-review-estimate--${estimateRing.tone}`} style={{ "--estimate-arc": estimateRing.arc } as CSSProperties} title={`预计时效 ${state.estimate.minDays}至${state.estimate.maxDays}日 ${state.pendingCount}项待办 非承诺`}><span aria-hidden="true" className="pre-review-estimate-ring" /></span>
  </section>;
}

export function PreReviewActionBar({ state, pending, onSubmit, onDisposition }: PreReviewActionBarProps) {
  return <div className="pre-review-top-actions" aria-label="预审处置操作">
    <button type="button" onClick={onSubmit} disabled={pending || state.status !== "working"}>提交</button>
    <button type="button" onClick={() => onDisposition("复核")} aria-pressed={state.disposition === "复核"}>复核</button>
    <button type="button" onClick={() => onDisposition("否决")} aria-pressed={state.disposition === "否决"}>否决</button>
  </div>;
}
