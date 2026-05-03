#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REPORT_ROOT="${1:-$ROOT_DIR/artifacts/restore_drills_ci}"
ARTIFACTS_ROOT="${GENOMEAI_ARTIFACTS_ROOT:-$ROOT_DIR/artifacts}"
WEB_STORAGE="${GENOMEAI_WEB_STORAGE:-$ROOT_DIR/web_cabinet/storage}"
DB_PATH="${GENOMEAI_WEB_DB_PATH:-$WEB_STORAGE/web.db}"

mkdir -p "$REPORT_ROOT"

echo "[restore_drill] project_root=$ROOT_DIR"
echo "[restore_drill] report_root=$REPORT_ROOT"
echo "[restore_drill] artifacts_root=$ARTIFACTS_ROOT"
echo "[restore_drill] web_storage=$WEB_STORAGE"

PYTHONPATH=src python -m genomeai.cli restore-drill \
  --project-root "$ROOT_DIR" \
  --artifacts "$ARTIFACTS_ROOT" \
  --web-storage "$WEB_STORAGE" \
  --db-path "$DB_PATH" \
  --report-root "$REPORT_ROOT"
