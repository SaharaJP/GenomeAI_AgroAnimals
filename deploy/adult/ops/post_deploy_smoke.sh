#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-prod}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STACK_DIR="$ROOT_DIR/deploy/adult"
ENV_FILE="$STACK_DIR/env/runtime.env"

case "$PROFILE" in
  dev|test|stage|prod) ;;
  *)
    echo "unsupported profile: $PROFILE" >&2
    exit 2
    ;;
esac

COMPOSE=(docker compose -f "$STACK_DIR/compose.yaml" -f "$STACK_DIR/compose.${PROFILE}.yaml" --env-file "$ENV_FILE")

echo "[post_deploy_smoke] profile=$PROFILE"
"${COMPOSE[@]}" ps

for svc in reverse-proxy web-frontend backend-api worker scheduler postgres redis artifact-storage prometheus; do
  cid="$(${COMPOSE[@]} ps -q "$svc")"
  if [[ -z "$cid" ]]; then
    echo "service_not_found=$svc" >&2
    exit 3
  fi
done

curl -fsS http://127.0.0.1/healthz >/dev/null
curl -fsS http://127.0.0.1/readyz >/dev/null
curl -fsS http://127.0.0.1/api/healthz >/dev/null
curl -fsS http://127.0.0.1/api/readyz >/dev/null
curl -fsS http://127.0.0.1/metrics/prometheus >/dev/null

echo "[post_deploy_smoke] ok"
