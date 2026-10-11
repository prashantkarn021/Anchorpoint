# Anchorpoint web (P3)

React 19 + Vite + TypeScript (strict) + Tailwind v4, TanStack Query, native `EventSource` for the
activity feed, Recharts for the duplicate-expense chart. Contract types mirror
`backend/app/models.py` in `src/api/types.ts`.

## Run

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000 (VITE_API_PROXY to change)
npm test           # vitest
npm run build      # typecheck + production build to dist/
```

In Docker, `frontend/Dockerfile` builds the app and serves `dist/` with Caddy (SPA fallback in
`frontend/Caddyfile`). The root Caddy routes `/api/*` to the api service as before.

## API mode (`VITE_API_MODE`, build arg in the Dockerfile)

| Mode             | Behavior                                                                                                                                                                                                                                                                                   |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `auto` (default) | Calls the live API. An endpoint that is not implemented yet (FastAPI `{"detail":"Not Found"}`, 405) or unreachable (network, or a 502-504 from the proxy without a FastAPI `detail`) is served from `src/fixtures`. The header shows "Fixtures for N endpoints". Real errors (404 with another detail, 4xx, 500) are shown, never hidden. |
| `live`           | Never falls back. Use for the final demo build: `docker compose build --build-arg VITE_API_MODE=live web`.                                                                                                                                                                                 |
| `fixtures`       | Frontend only, no API calls.                                                                                                                                                                                                                                                               |

## What the UI expects where the plan leaves the shape open (P2: please confirm)

| Endpoint                             | Frontend sends / expects                                                                                                                                                                             |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /records`                       | Query params `type`, `factor`, `status`, `provider` (also filtered client-side, so ignoring them is safe)                                                                                            |
| `PATCH /records/{id}`                | JSON `{ "user_status": "confirmed" \| "rejected" \| "pending", "edits": { ... } }` (either key optional); edits support `type, date, amount, payee, address, factor, period_start, period_end`. The API client nests the UI's flat edit fields; returns the full `Record` with the new `AuditEvent` in `history` |
| `POST /connections/{id}/revoke`      | JSON `{ "delete_data": true \| false }`; `{id}` is the `Connection.id`                                                                                                                               |
| `POST /connections/{provider}/start` | Returns `{ "redirect_url": "https://accounts.google.com/..." }` (browser navigates) or `{ "redirect_url": null }` when the server connected directly (Plaid sandbox)                                 |
| `GET /api/oauth/callback`            | After Google, redirect the browser to `/connections?connected=gmail` (or `?error=access_denied`); the page shows a toast                                                                             |
| `GET /activity/stream`               | SSE, one JSON `AuditEvent` per message in `data:` (unnamed event, or named `activity`/`audit`)                                                                                                       |
| `POST /documents`                    | `multipart/form-data`, field `files` repeated; returns `Record[]`. Client limits: PDF/PNG/JPG/WEBP/HEIC, 10 MB, 10 files                                                                             |
| `POST /risk-check`                   | Exactly one of `{ "offer_text": "..." }` (max 4,000 chars) or `{ "assignment_id": "..." }`. Text must identify a known offered metro/facility; `Start:`/`End:` ISO dates and `Lodging stipend:`/`M&IE stipend:` amounts in `$number/week` or `/day` override the saved offer for the preview. Omitted terms use the saved offer. Rules decide the verdict; the auditor explains with a template fallback. Successful checks append a `risk_checked` audit event. |
| `POST /demo/reset`                   | Optional JSON `{ "persona": "maya" \| "sam" \| "luis" }` for the persona switcher; `Profile.id` should start with the persona (`maya-torres` is fine)                                                |
| `POST /packet`                       | Returns `{ "url": "..." }`, opened as a download                                                                                                                                                     |
| `GET /timeline`                      | Not used: the timeline is drawn from `GET /assignments`; R3/R5 findings come from `GET /assessment`                                                                                                  |

## Layout

```text
src/api/         types.ts (contract), client.ts (fetch + fallback), hooks.ts (queries, SSE)
src/fixtures/    synthetic personas (Maya, Sam, Luis) and an in-browser stand-in for the API
src/components/  Layout, AgentTasks (yes/no approvals), RecordDrawer (provenance), ActivityFeed, DuplicateExpenseChart, Findings, UploadDialog, ui
src/pages/       Overview, Records, ActivityPage, RiskCheck, Timeline, Packet, Connections, Privacy
src/lib/         format, timeline, agentTasks (pending records -> agent questions)
```
