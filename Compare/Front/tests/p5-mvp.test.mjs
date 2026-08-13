import assert from "node:assert/strict";
import test from "node:test";
import { readFile, stat } from "node:fs/promises";
import { HttpWorkbenchGateway } from "../src/gateway/httpWorkbenchGateway.ts";
import { evidenceRefForSourceAnchor } from "../src/contracts/materialIntelligence.ts";

const root = new URL("../", import.meta.url);
const meta = { requestId: "request-p5", schemaVersion: "1.0", dataStatus: "simulated", source: "deterministic_business_rules", disclaimer: "synthetic demo" };
const envelope = (data) => new Response(JSON.stringify({ data, meta, errors: [] }), { status: 200, headers: { "Content-Type": "application/json" } });

test("P5 gateway maps all six FastAPI paths with envelope, expectedVersion and Idempotency-Key", async () => {
  const calls = [];
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async (url, init) => {
    calls.push({ url: String(url), init });
    return envelope({});
  } });

  await gateway.preflightMaterialImport("project-a", "manifest.json");
  await gateway.executeMaterialImport("project-a", "manifest.json", 3, "p5-import-12345678");
  await gateway.runMaterialIntelligence({ projectId: "project-a", materialId: "material-a", materialVersionId: "material-a-v2", contextVersion: "p5-test", taskGoals: ["observe"], expectedVersion: 2, idempotencyKey: "p5-intel-12345678" });
  await gateway.readMaterialIntelligence("project-a", "material-a");
  await gateway.confirmMaterialCandidate({ projectId: "project-a", candidateId: "candidate-a", fromFactVersionId: "fact-a-v2", expectedVersion: 2, reason: "人工核对完成", idempotencyKey: "p5-confirm-12345678" });
  await gateway.readMaterialSceneSpec("project-a", "material-a");

  assert.deepEqual(calls.map((call) => call.url), [
    "http://api.test/api/v1/projects/project-a/materials/imports/preflight",
    "http://api.test/api/v1/projects/project-a/materials/imports",
    "http://api.test/api/v1/projects/project-a/materials/material-a/intelligence",
    "http://api.test/api/v1/projects/project-a/materials/material-a/intelligence/latest",
    "http://api.test/api/v1/projects/project-a/candidates/candidate-a/confirm",
    "http://api.test/api/v1/projects/project-a/materials/material-a/scene-spec",
  ]);
  assert.deepEqual(JSON.parse(calls[0].init.body), { projectId: "project-a", manifestRef: "manifest.json" });
  assert.equal(calls[1].init.headers["Idempotency-Key"], "p5-import-12345678");
  assert.equal(JSON.parse(calls[1].init.body).expectedVersion, 3);
  assert.equal(calls[2].init.headers["Idempotency-Key"], "p5-intel-12345678");
  assert.equal(JSON.parse(calls[2].init.body).idempotencyKey, undefined);
  assert.equal(calls[4].init.headers["Idempotency-Key"], "p5-confirm-12345678");
  assert.equal(JSON.parse(calls[4].init.body).reason, "人工核对完成");
});

test("material package upload sends the ZIP as raw File content and preserves only its basename", async () => {
  let call;
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async (url, init) => {
    call = { url: String(url), init };
    return envelope({ projectId: "project-a", uploadId: "upload-a", fileName: "materials.zip", byteSize: 3, sha256: "a".repeat(64), manifestRef: "manifest-a", isSimulated: true });
  } });
  const file = new File(["zip"], "C:\\private\\materials.zip", { type: "application/zip" });
  await gateway.uploadMaterialPackage("project-a", file);
  assert.equal(call.url, "http://api.test/api/v1/projects/project-a/materials/uploads");
  assert.equal(call.init.method, "POST");
  assert.equal(call.init.headers["Content-Type"], "application/zip");
  assert.equal(call.init.headers["X-File-Name"], "materials.zip");
  assert.equal(call.init.body, file);
  assert.doesNotMatch(String(call.init.body), /JSON/);
});

test("SourceAnchor uses stable id mapping even when evidenceRefs are returned in another order", () => {
  const providerAnchors = [{ id: "anchor-z" }, { id: "anchor-a" }, { id: "anchor-m" }];
  const repositoryEvidenceRefs = ["ev-mi-anchor-a", "ev-mi-anchor-m", "ev-mi-anchor-z"];
  assert.deepEqual(providerAnchors.map((anchor) => evidenceRefForSourceAnchor(anchor.id)), ["ev-mi-anchor-z", "ev-mi-anchor-a", "ev-mi-anchor-m"]);
  assert.ok(providerAnchors.every((anchor) => repositoryEvidenceRefs.includes(evidenceRefForSourceAnchor(anchor.id))));
  assert.notEqual(repositoryEvidenceRefs[0], evidenceRefForSourceAnchor(providerAnchors[0].id));
});

test("P5 archive binaries stay outside the core repository while MaterialPane keeps an honest original boundary", async () => {
  await assert.rejects(stat(new URL("public/p5-materials/", root)), { code: "ENOENT" });
  const pane = await readFile(new URL("src/components/MaterialPane.tsx", root), "utf8");
  assert.doesNotMatch(pane, /SYN-P\{projectAssetBadge\}|synthetic-project-overlay/);
  assert.match(pane, /cleanVisualFileName\(material\.fileName\)/);
});

test("P5 UI keeps candidate confirmation manual and renders only declarative SceneSpec", async () => {
  const [app, pane, scene] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialSceneSpecPreview.tsx", root), "utf8"),
  ]);
  assert.match(pane, /人工确认候选/);
  assert.match(pane, /候选不会自动写入权威事实/);
  assert.match(app, /confirmMaterialCandidate/);
  assert.doesNotMatch(app, /sourceAnchors\.findIndex/);
  assert.match(app, /evidenceRefForSourceAnchor\(sourceAnchorId\)/);
  assert.match(scene, /scene\.spec\.objects/);
  assert.match(scene, /scene\.spec\.hotspots/);
  assert.match(scene, /不执行模型代码/);
  assert.doesNotMatch(scene, /eval\(|new Function|dangerouslySetInnerHTML/);
});

test("business composer validates ZIP size and requires an explicit material import confirmation", async () => {
  const [dock, app] = await Promise.all([
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
  ]);
  assert.match(dock, /MAX_MATERIAL_PACKAGE_BYTES = 100 \* 1024 \* 1024/);
  assert.match(dock, /file\.size > MAX_MATERIAL_PACKAGE_BYTES/);
  assert.match(dock, /材料包不能超过 100 MiB/);
  assert.match(dock, /accept="\.zip,application\/zip"/);
  assert.match(dock, /确认导入/);
  assert.match(dock, /已预检 \{importPreview\.preflight\.items\.length\} 项/);
  assert.match(dock, /actor === "business"/);
  assert.doesNotMatch(dock, /uploadMaterialPackage\(file\)[\s\S]{0,240}executeMaterialImport/);
  assert.match(app, /const onImportMaterialPackage/);
  assert.match(app, /gateway\.uploadMaterialPackage\(activeId, file\)/);
  assert.match(app, /await refreshP5Authority\(\)/);
  assert.doesNotMatch(app, /window\.location\.(reload|assign|replace)/);
});

test("P5 material preview uses direct lazy original URLs, releases video resources, and keeps GLB declarative", async () => {
  const [pane, contracts, app] = await Promise.all([
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/contracts/workbench.ts", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
  ]);
  assert.match(pane, /const sourceUrl = materialPreviewUrl\(material\)/);
  assert.match(pane, /src=\{sourceUrl\}/);
  assert.doesNotMatch(pane, /fetch\(sourceUrl|URL\.createObjectURL|URL\.revokeObjectURL/);
  assert.match(pane, /loading="lazy"/);
  assert.match(pane, /decoding="async"/);
  assert.match(pane, /preload="metadata"/);
  assert.match(pane, /video\.pause\(\)/);
  assert.match(pane, /video\.removeAttribute\("src"\)/);
  assert.match(pane, /EXCEL_RENDER_WINDOW = 200/);
  assert.match(pane, /PDF 页面/);
  assert.match(pane, /派生分析不会作为原件显示/);
  assert.match(contracts, /"model\/gltf-binary"/);
  assert.match(contracts, /assetUrl\?: string/);
  assert.match(app, /materialAbortRef\.current\?\.abort\(\)/);
});
