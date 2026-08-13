import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const source = (path) => readFile(new URL(path, root), "utf8");

test("3D 现场使用深度测试的原生 WebGL 体块，不再用图片环廊冒充空间", async () => {
  const [scene, css] = await Promise.all([
    source("src/components/SiteScenePreview.tsx"),
    source("src/components/SiteScenePreview.css"),
  ]);

  assert.match(scene, /canvas\.getContext\("webgl"/);
  assert.match(scene, /gl\.enable\(gl\.DEPTH_TEST\)/);
  assert.match(scene, /perspectiveMatrix[\s\S]*lookAtMatrix/);
  assert.match(scene, /gl\.drawArrays\(gl\.TRIANGLES/);
  assert.match(scene, /function addBox[\s\S]*createSceneGeometry/);
  assert.doesNotMatch(css, /\.scene-space-world|\.scene-space-view|translateZ\(var\(--scene-radius\)\)/);
  assert.match(scene, /className="scene-evidence-reference"[\s\S]*<img/);
});

test("现场动画固定材料设备成品三个两字区域且不显示编号", async () => {
  const scene = await source("src/components/SiteScenePreview.tsx");

  assert.match(scene, /id: "raw", label: "材料"/);
  assert.match(scene, /id: "equipment", label: "设备"/);
  assert.match(scene, /id: "finished", label: "成品"/);
  assert.doesNotMatch(scene, /id: "people", label:/);
  assert.match(scene, /zone === "process" \|\| zone === "people" \? "equipment" : zone/);
  assert.match(scene, /displayAreas\(views\)/);
  assert.match(scene, /if \(observed\.has\("raw"\)\)/);
  assert.match(scene, /if \(observed\.has\("finished"\)\)/);
  assert.match(scene, /addRouteSegment\(buffers, sceneArea\("raw"\)\.center, sceneArea\("equipment"\)\.center\)/);
  assert.match(scene, /addRouteSegment\(buffers, sceneArea\("equipment"\)\.center, sceneArea\("finished"\)\.center\)/);
  assert.match(scene, /function productionMaterialMotion[\s\S]*PRODUCTION_CYCLE_SECONDS/);
  assert.match(scene, /addMovingMaterial\(buffers, animationSeconds\)/);
  assert.match(scene, /aria-label=\{copy\(locale, "Raw material, equipment, and finished product", "材料设备成品"\)\}/);
  assert.doesNotMatch(scene, /<small>\{index \+ 1\}<\/small>/);
});

test("一个模拟人员在设备区三台代表设备之间巡看停留", async () => {
  const [scene, onsite, css] = await Promise.all([
    source("src/components/SiteScenePreview.tsx"),
    source("src/components/ProductionOnsitePanel.tsx"),
    source("src/components/SiteScenePreview.css"),
  ]);

  assert.match(scene, /<strong>\{copy\(locale, "Animated site schematic", "现场动画"\)\}<\/strong>/);
  assert.match(scene, /function operatorMotion[\s\S]*machineA[\s\S]*machineB[\s\S]*machineC[\s\S]*stationA[\s\S]*stationB[\s\S]*stationC/);
  assert.match(scene, /position: stationA, target: machineA[\s\S]*position: stationB, target: machineB[\s\S]*position: stationC, target: machineC/);
  assert.match(scene, /cycle < 4[\s\S]*cycle < 6[\s\S]*cycle < 10[\s\S]*cycle < 12[\s\S]*cycle < 16[\s\S]*cycle < 20/);
  assert.match(scene, /if \(observed\.has\("equipment"\)\) addOperator\(buffers, animationSeconds\)/);
  assert.match(scene, /equipmentSummary\.operating[\s\S]*equipmentSummary\.maintenance/);
  assert.match(onsite, /people\|personnel\|worker\|employee\|operator\|staff\|人员\|员工\|工人\|操作员/);
  assert.match(onsite, /sceneEquipmentSummary[\s\S]*status === "operating"[\s\S]*status === "maintenance"[\s\S]*status === "idle"/);
  assert.match(scene, /requestAnimationFrame\(draw\)/);
  assert.match(scene, /暂停现场轻微动画|播放现场轻微动画/);
  assert.match(scene, /prefers-reduced-motion: reduce/);
  assert.match(css, /\.scene-observation-summary/);
  assert.match(css, /\.scene-observation-summary button\.is-cycle-active/);
  assert.doesNotMatch(scene, /scene-demo-runtime|scene-interaction-hint/);
  assert.doesNotMatch(css, /\.scene-demo-runtime|\.scene-interaction-hint/);
});

test("本轮只渲染 L1，并为未来真实 L2 到 L4 保留禁用楼层与独立高度", async () => {
  const scene = await source("src/components/SiteScenePreview.tsx");

  assert.match(scene, /id: "L1", label: "L1 地面层", available: true, renderOrigin: \[0, 0, 0\]/);
  assert.match(scene, /id: "L2", label: "L2", available: false, renderOrigin: \[0, LEVEL_HEIGHT, 0\]/);
  assert.match(scene, /id: "L3", label: "L3", available: false, renderOrigin: \[0, LEVEL_HEIGHT \* 2, 0\]/);
  assert.match(scene, /id: "L4", label: "L4", available: false, renderOrigin: \[0, LEVEL_HEIGHT \* 3, 0\]/);
  assert.match(scene, /if \(!level\?\.available \|\| activeLevel !== "L1"\) return emptySceneGeometry\(\)/);
  assert.match(scene, /const activeLevel: SiteSceneLevelId = "L1"/);
  assert.doesNotMatch(scene, /<option disabled=\{!level\.available\}/);
  assert.match(scene, /data-scene-level=\{activeLevel\}/);
});

test("轨道视角支持拖动、滚轮、按钮、键盘和视角预设", async () => {
  const [scene, css] = await Promise.all([
    source("src/components/SiteScenePreview.tsx"),
    source("src/components/SiteScenePreview.css"),
  ]);

  assert.match(scene, /useLockedWheel\(canvasRef/);
  assert.match(scene, /onPointerDown=\{beginOrbit\}/);
  assert.match(scene, /onPointerMove=\{orbit\}/);
  assert.match(scene, /yaw: drag\.yaw - \(event\.clientX - drag\.x\)/);
  assert.match(scene, /pitch: clamp\(drag\.pitch \+ \(event\.clientY - drag\.y\)/);
  assert.match(scene, /data-drag-mode="scene-follows-pointer"/);
  assert.match(scene, /data-camera-yaw=\{camera\.yaw\.toFixed\(3\)\}/);
  assert.match(scene, /data-camera-pitch=\{camera\.pitch\.toFixed\(3\)\}/);
  assert.match(scene, /Math\.max\(GROUND_Y \+ MIN_CAMERA_CLEARANCE/);
  assert.match(scene, /data-camera-height=\{cameraHeight\.toFixed\(3\)\}/);
  assert.match(scene, /copy\(locale, "Top", "俯视"\)[\s\S]*copy\(locale, "Eye level", "平视"\)/);
  assert.match(scene, /重置 3D 现场视角/);
  assert.match(scene, /event\.key === "0"[\s\S]*event\.key === "1"[\s\S]*event\.key === "2"/);
  assert.match(css, /\.scene-webgl-viewport\s*\{[\s\S]*?min-height:\s*500px;/);
  assert.doesNotMatch(css, /\.scene-interaction-hint\s*\{/);
});

test("沉浸式 L1 主画布约为旧 260px 预览的两倍，原图只在右侧对照", async () => {
  const [scene, css] = await Promise.all([
    source("src/components/SiteScenePreview.tsx"),
    source("src/components/SiteScenePreview.css"),
  ]);

  assert.match(css, /\.site-scene-preview\s*\{[^}]*min-height:\s*590px;[^}]*grid-template-rows:\s*48px minmax\(500px, 1fr\) 42px;/);
  assert.match(css, /\.scene-evidence-reference\s*\{[^}]*right:\s*10px;[^}]*bottom:\s*10px;/);
  assert.doesNotMatch(css, /\.scene-evidence-reference\s*\{[^}]*left:\s*8px;/);
  assert.match(scene, /Compare with source image: \$\{formatCanonicalNarrative\(activeView\.label, locale\)\}/);
});

test("区域、外部证据选择与现场原图保持双向同步且布局不横向溢出", async () => {
  const [scene, onsite, css] = await Promise.all([
    source("src/components/SiteScenePreview.tsx"),
    source("src/components/ProductionOnsitePanel.tsx"),
    source("src/components/SiteScenePreview.css"),
  ]);

  assert.match(onsite, /function sceneZoneForMaterial/);
  assert.match(onsite, /selectedTargetMaterialId[\s\S]*matchingView[\s\S]*setSelectedViewId/);
  assert.match(onsite, /\[onsiteViews, selectedTargetMaterialId\]/);
  assert.doesNotMatch(onsite, /\[evidenceById, onsiteViews, selectedTarget, selectedViewId\]/);
  assert.match(onsite, /zone: item\.zone/);
  assert.match(onsite, /equipmentSummary=\{sceneEquipmentSummary\}/);
  assert.match(onsite, /activeViewId=\{selectedView\?\.id/);
  assert.match(scene, /const selectZone[\s\S]*onViewSelect\(view\.id\)/);
  assert.match(css, /\.site-scene-preview[\s\S]*min-width:\s*0;[\s\S]*overflow:\s*hidden;/);
  assert.match(css, /\.scene-webgl-canvas[\s\S]*overscroll-behavior:\s*contain;/);
  assert.match(css, /\.scene-observation-summary[\s\S]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)[\s\S]*overflow:\s*hidden;/);
});
