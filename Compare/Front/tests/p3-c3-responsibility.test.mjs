import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import test from "node:test";
import { mockEvidence, mockMaterials, mockOnsiteAssets } from "../src/mock/mockCase.ts";

const root = new URL("../", import.meta.url);

async function source(path) {
  return readFile(new URL(path, root), "utf8");
}

test("C3-1 keeps one concise project truth boundary and removes visible implementation tutorials", async () => {
  const sources = await Promise.all([
    source("src/components/DimensionDetailView.tsx"),
    source("src/components/ComplianceSubjectGraph.tsx"),
    source("src/components/FinancedEquipmentPanel.tsx"),
    source("src/components/MaterialPane.tsx"),
    source("src/components/ProductionStagesPanel.tsx"),
    source("src/components/TransactionCoreCharts.tsx"),
  ]);
  const visibleSources = sources.join("\n");
  for (const banned of ["一个设备 ID 同步驱动", "稳定 UI ID", "选择中间数据可后台定位", "全部为模拟/脱敏内容"]) {
    assert.equal(visibleSources.includes(banned), false, banned);
  }
  assert.equal((visibleSources.match(/数据边界：本项目为脱敏模拟/g) ?? []).length, 1);
  assert.match(visibleSources, /待定位|定位未完成/);
  assert.match(visibleSources, /不可核验/);
});

test("C3-2 compresses compliance graph and only opens its internal inspector after selection", async () => {
  const [graph, css] = await Promise.all([
    source("src/components/ComplianceSubjectGraph.tsx"),
    source("src/styles/app.css"),
  ]);
  assert.match(graph, /is-inspector-open/);
  assert.match(graph, /selectedSubjectIds\.length \? <aside/);
  assert.doesNotMatch(graph, /拖动节点|滚轮缩放|键盘方向键|稳定 UI ID/);
  assert.match(css, /\.review-canvas \.interactive-graph-layout \{[\s\S]*min-height: 370px/);
  assert.match(css, /\.review-canvas \.interactive-graph-layout\.is-inspector-open/);
});

test("C3-3 has one financed-equipment entry with all core facts and no duplicate relation row", async () => {
  const [workspace, panel, logic] = await Promise.all([
    source("src/components/TransactionWorkspace.tsx"),
    source("src/components/FinancedEquipmentPanel.tsx"),
    source("src/lib/workbenchLogic.ts"),
  ]);
  assert.equal((workspace.match(/<FinancedEquipmentPanel/g) ?? []).length, 1);
  assert.doesNotMatch(workspace, /TransactionCoreParameters|transaction-semantic-chain|transaction-equipment-switch/);
  assert.doesNotMatch(panel, /financed-equipment-relation|transaction-chain-borrower|transaction-chain-lessor/);
  assert.match(panel, /deriveTransactionTopParameters/);
  for (const label of ["供应商评级", "品牌评级", "项目金额", "融资成数", "融资金额", "期限", "还款结构风险"]) assert.match(logic, new RegExp(label));
  for (const targetId of ["transaction-core-supplier-rating-", "transaction-core-brand-rating-", "transaction-core-project-amount", "transaction-core-financing-ratio"]) {
    assert.equal((logic.match(new RegExp(targetId, "g")) ?? []).length, 1, targetId);
  }
  assert.ok(workspace.indexOf("transaction-finance-price-grid") < workspace.indexOf("TransactionRepaymentChart"));
  assert.ok(workspace.indexOf("TransactionRepaymentChart") < workspace.indexOf("transaction-config-panel"));
});

test("C3-4 keeps MaterialPane raw-only with direct originalUrl image and locators in the same layer", async () => {
  const [pane, app, css] = await Promise.all([
    source("src/components/MaterialPane.tsx"),
    source("src/App.tsx"),
    source("src/styles/app.css"),
  ]);
  assert.doesNotMatch(pane, /ReferenceImageGallery|SiteScenePreview|factory-preview/);
  assert.doesNotMatch(app, /selectedReferenceImageId=|referenceImages=|onReferenceImageSelect=|onCloseReferenceGallery=/);
  assert.match(pane, /className=\{`image-original-layer/);
  assert.match(pane, /src=\{sourceUrl\}/);
  assert.match(pane, /imageItems\.map/);
  assert.doesNotMatch(pane, /useDeferredImageAsset|URL\.createObjectURL|synthetic-project-overlay/);
  assert.match(pane, /View image at original pixels[\s\S]*Original size/);
  assert.match(pane, /visibleHeightRatio=\{visibleHeightRatio\}/);
  assert.match(pane, /scene=\{selected\?\.kind === "image" \? null : sceneSpec\}/);
  assert.match(pane, /scale\([^)]*view\.scale/);
  assert.match(pane, /\{displayHitCount\} \{copy\(locale, "regions", "个区域"\)\}/);
  assert.doesNotMatch(css, /\.factory-preview/);
});

test("C3-5 and C3-6 map both onsite views to local simulated images and existing bbox evidence", async () => {
  const factory = mockMaterials.find((material) => material.id === "material-factory");
  const supplement = mockMaterials.find((material) => material.id === "material-factory-supplement");
  assert.equal(factory?.kind, "image");
  assert.equal(supplement?.kind, "image");
  assert.equal(factory?.isSimulated, true);
  assert.equal(supplement?.isSimulated, true);
  assert.equal(factory?.sourceLabel, "脱敏模拟现场材料");
  assert.equal(supplement?.sourceLabel, "脱敏模拟现场材料");
  assert.equal(factory?.assetUrl, "/mock-materials/precision-workshop-main.png");
  assert.equal(supplement?.assetUrl, "/mock-materials/equipment-nameplate-station.png");
  for (const assetUrl of [factory?.assetUrl, supplement?.assetUrl]) {
    assert.ok(assetUrl);
    const info = await stat(new URL(`public${assetUrl}`, root));
    assert.ok(info.size > 100_000);
  }
  assert.deepEqual(mockOnsiteAssets.slice(0, 2).map((asset) => asset.materialId), [factory?.id, supplement?.id]);
  const evidence = mockEvidence.filter((item) => ["evidence-factory-site", "evidence-factory-supplement"].includes(item.id));
  assert.deepEqual(evidence.map((item) => item.locator?.kind), ["image", "image"]);
  assert.deepEqual(evidence.map((item) => item.locator && "materialId" in item.locator ? item.locator.materialId : null), [factory?.id, supplement?.id]);
  assert.deepEqual(evidence.map((item) => item.locator && "materialVersionId" in item.locator ? item.locator.materialVersionId : null), [factory?.versionId, supplement?.versionId]);
  assert.equal(evidence.every((item) => item.locator?.kind === "image" && item.locator.bbox.width > 0 && item.locator.bbox.height > 0), true);
});

test("C3-5 uses the same material and asset in the onsite preview, keeps equipment facts, and preserves failure fallback", async () => {
  const [onsite, detail] = await Promise.all([
    source("src/components/ProductionOnsitePanel.tsx"),
    source("src/components/DimensionDetailView.tsx"),
  ]);
  assert.match(onsite, /data-material-id=\{selectedMaterial\?\.id/);
  assert.match(onsite, /data-material-version-id=\{selectedMaterial\?\.versionId/);
  assert.match(onsite, /materialPreviewUrl/);
  assert.match(onsite, /src=\{selectedMaterialUrl\}/);
  assert.match(onsite, /assetTarget: ReviewEvidenceTarget \| null = selectedMaterial && assetEvidenceRefs\[0\]/);
  assert.match(onsite, /现场设备事实/);
  assert.match(onsite, /该角度原件尚未上传[\s\S]*不使用公开图替代/);
  assert.doesNotMatch(onsite, /scene_3dgs|panorama|public\/reference-images/);
  assert.ok(detail.indexOf("<ProductionOnsitePanel") < detail.indexOf("<ProductionStagesPanel"));
  assert.ok(detail.indexOf("<ProductionStagesPanel") < detail.indexOf("production-time-controls-sticky"));
});

test("C3-7 fixes revenue zero growth at 72 percent with independent positive and negative scales", async () => {
  const revenue = await source("src/components/RevenueCoreCharts.tsx");
  assert.match(revenue, /const growthMinimum = Math\.min\(-10, \.\.\.growthValues\)/);
  assert.match(revenue, /const growthMaximum = Math\.max\(25, \.\.\.growthValues\)/);
  assert.match(revenue, /const growthBaselineRatio = \.72/);
  assert.match(revenue, /const positivePlotHeight = growthBaselineY - plot\.top/);
  assert.match(revenue, /const negativePlotHeight = plot\.bottom - growthBaselineY/);
  assert.match(revenue, /data-baseline-ratio=\{growthBaselineRatio\}/);
});

test("C3-V1 keeps production stage frames bounded and crops known project-photo footers", async () => {
  const [stages, css] = await Promise.all([
    source("src/components/ProductionStagesPanel.tsx"),
    source("src/styles/app.css"),
  ]);
  assert.match(stages, /className=\{`production-stage-media[\s\S]*<img[^>]*loading="lazy"/);
  assert.match(stages, /PROJECT_PHOTO_VISIBLE_RATIO = 0\.885/);
  assert.match(stages, /image\.pixelHeight \* visibleHeightRatio/);
  const mediaRule = css.match(/\.review-canvas \.production-stage-media \{([^}]+)\}/)?.[1] ?? "";
  assert.match(mediaRule, /aspect-ratio:\s*4 \/ 3/);
  assert.match(mediaRule, /min-width:\s*0/);
  assert.match(mediaRule, /min-height:\s*0/);
  assert.match(mediaRule, /position:\s*relative/);
  assert.match(mediaRule, /overflow:\s*hidden/);
  const imageRule = css.match(/\.review-canvas \.production-stage-media > img,[\s\S]*?\{([^}]+)\}/)?.[1] ?? "";
  assert.match(imageRule, /position:\s*absolute/);
  assert.match(imageRule, /inset:\s*0/);
  assert.match(imageRule, /min-width:\s*0/);
  assert.match(imageRule, /min-height:\s*0/);
  assert.match(imageRule, /object-fit:\s*contain/);
});

test("C3-V2 coalesces resize work and never observes while writing the same canvas", async () => {
  const [model, graph] = await Promise.all([
    source("src/components/EquipmentModelPreview.tsx"),
    source("src/components/ComplianceSubjectGraph.tsx"),
  ]);
  assert.match(model, /const containerRef = useRef<HTMLDivElement>/);
  assert.match(model, /observer\?\.observe\(container\)/);
  assert.doesNotMatch(model, /observe\(canvas\)/);
  assert.match(model, /if \(canvas\.width !== pixelWidth\) canvas\.width = pixelWidth/);
  assert.match(model, /if \(canvas\.height !== pixelHeight\) canvas\.height = pixelHeight/);
  assert.match(model, /scheduleDraw[\s\S]*frameId !== null[\s\S]*requestAnimationFrame/);
  assert.match(model, /observer\?\.disconnect\(\)[\s\S]*cancelAnimationFrame\(frameId\)/);
  assert.match(graph, /width === observedWidth && height === observedHeight/);
  assert.match(graph, /scheduleFit[\s\S]*requestAnimationFrame[\s\S]*new ResizeObserver\(scheduleFit\)/);
  assert.match(graph, /observer\.disconnect\(\)[\s\S]*cancelAnimationFrame\(frameId\)/);
});

test("compliance fit uses live subject bounds and locks wheel zoom inside the graph viewport", async () => {
  const [graph, css] = await Promise.all([
    source("src/components/ComplianceSubjectGraph.tsx"),
    source("src/styles/app.css"),
  ]);
  assert.match(graph, /const positionsRef = useRef\(positions\)/);
  assert.match(graph, /const left = Math\.min\([\s\S]*point\.x/);
  assert.match(graph, /const right = Math\.max\([\s\S]*point\.x \+ NODE_DIAMETER/);
  assert.match(graph, /contentWidth[\s\S]*contentHeight[\s\S]*width - contentWidth \* scale/);
  assert.match(graph, /event\.preventDefault\(\)[\s\S]*event\.stopPropagation\(\)/);
  assert.match(graph, /addEventListener\("wheel", lockGraphWheel, \{ passive: false \}\)/);
  assert.match(graph, /removeEventListener\("wheel", lockGraphWheel\)/);
  assert.doesNotMatch(graph, /onWheel=/);
  assert.match(graph, /className="compliance-plane interactive-subject-graph"/);
  assert.match(css, /\.compliance-plane\.interactive-subject-graph \{[\s\S]*?grid-template-columns:\s*1fr;[\s\S]*?padding:\s*0;/);
  assert.doesNotMatch(css, /\.compliance-plane\.subject-graph \{/);
});

test("all zoomable visual surfaces lock native wheel events before they reach outer scroll containers", async () => {
  const [wheelHook, graph, model, onsite, pane, scene, css] = await Promise.all([
    source("src/lib/useLockedWheel.ts"),
    source("src/components/ComplianceSubjectGraph.tsx"),
    source("src/components/EquipmentModelPreview.tsx"),
    source("src/components/ProductionOnsitePanel.tsx"),
    source("src/components/MaterialPane.tsx"),
    source("src/components/SiteScenePreview.tsx"),
    source("src/styles/app.css"),
  ]);

  assert.match(wheelHook, /event\.preventDefault\(\)[\s\S]*event\.stopPropagation\(\)/);
  assert.match(wheelHook, /addEventListener\("wheel", lockWheel, \{ passive: false \}\)/);
  assert.match(wheelHook, /removeEventListener\("wheel", lockWheel\)/);
  assert.match(graph, /addEventListener\("wheel", lockGraphWheel, \{ passive: false \}\)/);

  for (const [label, component] of [["equipment model", model], ["onsite image", onsite], ["raw material image", pane], ["scene preview", scene]]) {
    assert.match(component, /useLockedWheel\(/, label);
    assert.doesNotMatch(component, /onWheel=/, label);
    assert.doesNotMatch(component, /ReactWheelEvent/, label);
  }
  assert.match(model, /data-view-zoom=\{view\.zoom\.toFixed\(2\)\}/);
  assert.match(scene, /data-view-zoom=\{zoom\.toFixed\(2\)\}/);

  for (const selector of [".subject-graph-viewport", ".equipment-model-preview canvas", ".production-onsite-viewport", ".image-original-viewport", ".site-scene-preview canvas"]) {
    const selectorIndex = css.indexOf(selector);
    assert.notEqual(selectorIndex, -1, selector);
    assert.match(css.slice(selectorIndex, selectorIndex + 420), /overscroll-behavior:\s*contain/, selector);
  }
});
