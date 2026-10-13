import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The production build is written into the Python package so the optional
// web transport can serve it from one origin. The directory is gitignored and
// force-included into the wheel. A relative base keeps asset URLs valid
// wherever FastAPI mounts the application.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: "../src/omrg/transports/api/static",
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
