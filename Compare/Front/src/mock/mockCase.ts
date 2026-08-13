import type {
  CommonReviewEvent,
  ComplianceSubjectGraph,
  DimensionDefinition,
  DimensionDetail,
  EvidenceReference,
  FactVersion,
  GlobalRiskSummary,
  HardConstraintResult,
  Material,
  MappedCommonReviewEvent,
  OnsiteAsset,
  RiskDetermination,
  ReviewEvidenceTarget,
  WorkbenchProject,
} from "../contracts/workbench";
import { attachReviewEvidenceTargets, averageScore, scoreToGrade } from "../lib/workbenchLogic.ts";
import {
  mockFinancedEquipment,
  mockOperatingEquipment,
  mockP2Evidence,
  mockP2Facts,
  mockP2Materials,
  mockProductionEnergy,
  mockProductionPayrollSeries,
  mockProductionStages,
  mockReferenceImages,
} from "./p2Content.ts";
import { mockP3Evidence, mockP3Materials } from "./p3AdjustData.ts";

export const MOCK_PROJECT_ID = "compare-demo-east-precision";

const mockDimensionSeeds: Array<Omit<DimensionDefinition, "scoreGrade">> = [
  { id: "compliance", index: 1, name: "合规", fullName: "合规", score: 82, confidence: 76, summary: "证照与外部登记基本一致，章程和个人涉诉仍待定位核验。" },
  { id: "transaction", index: 2, name: "交易", fullName: "交易", score: 68, confidence: 71, summary: "交易结构、方案和关系可解释，设备报价仍需复核。" },
  { id: "production", index: 3, name: "生产", fullName: "生产", score: 74, confidence: 73, summary: "运营设备、工艺、现场、用电量与完工产量口径基本一致。" },
  { id: "revenue", index: 4, name: "营收", fullName: "营收", score: 71, confidence: 69, summary: "收入、订单和发票方向一致，经营表现需持续核验。" },
  { id: "debt", index: 5, name: "负债", fullName: "负债", score: 64, confidence: 66, summary: "征信、借款与中登口径待交叉核验，未触发禁止性硬约束。" },
  { id: "cashflow", index: 6, name: "流水", fullName: "流水", score: 78, confidence: 74, summary: "收支真实性与经营匹配基本成立，异常流水保留人工复核。" },
];

export const mockDimensions: DimensionDefinition[] = mockDimensionSeeds.map((dimension) => ({
  ...dimension,
  scoreGrade: scoreToGrade(dimension.score),
}));

const mockOverallScore = averageScore(mockDimensions.map((dimension) => dimension.score));

const cashflowMonthlyData = [
  { id: "jan", label: "1月", inflow: 1180, outflow: 1040 },
  { id: "feb", label: "2月", inflow: 1260, outflow: 1190 },
  { id: "mar", label: "3月", inflow: 1380, outflow: 1260 },
  { id: "apr", label: "4月", inflow: 1290, outflow: 1210 },
  { id: "may", label: "5月", inflow: 1460, outflow: 1280 },
  { id: "jun", label: "6月", inflow: 1510, outflow: 1360 },
] as const;

const cashflowNetRate = (inflow: number, outflow: number) => Math.round(((inflow - outflow) / Math.max(inflow, 1)) * 1000) / 10;

const cashflowInflowParties = [
  { id: "cashflow-inflow-huadong", label: "华东建设集团", value: 2157, share: 26.7, note: "30天" },
  { id: "cashflow-inflow-changjiang", label: "长江实业发展", value: 1624, share: 20.1, note: "30天" },
  { id: "cashflow-inflow-zhongyuan", label: "中原控股", value: 1260, share: 15.6, note: "30天" },
  { id: "cashflow-inflow-dongnan", label: "东南贸易", value: 978, share: 12.1, note: "60天" },
  { id: "cashflow-inflow-qiming", label: "启明科技", value: 776, share: 9.6, note: "30天" },
  { id: "cashflow-inflow-other", label: "其他", value: 1285, share: 15.9, note: "其他" },
] as const;

const cashflowOutflowParties = [
  { id: "cashflow-outflow-hongyuan", label: "宏远建筑工程", value: 1828, share: 24.9, note: "30天" },
  { id: "cashflow-outflow-dingsheng", label: "鼎盛材料供应", value: 1336, share: 18.2, note: "60天" },
  { id: "cashflow-outflow-huayi", label: "华翼设备租赁", value: 1028, share: 14.0, note: "30天" },
  { id: "cashflow-outflow-citic", label: "中信银行", value: 763, share: 10.4, note: "无账期" },
  { id: "cashflow-outflow-xinda", label: "信达融资担保", value: 646, share: 8.8, note: "30天" },
  { id: "cashflow-outflow-other", label: "其他", value: 1739, share: 23.7, note: "其他" },
] as const;

export const mockDimensionDetails: DimensionDetail[] = [
  {
    dimensionId: "compliance",
    visual: "subject-network",
    defaultView: "visual",
    availableViews: ["visual", "table"],
    unit: "项",
    metrics: [
      { id: "compliance-license-status", label: "证照状态", value: "有效", note: "营业执照", tone: "positive", evidenceRefs: ["evidence-compliance-license"] },
      { id: "compliance-external-check", label: "外部核验", value: "2 项", note: "工商与涉诉", tone: "neutral", evidenceRefs: ["evidence-compliance-registry", "evidence-compliance-subject-litigation"] },
      { id: "compliance-pending", label: "待处理", value: "3 项", note: "待定位或不可核验", tone: "attention", evidenceRefs: ["evidence-compliance-identity", "evidence-compliance-charter", "evidence-compliance-personal-litigation"] },
    ],
    series: [],
    breakdown: [
      { id: "compliance-license", label: "营业执照", value: "有效", detail: "模拟核验索引第 4 行", tone: "positive", evidenceRefs: ["evidence-compliance-license"] },
      { id: "compliance-identity", label: "身份证", value: "待核", detail: "证件范围尚未完成定位", tone: "attention", evidenceRefs: ["evidence-compliance-identity"] },
      { id: "compliance-charter", label: "章程", value: "待核", detail: "章程版本与签署页待定位", tone: "attention", evidenceRefs: ["evidence-compliance-charter"] },
      { id: "compliance-registry", label: "外部工商", value: "基本一致", detail: "模拟核验索引第 5 行", tone: "positive", evidenceRefs: ["evidence-compliance-registry"] },
      { id: "compliance-subject-litigation", label: "主体涉诉", value: "未见异常", detail: "模拟核验索引第 6 行", tone: "neutral", evidenceRefs: ["evidence-compliance-subject-litigation"] },
      { id: "compliance-personal-litigation", label: "个人涉诉", value: "待核", detail: "关联自然人范围待人工确认", tone: "attention", evidenceRefs: ["evidence-compliance-personal-litigation"] },
    ],
    conclusion: "证照、外部工商与主体涉诉已有模拟精确范围；章程、身份证和个人涉诉仍待定位，只进入人工复核。",
    sourceLabel: "演示证照、章程、外部工商与涉诉材料",
    isSimulated: true,
  },
  {
    dimensionId: "transaction",
    visual: "transaction-structure",
    defaultView: "visual",
    availableViews: ["visual"],
    unit: "万元",
    metrics: [],
    series: [],
    breakdown: [],
    conclusion: "交易结构、方案与关系具备可视化价值；完整合同字段保留表格，报价差异仅作为软提示。",
    sourceLabel: "演示合同、交易方案与主体关系材料",
    isSimulated: true,
  },
  {
    dimensionId: "production",
    visual: "production-series",
    defaultView: "visual",
    availableViews: ["visual"],
    unit: "运营事实",
    metrics: [],
    series: [],
    seriesGroups: [mockProductionPayrollSeries],
    breakdown: [],
    conclusion: "运营设备、三阶段工艺、现场原型、用电量与完工产量统一归入生产；设备合同报价只在交易。",
    sourceLabel: "演示运营设备、生产流程、电表与完工记录",
    isSimulated: true,
  },
  {
    dimensionId: "revenue",
    visual: "revenue-series",
    defaultView: "visual",
    availableViews: ["visual", "table"],
    unit: "万元",
    metrics: [
      { id: "revenue-income-metric", label: "年度营收", value: "12,800 万", note: "2024 年度汇总", tone: "positive", evidenceRefs: ["evidence-revenue-profit-annual-revenue", "evidence-p3-revenue-summary"] },
      { id: "revenue-orders-metric", label: "订单覆盖", value: "94.1%", note: "演示口径", tone: "positive", evidenceRefs: ["evidence-revenue-orders"] },
      { id: "revenue-invoices-metric", label: "发票覆盖", value: "96.6%", note: "演示口径", tone: "positive", evidenceRefs: ["evidence-revenue-invoices"] },
      { id: "revenue-net-profit-metric", label: "净利润", value: "1,500 万", note: "年度营收扣除五项费用", tone: "positive", evidenceRefs: ["evidence-revenue-profit-net-profit"] },
      { id: "revenue-net-margin-metric", label: "净利率", value: "11.7%", note: "净利润 ÷ 年度营收", tone: "neutral", evidenceRefs: ["evidence-revenue-profit-margin-inputs"] },
      { id: "revenue-rent-first-12-metric", label: "前12期项目租金", value: "72.318 万", note: "交易租金计划前12期", tone: "neutral", evidenceRefs: ["evidence-transaction-rent-first-12", "evidence-revenue-profit-rent-summary"] },
      { id: "revenue-rent-coverage-metric", label: "租金覆盖倍数", value: "20.74×", note: "净利润 ÷ 前12期项目租金", tone: "positive", evidenceRefs: ["evidence-revenue-profit-coverage-inputs"] },
    ],
    series: [
      { id: "revenue-2022", label: "2022", note: "年度累计 · 万元 · 含期初订单", measures: [{ id: "revenue-2022-orders", label: "合同订单", value: 9000, unit: "万元", evidenceRefs: ["evidence-revenue-2022-orders"] }, { id: "revenue-2022-invoices", label: "发票", value: 8240, unit: "万元", evidenceRefs: ["evidence-revenue-2022-invoices"], comparisonEvidenceRefs: ["evidence-revenue-2022-gap-invoices"] }, { id: "revenue-2022-collections", label: "回款流水", value: 7880, unit: "万元", evidenceRefs: ["evidence-revenue-2022-collections"], comparisonEvidenceRefs: ["evidence-revenue-2022-gap-collections"] }, { id: "revenue-2022-income", label: "确认收入", value: 8600, unit: "万元", evidenceRefs: ["evidence-revenue-2022-income"], comparisonEvidenceRefs: ["evidence-revenue-2022-gap-income"] }] },
      { id: "revenue-2023", label: "2023", note: "年度累计 · 万元 · 含期初订单", measures: [{ id: "revenue-2023-orders", label: "合同订单", value: 10860, unit: "万元", evidenceRefs: ["evidence-revenue-2023-orders"] }, { id: "revenue-2023-invoices", label: "发票", value: 10080, unit: "万元", evidenceRefs: ["evidence-revenue-2023-invoices"], comparisonEvidenceRefs: ["evidence-revenue-2023-gap-invoices"] }, { id: "revenue-2023-collections", label: "回款流水", value: 9840, unit: "万元", evidenceRefs: ["evidence-revenue-2023-collections"], comparisonEvidenceRefs: ["evidence-revenue-2023-gap-collections"] }, { id: "revenue-2023-income", label: "确认收入", value: 10400, unit: "万元", evidenceRefs: ["evidence-revenue-2023-income"], comparisonEvidenceRefs: ["evidence-revenue-2023-gap-income"] }] },
      { id: "revenue-2024", label: "2024", note: "年度累计 · 万元 · 含跨期履约", measures: [{ id: "revenue-2024-orders", label: "合同订单", value: 12040, unit: "万元", evidenceRefs: ["evidence-revenue-2024-orders"] }, { id: "revenue-2024-invoices", label: "发票", value: 12360, unit: "万元", evidenceRefs: ["evidence-revenue-2024-invoices"], comparisonEvidenceRefs: ["evidence-revenue-2024-gap-invoices"] }, { id: "revenue-2024-collections", label: "回款流水", value: 11790, unit: "万元", evidenceRefs: ["evidence-revenue-2024-collections"], comparisonEvidenceRefs: ["evidence-revenue-2024-gap-collections"] }, { id: "revenue-2024-income", label: "确认收入", value: 12800, unit: "万元", evidenceRefs: ["evidence-revenue-2024-income"], comparisonEvidenceRefs: ["evidence-revenue-2024-gap-income"] }] },
    ],
    compositions: [
      { id: "revenue-upstream", label: "上游", segments: [
        { id: "revenue-upstream-material", label: "核心原材料", value: 42, unit: "%", tone: "neutral", evidenceRefs: ["evidence-revenue-upstream-material"] },
        { id: "revenue-upstream-equipment", label: "设备耗材", value: 33, unit: "%", tone: "positive", evidenceRefs: ["evidence-revenue-upstream-equipment"] },
        { id: "revenue-upstream-energy", label: "物流能源", value: 25, unit: "%", tone: "attention", evidenceRefs: ["evidence-revenue-upstream-energy"] },
      ] },
      { id: "revenue-downstream", label: "下游", segments: [
        { id: "revenue-downstream-manufacturing", label: "制造客户", value: 48, unit: "%", tone: "neutral", evidenceRefs: ["evidence-revenue-downstream-manufacturing"] },
        { id: "revenue-downstream-channel", label: "经销渠道", value: 31, unit: "%", tone: "positive", evidenceRefs: ["evidence-revenue-downstream-channel"] },
        { id: "revenue-downstream-service", label: "服务客户", value: 21, unit: "%", tone: "attention", evidenceRefs: ["evidence-revenue-downstream-service"] },
      ] },
      { id: "revenue-receivable-aging", label: "应收账龄", segments: [
        { id: "revenue-aging-30", label: "30天内", value: 55, unit: "%", tone: "positive", evidenceRefs: ["evidence-revenue-aging-30"] },
        { id: "revenue-aging-60", label: "31–60天", value: 28, unit: "%", tone: "attention", evidenceRefs: ["evidence-revenue-aging-60"] },
        { id: "revenue-aging-over-60", label: "60天以上", value: 17, unit: "%", tone: "critical", evidenceRefs: ["evidence-revenue-aging-over-60"] },
      ] },
      { id: "revenue-profitability", label: "利润与租金覆盖", segments: [
        { id: "revenue-profit-material", label: "材料成本", value: 9600, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-revenue-profit-material"] },
        { id: "revenue-profit-site-rent", label: "场地房租", value: 360, unit: "万元", tone: "attention", evidenceRefs: ["evidence-revenue-profit-site-rent"] },
        { id: "revenue-profit-utilities", label: "水电费用", value: 384, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-revenue-profit-utilities"] },
        { id: "revenue-profit-payroll", label: "人工费用", value: 278.4, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-revenue-profit-payroll"] },
        { id: "revenue-profit-other", label: "其他费用", value: 677.6, unit: "万元", tone: "attention", evidenceRefs: ["evidence-revenue-profit-other"] },
        { id: "revenue-profit-net-profit", label: "净利润", value: 1500, unit: "万元", tone: "positive", evidenceRefs: ["evidence-revenue-profit-net-profit"] },
      ] },
    ],
    breakdown: [
      { id: "revenue-income", label: "收入", value: "12,800 万", detail: "模拟核验索引第 15 行", tone: "positive", evidenceRefs: ["evidence-revenue-income"] },
      { id: "revenue-orders", label: "订单", value: "12,040 万", detail: "模拟核验索引第 16 行", tone: "positive", evidenceRefs: ["evidence-revenue-orders"] },
      { id: "revenue-invoices", label: "发票", value: "12,360 万", detail: "模拟核验索引第 17 行", tone: "positive", evidenceRefs: ["evidence-revenue-invoices"] },
      { id: "revenue-performance", label: "经营表现", value: "稳定", detail: "模拟核验索引第 18 行", tone: "neutral", evidenceRefs: ["evidence-revenue-performance"] },
    ],
    conclusion: "收入、订单、发票与经营表现统一归入营收；趋势用于图形，逐笔字段由表格承载。",
    sourceLabel: "演示收入、订单、发票与经营表现材料",
    isSimulated: true,
  },
  {
    dimensionId: "debt",
    visual: "debt-structure",
    defaultView: "visual",
    availableViews: ["visual", "table"],
    unit: "万元",
    metrics: [
      { id: "debt-credit-metric", label: "征信负债", value: "4,260 万", note: "演示汇总", tone: "attention", evidenceRefs: ["evidence-debt-credit"] },
      { id: "debt-maturity", label: "一年到期", value: "1,860 万", note: "未来12月合计 · 占总负债43.7%", tone: "attention", evidenceRefs: ["evidence-debt-repayment-total-due-inputs"] },
      { id: "debt-registration", label: "中登登记", value: "待核", note: "尚未准确定位", tone: "attention", evidenceRefs: ["evidence-debt-zhongdeng"] },
      { id: "debt-exposure-history", label: "历史存量", value: "419W", note: "圆心口径 · 项目既有敞口", tone: "neutral", evidenceRefs: ["evidence-debt-exposure-history"] },
      { id: "debt-exposure-current", label: "本次融资", value: "121W", note: "本次新增融资金额", tone: "neutral", evidenceRefs: ["evidence-debt-exposure-current"] },
      { id: "debt-exposure-total", label: "项目总敞口", value: "540W", note: "历史存量 + 本次融资 · 全局上限1000W", tone: "attention", evidenceRefs: ["evidence-debt-exposure-total"] },
      { id: "debt-exposure-deduplication", label: "重复融资核验", value: "待人工去重", note: "中登清单尚未精确定位", tone: "attention", evidenceRefs: ["evidence-debt-zhongdeng"] },
    ],
    series: [
      { id: "debt-history-2022", label: "2022", note: "企业与个人主体口径", measures: [{ id: "debt-history-2022-enterprise", label: "企业负债", value: 2250, unit: "万元", evidenceRefs: ["evidence-debt-history-2022-enterprise"] }, { id: "debt-history-2022-personal", label: "个人负债", value: 830, unit: "万元", evidenceRefs: ["evidence-debt-history-2022-personal"] }] },
      { id: "debt-history-2023", label: "2023", note: "企业与个人主体口径", measures: [{ id: "debt-history-2023-enterprise", label: "企业负债", value: 2700, unit: "万元", evidenceRefs: ["evidence-debt-history-2023-enterprise"] }, { id: "debt-history-2023-personal", label: "个人负债", value: 1010, unit: "万元", evidenceRefs: ["evidence-debt-history-2023-personal"] }] },
      { id: "debt-history-2024", label: "2024", note: "企业与个人主体口径", measures: [{ id: "debt-history-2024-enterprise", label: "企业负债", value: 3140, unit: "万元", evidenceRefs: ["evidence-debt-history-2024-enterprise"] }, { id: "debt-history-2024-personal", label: "个人负债", value: 1120, unit: "万元", evidenceRefs: ["evidence-debt-history-2024-personal"] }] },
    ],
    seriesGroups: [{
      id: "debt-repayment",
      label: "未来12月偿债计划",
      points: [
        { id: "debt-repayment-2026-09", label: "26/09", measures: [{ id: "debt-repayment-2026-09-due", label: "到期负债", value: 150, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-09-due"] }, { id: "debt-repayment-2026-09-capacity", label: "可偿还能力", value: 240, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-09-comparison-inputs"] }] },
        { id: "debt-repayment-2026-10", label: "26/10", measures: [{ id: "debt-repayment-2026-10-due", label: "到期负债", value: 130, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-10-due"] }, { id: "debt-repayment-2026-10-capacity", label: "可偿还能力", value: 210, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-10-comparison-inputs"] }] },
        { id: "debt-repayment-2026-11", label: "26/11", measures: [{ id: "debt-repayment-2026-11-due", label: "到期负债", value: 180, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-11-due"] }, { id: "debt-repayment-2026-11-capacity", label: "可偿还能力", value: 250, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-11-comparison-inputs"] }] },
        { id: "debt-repayment-2026-12", label: "26/12", measures: [{ id: "debt-repayment-2026-12-due", label: "到期负债", value: 115, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-12-due"] }, { id: "debt-repayment-2026-12-capacity", label: "可偿还能力", value: 190, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2026-12-comparison-inputs"] }] },
        { id: "debt-repayment-2027-01", label: "27/01", measures: [{ id: "debt-repayment-2027-01-due", label: "到期负债", value: 175, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-01-due"] }, { id: "debt-repayment-2027-01-capacity", label: "可偿还能力", value: 230, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-01-comparison-inputs"] }] },
        { id: "debt-repayment-2027-02", label: "27/02", measures: [{ id: "debt-repayment-2027-02-due", label: "到期负债", value: 155, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-02-due"] }, { id: "debt-repayment-2027-02-capacity", label: "可偿还能力", value: 220, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-02-comparison-inputs"] }] },
        { id: "debt-repayment-2027-03", label: "27/03", measures: [{ id: "debt-repayment-2027-03-due", label: "到期负债", value: 140, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-03-due"] }, { id: "debt-repayment-2027-03-capacity", label: "可偿还能力", value: 200, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-03-comparison-inputs"] }] },
        { id: "debt-repayment-2027-04", label: "27/04", measures: [{ id: "debt-repayment-2027-04-due", label: "到期负债", value: 190, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-04-due"] }, { id: "debt-repayment-2027-04-capacity", label: "可偿还能力", value: 250, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-04-comparison-inputs"] }] },
        { id: "debt-repayment-2027-05", label: "27/05", measures: [{ id: "debt-repayment-2027-05-due", label: "到期负债", value: 125, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-05-due"] }, { id: "debt-repayment-2027-05-capacity", label: "可偿还能力", value: 180, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-05-comparison-inputs"] }] },
        { id: "debt-repayment-2027-06", label: "27/06", measures: [{ id: "debt-repayment-2027-06-due", label: "到期负债", value: 165, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-06-due"] }, { id: "debt-repayment-2027-06-capacity", label: "可偿还能力", value: 230, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-06-comparison-inputs"] }] },
        { id: "debt-repayment-2027-07", label: "27/07", measures: [{ id: "debt-repayment-2027-07-due", label: "到期负债", value: 150, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-07-due"] }, { id: "debt-repayment-2027-07-capacity", label: "可偿还能力", value: 210, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-07-comparison-inputs"] }] },
        { id: "debt-repayment-2027-08", label: "27/08", measures: [{ id: "debt-repayment-2027-08-due", label: "到期负债", value: 185, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-08-due"] }, { id: "debt-repayment-2027-08-capacity", label: "可偿还能力", value: 240, unit: "万元", evidenceRefs: ["evidence-debt-repayment-2027-08-comparison-inputs"] }] },
      ],
    }],
    compositions: [
      { id: "debt-enterprise-creditors", label: "企业负债", segments: [
        { id: "debt-enterprise-ccb", label: "建设银行", value: 620, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-debt-enterprise-ccb"] },
        { id: "debt-enterprise-icbc", label: "工商银行", value: 580, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-debt-enterprise-icbc"] },
        { id: "debt-enterprise-suzhou", label: "苏州银行", value: 600, unit: "万元", tone: "positive", evidenceRefs: ["evidence-debt-enterprise-suzhou"] },
        { id: "debt-enterprise-feh", label: "远东宏信", value: 520, unit: "万元", tone: "attention", evidenceRefs: ["evidence-debt-enterprise-feh"] },
        { id: "debt-enterprise-pingan", label: "平安租赁", value: 440, unit: "万元", tone: "attention", evidenceRefs: ["evidence-debt-enterprise-pingan"] },
        { id: "debt-enterprise-chailease", label: "仲利国际", value: 380, unit: "万元", tone: "attention", evidenceRefs: ["evidence-debt-enterprise-chailease"] },
      ] },
      { id: "debt-personal-creditors", label: "个人负债", segments: [
        { id: "debt-personal-controller", label: "实控人", value: 381, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-debt-personal-controller"] },
        { id: "debt-personal-spouse", label: "配偶", value: 224, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-debt-personal-spouse"] },
        { id: "debt-personal-shareholder", label: "股东", value: 202, unit: "万元", tone: "neutral", evidenceRefs: ["evidence-debt-personal-shareholder"] },
        { id: "debt-personal-legal", label: "法定代表人", value: 179, unit: "万元", tone: "attention", evidenceRefs: ["evidence-debt-personal-legal"] },
        { id: "debt-personal-relative", label: "亲属", value: 134, unit: "万元", tone: "attention", evidenceRefs: ["evidence-debt-personal-relative"] },
      ] },
      { id: "debt-project-exposure", label: "项目通道敞口", segments: [
        { id: "debt-exposure-direct-200", label: "200直", value: 113, unit: "W", note: "formal-product-channels-v2 · 限额200W · 份额21%", tone: "attention", evidenceRefs: ["evidence-debt-exposure-direct-200"] },
        { id: "debt-exposure-core-200", label: "200核心", value: 190, unit: "W", note: "formal-product-channels-v2 · 限额200W · 份额35%", tone: "neutral", evidenceRefs: ["evidence-debt-exposure-core-200"] },
        { id: "debt-exposure-core-300", label: "300核心", value: 124, unit: "W", note: "formal-product-channels-v2 · 限额300W · 份额23%", tone: "neutral", evidenceRefs: ["evidence-debt-exposure-core-300"] },
        { id: "debt-exposure-core-500", label: "500核心", value: 113, unit: "W", note: "formal-product-channels-v2 · 限额500W · 份额21%", tone: "neutral", evidenceRefs: ["evidence-debt-exposure-core-500"] },
      ] },
    ],
    breakdown: [
      { id: "debt-credit", label: "征信", value: "4,260 万", detail: "模拟核验索引第 19 行", tone: "attention", evidenceRefs: ["evidence-debt-credit"] },
      { id: "debt-loans", label: "借款", value: "3,140 万", detail: "模拟核验索引第 20 行", tone: "attention", evidenceRefs: ["evidence-debt-loans"] },
      { id: "debt-zhongdeng", label: "中登", value: "待核", detail: "登记清单尚无准确定位范围", tone: "attention", evidenceRefs: ["evidence-debt-zhongdeng"] },
      { id: "debt-guarantees", label: "担保", value: "无异常记录", detail: "演示征信第 7 页两处区域交叉核验", tone: "neutral", evidenceRefs: ["evidence-credit-guarantee", "evidence-p3-credit-guarantee-related"] },
      { id: "debt-other-obligations", label: "其他偿债义务", value: "待核", detail: "模拟核验索引第 21 行", tone: "attention", evidenceRefs: ["evidence-debt-other-obligations"] },
    ],
    conclusion: "征信、借款、中登、担保与其他偿债义务统一归入负债；中登缺少准确定位范围，只进入人工复核。",
    sourceLabel: "演示征信、借款、中登、担保与其他偿债材料",
    isSimulated: true,
  },
  {
    dimensionId: "cashflow",
    visual: "cashflow-series",
    defaultView: "visual",
    availableViews: ["visual", "table"],
    unit: "万元",
    metrics: [
      { id: "cashflow-in", label: "半年流入", value: "8,080 万", note: "6个月账户流入合计", tone: "positive", evidenceRefs: ["evidence-cashflow-half-in"] },
      { id: "cashflow-out", label: "半年流出", value: "7,340 万", note: "6个月账户流出合计", tone: "neutral", evidenceRefs: ["evidence-cashflow-half-out"] },
      { id: "cashflow-net", label: "半年净流入", value: "740 万", note: "由半年流入与流出确定性派生", tone: "positive", evidenceRefs: ["evidence-cashflow-half-net-inputs"] },
      { id: "cashflow-anomalies-metric", label: "异常笔数", value: "7 笔", note: "待人工复核", tone: "attention", evidenceRefs: ["evidence-cashflow-anomalies"] },
    ],
    series: cashflowMonthlyData.map((item) => ({
      id: `cashflow-${item.id}`,
      label: item.label,
      note: "净额与净流入率由流入、流出确定性派生",
      measures: [
        { id: `cashflow-${item.id}-in`, label: "流入", value: item.inflow, unit: "万元", evidenceRefs: [`evidence-cashflow-${item.id}-in`] },
        { id: `cashflow-${item.id}-out`, label: "流出", value: item.outflow, unit: "万元", evidenceRefs: [`evidence-cashflow-${item.id}-out`] },
        { id: `cashflow-${item.id}-net`, label: "净额", value: item.inflow - item.outflow, unit: "万元", evidenceRefs: [`evidence-cashflow-${item.id}-net-inputs`] },
      ],
    })),
    compositions: [
      { id: "cashflow-inflow-parties", label: "流入方", segments: cashflowInflowParties.map((item) => ({ id: item.id, label: item.label, value: item.value, unit: "万元", note: item.note, tone: "neutral", evidenceRefs: [`evidence-${item.id}`] })) },
      { id: "cashflow-outflow-parties", label: "流出方", segments: cashflowOutflowParties.map((item) => ({ id: item.id, label: item.label, value: item.value, unit: "万元", note: item.note, tone: "neutral", evidenceRefs: [`evidence-${item.id}`] })) },
    ],
    breakdown: [
      { id: "cashflow-authenticity", label: "收支真实性", value: "基本成立", detail: "模拟核验索引第 22 行", tone: "positive", evidenceRefs: ["evidence-cashflow-authenticity"] },
      { id: "cashflow-operating-match", label: "经营匹配", value: "基本匹配", detail: "模拟核验索引第 23 行", tone: "neutral", evidenceRefs: ["evidence-cashflow-operating-match"] },
      { id: "cashflow-anomalies", label: "异常流水", value: "7 笔", detail: "大额、整额与关联往来逐笔明细待定位", tone: "attention", evidenceRefs: ["evidence-cashflow-anomalies"] },
    ],
    conclusion: "收支真实性、经营匹配与异常流水统一归入流水；趋势图和逐笔表格分别承载不同信息。",
    sourceLabel: "演示银行流水与经营匹配材料",
    isSimulated: true,
  },
];

export const mockMaterials: Material[] = [
  {
    id: "material-review-index",
    versionId: "material-review-index-v1",
    kind: "excel",
    fileName: "核验索引.xlsx",
    label: "首轮核验索引",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟核验索引",
    sheets: [{
      name: "核验索引",
      columns: ["序号", "维度", "栏目", "模拟结果", "来源说明"],
      rows: [
        [1, "合规", "营业执照", "有效", "模拟证照字段"],
        [2, "合规", "外部工商", "基本一致", "模拟外部核验"],
        [3, "合规", "主体涉诉", "未见异常", "模拟案件清单"],
        [4, "交易", "交易结构", "直租", "模拟合同摘要"],
        [5, "交易", "交易方案", "36 期", "模拟方案摘要"],
        [6, "交易", "交易关系", "三方", "模拟主体关系"],
        [7, "生产", "行业标签", "精密制造", "模拟行业分类"],
        [8, "生产", "设备", "8 台", "模拟设备清单"],
        [9, "生产", "工艺", "4 道", "模拟流程记录"],
        [10, "生产", "用电", "上升", "模拟月度账单"],
        [11, "生产", "打卡", "基本匹配", "模拟考勤汇总"],
        [12, "营收", "收入", "12,800 万", "模拟财务汇总"],
        [13, "营收", "订单", "12,040 万", "模拟订单汇总"],
        [14, "营收", "发票", "12,360 万", "模拟开票汇总"],
        [15, "营收", "经营表现", "稳定", "模拟趋势判断"],
        [16, "负债", "征信", "4,260 万", "模拟负债汇总"],
        [17, "负债", "借款", "3,140 万", "模拟借款明细"],
        [18, "负债", "其他偿债义务", "待核", "模拟或有义务"],
        [19, "流水", "收支真实性", "基本成立", "模拟流水汇总"],
        [20, "流水", "经营匹配", "基本匹配", "模拟趋势对照"],
      ],
    }, {
      name: "负债主体构成",
      columns: ["主体", "类别", "金额", "单位", "数据状态"],
      rows: [
        ["企业", "建设银行", 620, "万元", "脱敏模拟"],
        ["企业", "工商银行", 580, "万元", "脱敏模拟"],
        ["企业", "苏州银行", 600, "万元", "脱敏模拟"],
        ["企业", "远东宏信", 520, "万元", "脱敏模拟"],
        ["企业", "平安租赁", 440, "万元", "脱敏模拟"],
        ["企业", "仲利国际", 380, "万元", "脱敏模拟"],
        ["个人", "实控人", 381, "万元", "脱敏模拟"],
        ["个人", "配偶", 224, "万元", "脱敏模拟"],
        ["个人", "股东", 202, "万元", "脱敏模拟"],
        ["个人", "法定代表人", 179, "万元", "脱敏模拟"],
        ["个人", "亲属", 134, "万元", "脱敏模拟"],
      ],
    }, {
      name: "负债历史",
      columns: ["期间", "企业负债", "个人负债", "总负债", "单位", "数据状态"],
      rows: [
        ["2022", 2250, 830, 3080, "万元", "脱敏模拟；总负债由B/C派生"],
        ["2023", 2700, 1010, 3710, "万元", "脱敏模拟；总负债由B/C派生"],
        ["2024", 3140, 1120, 4260, "万元", "脱敏模拟；总负债由B/C派生"],
      ],
    }, {
      name: "偿债计划",
      columns: ["期间", "到期负债", "可偿还能力", "覆盖率", "单位", "数据状态"],
      rows: [
        ["2026-09", 150, 240, "160.0%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2026-10", 130, 210, "161.5%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2026-11", 180, 250, "138.9%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2026-12", 115, 190, "165.2%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-01", 175, 230, "131.4%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-02", 155, 220, "141.9%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-03", 140, 200, "142.9%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-04", 190, 250, "131.6%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-05", 125, 180, "144.0%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-06", 165, 230, "139.4%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-07", 150, 210, "140.0%", "万元", "脱敏模拟；覆盖率由B/C派生"],
        ["2027-08", 185, 240, "129.7%", "万元", "脱敏模拟；覆盖率由B/C派生"],
      ],
    }, {
      name: "流水月度",
      columns: ["期间", "流入", "流出", "净额", "净流入率", "单位", "数据状态"],
      rows: cashflowMonthlyData.map((item) => [
        item.label,
        item.inflow,
        item.outflow,
        item.inflow - item.outflow,
        `${cashflowNetRate(item.inflow, item.outflow).toFixed(1)}%`,
        "万元",
        "脱敏模拟；净额与净流入率由B/C派生",
      ]),
    }, {
      name: "流水交易对手",
      columns: ["方向", "交易对手", "金额", "占比", "账期", "单位", "数据状态"],
      rows: [
        ...cashflowInflowParties.map((item) => ["流入", item.label, item.value, `${item.share.toFixed(1)}%`, item.note, "万元", "脱敏模拟"]),
        ...cashflowOutflowParties.map((item) => ["流出", item.label, item.value, `${item.share.toFixed(1)}%`, item.note, "万元", "脱敏模拟"]),
      ],
    }, {
      name: "项目敞口",
      columns: ["正式产品通道", "通道额度上限(W)", "项目分配金额(W)", "整数份额", "历史存量敞口(W)", "本次融资金额(W)", "项目总敞口(W)", "契约版本", "重复融资核验", "数据状态"],
      rows: [
        ["200直", 200, 113, "21%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
        ["200核心", 200, 190, "35%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
        ["300核心", 300, 124, "23%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
        ["500核心", 500, 113, "21%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
        ["合计", 1200, 540, "100%", 419, 121, 540, "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
      ],
    }, ...(mockP3Materials[0]?.sheets ?? [])],
  },
  {
    id: "material-shareholding",
    versionId: "material-shareholding-v1",
    kind: "excel",
    fileName: "股权结构.xlsx",
    label: "股权结构表",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    availability: "available",
    isSimulated: true,
    sourceLabel: "股权结构表",
    sheets: [{
      name: "股权结构表",
      columns: ["序号", "股东名称", "股东类型", "出资额", "持股比例"],
      rows: [
        [1, "华东控股有限公司", "企业法人", "4,500.00", "90.00%"],
        [2, "李娜", "自然人", "500.00", "10.00%"],
        [3, "其他自然人股东", "自然人", "—", "—"],
        ["", "合计", "", "5,000.00", "100.00%"],
      ],
    }, {
      name: "主体关系图",
      columns: ["对象类型", "对象名称", "关系", "关联对象", "核验状态"],
      rows: [
        ["公司", "华东精密制造有限公司", "承租主体", "本项目", "已定位"],
        ["公司", "华东控股有限公司", "控股股东", "华东精密制造有限公司", "已定位"],
        ["自然人", "王强", "法定代表人 / 实控人", "华东精密制造有限公司", "已定位"],
        ["自然人", "李娜", "股东", "华东精密制造有限公司", "已定位"],
        ["自然人", "陈明", "关联联系人", "华东精密制造有限公司", "待补材料"],
        ["公司", "华东控股有限公司", "持股 90%", "华东精密制造有限公司", "已定位"],
        ["自然人", "王强", "法定代表人", "华东精密制造有限公司", "已定位"],
        ["自然人", "王强", "实际控制", "华东精密制造有限公司", "已定位"],
        ["自然人", "李娜", "持股 10%", "华东精密制造有限公司", "已定位"],
        ["自然人", "陈明", "关联", "华东精密制造有限公司", "待定位"],
      ],
    }],
  },
  {
    id: "material-credit",
    versionId: "material-credit-v1",
    kind: "pdf",
    fileName: "企业征信.pdf",
    label: "企业征信报告",
    mimeType: "application/pdf",
    availability: "available",
    isSimulated: true,
    sourceLabel: "企业征信报告",
    pageCount: 12,
    pages: [{ page: 7, title: "企业基本信息", lines: ["法定代表人：王强", "对外担保：无异常记录"] }],
  },
  {
    id: "material-revenue-chain",
    versionId: "material-revenue-chain-v1",
    kind: "excel",
    fileName: "营收来源链.xlsx",
    label: "营收来源链",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟合同、发票、回款与收入汇总台账",
    sheets: [{
      name: "营收链",
      columns: ["期间", "合同订单", "发票", "回款流水", "确认收入", "单位", "汇总口径", "发票-订单差异", "回款-发票差异", "收入-回款差异"],
      rows: [
        ["2022", 9000, 8240, 7880, 8600, "万元", "年度累计，含期初订单", -760, -360, 720],
        ["2023", 10860, 10080, 9840, 10400, "万元", "年度累计，含期初订单", -780, -240, 560],
        ["2024", 12040, 12360, 11790, 12800, "万元", "年度累计，含跨期履约", 320, -570, 1010],
      ],
    }, {
      name: "上下游构成",
      columns: ["方向", "类别", "占比", "单位", "数据状态"],
      rows: [
        ["上游", "核心原材料", 42, "%", "脱敏模拟"],
        ["上游", "设备耗材", 33, "%", "脱敏模拟"],
        ["上游", "物流能源", 25, "%", "脱敏模拟"],
        ["下游", "制造客户", 48, "%", "脱敏模拟"],
        ["下游", "经销渠道", 31, "%", "脱敏模拟"],
        ["下游", "服务客户", 21, "%", "脱敏模拟"],
      ],
    }, {
      name: "应收账龄",
      columns: ["账龄", "占比", "单位", "数据状态"],
      rows: [
        ["30天内", 55, "%", "脱敏模拟"],
        ["31–60天", 28, "%", "脱敏模拟"],
        ["60天以上", 17, "%", "脱敏模拟"],
      ],
    }, {
      name: "利润与租金覆盖",
      columns: ["期间", "年度营收(万元)", "材料成本", "场地房租", "水电费用", "人工费用", "其他费用", "净利润", "净利率", "前12期项目租金(万元)", "租金覆盖倍数", "口径", "数据状态"],
      rows: [[2024, 12800, 9600, 360, 384, 278.4, 677.6, 1500, "11.7%", 72.318, "20.74×", "净利润=营收-五项费用；覆盖倍数=净利润/前12期项目租金", "脱敏模拟"]],
    }],
  },
  {
    id: "material-factory",
    versionId: "material-factory-v1",
    kind: "image",
    fileName: "厂房现场.png",
    label: "厂房现场图",
    mimeType: "image/png",
    assetUrl: "/mock-materials/precision-workshop-main.png",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟现场材料",
    pixelWidth: 1672,
    pixelHeight: 941,
    description: "厂房生产区域与设备摆放情况。",
    focalArea: { x: 0.18, y: 0.22, width: 0.56, height: 0.48 },
  },
  {
    id: "material-factory-supplement",
    versionId: "material-factory-supplement-v1",
    kind: "image",
    fileName: "现场补充.png",
    label: "现场补充图",
    mimeType: "image/png",
    assetUrl: "/mock-materials/equipment-nameplate-station.png",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟现场材料",
    pixelWidth: 1672,
    pixelHeight: 941,
    description: "设备铭牌与工位动线补充视角。",
    focalArea: { x: 0.22, y: 0.28, width: 0.46, height: 0.4 },
  },
  {
    id: "material-site-video",
    versionId: "material-site-video-v1",
    kind: "media",
    fileName: "现场巡检视频.mp4",
    label: "现场巡检视频",
    mimeType: "video/mp4",
    mediaKind: "video",
    durationSeconds: 42,
    description: "脱敏模拟巡检视频清单与时间范围；未嵌入真实客户视频。",
    posterMaterialId: "material-factory-supplement",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟现场视频清单",
  },
  {
    id: "material-site-panorama",
    versionId: "material-site-panorama-v1",
    kind: "media",
    fileName: "车间全景.local",
    label: "车间全景",
    mimeType: "image/vnd.compare.panorama",
    mediaKind: "panorama",
    durationSeconds: null,
    description: "本地模拟 360° 车间全景占位；无远程资产。",
    posterMaterialId: "material-factory",
    availability: "available",
    isSimulated: true,
    sourceLabel: "脱敏模拟全景资产清单",
  },
  {
    id: "material-site-scene",
    versionId: "material-site-scene-v1",
    kind: "scene",
    fileName: "现场空间.scene.json",
    label: "现场空间预览",
    mimeType: "application/vnd.compare.gaussian-scene+json",
    sceneFormat: "compare-gaussian-preview-v1",
    points: Array.from({ length: 96 }, (_, index) => ({
      id: `scene-point-${index + 1}`,
      x: ((index % 12) - 5.5) * 0.34,
      y: (Math.floor(index / 12) - 3.5) * 0.24 + Math.sin(index * 0.7) * 0.08,
      z: Math.cos(index * 0.47) * 0.75 + (index % 3) * 0.18,
      size: 5 + (index % 5),
      color: ["#52575a", "#777d80", "#a4a8a7", "#476b65", "#6d6257"][index % 5],
    })),
    fallbackMaterialId: "material-factory",
    description: "本地模拟点云近似现场原型，非真实 3DGS 重建。",
    availability: "available",
    isSimulated: true,
    sourceLabel: "本地脱敏模拟空间点清单",
  },
  ...mockP2Materials,
];

function pendingEvidence(id: string, label: string): EvidenceReference {
  return {
    id,
    label,
    locator: null,
    locationStatus: "pending",
    materialStatus: "review",
  };
}

function unverifiableEvidence(id: string, label: string): EvidenceReference {
  return {
    id,
    label,
    locator: null,
    locationStatus: "unverifiable",
    materialStatus: "conflict",
  };
}

function indexedEvidence(id: string, label: string, row: number, materialStatus: EvidenceReference["materialStatus"] = "confirmed"): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-review-index", materialVersionId: "material-review-index-v1", sheet: "核验索引", range: `C${row}:E${row}` },
    locationStatus: "located",
    materialStatus,
  };
}

function subjectEvidence(id: string, label: string, row: number, materialStatus: EvidenceReference["materialStatus"] = "confirmed"): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-shareholding", materialVersionId: "material-shareholding-v1", sheet: "主体关系图", range: `B${row}:E${row}` },
    locationStatus: "located",
    materialStatus,
  };
}

function revenueEvidence(id: string, label: string, row: number, column: "B" | "C" | "D" | "E"): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-revenue-chain", materialVersionId: "material-revenue-chain-v1", sheet: "营收链", range: `${column}${row}:${column}${row}` },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

function revenueComparisonEvidence(id: string, label: string, row: number, column: "H" | "I" | "J"): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-revenue-chain", materialVersionId: "material-revenue-chain-v1", sheet: "营收链", range: `${column}${row}:${column}${row}` },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

function revenueDerivedEvidence(id: string, label: string, range: string): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-revenue-chain", materialVersionId: "material-revenue-chain-v1", sheet: "营收链", range },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

function revenueCompositionEvidence(id: string, label: string, sheet: "上下游构成" | "应收账龄", row: number): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-revenue-chain", materialVersionId: "material-revenue-chain-v1", sheet, range: `B${row}:C${row}` },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

function debtExcelEvidence(id: string, label: string, sheet: "负债主体构成" | "负债历史" | "偿债计划" | "项目敞口", range: string): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-review-index", materialVersionId: "material-review-index-v1", sheet, range },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

function revenueProfitEvidence(id: string, label: string, range: string): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-revenue-chain", materialVersionId: "material-revenue-chain-v1", sheet: "利润与租金覆盖", range },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

function cashflowExcelEvidence(id: string, label: string, sheet: "流水月度" | "流水交易对手", range: string): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId: "material-review-index", materialVersionId: "material-review-index-v1", sheet, range },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

export const mockEvidence: EvidenceReference[] = [
  revenueEvidence("evidence-revenue-2022-orders", "2022 合同订单", 4, "B"),
  revenueEvidence("evidence-revenue-2022-invoices", "2022 发票", 4, "C"),
  revenueEvidence("evidence-revenue-2022-collections", "2022 回款流水", 4, "D"),
  revenueEvidence("evidence-revenue-2022-income", "2022 确认收入", 4, "E"),
  revenueEvidence("evidence-revenue-2023-orders", "2023 合同订单", 5, "B"),
  revenueEvidence("evidence-revenue-2023-invoices", "2023 发票", 5, "C"),
  revenueEvidence("evidence-revenue-2023-collections", "2023 回款流水", 5, "D"),
  revenueEvidence("evidence-revenue-2023-income", "2023 确认收入", 5, "E"),
  revenueEvidence("evidence-revenue-2024-orders", "2024 合同订单", 6, "B"),
  revenueEvidence("evidence-revenue-2024-invoices", "2024 发票", 6, "C"),
  revenueEvidence("evidence-revenue-2024-collections", "2024 回款流水", 6, "D"),
  revenueEvidence("evidence-revenue-2024-income", "2024 确认收入", 6, "E"),
  revenueDerivedEvidence("evidence-revenue-2023-income-growth-inputs", "2023 确认收入环比派生输入", "E4:E5"),
  revenueDerivedEvidence("evidence-revenue-2024-income-growth-inputs", "2024 确认收入环比派生输入", "E5:E6"),
  revenueDerivedEvidence("evidence-revenue-2022-collections-rate-inputs", "2022 回款率派生输入", "C4:D4"),
  revenueDerivedEvidence("evidence-revenue-2023-collections-rate-inputs", "2023 回款率派生输入", "C5:D5"),
  revenueDerivedEvidence("evidence-revenue-2024-collections-rate-inputs", "2024 回款率派生输入", "C6:D6"),
  revenueCompositionEvidence("evidence-revenue-upstream-material", "上游核心原材料构成", "上下游构成", 4),
  revenueCompositionEvidence("evidence-revenue-upstream-equipment", "上游设备耗材构成", "上下游构成", 5),
  revenueCompositionEvidence("evidence-revenue-upstream-energy", "上游物流能源构成", "上下游构成", 6),
  revenueCompositionEvidence("evidence-revenue-downstream-manufacturing", "下游制造客户构成", "上下游构成", 7),
  revenueCompositionEvidence("evidence-revenue-downstream-channel", "下游经销渠道构成", "上下游构成", 8),
  revenueCompositionEvidence("evidence-revenue-downstream-service", "下游服务客户构成", "上下游构成", 9),
  revenueCompositionEvidence("evidence-revenue-aging-30", "30天内应收账龄构成", "应收账龄", 4),
  revenueCompositionEvidence("evidence-revenue-aging-60", "31–60天应收账龄构成", "应收账龄", 5),
  revenueCompositionEvidence("evidence-revenue-aging-over-60", "60天以上应收账龄构成", "应收账龄", 6),
  revenueProfitEvidence("evidence-revenue-profit-annual-revenue", "2024 年度营收", "B4:B4"),
  revenueProfitEvidence("evidence-revenue-profit-material", "材料成本", "C4:C4"),
  revenueProfitEvidence("evidence-revenue-profit-site-rent", "场地房租", "D4:D4"),
  revenueProfitEvidence("evidence-revenue-profit-utilities", "水电费用", "E4:E4"),
  revenueProfitEvidence("evidence-revenue-profit-payroll", "人工费用", "F4:F4"),
  revenueProfitEvidence("evidence-revenue-profit-other", "其他费用", "G4:G4"),
  revenueProfitEvidence("evidence-revenue-profit-net-profit", "年度净利润", "H4:H4"),
  revenueProfitEvidence("evidence-revenue-profit-margin-inputs", "净利率派生输入", "B4:H4"),
  revenueProfitEvidence("evidence-revenue-profit-rent-summary", "前12期项目租金汇总", "J4:J4"),
  revenueProfitEvidence("evidence-revenue-profit-coverage-inputs", "租金覆盖倍数派生输入", "H4:K4"),
  debtExcelEvidence("evidence-debt-exposure-direct-200", "200直项目敞口分配", "项目敞口", "A4:D4"),
  debtExcelEvidence("evidence-debt-exposure-core-200", "200核心项目敞口分配", "项目敞口", "A5:D5"),
  debtExcelEvidence("evidence-debt-exposure-core-300", "300核心项目敞口分配", "项目敞口", "A6:D6"),
  debtExcelEvidence("evidence-debt-exposure-core-500", "500核心项目敞口分配", "项目敞口", "A7:D7"),
  debtExcelEvidence("evidence-debt-exposure-history", "项目历史存量敞口", "项目敞口", "E8:E8"),
  debtExcelEvidence("evidence-debt-exposure-current", "项目本次融资", "项目敞口", "F8:F8"),
  debtExcelEvidence("evidence-debt-exposure-total", "项目总敞口", "项目敞口", "G8:G8"),
  debtExcelEvidence("evidence-debt-exposure-summary-inputs", "项目敞口汇总输入", "项目敞口", "E8:G8"),
  ...[
    ["debt-enterprise-ccb", "企业负债·建设银行"],
    ["debt-enterprise-icbc", "企业负债·工商银行"],
    ["debt-enterprise-suzhou", "企业负债·苏州银行"],
    ["debt-enterprise-feh", "企业负债·远东宏信"],
    ["debt-enterprise-pingan", "企业负债·平安租赁"],
    ["debt-enterprise-chailease", "企业负债·仲利国际"],
    ["debt-personal-controller", "个人负债·实控人"],
    ["debt-personal-spouse", "个人负债·配偶"],
    ["debt-personal-shareholder", "个人负债·股东"],
    ["debt-personal-legal", "个人负债·法定代表人"],
    ["debt-personal-relative", "个人负债·亲属"],
  ].map(([id, label], index) => debtExcelEvidence(`evidence-${id}`, label, "负债主体构成", `A${index + 4}:D${index + 4}`)),
  ...[2022, 2023, 2024].flatMap((year, index) => {
    const row = index + 4;
    return [
      debtExcelEvidence(`evidence-debt-history-${year}-enterprise`, `${year} 企业负债`, "负债历史", `B${row}:B${row}`),
      debtExcelEvidence(`evidence-debt-history-${year}-personal`, `${year} 个人负债`, "负债历史", `C${row}:C${row}`),
      debtExcelEvidence(`evidence-debt-history-${year}-total-inputs`, `${year} 总负债派生输入`, "负债历史", `B${row}:C${row}`),
    ];
  }),
  debtExcelEvidence("evidence-debt-repayment-total-due-inputs", "未来12月到期负债合计输入", "偿债计划", "B4:B15"),
  ...["2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06", "2027-07", "2027-08"].flatMap((period, index) => {
    const row = index + 4;
    return [
      debtExcelEvidence(`evidence-debt-repayment-${period}-due`, `${period} 到期负债`, "偿债计划", `B${row}:B${row}`),
      debtExcelEvidence(`evidence-debt-repayment-${period}-comparison-inputs`, `${period} 可偿还能力比较输入`, "偿债计划", `B${row}:C${row}`),
    ];
  }),
  cashflowExcelEvidence("evidence-cashflow-half-in", "半年流入合计", "流水月度", "B4:B9"),
  cashflowExcelEvidence("evidence-cashflow-half-out", "半年流出合计", "流水月度", "C4:C9"),
  cashflowExcelEvidence("evidence-cashflow-half-net-inputs", "半年净流入派生输入", "流水月度", "B4:C9"),
  ...cashflowMonthlyData.flatMap((item, index) => {
    const row = index + 4;
    return [
      cashflowExcelEvidence(`evidence-cashflow-${item.id}-in`, `${item.label}流入`, "流水月度", `B${row}:B${row}`),
      cashflowExcelEvidence(`evidence-cashflow-${item.id}-out`, `${item.label}流出`, "流水月度", `C${row}:C${row}`),
      cashflowExcelEvidence(`evidence-cashflow-${item.id}-net-inputs`, `${item.label}净额派生输入`, "流水月度", `B${row}:C${row}`),
      cashflowExcelEvidence(`evidence-cashflow-${item.id}-net-rate-inputs`, `${item.label}净流入率派生输入`, "流水月度", `B${row}:C${row}`),
    ];
  }),
  ...[...cashflowInflowParties, ...cashflowOutflowParties].map((item, index) => cashflowExcelEvidence(
    `evidence-${item.id}`,
    `${item.label}交易对手构成`,
    "流水交易对手",
    `A${index + 4}:G${index + 4}`,
  )),
  ...[4, 5, 6].flatMap((row, index) => {
    const year = 2022 + index;
    return [
      revenueComparisonEvidence(`evidence-revenue-${year}-gap-invoices`, `${year} 发票与订单汇总差异`, row, "H"),
      revenueComparisonEvidence(`evidence-revenue-${year}-gap-collections`, `${year} 回款与发票汇总差异`, row, "I"),
      revenueComparisonEvidence(`evidence-revenue-${year}-gap-income`, `${year} 收入与回款汇总差异`, row, "J"),
    ];
  }),
  subjectEvidence("evidence-subject-borrower", "承租主体", 4),
  subjectEvidence("evidence-subject-holding", "控股股东", 5),
  subjectEvidence("evidence-subject-wang", "王强主体身份", 6),
  subjectEvidence("evidence-subject-li", "李娜主体身份", 7),
  subjectEvidence("evidence-subject-chen", "陈明关联身份", 8, "review"),
  subjectEvidence("evidence-relation-holding", "控股关系", 9),
  subjectEvidence("evidence-relation-legal", "法定代表人关系", 10),
  subjectEvidence("evidence-relation-controller", "实际控制关系", 11),
  subjectEvidence("evidence-relation-li-share", "自然人持股关系", 12),
  pendingEvidence("evidence-relation-chen-affiliate", "关联关系（待定位）"),
  {
    id: "evidence-controller",
    label: "实际控制人及股权关系",
    locator: { kind: "excel", materialId: "material-shareholding", materialVersionId: "material-shareholding-v1", sheet: "股权结构表", range: "D4:D7" },
    locationStatus: "located",
    materialStatus: "confirmed",
  },
  {
    id: "evidence-share-ratio",
    label: "持股比例合计",
    locator: { kind: "excel", materialId: "material-shareholding", materialVersionId: "material-shareholding-v1", sheet: "股权结构表", range: "E4:E7" },
    locationStatus: "located",
    materialStatus: "confirmed",
  },
  {
    id: "evidence-credit-guarantee",
    label: "对外担保记录",
    locator: { kind: "pdf", materialId: "material-credit", materialVersionId: "material-credit-v1", page: 7, bbox: { x: 0.12, y: 0.26, width: 0.74, height: 0.18 }, textAnchor: "对外担保" },
    locationStatus: "located",
    materialStatus: "review",
  },
  {
    id: "evidence-factory-site",
    label: "厂房经营现场",
    locator: { kind: "image", materialId: "material-factory", materialVersionId: "material-factory-v1", bbox: { x: 0.18, y: 0.22, width: 0.56, height: 0.48 } },
    locationStatus: "located",
    materialStatus: "confirmed",
  },
  {
    id: "evidence-factory-supplement",
    label: "设备铭牌补充视角",
    locator: { kind: "image", materialId: "material-factory-supplement", materialVersionId: "material-factory-supplement-v1", bbox: { x: 0.22, y: 0.28, width: 0.46, height: 0.4 } },
    locationStatus: "located",
    materialStatus: "confirmed",
  },
  {
    id: "evidence-site-video",
    label: "现场巡检视频 00:08–00:18",
    locator: { kind: "media", materialId: "material-site-video", materialVersionId: "material-site-video-v1", startSeconds: 8, endSeconds: 18 },
    locationStatus: "located",
    materialStatus: "review",
  },
  {
    id: "evidence-site-panorama",
    label: "车间全景主视角",
    locator: { kind: "media", materialId: "material-site-panorama", materialVersionId: "material-site-panorama-v1", startSeconds: 0, endSeconds: 0 },
    locationStatus: "located",
    materialStatus: "confirmed",
  },
  {
    id: "evidence-site-equipment-points",
    label: "设备点位 12 / 34 / 58",
    locator: { kind: "scene", materialId: "material-site-scene", materialVersionId: "material-site-scene-v1", pointIds: ["scene-point-12", "scene-point-34", "scene-point-58"] },
    locationStatus: "located",
    materialStatus: "review",
  },
  {
    id: "evidence-site-scene",
    label: "现场空间资产清单",
    locator: { kind: "scene", materialId: "material-site-scene", materialVersionId: "material-site-scene-v1", pointIds: ["scene-point-1", "scene-point-96"] },
    locationStatus: "located",
    materialStatus: "confirmed",
  },
  {
    id: "evidence-nominee-statement-pending",
    label: "代持说明（待上传）",
    locator: null,
    locationStatus: "pending",
    materialStatus: "review",
  },
  {
    id: "evidence-credit-version-mismatch",
    label: "旧版征信股东记录",
    locator: { kind: "pdf", materialId: "material-credit", materialVersionId: "material-credit-v0", page: 7, bbox: { x: 0.12, y: 0.51, width: 0.74, height: 0.14 }, textAnchor: "股东信息" },
    locationStatus: "version_mismatch",
    materialStatus: "conflict",
  },
  indexedEvidence("evidence-compliance-license", "营业执照字段", 4),
  pendingEvidence("evidence-compliance-identity", "身份证字段（待定位）"),
  pendingEvidence("evidence-compliance-charter", "章程字段（待定位）"),
  indexedEvidence("evidence-compliance-registry", "外部工商字段", 5),
  indexedEvidence("evidence-compliance-subject-litigation", "主体涉诉清单", 6),
  unverifiableEvidence("evidence-compliance-personal-litigation", "个人涉诉清单（不可核验）"),
  indexedEvidence("evidence-transaction-structure", "交易结构材料", 7),
  indexedEvidence("evidence-transaction-relations", "交易关系材料", 9),
  indexedEvidence("evidence-production-industry", "行业标签来源", 10),
  indexedEvidence("evidence-production-equipment", "设备清单", 11),
  indexedEvidence("evidence-production-process", "工艺材料", 12),
  indexedEvidence("evidence-production-electricity", "用电材料", 13),
  indexedEvidence("evidence-production-attendance", "打卡记录", 14, "review"),
  indexedEvidence("evidence-revenue-income", "收入明细", 15),
  indexedEvidence("evidence-revenue-orders", "订单明细", 16),
  indexedEvidence("evidence-revenue-invoices", "发票明细", 17),
  indexedEvidence("evidence-revenue-performance", "经营表现来源", 18),
  indexedEvidence("evidence-debt-credit", "征信负债明细", 19, "review"),
  indexedEvidence("evidence-debt-loans", "借款明细", 20, "review"),
  pendingEvidence("evidence-debt-zhongdeng", "中登登记清单（待定位）"),
  indexedEvidence("evidence-debt-other-obligations", "其他偿债义务", 21, "review"),
  indexedEvidence("evidence-cashflow-authenticity", "收支真实性明细", 22),
  indexedEvidence("evidence-cashflow-operating-match", "经营匹配明细", 23),
  pendingEvidence("evidence-cashflow-anomalies", "异常流水明细（待定位）"),
  ...mockP2Evidence,
  ...mockP3Evidence,
];

export const mockFacts: FactVersion[] = [
  { id: "fact-license-v1", factKey: "compliance.business_license", dimensionId: "compliance", version: 1, label: "营业执照", value: "有效", unit: null, source: "mock_material_extract", evidenceRefs: ["evidence-compliance-license"], createdAt: "2026-08-08T10:10:00+09:00", isSimulated: true },
  { id: "fact-identity-v1", factKey: "compliance.identity", dimensionId: "compliance", version: 1, label: "身份证", value: "待核", unit: null, source: "mock_material_extract", evidenceRefs: ["evidence-compliance-identity"], createdAt: "2026-08-08T10:11:00+09:00", isSimulated: true },
  { id: "fact-charter-v2", factKey: "compliance.charter", dimensionId: "compliance", version: 2, label: "章程", value: "版本待核", unit: null, source: "mock_business_correction", evidenceRefs: ["evidence-compliance-charter"], createdAt: "2026-08-08T10:20:00+09:00", isSimulated: true },
  { id: "fact-registry-v1", factKey: "compliance.external_registry", dimensionId: "compliance", version: 1, label: "外部工商", value: "基本一致", unit: null, source: "mock_material_extract", evidenceRefs: ["evidence-compliance-registry"], createdAt: "2026-08-08T10:12:00+09:00", isSimulated: true },
  { id: "fact-subject-litigation-v1", factKey: "compliance.subject_litigation", dimensionId: "compliance", version: 1, label: "主体涉诉", value: "待核", unit: null, source: "mock_material_extract", evidenceRefs: ["evidence-compliance-subject-litigation"], createdAt: "2026-08-08T10:13:00+09:00", isSimulated: true },
  { id: "fact-personal-litigation-v1", factKey: "compliance.personal_litigation", dimensionId: "compliance", version: 1, label: "个人涉诉", value: "待人工确认", unit: null, source: "mock_material_extract", evidenceRefs: ["evidence-compliance-personal-litigation"], createdAt: "2026-08-08T10:14:00+09:00", isSimulated: true },
  { id: "fact-debt-credit-v1", factKey: "debt.credit_balance", dimensionId: "debt", version: 1, label: "征信负债", value: 4260, unit: "万元", source: "mock_material_extract", evidenceRefs: ["evidence-debt-credit"], createdAt: "2026-08-08T10:14:20+09:00", isSimulated: true },
  { id: "fact-debt-loans-v1", factKey: "debt.loan_balance", dimensionId: "debt", version: 1, label: "借款余额", value: 3140, unit: "万元", source: "mock_material_extract", evidenceRefs: ["evidence-debt-loans"], createdAt: "2026-08-08T10:14:25+09:00", isSimulated: true },
  { id: "fact-debt-zhongdeng-v1", factKey: "debt.registration", dimensionId: "debt", version: 1, label: "中登登记", value: "待定位", unit: null, source: "mock_material_extract", evidenceRefs: ["evidence-debt-zhongdeng"], createdAt: "2026-08-08T10:14:30+09:00", isSimulated: true },
  ...mockP2Facts,
];

export const mockComplianceGraph: ComplianceSubjectGraph = {
  nodes: [
    { id: "subject-company-borrower", kind: "company", name: "华东精密制造有限公司", role: "承租主体", verificationStatus: "confirmed", evidenceRefs: ["evidence-subject-borrower"] },
    { id: "subject-company-holding", kind: "company", name: "华东控股有限公司", role: "控股股东", verificationStatus: "confirmed", evidenceRefs: ["evidence-subject-holding"] },
    { id: "subject-person-wang", kind: "person", name: "王强", role: "法定代表人 / 实控人", verificationStatus: "confirmed", evidenceRefs: ["evidence-subject-wang"] },
    { id: "subject-person-li", kind: "person", name: "李娜", role: "自然人股东", verificationStatus: "confirmed", evidenceRefs: ["evidence-subject-li"] },
    { id: "subject-person-chen", kind: "person", name: "陈明", role: "关联联系人", verificationStatus: "review", evidenceRefs: ["evidence-subject-chen"] },
  ],
  relations: [
    { id: "relation-holding-borrower", fromId: "subject-company-holding", toId: "subject-company-borrower", relation: "shareholding", sharePercent: 90, label: "持股 90%", verificationStatus: "confirmed", evidenceRefs: ["evidence-relation-holding"] },
    { id: "relation-wang-legal", fromId: "subject-person-wang", toId: "subject-company-borrower", relation: "legal_representative", label: "法定代表人", verificationStatus: "confirmed", evidenceRefs: ["evidence-relation-legal"] },
    { id: "relation-wang-controller", fromId: "subject-person-wang", toId: "subject-company-borrower", relation: "controller", label: "实际控制", verificationStatus: "confirmed", evidenceRefs: ["evidence-relation-controller"] },
    { id: "relation-li-borrower", fromId: "subject-person-li", toId: "subject-company-borrower", relation: "shareholding", sharePercent: 10, label: "持股 10%", verificationStatus: "confirmed", evidenceRefs: ["evidence-relation-li-share"] },
    { id: "relation-chen-affiliate", fromId: "subject-person-chen", toId: "subject-company-borrower", relation: "affiliate", label: "关联关系待核", verificationStatus: "review", evidenceRefs: ["evidence-relation-chen-affiliate"] },
  ],
  attachments: [
    { id: "attachment-license", subjectId: "subject-company-borrower", factVersionId: "fact-license-v1", label: "营业执照", verificationStatus: "confirmed", evidenceRefs: ["evidence-compliance-license"] },
    { id: "attachment-charter", subjectId: "subject-company-borrower", factVersionId: "fact-charter-v2", label: "章程", verificationStatus: "review", evidenceRefs: ["evidence-compliance-charter"] },
    { id: "attachment-registry", subjectId: "subject-company-borrower", factVersionId: "fact-registry-v1", label: "外部工商", verificationStatus: "confirmed", evidenceRefs: ["evidence-compliance-registry"] },
    { id: "attachment-company-litigation", subjectId: "subject-company-borrower", factVersionId: "fact-subject-litigation-v1", label: "主体涉诉", verificationStatus: "confirmed", evidenceRefs: ["evidence-compliance-subject-litigation"] },
    { id: "attachment-holding-registry", subjectId: "subject-company-holding", factVersionId: "fact-registry-v1", label: "外部工商", verificationStatus: "confirmed", evidenceRefs: ["evidence-compliance-registry"] },
    { id: "attachment-holding-litigation", subjectId: "subject-company-holding", factVersionId: "fact-subject-litigation-v1", label: "主体涉诉", verificationStatus: "confirmed", evidenceRefs: ["evidence-compliance-subject-litigation"] },
    { id: "attachment-wang-identity", subjectId: "subject-person-wang", factVersionId: "fact-identity-v1", label: "身份证", verificationStatus: "review", evidenceRefs: ["evidence-compliance-identity"] },
    { id: "attachment-wang-litigation", subjectId: "subject-person-wang", factVersionId: "fact-personal-litigation-v1", label: "个人涉诉", verificationStatus: "conflict", evidenceRefs: ["evidence-compliance-personal-litigation"] },
    { id: "attachment-li-identity", subjectId: "subject-person-li", factVersionId: "fact-identity-v1", label: "身份证", verificationStatus: "review", evidenceRefs: ["evidence-compliance-identity"] },
    { id: "attachment-li-litigation", subjectId: "subject-person-li", factVersionId: "fact-personal-litigation-v1", label: "个人涉诉", verificationStatus: "conflict", evidenceRefs: ["evidence-compliance-personal-litigation"] },
    { id: "attachment-chen-identity", subjectId: "subject-person-chen", factVersionId: "fact-identity-v1", label: "身份证", verificationStatus: "review", evidenceRefs: ["evidence-compliance-identity"] },
    { id: "attachment-chen-litigation", subjectId: "subject-person-chen", factVersionId: "fact-personal-litigation-v1", label: "个人涉诉", verificationStatus: "conflict", evidenceRefs: ["evidence-compliance-personal-litigation"] },
  ],
  sourceLabel: "脱敏模拟主体、关系和材料核验清单",
  isSimulated: true,
};

export const mockOnsiteAssets: OnsiteAsset[] = [
  { id: "onsite-primary-image", label: "现场主图", kind: "image", collectionStatus: "collected", materialId: "material-factory", sourceLabel: "脱敏模拟现场采集", evidenceRefs: ["evidence-factory-site", "evidence-p3-factory-equipment-zone"], lazyLoad: false, isSimulated: true },
  { id: "onsite-supplement-image", label: "设备铭牌补充图", kind: "supplement", collectionStatus: "collected", materialId: "material-factory-supplement", sourceLabel: "脱敏模拟补充采集", evidenceRefs: ["evidence-factory-supplement"], lazyLoad: false, isSimulated: true },
  { id: "onsite-video", label: "巡检视频", kind: "video", collectionStatus: "processing", materialId: "material-site-video", sourceLabel: "本地模拟媒体清单", evidenceRefs: ["evidence-site-video"], lazyLoad: true, isSimulated: true },
  { id: "onsite-panorama", label: "车间全景", kind: "panorama", collectionStatus: "collected", materialId: "material-site-panorama", sourceLabel: "本地模拟全景清单", evidenceRefs: ["evidence-site-panorama"], lazyLoad: true, isSimulated: true },
  { id: "onsite-equipment-points", label: "设备点位", kind: "equipment_point", collectionStatus: "processing", materialId: "material-site-scene", sourceLabel: "本地模拟空间点位", evidenceRefs: ["evidence-site-equipment-points"], lazyLoad: true, isSimulated: true },
  { id: "onsite-scene", label: "3DGS 场景原型", kind: "scene_3dgs", collectionStatus: "collected", materialId: "material-site-scene", sourceLabel: "本地模拟点云近似；非真实 3DGS", evidenceRefs: ["evidence-site-scene"], lazyLoad: true, isSimulated: true },
];

export const mockHardConstraints: HardConstraintResult[] = [
  {
    id: "hard-h03-v1",
    ruleId: "H-03",
    ruleVersion: "policy-2026.08",
    title: "章程与中登登记必须人工复核",
    result: "manual_review",
    evidenceTargets: [
      { evidenceRef: "evidence-compliance-charter", dimensionId: "compliance", reviewTargetId: "graph-attachment-attachment-charter", factVersionId: "fact-charter-v2", unavailableReason: "章程签署页尚未完成准确定位" },
      { evidenceRef: "evidence-debt-zhongdeng", dimensionId: "debt", reviewTargetId: "debt-zhongdeng", factVersionId: "fact-debt-zhongdeng-v1", unavailableReason: "中登登记清单尚未完成准确定位" },
    ],
    primaryTarget: { evidenceRef: "evidence-compliance-charter", dimensionId: "compliance", reviewTargetId: "graph-attachment-attachment-charter", factVersionId: "fact-charter-v2", unavailableReason: "章程签署页尚未完成准确定位" },
    scope: "承租主体章程与融资登记口径首轮核验",
    evidenceRequirement: "当前有效章程签署页与中登登记清单的可复核定位范围",
    gateTriggered: true,
    responsibleParty: "joint",
    nextAction: "业务补齐定位，风控完成规则适用与人工认定",
    explanation: "章程有效版本与中登登记清单尚未完成准确定位，必须人工复核；不自动形成拒绝。",
    evaluatedAt: "2026-08-08T10:25:00+09:00",
    isSimulated: true,
  },
];

export const mockGlobalRiskSummary: GlobalRiskSummary = {
  id: "global-risk-summary-v1",
  name: "风险",
  level: "confirm",
  scoreGrade: scoreToGrade(mockOverallScore),
  decisionGrade: "C",
  confidence: 68,
  summary: "演示规则汇总：未命中禁止性条件，但存在需要人工认定的材料缺口与偿债口径差异。",
  evidenceRefs: ["evidence-compliance-charter", "evidence-debt-zhongdeng", "evidence-cashflow-anomalies"],
  hardConstraintResults: mockHardConstraints,
  keyAnomalies: [
    {
      id: "risk-anomaly-debt-registration",
      title: "偿债口径差异",
      detail: "征信、借款与中登登记尚未形成可复现的交叉定位。",
      level: "attention",
      evidenceTargets: [
        { evidenceRef: "evidence-debt-credit", dimensionId: "debt", reviewTargetId: "debt-credit", factVersionId: "fact-debt-credit-v1" },
        { evidenceRef: "evidence-debt-loans", dimensionId: "debt", reviewTargetId: "debt-loans", factVersionId: "fact-debt-loans-v1" },
        { evidenceRef: "evidence-debt-zhongdeng", dimensionId: "debt", reviewTargetId: "debt-zhongdeng", factVersionId: "fact-debt-zhongdeng-v1", unavailableReason: "中登登记清单尚待精确定位" },
      ],
      primaryTarget: { evidenceRef: "evidence-debt-zhongdeng", dimensionId: "debt", reviewTargetId: "debt-zhongdeng", factVersionId: "fact-debt-zhongdeng-v1", unavailableReason: "中登登记清单尚待精确定位" },
      responsibleParty: "joint",
      nextAction: "业务核对登记清单，风控统一偿债口径",
      isSimulated: true,
    },
    {
      id: "risk-anomaly-cashflow",
      title: "异常流水待核",
      detail: "7 笔演示异常记录缺少准确逐笔定位范围。",
      level: "confirm",
      evidenceTargets: [{ evidenceRef: "evidence-cashflow-anomalies", dimensionId: "cashflow", reviewTargetId: "cashflow-anomalies", factVersionId: null, unavailableReason: "异常流水逐笔范围尚待定位" }],
      primaryTarget: { evidenceRef: "evidence-cashflow-anomalies", dimensionId: "cashflow", reviewTargetId: "cashflow-anomalies", factVersionId: null, unavailableReason: "异常流水逐笔范围尚待定位" },
      responsibleParty: "business",
      nextAction: "补齐 7 笔异常流水的逐笔定位范围",
      isSimulated: true,
    },
  ],
  pendingHumanDeterminations: [
    {
      id: "risk-pending-charter",
      title: "章程版本认定",
      detail: "章程签署页和当前有效版本待人工核验。",
      level: "confirm",
      evidenceTargets: [{ evidenceRef: "evidence-compliance-charter", dimensionId: "compliance", reviewTargetId: "graph-attachment-attachment-charter", factVersionId: "fact-charter-v2", unavailableReason: "章程签署页尚待定位" }],
      primaryTarget: { evidenceRef: "evidence-compliance-charter", dimensionId: "compliance", reviewTargetId: "graph-attachment-attachment-charter", factVersionId: "fact-charter-v2", unavailableReason: "章程签署页尚待定位" },
      responsibleParty: "joint",
      nextAction: "补充签署页后由风控完成人工认定",
      isSimulated: true,
    },
    {
      id: "risk-pending-personal-litigation",
      title: "个人涉诉范围待核",
      detail: "关联自然人涉诉清单为独立待核事项，不属于 H-03 证据要求。",
      level: "confirm",
      evidenceTargets: [{ evidenceRef: "evidence-compliance-personal-litigation", dimensionId: "compliance", reviewTargetId: "graph-attachment-attachment-wang-litigation", factVersionId: "fact-personal-litigation-v1", unavailableReason: "个人涉诉清单当前不可核验" }],
      primaryTarget: { evidenceRef: "evidence-compliance-personal-litigation", dimensionId: "compliance", reviewTargetId: "graph-attachment-attachment-wang-litigation", factVersionId: "fact-personal-litigation-v1", unavailableReason: "个人涉诉清单当前不可核验" },
      responsibleParty: "joint",
      nextAction: "业务补充清单，风控独立核验涉诉范围",
      isSimulated: true,
    },
  ],
  isSimulated: true,
};

export const mockDeterminations: RiskDetermination[] = [
  {
    id: "determination-compliance-v2",
    dimensionId: "compliance",
    score: 82,
    scoreGrade: scoreToGrade(82),
    decisionGrade: "B",
    confidence: 76,
    conclusion: "营业执照与外部工商演示值基本一致；章程和涉诉范围仍需人工复核。",
    evidenceRefs: ["evidence-compliance-license", "evidence-compliance-charter", "evidence-compliance-subject-litigation", "evidence-compliance-personal-litigation"],
    hardConstraintResults: mockHardConstraints,
    softRecommendations: [{
      id: "soft-compliance-01",
      dimensionId: "compliance",
      title: "补充章程与涉诉清单",
      recommendation: "建议补充当前有效章程签署页、主体涉诉和个人涉诉完整清单。",
      confidence: 64,
      evidenceRefs: ["evidence-compliance-charter", "evidence-compliance-subject-litigation", "evidence-compliance-personal-litigation"],
      advisoryOnly: true,
      isSimulated: true,
    }],
    isSimulated: true,
  },
];

type ReviewEventSeed = Omit<CommonReviewEvent, "evidenceTargets" | "reviewTargetId" | "factVersionIds" | "evidenceRefs"> & {
  evidenceTargets: ReviewEvidenceTarget[];
};

function mappedReviewEvent({ evidenceTargets, ...event }: ReviewEventSeed): MappedCommonReviewEvent {
  return attachReviewEvidenceTargets({ ...event, reviewTargetId: null, factVersionIds: [], evidenceRefs: [] }, evidenceTargets);
}

const h03EvidenceTargets = mockHardConstraints[0].evidenceTargets;
const h03RuleRef = `${mockHardConstraints[0].ruleId}@${mockHardConstraints[0].ruleVersion}`;
const h03Context = `适用范围：${mockHardConstraints[0].scope}；证据要求：${mockHardConstraints[0].evidenceRequirement}`;

export const mockReviewEvents: MappedCommonReviewEvent[] = [
  mappedReviewEvent({ id: "event-09-debt-evidence", projectId: MOCK_PROJECT_ID, sequence: 9, threadId: "thread-debt-cross-check", replyToEventId: null, issueStatus: "open", eventType: "issue_opened", actor: "system", actorLabel: "材料识别层", dimensionId: "debt", title: "债务口径 · 三份材料逐项核对", summary: "征信、借款与中登登记分别绑定独立事实和审查锚点；中登仍为待定位，不以其他材料近似替代。", evidenceTargets: mockGlobalRiskSummary.keyAnomalies.find((item) => item.id === "risk-anomaly-debt-registration")!.evidenceTargets, ruleRefs: [], createdAt: "2026-08-08T10:36:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-08-personal-litigation", projectId: MOCK_PROJECT_ID, sequence: 8, threadId: "thread-personal-litigation", replyToEventId: null, issueStatus: "open", eventType: "issue_opened", actor: "system", actorLabel: "材料识别层", dimensionId: "compliance", title: "独立待核 · 个人涉诉范围", summary: "个人涉诉清单单独进入人工核验，不属于 H-03 的章程与中登证据要求。", evidenceTargets: [{ evidenceRef: "evidence-compliance-personal-litigation", dimensionId: "compliance", reviewTargetId: "fact-personal-litigation-v1", factVersionId: "fact-personal-litigation-v1", unavailableReason: "个人涉诉清单当前不可核验" }], ruleRefs: [], createdAt: "2026-08-08T10:34:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-07", projectId: MOCK_PROJECT_ID, sequence: 7, threadId: "thread-compliance-h03", replyToEventId: "event-06", issueStatus: "pending_gate", eventType: "risk_answer_submitted", actor: "risk", actorLabel: "风控 AI 辅助", dimensionId: "compliance", title: "风控意见 · H-03 保持人工 Gate", summary: `${h03Context}；两份定位均未完成复核，材料缺失只降低置信并保留人工 Gate，不自动拒绝。`, evidenceTargets: h03EvidenceTargets, ruleRefs: [h03RuleRef], createdAt: "2026-08-08T10:32:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-06", projectId: MOCK_PROJECT_ID, sequence: 6, threadId: "thread-compliance-h03", replyToEventId: "event-05", issueStatus: "pending_gate", eventType: "policy_result_recorded", actor: "system", actorLabel: "制度规则层", dimensionId: "compliance", title: "制度复算 · H-03 仍需人工复核", summary: `${h03Context}；章程签署页与中登登记清单仍未完成准确定位，Gate 保持开启。`, evidenceTargets: h03EvidenceTargets, ruleRefs: [h03RuleRef], createdAt: "2026-08-08T10:30:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-05", projectId: MOCK_PROJECT_ID, sequence: 5, threadId: "thread-compliance-h03", replyToEventId: "event-04", issueStatus: "answered", eventType: "business_answer_submitted", actor: "business", actorLabel: "业务 AI 辅助", dimensionId: "compliance", title: "业务回答 · H-03 两项证据仍在补件", summary: `${h03Context}；已确认拟采用 2026 年修订版章程，中登登记清单仍在补件，暂不申请关闭 Gate。`, evidenceTargets: h03EvidenceTargets, ruleRefs: [h03RuleRef], createdAt: "2026-08-08T10:28:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-04", projectId: MOCK_PROJECT_ID, sequence: 4, threadId: "thread-compliance-h03", replyToEventId: "event-03", issueStatus: "pending_gate", eventType: "policy_result_recorded", actor: "system", actorLabel: "制度规则层", dimensionId: "compliance", title: "制度命中 · H-03 人工复核", summary: `${h03Context}；当前两份材料均需可复核定位后再由人工认定。`, evidenceTargets: h03EvidenceTargets, ruleRefs: [h03RuleRef], createdAt: "2026-08-08T10:25:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-03", projectId: MOCK_PROJECT_ID, sequence: 3, threadId: "thread-compliance-h03", replyToEventId: "event-02", issueStatus: "open", eventType: "business_correction_submitted", actor: "business", actorLabel: "业务方", dimensionId: "compliance", title: "业务补件 · H-03 章程与中登", summary: `${h03Context}；章程版本拟修正为 2026 年修订版，中登登记清单仍待补齐定位。`, evidenceTargets: h03EvidenceTargets, ruleRefs: [h03RuleRef], createdAt: "2026-08-08T10:20:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-02", projectId: MOCK_PROJECT_ID, sequence: 2, threadId: "thread-compliance-h03", replyToEventId: "event-01", issueStatus: "open", eventType: "risk_question_submitted", actor: "risk", actorLabel: "风控 AI 辅助", dimensionId: "compliance", title: "风控追问 · H-03 章程与中登", summary: `${h03Context}；请分别补充当前有效章程签署页和中登登记清单的准确范围。`, evidenceTargets: h03EvidenceTargets, ruleRefs: [h03RuleRef], createdAt: "2026-08-08T10:15:00+09:00", immutable: true, isSimulated: true }),
  mappedReviewEvent({ id: "event-01", projectId: MOCK_PROJECT_ID, sequence: 1, threadId: "thread-compliance-h03", replyToEventId: null, issueStatus: "open", eventType: "fact_version_created", actor: "system", actorLabel: "材料识别层", dimensionId: "compliance", title: "材料识别 · 章程版本待核", summary: "识别到章程修订日期，但未找到可准确定位的签署页；该状态仅降低置信。", evidenceTargets: [{ evidenceRef: "evidence-compliance-charter", dimensionId: "compliance", reviewTargetId: "fact-charter-v2", factVersionId: "fact-charter-v2", unavailableReason: "章程签署页尚待定位" }], ruleRefs: [], createdAt: "2026-08-08T10:10:00+09:00", immutable: true, isSimulated: true }),
];

export const mockWorkbenchProject: WorkbenchProject = {
  project: {
    id: MOCK_PROJECT_ID,
    name: "华东精密设备融资",
    materialCount: mockMaterials.length,
    collaborationIssueCount: 4,
    dataStatus: "simulated",
    disclaimer: "本页全部业务数据、材料内容、规则结果与风险结论均为演示模拟，不代表真实客户或真实审批意见。",
    isSimulated: true,
  },
  riskSummary: mockGlobalRiskSummary,
  dimensions: mockDimensions,
  dimensionDetails: mockDimensionDetails,
  materials: mockMaterials,
  evidence: mockEvidence,
  facts: mockFacts,
  complianceGraph: mockComplianceGraph,
  financedEquipment: mockFinancedEquipment,
  operatingEquipment: mockOperatingEquipment,
  productionStages: mockProductionStages,
  productionEnergy: mockProductionEnergy,
  referenceImages: mockReferenceImages,
  onsiteAssets: mockOnsiteAssets,
  corrections: [],
  determinations: mockDeterminations,
  reviewEvents: mockReviewEvents,
  layout: {
    navigationWidth: 212,
    materialWidth: 520,
    collaborationHeight: 175,
    navigationCollapsed: false,
    middleCollapsed: false,
    materialCollapsed: false,
    collaborationCollapsed: false,
    businessCollapsed: false,
    policyCollapsed: false,
    riskCollapsed: false,
    activeDimensionId: "compliance",
  },
};
