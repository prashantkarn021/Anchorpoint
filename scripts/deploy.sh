#!/usr/bin/env bash
# Deploy to the Linode: back up SQLite, pull, rebuild, reconnect the bank, smoke.
# Needs DEPLOY_HOST (e.g. root@1.2.3.4) and BASE_URL (https://<domain>); reads them from .env if present.
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi

: "${DEPLOY_HOST:?set DEPLOY_HOST, e.g. root@1.2.3.4}"
: "${BASE_URL:?set BASE_URL, e.g. https://anchorpoint.example.com}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/anchorpoint}"
BRANCH="${DEPLOY_BRANCH:-main}"

ssh "$DEPLOY_HOST" DEPLOY_DIR="$DEPLOY_DIR" BRANCH="$BRANCH" 'bash -se' <<'REMOTE'
set -euo pipefail
cd "$DEPLOY_DIR"

# Back up the SQLite file before touching anything (no-op on the first deploy).
# </dev/null matters: this script arrives on stdin, and exec would otherwise swallow the rest of it.
docker compose exec -T api sh -c \
  'mkdir -p /data/backups && [ -f /data/anchorpoint.db ] && cp /data/anchorpoint.db "/data/backups/anchorpoint-$(date +%Y%m%d-%H%M%S).db" && echo "db backed up" || echo "no db to back up"' \
  </dev/null || echo "api not running, skipping backup"

git fetch --tags origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
docker compose up -d --build </dev/null
docker compose ps
echo "deployed: $(git log --oneline -1)"
REMOTE

sleep 10
# The bank connection is held in memory and drops on every restart; bring it back before the smoke test.
curl -fsS -m 60 -o /dev/null -X POST -H "Content-Type: application/json" -d '{}' \
  "${BASE_URL%/}/api/connections/bank/start" && echo "bank reconnected" || echo "bank NOT reconnected"
sleep 20
scripts/smoke.sh "$BASE_URL"
