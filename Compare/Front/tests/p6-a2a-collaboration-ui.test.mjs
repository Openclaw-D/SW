import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("A2A collaboration uses three centered role words without activation copy", async () => {
  const [panel, css] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);
  assert.match(panel, /className="a2a-role-select"/);
  assert.match(panel, /formatAgentRole\(role, locale\)/);
  assert.match(panel, /setSelectedRole\("business"\)/);
  assert.match(panel, /setSelectedRole\("leadership"\)/);
  assert.match(panel, /setSelectedRole\("risk"\)/);
  assert.doesNotMatch(panel, />激活<|>当前</);
  assert.match(css, /\.a2a-role-header[^}]*justify-content: center/);
  assert.match(css, /\.a2a-role-select\[aria-pressed="true"\]/);
});

test("coordination keeps the six-dimension issue chain and date-first timeline", async () => {
  const panel = await readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8");
  assert.match(panel, /DIMENSION_IDS\.map/);
  assert.match(panel, /dimensionIssueCounts/);
  assert.match(panel, /rule\.result !== "pass"/);
  assert.match(panel, /rule\.evidenceTargets\.some\(\(target\) => target\.dimensionId === dimensionId\)/);
  assert.match(panel, /entry\.pending && entry\.dimensionId === dimensionId/);
  assert.match(panel, /formatShortDate\(item\.createdAt, locale\)/);
  assert.match(panel, /<time>\{group\.date\}<\/time>/);
  assert.match(panel, /className="a2a-dimension-chain"/);
});

test("all three roles have optional references compact tools and four-line composers", async () => {
  const [panel, app] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
  ]);
  for (const tool of ["Upload", "Voice", "MCP", "Skills"]) assert.match(panel, new RegExp(tool));
  assert.match(panel, /rows=\{4\}/);
  assert.match(panel, /reference \? <div className="a2a-reference"/);
  assert.match(panel, /onReference\(messageReference\(message, locale\)\)/);
  assert.match(panel, /onSubmitLeadership/);
  assert.match(app, /submitAgent\("leadership", message, reference\)/);
  assert.match(app, /onSubmitLeadership=\{submitLeadership\}/);
});

test("composer sends on plain Enter, keeps modified Enter for newline, and exposes recoverable processing states", async () => {
  const [panel, app] = await Promise.all([
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
  ]);
  assert.match(panel, /event\.key !== "Enter" \|\| event\.nativeEvent\.isComposing/);
  assert.match(panel, /event\.ctrlKey \|\| event\.metaKey \|\| event\.shiftKey \|\| event\.altKey/);
  assert.match(panel, /event\.preventDefault\(\);\s*void submit\(\);/);
  assert.match(panel, /已发送 · 正在处理/);
  assert.match(panel, /回复完成/);
  assert.match(panel, /发送失败 ·/);
  assert.match(panel, /aria-busy=\{pending\}/);
  assert.match(app, /Promise\.allSettled/);
  assert.match(app, /retryAgentRead/);
});
