import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { configureAuth, setAccessToken } from "../api/client";
import { server } from "./server";

// findBy*/waitFor wait up to 1 s by default; under CPU load a route transition (e.g. the redirect
// to /login after a session expires) can take longer. Assertions are unchanged.
// Paired with testTimeout: 15000 in vite.config.js so a longer wait never hits the per-test limit.
configure({ asyncUtilTimeout: 3000 });

// Unhandled requests fail the test: no test may reach a real backend.
// Route pages are lazy-loaded in the app (F11). Load their modules once per test file before the
// tests start, so a test never waits on a slow first dynamic import (which, under CPU load, can
// outlast findBy waits). The lazy/Suspense path itself is covered by src/routes/PageBoundary.test.jsx.
beforeAll(async () => {
  server.listen({ onUnhandledRequest: "error" });
  const { preloadAllPages } = await import("../routes/AppRoutes");
  await preloadAllPages();
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  setAccessToken(null);
  configureAuth({});
  window.sessionStorage.clear();
  window.localStorage.clear();
});

afterAll(() => server.close());
