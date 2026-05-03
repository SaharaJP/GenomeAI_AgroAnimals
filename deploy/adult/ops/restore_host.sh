#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "usage: restore_host.sh <backup_dir>" >&2
  exit 2
fi
BACKUP_DIR="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STACK_DIR="$ROOT_DIR/deploy/adult"
COMPOSE=(docker compose -f "$STACK_DIR/compose.yaml" -f "$STACK_DIR/compose.prod.yaml" --env-file "$STACK_DIR/env/runtime.env")
cat "$BACKUP_DIR/postgres.sql" | "${COMPOSE[@]}" exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
if [[ -f "$BACKUP_DIR/runtime_artifacts.tgz" ]]; then
  cat "$BACKUP_DIR/runtime_artifacts.tgz" | "${COMPOSE[@]}" exec -T backend-api sh -lc 'tar -C /runtime -xzf -'
fi
set +e
"$STACK_DIR/ops/post_deploy_smoke.sh" prod
SMOKE_RC=$?
set -e
mkdir -p "$BACKUP_DIR"
cat > "$BACKUP_DIR/restore_metadata.json" <<MANIFEST
{"restored_at":"$(date -u +%Y%m%dT%H%M%SZ)","profile":"prod","source_backup_dir":"$BACKUP_DIR","post_restore_smoke_ok":$([[ "$SMOKE_RC" -eq 0 ]] && echo true || echo false)}
MANIFEST
cat "$BACKUP_DIR/restore_metadata.json" | "${COMPOSE[@]}" exec -T backend-api sh -lc 'mkdir -p /runtime/artifacts/system/maintenance && cat > /runtime/artifacts/system/maintenance/latest_restore_metadata.json'
python "$ROOT_DIR/scripts/verify_adult_restore_set.py" --artifacts-root "$ROOT_DIR/runtime/artifacts"
echo "restore_completed_from=$BACKUP_DIR"
