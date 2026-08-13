import type {
  DimensionTimeObservation,
  DimensionTimeSeries,
  EvidenceReference,
  ExcelMaterial,
} from "../contracts/workbench";
import { calculateFinancedEquipmentLedger, deriveFinancingBreakdown } from "../lib/workbenchLogic.ts";
import { mockFinancedEquipment } from "./p2Content.ts";

const sourceLabel = "统一脱敏模拟业务数据包；人工构造且口径确定，不代表真实客户、真实模型输出或统计样本";
const materialId = "material-review-index";
const materialVersionId = "material-review-index-v1";

function datesBetween(start: string, end: string) {
  const dates: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  const final = new Date(`${end}T00:00:00Z`);
  while (cursor <= final) {
    dates.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

const dates = datesBetween("2026-01-01", "2026-06-30");

const productionDaily = dates.map((date, index) => {
  const weekday = new Date(`${date}T00:00:00Z`).getUTCDay();
  const operatingFactor = weekday === 0 ? .42 : weekday === 6 ? .68 : 1;
  const staff = 116 + (Math.floor(index / 30) % 4) * 2 + (index % 11 === 0 ? 1 : 0);
  const electricity = Math.round((1_520 + (index % 9) * 46 + Math.floor(index / 31) * 38) * operatingFactor);
  const output = Math.round((820 + (index % 7) * 34 + Math.floor(index / 31) * 22) * operatingFactor);
  return {
    date,
    electricity,
    output,
    payroll: Math.round(staff * 0.032 * 100) / 100,
    staff,
    utilization: Math.round((68 + (index % 8) * 2.1 + Math.floor(index / 45)) * operatingFactor * 10) / 10,
  };
});

const revenueDaily = dates.map((date, index) => {
  const weekday = new Date(`${date}T00:00:00Z`).getUTCDay();
  const businessDay = weekday !== 0 && weekday !== 6;
  const order = businessDay ? 34 + (index % 6) * 4 + Math.floor(index / 45) * 3 : 0;
  const invoice = businessDay ? Math.max(0, order - 3 + (index % 4) * 2) : 0;
  const collection = businessDay ? Math.max(0, invoice - 4 + (index % 5) * 2) : 0;
  const income = businessDay ? Math.max(0, order - 2 + (index % 3)) : 0;
  return { date, order, invoice, collection, income };
});

const cashflowDaily = revenueDaily.map((row, index) => {
  const inflow = row.collection + (index % 15 === 0 ? 18 : 6);
  const outflow = row.income * .72 + 7 + (index % 9 === 0 ? 12 : 0);
  return {
    date: row.date,
    inflow: Math.round(inflow * 100) / 100,
    outflow: Math.round(outflow * 100) / 100,
    anomalyCount: index % 29 === 0 ? 1 : 0,
  };
});

const debtMonthly = Array.from({ length: 12 }, (_, index) => {
  const month = index + 1;
  const enterpriseBalance = 3_140 - index * 32;
  const personalBalance = 1_120 - index * 9;
  const due = [150, 130, 180, 115, 175, 155, 140, 190, 125, 165, 150, 185][index];
  const capacity = [240, 210, 250, 190, 230, 220, 200, 250, 180, 230, 210, 240][index];
  return {
    date: `2026-${String(month).padStart(2, "0")}-28`,
    enterpriseBalance,
    personalBalance,
    totalBalance: enterpriseBalance + personalBalance,
    due,
    capacity,
  };
});

const complianceVersions = [
  ["2026-01-05", "营业执照", "有效", "2036-01-04", "已定位", "脱敏模拟"],
  ["2026-01-08", "公司章程", "2025修订版", "2025-12-20", "待签署页复核", "脱敏模拟"],
  ["2026-01-12", "法定代表人身份证", "有效期内", "2034-09-18", "已定位", "脱敏模拟"],
  ["2026-02-02", "外部工商", "基本一致", "2026-02-02", "已定位", "脱敏模拟"],
  ["2026-02-06", "主体涉诉", "未见异常", "2026-02-06", "已定位", "脱敏模拟"],
  ["2026-02-06", "个人涉诉", "范围待确认", "2026-02-06", "人工复核", "脱敏模拟"],
] as const;

const calculatedLedger = calculateFinancedEquipmentLedger(mockFinancedEquipment);
const financing = deriveFinancingBreakdown(calculatedLedger.contractTotal, mockFinancedEquipment.downPaymentAmount);
const financedAmount = financing.status === "available" ? financing.financedAmount : 0;
const repaymentPrincipal = mockFinancedEquipment.repaymentSchedule.points.reduce((sum, point) => sum + point.principal, 0);
const repaymentInterest = mockFinancedEquipment.repaymentSchedule.points.reduce((sum, point) => sum + point.interest, 0);
const repaymentRent = mockFinancedEquipment.repaymentSchedule.points.reduce((sum, point) => sum + point.rent, 0);

export const mockP3BusinessDataset = {
  id: "p3-adjust-unified-sanitized-package-v1",
  sourceLabel,
  isSimulated: true as const,
  compliance: {
    subjects: { companies: 2, people: 3 },
    shareholdingPercent: [90, 10],
    licensesAndChecks: complianceVersions,
  },
  transaction: {
    equipmentLines: calculatedLedger.lines.length,
    equipmentQuantity: calculatedLedger.totalQuantity,
    contractTotal: calculatedLedger.contractTotal,
    downPayment: mockFinancedEquipment.downPaymentAmount,
    financedAmount,
    repaymentPrincipal,
    repaymentInterest,
    repaymentRent,
    termMonths: mockFinancedEquipment.repaymentSchedule.termMonths,
  },
  production: productionDaily,
  revenue: revenueDaily,
  debt: debtMonthly,
  cashflow: {
    daily: cashflowDaily,
    transactions: cashflowDaily.flatMap((row, index) => [
      { id: `flow-in-${row.date}`, date: row.date, direction: "in" as const, counterparty: ["制造客户A", "经销渠道B", "服务客户C"][index % 3], amount: row.inflow, anomaly: false },
      { id: `flow-out-${row.date}`, date: row.date, direction: "out" as const, counterparty: ["原料供应商A", "设备耗材商B", "物流能源商C"][index % 3], amount: row.outflow, anomaly: row.anomalyCount > 0 },
    ]),
  },
} as const;

const sheets: ExcelMaterial["sheets"] = [
  {
    name: "合规版本",
    columns: ["生效日期", "材料/核验", "结果", "有效或版本日期", "定位状态", "数据状态"],
    rows: complianceVersions.map((row) => [...row]),
  },
  {
    name: "交易守恒",
    columns: ["合同总额", "首付款", "融资额", "本金合计", "利息合计", "租金合计", "期数", "数据状态"],
    rows: [[calculatedLedger.contractTotal, mockFinancedEquipment.downPaymentAmount, financedAmount, repaymentPrincipal, repaymentInterest, repaymentRent, mockFinancedEquipment.repaymentSchedule.termMonths, "脱敏模拟；本金+利息=租金"]],
  },
  {
    name: "生产日数据",
    columns: ["日期", "用电量(kWh)", "完工产量(件)", "工资计提(万元)", "在岗人数(人)", "设备利用率(%)", "数据状态"],
    rows: productionDaily.map((row) => [row.date, row.electricity, row.output, row.payroll, row.staff, row.utilization, "脱敏模拟"]),
  },
  {
    name: "营收日数据",
    columns: ["日期", "合同订单(万元)", "发票(万元)", "回款流水(万元)", "确认收入(万元)", "数据状态"],
    rows: revenueDaily.map((row) => [row.date, row.order, row.invoice, row.collection, row.income, "脱敏模拟"]),
  },
  {
    name: "负债月数据",
    columns: ["日期", "企业负债(万元)", "个人负债(万元)", "总负债(万元)", "到期负债(万元)", "可偿还能力(万元)", "数据状态"],
    rows: debtMonthly.map((row) => [row.date, row.enterpriseBalance, row.personalBalance, row.totalBalance, row.due, row.capacity, "脱敏模拟；总负债由B+C派生"]),
  },
  {
    name: "流水日汇总",
    columns: ["日期", "流入(万元)", "流出(万元)", "净额(万元)", "异常笔数", "数据状态"],
    rows: cashflowDaily.map((row) => [row.date, row.inflow, row.outflow, Math.round((row.inflow - row.outflow) * 100) / 100, row.anomalyCount, "脱敏模拟；净额由B-C派生"]),
  },
  {
    name: "流水逐笔",
    columns: ["交易ID", "日期", "方向", "交易对手", "金额(万元)", "异常标记", "数据状态"],
    rows: mockP3BusinessDataset.cashflow.transactions.map((row) => [row.id, row.date, row.direction === "in" ? "流入" : "流出", row.counterparty, row.amount, row.anomaly ? "待复核" : "无", "脱敏模拟"]),
  },
];

export const mockP3Materials: ExcelMaterial[] = [{
  id: materialId,
  versionId: materialVersionId,
  kind: "excel",
  fileName: "六维完整脱敏数据包.xlsx",
  label: "六维完整脱敏业务数据包",
  mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  availability: "available",
  isSimulated: true,
  sourceLabel,
  sheets,
}];

function excelEvidence(id: string, label: string, sheet: string, range: string): EvidenceReference {
  return {
    id,
    label,
    locator: { kind: "excel", materialId, materialVersionId, sheet, range },
    locationStatus: "located",
    materialStatus: "confirmed",
  };
}

const p3Evidence: EvidenceReference[] = [
  excelEvidence("evidence-p3-compliance-versions", "合规材料版本矩阵", "合规版本", "A4:F9"),
  excelEvidence("evidence-p3-transaction-conservation", "交易融资与租金守恒", "交易守恒", "A4:H4"),
  excelEvidence("evidence-p3-revenue-summary", "营收日数据汇总输入", "营收日数据", `B4:E${revenueDaily.length + 3}`),
  {
    id: "evidence-p3-credit-guarantee-related",
    label: "征信担保关联说明",
    locator: { kind: "pdf", materialId: "material-credit", materialVersionId: "material-credit-v1", page: 7, bbox: { x: .12, y: .48, width: .74, height: .14 }, textAnchor: "关联担保说明" },
    locationStatus: "located",
    materialStatus: "review",
  },
  {
    id: "evidence-p3-factory-equipment-zone",
    label: "现场设备作业区",
    locator: { kind: "image", materialId: "material-factory", materialVersionId: "material-factory-v1", bbox: { x: .28, y: .34, width: .24, height: .22 } },
    locationStatus: "located",
    materialStatus: "confirmed",
  },
];

function timeObservations(
  dimensionId: "production" | "revenue" | "debt" | "cashflow",
  sheet: string,
  rows: Array<Record<string, string | number>>,
  definitions: Array<{ metricId: string; column: string; value: (row: Record<string, string | number>) => number; evidenceRange?: (rowNumber: number) => string }>,
) {
  return rows.flatMap((row, rowIndex) => definitions.map((definition): DimensionTimeObservation => {
    const date = String(row.date);
    const evidenceId = `evidence-p3-${dimensionId}-${date}-${definition.metricId}`;
    const rowNumber = rowIndex + 4;
    p3Evidence.push(excelEvidence(evidenceId, `${date} ${definition.metricId}`, sheet, definition.evidenceRange?.(rowNumber) ?? `${definition.column}${rowNumber}:${definition.column}${rowNumber}`));
    return {
      id: `${dimensionId}-${date}-${definition.metricId}`,
      date,
      metricId: definition.metricId,
      value: definition.value(row),
      evidenceRefs: [evidenceId],
      isSimulated: true,
    };
  }));
}

const productionObservations = timeObservations("production", "生产日数据", productionDaily, [
  { metricId: "electricity", column: "B", value: (row) => Number(row.electricity) },
  { metricId: "output", column: "C", value: (row) => Number(row.output) },
  { metricId: "payroll", column: "D", value: (row) => Number(row.payroll) },
  { metricId: "staff", column: "E", value: (row) => Number(row.staff) },
  { metricId: "utilization", column: "F", value: (row) => Number(row.utilization) },
]);

const revenueObservations = timeObservations("revenue", "营收日数据", revenueDaily, [
  { metricId: "orders", column: "B", value: (row) => Number(row.order) },
  { metricId: "invoices", column: "C", value: (row) => Number(row.invoice) },
  { metricId: "collections", column: "D", value: (row) => Number(row.collection) },
  { metricId: "income", column: "E", value: (row) => Number(row.income) },
]);

const debtObservations = timeObservations("debt", "负债月数据", debtMonthly, [
  { metricId: "enterprise", column: "B", value: (row) => Number(row.enterpriseBalance) },
  { metricId: "personal", column: "C", value: (row) => Number(row.personalBalance) },
  { metricId: "due", column: "E", value: (row) => Number(row.due) },
  { metricId: "capacity", column: "F", value: (row) => Number(row.capacity) },
]);

const cashflowObservations = timeObservations("cashflow", "流水日汇总", cashflowDaily, [
  { metricId: "inflow", column: "B", value: (row) => Number(row.inflow) },
  { metricId: "outflow", column: "C", value: (row) => Number(row.outflow) },
  { metricId: "net", column: "D", value: (row) => Number(row.inflow) - Number(row.outflow), evidenceRange: (rowNumber) => `B${rowNumber}:C${rowNumber}` },
]);

export const mockDimensionTimeSeries: DimensionTimeSeries[] = [
  {
    dimensionId: "production",
    supportedGrains: ["day", "week", "month", "year"],
    metrics: [
      { id: "electricity", label: "用电量", unit: "kWh", aggregation: "sum" },
      { id: "output", label: "完工产量", unit: "件", aggregation: "sum" },
      { id: "payroll", label: "工资总额", unit: "万元", aggregation: "sum" },
      { id: "staff", label: "在岗人数", unit: "人", aggregation: "last" },
      { id: "utilization", label: "设备利用率", unit: "%", aggregation: "average" },
    ],
    observations: productionObservations,
    sourceLabel,
    isSimulated: true,
  },
  {
    dimensionId: "revenue",
    supportedGrains: ["day", "week", "month", "year"],
    metrics: [
      { id: "orders", label: "合同订单", unit: "万元", aggregation: "sum" },
      { id: "invoices", label: "发票", unit: "万元", aggregation: "sum" },
      { id: "collections", label: "回款流水", unit: "万元", aggregation: "sum" },
      { id: "income", label: "确认收入", unit: "万元", aggregation: "sum" },
    ],
    observations: revenueObservations,
    sourceLabel,
    isSimulated: true,
  },
  {
    dimensionId: "debt",
    supportedGrains: ["month", "year"],
    metrics: [
      { id: "enterprise", label: "企业负债", unit: "万元", aggregation: "last" },
      { id: "personal", label: "个人负债", unit: "万元", aggregation: "last" },
      { id: "due", label: "到期负债", unit: "万元", aggregation: "sum" },
      { id: "capacity", label: "可偿还能力", unit: "万元", aggregation: "last" },
    ],
    observations: debtObservations,
    sourceLabel,
    isSimulated: true,
  },
  {
    dimensionId: "cashflow",
    supportedGrains: ["day", "week", "month", "year"],
    metrics: [
      { id: "inflow", label: "流入", unit: "万元", aggregation: "sum" },
      { id: "outflow", label: "流出", unit: "万元", aggregation: "sum" },
      { id: "net", label: "净额", unit: "万元", aggregation: "sum" },
    ],
    observations: cashflowObservations,
    sourceLabel,
    isSimulated: true,
  },
];

export const mockP3Evidence = p3Evidence;

function nearlyEqual(left: number, right: number) {
  return Math.abs(left - right) < .001;
}

export function validateP3BusinessConservation() {
  const revenueTotals = revenueDaily.reduce((totals, row) => ({
    orders: totals.orders + row.order,
    invoices: totals.invoices + row.invoice,
    collections: totals.collections + row.collection,
    income: totals.income + row.income,
  }), { orders: 0, invoices: 0, collections: 0, income: 0 });
  const revenueObservationTotals = Object.fromEntries(["orders", "invoices", "collections", "income"].map((metricId) => [metricId, revenueObservations.filter((item) => item.metricId === metricId).reduce((sum, item) => sum + item.value, 0)]));
  const transactionTotals = mockP3BusinessDataset.cashflow.transactions.reduce((totals, item) => {
    totals[item.direction] += item.amount;
    return totals;
  }, { in: 0, out: 0 });
  const dailyTotals = cashflowDaily.reduce((totals, row) => ({ in: totals.in + row.inflow, out: totals.out + row.outflow }), { in: 0, out: 0 });
  return {
    financing: calculatedLedger.contractTotal === mockFinancedEquipment.downPaymentAmount + financedAmount,
    rent: repaymentPrincipal === financedAmount && repaymentRent === repaymentPrincipal + repaymentInterest,
    revenue: Object.entries(revenueTotals).every(([metricId, total]) => nearlyEqual(total, Number(revenueObservationTotals[metricId]))),
    debt: debtMonthly.every((row) => row.totalBalance === row.enterpriseBalance + row.personalBalance),
    cashflow: nearlyEqual(transactionTotals.in, dailyTotals.in) && nearlyEqual(transactionTotals.out, dailyTotals.out),
    exposure: 419 + 121 === 540 && [113, 190, 124, 113].reduce((sum, value) => sum + value, 0) === 540,
  };
}
