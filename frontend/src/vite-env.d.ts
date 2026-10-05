/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GOONG_MAPTILES_KEY?: string;
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
