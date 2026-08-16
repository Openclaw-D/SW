import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { HttpWorkbenchGateway } from "../src/gateway/httpWorkbenchGateway.ts";

const root = new URL("../", import.meta.url);
const meta = { requestId: "request-p4", schemaVersion: "1.0", dataStatus: "simulated", source: "deterministic_business_rules", disclaimer: "simulated" };

function envelope(data, errors = []) {
  return new Response(JSON.stringify({ data, meta, errors }), { status: errors.length ? 404 : 200, headers: { "Content-Type": "application/json" } });
}

test("HTTP gateway unwraps the envelope and keeps all read paths project-scoped", async () => {
  const calls = [];
  const gateway = new HttpWorkbenchGateway({
    apiBase: "http://127.0.0.1:8000/api/v1/",
    fetchImpl: async (url, init) => {
      calls.push({ url: String(url), init });
      return envelope({ id: "material-a" });
    },
  });
  assert.equal(gateway.getLastResponseMeta(), null);

  const material = await gateway.readMaterial("project-a", "material-a");
  assert.equal(material.id, "material-a");
  assert.equal(calls[0].url, "http://127.0.0.1:8000/api/v1/projects/project-a/materials/material-a");
  assert.equal(calls[0].init.method, "GET");
  assert.deepEqual(gateway.getLastResponseMeta(), meta);
  const metaCopy = gateway.getLastResponseMeta();
  metaCopy.requestId = "mutated";
  assert.equal(gateway.getLastResponseMeta().requestId, "request-p4");
});

test("HTTP gateway binds project originals to the streamed original route", async () => {
  const material = {
    id: "site-front",
    versionId: "site-front-v1",
    fileName: "厂门正视.jpg",
    label: "厂门正视",
    availability: "available",
    originalAccess: { status: "available", available: true },
    isSimulated: true,
    sourceLabel: "脱敏模拟",
    businessPath: "现场照片/厂门正视.jpg",
    folderPath: "现场照片",
    kind: "image",
    mimeType: "image/jpeg",
    pixelWidth: 1600,
    pixelHeight: 900,
    description: "脱敏模拟现场",
    focalArea: { x: 0, y: 0, width: 1, height: 1 },
  };
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1/", fetchImpl: async () => envelope([material]) });
  const [bound] = await gateway.listMaterials("project / a");
  assert.equal(bound.originalUrl, "http://api.test/api/v1/projects/project%20%2F%20a/materials/site-front/original");
  assert.equal(bound.assetUrl, undefined);
});

test("HTTP gateway does not construct an original URL when the external material root is unavailable", async () => {
  const material = {
    id: "site-front", versionId: "site-front-v1", fileName: "厂门正视.jpg", label: "厂门正视",
    availability: "available", isSimulated: true, sourceLabel: "脱敏模拟",
    businessPath: "现场照片/厂门正视.jpg", folderPath: "现场照片",
    originalAccess: { status: "not_configured", available: false },
    kind: "image", mimeType: "image/jpeg", pixelWidth: 1600, pixelHeight: 900,
    description: "脱敏模拟现场", focalArea: { x: 0, y: 0, width: 1, height: 1 }, assetUrl: "/p5-materials/legacy.jpg",
  };
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async () => envelope([material]) });
  const [unavailable] = await gateway.listMaterials("project-a");
  assert.equal(unavailable.originalUrl, undefined);
  assert.equal(unavailable.originalAccess.status, "not_configured");
});

test("HTTP gateway resolves one complete evidence selection group in one POST", async () => {
  const group = {
    id: "transaction::target::fact::e-1::e-2",
    dimensionId: "transaction",
    reviewTargetId: "target",
    factVersionId: "fact",
    targets: [
      { evidenceRef: "e-1", evidenceRefs: ["e-1", "e-2"], dimensionId: "transaction", reviewTargetId: "target", factVersionId: "fact" },
      { evidenceRef: "e-2", evidenceRefs: ["e-1", "e-2"], dimensionId: "transaction", reviewTargetId: "target", factVersionId: "fact" },
    ],
  };
  let call;
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async (url, init) => {
    call = { url: String(url), init };
    return envelope({ status: "located", selectionGroup: group, items: group.targets.map((target) => ({ target, evidence: { id: target.evidenceRef, label: target.evidenceRef, locator: null, locationStatus: "located", materialStatus: "confirmed" } })) });
  } });

  const result = await gateway.resolveEvidenceSelection("project-a", group);
  assert.equal(call.url, "http://api.test/api/v1/projects/project-a/evidence/resolve");
  assert.equal(call.init.method, "POST");
  assert.deepEqual(JSON.parse(call.init.body), group);
  assert.deepEqual(result.items.map((item) => item.evidence.id), ["e-1", "e-2"]);
});

test("HTTP gateway preserves API errors and never converts a failed HTTP request to mock data", async () => {
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async () => envelope(null, [{ code: "material_not_found", category: "not_found", message: "项目内不存在该材料。" }]) });
  await assert.rejects(() => gateway.readMaterial("project-a", "material-b"), (error) => error?.code === "not_found" && error?.httpStatus === 404 && error?.requestId === "request-p4");
});

test("HTTP gateway preserves stable API error fields for M2 recovery", async () => {
  const errors = [{ code: "hard_gate_blocked", category: "conflict", message: "blocked", field: "transition", details: { blockingRuleIds: ["H-03"], actualVersion: 7 } }];
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async () => envelope(null, errors) });
  await assert.rejects(() => gateway.readApprovalState("project-a"), (error) => error?.apiCode === "hard_gate_blocked" && error?.field === "transition" && error?.details?.blockingRuleIds?.[0] === "H-03" && error?.details?.actualVersion === 7);
  assert.deepEqual(gateway.getLastResponseMeta(), meta);
});

test("HTTP gateway turns stale-contract extra fields into an actionable restart message", async () => {
  const errors = [{ code: "validation_error", category: "validation", message: "请求字段校验失败。", field: "body.evidenceTargets", details: { errors: [{ field: "body.evidenceTargets", type: "extra_forbidden", message: "Extra inputs are not permitted" }] } }];
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async () => new Response(JSON.stringify({ data: null, meta, errors }), { status: 422, headers: { "Content-Type": "application/json" } }) });
  await assert.rejects(() => gateway.readApprovalState("project-a"), (error) => error?.message.includes("body.evidenceTargets") && error?.message.includes("Front/Back 接口版本可能不一致") && error?.httpStatus === 422);
});

test("MVP-R2 loads policy rules independently and refreshes every authoritative correction projection", async () => {
  const app = await readFile(new URL("src/App.tsx", root), "utf8");
  assert.match(app, /gateway\.readPolicyResults\(projectId/);
  assert.match(app, /setPolicyRules\(policies\)/);
  assert.match(app, /gateway\.readApprovalState\(data\.project\.id\)/);
  assert.match(app, /修正已成功、权威状态刷新失败/);
  assert.match(app, /clearIdempotencyKey\(operation/);
});

test("latest fact projection keeps only the deterministic highest version per fact key", async () => {
  const app = await readFile(new URL("src/App.tsx", root), "utf8");
  assert.match(app, /function latestFactVersionsByFactKey/);
  assert.match(app, /item\.version > current\.version/);
  assert.match(app, /setFacts\(latestFactVersionsByFactKey\(project\.facts\)\)/);
  assert.match(app, /版本冲突，且权威状态刷新失败/);
});

test("HTTP gateway sends server versions and idempotency keys on every M2 write", async () => {
  const calls = [];
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async (url, init) => {
    calls.push({ url: String(url), init });
    return envelope({ projectId: "project-a", version: 2, status: "submitted", hardGateStatus: "pass", blockingRuleIds: [], riskVeto: false, riskVetoRuleIds: [], updatedAt: "2026-01-01T00:00:00Z", isSimulated: true });
  } });
  await gateway.transitionApproval("project-a", { expectedVersion: 1, transition: "submit", requestedBy: "risk", idempotencyKey: "p4m2-12345678" });
  assert.equal(calls[0].url, "http://api.test/api/v1/projects/project-a/approval/transitions");
  assert.equal(calls[0].init.headers["Idempotency-Key"], "p4m2-12345678");
  assert.deepEqual(JSON.parse(calls[0].init.body), { expectedVersion: 1, transition: "submit", requestedBy: "risk" });
});

test("M2 consumes server-produced facts, events and approval state instead of local authority", async () => {
  const app = await readFile(new URL("src/App.tsx", root), "utf8");
  const dock = await readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8");
  assert.match(app, /result\.factVersion/);
  assert.match(app, /gateway\.readApprovalState/);
  assert.match(app, /gateway\.transitionApproval/);
  assert.doesNotMatch(app, /event-correction-\$\{Date\.now\(\)\}/);
  assert.match(dock, /正式链 v\$\{approval\.version\}/);
  assert.doesNotMatch(dock, /useState<ApprovalStatus>/);
});

test("dynamic first-twelve-rent evidence is used for both chart selection paths", async () => {
  const source = await readFile(new URL("src/components/RevenueCoreCharts.tsx", root), "utf8");
  assert.doesNotMatch(source, /evidence-transaction-rent-first-12/);
  assert.match(source, /evidenceRefs: rentEvidenceRefs/);
  assert.match(source, /revenue-cover-rent-input", rentEvidenceRefs/);
  const detailSource = await readFile(new URL("src/components/DimensionDetailView.tsx", root), "utf8");
  assert.match(detailSource, /financedEquipment\?\.repaymentSchedule\.firstTwelveEvidenceRefs/);
});
