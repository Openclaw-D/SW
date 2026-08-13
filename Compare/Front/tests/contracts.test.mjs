import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("keeps the six-dimension and evidence contracts explicit", async () => {
  const contract = await readFile(new URL("src/contracts/workbench.ts", root), "utf8");

  for (const dimension of [
    "compliance",
    "transaction",
    "production",
    "revenue",
    "debt",
    "cashflow",
  ]) {
    assert.match(contract, new RegExp(`"${dimension}"`));
  }

  assert.match(contract, /kind:\s*"excel"/);
  assert.match(contract, /sheet:\s*string/);
  assert.match(contract, /range:\s*string/);
  assert.match(contract, /kind:\s*"pdf"/);
  assert.match(contract, /page:\s*number/);
  assert.match(contract, /bbox:\s*NormalizedBBox/);
  assert.match(contract, /kind:\s*"image"/);
});

test("keeps P01 data local while presentation copy remains formal", async () => {
  const [gateway, mock, page, app, layout, components] = await Promise.all([
    readFile(new URL("src/gateway/mockWorkbenchGateway.ts", root), "utf8"),
    readFile(new URL("src/mock/mockCase.ts", root), "utf8"),
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("src/App.tsx", root), "utf8"),
    readFile(new URL("app/layout.tsx", root), "utf8"),
    Promise.all([
      "CollaborationDock.tsx",
      "DimensionDetailView.tsx",
      "MaterialPane.tsx",
      "NavigationRail.tsx",
      "ReviewCanvas.tsx",
      "TopBar.tsx",
    ].map((file) => readFile(new URL(`src/components/${file}`, root), "utf8"))).then((files) => files.join("\n")),
  ]);

  assert.doesNotMatch(gateway, /\bfetch\s*\(/);
  assert.doesNotMatch(page, /https?:\/\//);
  assert.match(mock, /isSimulated:\s*true/);
  assert.match(mock, /dataStatus:\s*"simulated"/);
  assert.match(mock, /disclaimer:\s*"[^"]*演示模拟/);
  assert.doesNotMatch([app, layout, components].join("\n"), /非真实|概念|本地 mock/);
});
