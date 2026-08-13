import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { DIMENSION_IDS } from "../src/contracts/workbench.ts";
import {
  mockDimensionDetails,
  mockDimensions,
  mockEvidence,
  mockFacts,
  mockGlobalRiskSummary,
  mockWorkbenchProject,
} from "../src/mock/mockCase.ts";

const expectedDimensionIds = ["compliance", "transaction", "production", "revenue", "debt", "cashflow"];
const expectedDimensionNames = ["合规", "交易", "生产", "营收", "负债", "流水"];

test("keeps risk global and preserves the six-dimension order", () => {
  assert.deepEqual(DIMENSION_IDS, expectedDimensionIds);
  assert.deepEqual(mockDimensions.map((item) => item.id), expectedDimensionIds);
  assert.deepEqual(mockDimensionDetails.map((item) => item.dimensionId), expectedDimensionIds);
  assert.deepEqual(mockDimensions.map((item) => item.name), expectedDimensionNames);
  assert.deepEqual(mockDimensions.map((item) => item.fullName), expectedDimensionNames);
  assert.equal(mockGlobalRiskSummary.name, "风险");
  assert.equal(mockWorkbenchProject.riskSummary, mockGlobalRiskSummary);
  assert.equal(mockDimensions.some((item) => item.id === "risk" || item.name === "风险"), false);
  assert.equal(mockDimensionDetails.some((item) => item.dimensionId === "risk"), false);
  assert.equal([mockGlobalRiskSummary.name, ...expectedDimensionNames].every((name) => [...name].length === 2), true);
});

test("maps frozen business categories without excluded standalone columns", () => {
  const labelsByDimension = Object.fromEntries(
    mockDimensionDetails.map((detail) => [detail.dimensionId, detail.breakdown.map((item) => item.label)]),
  );

  assert.deepEqual(labelsByDimension.compliance, ["营业执照", "身份证", "章程", "外部工商", "主体涉诉", "个人涉诉"]);
  assert.deepEqual(labelsByDimension.transaction, []);
  assert.deepEqual(labelsByDimension.production, []);
  assert.deepEqual(labelsByDimension.revenue, ["收入", "订单", "发票", "经营表现"]);
  assert.deepEqual(labelsByDimension.debt, ["征信", "借款", "中登", "担保", "其他偿债义务"]);
  assert.deepEqual(labelsByDimension.cashflow, ["收支真实性", "经营匹配", "异常流水"]);
  assert.deepEqual(mockFacts.filter((item) => item.dimensionId === "compliance").map((item) => item.label), labelsByDimension.compliance);

  const businessHeadings = new Set([mockGlobalRiskSummary.name, ...expectedDimensionNames, ...Object.values(labelsByDimension).flat()]);
  for (const excluded of ["五选二", "后续风险关注", "OCR", "房产", "车辆", "项目"]) {
    assert.equal(businessHeadings.has(excluded), false);
  }
});

test("keeps five-color risk semantics separate from material recognition status", async () => {
  const root = new URL("../", import.meta.url);
  const [contract, tokens] = await Promise.all([
    readFile(new URL("src/contracts/workbench.ts", root), "utf8"),
    readFile(new URL("src/styles/tokens.css", root), "utf8"),
  ]);

  assert.match(contract, /RiskLevel = "support" \| "attention" \| "confirm" \| "risk" \| "forbid"/);
  assert.match(contract, /LocalMaterialStatus = "confirmed" \| "review" \| "conflict"/);
  assert.match(contract, /GlobalRiskSummary[\s\S]*level:\s*RiskLevel/);
  assert.match(contract, /EvidenceReference[\s\S]*materialStatus:\s*LocalMaterialStatus/);

  for (const [name, color] of Object.entries({
    support: "#22c55e",
    attention: "#2563eb",
    confirm: "#f59e0b",
    risk: "#dc2626",
    forbid: "#7c3aed",
  })) {
    assert.match(tokens, new RegExp(`--risk-${name}: ${color}`));
  }

  const recognitionStatuses = new Set(mockEvidence.map((item) => item.materialStatus));
  assert.deepEqual([...recognitionStatuses].sort(), ["confirmed", "conflict", "review"]);
  assert.equal(recognitionStatuses.has(mockGlobalRiskSummary.level), false);
});

test("uses metrics, series and breakdown as the only dual-view sources", () => {
  const evidenceIds = new Set(mockEvidence.map((item) => item.id));

  for (const detail of mockDimensionDetails) {
    assert.equal(detail.defaultView, "visual");
    assert.deepEqual(detail.availableViews, ["transaction", "production"].includes(detail.dimensionId) ? ["visual"] : ["visual", "table"]);
    assert.equal(new Set(detail.availableViews).size, detail.availableViews.length);
    assert.equal(detail.breakdown.length > 0, !["transaction", "production"].includes(detail.dimensionId));
    assert.equal(Object.hasOwn(detail, "tableRows"), false);
    assert.equal(Object.hasOwn(detail, "tableData"), false);

    const viewItems = [...detail.metrics, ...detail.series, ...detail.breakdown];
    assert.equal(new Set(viewItems.map((item) => item.id)).size, viewItems.length);

    for (const item of [...detail.metrics, ...detail.breakdown]) {
      assert.equal(item.evidenceRefs.length > 0, true, `${detail.dimensionId}/${item.id} must keep evidence refs`);
      for (const evidenceId of item.evidenceRefs) {
        assert.equal(evidenceIds.has(evidenceId), true, `${detail.dimensionId}/${item.id} references missing ${evidenceId}`);
      }
    }
    for (const point of detail.series) {
      assert.equal(Object.hasOwn(point, "primary") || Object.hasOwn(point, "secondary") || Object.hasOwn(point, "tertiary"), false);
      assert.equal(point.measures.length > 0, true, `${detail.dimensionId}/${point.id} must keep named measures`);
      for (const measure of point.measures) {
        assert.equal(measure.evidenceRefs.length > 0, true, `${detail.dimensionId}/${measure.id} must keep evidence refs`);
        for (const evidenceId of measure.evidenceRefs) assert.equal(evidenceIds.has(evidenceId), true, `${detail.dimensionId}/${measure.id} references missing ${evidenceId}`);
        for (const evidenceId of measure.comparisonEvidenceRefs ?? []) assert.equal(evidenceIds.has(evidenceId), true, `${detail.dimensionId}/${measure.id} references missing comparison ${evidenceId}`);
      }
    }
  }

  const pendingEvidence = mockEvidence.filter((item) => item.id.startsWith("evidence-") && item.locationStatus === "pending");
  assert.equal(pendingEvidence.length > 0, true);
  assert.equal(pendingEvidence.every((item) => item.locator === null && item.materialStatus === "review"), true);
  const riskEvidenceRefs = [
    ...mockGlobalRiskSummary.evidenceRefs,
    ...mockGlobalRiskSummary.keyAnomalies.flatMap((item) => item.evidenceTargets.map((target) => target.evidenceRef)),
    ...mockGlobalRiskSummary.pendingHumanDeterminations.flatMap((item) => item.evidenceTargets.map((target) => target.evidenceRef)),
    ...mockGlobalRiskSummary.hardConstraintResults.flatMap((item) => item.evidenceTargets.map((target) => target.evidenceRef)),
  ];
  assert.equal(riskEvidenceRefs.every((evidenceId) => evidenceIds.has(evidenceId)), true);
  assert.equal(mockDimensionDetails.every((item) => item.isSimulated), true);
  assert.equal(mockGlobalRiskSummary.isSimulated, true);
  assert.match(mockWorkbenchProject.project.disclaimer, /演示模拟/);
});
