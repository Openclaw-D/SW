import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { PRODUCTION_ENERGY_SLOT_WIDTH, productionEnergyEvidenceUnion, productionEnergyPlotGeometry } from "../src/lib/productionEnergyGeometry.ts";
import { createEvidenceSelectionGroup } from "../src/lib/workbenchLogic.ts";
import { mockDimensionDetails, mockEvidence, mockMaterials } from "../src/mock/mockCase.ts";
import { mockProductionPayrollSeries } from "../src/mock/p2Content.ts";

const root = new URL("../", import.meta.url);

async function readSources() {
  return Promise.all([
    readFile(new URL("src/mock/p2Content.ts", root), "utf8"),
    readFile(new URL("src/mock/mockCase.ts", root), "utf8"),
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/components/ProductionPayrollChart.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
}

test("P3-Adjust energy geometry keeps all grains readable and line/bar/point centers identical", async () => {
  for (const grain of ["day", "week", "month", "year"]) {
    const geometry = productionEnergyPlotGeometry(181, grain);
    assert.equal(geometry.slotWidth, PRODUCTION_ENERGY_SLOT_WIDTH);
    assert.equal(geometry.minimumPlotWidth, 181 * PRODUCTION_ENERGY_SLOT_WIDTH);
    assert.equal(geometry.labelEvery, Math.ceil(84 / PRODUCTION_ENERGY_SLOT_WIDTH));
    for (const index of [0, 90, 180]) {
      const markCenter = (index + .5) / 181 * 100;
      assert.equal(geometry.lineCenters[index] - markCenter, 0, `${grain}-${index}`);
    }
  }

  assert.deepEqual(productionEnergyEvidenceUnion(["electricity-a", "shared"], ["output-a", "shared"]), ["electricity-a", "shared", "output-a"]);
  assert.deepEqual(productionEnergyEvidenceUnion(["output-a", "shared"], ["electricity-a", "shared"]), ["output-a", "shared", "electricity-a"]);
  const periodRefs = productionEnergyEvidenceUnion(["electricity-a"], ["output-a", "output-b"]);
  const selectionGroup = createEvidenceSelectionGroup({ evidenceRef: periodRefs[0], evidenceRefs: periodRefs, dimensionId: "production", reviewTargetId: "timeseries-production-day-2026-04-01-electricity", factVersionId: null });
  assert.deepEqual(selectionGroup.targets.map((target) => target.evidenceRef), ["electricity-a", "output-a", "output-b"]);
  assert.equal(selectionGroup.targets.every((target) => target.reviewTargetId === "timeseries-production-day-2026-04-01-electricity" && target.factVersionId === null), true);

  const [energy, detailView, styles] = await Promise.all([
    readFile(new URL("src/components/ProductionEnergyChart.tsx", root), "utf8"),
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(energy, /productionEnergyPlotGeometry\(pointCount, activeGrain\)/);
  assert.match(energy, /grainLabels: Record<ProductionEnergyDisplayGrain, string> = \{ day: "日", week: "周", month: "月", quarter: "季", year: "年" \}/);
  assert.match(energy, /\{grainLabels\[activeGrain\]\}内求和的绝对值/);
  assert.match(energy, /plotGeometry\.lineCenters\[index\]/);
  assert.match(energy, /className="production-energy-scroll"[\s\S]*--production-energy-min-width/);
  assert.match(energy, /productionEnergyEvidenceUnion\(point\.electricityEvidenceRefs, point\.outputEvidenceRefs\)/);
  assert.match(energy, /productionEnergyEvidenceUnion\(point\.outputEvidenceRefs, point\.electricityEvidenceRefs\)/);
  assert.match(energy, /const periodSelected =[\s\S]*selectedTarget\?\.reviewTargetId[\s\S]*selectedEvidenceRefs\.includes/);
  assert.equal([...energy.matchAll(/aria-pressed=\{periodSelected\}/g)].length, 2);
  assert.equal([...energy.matchAll(/focusClass\(point\.id\)/g)].length, 2);
  assert.equal([...energy.matchAll(/focusProps\(point\.id\)/g)].length, 2);
  assert.match(detailView, /<ProductionEnergyChart[\s\S]*grain=\{timeSeriesResponse\?\.request\.grain \?\? timeSeriesRequest\?\.grain \?\? "month"\}/);
  assert.match(styles, /\.review-canvas \.production-energy-scroll \{[^}]*overflow-x:\s*auto[^}]*overflow-y:\s*hidden/s);
  assert.match(styles, /\.review-canvas \.production-chart-grid \{[^}]*min-width:\s*var\(--production-energy-min-width[^}]*minmax\(var\(--production-energy-slot-width/s);
  assert.match(styles, /\.review-canvas \.production-output-line \{ bottom:\s*28px; height:\s*calc\(100% - 28px\); \}/);
  assert.match(styles, /\.review-canvas \.production-chart-item \{ grid-template-rows:\s*164px 28px; \}/);
  assert.match(styles, /\.review-canvas \.production-electricity-bar \{[^}]*left:\s*50%[^}]*translateX\(-50%\)/s);
  assert.match(styles, /\.review-canvas \.production-output-point \{ left:\s*50%; \}/);
});

test("P3-F5 keeps Production B payroll values and deterministic summaries in one series group", () => {
  assert.equal(mockProductionPayrollSeries.id, "production-payroll");
  assert.equal(mockProductionPayrollSeries.label, "人员工资");
  assert.deepEqual(mockProductionPayrollSeries.points.map((point) => point.label), ["4月", "5月", "6月"]);
  const values = mockProductionPayrollSeries.points.map((point) => Object.fromEntries(point.measures.map((measure) => [measure.label, measure.value])));
  assert.deepEqual(values, [
    { 工资总额: 22.8, 在岗人数: 38, 人均工资: 0.6 },
    { 工资总额: 23.2, 在岗人数: 38, 人均工资: 0.61 },
    { 工资总额: 23.6, 在岗人数: 38, 人均工资: 0.62 },
  ]);
  assert.equal(values.reduce((sum, item) => sum + item.工资总额, 0), 69.6);
  assert.equal(values.at(-1).在岗人数, 38);
  assert.equal((values.at(-1).工资总额 / values.at(-1).在岗人数).toFixed(2), "0.62");
  const production = mockDimensionDetails.find((detail) => detail.dimensionId === "production");
  assert.ok(production);
  assert.deepEqual(production.seriesGroups?.map((group) => group.id), ["production-payroll"]);
  assert.equal(production.seriesGroups?.[0], mockProductionPayrollSeries);
});

test("P3-F5 stores payroll rows in the existing production Excel material", () => {
  assert.equal(mockMaterials.length, 11);
  const material = mockMaterials.find((item) => item.id === "material-production-operations");
  assert.equal(material?.kind, "excel");
  const sheet = material.sheets.find((item) => item.name === "人员工资");
  assert.ok(sheet);
  assert.deepEqual(sheet.columns, ["月份", "工资总额（万元）", "在岗人数（人）", "人均工资（万元/人）", "口径说明", "数据状态"]);
  assert.deepEqual(sheet.rows.map((row) => row.slice(0, 4)), [
    ["4月", 22.8, 38, 0.6],
    ["5月", 23.2, 38, 0.61],
    ["6月", 23.6, 38, 0.62],
  ]);
  sheet.rows.forEach((row) => assert.equal(Number(row[3]), Number((Number(row[1]) / Number(row[2])).toFixed(2))));
});

test("P3-F5 binds every payroll input and summary to exact located ranges", () => {
  const evidenceById = new Map(mockEvidence.map((reference) => [reference.id, reference]));
  const exact = new Map([
    ["evidence-production-payroll-2026-04-amount", "B4:B4"],
    ["evidence-production-payroll-2026-04-staff", "C4:C4"],
    ["evidence-production-payroll-2026-04-per-capita-inputs", "B4:C4"],
    ["evidence-production-payroll-2026-05-amount", "B5:B5"],
    ["evidence-production-payroll-2026-05-staff", "C5:C5"],
    ["evidence-production-payroll-2026-05-per-capita-inputs", "B5:C5"],
    ["evidence-production-payroll-2026-06-amount", "B6:B6"],
    ["evidence-production-payroll-2026-06-staff", "C6:C6"],
    ["evidence-production-payroll-2026-06-per-capita-inputs", "B6:C6"],
    ["evidence-production-payroll-three-month-total", "B4:B6"],
    ["evidence-production-payroll-latest-staff", "C6:C6"],
    ["evidence-production-payroll-latest-per-capita-inputs", "B6:C6"],
  ]);
  for (const [id, range] of exact) {
    const reference = evidenceById.get(id);
    assert.equal(reference?.locationStatus, "located", id);
    assert.equal(reference?.locator?.kind, "excel", id);
    assert.equal(reference?.locator?.materialId, "material-production-operations", id);
    assert.equal(reference?.locator?.materialVersionId, "material-production-operations-v1", id);
    assert.equal(reference?.locator?.sheet, "人员工资", id);
    assert.equal(reference?.locator?.range, range, id);
  }
});

test("P3-Adjust places the one production time control immediately before payroll and energy", async () => {
  const [content, mockCase, detailView, chart] = await readSources();
  assert.match(content, /export const mockProductionPayrollSeries: DimensionSeriesGroup/);
  assert.match(mockCase, /seriesGroups:\s*\[mockProductionPayrollSeries\]/);
  const productionStart = detailView.indexOf('dimension.id === "production"');
  const productionEnd = detailView.indexOf(': dimension.id === "revenue"', productionStart);
  const productionBranch = detailView.slice(productionStart, productionEnd);
  const stagesIndex = productionBranch.indexOf("<ProductionStagesPanel");
  const controlsIndex = productionBranch.indexOf('className="production-time-controls-sticky"');
  const payrollIndex = productionBranch.indexOf("<ProductionPayrollChart");
  const energyIndex = productionBranch.indexOf("<ProductionEnergyChart");
  assert.ok(stagesIndex >= 0 && stagesIndex < controlsIndex && controlsIndex < payrollIndex && payrollIndex < energyIndex);
  assert.match(productionBranch, /\{timeControls\}[\s\S]*<ProductionPayrollChart[\s\S]*grain=\{timeSeriesResponse\?\.request\.grain \?\? timeSeriesRequest\?\.grain \?\? "month"\}/);
  assert.match(detailView, /dimension\.id !== "production" \? timeControls : null/);
  assert.match(detailView, /dimension\.id === "production" && timeSeriesRequest \? undefined : detail\.seriesGroups/);
  assert.match(productionBranch, /detail\.seriesGroups\?\.find\(\(group\) => group\.id === "production-payroll"\)/);
  assert.doesNotMatch(productionBranch, /LineSeriesChart|RevenueCoreCharts|DebtCoreCharts|CashflowCoreCharts/);
  assert.match(chart, /工资总额与期末在岗人数分轴展示/);
  assert.doesNotMatch(chart, /利润率|行业基准|测试版|演示版|开发说明/);
});

test("P3-F5 keeps payroll chart accessible, empty-safe, label-separated and container responsive", async () => {
  const [, , detailView, chart, styles] = await readSources();
  assert.match(chart, /role="button"/);
  assert.match(chart, /tabIndex=\{0\}/);
  assert.match(chart, /onKeyDown=\{\(event\) => activateWithKeyboard/);
  assert.match(chart, /aria-pressed=\{selected\}/);
  assert.match(chart, /data-target-id=/);
  assert.match(chart, /is-selected/);
  assert.match(chart, /人员工资不可用/);
  assert.match(chart, /latest\.amount\.value \/ latest\.staff\.value/);
  assert.doesNotMatch(chart, /在岗\$\{row\.staff\.value\.toLocaleString\(\)\}人，人均工资/);
  assert.doesNotMatch(chart, /在岗人数 · \$\{row\.staff\.value\.toLocaleString\(\)\}人 · 人均/);
  assert.match(chart, /production-payroll-latest-per-capita-inputs/);
  assert.match(chart, /production-payroll-label-divider/);
  assert.match(chart, /production-payroll-label-guide/);
  assert.match(chart, /export function payrollPlotGeometry\(pointCount: number, grain: TimeGrain\)[\s\S]*const centers = Array\.from\([\s\S]*plotMargins\.left \+ \(index \+ \.5\) \* slotWidth/);
  assert.match(chart, /x=\{center - barWidth \/ 2\}/);
  assert.match(chart, /staffPoints = rows\.map\(\(row, index\) => \(\{ x: centers\[index\]/);
  assert.match(chart, /innerPlotWidth = Math\.max\(minimumInnerWidth, pointCount \* grainPresentation\[grain\]\.minimumSlotWidth\)/);
  assert.match(chart, /minimumLabelSpacing = 82[\s\S]*Math\.ceil\(minimumLabelSpacing \/ slotWidth\)/);
  assert.match(chart, /className="production-payroll-chart-scroll"[\s\S]*data-minimum-plot-width=\{plotCanvasWidth\}/);
  assert.match(chart, /minWidth: `\$\{plotCanvasWidth\}px`, width: `max\(100%, \$\{plotCanvasWidth\}px\)`/);
  assert.deepEqual([...chart.matchAll(/(?:day|week|month|year): \{ label: "(日|周|月|年)", perCapitaUnit: "(万元\/人\/(?:日|周|月|年))"/g)].map((match) => [match[1], match[2]]), [["日", "万元/人/日"], ["周", "万元/人/周"], ["月", "万元/人/月"], ["年", "万元/人/年"]]);
  assert.match(chart, /periodEvidenceRefs\(row, row\.amount\)/);
  assert.match(chart, /periodEvidenceRefs\(row, row\.staff\)/);
  assert.match(chart, /isPeriodSelected\(row, selectedTarget\)/);
  assert.match(chart, /data-period-id=\{row\.id\}/);
  assert.match(detailView, /groupedMeasureLabels=\{dimension\.id === "production" \? \["工资总额", "在岗人数"\] : \[\]\}/);
  assert.match(detailView, /groupedEvidenceRefs = \[\.\.\.new Set\(groupedMeasures\.flatMap/);
  assert.match(styles, /\.review-canvas \.production-payroll-chart-scroll \{[^}]*overflow-x:\s*auto[^}]*overflow-y:\s*hidden/s);
  assert.match(styles, /\.review-canvas \.production-time-controls-sticky \{[^}]*position:\s*sticky[^}]*grid-column:\s*1 \/ -1/s);
  assert.match(styles, /\/\* P3-F5:[\s\S]*?\.production-dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(styles, /@container review-section \(min-width:\s*900px\)[\s\S]*?\.workbench-body\.is-material-collapsed \.production-dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)[^}]*align-items:\s*stretch/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.production-stage-chain\s*\{[^}]*grid-column:\s*1 \/ -1/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.operating-equipment\s*\{[^}]*grid-column:\s*1/);
  assert.match(styles, /@container review-section \(min-width:\s*900px\)[\s\S]*?\.workbench-body\.is-material-collapsed \.operating-equipment-cards\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.operating-equipment-card\s*\{[^}]*height:\s*100%[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\) auto/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.production-payroll-panel\s*\{[^}]*grid-column:\s*1 \/ -1/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.production-energy-panel\s*\{[^}]*grid-column:\s*1 \/ -1/);
  assert.match(styles, /\.production-dashboard > :is\(\.production-time-controls-sticky, \.production-payroll-panel, \.production-energy-panel\)\s*\{[^}]*width:\s*100%[^}]*min-width:\s*0[^}]*grid-column:\s*1 \/ -1/);
  assert.doesNotMatch(chart, /fullscreen/i);
});

test("Fix3-Corr2 keeps the production controls and both time-series panels on full responsive rows", async () => {
  const [, , detailView, payroll, styles] = await readSources();
  const energy = await readFile(new URL("src/components/ProductionEnergyChart.tsx", root), "utf8");
  const productionStart = detailView.indexOf('dimension.id === "production"');
  const productionEnd = detailView.indexOf(': dimension.id === "revenue"', productionStart);
  const productionBranch = detailView.slice(productionStart, productionEnd);

  assert.ok(productionBranch.indexOf('className="production-time-controls-sticky"') < productionBranch.indexOf("<ProductionPayrollChart"));
  assert.ok(productionBranch.indexOf("<ProductionPayrollChart") < productionBranch.indexOf("<ProductionEnergyChart"));
  assert.match(styles, /\.production-dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.production-dashboard\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.production-payroll-panel\s*\{[^}]*grid-column:\s*1 \/ -1/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.production-energy-panel\s*\{[^}]*grid-column:\s*1 \/ -1/);
  assert.doesNotMatch(styles, /\.workbench-body\.is-material-collapsed \.production-payroll-panel\s*\{[^}]*grid-column:\s*2/);
  assert.match(payroll, /className="production-payroll-chart-scroll"[\s\S]*data-minimum-plot-width=\{plotCanvasWidth\}/);
  assert.match(styles, /\.review-canvas \.production-payroll-chart-scroll\s*\{[^}]*max-width:\s*100%[^}]*overflow-x:\s*auto[^}]*overflow-y:\s*hidden/s);
  assert.match(energy, /className="production-energy-scroll"[\s\S]*--production-energy-min-width/);
  assert.match(styles, /\.review-canvas \.production-energy-scroll\s*\{[^}]*max-width:\s*100%[^}]*overflow-x:\s*auto[^}]*overflow-y:\s*hidden/s);
});
