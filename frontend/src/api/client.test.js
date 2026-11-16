import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "../test/server";
import { refreshTokens } from "./auth";
import { api, configureAuth, getAccessToken, setAccessToken } from "./client";
import { ApiError } from "./errors";

// A protected endpoint that only accepts the token "fresh".
function protectedEndpoint(seen) {
  return http.get("/api/protected/:n", ({ request, params }) => {
    const auth = request.headers.get("authorization");
    seen.push({ n: params.n, auth });
    if (auth !== "Bearer fresh") return HttpResponse.json({ detail: "Invalid or expired access token" }, { status: 401 });
    return HttpResponse.json({ ok: params.n });
  });
}

describe("api client", () => {
  it("sends the in-memory access token", async () => {
    const seen = [];
    server.use(protectedEndpoint(seen));
    setAccessToken("fresh");
    const { data } = await api.get("/protected/1");
    expect(data).toEqual({ ok: "1" });
    expect(seen[0].auth).toBe("Bearer fresh");
  });

  it("refreshes ONCE for concurrent 401s and retries every request", async () => {
    const seen = [];
    server.use(protectedEndpoint(seen));
    setAccessToken("expired");
    const refresh = vi.fn(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      return "fresh";
    });
    configureAuth({ refresh, onAuthFailure: vi.fn() });

    const results = await Promise.all([1, 2, 3].map((n) => api.get(`/protected/${n}`)));

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(results.map((r) => r.data.ok)).toEqual(["1", "2", "3"]);
    expect(getAccessToken()).toBe("fresh");
    expect(seen.filter((s) => s.auth === "Bearer fresh")).toHaveLength(3);
  });

  describe("when the refresh itself fails", () => {
    // Uses the real refreshTokens() call so the refresh endpoint's response is normalised exactly
    // as in the app.
    function setup(refreshResponse) {
      const seen = [];
      let refreshCalls = 0;
      server.use(
        protectedEndpoint(seen),
        http.post("/api/auth/refresh", () => {
          refreshCalls += 1;
          return refreshResponse();
        }),
      );
      setAccessToken("expired");
      const onAuthFailure = vi.fn();
      configureAuth({ refresh: async () => (await refreshTokens("stored")).access_token, onAuthFailure });
      return { seen, onAuthFailure, refreshCalls: () => refreshCalls };
    }

    it("HTTP 401: signs out and rejects with the original 401", async () => {
      const t = setup(() => HttpResponse.json({ detail: "Refresh token is expired or revoked" }, { status: 401 }));
      await expect(api.get("/protected/1")).rejects.toMatchObject({ name: "ApiError", status: 401 });
      expect(t.onAuthFailure).toHaveBeenCalledTimes(1);
      expect(getAccessToken()).toBeNull();
      expect(t.refreshCalls()).toBe(1);
      expect(t.seen).toHaveLength(1); // no retry after a rejected refresh
    });

    it("network failure: keeps the session and reports the connection problem", async () => {
      const t = setup(() => HttpResponse.error());
      await expect(api.get("/protected/1")).rejects.toMatchObject({ name: "ApiError", status: 0 });
      expect(t.onAuthFailure).not.toHaveBeenCalled();
      expect(t.refreshCalls()).toBe(1);
      expect(t.seen).toHaveLength(1);
    });

    it("HTTP 5xx: keeps the session and reports the server error", async () => {
      const t = setup(() => HttpResponse.json({ detail: "Service temporarily unavailable" }, { status: 503 }));
      await expect(api.get("/protected/1")).rejects.toMatchObject({
        status: 503,
        message: "Service temporarily unavailable",
      });
      expect(t.onAuthFailure).not.toHaveBeenCalled();
      expect(t.refreshCalls()).toBe(1);
      expect(t.seen).toHaveLength(1);
    });

    it("does not loop: each new request tries at most one refresh", async () => {
      const t = setup(() => HttpResponse.json({}, { status: 500 }));
      await expect(api.get("/protected/1")).rejects.toMatchObject({ status: 500 });
      await expect(api.get("/protected/2")).rejects.toMatchObject({ status: 500 });
      expect(t.refreshCalls()).toBe(2);
      expect(t.seen).toHaveLength(2);
      expect(t.onAuthFailure).not.toHaveBeenCalled();
    });
  });

  it("does not retry the same request twice", async () => {
    const seen = [];
    server.use(http.get("/api/always-401", () => {
      seen.push(1);
      return HttpResponse.json({ detail: "nope" }, { status: 401 });
    }));
    setAccessToken("expired");
    configureAuth({ refresh: vi.fn(async () => "still-bad"), onAuthFailure: vi.fn() });
    await expect(api.get("/always-401")).rejects.toBeInstanceOf(ApiError);
    expect(seen).toHaveLength(2); // original + one retry
  });

  it("skips refresh for requests marked skipAuthRefresh (login, refresh, health)", async () => {
    server.use(http.post("/api/auth/login", () => HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 })));
    const refresh = vi.fn();
    configureAuth({ refresh, onAuthFailure: vi.fn() });
    await expect(api.post("/auth/login", {}, { skipAuthRefresh: true })).rejects.toMatchObject({
      status: 401,
      message: "Invalid email or password",
    });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("normalises network errors", async () => {
    server.use(http.get("/api/down", () => HttpResponse.error()));
    await expect(api.get("/down")).rejects.toMatchObject({ name: "ApiError", status: 0 });
  });
});
