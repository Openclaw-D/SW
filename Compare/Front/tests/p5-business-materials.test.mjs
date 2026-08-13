import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { businessFolderFor, isOriginalMaterial, materialPreviewUrl, materialRelativePath } from "../src/lib/materialBusinessFolders.ts";

const root = new URL("../", import.meta.url);
const base = { id: "m", versionId: "m-v1", fileName: "file.png", label: "材料", availability: "available", isSimulated: true, sourceLabel: "脱敏模拟" };

test("原始材料只接受业务原件并排除 SceneSpec、GLB 与伪全景描述", () => {
  const image = { ...base, kind: "image", mimeType: "image/png", pixelWidth: 100, pixelHeight: 100, description: "模拟", focalArea: { x: 0, y: 0, width: 1, height: 1 }, role: "original" };
  const scene = { ...base, kind: "scene", mimeType: "model/gltf-binary", sceneFormat: "glb", points: [], fallbackMaterialId: image.id, description: "派生", role: "derived" };
  const panorama = { ...base, kind: "media", mimeType: "image/vnd.compare.panorama", mediaKind: "panorama", durationSeconds: null, description: "描述文件", posterMaterialId: image.id };
  const video = { ...base, kind: "media", mimeType: "video/mp4", mediaKind: "video", durationSeconds: 10, description: "巡检原件", posterMaterialId: image.id, role: "original" };
  const document = { ...base, kind: "document", fileName: "授权书.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", description: "受控 Word 原件", role: "original", businessPath: "基本证照/授权书.docx", originalUrl: "http://api.test/original" };
  assert.equal(isOriginalMaterial(image), true);
  assert.equal(isOriginalMaterial(video), true);
  assert.equal(isOriginalMaterial(document), true);
  assert.equal(businessFolderFor(document), "基本证照");
  assert.equal(materialPreviewUrl(document), "http://api.test/original");
  assert.equal(isOriginalMaterial(scene), false);
  assert.equal(isOriginalMaterial(panorama), false);
});

test("业务路径严格按五类 Windows 文件夹分组并保留相对路径", () => {
  for (const folder of ["基本证照", "经营证明", "现场照片", "增信", "租赁标的"]) {
    const material = { ...base, kind: "image", mimeType: "image/png", pixelWidth: 100, pixelHeight: 100, description: "模拟", focalArea: { x: 0, y: 0, width: 1, height: 1 }, businessPath: `${folder}\\子目录\\原件.png` };
    assert.equal(businessFolderFor(material), folder);
    assert.equal(materialRelativePath(material), "子目录 / 原件.png");
  }
});

test("后端项目原件地址优先于旧快照 assetUrl", () => {
  const image = { ...base, kind: "image", mimeType: "image/png", pixelWidth: 100, pixelHeight: 100, description: "模拟", focalArea: { x: 0, y: 0, width: 1, height: 1 }, originalUrl: "http://api.test/original", assetUrl: "/legacy.png" };
  assert.equal(materialPreviewUrl(image), "http://api.test/original");
  assert.equal(materialPreviewUrl({ ...image, originalUrl: undefined }), "/legacy.png");
  assert.equal(materialPreviewUrl({ ...image, originalAccess: { status: "not_imported", available: false } }), undefined);
});

test("生产与设备页面只从当前项目原始 Material 取图且不展示未证实的通用 3D", async () => {
  const [stages, equipment, onsite, pane, styles] = await Promise.all([
    readFile(new URL("src/components/ProductionStagesPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/FinancedEquipmentPanel.tsx", root), "utf8"),
    readFile(new URL("src/components/ProductionOnsitePanel.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(stages, /materials\.find/);
  assert.doesNotMatch(stages, /公开参考图/);
  assert.match(equipment, /nameplateMaterialId/);
  assert.match(equipment, /currentImageIds[\s\S]*current\.imageId[\s\S]*current\.imageIds/);
  assert.match(equipment, /data-equipment-line-id=\{current\.id\}/);
  assert.match(equipment, /data-current-material-id=\{currentSourceImage\?\.id/);
  assert.match(equipment, /financed-equipment-angle-gallery/);
  assert.doesNotMatch(equipment, /import EquipmentModelPreview|<EquipmentModelPreview|className="derived-model-boundary"|>派生设备3D|alt=\{`[^`]*脱敏模拟/);
  assert.doesNotMatch(onsite, /alt=\{`[^`]*脱敏模拟|SYN-P\d/);
  assert.match(onsite, /materialPreviewUrl/);
  assert.match(onsite, /cleanVisualFileName\(selectedMaterial\.fileName\)/);
  assert.doesNotMatch(pane, /synthetic-project-overlay|useDeferredImageAsset/);
  assert.doesNotMatch(styles, /\.synthetic-project-overlay|\.derived-model-boundary/);
  assert.match(styles, /\.photo-frame > img[^}]*height: auto[^}]*object-fit: contain/);
  assert.match(styles, /\.financed-equipment-primary-photo-frame[^}]*width: 100%[^}]*height: auto[^}]*overflow: hidden/);
  assert.match(pane, /material-folder-tree/);
  assert.match(pane, /MATERIAL_BUSINESS_FOLDERS/);
  assert.match(pane, /打开 PDF 原件/);
  assert.match(pane, /打开 Word 原件/);
});
