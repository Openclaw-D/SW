import assert from "node:assert/strict";
import test from "node:test";
import { mockFinancedEquipment } from "../src/mock/p2Content.ts";
import {
  analyzeRepaymentSchedule,
  createTimeSeriesRequest,
  defaultTimeSeriesRange,
  deriveTransactionPriceVerification,
  deriveTransactionTopParameters,
  repaymentChartLabelPeriods,
  resolveTimeSeriesRange,
} from "../src/lib/workbenchLogic.ts";

function schedule(principals, { rentDelta = 0, evidence = true } = {}) {
  return {
    status: "available",
    termMonths: principals.length,
    amountUnit: "元",
    points: principals.map((principal, index) => ({
      id: `period-${index + 1}`,
      period: index + 1,
      principal,
      interest: 10,
      rent: principal + 10 + rentDelta,
      evidenceRefs: evidence ? [`evidence-${index + 1}`] : [],
      isSimulated: true,
    })),
    firstPaymentEvidenceRefs: evidence ? ["first"] : [],
    firstTwelveEvidenceRefs: evidence ? ["first-twelve"] : [],
    totalRentEvidenceRefs: evidence ? ["total"] : [],
    termEvidenceRefs: evidence ? ["term"] : [],
    message: "test schedule",
    sourceLabel: "test",
    isSimulated: true,
  };
}

test("Fix2 classifies complete front-loaded, balanced and back-loaded plans with the backend 8pp boundary", () => {
  assert.equal(analyzeRepaymentSchedule(schedule([19, 19, 16, 16, 15, 15])).structure, "front_loaded");
  assert.equal(analyzeRepaymentSchedule(schedule([18.95, 18.95, 16.05, 16.05, 15, 15])).structure, "balanced");
  assert.equal(analyzeRepaymentSchedule(schedule([15, 15, 16, 16, 19, 19])).structure, "back_loaded");
  assert.deepEqual(analyzeRepaymentSchedule(schedule([20, 20, 15, 15, 10, 10])).status === "available" ? { value: analyzeRepaymentSchedule(schedule([20, 20, 15, 15, 10, 10])).displayValue, risk: analyzeRepaymentSchedule(schedule([20, 20, 15, 15, 10, 10])).riskLabel } : null, { value: "前高后低", risk: "低风险" });
  assert.deepEqual(analyzeRepaymentSchedule(schedule([15, 15, 15, 15, 15, 15])).status === "available" ? { value: analyzeRepaymentSchedule(schedule([15, 15, 15, 15, 15, 15])).displayValue, risk: analyzeRepaymentSchedule(schedule([15, 15, 15, 15, 15, 15])).riskLabel } : null, { value: "均衡", risk: "中风险" });
  assert.deepEqual(analyzeRepaymentSchedule(schedule([10, 10, 15, 15, 20, 20])).status === "available" ? { value: analyzeRepaymentSchedule(schedule([10, 10, 15, 15, 20, 20])).displayValue, risk: analyzeRepaymentSchedule(schedule([10, 10, 15, 15, 20, 20])).riskLabel } : null, { value: "前低后高", risk: "高风险" });
});

test("Fix2 validates cents tolerance, total principal, continuous periods and evidence honesty", () => {
  assert.equal(analyzeRepaymentSchedule(schedule([100, 100, 100], { rentDelta: .009 })).status, "available");
  assert.equal(analyzeRepaymentSchedule(schedule([100, 100, 100], { rentDelta: .011 })).status, "invalid");
  const missingPeriod = schedule([100, 100, 100]);
  missingPeriod.points[1].period = 3;
  assert.equal(analyzeRepaymentSchedule(missingPeriod).status, "invalid");
  assert.equal(analyzeRepaymentSchedule(schedule([0, 0, 0])).status, "invalid");
  const noEvidence = analyzeRepaymentSchedule(schedule([100, 100, 100], { evidence: false }));
  assert.equal(noEvidence.status, "available");
  assert.deepEqual(noEvidence.evidenceRefs, []);
});

test("Fix2 derives the seven transaction top parameters in the frozen order from the live schedule", () => {
  const ledger = { ...mockFinancedEquipment, termMonths: 6, repaymentSchedule: schedule([20, 20, 15, 15, 10, 10]) };
  const parameters = deriveTransactionTopParameters(ledger, ledger.lines[0]);
  assert.deepEqual(parameters.map((item) => item.label), ["供应商评级", "品牌评级", "项目金额", "融资成数", "融资金额", "期限", "还款结构风险"]);
  assert.equal(parameters.some((item) => item.label === "报价偏离"), false);
  assert.equal(parameters.at(-1).value, "前高后低");
  assert.equal(parameters.at(-1).status, "低风险");
  assert.match(parameters.at(-1).context, /前半期本金回收/);
  assert.ok(parameters.at(-1).evidenceRefs.includes("evidence-1"));
});

test("Fix2 keeps quotation deviation inside the lower equipment price verification group", () => {
  const items = deriveTransactionPriceVerification(mockFinancedEquipment.lines[0]);
  assert.deepEqual(items.map((item) => item.label), ["合同价", "供应商报价", "可比价", "报价偏离"]);
  assert.equal(items.at(-1).evidenceRefs[0], mockFinancedEquipment.lines[0].priceBenchmark.evidenceRefs[0]);
});

test("Fix2 renders a valid 60-period plan with a last-period tick instead of an invalid schedule", () => {
  const sixty = analyzeRepaymentSchedule(schedule(Array.from({ length: 60 }, () => 100)));
  assert.equal(sixty.status, "available");
  assert.equal(sixty.firstHalfPrincipalRecoveryRatio, .5);
  assert.deepEqual(repaymentChartLabelPeriods(60), [1, 10, 20, 30, 40, 50, 60]);
});

test("Fix2 uses the frozen local-date range for controls and the first gateway request without replacing valid user input", () => {
  assert.deepEqual(defaultTimeSeriesRange(), { startDate: "2025-08-01", endDate: "2026-08-01" });
  assert.deepEqual(resolveTimeSeriesRange(), { startDate: "2025-08-01", endDate: "2026-08-01" });
  assert.deepEqual(resolveTimeSeriesRange({ startDate: "2025-09-01", endDate: "2025-10-01" }), { startDate: "2025-09-01", endDate: "2025-10-01" });
  assert.deepEqual(createTimeSeriesRequest({ projectId: "project-1", dimensionId: "revenue", metricIds: ["revenue"], grain: "month", ...defaultTimeSeriesRange() }), {
    projectId: "project-1", dimensionId: "revenue", metricIds: ["revenue"], grain: "month", startDate: "2025-08-01", endDate: "2026-08-01", timezone: "Asia/Shanghai",
  });
});
