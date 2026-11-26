import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI backend. Override with BACKEND_URL when it runs elsewhere.
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "localhost", // never exposed on the network (see README: dev-server advisories)
    port: 5173,
    strictPort: true,
    proxy: {
      // Browser -> http://localhost:5173/api/... -> FastAPI http://127.0.0.1:8000/...
      // Same-origin for the browser, so no CORS and every response header is readable.
      // Keys starting with "^" are regular expressions: only "/api/..." is proxied, never "/apifoo".
      "^/api/": {
        target: BACKEND_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    host: "localhost",
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    css: false,
    restoreMocks: true,
    // Full-page tests on a busy machine (many jsdom workers, background sync) can need more than the
    // 5 s default; findBy/waitFor get 3 s (src/test/setup.js). Passing tests finish as fast as before.
    testTimeout: 15000,
  },
});
