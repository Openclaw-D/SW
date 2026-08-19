import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const showDirectory = path.resolve(frontDirectory, "../Show");
const assetDirectory = path.join(showDirectory, "assets");
const assetFiles = await readdir(assetDirectory);
const cssFile = assetFiles.find((file) => file.endsWith(".css"));
const scriptFile = assetFiles.find((file) => file.endsWith(".js"));

if (!cssFile || !scriptFile) throw new Error("展示构建缺少 CSS 或 JavaScript 产物。");

const [cssSource, scriptSource] = await Promise.all([
  readFile(path.join(assetDirectory, cssFile), "utf8"),
  readFile(path.join(assetDirectory, scriptFile), "utf8"),
]);

const imageMimeTypes = new Map([
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".png", "image/png"],
  [".webp", "image/webp"],
]);

let portableScript = scriptSource
  .replaceAll("/mock-materials/", "./mock-materials/")
  .replaceAll("/reference-images/", "./reference-images/")
  .replaceAll("</script", "<\\/script");

for (const directoryName of ["mock-materials", "reference-images"]) {
  const directoryPath = path.join(showDirectory, directoryName);
  const entries = await readdir(directoryPath, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile()) continue;
    const mimeType = imageMimeTypes.get(path.extname(entry.name).toLowerCase());
    if (!mimeType) continue;
    const bytes = await readFile(path.join(directoryPath, entry.name));
    const dataUrl = `data:${mimeType};base64,${bytes.toString("base64")}`;
    portableScript = portableScript
      .replaceAll(`./${directoryName}/${entry.name}`, dataUrl)
      .replaceAll(`/${directoryName}/${entry.name}`, dataUrl);
  }
}

const portableCss = cssSource.replaceAll("</style", "<\\/style");
const standaloneHtml = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="见微项目预审工作台前端展示页" />
    <link rel="icon" href="data:," />
    <title>见微 · 项目预审工作台</title>
    <style>${portableCss}</style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module">${portableScript}</script>
  </body>
</html>
`;

await writeFile(path.join(showDirectory, "见微-前端展示页.html"), standaloneHtml, "utf8");
