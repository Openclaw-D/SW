import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { mockDimensionDetails, mockEvidence, mockMaterials } from "../src/mock/mockCase.ts";

const root = new URL("../", import.meta.url);

async function readSources() {
  return Promise.all([
    readFile(new URL("src/contracts/workbench.ts", root), "utf8"),
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/components/RevenueCoreCharts.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
}

test("P3-F2 revenue compositions remain exact while P3-F7 adds profitability", async () => {
  const [contracts] = await readSources();
  assert.match(contracts, /interface DimensionCompositionSegment[\s\S]*id: string;[\s\S]*label: string;[\s\S]*value: number;[\s\S]*unit: string;[\s\S]*evidenceRefs: string\[\];[\s\S]*tone: AssessmentTone;/);
  assert.match(contracts, /compositions\?: DimensionComposition\[\];/);

  const revenue = mockDimensionDetails.find((detail) => detail.dimensionId === "revenue");
  assert.ok(revenue);
  const inheritedIds = ["revenue-upstream", "revenue-downstream", "revenue-receivable-aging"];
  const inherited = revenue.compositions.filter((composition) => inheritedIds.includes(composition.id));
  assert.deepEqual(inherited.map((composition) => composition.id), inheritedIds);
  const segments = inherited.flatMap((composition) => composition.segments);
  assert.equal(segments.length, 9);
  assert.equal(segments.every((segment) => typeof segment.value === "number" && segment.unit === "%" && segment.evidenceRefs.length > 0 && typeof segment.tone === "string"), true);

  const evidenceById = new Map(mockEvidence.map((reference) => [reference.id, reference]));
  for (const segment of segments) {
    for (const evidenceId of segment.evidenceRefs) {
      const reference = evidenceById.get(evidenceId);
      assert.ok(reference, evidenceId);
      assert.equal(reference.locationStatus, "located");
      assert.equal(reference.locator?.kind, "excel");
      assert.equal(reference.locator?.materialId, "material-revenue-chain");
      assert.equal(["上下游构成", "应收账龄"].includes(reference.locator?.sheet), true);
    }
  }

  const revenueMaterial = mockMaterials.find((material) => material.id === "material-revenue-chain");
  assert.equal(revenueMaterial?.kind, "excel");
  assert.deepEqual(revenueMaterial.sheets.filter((sheet) => ["营收链", "上下游构成", "应收账龄"].includes(sheet.name)).map((sheet) => sheet.name), ["营收链", "上下游构成", "应收账龄"]);
  assert.equal(revenueMaterial.isSimulated, true);

  const profitability = revenue.compositions.find((composition) => composition.id === "revenue-profitability");
  assert.ok(profitability);
  assert.deepEqual(profitability.segments.map((segment) => segment.id), [
    "revenue-profit-material",
    "revenue-profit-site-rent",
    "revenue-profit-utilities",
    "revenue-profit-payroll",
    "revenue-profit-other",
    "revenue-profit-net-profit",
  ]);
  assert.equal(profitability.segments.every((segment) => segment.unit === "万元" && segment.evidenceRefs.length === 1), true);
  assert.deepEqual(profitability.segments.map((segment) => evidenceById.get(segment.evidenceRefs[0])?.locator?.range), ["C4:C4", "D4:D4", "E4:E4", "F4:F4", "G4:G4", "H4:H4"]);
  assert.equal(profitability.segments.every((segment) => evidenceById.get(segment.evidenceRefs[0])?.locator?.sheet === "利润与租金覆盖"), true);
  const profitabilitySheet = revenueMaterial.sheets.find((sheet) => sheet.name === "利润与租金覆盖");
  assert.ok(profitabilitySheet);
  assert.equal(profitabilitySheet.rows.length, 1);
});

test("P3-F2 four inherited charts remain and P3-F7 adds profitability without LineSeriesChart", async () => {
  const [, detailView, charts] = await readSources();
  for (const component of ["RevenueChart", "InvoiceChart", "CompositionDonuts", "CollectionChart"]) assert.match(charts, new RegExp(`function ${component}`));
  for (const title of ["营收趋势", "票款互证", "上下游构成", "回款账龄"]) assert.match(charts, new RegExp(title));
  assert.match(charts, /function ProfitabilityPanel/);
  assert.match(charts, /利润与租金覆盖/);
  assert.match(charts, /detail\.series\.flatMap/);
  assert.match(charts, /detail\.compositions \?\? \[\]/);
  assert.doesNotMatch(charts, /mockCase|LineSeriesChart|OperationDetail|runtime.*Front/i);

  const revenueStart = detailView.indexOf('dimension.id === "revenue"');
  const genericStart = detailView.indexOf(': <div className={`dimension-visual-grid', revenueStart);
  assert.notEqual(revenueStart, -1);
  assert.notEqual(genericStart, -1);
  const revenueBranch = detailView.slice(revenueStart, genericStart);
  assert.match(revenueBranch, /<RevenueCoreCharts/);
  assert.match(revenueBranch, /<RevenueSourceChain/);
  assert.equal(revenueBranch.indexOf("<RevenueCoreCharts") < revenueBranch.indexOf("<RevenueSourceChain"), true);
  assert.doesNotMatch(revenueBranch, /LineSeriesChart/);
  assert.match(detailView, /function RevenueSourceChain/);
  assert.match(detailView, /营收来源链/);
  assert.match(detailView, /dimension-detail-table/);
  assert.match(detailView, /切换平面或表格视图/);
});

test("P3-F2 keeps every bar point and segment evidence-interactive and container responsive", async () => {
  const [, , charts, styles] = await readSources();
  for (const kind of ["revenue-bar", "revenue-line-point", "invoice-bar", "invoice-line-point", "composition-segment", "aging-segment"]) assert.match(charts, new RegExp(`data-chart-kind="${kind}"`));
  assert.match(charts, /onEvidenceSelect\(evidenceId, row\.income\.id\)/);
  assert.match(charts, /onEvidenceSelect\(evidenceId, targetId\)/);
  assert.match(charts, /onEvidenceSelect\(evidenceId, segment\.id\)/);
  assert.match(charts, /aria-pressed=\{selected\}/);
  assert.match(charts, /role="button"/);
  assert.match(charts, /确定性派生/);

  assert.match(styles, /\.revenue-core-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(styles, /@container review-section \(min-width:\s*900px\)[\s\S]*?\.workbench-body\.is-material-collapsed \.revenue-core-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styles, /\.revenue-core-panel\s*\{[^}]*min-width:\s*0[^}]*overflow:\s*hidden/);
  assert.match(styles, /\.revenue-chart-item\.is-selected/);
  assert.match(styles, /\.revenue-segment-label/);
});

test("P3-F2 keeps derived targets stable and locates every complete Excel input range", async () => {
  const [, , charts] = await readSources();
  const expectedRanges = new Map([
    ["evidence-revenue-2023-income-growth-inputs", "E4:E5"],
    ["evidence-revenue-2024-income-growth-inputs", "E5:E6"],
    ["evidence-revenue-2022-collections-rate-inputs", "C4:D4"],
    ["evidence-revenue-2023-collections-rate-inputs", "C5:D5"],
    ["evidence-revenue-2024-collections-rate-inputs", "C6:D6"],
  ]);
  const evidenceById = new Map(mockEvidence.map((reference) => [reference.id, reference]));

  for (const [evidenceId, range] of expectedRanges) {
    const reference = evidenceById.get(evidenceId);
    assert.ok(reference, evidenceId);
    assert.equal(reference.locationStatus, "located");
    assert.equal(reference.locator?.kind, "excel");
    assert.equal(reference.locator?.materialId, "material-revenue-chain");
    assert.equal(reference.locator?.materialVersionId, "material-revenue-chain-v1");
    assert.equal(reference.locator?.sheet, "营收链");
    assert.equal(reference.locator?.range, range);
  }

  assert.match(charts, /const growthTargetId = index === 0 \? null : `\$\{row\.income\.id\}-growth`/);
  assert.match(charts, /const rateTargetId = `\$\{collected\.id\}-rate`/);
  assert.match(charts, /growthEvidenceRefs: growthTargetId \? \[`evidence-\$\{growthTargetId\}-inputs`\] : \[\]/);
  assert.match(charts, /rateEvidenceRefs: \[`evidence-\$\{rateTargetId\}-inputs`\]/);
  assert.match(charts, /const labelBand = \{ top: 28, height: 46, divider: 51, incomeY: 43, growthY: 68 \};/);
  assert.match(charts, /y=\{labelBand\.incomeY\}/);
  assert.match(charts, /y=\{labelBand\.growthY\}/);
});
