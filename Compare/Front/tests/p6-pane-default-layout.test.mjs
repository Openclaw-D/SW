import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("default responsive layout keeps both axes proportional at target viewports", async () => {
  const [app, material, styles, logic] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
    readFile(new URL("src/lib/workbenchLogic.ts", root), "utf8"),
  ]);

  assert.match(app, /const PERSISTED_LAYOUT_VERSION = 3;/);
  assert.match(logic, /materialRatio:\s*50/);
  assert.match(logic, /collaborationRatio:\s*50/);
  assert.match(logic, /PRESENTATION_LAYOUT_RATIOS[\s\S]*materialRatio:\s*30[\s\S]*collaborationRatio:\s*50/);
  assert.match(logic, /materialRatio:\s*\[10, 90\]/);
  assert.match(logic, /collaborationRatio:\s*\[10, 90\]/);
  assert.match(app, /sanitizePersistedLayout\(stored, layoutFallback\)/);
  assert.match(app, /setLayout\(\{ \.\.\.scoredProject\.layout, \.\.\.persisted \}\)/);
  assert.match(app, /localStorage\.setItem\(PERSISTED_LAYOUT_VERSION_KEY, String\(PERSISTED_LAYOUT_VERSION\)\)/);
  assert.match(app, /presentationMode \? PRESENTATION_LAYOUT_RATIOS : DEFAULT_LAYOUT_RATIOS/);

  assert.match(styles, /grid-template-columns:[^;]*var\(--layout-review-share\)[^;]*var\(--layout-material-share\)/);
  assert.match(styles, /grid-template-rows:[^;]*var\(--layout-source-share\)[^;]*var\(--layout-chat-share\)/);
  assert.match(material, /style=\{\{ "--layout-source-share": `\$\{100 - chatRatio\}fr`, "--layout-chat-share": `\$\{chatRatio\}fr` \}/);

  const targetViewports = [
    { width: 1920, height: 1080 },
    { width: 2560, height: 1440 },
  ];
  for (const viewport of targetViewports) {
    assert.equal(viewport.width * 0.3, viewport.width - viewport.width * 0.7);
    assert.equal(viewport.height * 0.5, viewport.height - viewport.height * 0.5);
  }
});

test("approved chat maximize covers the workbench below the project bar and restores in place", async () => {
  const [app, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.match(app, /chatMaximized/);
  assert.match(styles, /\.workbench-body\.is-chat-maximized\s*\{[^}]*overflow:\s*hidden;/s);
  assert.match(styles, /\.material-pane\.has-project-chat\.is-chat-maximized\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0;/s);
  assert.match(styles, /\.workbench-body\.is-chat-maximized > :not\(\.material-pane\)\s*\{[^}]*visibility:\s*hidden;/s);
});
