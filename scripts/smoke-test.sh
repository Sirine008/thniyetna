#!/usr/bin/env sh
set -eu

API="${API_URL:-http://localhost:8000}"
PASSWORD="${BOOTSTRAP_PASSWORD:-Thniyetna2026!}"

curl -fsS "$API/health" >/dev/null
curl -fsS "$API/system/ready" | grep -q '"status":"ready"'
curl -fsS -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"transport.supervisor\",\"password\":\"$PASSWORD\"}" \
  | grep -q 'access_token'
printf 'THNIYETNA smoke test passed.\n'
