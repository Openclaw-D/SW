import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const root = new URL("../", import.meta.url);
const read = (file) => readFile(new URL(file, root), "utf8");

test("showcase entry is a static mock-only App entry", async () => {
  const [experience, main, html, config, packageJson] = await Promise.all([
    read("src/ShowcaseExperience.tsx"),
    read("src/showcase-main.tsx"),
    read("showcase/index.html"),
    read("vite.showcase.config.ts"),
    read("package.json"),
  ]);
  assert.match(experience, /MockWorkbenchGateway/);
  assert.match(experience, /new MockWorkbenchGateway\(20260812, \[canonicalProject\]\)/);
  assert.match(experience, /locale="zh-CN"/);
  assert.match(experience, /PublicLocaleContext\.Provider value="zh-CN"/);
  assert.match(experience, /presentationMode/);
  assert.doesNotMatch(experience, /onLocaleChange/);
  assert.doesNotMatch(experience, /mock\/synthetic|仅供产品沟通/);
  assert.doesNotMatch(experience, /HttpWorkbenchGateway|AuthenticationClient|ProjectExperience/);
  assert.match(main, /ShowcaseExperience/);
  assert.match(main, /localStorage\.setItem\(PUBLIC_LOCALE_KEY, "zh-CN"\)/);
  assert.match(html, /src="\.\.\/src\/showcase-main\.tsx"/);
  assert.match(config, /root: path\.resolve\(frontDirectory, "showcase"\)/);
  assert.match(config, /publicDir: path\.resolve\(frontDirectory, "public"\)/);
  assert.match(config, /base: "\.\/"/);
  assert.match(config, /outDir: path\.resolve\(frontDirectory, "\.\.\/Show"\)/);
  assert.match(packageJson, /"showcase:dev"\s*:/);
  assert.match(packageJson, /"showcase:build"\s*:/);
});

test("showcase build emits one portable Chinese standalone page", async () => {
  const [packageJson, builder, showcaseHtml] = await Promise.all([
    read("package.json"),
    read("scripts/build-showcase-standalone.mjs"),
    read("showcase/index.html"),
  ]);

  assert.match(packageJson, /node scripts\/build-showcase-standalone\.mjs/);
  assert.match(builder, /见微-前端展示页\.html/);
  assert.match(builder, /replaceAll\("\/mock-materials\/", "\.\/mock-materials\/"\)/);
  assert.match(builder, /replaceAll\("\/reference-images\/", "\.\/reference-images\/"\)/);
  assert.match(builder, /data:\$\{mimeType\};base64,/);
  assert.match(builder, /bytes\.toString\("base64"\)/);
  assert.match(showcaseHtml, /<title>见微 · 项目预审工作台<\/title>/);
  assert.doesNotMatch(showcaseHtml, /signal-council|脱敏演示/);
});
