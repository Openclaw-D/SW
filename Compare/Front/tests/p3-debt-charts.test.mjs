import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { mockDimensionDetails, mockEvidence, mockMaterials } from "../src/mock/mockCase.ts";

const root = new URL("../", import.meta.url);

async function readSources() {
  return Promise.all([
    readFile(new URL("src/contracts/workbench.ts", root), "utf8"),
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/components/DebtCoreCharts.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
}

test("P3-F3 debt subject splits remain exact while P3-F7 adds project exposure", async () => {
  const [contracts] = await readSources();
  assert.match(contracts, /interface DimensionSeriesGroup[\s\S]*id: string;[\s\S]*label: string;[\s\S]*points: DimensionSeriesPoint\[\];/);
  assert.match(contracts, /seriesGroups\?: DimensionSeriesGroup\[\];/);

  const debt = mockDimensionDetails.find((detail) => detail.dimensionId === "debt");
  assert.ok(debt);
  const inheritedIds = ["debt-enterprise-creditors", "debt-personal-creditors"];
  assert.deepEqual(debt.compositions.filter((composition) => inheritedIds.includes(composition.id)).map((composition) => composition.id), inheritedIds);
  assert.deepEqual(debt.compositions.find((composition) => composition.id === "debt-project-exposure")?.segments.map((segment) => segment.id), ["debt-exposure-direct-200", "debt-exposure-core-200", "debt-exposure-core-300", "debt-exposure-core-500"]);
  const enterprise = debt.compositions[0].segments.reduce((sum, segment) => sum + segment.value, 0);
  const personal = debt.compositions[1].segments.reduce((sum, segment) => sum + segment.value, 0);
  assert.equal(enterprise, 3140);
  assert.equal(personal, 1120);
  assert.equal(enterprise + personal, 4260);
  assert.equal(debt.compositions.flatMap((composition) => composition.segments).some((segment) => /中登/.test(segment.label)), false);

  assert.equal(debt.series.length, 3);
  assert.deepEqual(debt.series.at(-1).measures.map((measure) => [measure.label, measure.value]), [["企业负债", 3140], ["个人负债", 1120]]);
  assert.equal(debt.series.flatMap((point) => point.measures).some((measure) => /征信|借款/.test(measure.label)), false);
  const repayment = debt.seriesGroups.find((group) => group.id === "debt-repayment");
  assert.equal(repayment.points.length, 12);
  assert.equal(repayment.points.every((point) => point.measures.map((measure) => measure.label).join("|") === "到期负债|可偿还能力"), true);
});

test("P3-F7-Corr1 follows formal-product-channels-v2 and reconciles the latest project exposure", async () => {
  const [, , charts] = await readSources();
  const debt = mockDimensionDetails.find((detail) => detail.dimensionId === "debt");
  assert.ok(debt);
  const exposure = debt.compositions.find((composition) => composition.id === "debt-project-exposure");
  assert.ok(exposure);
  assert.deepEqual(exposure.segments.map((segment) => [segment.id, segment.label, segment.value, segment.unit]), [
    ["debt-exposure-direct-200", "200直", 113, "W"],
    ["debt-exposure-core-200", "200核心", 190, "W"],
    ["debt-exposure-core-300", "300核心", 124, "W"],
    ["debt-exposure-core-500", "500核心", 113, "W"],
  ]);
  assert.deepEqual(exposure.segments.map((segment) => Number(segment.note.match(/限额(\d+)W/)?.[1])), [200, 200, 300, 500]);
  assert.deepEqual(exposure.segments.map((segment) => Number(segment.note.match(/份额(\d+)%/)?.[1])), [21, 35, 23, 21]);
  assert.equal(exposure.segments.every((segment) => segment.note.includes("formal-product-channels-v2")), true);
  assert.equal(new Set(exposure.segments.map((segment) => segment.label)).size, 4);
  assert.equal(exposure.segments.reduce((sum, segment) => sum + segment.value, 0), 540);
  assert.equal(exposure.segments.reduce((sum, segment) => sum + Number(segment.note.match(/份额(\d+)%/)?.[1]), 0), 100);
  assert.equal(exposure.segments.every((segment) => segment.value > 0 && segment.value <= Number(segment.note.match(/限额(\d+)W/)?.[1])), true);
  assert.equal(exposure.segments.some((segment) => ["银行贷款", "融资租赁", "供应链融资", "对外担保"].includes(segment.label)), false);

  const metricById = new Map(debt.metrics.map((metric) => [metric.id, metric]));
  const numberValue = (id) => Number(metricById.get(id).value.replace(/[^\d.]/g, ""));
  assert.equal(numberValue("debt-exposure-history"), 419);
  assert.equal(numberValue("debt-exposure-current"), 121);
  assert.equal(numberValue("debt-exposure-total"), 540);
  assert.equal(numberValue("debt-exposure-history") + numberValue("debt-exposure-current"), numberValue("debt-exposure-total"));
  assert.equal(numberValue("debt-exposure-total") <= 1000, true);
  assert.equal(exposure.segments.reduce((sum, segment) => sum + Number(segment.note.match(/限额(\d+)W/)?.[1]), 0), 1200);
  assert.deepEqual(metricById.get("debt-exposure-deduplication").evidenceRefs, ["evidence-debt-zhongdeng"]);

  const sheet = mockMaterials.find((item) => item.id === "material-review-index")?.sheets.find((item) => item.name === "项目敞口");
  assert.ok(sheet);
  assert.deepEqual(sheet.columns, ["正式产品通道", "通道额度上限(W)", "项目分配金额(W)", "整数份额", "历史存量敞口(W)", "本次融资金额(W)", "项目总敞口(W)", "契约版本", "重复融资核验", "数据状态"]);
  assert.deepEqual(sheet.rows, [
    ["200直", 200, 113, "21%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
    ["200核心", 200, 190, "35%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
    ["300核心", 300, 124, "23%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
    ["500核心", 500, 113, "21%", "", "", "", "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
    ["合计", 1200, 540, "100%", 419, 121, 540, "formal-product-channels-v2", "待中登去重", "脱敏模拟"],
  ]);

  const ids = mockEvidence.map((reference) => reference.id);
  assert.equal(new Set(ids).size, ids.length);
  const evidenceById = new Map(mockEvidence.map((reference) => [reference.id, reference]));
  const expectedRanges = new Map([
    ["evidence-debt-exposure-direct-200", "A4:D4"],
    ["evidence-debt-exposure-core-200", "A5:D5"],
    ["evidence-debt-exposure-core-300", "A6:D6"],
    ["evidence-debt-exposure-core-500", "A7:D7"],
    ["evidence-debt-exposure-history", "E8:E8"],
    ["evidence-debt-exposure-current", "F8:F8"],
    ["evidence-debt-exposure-total", "G8:G8"],
    ["evidence-debt-exposure-summary-inputs", "E8:G8"],
  ]);
  for (const [id, range] of expectedRanges) {
    const reference = evidenceById.get(id);
    assert.equal(reference?.locationStatus, "located", id);
    assert.equal(reference?.locator?.kind, "excel", id);
    assert.equal(reference?.locator?.materialId, "material-review-index", id);
    assert.equal(reference?.locator?.materialVersionId, "material-review-index-v1", id);
    assert.equal(reference?.locator?.sheet, "项目敞口", id);
    assert.equal(reference?.locator?.range, range, id);
  }
  for (const removed of ["evidence-debt-exposure-bank", "evidence-debt-exposure-leasing", "evidence-debt-exposure-supply-chain"]) assert.equal(evidenceById.has(removed), false);
  const zhongdeng = evidenceById.get("evidence-debt-zhongdeng");
  assert.equal(zhongdeng?.locationStatus, "pending");
  assert.equal(zhongdeng?.locator, null);

  assert.match(charts, /const exposureGlobalLimit = 1000/);
  assert.match(charts, /"200直": \{ limit: 200, color: "#111111" \}/);
  assert.match(charts, /"200核心": \{ limit: 200, color: "#30343b" \}/);
  assert.match(charts, /"300核心": \{ limit: 300, color: "#59606a" \}/);
  assert.match(charts, /"500核心": \{ limit: 500, color: "#7b828c" \}/);
  assert.match(charts, /history \+ current - total/);
  assert.match(charts, /compositionTotal - total/);
  assert.match(charts, /uniqueLabels\.size !== composition\.segments\.length/);
  assert.match(charts, /segment\.value <= 0 \|\| segment\.value > formalExposureChannels\[segment\.label\]\.limit/);
  assert.match(charts, /shareTotal !== 100/);
  assert.match(charts, /total > selectedCapacity/);
  assert.match(charts, /total > exposureGlobalLimit/);
  assert.match(charts, /data-chart-kind="debt-project-exposure-history"/);
  assert.match(charts, /surface\("Historical exposure", "历史存量敞口"\)\} · \{history\} \{surface\("CNY 10k", "W"\)\}/);
  assert.doesNotMatch(charts.slice(charts.indexOf("function DebtProjectExposure"), charts.indexOf("function DebtSubjectPie")), /银行贷款|融资租赁|供应链融资|项目总敞口 · \{total\}/);
});

test("P3-F3 keeps the one-year maturity metric synchronized with all 12 located due inputs", () => {
  const debt = mockDimensionDetails.find((detail) => detail.dimensionId === "debt");
  assert.ok(debt);
  const repayment = debt.seriesGroups.find((group) => group.id === "debt-repayment");
  assert.ok(repayment);
  const dueTotal = repayment.points.reduce((sum, point) => sum + point.measures.find((measure) => measure.label === "到期负债").value, 0);
  assert.equal(dueTotal, 1860);

  const totalDebtMetric = debt.metrics.find((metric) => metric.id === "debt-credit-metric");
  const maturityMetric = debt.metrics.find((metric) => metric.id === "debt-maturity");
  assert.ok(totalDebtMetric);
  assert.ok(maturityMetric);
  const totalDebt = Number(String(totalDebtMetric.value).replace(/[^\d.]/g, ""));
  const maturityAmount = Number(String(maturityMetric.value).replace(/[^\d.]/g, ""));
  assert.equal(totalDebt, 4260);
  assert.equal(maturityAmount, dueTotal);
  assert.equal(Number((maturityAmount / totalDebt * 100).toFixed(1)), 43.7);
  assert.equal(maturityMetric.note, "未来12月合计 · 占总负债43.7%");
  assert.deepEqual(maturityMetric.evidenceRefs, ["evidence-debt-repayment-total-due-inputs"]);
  assert.equal(maturityMetric.evidenceRefs.includes("evidence-debt-loans"), false);

  const repaymentSheet = mockMaterials.find((item) => item.id === "material-review-index")?.sheets.find((sheet) => sheet.name === "偿债计划");
  assert.ok(repaymentSheet);
  assert.equal(repaymentSheet.rows.reduce((sum, row) => sum + Number(row[1]), 0), dueTotal);
  assert.deepEqual(repaymentSheet.rows.map((row) => row[1]), repayment.points.map((point) => point.measures.find((measure) => measure.label === "到期负债").value));

  const evidence = mockEvidence.find((reference) => reference.id === "evidence-debt-repayment-total-due-inputs");
  assert.equal(evidence?.locationStatus, "located");
  assert.equal(evidence?.locator?.kind, "excel");
  assert.equal(evidence?.locator?.materialId, "material-review-index");
  assert.equal(evidence?.locator?.materialVersionId, "material-review-index-v1");
  assert.equal(evidence?.locator?.sheet, "偿债计划");
  assert.equal(evidence?.locator?.range, "B4:B15");
});

test("P3-F3 stores every debt chart input in existing Excel sheets with exact located ranges", () => {
  assert.equal(mockMaterials.length, 11);
  const material = mockMaterials.find((item) => item.id === "material-review-index");
  assert.equal(material?.kind, "excel");
  assert.equal(["核验索引", "负债主体构成", "负债历史", "偿债计划"].every((name) => material.sheets.some((sheet) => sheet.name === name)), true);
  assert.equal(material.sheets.find((sheet) => sheet.name === "负债主体构成")?.rows.length, 11);
  assert.equal(material.sheets.find((sheet) => sheet.name === "负债历史")?.rows.at(-1)?.slice(1, 4).reduce((sum, value, index) => index < 2 ? sum + Number(value) : sum, 0), 4260);
  assert.equal(material.sheets.find((sheet) => sheet.name === "偿债计划")?.rows.length, 12);

  const evidenceById = new Map(mockEvidence.map((reference) => [reference.id, reference]));
  const expectedDerivedRanges = new Map([
    ["evidence-debt-history-2022-total-inputs", "B4:C4"],
    ["evidence-debt-history-2023-total-inputs", "B5:C5"],
    ["evidence-debt-history-2024-total-inputs", "B6:C6"],
    ["evidence-debt-repayment-2026-09-comparison-inputs", "B4:C4"],
    ["evidence-debt-repayment-2027-08-comparison-inputs", "B15:C15"],
  ]);
  for (const [evidenceId, range] of expectedDerivedRanges) {
    const reference = evidenceById.get(evidenceId);
    assert.ok(reference, evidenceId);
    assert.equal(reference.locationStatus, "located");
    assert.equal(reference.locator?.kind, "excel");
    assert.equal(reference.locator?.materialId, "material-review-index");
    assert.equal(reference.locator?.materialVersionId, "material-review-index-v1");
    assert.equal(reference.locator?.range, range);
  }

  const debt = mockDimensionDetails.find((detail) => detail.dimensionId === "debt");
  const inheritedCompositions = debt.compositions.filter((composition) => ["debt-enterprise-creditors", "debt-personal-creditors"].includes(composition.id));
  assert.deepEqual(inheritedCompositions.map((composition) => composition.id), ["debt-enterprise-creditors", "debt-personal-creditors"]);
  for (const segment of inheritedCompositions.flatMap((composition) => composition.segments)) {
    assert.equal(segment.evidenceRefs.length > 0, true);
    const reference = evidenceById.get(segment.evidenceRefs[0]);
    assert.equal(reference?.locator?.kind, "excel");
    assert.equal(reference?.locator?.sheet, "负债主体构成");
    assert.match(reference?.locator?.range ?? "", /^A\d+:D\d+$/);
  }
  const exposure = debt.compositions.find((composition) => composition.id === "debt-project-exposure");
  assert.ok(exposure);
  assert.deepEqual(exposure.segments.map((segment) => evidenceById.get(segment.evidenceRefs[0])?.locator?.sheet), ["项目敞口", "项目敞口", "项目敞口", "项目敞口"]);
  assert.deepEqual(exposure.segments.map((segment) => evidenceById.get(segment.evidenceRefs[0])?.locator?.range), ["A4:D4", "A5:D5", "A6:D6", "A7:D7"]);
  for (const point of debt.series) {
    const enterprise = point.measures.find((measure) => measure.label === "企业负债");
    const personal = point.measures.find((measure) => measure.label === "个人负债");
    assert.equal(evidenceById.get(enterprise.evidenceRefs[0])?.locator?.sheet, "负债历史");
    assert.equal(evidenceById.get(personal.evidenceRefs[0])?.locator?.sheet, "负债历史");
    assert.equal(evidenceById.get(`evidence-${point.id}-total-inputs`)?.locator?.range.includes(":"), true);
  }
  const repayment = debt.seriesGroups.find((group) => group.id === "debt-repayment");
  for (const point of repayment.points) {
    const capacity = point.measures.find((measure) => measure.label === "可偿还能力");
    const reference = evidenceById.get(capacity.evidenceRefs[0]);
    assert.equal(reference?.locator?.sheet, "偿债计划");
    assert.match(reference?.locator?.range ?? "", /^B\d+:C\d+$/);
  }

  const zhongdeng = evidenceById.get("evidence-debt-zhongdeng");
  assert.equal(zhongdeng?.locationStatus, "pending");
  assert.equal(zhongdeng?.locator, null);
});

test("P3-F3 four CreditVisual debt charts remain and P3-F7 adds project exposure", async () => {
  const [, detailView, charts] = await readSources();
  for (const component of ["DebtSubjectPie", "DebtTrendChart", "DebtRepaymentChart", "DebtCoreCharts"]) assert.match(charts, new RegExp(`function ${component}|export function ${component}`));
  for (const title of ["企业负债", "个人负债", "负债趋势", "偿债能力"]) assert.match(charts, new RegExp(title));
  assert.match(charts, /function DebtProjectExposure/);
  assert.match(charts, /项目通道敞口/);
  assert.match(charts, /detail\.series\.flatMap/);
  assert.match(charts, /detail\.seriesGroups\?\.find/);
  assert.match(charts, /detail\.compositions \?\? \[\]/);
  assert.doesNotMatch(charts, /mockCase|LineSeriesChart|CreditDetail|runtime.*Front/i);
  assert.doesNotMatch(charts, /中登/);

  const debtStart = detailView.indexOf('dimension.id === "debt"');
  const genericStart = detailView.indexOf(': <div className={`dimension-visual-grid', debtStart);
  assert.notEqual(debtStart, -1);
  assert.notEqual(genericStart, -1);
  const debtBranch = detailView.slice(debtStart, genericStart);
  assert.match(debtBranch, /<DebtCoreCharts/);
  assert.doesNotMatch(debtBranch, /PlanarVisual|LineSeriesChart|dimension-breakdown/);
  assert.match(detailView, /dimension-detail-table/);
  assert.match(detailView, /dimension-conclusion/);
});

test("P3-F3 keeps debt marks accessible, evidence-interactive and container responsive", async () => {
  const [, , charts, styles] = await readSources();
  for (const kind of ["debt-enterprise-segment", "debt-personal-segment", "debt-enterprise-bar", "debt-personal-bar", "debt-total-point", "debt-due-bar", "debt-capacity-point"]) assert.match(charts, new RegExp(`data-chart-kind=(?:\\{[^}]+\\}|)"${kind}"|"${kind}"`));
  assert.match(charts, /data-chart-kind="debt-project-exposure-segment"/);
  assert.match(charts, /data-chart-kind="debt-project-exposure-history"/);
  assert.match(charts, /aria-pressed=\{selected\}/);
  assert.match(charts, /role="button"/);
  assert.match(charts, /event\.key !== "Enter" && event\.key !== " "/);
  assert.match(charts, /evidence-\$\{targetId\}-inputs/);
  assert.match(charts, /capacity\.value \/ Math\.max\(due\.value, 1\) \* 100/);

  assert.match(styles, /\/\* P3-F3:[\s\S]*?\.debt-core-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(styles, /@container review-section \(min-width:\s*900px\)[\s\S]*?\.workbench-body\.is-material-collapsed \.debt-core-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styles, /\.debt-core-panel\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden/);
  assert.match(styles, /\.debt-pie-label\s*\{[^}]*font-size:\s*12px/);
  assert.match(styles, /\.debt-chart-item\.is-selected/);
  assert.doesNotMatch(charts, /fullscreen/i);
});

test("P3-F7-Corr2 keeps history in the center and uses the first screen for three non-duplicate facts", async () => {
  const [, , charts, styles] = await readSources();
  assert.match(charts, /const requiredFactIds = \["debt-exposure-history", "debt-exposure-current", "debt-exposure-total", "debt-exposure-deduplication"\]/);
  assert.match(charts, /const displayedFactIds = \["debt-exposure-current", "debt-exposure-total", "debt-exposure-deduplication"\]/);
  assert.match(charts, /requiredFacts\.some\(\(metric\) => !metric\)/);
  assert.match(charts, /\{displayedFacts\.map\(\(metric\) => \{/);
  assert.match(charts, /data-chart-kind="debt-project-exposure-history"/);
  assert.match(charts, /data-target-id=\{centerTargetId\}/);

  assert.match(styles, /\.debt-exposure-facts\s*\{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/);
  assert.match(styles, /@container review-section \(max-width:\s*520px\)[\s\S]*?\.debt-exposure-facts\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styles, /@container review-section \(max-width:\s*520px\)[\s\S]*?\[data-target-id="debt-exposure-deduplication"\]\s*\{[^}]*grid-column:\s*1 \/ -1/);
  assert.match(styles, /@container review-section \(min-width:\s*900px\)[\s\S]*?\.debt-exposure-facts\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styles, /@container review-section \(min-width:\s*900px\)[\s\S]*?\[data-target-id="debt-exposure-deduplication"\]\s*\{[^}]*grid-column:\s*1 \/ -1/);
});
