#!/usr/bin/env bash
# Smoke test. Usage: scripts/smoke.sh [base_url]   (default: $BASE_URL or http://localhost)
# Read-only apart from asking for a Google sign-in URL; it never injects or resets.
set -u

BASE="${1:-${BASE_URL:-http://localhost}}"
BASE="${BASE%/}"
fail=0
ok=0
waiting=0

OFFER='{"offer_text":"Extension offer: Fictional Front Range Regional Hospital, Denver CO. 17 more weeks. Lodging stipend $1,750/week, M&IE stipend $630/week."}'

# request <method> <path> [json body] -> sets $code and $body
request() {
  local out
  out=$(curl -sS --max-time 20 -X "$1" ${3:+-H "Content-Type: application/json" -d "$3"} \
    -w $'\n%{http_code}' "$BASE$2" 2>&1)
  code="${out##*$'\n'}"
  body="${out%$'\n'*}"
}

# check <name> <method> <path> <text the body must contain> [json body]
check() {
  request "$2" "$3" "${5:-}"
  if [[ "$code" == 2* && "$body" == *"$4"* ]]; then
    echo "ok    $1"
    ok=$((ok + 1))
  else
    echo "FAIL  $1  ($2 $3) -> HTTP $code ${body:0:160}"
    fail=1
  fi
}

# Like check, but the listed status codes mean "not built or not configured here" and do not fail.
# soft <name> <method> <path> <text> <codes that mean waiting> [json body]
soft() {
  request "$2" "$3" "${6:-}"
  if [[ " $5 " == *" $code "* ]]; then
    echo "wait  $1  (HTTP $code)"
    waiting=$((waiting + 1))
  elif [[ "$code" == 2* && "$body" == *"$4"* ]]; then
    echo "ok    $1"
    ok=$((ok + 1))
  else
    echo "FAIL  $1  ($2 $3) -> HTTP $code ${body:0:160}"
    fail=1
  fi
}

echo "Smoke: $BASE"
check "health"             GET  /api/health          '"status":"ok"'
check "web"                GET  /                    "Anchorpoint"
check "profile"            GET  /api/profile         '"home_address"'
check "connections: gmail" GET  /api/connections     '"provider":"gmail"'
check "connections: bank"  GET  /api/connections     '"provider":"bank"'
check "records non-empty"  GET  /api/records         '"source_id"'
check "assessment score"   GET  /api/assessment      '"score"'
check "monthly ledger"     GET  /api/ledger/monthly  '"month"'
# 503 = no Google client or vault key on this machine
soft  "gmail sign-in url"  POST /api/connections/gmail/start 'accounts.google.com' "503"
# 404/405 = endpoint not built yet
soft  "risk check verdict" POST /api/risk-check      '"verdict"' "404 405" "$OFFER"
soft  "activity feed"      GET  /api/activity        '"action"'  "404 405"

if [[ $fail -eq 0 ]]; then
  echo "SMOKE GREEN ($ok ok, $waiting waiting)"
else
  echo "SMOKE RED"
fi
exit $fail
