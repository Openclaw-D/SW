import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("P6 equipment preview renders structured volumetric geometry with native WebGL", async () => {
  const preview = await readFile(new URL("src/components/EquipmentModelPreview.tsx", root), "utf8");

  assert.match(preview, /canvas\.getContext\("webgl"/);
  assert.match(preview, /function buildEquipmentMesh\(equipment: FinancedEquipmentLine, mode: StructureMode\)/);
  assert.match(preview, /function addBox\(/);
  assert.match(preview, /function addCylinder\(/);
  assert.match(preview, /equipment\.modelPreset\.(?:kind|width|height|depth)/);
  assert.match(preview, /preset\.spindleCount > 1/);
  assert.match(preview, /configurationNumber\(equipment, \/刀塔\|刀位\|工位/);
  assert.match(preview, /mode === "exploded"/);
  assert.match(preview, /gl\.enable\(gl\.DEPTH_TEST\)/);
  assert.match(preview, /gl\.enable\(gl\.CULL_FACE\)/);
  assert.match(preview, /gl\.drawElements\(gl\.TRIANGLES/);
  assert.match(preview, /data-renderer="webgl"/);
  assert.match(preview, /data-model-claim="schematic"/);
  assert.match(preview, /配置化结构示意 · 非扫描 \/ CAD/);
  assert.doesNotMatch(preview, /getContext\("2d"\)|context\.drawImage|buildImageViews/);
});

test("P6 equipment preview locks camera above the floor and exposes a draggable direction gizmo", async () => {
  const [preview, panel, styles] = await Promise.all([
    readFile(new URL("src/components/EquipmentModelPreview.tsx", root), "utf8"),
    readFile(new URL("src/components/FinancedEquipmentPanel.tsx", root), "utf8"),
    readFile(new URL("src/styles/EquipmentModelPreview.css", root), "utf8"),
  ]);

  for (const event of ["onPointerDown", "onPointerMove", "onPointerUp", "onPointerCancel", "onLostPointerCapture"]) {
    assert.match(preview, new RegExp(event + "="));
  }
  assert.match(preview, /drag\.view\.yaw - deltaX/);
  assert.match(preview, /drag\.view\.pitch \+ deltaY/);
  assert.match(preview, /drag\.view\.yaw - \(event\.clientX - drag\.x\)/);
  assert.match(preview, /drag\.view\.pitch \+ \(event\.clientY - drag\.y\)/);
  assert.match(preview, /const PITCH_MIN = \.04/);
  assert.doesNotMatch(preview, /const PITCH_MIN = -/);
  assert.match(preview, /useLockedWheel\(canvasRef/);
  assert.match(preview, /applyPreset\("top"\)/);
  assert.match(preview, /applyPreset\("front"\)/);
  assert.match(preview, /applyPreset\("right"\)/);
  assert.match(preview, /applyPreset\("left"\)/);
  assert.match(preview, /applyPreset\("back"\)/);
  assert.match(preview, /className="equipment-view-gizmo"/);
  assert.match(preview, /onGizmoPointerDown/);
  assert.match(preview, /onGizmoPointerMove/);
  assert.match(preview, /拖动方向球精确旋转设备/);
  assert.match(preview, /data-camera-floor-lock="horizon"/);
  assert.match(preview, /copy\(locale, "Reset", "重置"\)/);
  assert.match(preview, /copy\(locale, "Cutaway", "剖切"\)/);
  assert.match(preview, /copy\(locale, "Exploded", "展开"\)/);
  assert.match(preview, /copy\(locale, "Operation \/ process", "运行\/工艺"\)/);
  assert.match(preview, /copy\(locale, "Raw material", "原材料"\)[\s\S]*copy\(locale, "Operation \/ processing", "运行 \/ 加工"\)[\s\S]*copy\(locale, "Finished product", "成品"\)/);
  assert.match(preview, /data-process-source="project-semantic"/);
  assert.match(preview, /data-current-equipment-id=\{equipment\.id\}/);
  assert.match(preview, /onSelect\?\.\(item\.id\)/);
  assert.doesNotMatch(preview, /ImageMaterial|images\?|selectedImageId|data-active-material-id|<img/);

  assert.match(panel, /currentImageIds[\s\S]*current\.imageId[\s\S]*current\.imageIds/);
  assert.match(panel, /processStageImages\(materials\)/);
  assert.match(panel, /原材料\|原料\|raw/);
  assert.match(panel, /工艺\|加工\|运行\|process/);
  assert.match(panel, /成品\|finished/);
  assert.match(panel, /data-equipment-line-id=\{current\.id\}/);
  assert.match(panel, /equipment-3d-primary-column[\s\S]*equipment-evidence-sidebar[\s\S]*equipment-process-comparison[\s\S]*equipment-original-series[\s\S]*financed-equipment-current/);
  assert.match(panel, /设备原始材料与当前配置对照抽屉/);
  assert.match(panel, /current\.configuration\.rows\.map/);
  assert.match(panel, /equipment-data-density/);
  assert.doesNotMatch(panel, /<EquipmentStructurePreview[\s\S]{0,180}(?:images|selectedImageId)=/);
  assert.doesNotMatch(panel, /selectComparisonImage[\s\S]{0,800}setView/);

  assert.match(styles, /touch-action:\s*none/);
  assert.match(styles, /overscroll-behavior:\s*contain/);
  assert.match(styles, /min-width:\s*0/);
  assert.match(styles, /overflow:\s*hidden/);
  assert.match(styles, /width:\s*100%/);
  assert.match(styles, /max-width:\s*calc\(100% - 16px\)/);
  assert.match(styles, /\.equipment-view-gizmo\s*\{[^}]*right:\s*8px[^}]*bottom:\s*8px/s);
  assert.match(styles, /equipment-3d-workspace[^}]*1\.95fr[^}]*\.48fr/s);
  assert.match(styles, /equipment-process-flow/);
  assert.match(styles, /equipment-process-chain/);
  assert.match(styles, /equipment-original-series[^}]*financed-equipment-angle-gallery[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\)/);
});
