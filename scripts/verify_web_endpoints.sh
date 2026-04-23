#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

function _check() {
  local path="$1"
  local url="${BASE_URL}${path}"
  local code
  code="$(curl -sS -o /tmp/genomeai_verify_body.json -w '%{http_code}' "$url" || true)"
  if [[ "$code" != "200" ]]; then
    echo "[verify_web_endpoints] FAIL $url (http=$code)"
    if [[ -s /tmp/genomeai_verify_body.json ]]; then
      echo "--- body ---"
      cat /tmp/genomeai_verify_body.json
      echo "------------"
    fi
    exit 2
  fi
  echo "[verify_web_endpoints] OK  $url"
}

_check "/healthz"
_check "/readyz"
_check "/api/observability"

echo "[verify_web_endpoints] ALL OK"
