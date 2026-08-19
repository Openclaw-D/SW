import type { DecisionGrade, DimensionDefinition, RiskLevel } from "./workbench";

export const PUBLIC_DEMO_PROJECT_COUNT = 1;

export const PROJECT_VIEWS = ["list", "group", "cards"] as const;
export type ProjectView = (typeof PROJECT_VIEWS)[number];

export const GROUP_BASES = ["industry", "risk", "time", "region", "store"] as const;
export type GroupBasis = (typeof GROUP_BASES)[number];

export type ProjectMaterialStatus = "材料齐备" | "待补材料" | "人工复核";
export type ProjectRiskBand = "禁止" | "风险" | "核实" | "关注" | "支持";

export const PROJECT_RISK_LEVELS = ["forbid", "risk", "confirm", "attention", "support"] as const satisfies readonly RiskLevel[];

export const PROJECT_RISK_BAND_LABELS: Record<RiskLevel, ProjectRiskBand> = {
  forbid: "禁止",
  risk: "风险",
  confirm: "核实",
  attention: "关注",
  support: "支持",
};

export interface ProjectCatalogItem {
  projectId: string;
  projectNo: string;
  companyName: string;
  companyShortName: string;
  region: string;
  industry: string;
  durationDays: number;
  store: string;
  salesperson: string;
  amountWan: number;
  financingType: "设备融资";
  materialStatus: ProjectMaterialStatus;
  createdAt: string;
  timeBucket: string;
  riskLevel: RiskLevel;
  riskBand: ProjectRiskBand;
  decisionGrade: DecisionGrade;
  dimensions: DimensionDefinition[];
  isSimulated: true;
}

export const PROJECT_VIEW_LABELS: Record<ProjectView, string> = {
  list: "清单",
  group: "分组",
  cards: "卡片",
};

export const GROUP_BASIS_LABELS: Record<GroupBasis, string> = {
  industry: "行业",
  risk: "风险表现",
  time: "时间",
  region: "区域",
  store: "门店",
};

export function isProjectView(value: string | null): value is ProjectView {
  return PROJECT_VIEWS.includes(value as ProjectView);
}
