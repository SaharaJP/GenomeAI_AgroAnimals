#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
USERNAME="${GENOMEAI_ANDROID_SMOKE_USERNAME:-admin}"
PASSWORD="${GENOMEAI_ANDROID_SMOKE_PASSWORD:-admin}"
DEVICE_ID="${GENOMEAI_ANDROID_DEVICE_ID:-android-smoke-1}"

login_json=$(curl -sS -X POST "$BASE_URL/api/app/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\",\"tenant_id\":\"default\",\"client_kind\":\"android\",\"device\":{\"device_id\":\"$DEVICE_ID\",\"device_label\":\"Android Smoke\",\"platform\":\"android\",\"app_version\":\"0.1.0\"}}")

access_token=$(python - <<'PY' "$login_json"
import json,sys
body=json.loads(sys.argv[1])
print(body['tokens']['access_token'])
PY
)
refresh_token=$(python - <<'PY' "$login_json"
import json,sys
body=json.loads(sys.argv[1])
print(body['tokens']['refresh_token'])
PY
)

curl -sS "$BASE_URL/api/app/v1/auth/me" -H "Authorization: Bearer $access_token" >/dev/null
curl -sS "$BASE_URL/api/app/v1/auth/mobile/runtime-proof" -H "Authorization: Bearer $access_token" >/dev/null

refresh_json=$(curl -sS -X POST "$BASE_URL/api/app/v1/auth/refresh" \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$refresh_token\",\"device\":{\"device_id\":\"$DEVICE_ID\",\"platform\":\"android\",\"app_version\":\"0.1.1\"}}")

new_access=$(python - <<'PY' "$refresh_json"
import json,sys
body=json.loads(sys.argv[1])
print(body['tokens']['access_token'])
PY
)

curl -sS -X POST "$BASE_URL/api/app/v1/auth/logout" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $new_access" \
  -d '{"all_devices": false}' >/dev/null

echo "android auth runtime smoke passed"
