# Anchorpoint

Connect your accounts once. Anchorpoint's agent finds, reads and files your tax-home evidence, checks it against the IRS tax-home tests, warns you before a new contract puts your tax-free stipends at risk, and hands your CPA a clean, traceable packet.

Built at Hack Midwest. All people, merchants and accounts in the demo are synthetic. **Not tax advice; review with a CPA.**

## Run it locally

You need Docker.

```bash
cp .env.example .env      # fill in the keys you own; the scaffold runs with none
docker compose up -d --build
bash scripts/smoke.sh     # expects SMOKE GREEN
```

- App: <http://localhost>
- API: <http://localhost/api/health> (also directly on <http://localhost:8000> for the local OAuth redirect)

`make up`, `make down`, `make logs`, `make test`, `make smoke` and `make deploy` wrap the same commands.

## How the pieces fit

Three containers, one `docker-compose.yml`:

| Service | What it is                                             | Reached at                |
| ------- | ------------------------------------------------------ | ------------------------- |
| `caddy` | Front door. HTTPS on the Linode, plain HTTP locally    | ports 80 / 443            |
| `api`   | FastAPI backend, SQLite on the `api-data` volume       | `/api/*`                  |
| `web`   | Frontend (a placeholder page until the Vite app lands) | everything else           |

All API routes live under `/api`. Caddy does not strip the prefix, so routers mount at `/api/...`.

## Repo layout

```text
README.md  .env.example  docker-compose.yml  Caddyfile  Makefile
contract/            openapi.json, fixtures/, CHANGELOG.md
backend/app/
  main.py            app + /api/health
  routers/  connectors/  sync/  vault/  ledger/  rules/  agents/  packet/
frontend/            Vite + React + TS + Tailwind (placeholder for now)
scripts/             personas/, seed_*.py, smoke.sh, deploy.sh
```

Python dependencies go in `backend/requirements.txt`.

## Environment variables

Copy `.env.example` to `.env`. `.env` is gitignored: never commit it and never paste keys into chat.

| Variable                                              | Owner | Purpose                                                       |
| ----------------------------------------------------- | ----- | ------------------------------------------------------------- |
| `SITE_ADDRESS`                                        | P4    | `:80` locally; the bare domain on the Linode (turns on HTTPS) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`            | P4    | Google OAuth web client                                       |
| `OAUTH_REDIRECT_URI`                                  | P4    | Must match a redirect URI registered on that client           |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`        | P1    | Plaid Sandbox                                                 |
| `INFERENCE_BASE_URL`, `INFERENCE_API_KEY`, `MODEL_ID` | P1    | Akamai hosted inference                                       |
| `TOKEN_ENC_KEY`                                       | P2    | Fernet key for the token vault                                |
| `DATABASE_URL`                                        | P2    | SQLite path inside the `api` container                        |
| `ALLOWED_ORIGINS`                                     | P2    | Comma-separated CORS origins                                  |
| `DEPLOY_HOST`, `DEPLOY_DIR`, `BASE_URL`               | P4    | Only on the machine that runs `make deploy`                   |

## Deploy

`make deploy` SSHes to `DEPLOY_HOST`, backs up the SQLite file, pulls `main`, rebuilds the containers and runs the smoke test against `BASE_URL`. Set `DEPLOY_BRANCH` to deploy something other than `main`.

Rollback: check out the previous tag on the server and run `docker compose up -d --build`.

## Working in this repo

- `main` always builds. Branch as `feat/<module>-<thing>`, keep PRs small, merge when `make test` and `make smoke` pass.
- Changes to `contract/` or `rules/` need P2's OK.
- Commit every 30 to 45 minutes.
