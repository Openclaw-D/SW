import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { mockEvidence, mockMaterials } from "../src/mock/mockCase.ts";
import { mockFinancedEquipment, mockTransactionRepaymentSchedule } from "../src/mock/p2Content.ts";

const root = new URL("../", import.meta.url);

async function readSources() {
  return Promise.all([
    readFile(new URL("src/contracts/workbench.ts", root), "utf8"),
    readFile(new URL("src/mock/p2Content.ts", root), "utf8"),
    readFile(new URL("src/mock/mockCase.ts", root), "utf8"),
    readFile(new URL("src/components/TransactionWorkspace.tsx", root), "utf8"),
    readFile(new URL("src/components/FinancedEquipmentPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/TransactionCoreCharts.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
}

test("P3-F6 extends the existing equipment ledger with optional ratings and a reusable repayment schedule", async () => {
  const [contracts] = await readSources();
  assert.match(contracts, /export type TransactionRating = "A级" \| "B级" \| "C级" \| "D级" \| "E级"/);
  assert.match(contracts, /export interface TransactionRepaymentPoint[\s\S]*period: number;[\s\S]*principal: number;[\s\S]*interest: number;[\s\S]*rent: number;[\s\S]*evidenceRefs: string\[\]/);
  assert.match(contracts, /export interface TransactionRepaymentSchedule[\s\S]*status: AvailabilityState;[\s\S]*points: TransactionRepaymentPoint\[\]/);
  assert.match(contracts, /export interface FinancedEquipmentLine[\s\S]*supplierRating\?: TransactionRating;[\s\S]*brandRating\?: TransactionRating/);
  assert.match(contracts, /export interface FinancedEquipmentLedger[\s\S]*projectAmountEvidenceRefs: string\[\];[\s\S]*financingRatioEvidenceRefs: string\[\];[\s\S]*repaymentSchedule: TransactionRepaymentSchedule/);
  assert.doesNotMatch(contracts, /interface (?:WorkbenchProject|ReviewCanvas)[\s\S]*TransactionRepayment/);
});

test("P3-F6 keeps ratings per equipment and derives the frozen project financing facts", () => {
  assert.deepEqual(mockFinancedEquipment.lines.map((line) => [line.id, line.supplierRating, line.brandRating]), [
    ["financed-equipment-1", "A级", "A级"],
    ["financed-equipment-2", "B级", "B级"],
    ["financed-equipment-3", "B级", "B级"],
  ]);
  assert.equal(mockFinancedEquipment.lines.every((line) => line.supplierRatingEvidenceRefs?.length === 1 && line.brandRatingEvidenceRefs?.length === 1), true);
  const projectAmount = mockFinancedEquipment.lines.reduce((sum, line) => sum + line.quantity * line.contractUnitPrice, 0);
  const financedAmount = projectAmount - mockFinancedEquipment.downPaymentAmount;
  assert.equal(projectAmount, 2_740_000);
  assert.equal(mockFinancedEquipment.downPaymentAmount, 767_200);
  assert.equal(financedAmount, 1_972_800);
  assert.equal(financedAmount / projectAmount * 100, 72);
});

test("P3-F6 keeps all 36 rent periods in exact yuan amounts with deterministic totals", () => {
  const schedule = mockTransactionRepaymentSchedule;
  assert.equal(schedule, mockFinancedEquipment.repaymentSchedule);
  assert.equal(schedule.status, "available");
  assert.equal(schedule.termMonths, 36);
  assert.equal(schedule.amountUnit, "元");
  assert.equal(schedule.points.length, 36);
  schedule.points.forEach((point, index) => {
    assert.equal(point.id, `transaction-rent-period-${String(index + 1).padStart(2, "0")}`);
    assert.equal(point.period, index + 1);
    assert.equal(point.principal, 54_800);
    assert.equal(point.interest, 6_400 - index * 170);
    assert.equal(point.rent, point.principal + point.interest);
    assert.equal(point.isSimulated, true);
  });
  assert.equal(schedule.points[0].rent, 61_200);
  assert.equal(schedule.points.at(-1).interest, 450);
  assert.equal(schedule.points.reduce((sum, point) => sum + point.principal, 0), 1_972_800);
  assert.equal(schedule.points.reduce((sum, point) => sum + point.interest, 0), 123_300);
  assert.equal(schedule.points.reduce((sum, point) => sum + point.rent, 0), 2_096_100);
  assert.equal(schedule.points.slice(0, 12).reduce((sum, point) => sum + point.rent, 0), 723_180);
});

test("P3-F6 stores ratings, financing and rent rows in the existing equipment workbook", () => {
  assert.equal(mockMaterials.length, 11);
  const material = mockMaterials.find((item) => item.id === "material-financed-equipment");
  assert.equal(material?.kind, "excel");
  const ratings = material.sheets.find((sheet) => sheet.name === "设备评级");
  const financing = material.sheets.find((sheet) => sheet.name === "融资方案");
  const repayment = material.sheets.find((sheet) => sheet.name === "租金计划");
  assert.ok(ratings);
  assert.ok(financing);
  assert.ok(repayment);
  assert.deepEqual(ratings.columns, ["设备ID", "设备/型号", "供应商", "供应商评级", "品牌", "品牌评级", "评级口径", "数据状态"]);
  assert.deepEqual(ratings.rows.map((row) => [row[0], row[3], row[5], row[7]]), [
    ["financed-equipment-1", "A级", "A级", "脱敏模拟"],
    ["financed-equipment-2", "B级", "B级", "脱敏模拟"],
    ["financed-equipment-3", "B级", "B级", "脱敏模拟"],
  ]);
  assert.deepEqual(financing.columns, ["交易结构", "出租人", "期限(月)", "合同总额(元)", "首付款(元)", "融资额(元)", "融资成数(%)", "口径", "数据状态"]);
  assert.deepEqual(financing.rows[0].slice(2, 7), [36, 2_740_000, 767_200, 1_972_800, 72]);
  assert.deepEqual(repayment.columns, ["期次", "月租金(元)", "本金(元)", "利息(元)", "占计划总额(%)", "数据状态"]);
  assert.equal(repayment.rows.length, 36);
  repayment.rows.forEach((row, index) => assert.deepEqual(row.slice(0, 4), [
    mockTransactionRepaymentSchedule.points[index].period,
    mockTransactionRepaymentSchedule.points[index].rent,
    mockTransactionRepaymentSchedule.points[index].principal,
    mockTransactionRepaymentSchedule.points[index].interest,
  ]));
});

test("P3-F6 binds ratings, project facts, every period and summaries to exact Excel ranges", () => {
  const ids = mockEvidence.map((reference) => reference.id);
  assert.equal(new Set(ids).size, ids.length, "EvidenceReference id must remain unique");
  assert.equal(ids.filter((id) => id === "evidence-transaction-plan").length, 1);
  const evidenceById = new Map(mockEvidence.map((reference) => [reference.id, reference]));
  const exact = new Map([
    ["evidence-financed-supplier-rating-1", ["设备评级", "D4:D4"]],
    ["evidence-financed-brand-rating-1", ["设备评级", "F4:F4"]],
    ["evidence-financed-supplier-rating-2", ["设备评级", "D5:D5"]],
    ["evidence-financed-brand-rating-2", ["设备评级", "F5:F5"]],
    ["evidence-financed-supplier-rating-3", ["设备评级", "D6:D6"]],
    ["evidence-financed-brand-rating-3", ["设备评级", "F6:F6"]],
    ["evidence-transaction-project-amount", ["合同设备", "F7:F7"]],
    ["evidence-transaction-finance-ratio-inputs", ["融资方案", "D4:G4"]],
    ["evidence-transaction-plan", ["融资方案", "A4:I4"]],
    ["evidence-transaction-rent-first", ["租金计划", "B4:D4"]],
    ["evidence-transaction-rent-first-12", ["租金计划", "B4:B15"]],
    ["evidence-transaction-rent-total", ["租金计划", "B4:B39"]],
    ["evidence-transaction-rent-term", ["融资方案", "C4:C4"]],
  ]);
  for (const [id, [sheet, range]] of exact) {
    const reference = evidenceById.get(id);
    assert.equal(reference?.locationStatus, "located", id);
    assert.equal(reference?.locator?.kind, "excel", id);
    assert.equal(reference?.locator?.materialId, "material-financed-equipment", id);
    assert.equal(reference?.locator?.materialVersionId, "material-financed-equipment-v1", id);
    assert.equal(reference?.locator?.sheet, sheet, id);
    assert.equal(reference?.locator?.range, range, id);
  }
  mockTransactionRepaymentSchedule.points.forEach((point, index) => {
    const reference = evidenceById.get(point.evidenceRefs[0]);
    assert.equal(reference?.locator?.kind, "excel", point.id);
    assert.equal(reference?.locator?.sheet, "租金计划", point.id);
    assert.equal(reference?.locator?.range, `B${index + 4}:D${index + 4}`, point.id);
  });
});

test("P3-F6 keeps one equipment entry before financing, rent and folded contract details", async () => {
  const [, , mockCase, workspace, equipment, chart] = await readSources();
  const equipmentIndex = workspace.indexOf("<FinancedEquipmentPanel");
  const analysisIndex = workspace.indexOf('<div className="transaction-analysis-grid">');
  const repaymentIndex = workspace.indexOf("<TransactionRepaymentChart");
  const configIndex = workspace.indexOf('<details className="transaction-config-panel"');
  assert.ok(equipmentIndex >= 0 && equipmentIndex < analysisIndex && analysisIndex < repaymentIndex && repaymentIndex < configIndex);
  assert.doesNotMatch(workspace, /TransactionCoreParameters|transaction-semantic-chain|transaction-equipment-switch/);
  assert.doesNotMatch(equipment, /financed-equipment-relation|transaction-chain-borrower|transaction-chain-lessor/);
  assert.match(equipment, /deriveTransactionTopParameters/);
  assert.match(chart, /scheduleTitle/);
  assert.match(chart, /租金计划待补/);
  assert.match(chart, /租金计划异常/);
  assert.doesNotMatch(chart, /Donut|渠道敞口|租金覆盖|利润测算|统计模型|真实客户还款表现/i);
  assert.doesNotMatch(chart, /mockCase|p2Content/);
  assert.doesNotMatch(mockCase, /indexedEvidence\("evidence-transaction-plan"/);
});

test("P3-F6 keeps chart interaction accessible and layout driven by the review container", async () => {
  const [, , , , equipment, chart, styles] = await readSources();
  assert.match(chart, /data-target-id=\{point\.id\}/);
  assert.match(chart, /role="button"/);
  assert.match(chart, /tabIndex=\{0\}/);
  assert.match(chart, /onKeyDown=\{\(event\) => activateWithKeyboard/);
  assert.match(chart, /aria-pressed=\{selected\}/);
  assert.match(chart, /<title>\{copy\(locale, `Period \$\{point\.period\}/);
  assert.match(equipment, /disabled=\{!target\}/);
  assert.match(styles, /\.review-canvas \.transaction-core-facts \{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.doesNotMatch(styles, /financed-equipment-relation/);
  assert.match(styles, /\.transaction-repayment-panel\s*\{[\s\S]*?min-width:\s*0/);
  assert.match(styles, /\.transaction-repayment-svg\s*\{[^}]*width:\s*100%[^}]*overflow:\s*hidden/);
  assert.doesNotMatch(`${chart}\n${styles.slice(styles.indexOf("/* P3-F6:"))}`, /fullscreen/i);
});
