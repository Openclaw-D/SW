export type PreReviewStatus = "not_started" | "working" | "submitted";

export type PreReviewDisposition = "支持" | "退回" | "复核" | "否决";
export type PreReviewRiskLevel = "support" | "attention" | "confirm" | "risk" | "forbid";

export type PreReviewTendencies = Record<PreReviewDisposition, number>;

export interface PreReviewDimension {
  id: string;
  name: string;
  score: number;
  riskLevel: PreReviewRiskLevel;
  summary: string;
}
export interface PreReviewDriver {
  id: string;
  title: string;
  detail: string;
  dimensionId: string;
  evidenceRefs: string[];
}

export interface PreReviewIssue {
  id: string;
  title: string;
  detail: string;
  severity: PreReviewRiskLevel;
  status: "open" | "pending" | "resolved";
  evidenceRefs: string[];
}

export interface PreReviewSnapshot {
  id: string;
  label: "基线" | "阶段版本" | "最终";
  version: string;
  createdAt: string;
  locked: boolean;
  note: string;
}

export interface PreReviewDiff {
  fromVersion: string;
  toVersion: string;
  changedDimensions: string[];
  summary: string;
}

export interface PreReviewEstimate {
  minDays: number;
  maxDays: number;
  label: string;
}

export interface PreReviewDemoState {
  projectId: string;
  status: PreReviewStatus;
  versionLabel: string;
  tendencies: PreReviewTendencies;
  disposition: PreReviewDisposition;
  estimate: PreReviewEstimate;
  pendingCount: number;
  sixDimensions: PreReviewDimension[];
  drivers: PreReviewDriver[];
  issues: PreReviewIssue[];
  snapshots: PreReviewSnapshot[];
  diff: PreReviewDiff | null;
}
