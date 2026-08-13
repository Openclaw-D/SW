interface ImportMetaEnv {
  readonly VITE_COMPARE_API_BASE?: string;
  readonly VITE_COMPARE_GATEWAY?: "http" | "mock";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
