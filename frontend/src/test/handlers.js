import { http, HttpResponse } from "msw";

// Default API mocks. Tests override them with server.use(...).
export const handlers = [
  http.get("/api/health", () =>
    HttpResponse.json({ status: "Healthy", database: "test-db", message: "Database connection successful" }),
  ),
];
