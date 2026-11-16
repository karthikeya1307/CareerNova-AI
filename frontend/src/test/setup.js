import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { configureAuth, setAccessToken } from "../api/client";
import { server } from "./server";

// Unhandled requests fail the test: no test may reach a real backend.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
  setAccessToken(null);
  configureAuth({});
  window.sessionStorage.clear();
  window.localStorage.clear();
});

afterAll(() => server.close());
