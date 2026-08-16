import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("both responsive dividers keep pointer capture, keyboard values and a 10 to 90 percent range", async () => {
  const [app, material, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.equal((app.match(/role="separator"/g) ?? []).length, 1);
  assert.equal((material.match(/role="separator"/g) ?? []).length, 1);
  assert.match(app, /Resize the review and original-material areas[\s\S]*aria-valuemax=\{LAYOUT_LIMITS\.materialRatio\[1\]\}[\s\S]*aria-valuemin=\{LAYOUT_LIMITS\.materialRatio\[0\]\}[\s\S]*aria-valuenow=\{materialAriaValue\}/);
  assert.match(material, /Resize original materials and project group chat[\s\S]*aria-valuemax=\{LAYOUT_LIMITS\.collaborationRatio\[1\]\}[\s\S]*aria-valuemin=\{LAYOUT_LIMITS\.collaborationRatio\[0\]\}/);
  assert.doesNotMatch(app, /Resize the collaboration workspace|<CollaborationDock/);
  for (const source of [app, material]) {
    assert.match(source, /divider\.setPointerCapture\(pointerId\)/);
    assert.match(source, /pointercancel/);
    assert.match(source, /hasPointerCapture\(pointerId\)/);
    assert.match(source, /releasePointerCapture\(pointerId\)/);
    assert.match(source, /"Home", "End"/);
  }
  assert.match(app, /LAYOUT_LIMITS\.materialRatio/);
  assert.doesNotMatch(app, /DIVIDER_SNAP_THRESHOLD|readableMaximum|420 - 8/);
  assert.match(styles, /var\(--layout-review-share\)[\s\S]*var\(--layout-material-share\)/);
  assert.match(styles, /\.workbench-body\.has-embedded-chat[\s\S]*grid-template-rows:\s*44px minmax\(0, 1fr\)/);
});

test("embedded chat has divider collapse plus the approved workspace maximize and restore control", async () => {
  const [app, review, material, chat, styles] = await Promise.all([
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("src/components/ReviewCanvas.tsx", root), "utf8"),
    readFile(new URL("src/components/MaterialPane.tsx", root), "utf8"),
    readFile(new URL("src/components/A2ACollaborationPanel.tsx", root), "utf8"),
    readFile(new URL("src/styles/app.css", root), "utf8"),
  ]);

  assert.match(styles, /\.workbench-body\.is-material-collapsed\s*\{[^}]*0 0;/s);
  assert.match(styles, /\.material-pane\.is-collapsed\s*\{[^}]*position:\s*absolute;/s);
  assert.match(styles, /\.material-pane\.has-project-chat\.is-chat-collapsed[\s\S]*44px/);
  assert.match(material, /is-source-collapsed/);
  assert.match(material, /onToggleMaximized/);
  assert.match(chat, /a2a-chat-toggle/);
  assert.match(chat, /Fullscreen project group chat/);
  assert.match(chat, /Exit project group chat fullscreen/);
  assert.match(app, /is-chat-maximized/);
  assert.match(styles, /\.material-pane\.has-project-chat\.is-chat-maximized[\s\S]*position:\s*absolute/);
  assert.doesNotMatch(app, /<CollaborationDock/);
});
