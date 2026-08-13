import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { mockFinancedEquipment } from "../src/mock/p2Content.ts";
import { mockGlobalRiskSummary } from "../src/mock/mockCase.ts";
import {
  catalogProjectIdentity,
  displayBusinessName,
  displayBusinessText,
  deriveFinancingBreakdown,
  deriveTransactionPriceVerification,
  deriveTransactionTopParameters,
  formatFinancingRatio,
  materialTabPresentation,
  riskItemCount,
} from "../src/lib/workbenchLogic.ts";

test("Fix3 keeps the catalog project number visible while retaining the internal request id", () => {
  const identity = catalogProjectIdentity([{ projectId: "gen-electronics-42", projectNo: "SYN-06-024-14AD" }], "gen-electronics-42");
  assert.deepEqual(identity, { requestProjectId: "gen-electronics-42", projectNo: "SYN-06-024-14AD" });
  assert.equal(catalogProjectIdentity([{ projectId: "gen-electronics-42", projectNo: "SYN-06-024-14AD" }], "missing"), null);
});

test("Fix3 removes generated-system prefixes from visible entity names without changing source data", () => {
  assert.equal(displayBusinessName("系统生成·电子庚申·柔性电子装联线设备融资"), "电子庚申·柔性电子装联线设备融资");
  assert.equal(displayBusinessName("规则生成品牌 E2"), "品牌 E2");
  assert.equal(displayBusinessName("系统生成"), "待核验主体");
  assert.equal(displayBusinessName("华东电子有限公司"), "华东电子有限公司");
  assert.equal(displayBusinessText("完整脱敏的确定性业务规则生成数据"), "完整脱敏的确定性业务模拟数据");
});

test("Fix3 separates repayment direction, risk status and recovery explanation in the frozen seven-item order", () => {
  const parameters = deriveTransactionTopParameters(mockFinancedEquipment, mockFinancedEquipment.lines[0]);
  assert.deepEqual(parameters.map((item) => item.label), ["供应商评级", "品牌评级", "项目金额", "融资成数", "融资金额", "期限", "还款结构风险"]);
  const repayment = parameters.at(-1);
  assert.ok(repayment);
  assert.equal(["前高后低", "均衡", "前低后高"].includes(repayment.value), true);
  assert.equal(["低风险", "中风险", "高风险"].includes(repayment.status), true);
  assert.match(repayment.context, /^前半期本金回收 \d+\.\d%$/);
  assert.equal(repayment.value.includes("（"), false);
});

test("Fix3 uses one one-decimal financing ratio in the top parameter and financing composition", () => {
  const ledger = { ...mockFinancedEquipment, downPaymentAmount: 48_550 };
  const breakdown = deriveFinancingBreakdown(2_740_000, ledger.downPaymentAmount);
  assert.equal(breakdown.status, "available");
  if (breakdown.status !== "available") return;
  const topRatio = deriveTransactionTopParameters(ledger, ledger.lines[0]).find((item) => item.label === "融资成数");
  assert.equal(topRatio?.value, formatFinancingRatio(breakdown.financedPercent));
  assert.equal(formatFinancingRatio(98.06), "98.1%");
});

test("Fix3 keeps supplier quotation honest when only source evidence exists", () => {
  const supplierQuote = deriveTransactionPriceVerification(mockFinancedEquipment.lines[0]).find((item) => item.label === "供应商报价");
  assert.deepEqual(supplierQuote && { value: supplierQuote.value, context: supplierQuote.context, evidenceRefs: supplierQuote.evidenceRefs, sourceLabel: supplierQuote.sourceLabel }, {
    value: "待结构化",
    context: "已关联报价材料",
    evidenceRefs: mockFinancedEquipment.lines[0].supplierQuoteEvidenceRefs,
    sourceLabel: mockFinancedEquipment.lines[0].supplierQuoteSource,
  });
});

test("Fix3 derives risk navigation counts and short material labels without changing identifiers", () => {
  assert.equal(riskItemCount({ ...mockGlobalRiskSummary, hardConstraintResults: [], keyAnomalies: [], pendingHumanDeterminations: [] }), 0);
  assert.equal(riskItemCount(mockGlobalRiskSummary), 5);
  assert.deepEqual(materialTabPresentation({ kind: "excel", fileName: "SYN-06-024-14AD-业务数据.xlsx" }), { label: "业务数据", extension: ".XLSX" });
  assert.deepEqual(materialTabPresentation({ kind: "image", fileName: "设备原图.png" }), { label: "设备图片", extension: ".PNG" });
  assert.deepEqual(materialTabPresentation({ kind: "pdf", fileName: "主体核验.pdf" }), { label: "主体核验", extension: ".PDF" });
});

test("Fix3-Corr1 gives one equipment a full-width four-part summary while multiple equipment stays a grid", async () => {
  const [panel, styles] = await Promise.all([
    readFile(new URL("../src/components/FinancedEquipmentPanel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/styles/app.css", import.meta.url), "utf8"),
  ]);
  assert.match(panel, /calculated\.lines\.length === 1 \? "is-singleton" : "is-multiple"/);
  for (const label of ["equipment-card-identity", "equipment-card-parameters", "equipment-card-quantity", "equipment-card-amount", "关键参数", "合同金额"]) assert.match(panel, new RegExp(label));
  assert.match(styles, /\.financed-equipment-cards\.is-singleton \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(styles, /\.financed-equipment-cards\.is-multiple \{ grid-template-columns: repeat\(auto-fit, minmax\(260px, 1fr\)\); \}/);
});
