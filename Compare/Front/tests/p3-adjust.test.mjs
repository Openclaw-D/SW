import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  aggregateDimensionTimeSeries,
  createEvidenceSelectionGroup,
  materialHitCounts,
  resolveEvidenceSelectionGroup,
  reviewTargetForEvidence,
  validEvidenceLocator,
} from "../src/lib/workbenchLogic.ts";
import { mockMaterials } from "../src/mock/mockCase.ts";
import {
  mockDimensionTimeSeries,
  mockP3BusinessDataset,
  mockP3Evidence,
  mockP3Materials,
  validateP3BusinessConservation,
} from "../src/mock/p3AdjustData.ts";

const target = (evidenceRef, reviewTargetId = "fact-a") => ({
  evidenceRef,
  evidenceRefs: ["excel-a", "excel-b", "pdf-a", "pdf-b", "image-a", "image-b"],
  dimensionId: "revenue",
  reviewTargetId,
  factVersionId: null,
});

test("P3-Adjust resolves one selection group across multiple ranges and materials", () => {
  const group = createEvidenceSelectionGroup(target("excel-a"));
  assert.deepEqual(group.targets.map((item) => item.evidenceRef), ["excel-a", "excel-b", "pdf-a", "pdf-b", "image-a", "image-b"]);

  const materials = [
    {
      id: "excel",
      versionId: "excel-v1",
      kind: "excel",
      fileName: "a.xlsx",
      label: "a",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      availability: "available",
      isSimulated: true,
      sourceLabel: "test",
      sheets: [{ name: "S", columns: ["A", "B"], rows: [[1, 2], [3, 4]] }],
    },
    {
      id: "pdf",
      versionId: "pdf-v1",
      kind: "pdf",
      fileName: "a.pdf",
      label: "a",
      mimeType: "application/pdf",
      availability: "available",
      isSimulated: true,
      sourceLabel: "test",
      pageCount: 1,
      pages: [{ page: 1, title: "P1", lines: ["row"] }],
    },
    {
      id: "image",
      versionId: "image-v1",
      kind: "image",
      fileName: "a.png",
      label: "a",
      mimeType: "image/png",
      availability: "available",
      isSimulated: true,
      sourceLabel: "test",
      pixelWidth: 1000,
      pixelHeight: 600,
      description: "test",
    },
  ];
  const evidence = [
    { id: "excel-a", label: "A", locationStatus: "located", materialStatus: "confirmed", locator: { kind: "excel", materialId: "excel", materialVersionId: "excel-v1", sheet: "S", range: "A4:A4" } },
    { id: "excel-b", label: "B", locationStatus: "located", materialStatus: "confirmed", locator: { kind: "excel", materialId: "excel", materialVersionId: "excel-v1", sheet: "S", range: "B5:B5" } },
    { id: "pdf-a", label: "PDF", locationStatus: "located", materialStatus: "confirmed", locator: { kind: "pdf", materialId: "pdf", materialVersionId: "pdf-v1", page: 1, bbox: { x: .1, y: .2, width: .3, height: .1 } } },
    { id: "pdf-b", label: "PDF2", locationStatus: "located", materialStatus: "confirmed", locator: { kind: "pdf", materialId: "pdf", materialVersionId: "pdf-v1", page: 1, bbox: { x: .5, y: .55, width: .25, height: .12 } } },
    { id: "image-a", label: "IMG", locationStatus: "located", materialStatus: "confirmed", locator: { kind: "image", materialId: "image", materialVersionId: "image-v1", bbox: { x: .08, y: .15, width: .28, height: .2 } } },
    { id: "image-b", label: "IMG2", locationStatus: "located", materialStatus: "confirmed", locator: { kind: "image", materialId: "image", materialVersionId: "image-v1", bbox: { x: .58, y: .48, width: .22, height: .25 } } },
  ];
  const resolved = resolveEvidenceSelectionGroup(group, evidence, materials);
  assert.equal(resolved.status, "located");
  assert.deepEqual(materialHitCounts(resolved), { excel: 2, pdf: 2, image: 2 });
  assert.equal(reviewTargetForEvidence(group, "excel-b")?.reviewTargetId, "fact-a");
});

test("P3-Adjust treats a selection group as all-or-clear for invalid and version-mismatched evidence", () => {
  const group = createEvidenceSelectionGroup(target("excel-a"));
  const material = {
    id: "excel",
    versionId: "excel-v2",
    kind: "excel",
    fileName: "a.xlsx",
    label: "a",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    availability: "available",
    isSimulated: true,
    sourceLabel: "test",
    sheets: [{ name: "S", columns: ["A"], rows: [[1]] }],
  };
  const evidence = [
    { id: "excel-a", label: "A", locationStatus: "located", materialStatus: "confirmed", locator: { kind: "excel", materialId: "excel", materialVersionId: "excel-v2", sheet: "S", range: "A4:A4" } },
    { id: "excel-b", label: "B", locationStatus: "version_mismatch", materialStatus: "review", locator: { kind: "excel", materialId: "excel", materialVersionId: "excel-v1", sheet: "S", range: "A4:A4" } },
    { id: "pdf-a", label: "PDF", locationStatus: "pending", materialStatus: "review", locator: null },
  ];
  const resolved = resolveEvidenceSelectionGroup(group, evidence, [material]);
  assert.equal(resolved.status, "version_mismatch");
  assert.deepEqual(materialHitCounts(resolved), {});
});

test("P3-Adjust clears every previous hit for pending, unverifiable, missing material and invalid locator", () => {
  const material = {
    id: "excel",
    versionId: "excel-v1",
    kind: "excel",
    fileName: "a.xlsx",
    label: "a",
    mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    availability: "available",
    isSimulated: true,
    sourceLabel: "test",
    sheets: [{ name: "S", columns: ["A"], rows: [[1]] }],
  };
  const cases = [
    { expected: "pending", evidence: { id: "case", label: "pending", locationStatus: "pending", materialStatus: "review", locator: null } },
    { expected: "unverifiable", evidence: { id: "case", label: "bad", locationStatus: "unverifiable", materialStatus: "review", locator: null } },
    { expected: "missing_material", evidence: { id: "case", label: "missing material", locationStatus: "located", materialStatus: "review", locator: { kind: "excel", materialId: "absent", materialVersionId: "absent-v1", sheet: "S", range: "A4:A4" } } },
    { expected: "invalid_locator", evidence: { id: "case", label: "bad range", locationStatus: "located", materialStatus: "review", locator: { kind: "excel", materialId: "excel", materialVersionId: "excel-v1", sheet: "S", range: "A9:A9" } } },
  ];
  for (const item of cases) {
    const group = createEvidenceSelectionGroup({ evidenceRef: "case", dimensionId: "revenue", reviewTargetId: "fact-case", factVersionId: null });
    const resolved = resolveEvidenceSelectionGroup(group, [item.evidence], [material]);
    assert.equal(resolved.status, item.expected);
    assert.deepEqual(materialHitCounts(resolved), {});
  }
  const missing = createEvidenceSelectionGroup({ evidenceRef: "absent", dimensionId: "revenue", reviewTargetId: "fact-absent", factVersionId: null });
  assert.equal(resolveEvidenceSelectionGroup(missing, [], [material]).status, "missing_evidence");
});

test("P3-Adjust aggregates one raw time series as day week month year and handles range boundaries", () => {
  const revenue = mockDimensionTimeSeries.find((series) => series.dimensionId === "revenue");
  assert.ok(revenue);
  const base = { projectId: "p", dimensionId: "revenue", metricIds: revenue.metrics.map((metric) => metric.id), startDate: "2026-01-01", endDate: "2026-03-31", timezone: "Asia/Shanghai" };
  for (const grain of ["day", "week", "month", "year"]) {
    const result = aggregateDimensionTimeSeries(revenue, { ...base, grain });
    assert.equal(result.status, "available", grain);
    assert.deepEqual([...result.points].sort((left, right) => left.periodStart.localeCompare(right.periodStart)), result.points);
    assert.equal(result.points.every((point) => point.measures.every((measure) => measure.evidenceRefs.length > 0)), true);
  }
  assert.equal(aggregateDimensionTimeSeries(revenue, { ...base, startDate: "2027-01-01", endDate: "2027-01-31", grain: "month" }).status, "empty");
  assert.equal(aggregateDimensionTimeSeries(revenue, { ...base, startDate: "2026-03-01", endDate: "2026-01-01", grain: "month" }).status, "invalid");
  const debt = mockDimensionTimeSeries.find((series) => series.dimensionId === "debt");
  assert.equal(aggregateDimensionTimeSeries(debt, { ...base, dimensionId: "debt", metricIds: debt.metrics.map((metric) => metric.id), grain: "day" }).status, "unavailable");
});

test("P3-Control preserves complete and custom daily ranges without UI clipping", async () => {
  const revenue = mockDimensionTimeSeries.find((series) => series.dimensionId === "revenue");
  assert.ok(revenue);
  const request = {
    projectId: "p",
    dimensionId: "revenue",
    metricIds: revenue.metrics.map((metric) => metric.id),
    startDate: "2026-01-01",
    endDate: "2026-06-30",
    timezone: "Asia/Shanghai",
    grain: "day",
  };
  const complete = aggregateDimensionTimeSeries(revenue, request);
  assert.equal(complete.status, "available");
  assert.equal(complete.points.length, 181);
  assert.equal(complete.points[0].periodStart, request.startDate);
  assert.equal(complete.points.at(-1).periodEnd, request.endDate);

  const custom = aggregateDimensionTimeSeries(revenue, { ...request, endDate: "2026-01-31" });
  assert.equal(custom.status, "available");
  assert.equal(custom.points.length, 31);
  assert.equal(custom.points.at(-1).periodEnd, "2026-01-31");

  const controls = await readFile(new URL("../src/components/TimeSeriesControls.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(controls, /rangeEndForGrain|maximumDays|addDays/);
  assert.match(controls, /createTimeSeriesRequest/);
  assert.match(controls, /resolveTimeSeriesRange/);
  assert.doesNotMatch(controls, /setTimezone|time-zone-control|<select|北京时间|>UTC</);
  assert.match(controls, /\$\{dimensionName\} end date[\s\S]*setRange/);
});

test("P3-Control keeps reference labels above chart marks and removes the material demo switch", async () => {
  const [charts, pane, app] = await Promise.all([
    readFile(new URL("../src/components/RevenueCoreCharts.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/MaterialPane.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
  ]);
  const revenueChart = charts.slice(charts.indexOf("function RevenueChart"), charts.indexOf("function InvoiceChart"));
  const invoiceChart = charts.slice(charts.indexOf("function InvoiceChart"), charts.indexOf("function polarPoint"));
  assert.ok(revenueChart.indexOf('copy(locale, "0% growth baseline", "0% 增长基线")') > revenueChart.indexOf("revenue-income-bar"));
  assert.ok(invoiceChart.indexOf('copy(locale, "90% reference line", "90% 参考线")') > invoiceChart.indexOf("revenue-invoice-bar"));
  assert.match(revenueChart, /revenue-reference-overlay/);
  assert.match(invoiceChart, /revenue-reference-overlay/);
  assert.match(charts, /pointSpacing/);
  assert.match(charts, /barWidth/);

  assert.doesNotMatch(pane, /切换预览状态|PreviewMode|<option value="(?:ready|loading|empty|error)"/);
  assert.doesNotMatch(app, /previewMode|setPreviewMode|onPreviewModeChange/);
  for (const stateText of ["后台解析中", "证据待定位", "材料版本不符", "证据不可核验", "暂无材料"]) assert.match(pane, new RegExp(stateText));
});

test("P3-Adjust mock package is deterministic, fully located, and conserves linked business totals", () => {
  assert.equal(mockP3BusinessDataset.isSimulated, true);
  assert.match(mockP3BusinessDataset.sourceLabel, /脱敏|模拟/);
  assert.equal(mockP3Materials.every((material) => material.isSimulated), true);
  assert.equal(mockP3Evidence.every((reference) => reference.locationStatus === "located" && reference.locator), true);
  const mergedMaterial = mockMaterials.find((material) => material.id === "material-review-index");
  assert.equal(mergedMaterial?.kind, "excel");
  assert.equal(mergedMaterial?.kind === "excel" && mergedMaterial.sheets.some((sheet) => sheet.name === "生产日数据"), true);
  for (const reference of mockP3Evidence) {
    const material = reference.locator ? mockMaterials.find((item) => item.id === reference.locator.materialId) : null;
    assert.ok(material, reference.id);
    assert.equal(validEvidenceLocator(reference, material), true, reference.id);
  }
  assert.deepEqual(validateP3BusinessConservation(), {
    financing: true,
    rent: true,
    revenue: true,
    debt: true,
    cashflow: true,
    exposure: true,
  });
});

test("P3-Adjust UI keeps background selection, multi-hit counts, pulse and reduced-motion fallback", async () => {
  const [app, pane, css, gateway, controls] = await Promise.all([
    readFile(new URL("../src/App.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/MaterialPane.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/styles/app.css", import.meta.url), "utf8"),
    readFile(new URL("../src/gateway/workbenchGateway.ts", import.meta.url), "utf8"),
    readFile(new URL("../src/components/TimeSeriesControls.tsx", import.meta.url), "utf8"),
  ]);
  assert.match(app, /selectEvidenceGroup/);
  assert.match(app, /selectionRequestRef/);
  assert.doesNotMatch(app, /selectEvidenceGroup[\s\S]{0,900}materialCollapsed:\s*false/);
  assert.match(app, /document\.getElementById\(`fact-\$\{factId\}`\)[\s\S]*#review-pane \[data-target-id\][\s\S]*dataset\.targetId === factId/);
  assert.match(pane, /materialHitCounts/);
  assert.match(pane, /selectionTargets/);
  assert.match(css, /@keyframes\s+evidence-breathe/);
  assert.match(css, /prefers-reduced-motion:\s*reduce[\s\S]*evidence-highlight/);
  assert.match(gateway, /queryDimensionSeries/);
  assert.match(controls, /日[\s\S]*周[\s\S]*月[\s\S]*年/);
  assert.match(controls, /type="date"/);
  const detail = await readFile(new URL("../src/components/DimensionDetailView.tsx", import.meta.url), "utf8");
  assert.match(detail, /right\.periodStart\.localeCompare\(left\.periodStart\)/);
});

test("P3-Adjust keeps review data marks neutral and binds equipment views to current-line originals", async () => {
  const files = [
    "ComplianceSubjectGraph.tsx",
    "DimensionDetailView.tsx",
    "RevenueCoreCharts.tsx",
    "DebtCoreCharts.tsx",
    "CashflowCoreCharts.tsx",
  ];
  const [styles, equipment, model, stages, energy, review, workspace, repayment, revenue, ...componentSources] = await Promise.all([
    readFile(new URL("../src/styles/app.css", import.meta.url), "utf8"),
    readFile(new URL("../src/components/FinancedEquipmentPanel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/EquipmentModelPreview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/ProductionStagesPanel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/ProductionEnergyChart.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/ReviewCanvas.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/TransactionWorkspace.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/TransactionCoreCharts.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/components/RevenueCoreCharts.tsx", import.meta.url), "utf8"),
    ...files.map((file) => readFile(new URL(`../src/components/${file}`, import.meta.url), "utf8")),
  ]);

  const neutralStart = styles.indexOf("/* P3-Control: the review canvas is temporarily monochrome");
  assert.ok(neutralStart >= 0);
  const neutralBlock = styles.slice(neutralStart);
  for (const token of ["#111", "#30343b", "#59606a", "#7b828c", "#a6abb2", "#d7d9dd", "#f1f2f4"]) assert.match(neutralBlock, new RegExp(token));
  const allowedColors = new Set(["#111", "#111111", "#30343b", "#59606a", "#7b828c", "#a6abb2", "#d7d9dd", "#f1f2f4"]);
  for (const source of componentSources) {
    for (const match of source.matchAll(/#[0-9a-f]{3,8}\b/gi)) assert.equal(allowedColors.has(match[0].toLowerCase()), true, match[0]);
  }

  assert.match(equipment, /aria-label=\{copy\(locale, "Financed-equipment details", "融资设备详情"\)\}/);
  assert.match(equipment, /financed-equipment-photo-column[\s\S]*financed-equipment-primary-image[\s\S]*financed-equipment-angle-gallery[\s\S]*financed-equipment-current[\s\S]*financed-equipment-detail-evidence/);
  assert.match(equipment, /data-equipment-line-id=\{current\.id\}/);
  assert.match(equipment, /data-material-id=\{image\.id\}/);
  assert.doesNotMatch(equipment, /EquipmentModelPreview|financed-equipment-model-sidecar|derived-model-boundary|derivedModelRef/);
  assert.match(model, /variant\?: "full" \| "sidecar"/);
  assert.match(model, /variant === "sidecar"/);
  assert.match(model, /Configuration-driven structural schematic/);
  assert.match(model, /variant === "full" \? <div className="equipment-model-switch"/);
  assert.match(model, /variant === "full" \? <footer>/);
  assert.doesNotMatch(equipment, /financed-equipment-preview-shell/);
  assert.match(styles, /P5 evidence polish:[\s\S]*?\.review-canvas \.financed-equipment-workspace \{[^}]*height: 430px[^}]*1\.18fr[^}]*\.82fr/s);
  assert.match(styles, /\.review-canvas \.financed-equipment-angle-gallery \{[^}]*overflow-x: auto/s);
  assert.match(styles, /@container review-section \(max-width: 760px\)[\s\S]*?\.review-canvas \.financed-equipment-workspace \{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(stages, /className=\{`production-stage-media[\s\S]*className="production-stage-copy"/);
  assert.match(styles, /\.review-canvas \.production-stage-media \{[^}]*aspect-ratio:\s*4 \/ 3[^}]*background:\s*var\(--review-neutral-100\)/s);
  assert.match(styles, /\.review-canvas \.production-stage-media > img,[\s\S]*object-fit:\s*contain/);
  assert.match(review, /className="risk-level-cards"[\s\S]*risk-level-detail/);
  for (const color of ["#7c3aed", "#dc2626", "#f59e0b", "#2563eb", "#22c55e"]) {
    assert.equal(styles.split(/\r?\n/).filter((line) => line.includes(color)).every((line) => line.trim().startsWith("#review-risk") || line.trim().startsWith(".review-canvas :is(.transaction-price-range")), true, color);
  }
  assert.match(workspace, /priceRiskLevel[\s\S]*price-risk-\$\{priceRiskLevel\}[\s\S]*data-risk-level=\{priceRiskLevel/);
  assert.match(styles, /\.review-canvas \.price-range-track > i \{[^}]*business-risk-support[^}]*business-risk-attention[^}]*business-risk-confirm[^}]*business-risk-risk[^}]*business-risk-forbid/);
  assert.match(styles, /transaction-repayment-principal[^}]*business-risk-support[\s\S]*transaction-repayment-interest[^}]*business-risk-confirm[\s\S]*transaction-repayment-line[^}]*business-risk-risk/);
  assert.match(repayment, /transaction-repayment-principal[\s\S]*transaction-repayment-interest[\s\S]*transaction-repayment-node/);
  assert.match(revenue, /function coverageRiskLevel[\s\S]*value >= 2[\s\S]*value >= 1\.5[\s\S]*value >= 1[\s\S]*value >= \.75/);
  assert.match(revenue, /coverage-risk-\$\{fact\.riskLevel\}[\s\S]*data-risk-level=\{fact\.riskLevel/);
  assert.doesNotMatch(energy, /利润率对比不可用|production-point-evidence/);
  assert.match(energy, /labelEvery[\s\S]*showsLabel/);
  assert.match(energy, /point\.electricityEvidenceRefs\.length[\s\S]*point\.outputEvidenceRefs\.length/);
  assert.match(styles, /\.review-canvas \.production-payroll-svg \{ height: 220px; max-height: 220px; display: block; \}/);
  assert.match(styles, /\.review-canvas \.operating-equipment-cards \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
});
