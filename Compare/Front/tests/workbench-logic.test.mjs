import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { DIMENSION_IDS } from "../src/contracts/workbench.ts";
import {
  activeDimensionFromPositions,
  averageScore,
  aggregateProductionEnergy,
  appendImmutableEvent,
  attachReviewEvidenceTargets,
  calculateFinancedEquipmentLedger,
  canStartGraphPan,
  createCorrectedFact,
  deriveDetailFocus,
  deriveFinancingBreakdown,
  derivePriceBenchmark,
  deriveScoreSummary,
  groupRiskItems,
  hardConstraintEvidenceRefs,
  isActivationKey,
  materialIdForEvidenceResolution,
  moveGraphNode,
  relationshipEdgePoints,
  parseExcelRange,
  persistedLayoutFrom,
  productionSeriesStatus,
  RISK_LEVEL_ORDER,
  resolveEvidence,
  reviewEvidenceTargetAt,
  sanitizePersistedLayout,
  scoreRadius,
  scoreToGrade,
  sameReviewEvidenceTarget,
  selectedRiskItemId,
  shortestRelationshipPath,
  terminatePointerSession,
  toggledRiskLevel,
  variancePresentation,
} from "../src/lib/workbenchLogic.ts";
import { mockComplianceGraph, mockDimensions, mockEvidence, mockFacts, mockGlobalRiskSummary, mockHardConstraints, mockMaterials, mockReviewEvents } from "../src/mock/mockCase.ts";
import { mockFinancedEquipment, mockProductionEnergy } from "../src/mock/p2Content.ts";

const baseLayout = {
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
};

test("keeps dimension order and derives the shared active dimension from scroll positions", () => {
  assert.deepEqual(DIMENSION_IDS, ["compliance", "transaction", "production", "revenue", "debt", "cashflow"]);
  assert.equal(activeDimensionFromPositions([
    { id: "compliance", top: -600 },
    { id: "transaction", top: -20 },
    { id: "production", top: 540 },
  ]), "transaction");
});

test("R8-2 derives every score letter from strict five-grade boundaries and one equal-weight summary", () => {
  assert.deepEqual([0, 19, 20, 39, 40, 59, 60, 79, 80, 100].map(scoreToGrade), ["E", "E", "D", "D", "C", "C", "B", "B", "A", "A"]);
  assert.equal(scoreToGrade(79.94), "B");
  assert.equal(scoreToGrade(79.95), "A");
  assert.deepEqual([19.94, 19.95, 39.94, 39.95, 59.94, 59.95].map(scoreToGrade), ["E", "D", "D", "C", "C", "B"]);
  assert.equal(averageScore([82, 68, 74, 71, 64, 78]), 72.8);
  const intentionallyStale = mockDimensions.map((dimension) => ({ ...dimension, scoreGrade: "E" }));
  const derived = deriveScoreSummary(intentionallyStale);
  assert.deepEqual(derived.dimensions.map((dimension) => dimension.scoreGrade), ["A", "B", "B", "B", "B", "B"]);
  assert.equal(derived.overallScore, 72.8);
  assert.equal(derived.overallGrade, "B");
  const roundedBoundary = deriveScoreSummary(mockDimensions.map((dimension) => ({ ...dimension, score: 79.95 })));
  assert.deepEqual(roundedBoundary.dimensions.map((dimension) => dimension.scoreGrade), ["A", "A", "A", "A", "A", "A"]);
  assert.equal(roundedBoundary.overallScore, 80);
  assert.equal(roundedBoundary.overallGrade, "A");
  assert.deepEqual(deriveScoreSummary([...intentionallyStale].reverse()).dimensions.map((dimension) => dimension.id), DIMENSION_IDS);
  assert.throws(() => deriveScoreSummary(intentionallyStale.slice(0, 5)), /六维评分必须包含/);
  assert.throws(() => deriveScoreSummary([...intentionallyStale.slice(0, 5), intentionallyStale[0]]), /六维评分必须包含/);
  assert.deepEqual(mockDimensions.map((dimension) => dimension.scoreGrade), mockDimensions.map((dimension) => scoreToGrade(dimension.score)));
  assert.equal(scoreRadius(100), 100);
  assert.equal(scoreRadius(0), 18);
});

test("P2-F2 groups rules anomalies and determinations in the fixed five-level order", () => {
  const groups = groupRiskItems(mockGlobalRiskSummary);
  assert.deepEqual(groups.map((group) => group.level), RISK_LEVEL_ORDER);
  assert.deepEqual(groups.map((group) => group.items.length), [0, 0, 4, 1, 0]);
  assert.equal(groups.flatMap((group) => group.items).length, mockGlobalRiskSummary.hardConstraintResults.length + mockGlobalRiskSummary.keyAnomalies.length + mockGlobalRiskSummary.pendingHumanDeterminations.length);
  const synthetic = groupRiskItems({
    ...mockGlobalRiskSummary,
    hardConstraintResults: [
      { ...mockGlobalRiskSummary.hardConstraintResults[0], id: "block", result: "block" },
      { ...mockGlobalRiskSummary.hardConstraintResults[0], id: "manual", result: "manual_review" },
      { ...mockGlobalRiskSummary.hardConstraintResults[0], id: "pass", result: "pass" },
    ],
    keyAnomalies: [],
    pendingHumanDeterminations: [],
  });
  assert.deepEqual(synthetic.map((group) => group.items.map((item) => item.id)), [["risk-rule-block"], [], ["risk-rule-manual"], [], ["risk-rule-pass"]]);
  const rule = groups.flatMap((group) => group.items).find((item) => item.id === "risk-rule-hard-h03-v1");
  assert.deepEqual(rule.evidenceTargets.map(({ evidenceRef, dimensionId, reviewTargetId, factVersionId }) => ({ evidenceRef, dimensionId, reviewTargetId, factVersionId })), [
    { evidenceRef: "evidence-compliance-charter", dimensionId: "compliance", reviewTargetId: "graph-attachment-attachment-charter", factVersionId: "fact-charter-v2" },
    { evidenceRef: "evidence-debt-zhongdeng", dimensionId: "debt", reviewTargetId: "debt-zhongdeng", factVersionId: "fact-debt-zhongdeng-v1" },
  ]);
  assert.deepEqual(hardConstraintEvidenceRefs(mockGlobalRiskSummary.hardConstraintResults[0]), ["evidence-compliance-charter", "evidence-debt-zhongdeng"]);
  for (const item of groups.flatMap((group) => group.items)) {
    assert.ok(item.primaryTarget);
    assert.equal(item.evidenceTargets.some((target) => sameReviewEvidenceTarget(target, item.primaryTarget)), true);
  }
  const debt = groups.flatMap((group) => group.items).find((item) => item.id === "risk-anomaly-debt-registration");
  assert.equal(debt.primaryTarget.reviewTargetId, "debt-zhongdeng");
  assert.equal(debt.evidenceTargets[0].reviewTargetId, "debt-credit");
});

test("P2-F2 keeps the exact risk row when two items share one evidence and target", () => {
  const groups = groupRiskItems(mockGlobalRiskSummary);
  const target = mockGlobalRiskSummary.pendingHumanDeterminations.find((item) => item.id === "risk-pending-charter").evidenceTargets[0];
  assert.equal(selectedRiskItemId(groups, target, "risk-pending-charter"), "risk-pending-charter");
  assert.equal(selectedRiskItemId(groups, target, "risk-rule-hard-h03-v1"), "risk-rule-hard-h03-v1");
  assert.equal(selectedRiskItemId(groups, null, "risk-pending-charter"), null);
});

test("P2 risk accordion starts closed, toggles one populated level, and ignores empty levels", () => {
  assert.equal(toggledRiskLevel(null, "confirm", 4), "confirm");
  assert.equal(toggledRiskLevel("confirm", "confirm", 4), null);
  assert.equal(toggledRiskLevel("confirm", "attention", 1), "attention");
  assert.equal(toggledRiskLevel("attention", "forbid", 0), "attention");
});

test("P2-F3 moves graph coordinates inside bounds and resolves direct or shortest subject paths", () => {
  const initial = { a: { x: 20, y: 30 }, b: { x: 80, y: 90 } };
  const moved = moveGraphNode(initial, "a", { x: 999, y: -20 }, { width: 400, height: 300, nodeWidth: 100, nodeHeight: 80 });
  assert.deepEqual(moved.a, { x: 300, y: 0 });
  assert.deepEqual(initial.a, { x: 20, y: 30 });
  assert.deepEqual(moveGraphNode(initial, "missing", { x: 1, y: 1 }), initial);
  const direct = shortestRelationshipPath(mockComplianceGraph, "subject-person-wang", "subject-company-borrower");
  assert.deepEqual(direct?.nodeIds, ["subject-person-wang", "subject-company-borrower"]);
  assert.deepEqual(new Set(direct?.relationIds), new Set(["relation-wang-legal", "relation-wang-controller"]));
  const indirect = shortestRelationshipPath(mockComplianceGraph, "subject-company-holding", "subject-person-li");
  assert.deepEqual(indirect?.nodeIds, ["subject-company-holding", "subject-company-borrower", "subject-person-li"]);
  assert.equal(shortestRelationshipPath(mockComplianceGraph, "missing", "subject-person-li"), null);
  assert.equal(canStartGraphPan(false), true);
  assert.equal(canStartGraphPan(true), false);
  assert.equal(terminatePointerSession({ pointerId: 4, value: "drag" }, 4), null);
  assert.deepEqual(terminatePointerSession({ pointerId: 4, value: "drag" }, 5), { pointerId: 4, value: "drag" });
  const edge = relationshipEdgePoints({ x: 0, y: 0 }, { x: 300, y: 0 }, 100);
  assert.deepEqual(edge, { x1: 100, y1: 50, x2: 300, y2: 50 });
  const diagonal = relationshipEdgePoints({ x: 0, y: 0 }, { x: 100, y: 100 }, 100);
  assert.equal(Math.round(Math.hypot(diagonal.x1 - 50, diagonal.y1 - 50)), 50);
  assert.equal(Math.round(Math.hypot(diagonal.x2 - 150, diagonal.y2 - 150)), 50);
  const shares = mockComplianceGraph.relations.filter((relation) => relation.relation === "shareholding");
  assert.deepEqual(shares.map((relation) => relation.sharePercent), [90, 10]);
  assert.equal(mockComplianceGraph.nodes.some((node) => node.kind === "company" && !shares.some((relation) => relation.toId === node.id)), true);
});

test("P2-F4 derives contract totals, comparable values and signed variances from one benchmark source", () => {
  const result = calculateFinancedEquipmentLedger(mockFinancedEquipment);
  assert.deepEqual(result.lines.map((line) => line.contractTotal), [820000, 1140000, 780000]);
  assert.deepEqual(result.lines.map((line) => line.comparableUnitPrice), [395000, 365000, 252000]);
  assert.deepEqual(result.lines.map((line) => line.variance), [30000, 45000, 24000]);
  assert.equal(result.totalQuantity, 8);
  assert.equal(result.contractTotal, 2740000);
  assert.equal(result.comparableTotal, 2641000);
  assert.equal(result.variance, 99000);
  const changed = calculateFinancedEquipmentLedger({ ...mockFinancedEquipment, lines: mockFinancedEquipment.lines.map((line, index) => index ? line : { ...line, priceBenchmark: { ...line.priceBenchmark, median: 400000 } }) });
  assert.equal(changed.lines[0].comparableUnitPrice, 400000);
  assert.equal(changed.comparableTotal, 2651000);
  const unavailable = calculateFinancedEquipmentLedger({ ...mockFinancedEquipment, lines: mockFinancedEquipment.lines.map((line, index) => index ? line : { ...line, priceBenchmark: { ...line.priceBenchmark, status: "unavailable", median: null } }) });
  assert.equal(unavailable.comparableStatus, "unavailable");
  assert.equal(unavailable.comparableTotal, null);
  assert.equal(unavailable.variance, null);
  assert.deepEqual([variancePresentation(12).tone, variancePresentation(-12).tone, variancePresentation(0).tone], ["higher", "lower", "equal"]);
});

test("P2-F4 derives price positions, financing composition, focus states and keyboard activation", () => {
  const line = mockFinancedEquipment.lines[0];
  const price = derivePriceBenchmark(line.priceBenchmark, line.contractUnitPrice);
  assert.equal(price.status, "available");
  assert.equal(price.currentPosition > 0 && price.currentPosition < 100, true);
  assert.equal(derivePriceBenchmark({ ...line.priceBenchmark, status: "unavailable", low: null, median: null, high: null }, line.contractUnitPrice).status, "unavailable");
  assert.equal(derivePriceBenchmark({ ...line.priceBenchmark, low: 5, median: 4, high: 3 }, 4).status, "invalid");
  const financing = deriveFinancingBreakdown(2_740_000, 767_200);
  assert.deepEqual(financing.status === "available" ? [financing.downPaymentPercent, financing.financedPercent] : [], [28, 72]);
  assert.equal(deriveFinancingBreakdown(100, 120).status, "invalid");
  assert.deepEqual(deriveDetailFocus("price", "row-a", { panelId: "price", itemId: "row-b" }), { panelActive: true, panelMuted: false, itemActive: false, itemMuted: true });
  assert.deepEqual([isActivationKey("Enter"), isActivationKey(" "), isActivationKey("ArrowRight")], [true, true, false]);
});

test("P2-F4 keeps transaction configuration source unit fact and evidence semantics explicit", () => {
  const rows = mockFinancedEquipment.lines.flatMap((line) => line.configuration.rows);
  assert.equal(rows.length > 0, true);
  for (const row of rows) {
    assert.equal(typeof row.sourceLabel, "string");
    assert.equal(row.sourceLabel.length > 0, true);
    assert.equal(typeof row.unit, "string");
    assert.equal(row.unit.length > 0, true);
    assert.equal(mockFacts.some((fact) => fact.id === row.factVersionId && fact.dimensionId === "transaction"), true);
    assert.equal(row.evidenceRefs.length > 0, true);
  }
});

test("P2-Gate keeps H-03 scope and evidence requirements identical across rule and shared chain", () => {
  const rule = mockHardConstraints.find((item) => item.ruleId === "H-03" && item.ruleVersion === "policy-2026.08");
  assert.ok(rule);
  const canonicalTargets = rule.evidenceTargets.map(({ evidenceRef, dimensionId, reviewTargetId, factVersionId }) => ({ evidenceRef, dimensionId, reviewTargetId, factVersionId }));
  assert.deepEqual(canonicalTargets.map((target) => target.evidenceRef), ["evidence-compliance-charter", "evidence-debt-zhongdeng"]);
  const h03Events = mockReviewEvents.filter((event) => event.ruleRefs.includes("H-03@policy-2026.08"));
  assert.equal(h03Events.length, 6);
  for (const event of h03Events) {
    assert.match(event.summary, new RegExp(rule.scope));
    assert.match(event.summary, new RegExp(rule.evidenceRequirement));
    assert.doesNotMatch(`${event.title}${event.summary}${event.evidenceRefs.join("|")}`, /个人涉诉/);
    assert.deepEqual(event.evidenceTargets.map(({ evidenceRef, dimensionId, reviewTargetId, factVersionId }) => ({ evidenceRef, dimensionId, reviewTargetId, factVersionId })), canonicalTargets);
    assert.deepEqual(event.evidenceRefs, event.evidenceTargets.map((target) => target.evidenceRef));
  }
  assert.equal(mockReviewEvents.some((event) => event.title.includes("个人涉诉") && event.ruleRefs.length === 0), true);
});

test("P2-Gate maps every debt anomaly evidence and collaboration reference to its exact target tuple", () => {
  const debt = mockGlobalRiskSummary.keyAnomalies.find((item) => item.id === "risk-anomaly-debt-registration");
  assert.deepEqual(debt.evidenceTargets.map(({ evidenceRef, reviewTargetId, factVersionId }) => ({ evidenceRef, reviewTargetId, factVersionId })), [
    { evidenceRef: "evidence-debt-credit", reviewTargetId: "debt-credit", factVersionId: "fact-debt-credit-v1" },
    { evidenceRef: "evidence-debt-loans", reviewTargetId: "debt-loans", factVersionId: "fact-debt-loans-v1" },
    { evidenceRef: "evidence-debt-zhongdeng", reviewTargetId: "debt-zhongdeng", factVersionId: "fact-debt-zhongdeng-v1" },
  ]);
  const event = mockReviewEvents.find((item) => item.id === "event-09-debt-evidence");
  assert.equal(reviewEvidenceTargetAt(event, 0).reviewTargetId, "debt-credit");
  assert.equal(reviewEvidenceTargetAt(event, 1).reviewTargetId, "debt-loans");
  assert.equal(reviewEvidenceTargetAt(event, 2).reviewTargetId, "debt-zhongdeng");
  assert.equal(reviewEvidenceTargetAt(event, 3), null);
  const sameEvidenceDifferentTarget = { ...event.evidenceTargets[0], reviewTargetId: "another-anchor" };
  assert.equal(sameReviewEvidenceTarget(event.evidenceTargets[0], sameEvidenceDifferentTarget), false);
});

test("P2-Gate locates every visible price and configuration value in the authoritative material", () => {
  const material = mockMaterials.find((item) => item.id === "material-financed-equipment");
  assert.ok(material && material.kind === "excel");
  const evidenceById = new Map(mockEvidence.map((item) => [item.id, item]));
  const factsById = new Map(mockFacts.map((item) => [item.id, item]));
  mockFinancedEquipment.lines.forEach((line, lineIndex) => {
    const benchmarkEvidence = evidenceById.get(line.priceBenchmark.evidenceRefs[0]);
    assert.equal(benchmarkEvidence.locator?.kind, "excel");
    assert.equal(benchmarkEvidence.locator?.sheet, "价格基准");
    const parsed = parseExcelRange(benchmarkEvidence.locator.range);
    const sheet = material.sheets.find((item) => item.name === "价格基准");
    const row = sheet.rows[parsed.startRow - 4];
    assert.deepEqual(row.slice(parsed.startColumn - 1, parsed.endColumn), [`${line.equipment} / ${line.model}`, line.priceBenchmark.unit, line.priceBenchmark.low, line.priceBenchmark.median, line.priceBenchmark.high, line.contractUnitPrice, line.priceBenchmark.sourceLabel]);
    assert.equal(parsed.startRow, lineIndex + 4);
    assert.equal(factsById.get(line.priceBenchmark.factVersionId)?.evidenceRefs.includes(benchmarkEvidence.id), true);
  });
  let configurationIndex = 0;
  for (const line of mockFinancedEquipment.lines) for (const rowContract of line.configuration.rows) {
    const reference = evidenceById.get(rowContract.evidenceRefs[0]);
    const parsed = parseExcelRange(reference.locator.range);
    const sheet = material.sheets.find((item) => item.name === "配置对比");
    const row = sheet.rows[parsed.startRow - 4];
    assert.deepEqual(row.slice(parsed.startColumn - 1, parsed.endColumn), [rowContract.label, rowContract.unit, rowContract.current, rowContract.median, rowContract.range, rowContract.sourceLabel]);
    assert.equal(parsed.startRow, configurationIndex + 4);
    assert.equal(factsById.get(rowContract.factVersionId)?.evidenceRefs.includes(reference.id), true);
    configurationIndex += 1;
  }
});

test("P2-Gate derives event compatibility projections and never invents a FactVersion for UI anchors", () => {
  const targets = [
    { evidenceRef: "same-evidence", dimensionId: "transaction", reviewTargetId: "down-payment", factVersionId: null },
    { evidenceRef: "same-evidence", dimensionId: "transaction", reviewTargetId: "financed", factVersionId: null },
  ];
  const seed = { ...mockReviewEvents[0], evidenceTargets: undefined, evidenceRefs: ["stale"], factVersionIds: ["fake-ui-id"], reviewTargetId: "stale" };
  const mapped = attachReviewEvidenceTargets(seed, targets);
  assert.deepEqual(mapped.evidenceRefs, ["same-evidence"]);
  assert.deepEqual(mapped.factVersionIds, []);
  assert.equal(mapped.reviewTargetId, "down-payment");
  assert.equal(sameReviewEvidenceTarget(mapped.evidenceTargets[0], mapped.evidenceTargets[1]), false);
});

test("P2-F5 aggregates absolute kWh/output with explicit unavailable and empty states", () => {
  assert.equal(productionSeriesStatus(mockProductionEnergy).status, "available");
  assert.equal(productionSeriesStatus({ ...mockProductionEnergy, status: "missing", points: [] }).status, "missing");
  assert.equal(productionSeriesStatus({ ...mockProductionEnergy, status: "invalid" }).status, "invalid");
  assert.equal(productionSeriesStatus({ ...mockProductionEnergy, status: "unavailable" }).status, "unavailable");
  assert.equal(productionSeriesStatus({ ...mockProductionEnergy, electricityUnit: "CNY" }).status, "invalid");
  assert.equal(productionSeriesStatus({ ...mockProductionEnergy, outputUnit: "件", electricityUnit: "kWh", aggregation: "sum", points: [] }).status, "missing");
  const month = aggregateProductionEnergy(mockProductionEnergy.points, "month");
  assert.equal(month.status, "available");
  assert.equal(month.points.length, 6);
  const quarter = aggregateProductionEnergy(mockProductionEnergy.points, "quarter");
  assert.equal(quarter.status, "available");
  assert.deepEqual(quarter.points.map((point) => [point.electricity, point.output]), [[55300, 32350], [62500, 37150]]);
  assert.equal(aggregateProductionEnergy(mockProductionEnergy.points, "week").status, "unavailable");
  assert.equal(aggregateProductionEnergy(mockProductionEnergy.points, "month", "2027-01-01", "2027-12-31").status, "empty");
  assert.equal(aggregateProductionEnergy(mockProductionEnergy.points, "month", "2026-06-01", "2026-01-01").status, "invalid");
  assert.equal(aggregateProductionEnergy([{ ...mockProductionEnergy.points[0], electricityEvidenceRefs: [] }], "month").status, "invalid");
});

test("clamps and persists only the permitted layout subset", () => {
  const saved = sanitizePersistedLayout({ ...baseLayout, materialWidth: 9999, collaborationHeight: 20, middleCollapsed: true, materialCollapsed: true, policyCollapsed: true, materialFullscreen: true, draft: "secret" }, baseLayout);
  assert.equal(saved.materialWidth, 960);
  assert.equal(saved.collaborationHeight, 140);
  assert.equal(saved.middleCollapsed, true);
  assert.equal(saved.materialCollapsed, true);
  assert.equal(saved.policyCollapsed, true);
  assert.equal("materialFullscreen" in saved, false);
  assert.equal("draft" in saved, false);
  assert.deepEqual(persistedLayoutFrom({ ...baseLayout, businessCollapsed: true, policyCollapsed: true, riskCollapsed: true }), sanitizePersistedLayout({ ...baseLayout, businessCollapsed: true, policyCollapsed: true, riskCollapsed: true }, baseLayout));
});

test("resolves Excel, PDF, image and evidence exceptions without approximate success", () => {
  const materials = [
    { id: "x", versionId: "x-v1", kind: "excel", fileName: "x.xlsx", label: "x", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", availability: "available", isSimulated: true, sourceLabel: "模拟", sheets: [{ name: "S", columns: ["A", "B"], rows: [[1, 2], [3, 4]] }] },
    { id: "p", versionId: "p-v1", kind: "pdf", fileName: "p.pdf", label: "p", mimeType: "application/pdf", availability: "available", isSimulated: true, sourceLabel: "模拟", pageCount: 1, pages: [{ page: 1, title: "P1", lines: ["模拟"] }] },
    { id: "i", versionId: "i-v1", kind: "image", fileName: "i.png", label: "i", mimeType: "image/png", availability: "available", isSimulated: true, sourceLabel: "模拟", pixelWidth: 10, pixelHeight: 10, description: "模拟", focalArea: { x: 0, y: 0, width: 1, height: 1 } },
  ];
  const located = { id: "e-x", label: "Excel", locator: { kind: "excel", materialId: "x", materialVersionId: "x-v1", sheet: "S", range: "A4:B5" }, locationStatus: "located", materialStatus: "confirmed" };
  assert.equal(resolveEvidence("e-x", [located], materials).status, "located");
  assert.equal(resolveEvidence("outside", [{ ...located, id: "outside", locator: { ...located.locator, range: "A4:B6" } }], materials).status, "invalid_locator");
  assert.equal(resolveEvidence("wrong-kind", [{ ...located, id: "wrong-kind", locator: { kind: "excel", materialId: "p", materialVersionId: "p-v1", sheet: "S", range: "A4:B4" } }], materials).status, "invalid_locator");
  assert.equal(resolveEvidence("pending", [{ ...located, id: "pending", locator: null, locationStatus: "pending" }], materials).status, "pending");
  assert.equal(resolveEvidence("mismatch", [{ ...located, id: "mismatch", locator: { ...located.locator, materialVersionId: "x-v0" }, locationStatus: "version_mismatch" }], materials).status, "version_mismatch");
  assert.equal(resolveEvidence("missing", [], materials).status, "missing_evidence");
  assert.deepEqual(materials.map((item) => item.kind), ["excel", "pdf", "image"]);
  for (const reference of mockEvidence.filter((item) => item.locationStatus === "located")) {
    assert.equal(resolveEvidence(reference.id, [reference], mockMaterials).status, "located", reference.id);
  }
  assert.equal(materialIdForEvidenceResolution(resolveEvidence("e-x", [located], materials)), "x");
  assert.equal(materialIdForEvidenceResolution(resolveEvidence("pending", [{ ...located, id: "pending", locator: null, locationStatus: "pending" }], materials)), "");
});

test("creates a new fact version and appends immutable review events", () => {
  const current = { id: "fact-v2", factKey: "subject.name", dimensionId: "compliance", version: 2, label: "名称", value: "旧值", unit: null, source: "mock_material_extract", evidenceRefs: ["e-1"], createdAt: "2026-01-01T00:00:00Z", isSimulated: true };
  const next = createCorrectedFact(current, { projectId: "p", factKey: current.factKey, fromFactVersionId: current.id, proposedValue: "新值", reason: "人工核对", evidenceRefs: ["e-1"] }, 3);
  assert.equal(next.version, 3);
  assert.equal(next.value, "新值");
  assert.equal(next.source, "mock_business_correction");

  const event = { id: "e", projectId: "p", sequence: 0, eventType: "fact_version_created", actor: "system", actorLabel: "系统", title: "事实", summary: "模拟", factVersionIds: [next.id], evidenceRefs: ["e-1"], createdAt: "2026-01-01T00:00:00Z", immutable: true, isSimulated: true };
  assert.equal(appendImmutableEvent([{ ...event, id: "old", sequence: 4 }], event)[0].sequence, 5);
});

test("keeps hard constraints separate from advisory soft recommendations and gateway local", async () => {
  const root = new URL("../", import.meta.url);
  const [contract, gateway, app] = await Promise.all([
    readFile(new URL("src/contracts/workbench.ts", root), "utf8"),
    readFile(new URL("src/gateway/mockWorkbenchGateway.ts", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
  ]);
  assert.match(contract, /result:\s*"pass" \| "block" \| "manual_review"/);
  assert.match(contract, /advisoryOnly:\s*true/);
  assert.doesNotMatch(gateway, /\bfetch\s*\(/);
  assert.doesNotMatch(app, /\bfetch\s*\(/);
  assert.match(gateway, /simulated_failure/);
});
