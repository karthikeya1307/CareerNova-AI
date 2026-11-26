import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { lazy, useState } from "react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { lazyPage } from "./AppRoutes";
import PageBoundary from "./PageBoundary";

// These tests throw on purpose. Keep React's and jsdom's reports of the caught errors out of the
// test output (the assertions below still check what the user sees).
let quiet;
const swallow = (event) => event.preventDefault();
beforeEach(() => {
  quiet = vi.spyOn(console, "error").mockImplementation(() => {});
  window.addEventListener("error", swallow);
});
afterEach(() => {
  window.removeEventListener("error", swallow);
  quiet.mockRestore();
});

function renderPage(element, path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <PageBoundary>{element}</PageBoundary>
    </MemoryRouter>,
  );
}

describe("PageBoundary (route-level code splitting)", () => {
  it("shows a loading state, then the lazy page", async () => {
    let resolve;
    const Page = lazy(() => new Promise((r) => { resolve = r; }));
    renderPage(<Page />);
    expect(screen.getByText("Loading page")).toBeInTheDocument();
    resolve({ default: () => <h1>Loaded page</h1> });
    expect(await screen.findByRole("heading", { name: "Loaded page" })).toBeInTheDocument();
  });

  it("explains a failed chunk download and offers a reload", async () => {
    const Page = lazy(() => Promise.reject(new TypeError("Failed to fetch dynamically imported module: /assets/Page.js")));
    renderPage(<Page />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This page couldn't be loaded");
    expect(screen.getByRole("button", { name: "Reload page" })).toBeInTheDocument();
  });

  it("shows a generic message when a page crashes while rendering", async () => {
    const Broken = () => {
      throw new Error("boom");
    };
    renderPage(<Broken />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on this page");
  });

  // Regression (F11): the boundary used to be keyed by path, which remounted a page whenever it
  // changed its own URL (/assistant -> /assistant/7) and lost its state.
  it("keeps a page's state when the page changes its own URL", async () => {
    function Chat() {
      const [text, setText] = useState("");
      const navigate = useNavigate();
      return (
        <>
          <label htmlFor="t">Draft</label>
          <input id="t" value={text} onChange={(e) => setText(e.target.value)} />
          <button type="button" onClick={() => navigate("/chat/7")}>
            Open 7
          </button>
        </>
      );
    }
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <PageBoundary>
          <Routes>
            <Route path="/chat/:id?" element={<Chat />} />
          </Routes>
        </PageBoundary>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Draft"), "keep me");
    await user.click(screen.getByRole("button", { name: "Open 7" }));
    expect(screen.getByLabelText("Draft")).toHaveValue("keep me");
  });

  it("clears the error after navigating to another page", async () => {
    function Broken() {
      throw new Error("boom");
    }
    // The "Leave" button sits outside the boundary, like the app's sidebar links.
    function Harness() {
      const navigate = useNavigate();
      return (
        <>
          <button type="button" onClick={() => navigate("/ok")}>
            Leave
          </button>
          <PageBoundary>
            <Routes>
              <Route path="/broken" element={<Broken />} />
              <Route path="/ok" element={<h1>Healthy page</h1>} />
            </Routes>
          </PageBoundary>
        </>
      );
    }
    render(
      <MemoryRouter initialEntries={["/broken"]}>
        <Harness />
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on this page");
    await user.click(screen.getByRole("button", { name: "Leave" }));
    expect(await screen.findByRole("heading", { name: "Healthy page" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// Regression (F11): the lazy page wrapper must never swap component types on re-render, or a page
// that first mounted while its chunk was downloading would remount (and lose state) on a URL change.
describe("lazyPage", () => {
  it("keeps state across URL changes when it mounted before its module loaded", async () => {
    let resolve;
    function Chat() {
      const [text, setText] = useState("");
      const navigate = useNavigate();
      return (
        <>
          <label htmlFor="d">Draft</label>
          <input id="d" value={text} onChange={(e) => setText(e.target.value)} />
          <button type="button" onClick={() => navigate("/chat/9")}>
            Open 9
          </button>
        </>
      );
    }
    const Page = lazyPage(() => new Promise((r) => { resolve = r; }));
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <PageBoundary>
          <Routes>
            <Route path="/chat/:id?" element={<Page />} />
          </Routes>
        </PageBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText("Loading page")).toBeInTheDocument();
    resolve({ default: Chat });
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Draft"), "still here");
    await user.click(screen.getByRole("button", { name: "Open 9" }));
    expect(screen.getByLabelText("Draft")).toHaveValue("still here");
  });

  it("renders without suspending once preloaded", async () => {
    const Page = lazyPage(() => Promise.resolve({ default: () => <h1>Ready</h1> }));
    await Page.preload();
    renderPage(<Page />);
    expect(screen.getByRole("heading", { name: "Ready" })).toBeInTheDocument();
    expect(screen.queryByText("Loading page")).not.toBeInTheDocument();
  });
});
