#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-prod}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STACK_DIR="$ROOT_DIR/deploy/adult"
ENV_FILE="$STACK_DIR/env/runtime.env"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_PATH="/runtime/artifacts/support_bundles/support_bundle_${PROFILE}_${STAMP}.zip"

case "$PROFILE" in
  dev|test|stage|prod) ;;
  *)
    echo "unsupported profile: $PROFILE" >&2
    exit 2
    ;;
esac

COMPOSE=(docker compose -f "$STACK_DIR/compose.yaml" -f "$STACK_DIR/compose.${PROFILE}.yaml" --env-file "$ENV_FILE")

"${COMPOSE[@]}" exec -T backend-api \
  python -m genomeai.cli support-bundle \
  --project-root /app \
  --artifacts /runtime/artifacts \
  --web-storage /runtime/web_storage \
  --tmp-root /tmp \
  --out "$OUT_PATH"

echo "support_bundle=$OUT_PATH"
