import {
  PROJECT_RISK_BAND_LABELS,
  type GroupBasis,
  type ProjectCatalogItem,
  type ProjectMaterialStatus,
  type ProjectRiskBand,
} from "../contracts/projectSelection.ts";
import type { DecisionGrade, DimensionDefinition, DimensionId, RiskLevel } from "../contracts/workbench";
import { DIMENSION_IDS } from "../contracts/workbench.ts";
import { averageScore, scoreToGrade } from "../lib/workbenchLogic.ts";

const DIMENSION_META: Record<DimensionId, Pick<DimensionDefinition, "index" | "name" | "fullName">> = {
  compliance: { index: 1, name: "合规", fullName: "合规" },
  transaction: { index: 2, name: "交易", fullName: "交易" },
  production: { index: 3, name: "生产", fullName: "生产" },
  revenue: { index: 4, name: "营收", fullName: "营收" },
  debt: { index: 5, name: "负债", fullName: "负债" },
  cashflow: { index: 6, name: "流水", fullName: "流水" },
};

const INDUSTRIES = [
  { industry: "装备制造", companies: ["启衡", "锐川", "拓原", "恒轴"] },
  { industry: "纺织服装", companies: ["织屿", "锦川", "纬成", "素纺"] },
  { industry: "食品加工", companies: ["谷丰", "味衡", "鲜序", "禾岭"] },
  { industry: "物流运输", companies: ["迅桥", "途安", "联港", "驰域"] },
  { industry: "医疗服务", companies: ["康序", "明诊", "衡益", "澄心"] },
  { industry: "新能源", companies: ["光屿", "储峰", "清曜", "新衡"] },
] as const;

const REGIONS = ["华东", "华南", "华北", "华中", "西南", "东北"] as const;
const STORES = ["上海一部", "广州中心", "北京二部", "武汉中心", "成都一部", "沈阳中心"] as const;
const SALESPEOPLE = ["陈雨", "周宁", "林嘉", "唐安", "沈悦", "许舟", "顾言", "陆青"] as const;
const MATERIAL_STATUSES: ProjectMaterialStatus[] = ["材料齐备", "待补材料", "人工复核"];

function seededRandom(seed: number) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let result = value;
    result = Math.imul(result ^ (result >>> 15), result | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(items: readonly T[], random: () => number): T {
  return items[Math.floor(random() * items.length)] ?? items[0];
}

function clampScore(score: number) {
  return Math.max(24, Math.min(94, Math.round(score)));
}

function buildDimensions(random: () => number, index: number): DimensionDefinition[] {
  const profileBias = ((index % 6) - 2.5) * 2.2;
  return DIMENSION_IDS.map((id, dimensionIndex) => {
    const score = clampScore(68 + profileBias + (random() - 0.5) * 31 + ((index + dimensionIndex) % 3) * 2);
    return {
      id,
      ...DIMENSION_META[id],
      score,
      scoreGrade: scoreToGrade(score),
      confidence: clampScore(score - 7 + random() * 11),
      summary: `${DIMENSION_META[id].name}维度为脱敏模拟规则评估结果，进入项目后仍需结合材料人工核验。`,
    };
  });
}

function previousGrade(grade: DecisionGrade): DecisionGrade {
  const grades: DecisionGrade[] = ["A", "B", "C", "D", "E"];
  return grades[Math.min(grades.length - 1, grades.indexOf(grade) + 1)] ?? "E";
}

function deriveDecisionGrade(dimensions: DimensionDefinition[], materialStatus: ProjectMaterialStatus): DecisionGrade {
  const scoreGrade = scoreToGrade(averageScore(dimensions.map((dimension) => dimension.score)));
  return materialStatus === "材料齐备" ? scoreGrade : previousGrade(scoreGrade);
}

export function projectRiskBand(riskLevel: RiskLevel): ProjectRiskBand {
  return PROJECT_RISK_BAND_LABELS[riskLevel];
}

export function deriveSimulatedRiskLevel(
  _dimensions: readonly DimensionDefinition[],
  _materialStatus: ProjectMaterialStatus,
): RiskLevel {
  // 公开运行时只展示一套含人工 Gate 与“核实”项的脱敏模板，
  // 没有每项目独立风险事实；材料状态、置信度和 decisionGrade 均不得降低风险级别。
  return "confirm";
}

function timeBucket(days: number) {
  if (days <= 7) return "7天内";
  if (days <= 15) return "8–15天";
  if (days <= 30) return "16–30天";
  return "30天以上";
}

function dateParts(now: Date) {
  const year = now.getFullYear().toString();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return { year, month, day };
}

export function generateProjectCatalog(seed: number, now = new Date()): ProjectCatalogItem[] {
  const random = seededRandom(seed);
  const { year, month, day } = dateParts(now);
  const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();

  return INDUSTRIES.flatMap((industryGroup, industryIndex) => industryGroup.companies.map((company, companyIndex) => {
    const index = industryIndex * 4 + companyIndex;
    const durationDays = 4 + Math.floor(random() * 38);
    const materialStatus = MATERIAL_STATUSES[(index + Math.floor(random() * MATERIAL_STATUSES.length)) % MATERIAL_STATUSES.length];
    const dimensions = buildDimensions(random, index);
    const decisionGrade = deriveDecisionGrade(dimensions, materialStatus);
    const riskLevel = deriveSimulatedRiskLevel(dimensions, materialStatus);
    const projectNo = `${year}PAZL${month}${day}${String(index + 1).padStart(3, "0")}`;
    const suffix = ["设备", "实业", "科技", "服务"][companyIndex] ?? "企业";

    return {
      projectId: projectNo,
      projectNo,
      companyName: `${company}${suffix}有限公司`,
      companyShortName: `${company}${suffix}`,
      region: REGIONS[(industryIndex + companyIndex * 2) % REGIONS.length],
      industry: industryGroup.industry,
      durationDays,
      store: STORES[(industryIndex * 2 + companyIndex) % STORES.length],
      salesperson: SALESPEOPLE[(index + Math.floor(random() * 3)) % SALESPEOPLE.length],
      amountWan: 180 + Math.floor(random() * 1680),
      financingType: "设备融资",
      materialStatus,
      createdAt: new Date(startOfDay - durationDays * 86_400_000 + index * 3_600_000).toISOString(),
      timeBucket: timeBucket(durationDays),
      riskLevel,
      riskBand: projectRiskBand(riskLevel),
      decisionGrade,
      dimensions,
      isSimulated: true,
    } satisfies ProjectCatalogItem;
  }));
}

export function groupProjectValue(project: ProjectCatalogItem, basis: GroupBasis) {
  if (basis === "industry") return project.industry;
  if (basis === "risk") return project.riskBand;
  if (basis === "time") return project.timeBucket;
  if (basis === "region") return project.region;
  return project.store;
}
