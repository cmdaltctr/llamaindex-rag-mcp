import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// The production build is written into the Python package so the optional
// web transport can serve it from one origin. The directory is gitignored and
// force-included into the wheel. A relative base keeps asset URLs valid
// wherever FastAPI mounts the application.
// Under `npm run dev`, /v1 requests go to the local web transport (the
// `omrg web` default port). OMRG_API_URL points them at another address.
export default defineConfig(({ mode }) => ({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/v1": { target: loadEnv(mode, ".", "OMRG_").OMRG_API_URL || "http://127.0.0.1:8765" } },
  },
  build: {
    outDir: "../src/omrg/transports/api/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // Vitest replaces every CSS import with an empty string. The stylesheet
    // guard tests read CSS source with ?raw, so let those reads through.
    css: { include: [/\.css\?raw$/] },
    restoreMocks: true,
  },
}));
