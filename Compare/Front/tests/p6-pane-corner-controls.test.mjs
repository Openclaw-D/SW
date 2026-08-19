import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("three large panes use one fixed square corner anchor each", async () => {
  const [review, material, collaboration, styles] = await Promise.all([
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.equal((review.match(/pane-corner-anchor/g) ?? []).length, 3);
  assert.equal((material.match(/pane-corner-anchor/g) ?? []).length, 3);
  assert.equal((collaboration.match(/pane-corner-anchor/g) ?? []).length, 1);
  assert.match(review, /aria-expanded=\{false\}/);
  assert.match(review, /从左上角展开审查画布[\s\S]*pane-corner-glyph">↘/);
  assert.match(review, /收起审查画布至左上角[\s\S]*pane-corner-glyph">↖/);
  assert.match(material, /从右上角展开原始材料[\s\S]*pane-corner-glyph">↙/);
  assert.match(material, /收起原始材料至右上角[\s\S]*pane-corner-glyph">↗/);
  assert.match(collaboration, /aria-expanded=\{!collapsed\}/);
  assert.match(collaboration, /从右下角展开审批协同/);
  assert.match(collaboration, /收起审批协同至右下角/);
  assert.match(collaboration, /collapsed \? "↖" : "↘"/);

  assert.match(styles, /\.pane-corner-anchor,[\s\S]*?width:\s*44px;[\s\S]*?height:\s*44px;/);
  assert.match(styles, /\.review-corner-anchor\s*\{[^}]*left:\s*0;[^}]*top:\s*0;/s);
  assert.match(styles, /\.material-corner-anchor\s*\{[^}]*right:\s*0;[^}]*top:\s*0;/s);
  assert.match(styles, /\.collaboration-corner-anchor\s*\{[^}]*right:\s*0;[^}]*bottom:\s*0;/s);
  assert.match(styles, /\.workbench-body\.is-material-collapsed\s*\{[^}]*grid-template-columns:[^}]*0 0;/s);
  assert.match(styles, /\.workbench-body\.is-collaboration-collapsed\s*\{[^}]*grid-template-rows:[^}]*0 0;/s);
  assert.doesNotMatch(styles, /\.workbench-body\.is-material-collapsed\s*\{[^}]*grid-template-columns:[^}]*44px;/s);
  assert.doesNotMatch(styles, /\.workbench-body\.is-collaboration-collapsed\s*\{[^}]*grid-template-rows:[^}]*44px\s*;/s);
  assert.match(styles, /\.workbench-body\.is-middle-collapsed \.review-canvas\s*\{[^}]*position:\s*absolute;[^}]*left:\s*var\(--resolved-navigation-width\);[^}]*top:\s*0;/s);
  assert.match(styles, /\.review-canvas\.is-collapsed\s*\{[^}]*background:\s*transparent;/s);
  assert.match(styles, /\.material-pane\.is-collapsed\s*\{[^}]*position:\s*absolute;[^}]*right:\s*0;[^}]*top:\s*0;[^}]*background:\s*transparent;/s);
  assert.match(styles, /\.collaboration-dock\.is-collapsed\s*\{[^}]*position:\s*absolute;[^}]*right:\s*0;[^}]*bottom:\s*0;[^}]*background:\s*transparent;/s);
});

test("review and material fullscreen remain absent while chat has the approved maximize control", async () => {
  const [app, review, material, collaboration, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.doesNotMatch(app, /collaborationMaximized|is-collaboration-maximized|toggleCollaborationMaximized/);
  assert.doesNotMatch(review, /全屏|Maximized|panel-collapse-rail|rail-toggle-surface/);
  assert.doesNotMatch(material, /全屏|panel-collapse-rail|rail-toggle-surface/);
  assert.match(material, /chatMaximized/);
  assert.doesNotMatch(collaboration, /全屏|Maximized|maximized|onToggleMaximized|panel-maximize-trigger/);
  assert.doesNotMatch(styles, /panel-collapse-rail|rail-toggle-surface|review-expanded-toggle|material-collapse-trigger|material-rail-toggle|is-collaboration-maximized|collaboration-maximize-trigger|panel-maximize-trigger/);
  assert.match(styles, /\.material-pane\.has-project-chat\.is-chat-maximized/);
});
