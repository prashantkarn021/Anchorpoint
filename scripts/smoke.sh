#!/usr/bin/env bash
# Smoke test. Usage: scripts/smoke.sh [base_url]   (default: $BASE_URL or http://localhost)
set -u

BASE="${1:-${BASE_URL:-http://localhost}}"
BASE="${BASE%/}"
fail=0

# check <name> <path> <text the body must contain>
check() {
  local name="$1" path="$2" want="$3" body
  if body=$(curl -fsS --max-time 10 "$BASE$path" 2>&1) && [[ "$body" == *"$want"* ]]; then
    echo "ok    $name"
  else
    echo "FAIL  $name  ($path) -> ${body:0:200}"
    fail=1
  fi
}

echo "Smoke: $BASE"
check "health" "/api/health" '"status":"ok"'
check "web"    "/"           "Anchorpoint"

# Add as endpoints land (plan 13.4): /connections, /assessment, /records, /risk-check, upload.

if [[ $fail -eq 0 ]]; then echo "SMOKE GREEN"; else echo "SMOKE RED"; fi
exit $fail
