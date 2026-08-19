import path from "node:path";
import { fileURLToPath } from "node:url";
import { copyFile } from "node:fs/promises";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const frontDirectory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: path.resolve(frontDirectory, "showcase"),
  publicDir: path.resolve(frontDirectory, "public"),
  base: "./",
  plugins: [react(), {
    name: "showcase-readme",
    closeBundle: () => copyFile(
      path.resolve(frontDirectory, "showcase/README.md"),
      path.resolve(frontDirectory, "../Show/README.md"),
    ),
  }],
  build: {
    outDir: path.resolve(frontDirectory, "../Show"),
    emptyOutDir: true,
  },
});
