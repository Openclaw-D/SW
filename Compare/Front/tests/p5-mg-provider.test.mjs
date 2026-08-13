import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { HttpWorkbenchGateway } from "../src/gateway/httpWorkbenchGateway.ts";
import { WorkbenchGatewayError } from "../src/gateway/workbenchGateway.ts";
import {
  cancelledModelGatewayRuntime,
  failedModelGatewayRuntime,
  modelGatewayRuntimeFromResult,
} from "../src/lib/modelGatewayState.ts";

const root = new URL("../", import.meta.url);
const meta = { requestId: "request-mg", schemaVersion: "1.0", dataStatus: "simulated", source: "deterministic_business_rules", disclaimer: "synthetic route envelope" };
const envelope = (data) => new Response(JSON.stringify({ data, meta, errors: [] }), { status: 200, headers: { "Content-Type": "application/json" } });

test("Model Gateway client maps capability and project-scoped run-status routes", async () => {
  const calls = [];
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async (url, init) => {
    calls.push({ url: String(url), init });
    return envelope([]);
  } });

  await gateway.listModelGatewayCapabilities();
  await gateway.readModelGatewayRun("project-01", "mgr-aabbcc");

  assert.deepEqual(calls.map((call) => call.url), [
    "http://api.test/api/v1/model-gateway/capabilities",
    "http://api.test/api/v1/projects/project-01/model-gateway/runs/mgr-aabbcc",
  ]);
  assert.ok(calls.every((call) => call.init.method === "GET"));
});

test("material intelligence client forwards AbortSignal without serializing it", async () => {
  const controller = new AbortController();
  let call;
  const gateway = new HttpWorkbenchGateway({ apiBase: "http://api.test/api/v1", fetchImpl: async (url, init) => {
    call = { url: String(url), init };
    return envelope({});
  } });
  await gateway.runMaterialIntelligence({
    projectId: "project-01",
    materialId: "material-image",
    materialVersionId: "material-image-v1",
    contextVersion: "p5-mg-provider-v1",
    taskGoals: ["observe"],
    expectedVersion: 1,
    idempotencyKey: "mg-provider-12345678",
    providerMode: "real",
  }, { signal: controller.signal });

  assert.equal(call.init.signal, controller.signal);
  assert.equal(JSON.parse(call.init.body).providerMode, "real");
  assert.equal(JSON.parse(call.init.body).idempotencyKey, undefined);
});

test("runtime state keeps provider, status, client latency and inputHash separate", () => {
  const stored = {
    runId: "mi-run-a",
    result: {
      status: "completed",
      inputHash: "a".repeat(64),
      modelInfo: { provider: "openai", model: "gpt-5.6-terra", modelVersion: null },
    },
  };
  assert.deepEqual(modelGatewayRuntimeFromResult(stored, 321), {
    runId: "mi-run-a",
    provider: "openai",
    status: "succeeded",
    latencyMs: 321,
    inputHash: "a".repeat(64),
    error: null,
    retryable: false,
    advisoryOnly: true,
  });
});

test("error taxonomy drives retry UI and cancellation remains non-retryable", () => {
  const running = { runId: null, provider: "openai", status: "running", latencyMs: null, inputHash: null, error: null, retryable: false, advisoryOnly: true };
  const failed = failedModelGatewayRuntime(new WorkbenchGatewayError("transport", "provider timeout", { apiCode: "model_provider_timeout", httpStatus: 504 }), 456, running);
  assert.equal(failed.status, "failed");
  assert.equal(failed.retryable, true);
  assert.equal(failed.latencyMs, 456);
  const cancelled = cancelledModelGatewayRuntime(12, running);
  assert.equal(cancelled.status, "cancelled");
  assert.equal(cancelled.retryable, false);
});

test("material page exposes honest advisory state, cancel and bounded status fields", async () => {
  const pane = await readFile(new URL("src/components/MaterialPane.tsx", root), "utf8");
  assert.match(pane, /provider/);
  assert.match(pane, /latency/);
  assert.match(pane, /inputHash/);
  assert.match(pane, /retryable/);
  assert.match(pane, /advisoryOnly: true/);
  assert.match(pane, /取消本次运行/);
  assert.match(pane, /必须经过人工确认 Gate/);
});
