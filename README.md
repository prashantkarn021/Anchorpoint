# Anchorpoint

Connect your accounts once. Anchorpoint's agent finds, reads and files your tax-home evidence, checks it against the IRS tax-home tests, warns you before a new contract puts your tax-free stipends at risk, and hands your CPA a clean, traceable packet.

Built at Hack Midwest. All people, merchants and accounts in the demo are synthetic. **Not tax advice; review with a CPA.**

## Live deployment

| | |
| --- | --- |
| URL | <https://172-232-25-241.sslip.io> |
| API | <https://172-232-25-241.sslip.io/api/health> |
| Host | Akamai Cloud (Linode) VM, Chicago, public IP `172.232.25.241` |
| Runs | `docker compose` from this repo's `main`, in `/opt/anchorpoint` |
| HTTPS | Caddy, with a Let's Encrypt certificate for the `sslip.io` name |

`sslip.io` is a public DNS service that resolves `172-232-25-241.sslip.io` to that IP, which gives the server a hostname Google OAuth accepts.

**The server does not update when a PR merges.** A deploy is a manual `git pull` and rebuild over SSH (see [Deploy](#deploy)), and only P4 has SSH access. Ask P4 to deploy or to check something on the server.

Code reaches the server from GitHub. Data reaches it from the services themselves: the server calls Gmail, Plaid and Akamai inference directly. Keys live in the server's `.env` and are not in this repo.

The bank connection is held in memory, so it drops on every deploy; connect it again from the Connections page or run a demo reset.

## Run it locally

You need Docker.

```bash
cp .env.example .env      # fill in the keys you have; the app starts with none
docker compose up -d --build
bash scripts/smoke.sh     # expects SMOKE GREEN; "wait" lines are endpoints not built or not configured here
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
| `web`   | Vite app built and served by Caddy (`frontend/`)       | everything else           |

All API routes live under `/api`. Caddy does not strip the prefix, so routers mount at `/api/...`.

## Repo layout

```text
README.md  .env.example  docker-compose.yml  Caddyfile  Makefile
contract/            openapi.json, fixtures/, CHANGELOG.md
backend/app/
  main.py            app + /api/health
  models.py          shared contract models
  connectors/        gmail.py, plaid.py, google_oauth.py (shared OAuth plumbing)
  vault/             encrypted token store
  routers/           oauth.py, demo.py, stubs.py (fixtures until the real endpoints land)
  agents/            triage and extraction
  rules/             deterministic engine
  seed/              persona -> synthetic emails and bank transactions
  sync/  ledger/  packet/
frontend/            Vite + React + TS + Tailwind (see frontend/README.md)
scripts/             personas/, seed_gmail.py, smoke.sh, deploy.sh, p1_* and p4_* gate checks
```

Python dependencies go in `backend/requirements.txt`.

## Environment variables

Copy `.env.example` to `.env`. `.env` is gitignored: never commit it and never paste keys into chat.

| Variable                                              | Owner | Purpose                                                       |
| ----------------------------------------------------- | ----- | ------------------------------------------------------------- |
| `SITE_ADDRESS`                                        | P4    | `:80` locally; the bare domain on the Linode (turns on HTTPS) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`            | P4    | Google OAuth web client                                       |
| `OAUTH_REDIRECT_URI`                                  | P4    | Must match a redirect URI registered on that client           |
| `FRONTEND_URL`                                        | P4    | Where the OAuth callback returns to; empty on the Linode      |
| `SEED_GOOGLE_CLIENT_ID`, `SEED_GOOGLE_CLIENT_SECRET`  | P4    | Seeder client (Desktop app); only `/api/demo/inject` uses it  |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`        | P1    | Plaid Sandbox                                                 |
| `INFERENCE_BASE_URL`, `INFERENCE_API_KEY`, `MODEL_ID` | P1    | Akamai hosted inference                                       |
| `TOKEN_ENC_KEY`                                       | P4    | Fernet key for the vault, which will not run without it       |
| `DATABASE_URL`                                        | P2    | SQLite path inside the `api` container                        |
| `ALLOWED_ORIGINS`                                     | P2    | Comma-separated CORS origins                                  |
| `DEPLOY_HOST`, `DEPLOY_DIR`, `BASE_URL`               | P4    | Only on the machine that runs `make deploy`                   |

## Google sign-in

Two OAuth clients in one Google Cloud project, kept apart on purpose:

- **App client (Web application):** asks for `gmail.readonly` only. `POST /api/connections/gmail/start` returns Google's consent URL, and `/api/oauth/callback` stores the tokens in the vault, encrypted.
- **Seeder client (Desktop app):** writes the synthetic inbox. The app never holds its `gmail.modify` grant; the server keeps only an insert-only grant for `/api/demo/inject`.

The consent screen is in Testing mode, so only listed test users can sign in and Google shows an "unverified app" warning. Grants expire after 7 days.

## Demo data

Everything comes from one spec, `scripts/personas/maya.yaml`, with dates relative to the day you seed.

```bash
# Preview the inbox without touching anything
docker compose run --rm -e PYTHONPATH=/srv -v ./scripts:/srv/scripts api     python scripts/seed_gmail.py --dry-run

# Fill the demo inbox (opens a Google sign-in for the demo account; --clear trashes what is there)
docker compose run --rm -p 127.0.0.1:8765:8765 -e PYTHONPATH=/srv     -v ./scripts:/srv/scripts -v /path/to/seeder_client.json:/secrets/seeder.json:ro     api python scripts/seed_gmail.py --client /secrets/seeder.json --clear
```

- **Bank:** `backend.app.seed.bank.bank_transactions(Persona.load("maya"))` returns the rows the Plaid connector plants in the sandbox.
- **Live email:** `POST /api/demo/inject` adds one fresh utility bill to the demo inbox.

## Deploy

`make deploy` SSHes to `DEPLOY_HOST`, backs up the SQLite file, pulls `main`, rebuilds the containers and runs the smoke test against `BASE_URL`. Set `DEPLOY_BRANCH` to deploy something other than `main`.

Rollback: check out the previous tag on the server and run `docker compose up -d --build`.

## Working in this repo

- `main` always builds. Branch as `feat/<module>-<thing>`, keep PRs small, merge when `make test` and `make smoke` pass.
- Changes to `contract/` or `rules/` need P2's OK.
- Commit every 30 to 45 minutes.
