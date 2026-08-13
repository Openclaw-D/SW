import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("three real layout dividers support pointer capture, keyboard values and edge snap", async () => {
  const [app, collaboration, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.equal((app.match(/role="separator"/g) ?? []).length, 2);
  assert.equal((collaboration.match(/role="separator"/g) ?? []).length, 1);
  assert.match(app, /Resize the review and original-material areas[\s\S]*aria-valuemax=\{100\}[\s\S]*aria-valuemin=\{0\}[\s\S]*aria-valuenow=\{materialAriaValue\}/);
  assert.match(app, /Resize the collaboration workspace[\s\S]*aria-valuenow=\{collaborationAriaValue\}/);
  assert.match(collaboration, /aria-label="调整业务与制度风控协同区域宽度"[\s\S]*aria-valuenow=\{a2aAriaValue\}/);
  assert.match(app, /divider\.setPointerCapture\(pointerId\)/);
  assert.match(collaboration, /divider\.setPointerCapture\(pointerId\)/);
  for (const source of [app, collaboration]) {
    assert.match(source, /pointercancel/);
    assert.match(source, /hasPointerCapture\(pointerId\)/);
    assert.match(source, /releasePointerCapture\(pointerId\)/);
    assert.match(source, /"Home", "End"/);
  }
  assert.match(app, /DIVIDER_SNAP_THRESHOLD = 24/);
  assert.match(collaboration, /A2A_SNAP_THRESHOLD = 24/);
  assert.match(styles, /data-material-edge="review"[\s\S]*grid-template-columns:[^;]*0 0;/);
  assert.match(styles, /data-material-edge="material"[\s\S]*grid-template-columns:[^;]* 0 0 minmax\(0, 1fr\);/);
  assert.match(styles, /data-collaboration-edge="review"[\s\S]*grid-template-rows:[^;]*0 0;/);
  assert.match(styles, /data-collaboration-edge="collaboration"[\s\S]*grid-template-rows:\s*0 0 0 minmax\(0, 1fr\);/);
  assert.match(styles, /data-a2a-edge="coordination"[\s\S]*grid-template-columns:\s*0 0 minmax/);
  assert.match(styles, /data-a2a-edge="business"[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\) 0 0 0;/);
  assert.match(styles, /data-material-edge="review"[\s\S]*\.divider-vertical[\s\S]*position:\s*absolute/);
  assert.match(styles, /data-collaboration-edge="review"[\s\S]*\.divider-horizontal[\s\S]*position:\s*absolute/);
  assert.match(styles, /data-a2a-edge="coordination"[\s\S]*\.divider-a2a[\s\S]*position:\s*absolute/);
});

test("divider edge fill does not reintroduce fullscreen controls or occupy collapsed corner tracks", async () => {
  const [app, review, material, collaboration, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/CollaborationDock.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  for (const source of [app, review, material, collaboration]) assert.doesNotMatch(source, /全屏|Fullscreen|Maximized|maximized/);
  assert.match(styles, /\.workbench-body\.is-material-collapsed\s*\{[^}]*0 0;/s);
  assert.match(styles, /\.workbench-body\.is-collaboration-collapsed\s*\{[^}]*0 0;/s);
  assert.match(styles, /\.material-pane\.is-collapsed\s*\{[^}]*position:\s*absolute;/s);
  assert.match(styles, /\.collaboration-dock\.is-collapsed\s*\{[^}]*position:\s*absolute;/s);
});
