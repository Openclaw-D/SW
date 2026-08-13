import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  IMAGE_TO_3D_BOUNDARY,
  formatAgentRole,
  formatApprovalStatus,
  formatCanonicalLabel,
  formatCanonicalNarrative,
  formatCollaborationKind,
  formatDataStatus,
  formatDimensionName,
  formatEvidenceLocator,
  formatEvidenceLocatorSummary,
  formatFactValue,
  formatHardGateStatus,
  formatReviewEventType,
  formatRiskLevel,
} from "../src/lib/publicLocale.ts";

const clean = (value) => assert.doesNotMatch(value, /source value|unknown/i);

test("Collaboration roles, review events, runtime states, and canonical messages have explicit English semantics", () => {
  assert.equal(formatAgentRole("business", "en"), "Business");
  assert.equal(formatAgentRole("risk", "en"), "Risk control");
  assert.equal(formatAgentRole("leadership", "en"), "Leadership coordination");
  assert.equal(formatReviewEventType("business_correction_submitted", "en"), "Business correction submitted");
  assert.equal(formatCollaborationKind("pending_question", "en"), "Awaiting response");
  assert.equal(formatDataStatus("needs_review", "en"), "Human review required");
  assert.equal(formatCanonicalNarrative("业务补充证据或作出可追溯答复。", "en"), "Business should add evidence or provide a traceable response.");
});

test("Conclusion semantics keep score, decision, confidence, evidence, policy, hard gate, and advisory boundaries separate", () => {
  assert.equal(formatApprovalStatus("submitted", "en"), "Submitted");
  assert.equal(formatHardGateStatus("manual_review", "en"), "Manual review");
  assert.equal(formatRiskLevel("forbid", "en"), "Prohibited");
  assert.equal(formatDimensionName("cashflow", "en", "流水"), "Cash flow");
  assert.equal(formatCanonicalNarrative("系统生成·玻璃乙丑·节能钢化炉设备融资", "en"), "Synthetic Customer 22 · Glass processing · Energy-efficient glass tempering furnace financing");
  const advisory = formatCanonicalNarrative("本报告是对当前项目状态、证据、正式协同、制度 Gate 与单焦点 Agent 建议的只读汇总。Agent 内容始终为 advisory-only；报告不执行审批、不替代人工判断，也不证明真实生产模型质量或外部网络核验结果。", "en");
  assert.match(advisory, /read-only consolidation/i);
  assert.match(advisory, /advisory-only/i);
  assert.match(advisory, /does not approve/i);
  clean(advisory);
});

test("3D surfaces expose truthful unavailability, provider, job, and verified-provenance boundaries", () => {
  assert.match(IMAGE_TO_3D_BOUNDARY.en, /unavailable/i);
  assert.match(IMAGE_TO_3D_BOUNDARY.en, /provider/i);
  assert.match(IMAGE_TO_3D_BOUNDARY.en, /job/i);
  assert.match(IMAGE_TO_3D_BOUNDARY.en, /independently verified asset provenance/i);
  clean(IMAGE_TO_3D_BOUNDARY.en);
});

test("Six-dimension charts and tables format canonical labels, values, units, empty states, and legends by domain", () => {
  assert.equal(formatCanonicalLabel("确认收入", "en"), "Recognized income");
  assert.equal(formatCanonicalLabel("企业负债", "en"), "Corporate debt");
  assert.equal(formatCanonicalLabel("完工产量", "en"), "Completed output");
  assert.equal(formatFactValue(328.4, "万元", "en"), "328.4 CNY 10k");
  assert.equal(formatCanonicalLabel("营收趋势", "en"), "Revenue trend");
  assert.equal(formatCanonicalNarrative("2026-02-01 至 2026-02-28", "en"), "2026-02-01 to 2026-02-28");
  assert.equal(formatCanonicalNarrative("200直130.84W", "en"), "200 periods · direct lease · 130.84 CNY 10k");
  assert.equal(formatCanonicalNarrative("历史存量 + 本次融资；全局上限1000W", "en"), "Historical exposure + current financing; global limit 1000 CNY 10k");
  assert.equal(formatCanonicalNarrative("工商核验 / 主体与登记核验.pdf", "en"), "Business-registration verification / Quoted source text: 主体与登记核验.pdf");
});

test("Corrections, approvals, material facts, and evidence locators preserve canonical payload meaning", () => {
  assert.equal(formatReviewEventType("fact_version_created", "en"), "Fact version created");
  assert.equal(formatApprovalStatus("completed", "en"), "Completed");
  assert.equal(formatFactValue(true, null, "en"), "Yes");
  assert.equal(formatEvidenceLocator({ kind: "pdf", materialId: "m1", materialVersionId: "m1-v2", page: 7, bbox: { x: 0, y: 0, width: 1, height: 1 } }, "located", "en"), "Page 7");
  assert.equal(formatEvidenceLocatorSummary("第 7 页", "located", "en"), "Page 7");
  assert.equal(formatEvidenceLocatorSummary("待定位", "pending", "en"), "Location pending");
  assert.equal(formatCanonicalNarrative("未映射的真实原文", "en"), "Quoted source text: 未映射的真实原文");
  const activeCollaboration = readFileSync(new URL("../src/components/A2ACollaborationPanel.tsx", import.meta.url), "utf8");
  assert.match(activeCollaboration, /A2AFormalCorrection/);
  assert.match(activeCollaboration, /formatFactValue\(fact\.value, fact\.unit, locale\)/);
  assert.match(activeCollaboration, /Human Gate · creates a new fact version/);
  assert.match(activeCollaboration, /formatServiceMessage\(resultMessage, locale\)/);
});

test("Critical product components use component formatters while the DOM compatibility layer is decorative-only", () => {
  const componentPaths = [
    "A2ACollaborationPanel.tsx",
    "FinalConclusionReport.tsx",
    "EquipmentModelPreview.tsx",
    "SiteScenePreview.tsx",
    "ReviewCanvas.tsx",
    "MaterialPane.tsx",
  ];
  for (const file of componentPaths) {
    const source = readFileSync(new URL(`../src/components/${file}`, import.meta.url), "utf8");
    assert.match(source, /data-semantic-localized/);
    assert.doesNotMatch(source, /translateEnglishSurface/);
  }
  const localeSource = readFileSync(new URL("../src/lib/publicLocale.ts", import.meta.url), "utf8");
  assert.match(localeSource, /\[data-legacy-decorative-copy\]/);
  assert.doesNotMatch(localeSource, /createTreeWalker|document\.body\.textContent/);
});
