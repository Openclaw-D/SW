import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { mockDimensionDetails, mockEvidence, mockMaterials } from "../src/mock/mockCase.ts";

const root = new URL("../", import.meta.url);

async function readSources() {
  return Promise.all([
    readFile(new URL("src/contracts/workbench.ts", root), "utf8"),
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/components/CashflowCoreCharts.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
}

function numericMetric(value) {
  return Number(String(value).replace(/[^\d.]/g, ""));
}

test("P3-F4 keeps six monthly cashflow rows derived and synchronized with four compact facts", async () => {
  const [contracts] = await readSources();
  assert.match(contracts, /interface DimensionCompositionSegment[\s\S]*note\?: string;/);
  const cashflow = mockDimensionDetails.find((detail) => detail.dimensionId === "cashflow");
  assert.ok(cashflow);
  assert.equal(cashflow.series.length, 6);
  const expected = [
    [1180, 1040, 140, 11.9],
    [1260, 1190, 70, 5.6],
    [1380, 1260, 120, 8.7],
    [1290, 1210, 80, 6.2],
    [1460, 1280, 180, 12.3],
    [1510, 1360, 150, 9.9],
  ];
  cashflow.series.forEach((point, index) => {
    const inflow = point.measures.find((measure) => measure.label === "流入");
    const outflow = point.measures.find((measure) => measure.label === "流出");
    const net = point.measures.find((measure) => measure.label === "净额");
    assert.deepEqual([inflow.value, outflow.value, net.value], expected[index].slice(0, 3));
    assert.equal(net.value, inflow.value - outflow.value);
    assert.equal(Number(((inflow.value - outflow.value) / inflow.value * 100).toFixed(1)), expected[index][3]);
    assert.equal(point.measures.some((measure) => measure.label === "净流入率"), false);
  });
  const totals = cashflow.series.reduce((sum, point) => {
    sum.inflow += point.measures.find((measure) => measure.label === "流入").value;
    sum.outflow += point.measures.find((measure) => measure.label === "流出").value;
    sum.net += point.measures.find((measure) => measure.label === "净额").value;
    return sum;
  }, { inflow: 0, outflow: 0, net: 0 });
  assert.deepEqual(totals, { inflow: 8080, outflow: 7340, net: 740 });
  assert.deepEqual(cashflow.metrics.map((metric) => [metric.label, numericMetric(metric.value)]), [["半年流入", 8080], ["半年流出", 7340], ["半年净流入", 740], ["异常笔数", 7]]);
});

test("P3-F4 keeps inflow and outflow counterparties conservative with exact concentration", () => {
  const cashflow = mockDimensionDetails.find((detail) => detail.dimensionId === "cashflow");
  assert.ok(cashflow);
  assert.deepEqual(cashflow.compositions.map((composition) => composition.id), ["cashflow-inflow-parties", "cashflow-outflow-parties"]);
  const [inflow, outflow] = cashflow.compositions;
  const total = (composition) => composition.segments.reduce((sum, segment) => sum + segment.value, 0);
  const shares = (composition) => composition.segments.map((segment) => Number((segment.value / total(composition) * 100).toFixed(1)));
  assert.equal(total(inflow), 8080);
  assert.equal(total(outflow), 7340);
  assert.deepEqual(shares(inflow), [26.7, 20.1, 15.6, 12.1, 9.6, 15.9]);
  assert.deepEqual(shares(outflow), [24.9, 18.2, 14.0, 10.4, 8.8, 23.7]);
  assert.equal(Number(shares(inflow).reduce((sum, share) => sum + share, 0).toFixed(1)), 100);
  assert.equal(Number(shares(outflow).reduce((sum, share) => sum + share, 0).toFixed(1)), 100);
  assert.equal(Number(inflow.segments.slice(0, 5).reduce((sum, segment) => sum + segment.value, 0) / total(inflow) * 100).toFixed(1), "84.1");
  assert.equal(Number(outflow.segments.slice(0, 5).reduce((sum, segment) => sum + segment.value, 0) / total(outflow) * 100).toFixed(1), "76.3");
  assert.equal([...inflow.segments, ...outflow.segments].every((segment) => typeof segment.note === "string" && segment.note.length > 0), true);
});

test("P3-F4 stores monthly and counterparty inputs in existing Excel material with exact locators", () => {
  assert.equal(mockMaterials.length, 11);
  const material = mockMaterials.find((item) => item.id === "material-review-index");
  assert.equal(material?.kind, "excel");
  const monthly = material.sheets.find((sheet) => sheet.name === "流水月度");
  const counterparties = material.sheets.find((sheet) => sheet.name === "流水交易对手");
  assert.ok(monthly);
  assert.ok(counterparties);
  assert.deepEqual(monthly.columns, ["期间", "流入", "流出", "净额", "净流入率", "单位", "数据状态"]);
  assert.equal(monthly.rows.length, 6);
  monthly.rows.forEach((row) => {
    assert.equal(row[3], Number(row[1]) - Number(row[2]));
    assert.equal(row[4], `${(((Number(row[1]) - Number(row[2])) / Number(row[1])) * 100).toFixed(1)}%`);
  });
  assert.equal(monthly.rows.reduce((sum, row) => sum + Number(row[1]), 0), 8080);
  assert.equal(monthly.rows.reduce((sum, row) => sum + Number(row[2]), 0), 7340);
  assert.equal(monthly.rows.reduce((sum, row) => sum + Number(row[3]), 0), 740);
  assert.deepEqual(counterparties.columns, ["方向", "交易对手", "金额", "占比", "账期", "单位", "数据状态"]);
  assert.equal(counterparties.rows.length, 12);

  const evidenceById = new Map(mockEvidence.map((reference) => [reference.id, reference]));
  const exact = new Map([
    ["evidence-cashflow-half-in", ["流水月度", "B4:B9"]],
    ["evidence-cashflow-half-out", ["流水月度", "C4:C9"]],
    ["evidence-cashflow-half-net-inputs", ["流水月度", "B4:C9"]],
    ["evidence-cashflow-jan-in", ["流水月度", "B4:B4"]],
    ["evidence-cashflow-jan-out", ["流水月度", "C4:C4"]],
    ["evidence-cashflow-jan-net-inputs", ["流水月度", "B4:C4"]],
    ["evidence-cashflow-jan-net-rate-inputs", ["流水月度", "B4:C4"]],
    ["evidence-cashflow-jun-net-rate-inputs", ["流水月度", "B9:C9"]],
  ]);
  for (const [id, [sheet, range]] of exact) {
    const reference = evidenceById.get(id);
    assert.equal(reference?.locationStatus, "located", id);
    assert.equal(reference?.locator?.kind, "excel", id);
    assert.equal(reference?.locator?.materialId, "material-review-index", id);
    assert.equal(reference?.locator?.materialVersionId, "material-review-index-v1", id);
    assert.equal(reference?.locator?.sheet, sheet, id);
    assert.equal(reference?.locator?.range, range, id);
  }
  const cashflow = mockDimensionDetails.find((detail) => detail.dimensionId === "cashflow");
  for (const [index, segment] of cashflow.compositions.flatMap((composition) => composition.segments).entries()) {
    const reference = evidenceById.get(segment.evidenceRefs[0]);
    assert.equal(reference?.locator?.sheet, "流水交易对手");
    assert.equal(reference?.locator?.range, `A${index + 4}:G${index + 4}`);
    assert.equal(counterparties.rows[index][1], segment.label);
    assert.equal(counterparties.rows[index][2], segment.value);
    assert.equal(counterparties.rows[index][4], segment.note);
  }
  const anomaly = evidenceById.get("evidence-cashflow-anomalies");
  assert.equal(anomaly?.locationStatus, "pending");
  assert.equal(anomaly?.locator, null);
});

test("P3-F4 renders only account flow and counterparty charts while retaining three conclusions", async () => {
  const [, detailView, charts] = await readSources();
  for (const component of ["CashflowTotals", "AccountFlowChart", "PartyPie", "CashflowCoreCharts"]) assert.match(charts, new RegExp(`function ${component}|export function ${component}`));
  for (const title of ["账户流水", "交易对手", "流入方", "流出方"]) assert.match(charts, new RegExp(title));
  assert.doesNotMatch(charts, /利润测算|租金覆盖|mockCase|GuaranteeDetail|runtime.*Front/i);
  assert.match(charts, /\(inflow\.value - outflow\.value\) \/ Math\.max\(inflow\.value, 1\) \* 100/);
  const branchStart = detailView.indexOf('dimension.id === "cashflow"');
  const branchEnd = detailView.indexOf(': <div className={`dimension-visual-grid', branchStart);
  const branch = detailView.slice(branchStart, branchEnd);
  assert.match(branch, /<CashflowCoreCharts/);
  assert.match(branch, /cashflow-key-conclusions/);
  assert.match(branch, /detail\.breakdown\.map/);
  assert.doesNotMatch(branch, /LineSeriesChart|PlanarVisual/);
  const cashflow = mockDimensionDetails.find((detail) => detail.dimensionId === "cashflow");
  assert.deepEqual(cashflow.breakdown.map((item) => item.label), ["收支真实性", "经营匹配", "异常流水"]);
});

test("P3-F4 keeps chart marks accessible, selected, empty-safe and container responsive", async () => {
  const [, , charts, styles] = await readSources();
  assert.match(charts, /role="button"/);
  assert.match(charts, /tabIndex=\{0\}/);
  assert.match(charts, /onKeyDown=\{\(event\) => activateWithKeyboard/);
  assert.match(charts, /aria-pressed=\{selected\}/);
  assert.match(charts, /data-target-id=/);
  assert.match(charts, /is-selected/);
  assert.match(charts, /账户流水不可用/);
  assert.match(charts, /构成不可用/);
  assert.match(styles, /\/\* P3-F4:[\s\S]*?\.cashflow-core-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(styles, /@container review-section \(min-width:\s*900px\)[\s\S]*?\.workbench-body\.is-material-collapsed \.cashflow-core-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styles, /\.cashflow-party-pair\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.doesNotMatch(charts, /fullscreen/i);
});
