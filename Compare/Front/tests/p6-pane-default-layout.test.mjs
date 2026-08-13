import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("default collaboration layout keeps composers and shared facts usable at target viewports", async () => {
  const [app, collaboration, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.match(app, /const DEFAULT_COLLABORATION_HEIGHT = 400;/);
  assert.match(app, /const LEGACY_DEFAULT_COLLABORATION_HEIGHT = 175;/);
  assert.match(app, /const PERSISTED_LAYOUT_VERSION = 2;/);
  assert.match(app, /layout: \{ \.\.\.presentedProject\.layout, collaborationHeight: DEFAULT_COLLABORATION_HEIGHT \}/);
  assert.match(app, /sanitizePersistedLayout\(stored, scoredProject\.layout\)/);
  assert.match(app, /storedLayoutVersion < PERSISTED_LAYOUT_VERSION && persisted\.collaborationHeight === LEGACY_DEFAULT_COLLABORATION_HEIGHT/);
  assert.match(app, /persisted\.collaborationHeight = DEFAULT_COLLABORATION_HEIGHT/);
  assert.match(app, /setLayout\(\{ \.\.\.scoredProject\.layout, \.\.\.persisted \}\)/);
  assert.match(app, /localStorage\.setItem\(PERSISTED_LAYOUT_VERSION_KEY, String\(PERSISTED_LAYOUT_VERSION\)\)/);
  assert.match(app, /onResetLayout=\{\(\) => \{ setLayout\(\{ \.\.\.data\.layout \}\)/);

  assert.match(styles, /\.workbench-body:not\(\.is-collaboration-collapsed\)\s*\{[^}]*min\(var\(--layout-collaboration-height\), 38dvh, 400px\)/s);
  assert.match(styles, /\.collaboration-columns\s*\{[^}]*height:\s*100%;[^}]*overflow:\s*hidden;/s);
  assert.match(styles, /\.shared-column \.shared-fact-stream\s*\{[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;/s);
  assert.match(collaboration, /className="composer-wrap"/);
  assert.match(collaboration, /className="review-timeline shared-fact-stream"/);

  const defaultHeight = 400;
  const targetViewports = [
    { height: 1080, workbenchHeight: 1024 },
    { height: 739, workbenchHeight: 684 },
  ];
  for (const viewport of targetViewports) {
    const dockHeight = Math.min(defaultHeight, viewport.height * 0.38, 400);
    const columnHeight = dockHeight - 44;
    const reviewHeight = viewport.workbenchHeight - 44 - 8 - dockHeight;
    assert.ok(columnHeight > 220, `collaboration columns must leave positive composer and shared-fact space at ${viewport.height}px`);
    assert.ok(reviewHeight >= 350, `review canvas must remain readable at ${viewport.height}px`);
    assert.ok(44 + reviewHeight + 8 + dockHeight <= viewport.workbenchHeight + 0.001, `collaboration dock must remain inside the workbench at ${viewport.height}px`);
  }
});

test("default-height repair preserves corner collapse, edge snap and no-fullscreen contracts", async () => {
  const [app, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.match(styles, /\.workbench-body\.is-collaboration-collapsed\s*\{[^}]*grid-template-rows:[^}]*0 0;/s);
  assert.match(styles, /data-collaboration-edge="review"[\s\S]*grid-template-rows:[^;]*0 0;/);
  assert.match(styles, /data-collaboration-edge="collaboration"[\s\S]*grid-template-rows:\s*0 0 0 minmax\(0, 1fr\);/);
  assert.doesNotMatch(app, /fullscreen|Maximized|maximized/);
});
