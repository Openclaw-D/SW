import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { mockDimensionDetails, mockReviewEvents } from "../src/mock/mockCase.ts";

const root = new URL("../", import.meta.url);

test("P2-Control keeps transaction and production on their dedicated single sources", async () => {
  const detailView = await readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8");
  const transaction = mockDimensionDetails.find((detail) => detail.dimensionId === "transaction");
  const production = mockDimensionDetails.find((detail) => detail.dimensionId === "production");
  for (const detail of [transaction, production]) {
    assert.deepEqual(detail.availableViews, ["visual"]);
    assert.deepEqual(detail.metrics, []);
    assert.deepEqual(detail.series, []);
    assert.deepEqual(detail.breakdown, []);
  }
  assert.match(detailView, /dimension\.id === "transaction" && financedEquipment/);
  assert.match(detailView, /dimension\.id === "production" && operatingEquipment && productionEnergy && productionStages/);
  assert.doesNotMatch(detailView, /EquipmentLedgerPanel|生产设备报价表/);
});

test("P2-Control uses an exact review target tuple in every new evidence surface", async () => {
  const files = await Promise.all([
    "TransactionWorkspace.tsx",
    "FinancedEquipmentPanel.tsx",
    "ProductionEnergyChart.tsx",
    "ProductionStagesPanel.tsx",
    "ComplianceSubjectGraph.tsx",
  ].map((name) => readFile(new URL(`src/components/${name}`, root), "utf8")));
  for (const source of files) {
    assert.match(source, /ReviewEvidenceTarget/);
    assert.match(source, /sameReviewEvidenceTarget/);
    assert.doesNotMatch(source, /selectedEvidenceId/);
  }
  assert.match(files[0], /transaction-finance-down-payment/);
  assert.match(files[0], /transaction-finance-financed/);
  assert.match(files[2], /\$\{point\.id\}-electricity/);
  assert.match(files[2], /\$\{point\.id\}-output/);
});

test("P2-Control exposes every shared event material as an independent native button", async () => {
  const dock = await readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8");
  assert.match(dock, /item\.evidenceTargets\.map\(\(target, index\)/);
  assert.match(dock, /onEvidenceActivate\(target\)/);
  assert.match(dock, /key=\{`\$\{item\.id\}-\$\{target\.evidenceRef\}-\$\{index\}`\}/);
  assert.match(dock, /type="button"/);
  const threeEvidenceEvent = mockReviewEvents.find((event) => event.id === "event-09-debt-evidence");
  assert.deepEqual(threeEvidenceEvent.evidenceTargets.map((target) => target.reviewTargetId), ["debt-credit", "debt-loans", "debt-zhongdeng"]);
});

test("P2-Control keeps exactly six dimension controls plus one overview control inside the dial", async () => {
  const navigation = await readFile(new URL("src/components/NavigationRail.tsx", root), "utf8");
  assert.match(navigation, /className=\{`wedge-hit/);
  assert.match(navigation, /className="dimension-axis-icon"/);
  assert.doesNotMatch(navigation, /dimension-dial-grade/);
  assert.match(navigation, /className=\{`dial-score detail-dial-back/);
});

test("P2-Control terminates graph and model pointer sessions on cancel, lost capture and window blur", async () => {
  const [graph, model] = await Promise.all([
    readFile(new URL("src/components/ComplianceSubjectGraph.tsx", root), "utf8"),
    readFile(new URL("src/components/EquipmentModelPreview.tsx", root), "utf8"),
  ]);
  for (const source of [graph, model]) {
    assert.match(source, /onPointerCancel=/);
    assert.match(source, /onLostPointerCapture=/);
    assert.match(source, /window\.addEventListener\("blur"/);
    assert.match(source, /terminatePointerSession/);
  }
});

test("P2-Control enforces readable auxiliary text and discernible graph muted state", async () => {
  const [styles, tokens] = await Promise.all([
    readFile(new URL("src/styles/app.css", root), "utf8"),
    readFile(new URL("src/styles/tokens.css", root), "utf8"),
  ]);
  assert.match(tokens, /--font-size-xs:\s*12px/);
  assert.match(styles, /\.dimension-context\s*\{[^}]*font-size:\s*12px/s);
  assert.match(styles, /\.dimension-context small\s*\{[^}]*font-size:\s*12px/s);
  const muted = styles.match(/\.graph-subject-node\.is-dimmed\s*\{\s*opacity:\s*([\d.]+)/);
  assert.ok(muted);
  assert.equal(Number(muted[1]) >= 0.45, true);
  assert.doesNotMatch(styles, /font-size:\s*(?:8|9|10|11)px/);
});
