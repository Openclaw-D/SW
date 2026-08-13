import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import test from "node:test";
import { mockComplianceGraph, mockDimensionDetails, mockEvidence, mockFacts, mockGlobalRiskSummary, mockHardConstraints, mockMaterials, mockOnsiteAssets, mockReviewEvents, mockWorkbenchProject } from "../src/mock/mockCase.ts";
import { mockFinancedEquipment, mockOperatingEquipment, mockProductionEnergy, mockProductionStages, mockReferenceImages } from "../src/mock/p2Content.ts";
import { calculateFinancedEquipmentLedger, excelRangeContains, excelRangeScrollTarget, parseExcelRange } from "../src/lib/workbenchLogic.ts";
import { dialState } from "../src/lib/navigationRailState.ts";

const root = new URL("../", import.meta.url);

test("R2 wires one risk-plus-six review state without turning risk into a dimension", async () => {
  const [app, review, navigation] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/NavigationRail.tsx", root), "utf8"),
  ]);
  assert.match(app, /activeReviewId/);
  assert.match(app, /onActiveReviewChange/);
  assert.match(review, /ReviewSectionId = "risk" \| DimensionId/);
  assert.match(review, /<RiskSection[\s\S]*<ComplianceSection/);
  assert.doesNotMatch(review, /识别状态与风险五色分别表达/);
  assert.match(navigation, /riskActive/);
  assert.equal(mockDimensionDetails.length, 6);
  assert.equal(mockGlobalRiskSummary.name, "风险");
});

test("R3 uses the same metrics series and breakdown for planar and table interactions", async () => {
  const source = await readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8");
  assert.match(source, /平面/);
  assert.match(source, /表格/);
  assert.match(source, /PlanarVisual/);
  assert.doesNotMatch(source, /tableRows|tableData/);
  for (const visual of ["transaction-structure", "production-series", "debt-structure", "cashflow-series"]) assert.match(source, new RegExp(`"${visual}"`));
  assert.deepEqual(new Set(mockDimensionDetails.map((detail) => detail.visual)), new Set(["subject-network", "transaction-structure", "production-series", "revenue-series", "debt-structure", "cashflow-series"]));
  for (const detail of mockDimensionDetails) {
    assert.deepEqual(detail.availableViews, ["transaction", "production"].includes(detail.dimensionId) ? ["visual"] : ["visual", "table"]);
    assert.equal(detail.defaultView, "visual");
    assert.equal(detail.breakdown.every((item) => item.evidenceRefs.length > 0), true);
  }
});

test("R4 keeps precise locators and explicit unresolved states without approximate success", async () => {
  const materialPane = await readFile(new URL("src/components/MaterialPane.tsx", root), "utf8");
  const located = mockEvidence.filter((item) => item.locationStatus === "located");
  const unresolved = mockEvidence.filter((item) => item.locationStatus !== "located");
  assert.equal(located.length >= 20, true);
  assert.equal(located.every((item) => item.locator !== null), true);
  assert.equal(unresolved.some((item) => item.locationStatus === "pending"), true);
  assert.equal(unresolved.some((item) => item.locationStatus === "unverifiable"), true);
  assert.equal(unresolved.filter((item) => item.locator === null).length > 0, true);
  assert.match(materialPane, /旧高亮已清除/);
  assert.match(materialPane, /displayHitCount.*个区域/s);
  assert.match(materialPane, /现场原图待接入/);
  assert.doesNotMatch(materialPane, /选择中间数据可后台定位/);
  assert.deepEqual(new Set(mockMaterials.map((item) => item.kind)), new Set(["excel", "pdf", "image", "media", "scene"]));
  assert.equal(mockMaterials.filter((item) => item.kind === "image").every((item) => item.mimeType === "image/png"), true);
});

test("R7 maps Excel locators to stable highlighted cells and internal scroll targets", async () => {
  const materialPane = await readFile(new URL("src/components/MaterialPane.tsx", root), "utf8");
  for (const row of [4, 10, 19, 22]) {
    const range = `C${row}:E${row}`;
    assert.deepEqual(parseExcelRange(range), { startColumn: 3, endColumn: 5, startRow: row, endRow: row });
    assert.deepEqual(excelRangeScrollTarget(range), { column: 3, row });
    assert.equal(excelRangeContains(range, 3, row), true);
    assert.equal(excelRangeContains(range, 5, row), true);
    assert.equal(excelRangeContains(range, 2, row), false);
  }
  assert.equal(parseExcelRange("not-a-range"), null);
  assert.match(materialPane, /scrollContainerRef/);
  assert.match(materialPane, /rowContentTop/);
  assert.doesNotMatch(materialPane, /scrollIntoView/);
});

test("R5 keeps formal corrections separate while Agent dialogue stays advisory-only", async () => {
  const [dock, review, top] = await Promise.all([
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/TopBar.tsx", root), "utf8"),
  ]);
  for (const text of ["业务修正", "显式 synthetic 开发模式", "协作事实流", "正式制度 Gate", "真实 Provider 输出仍是 advisory-only"]) assert.match(dock, new RegExp(text));
  assert.doesNotMatch(review, /CorrectionPanel|提交修正/);
  for (const text of ["global-approval-actions", "暂存", "退回", "提交", "完成", "制度 Gate 未解除"]) assert.match(top, new RegExp(text));
  assert.doesNotMatch(dock, /approval-actions/);
});

test("R8-1 keeps two optional-context Agent dialogues around one traceable shared stream", async () => {
  const [dock, top, app, gateway] = await Promise.all([
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/components/TopBar.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/gateway/mockWorkbenchGateway.ts", root), "utf8"),
  ]);
  for (const text of ["制度认知 / 协作事实流", "左右普通草稿不自动进入", "可不引用材料、维度或历史条目", "正式制度 Gate", "未确定 / 下一步"]) {
    assert.match(dock, new RegExp(text));
  }
  assert.match(dock, /const label = business \? "业务" : "风控"/);
  assert.match(dock, /`用户 × \$\{label\} Agent`/);
  assert.match(dock, /messages\.filter\(\(message\) => message\.role === actor\)\.sort/);
  assert.match(dock, /buildCollaborationStream\(events, agentMessages, focusEvents\)/);
  assert.equal((dock.match(/<Composer actor=/g) ?? []).length, 1);
  assert.doesNotMatch(dock, /submitPolicy|policy.*Composer/i);
  assert.deepEqual([...mockReviewEvents].sort((a, b) => a.sequence - b.sequence).map((event) => event.sequence), [1, 2, 3, 4, 5, 6, 7, 8, 9]);
  assert.equal(new Set(mockReviewEvents.map((event) => event.sequence)).size, mockReviewEvents.length);
  assert.equal(mockReviewEvents.some((event) => event.actor === "business" && event.eventType === "business_answer_submitted"), true);
  assert.equal(mockReviewEvents.some((event) => event.actor === "risk" && event.eventType === "risk_answer_submitted"), true);
  assert.equal(mockReviewEvents.filter((event) => event.actor === "system").every((event) => Array.isArray(event.ruleRefs)), true);
  assert.equal(mockReviewEvents.every((event) => event.evidenceTargets.every((target) => target.factVersionId === null || mockFacts.some((fact) => fact.id === target.factVersionId))), true);
  assert.deepEqual([...mockReviewEvents].filter((event) => event.ruleRefs.includes("H-03@policy-2026.08")).sort((a, b) => a.sequence - b.sequence).map((event) => event.replyToEventId), ["event-01", "event-02", "event-03", "event-04", "event-05", "event-06"]);
  assert.equal(mockHardConstraints.every((rule) => rule.scope && rule.evidenceRequirement && rule.nextAction), true);
  assert.match(app, /selectedReviewTarget/);
  assert.match(app, /evidenceSelectionGroup\?\.dimensionId === layout\.activeDimensionId/);
  assert.doesNotMatch(app, /currentDimensionFacts\.slice\(0, 1\)/);
  assert.match(app, /gateway\.executeAgentTurn/);
  assert.match(app, /replyToMessageId: referencedMessage\?\.id \?\? null/);
  assert.match(gateway, /async executeAgentTurn/);
  assert.match(top, /unresolvedGateCount/);
  assert.match(top, /制度 Gate 未解除/);
  assert.match(top, /disabled=\{completionBlocked\}/);
});

test("P4 uses one derived grade color for navigation sectors, icons, bars and letters", async () => {
  const [navigation, icons, mock, styles, tokens] = await Promise.all([
    readFile(new URL("src/components/NavigationRail.tsx", root), "utf8"),
    readFile(new URL("src/components/icons.tsx", root), "utf8"),
    readFile(new URL("src/mock/mockCase.ts", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
    readFile(new URL("src/styles/tokens.css", root), "utf8"),
  ]);
  assert.match(navigation, /visual: deriveScoreVisual\(dimension\.score\)/);
  assert.match(navigation, /--sector-color": visual\.colorVar/);
  assert.match(navigation, /--score-color": visual\.colorVar/);
  assert.doesNotMatch(navigation, /dimensionColorVar|--icon-color|--dimension-color/);
  assert.match(styles, /\.dimension-grade\s*\{[^}]*color:\s*var\(--score-color\)/);
  for (const id of ["compliance", "transaction", "production", "revenue", "debt", "cashflow"]) assert.match(icons, new RegExp(`${id}:\\s*"var\\(--dimension-${id}\\)"`));
  assert.match(mock, /mockDimensionSeeds[\s\S]*scoreGrade: scoreToGrade\(dimension\.score\)/);
  assert.doesNotMatch(mock, /score:\s*\d+,[^\n]*scoreGrade:\s*"[A-E]"/);
  assert.match(icons, /M4\.5 20\.5V7\.5h9v13/);
  assert.match(icons, /M5 3\.5h8l4 4v5/);
  assert.match(navigation, /import \{ dialState \} from "\.\.\/lib\/navigationRailState"/);
  assert.equal(dialState(0, null, -1), "");
  assert.equal(dialState(1, null, 1), "is-current");
  assert.equal(dialState(0, null, 1), "is-dimmed");
  assert.match(styles, /\.direction-corridor \{ width: 170%; height: 170%/);
  assert.match(styles, /\.direction-corridor \{[^}]*pointer-events: none/);
  assert.doesNotMatch(tokens, /--risk-(?:confirmed|review|conflict|manual)/);
  for (const token of ["--material-confirmed", "--material-review", "--material-conflict", "--evidence-pending", "--actor-business", "--actor-risk", "--policy-gate"]) assert.match(tokens, new RegExp(token));
});

test("P3 canvas keeps five ordered risk cards above one shared detail and uses explicit primary targets", async () => {
  const [review, styles] = await Promise.all([
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(review, /groupRiskItems\(summary\)/);
  assert.match(review, /riskLevelMeta\.flatMap/);
  assert.match(review, /orderedGroups\.map/);
  assert.deepEqual([...review.matchAll(/id:\s*"(forbid|risk|confirm|attention|support)"/g)].map((match) => match[1]), ["forbid", "risk", "confirm", "attention", "support"]);
  assert.match(review, /evidenceTargets\.map/);
  assert.match(review, /item\.primaryTarget/);
  assert.match(review, /activateItem\(item, item\.primaryTarget\)/);
  assert.doesNotMatch(review, /item\.evidenceTargets\[0\]/);
  assert.match(review, /const \[expandedRiskLevel, setExpandedRiskLevel\] = useState<RiskLevel \| null>\(null\)/);
  assert.match(review, /aria-controls=\{panelId\}/);
  assert.match(review, /aria-expanded=\{expanded\}/);
  assert.match(review, /onPointerEnter=\{\(\) => setActiveRiskLevel\(group\.level\)\}/);
  assert.match(review, /onPointerLeave=\{\(\) => setActiveRiskLevel\(null\)\}/);
  assert.match(review, /toggledRiskLevel\(current, group\.level, group\.items\.length\)/);
  assert.match(review, /className="risk-level-cards"/);
  assert.match(review, /const expandedGroup = orderedGroups\.find/);
  assert.match(review, /risk-level-detail[\s\S]*expandedGroup\.items\.map/);
  assert.ok(review.indexOf('className="risk-level-cards"') < review.indexOf("risk-level-detail"));
  assert.doesNotMatch(review, /硬性阻断|限制条件|人工认定|持续观察|事实支持/);
  assert.doesNotMatch(review, /risk-summary-strip|risk-disclaimer|本级无项目|选择并定位/);
  assert.match(review, /<h1 className="visually-hidden"[^>]*>\{copy\(locale, "Risk", "风险"\)\}<\/h1>/);
  assert.match(review, /selectedTarget/);
  assert.doesNotMatch(review, /activeRiskItemId/);
  assert.match(styles, /\.risk-row\s*\{[\s\S]*grid-template-columns:[^;]+;/);
  assert.match(styles, /--risk-row-color/);
  assert.match(styles, /\.risk-evidence-links > button/);
  assert.match(styles, /#review-risk \.risk-level-card\.is-dimmed \{ opacity: \.42; filter: saturate\(\.45\); \}/);
  assert.match(styles, /#review-risk \.risk-level-cards \{[^}]*grid-template-columns:\s*repeat\(5, minmax\(0, 1fr\)\)/s);
  assert.match(styles, /#review-risk \.risk-level-card\.is-dimmed/);
  assert.match(styles, /#review-risk \.risk-level-card\.is-expanded svg[^}]*rotate\(90deg\)/);
  for (const [level, color] of [["forbid", "#7c3aed"], ["risk", "#dc2626"], ["confirm", "#f59e0b"], ["attention", "#2563eb"], ["support", "#22c55e"]]) {
    assert.match(styles, new RegExp(`#review-risk \\.risk-level-${level} \\{ --risk-group-color: ${color}; \\}`));
    assert.equal(styles.split(/\r?\n/).filter((line) => line.includes(color)).every((line) => line.trim().startsWith("#review-risk") || line.trim().startsWith(".review-canvas :is(.transaction-price-range")), true, color);
  }
  assert.match(styles, /\.review-canvas :is\(\.transaction-price-range, \.transaction-repayment-panel, \.revenue-coverage-relation\)/);
  for (const item of [...mockGlobalRiskSummary.keyAnomalies, ...mockGlobalRiskSummary.pendingHumanDeterminations]) {
    assert.ok(item.responsibleParty);
    assert.ok(item.nextAction);
    assert.equal(item.evidenceTargets.length > 0, true);
    assert.ok(item.primaryTarget);
  }
});

test("P2-F3 keeps one normalized draggable 2-company 3-person graph with stable endpoints and honest evidence states", async () => {
  const [review, graphView] = await Promise.all([
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/ComplianceSubjectGraph.tsx", root), "utf8"),
  ]);
  assert.match(graphView, /2 家公司与 3 名自然人主体关系图谱/);
  assert.match(graphView, /graph\.relations\.map/);
  assert.match(graphView, /graph\.attachments\.filter/);
  assert.match(graphView, /setPointerCapture/);
  assert.match(graphView, /shortestRelationshipPath/);
  assert.match(graphView, /恢复默认布局/);
  assert.match(graphView, /selectedSubjectIds\.length \? <aside className="relationship-inspector"/);
  assert.doesNotMatch(graphView, /尚未选择主体|先选起点，再选终点/);
  assert.match(graphView, /relationshipEdgePoints/);
  assert.match(graphView, /sharePercent/);
  assert.match(graphView, /subject-inspector-materials/);
  assert.doesNotMatch(graphView, /subject-material-matrix/);
  assert.match(review, /<ComplianceSubjectGraph/);
  assert.match(review, /hidden=\{view !== "visual"\}[\s\S]*hidden=\{view !== "table"\}/);
  assert.equal(mockComplianceGraph.nodes.filter((node) => node.kind === "company").length, 2);
  assert.equal(mockComplianceGraph.nodes.filter((node) => node.kind === "person").length, 3);
  const nodeIds = new Set(mockComplianceGraph.nodes.map((node) => node.id));
  const evidenceById = new Map(mockEvidence.map((item) => [item.id, item]));
  const materialById = new Map(mockMaterials.map((item) => [item.id, item]));
  const factIds = new Set(mockFacts.map((fact) => fact.id));
  for (const relation of mockComplianceGraph.relations) {
    assert.equal(nodeIds.has(relation.fromId), true);
    assert.equal(nodeIds.has(relation.toId), true);
  }
  const liShareholding = mockComplianceGraph.relations.find((relation) => relation.id === "relation-li-borrower");
  assert.equal(liShareholding?.fromId, "subject-person-li");
  assert.equal(liShareholding?.toId, "subject-company-borrower");
  assert.equal(liShareholding?.sharePercent, 10);
  assert.deepEqual(mockComplianceGraph.relations.filter((relation) => relation.relation === "shareholding").map((relation) => relation.sharePercent), [90, 10]);
  assert.doesNotMatch(graphView, /节点、关系与材料均可定位/);
  for (const attachment of mockComplianceGraph.attachments) {
    assert.equal(nodeIds.has(attachment.subjectId), true);
    assert.equal(factIds.has(attachment.factVersionId), true);
  }
  for (const refId of [...mockComplianceGraph.nodes, ...mockComplianceGraph.relations, ...mockComplianceGraph.attachments].flatMap((item) => item.evidenceRefs)) {
    const reference = evidenceById.get(refId);
    assert.ok(reference, `missing evidence ${refId}`);
    if (reference.locationStatus === "located") {
      assert.ok(reference.locator);
      const material = materialById.get(reference.locator.materialId);
      assert.ok(material);
      if (reference.locator.kind === "excel") {
        const sheet = material.sheets.find((item) => item.name === reference.locator.sheet);
        assert.ok(sheet);
        const range = parseExcelRange(reference.locator.range);
        assert.ok(range);
        assert.equal(range.startRow >= 4 && range.endRow <= sheet.rows.length + 3, true);
      }
    } else {
      assert.equal(reference.locator, null);
    }
  }
});

test("P2 canvas keeps transaction, production and generic dimensions as responsive information boards", async () => {
  const [detail, transaction, equipment, stages, onsite, styles] = await Promise.all([
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/components/TransactionWorkspace.tsx", root), "utf8"),
    readFile(new URL("src/components/FinancedEquipmentPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/ProductionStagesPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/ProductionOnsitePanel.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(detail, /dimension-information-board/);
  assert.match(detail, /production-dashboard/);
  assert.doesNotMatch(detail, /detail\.metrics\.map/);
  assert.match(detail, /<ProductionOnsitePanel[\s\S]*<ProductionStagesPanel/);
  assert.doesNotMatch(detail, /onsite-assets-details/);
  assert.match(transaction, /<summary><strong>\{copy\(locale, "Full parameter comparison", "完整参数对比"\)\}/);
  assert.match(equipment, /financed-equipment-primary-image/);
  assert.match(equipment, /financed-equipment-ledger-details/);
  assert.match(onsite, /operating-equipment-cards/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed \.review-canvas:not\(\.is-collapsed\) \.dimension-section \{ max-width: none; \}/);
  assert.match(styles, /@container \(min-width: 1080px\)/);
  assert.match(styles, /\.transaction-workspace \{ grid-template-columns:/);
  assert.match(styles, /\.production-dashboard \{ grid-template-columns:/);
  assert.match(styles, /\.production-stage-main img \{ object-fit:\s*contain/);
  assert.match(styles, /\.financed-equipment-primary-image img \{[^}]*object-fit:\s*contain/s);
});

test("P2-F4 keeps financed equipment contracts in transaction and operating equipment in production", async () => {
  const [view, review, transaction, production] = await Promise.all([
    readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/FinancedEquipmentPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/ProductionOnsitePanel.tsx", root), "utf8"),
  ]);
  assert.match(view, /dimension\.id === "transaction"[\s\S]*<TransactionWorkspace/);
  assert.match(view, /dimension\.id === "production"[\s\S]*<ProductionStagesPanel/);
  assert.doesNotMatch(view, /EquipmentLedgerPanel|equipmentLedger/);
  for (const label of ["合同单价 / 合价", "供应商 / 报价", "可比价 / 差异", "对应材料"]) assert.match(transaction, new RegExp(label));
  for (const label of ["现场设备事实", "额定产能", "工艺使用"]) assert.match(production, new RegExp(label));
  assert.doesNotMatch(production, /contractUnitPrice|supplierQuoteSource|priceBenchmark/);
  assert.match(review, /financedEquipment=\{dimension\.id === "transaction"/);
  assert.match(review, /operatingEquipment=\{dimension\.id === "production"/);
  const evidenceById = new Map(mockEvidence.map((item) => [item.id, item]));
  const calculated = calculateFinancedEquipmentLedger(mockFinancedEquipment);
  assert.equal(calculated.contractTotal, 2_740_000);
  for (const line of mockFinancedEquipment.lines) {
    assert.equal(line.quantity > 0, true);
    assert.equal(line.contractUnitPrice > 0, true);
    const reference = evidenceById.get(line.contractEvidenceRefs[0]);
    assert.equal(reference?.locationStatus, "located");
    assert.equal(reference?.locator?.kind, "excel");
    assert.equal(reference?.locator?.sheet, "合同设备");
  }
  const totalReference = evidenceById.get(mockFinancedEquipment.totalContractEvidenceRefs[0]);
  assert.equal(totalReference?.locationStatus, "located");
  assert.equal(totalReference?.locator?.range, "D7:J7");
  assert.equal(mockOperatingEquipment.every((item) => !Object.hasOwn(item, "contractUnitPrice")), true);
});

test("P2-F5 keeps public references separate while production stages consume project originals", async () => {
  const [stageView, energyView, gallery, p2Data] = await Promise.all([
    readFile(new URL("src/components/ProductionStagesPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/ProductionEnergyChart.tsx", root), "utf8"),
    readFile(new URL("src/components/ReferenceImageGallery.tsx", root), "utf8"),
    readFile(new URL("src/mock/p2Content.ts", root), "utf8"),
  ]);
  assert.deepEqual(mockProductionStages.map((stage) => stage.stage), ["raw-material", "process", "finished-product"]);
  assert.equal(mockProductionEnergy.electricityUnit, "kWh");
  assert.equal(mockProductionEnergy.outputMetric, "absolute");
  assert.match(energyView, /production-output-line/);
  assert.match(energyView, /周不可用/);
  assert.doesNotMatch(energyView, /利润率对比不可用/);
  assert.match(energyView, /production-evidence-summary/);
  assert.match(stageView, /cleanVisualFileName\(image\.fileName\)/);
  assert.doesNotMatch(stageView, /公开参考图|非本项目客户现场|alt=\{`[^`]*脱敏模拟/);
  assert.match(gallery, /不参与风险事实认定/);
  assert.doesNotMatch(gallery, /role="listitem"/);
  assert.equal(mockReferenceImages.length, 7);
  assert.equal(mockReferenceImages.every((image) => image.src.startsWith("/reference-images/") && image.isEvidence === false), true);
  assert.doesNotMatch(p2Data, /src:\s*"https?:\/\//);
  const sources = JSON.parse(await readFile(new URL("public/reference-images/sources.json", root), "utf8"));
  assert.equal(sources.length, 7);
  assert.equal(sources.every((source) => source.isEvidence === false && source.originUrl.startsWith("https://commons.wikimedia.org/")), true);
  for (const image of mockReferenceImages) {
    const file = new URL(`public${image.src}`, root);
    assert.equal((await stat(file)).size > 10_000, true, image.src);
  }
});

test("R8-6 gives every semantic chart point its own evidence and exposes a complete revenue source chain", async () => {
  const detailView = await readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8");
  for (const component of ["LineSeriesChart", "DonutChart", "BarComparison", "RevenueSourceChain"]) assert.match(detailView, new RegExp(`function ${component}`));
  assert.match(detailView, /营收来源链/);
  assert.match(detailView, /节点与汇总差异均绑定来源单元格/);
  const revenue = mockDimensionDetails.find((detail) => detail.dimensionId === "revenue");
  assert.ok(revenue);
  const latest = revenue.series.at(-1);
  assert.deepEqual(latest.measures.map((measure) => measure.label), ["合同订单", "发票", "回款流水", "确认收入"]);
  assert.deepEqual(latest.measures.map((measure) => measure.value), [12040, 12360, 11790, 12800]);
  const evidenceById = new Map(mockEvidence.map((item) => [item.id, item]));
  for (const detail of mockDimensionDetails) {
    for (const point of detail.series) {
      assert.equal(Object.hasOwn(point, "primary"), false);
      for (const measure of point.measures) {
        const reference = evidenceById.get(measure.evidenceRefs[0]);
        assert.ok(reference);
      }
    }
  }
  for (const measure of latest.measures) {
    const reference = evidenceById.get(measure.evidenceRefs[0]);
    assert.equal(reference?.locator?.kind, "excel");
    assert.equal(reference?.locator?.sheet, "营收链");
  }
  assert.deepEqual(latest.measures.slice(1).map((measure) => evidenceById.get(measure.comparisonEvidenceRefs?.[0])?.locator?.range), ["H6:H6", "I6:I6", "J6:J6"]);
  const revenueMaterial = mockMaterials.find((material) => material.id === "material-revenue-chain");
  assert.deepEqual(revenueMaterial.sheets[0].rows[2].slice(7), [320, -570, 1010]);
  assert.match(detailView, /节点与汇总差异均绑定来源单元格/);
});

test("R8-6 keeps onsite manifests local while raw materials refuse processed scene substitution", async () => {
  const [materialPane, onsitePreview] = await Promise.all([
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/ProductionOnsitePanel.tsx", root), "utf8"),
  ]);
  assert.deepEqual(new Set(mockOnsiteAssets.map((asset) => asset.kind)), new Set(["image", "supplement", "video", "panorama", "equipment_point", "scene_3dgs"]));
  assert.equal(mockOnsiteAssets.filter((asset) => asset.lazyLoad).length >= 4, true);
  const materialIds = new Set(mockMaterials.map((material) => material.id));
  assert.equal(mockOnsiteAssets.filter((asset) => asset.materialId).every((asset) => materialIds.has(asset.materialId)), true);
  const scene = mockMaterials.find((material) => material.kind === "scene");
  assert.equal(scene?.points.length, 96);
  assert.doesNotMatch(materialPane, /SiteScenePreview|ReferenceImageGallery|factory-preview/);
  assert.match(materialPane, /原始资产待接入/);
  assert.match(onsitePreview, /asset\.kind === "image" \|\| asset\.kind === "supplement"/);
  assert.match(onsitePreview, /disabled=\{!available\}/);
  assert.match(onsitePreview, /该角度原件尚未上传/);
  assert.match(onsitePreview, /不使用公开图替代/);
  assert.doesNotMatch(onsitePreview, /scene_3dgs|panorama|https?:\/\//);
});

test("directional docks keep fixed restore anchors while material and review stay in one layout", async () => {
  const [app, topBar, navigation, review, material, dock, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/TopBar.tsx", root), "utf8"),
    readFile(new URL("src/components/NavigationRail.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.match(app, /scrollReviewPaneTo/);
  assert.match(app, /document\.getElementById\("review-pane"\)/);
  assert.match(app, /pane\.scrollTo\(\{ top: Math\.max\(0, top\), behavior: "auto" \}\)/);
  assert.doesNotMatch(app, /scrollIntoView/);
  assert.doesNotMatch(topBar, /全屏|Fullscreen/);
  assert.match(navigation, /向左折叠六维导航/);
  assert.match(navigation, /向右展开六维导航/);
  assert.match(navigation, /aria-controls="navigation-rail"/);
  assert.match(navigation, /aria-expanded=\{!collapsed\}/);
  assert.match(app, /setLayout\(\{ \.\.\.data\.layout \}\)/);
  assert.match(app, /layout\.middleCollapsed \? "is-middle-collapsed"/);
  assert.match(app, /layout\.materialCollapsed \? "is-material-collapsed"/);
  assert.match(app, /!layout\.middleCollapsed && !layout\.materialCollapsed \? <div aria-label=\{copy\(locale, "Resize the review and original-material areas", "调整中间与材料区域宽度"\)\}/);
  assert.match(app, /!layout\.collaborationCollapsed && !\(layout\.middleCollapsed && layout\.materialCollapsed\) \? <div aria-label=\{copy\(locale, "Resize the collaboration workspace", "调整协同工作台高度"\)\}/);
  assert.doesNotMatch(app, /MaximizedPane|maximizedPane|collaborationMaximized|is-collaboration-maximized|toggleCollaborationMaximized/);

  assert.match(review, /收起审查画布至左上角/);
  assert.match(review, /从左上角展开审查画布/);
  assert.match(review, /pane-corner-glyph">↘/);
  assert.match(review, /pane-corner-glyph">↖/);
  assert.doesNotMatch(review, /panel-collapse-rail|rail-toggle-surface/);
  assert.doesNotMatch(review, /全屏|review-(?:collapse-)?maximize-trigger|onToggleMaximized|maximized:/);
  assert.match(review, /onScroll=\{handleScroll\}/);
  assert.match(review, /<RiskSection/);
  assert.match(review, /<ComplianceSection/);
  assert.match(review, /data\.dimensions\.filter\(\(item\) => item\.id !== "compliance"\)\.map/);
  assert.match(app, /id === "risk" \|\| id === "compliance" \? "review-risk" : `dimension-\$\{id\}`/);
  assert.match(material, /收起原始材料至右上角/);
  assert.match(material, /从右上角展开原始材料/);
  assert.match(material, /pane-corner-glyph">↙/);
  assert.match(material, /pane-corner-glyph">↗/);
  assert.doesNotMatch(material, /panel-collapse-rail|rail-toggle-surface/);
  assert.doesNotMatch(material, /全屏|material-(?:rail-)?maximize-trigger|onToggleMaximized|maximized:/);
  assert.match(dock, /收起审批协同至右下角/);
  assert.match(dock, /从右下角展开审批协同/);
  assert.doesNotMatch(dock, /全屏|Maximized|maximized|onToggleMaximized|collaboration-maximize-trigger/);
  assert.match(dock, /pane-corner-anchor collaboration-corner-anchor/);
  assert.doesNotMatch(dock, /rail-toggle-surface|collaboration-rail-toggle|collaboration-expanded-toggle|collaboration-rail-maximize-trigger/);
  assert.match(dock, /is-business-collapsed/);
  assert.match(dock, /is-policy-collapsed/);
  assert.match(dock, /is-risk-collapsed/);
  assert.match(dock, /向中间折叠协作事实流/);
  assert.match(dock, /aria-expanded=\{!collapsed\}/);

  assert.match(app, /<MaterialPane[^>]*collapsed=\{layout\.materialCollapsed\}/);
  assert.match(app, /<CollaborationDock[^>]*collapsed=\{layout\.collaborationCollapsed\}/);

  assert.equal(mockWorkbenchProject.layout.collaborationHeight, 175);
  for (const key of ["navigationCollapsed", "middleCollapsed", "materialCollapsed", "collaborationCollapsed", "businessCollapsed", "policyCollapsed", "riskCollapsed"]) assert.equal(mockWorkbenchProject.layout[key], false, key);
  assert.match(styles, /\.navigation-toolbar\s*\{[^}]*left:\s*0;[^}]*top:\s*0;/s);
  assert.match(styles, /\.pane-corner-anchor\s*\{[^}]*position:\s*absolute;[^}]*z-index:\s*36;/s);
  assert.match(styles, /\.review-corner-anchor\s*\{[^}]*left:\s*0;[^}]*top:\s*0;/s);
  assert.match(styles, /\.material-corner-anchor\s*\{[^}]*right:\s*0;[^}]*top:\s*0;/s);
  assert.match(styles, /\.collaboration-corner-anchor\s*\{[^}]*right:\s*0;[^}]*bottom:\s*0;/s);
  assert.doesNotMatch(styles, /is-review-maximized|is-material-maximized|is-collaboration-maximized|review-canvas\.is-maximized|review-maximize-trigger|material-maximize-trigger|material-rail-maximize-trigger|collaboration-maximize-trigger|panel-maximize-trigger/);
  assert.doesNotMatch(styles, /panel-collapse-rail|rail-toggle-surface|review-expanded-toggle|material-collapse-trigger|collaboration-expanded-toggle/);
  assert.match(styles, /\.role-column-business \.role-collapse-trigger\s*\{[^}]*left:\s*0;/s);
  assert.match(styles, /\.shared-column \.policy-collapse-trigger\s*\{[^}]*left:\s*50%;/s);
  assert.match(styles, /\.role-column-risk \.role-collapse-trigger\s*\{[^}]*right:\s*0;/s);
  assert.match(styles, /\.workbench-body\.is-middle-collapsed:not\(\.is-material-collapsed\) \.material-pane\s*\{[^}]*grid-row:\s*1 \/ 3;/s);
  assert.match(styles, /\.workbench-body\.is-middle-collapsed \.review-canvas\s*\{[^}]*position:\s*absolute;[^}]*left:\s*var\(--resolved-navigation-width\);/s);
  assert.match(styles, /\.material-pane\.is-collapsed\s*\{[^}]*position:\s*absolute;[^}]*right:\s*0;[^}]*top:\s*0;/s);
  assert.match(styles, /\.collaboration-dock\.is-collapsed\s*\{[^}]*position:\s*absolute;[^}]*right:\s*0;[^}]*bottom:\s*0;/s);
  assert.doesNotMatch(styles, /\.workbench-body\.is-material-collapsed\s*\{[^}]*grid-template-columns:[^}]*44px;/s);
  assert.doesNotMatch(styles, /\.workbench-body\.is-collaboration-collapsed\s*\{[^}]*grid-template-rows:[^}]*44px\s*;/s);
});

test("horizontal splitter resizes the review viewport and collaboration dock in one animation frame", async () => {
  const [app, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(app, /const property = axis === "material" \? "--layout-material-width" : "--layout-collaboration-height"/);
  assert.match(app, /requestAnimationFrame\(applyResize\)/);
  assert.match(app, /workbench\.style\.setProperty\(property, `\$\{nextValue\}px`\)/);
  assert.match(app, /function stop[\s\S]*applyResize\(\);[\s\S]*setMaterialEdge[\s\S]*setCollaborationEdge/);
  assert.match(app, /removeEventListener\("pointercancel", stop\)/);
  assert.match(app, /removeEventListener\("blur", stop\)/);
  assert.match(styles, /grid-template-rows:\s*44px minmax\(0, 1fr\) var\(--layout-divider-hit\) var\(--layout-collaboration-height\)/);
  assert.match(styles, /\.review-canvas\s*\{[^}]*grid-row:\s*1 \/ 3;/s);
  assert.match(styles, /\.collaboration-dock\s*\{[^}]*grid-row:\s*4;/s);
});
