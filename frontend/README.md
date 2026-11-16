# AI Career Companion — Frontend

React + Vite single-page app for the AI Career Companion FastAPI backend.

**Status:** step F0 (foundation). The API client, authentication infrastructure, layouts, UI kit,
route guards, a backend health page and the test setup are in place. Feature screens are
placeholders that later steps replace (F1 sign-in … F12 dashboard).

## Stack

| Purpose | Package (exact version) |
|---|---|
| UI | React 18.3.1, React DOM 18.3.1 |
| Routing | React Router DOM 7.18.5 (declarative `<BrowserRouter>` mode) |
| HTTP | Axios 1.21.0 |
| Build / dev server | Vite 7.3.8, @vitejs/plugin-react 5.2.0 |
| Styling | Tailwind CSS 3.4.19, PostCSS 8.5.32, Autoprefixer 10.6.2 |
| Tests | Vitest 5.1.0, jsdom 25.0.1, React Testing Library 16.3.3 (+ @testing-library/dom 10.4.2, jest-dom 6.10.0, user-event 14.6.8), MSW 2.15.0 |

Versions are pinned exactly in `package.json`; `package-lock.json` is committed.

## Requirements

* Node.js 22.12 or newer (developed with Node 22.22.2) and npm 10. Vite 7 needs Node 20.19+/22.12+ and
  Vitest 5 needs Node 22.12+.
* The FastAPI backend running on `http://127.0.0.1:8000` for live use (tests do not need it).

## Install and run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Other scripts:

```bash
npm test             # run all tests once (Vitest + React Testing Library + MSW)
npm run test:watch   # re-run tests on change
npm run build        # production build into dist/
npm run preview      # serve the production build on http://localhost:4173
```

Open `http://localhost:5173/health` to check that the browser can reach the backend.

## How the frontend talks to FastAPI

```
Browser ──► http://localhost:5173/api/auth/login ──(Vite proxy)──► http://127.0.0.1:8000/auth/login
```

* All API calls use the base URL `/api` (`VITE_API_BASE_URL`, see `.env.example`).
* In development the Vite dev server forwards `/api/*` to FastAPI and strips the `/api` prefix
  (`vite.config.js`). The browser only talks to `localhost:5173`, so there is no CORS and
  headers such as `Content-Disposition` (download file names) and `Retry-After` are readable.
* Point the proxy at another backend with `BACKEND_URL=http://host:port npm run dev`.
* The dev server listens on `localhost` only.

### Running the backend for frontend development

The backend reads `.env` without overriding variables that are already set in the process, so
a development backend can be pointed at a separate database and index **without editing `.env`**
(decision D1/D2; the `career_companion_dev` database is set up in a later step):

```bash
DB_NAME=career_companion_dev FAISS_INDEX_DIR=<dev index folder> APP_BASE_URL=http://localhost:5173 \
  .venv/Scripts/python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

## Authentication design

* **Access token:** kept in memory only (`src/api/client.js`) and sent as `Authorization: Bearer …`.
* **Refresh token:** `sessionStorage` by default; `localStorage` only when "Remember me" is ticked
  (`src/utils/storage.js`). Passwords are never stored.
* **Expired access token:** the Axios interceptor refreshes once and retries the request. Requests
  that fail at the same time share a single refresh call, because the backend rotates refresh
  tokens (a second parallel refresh would use a revoked token).
* **Failed refresh:** the session is cleared and protected pages redirect to `/login?next=…`.
  The `next` value is only honoured for same-app paths (`src/utils/redirect.js`).
* **Roles:** `ProtectedRoute` requires a signed-in user; `RoleRoute` shows a 403 page to
  non-admins. The backend enforces the same rules.

## Error handling

`src/api/errors.js` turns every failure into an `ApiError` with `status`, `message`,
`fieldErrors` (from FastAPI 422 validation lists), `detail` (for object details such as a 409
duplicate with the existing id) and `retryAfter` (429). Network failures get a friendly message;
technical details are never shown.

## Project structure

```
src/
  api/          client.js (Axios + interceptors), errors.js, auth.js, system.js
  context/      AuthContext, ToastContext, ConfirmContext (promise-based confirm dialog)
  routes/       AppRoutes, ProtectedRoute, RoleRoute, navigation.js
  layouts/      AppLayout (sidebar + top bar), AuthLayout
  components/ui Button, Input, Select, Card, Badge, Spinner, Modal, ConfirmDialog,
                ErrorAlert, EmptyState, Pagination
  features/     system/ (Health, NotFound, Forbidden, ComingSoon), auth/ (F1 placeholder)
  utils/        storage.js, dates.js, redirect.js
  test/         setup.js, server.js, handlers.js (MSW)
```

## Testing

Tests run in jsdom with MSW intercepting every request; an unhandled request fails the test,
so no test can reach a real backend or database.

## Security notes

`npm audit` reports **0 vulnerabilities** (dependencies upgraded to Vite 7.3.8, Vitest 5.1.0 and
React Router 7.18.5). Defence in depth that stays in place:

* the dev and preview servers bind to `localhost` only;
* the Vitest UI and browser mode are not installed or used (`npm test` runs headless in Node);
* redirect targets (`?next=`) are validated before navigation (`src/utils/redirect.js`).

Nothing sensitive is configured in the frontend: anything in `VITE_*` variables is public.
