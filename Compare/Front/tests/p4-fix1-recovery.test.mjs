import assert from "node:assert/strict";
import test from "node:test";
import { initialMaterialLoadFailed, materialRecoveryFailed, materialRecoverySucceeded, replayMaterialRecovery, retryOnceAfterVersionConflict } from "../src/lib/recoveryState.ts";

const conflict = Object.assign(new Error("conflict"), { apiCode: "version_conflict" });

test("Fix1 retries exactly once after refresh with a new version and idempotency key", async () => {
  const attempts = []; const commands = []; let refreshed = null;
  const result = await retryOnceAfterVersionConflict({
    submit: async (attempt) => {
      const command = attempt
        ? { expectedVersion: 9, idempotencyKey: "key-after-refresh" }
        : { expectedVersion: 7, idempotencyKey: "key-before-refresh" };
      attempts.push(attempt); commands.push(command);
      if (!attempt) throw conflict;
      return command;
    },
    refresh: async () => [{ sequence: 8 }], isCurrent: () => true, onRefresh: (events) => { refreshed = events; },
  });
  assert.deepEqual(attempts, [0, 1]); assert.deepEqual(refreshed, [{ sequence: 8 }]);
  assert.deepEqual(result, { expectedVersion: 9, idempotencyKey: "key-after-refresh" });
  assert.notEqual(commands[0].expectedVersion, commands[1].expectedVersion);
  assert.notEqual(commands[0].idempotencyKey, commands[1].idempotencyKey);
});

test("Fix1 stops after a second conflict", async () => {
  let calls = 0;
  await assert.rejects(() => retryOnceAfterVersionConflict({ submit: async () => { calls += 1; throw conflict; }, refresh: async () => [], isCurrent: () => true, onRefresh: () => {} }), /并发冲突仍存在/);
  assert.equal(calls, 2);
});

test("Fix1 discards a recovered result after project switch", async () => {
  let refreshed = false;
  const result = await retryOnceAfterVersionConflict({ submit: async () => { throw conflict; }, refresh: async () => [1], isCurrent: () => false, onRefresh: () => { refreshed = true; } });
  assert.equal(result, null); assert.equal(refreshed, false);
});

test("Fix1 readMaterial failure remains local and a successful retry clears it", () => {
  assert.deepEqual(materialRecoveryFailed("读取材料失败", { kind: "material", materialId: "material-B" }), { error: "读取材料失败", retryable: true, fatal: null, operation: { kind: "material", materialId: "material-B" } });
  assert.deepEqual(materialRecoverySucceeded(), { error: null, retryable: false, fatal: null, operation: null });
});

test("Fix1 initial material failure leaves the workbench ready with a local retry", () => {
  const outcome = initialMaterialLoadFailed("首份材料读取失败", "material-A");
  assert.equal(outcome.workbench, "ready");
  assert.equal(outcome.recovery.fatal, null);
  assert.deepEqual(outcome.recovery.operation, { kind: "material", materialId: "material-A" });
});

test("Fix1 retries failed material B rather than the previously selected material A", () => {
  const calls = [];
  replayMaterialRecovery(materialRecoveryFailed("读取材料失败", { kind: "material", materialId: "material-B" }), {
    material: (id) => calls.push(`material:${id}`),
    evidence: () => calls.push("evidence"),
  });
  assert.deepEqual(calls, ["material:material-B"]);
});

test("Fix1 evidence retry replays evidence rather than a material selection", () => {
  const calls = [];
  const target = { dimensionId: "transaction", evidenceRef: "evidence-1", reviewTargetId: "target-1" };
  replayMaterialRecovery(materialRecoveryFailed("证据定位失败", { kind: "evidence", target }), {
    material: (id) => calls.push(`material:${id}`),
    evidence: (next) => calls.push(`evidence:${next.reviewTargetId}`),
  });
  assert.deepEqual(calls, ["evidence:target-1"]);
  assert.equal(materialRecoverySucceeded().operation, null);
});
