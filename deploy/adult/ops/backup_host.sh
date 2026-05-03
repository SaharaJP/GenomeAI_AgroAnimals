#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STACK_DIR="$ROOT_DIR/deploy/adult"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${GENOMEAI_BACKUP_DIR:-$ROOT_DIR/runtime/backups/$STAMP}"
mkdir -p "$OUT_DIR"
COMPOSE=(docker compose -f "$STACK_DIR/compose.yaml" -f "$STACK_DIR/compose.prod.yaml" --env-file "$STACK_DIR/env/runtime.env")

"${COMPOSE[@]}" exec -T postgres sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$OUT_DIR/postgres.sql"
"${COMPOSE[@]}" exec -T redis sh -lc 'redis-cli --rdb -' > "$OUT_DIR/redis.rdb"
"${COMPOSE[@]}" exec -T backend-api sh -lc 'tar -C /runtime -czf - artifacts logs web_storage 2>/dev/null || tar -C /runtime -czf - artifacts' > "$OUT_DIR/runtime_artifacts.tgz"
cat > "$OUT_DIR/manifest.json" <<MANIFEST
{"created_at":"$STAMP","profile":"prod","runtime_storage_backend":"postgres","queue_backend":"redis","artifact_storage_mode":"file_or_object_storage","components":["postgres_dump","redis_dump","artifact_archive"]}
MANIFEST

"${COMPOSE[@]}" exec -T backend-api sh -lc 'mkdir -p /runtime/artifacts/system/maintenance'
cat "$OUT_DIR/manifest.json" | "${COMPOSE[@]}" exec -T backend-api sh -lc 'cat > /runtime/artifacts/system/maintenance/latest_backup_metadata.json'
python "$ROOT_DIR/scripts/verify_adult_backup_set.py" --backup-dir "$OUT_DIR"
echo "backup_dir=$OUT_DIR"
