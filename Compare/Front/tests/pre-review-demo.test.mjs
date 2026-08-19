import assert from "node:assert/strict";
import test from "node:test";
import { createPreReviewDemoState, estimateRingPresentation, rerunPreReviewDemo, savePreReviewDemoCheckpoint, submitPreReviewDemo, trafficLightTendencySegments, visibleTendencyWidths } from "../src/mock/preReviewDemo.ts";

test("four-way tendency bar protects every visible segment at five percent without changing truthful labels", () => {
  assert.deepEqual(visibleTendencyWidths({ 支持: 36, 退回: 14, 复核: 42, 否决: 8 }), { 支持: 36, 退回: 14, 复核: 42, 否决: 8 });
  const protectedWidths = visibleTendencyWidths({ 支持: 93, 退回: 4, 复核: 2, 否决: 1 });
  assert.equal(Object.values(protectedWidths).reduce((sum, value) => sum + value, 0), 100);
  assert.ok(Object.values(protectedWidths).every((value) => value >= 5));
  assert.equal(protectedWidths.退回, 5);
  assert.equal(protectedWidths.复核, 5);
  assert.equal(protectedWidths.否决, 5);
});

test("top summary projects four-way truth into three traffic-light segments", () => {
  const segments = trafficLightTendencySegments({ 支持: 36, 退回: 14, 复核: 42, 否决: 8 });
  assert.deepEqual(segments.map(({ label, value }) => [label, value]), [["通过", 36], ["复核", 56], ["否决", 8]]);
  assert.equal(segments.reduce((sum, segment) => sum + segment.visibleWidth, 0), 100);
  const protectedSegments = trafficLightTendencySegments({ 支持: 94, 退回: 3, 复核: 2, 否决: 1 });
  assert.ok(protectedSegments.every((segment) => segment.visibleWidth >= 5));
});

test("estimate ring uses two days as the five-color time baseline", () => {
  assert.deepEqual(estimateRingPresentation(2), { tone: "support", arc: 40 });
  assert.deepEqual(estimateRingPresentation(3), { tone: "attention", arc: 55 });
  assert.deepEqual(estimateRingPresentation(4), { tone: "confirm", arc: 70 });
  assert.deepEqual(estimateRingPresentation(5), { tone: "risk", arc: 85 });
  assert.deepEqual(estimateRingPresentation(6), { tone: "forbid", arc: 100 });
});

test("pre-review demo keeps truthful four-way distribution and five risk dimensions separate", () => {
  const state = createPreReviewDemoState("demo-project");
  assert.equal(Object.keys(state.tendencies).join(","), "支持,退回,复核,否决");
  assert.equal(Object.values(state.tendencies).reduce((sum, value) => sum + value, 0), 100);
  assert.equal(state.sixDimensions.length, 6);
  assert.deepEqual(state.sixDimensions.map((item) => item.id), ["compliance", "transaction", "production", "revenue", "debt", "cashflow"]);
  assert.deepEqual(state.sixDimensions.map((item) => item.name), ["合规", "交易", "生产", "营收", "负债", "流水"]);
  assert.equal(state.versionLabel, "尚未开始");
  assert.deepEqual(state.snapshots, []);
  assert.equal(state.disposition, "复核");
  assert.match(state.issues[1].detail, /不会自动关闭/);
});

test("pre-review workflow is immutable and reserves one checkpoint before final", () => {
  const initial = createPreReviewDemoState("p");
  const working = rerunPreReviewDemo(initial);
  assert.equal(initial.status, "not_started");
  assert.equal(working.status, "working");
  assert.equal(working.snapshots[0].version, "V1");
  const rerun = rerunPreReviewDemo(working);
  assert.equal(rerun.snapshots.length, 1);
  assert.equal(rerun.versionLabel, "V1 基线");
  assert.doesNotMatch(rerun.versionLabel, /工作态/);
  const checkpoint = savePreReviewDemoCheckpoint(working);
  assert.equal(checkpoint.snapshots.filter((item) => item.label === "阶段版本").length, 1);
  assert.equal(savePreReviewDemoCheckpoint(checkpoint).snapshots.length, checkpoint.snapshots.length);
  const submitted = submitPreReviewDemo(checkpoint);
  assert.equal(submitted.status, "submitted");
  assert.equal(submitted.snapshots.filter((item) => item.label === "最终").length, 1);
  assert.equal(submitted.snapshots.find((item) => item.label === "最终").version, "V3");
  assert.equal(submitPreReviewDemo(submitted).snapshots.length, submitted.snapshots.length);
  assert.deepEqual(rerunPreReviewDemo(submitted), submitted);
});
