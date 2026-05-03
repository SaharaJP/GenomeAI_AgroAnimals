#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WORKDIR="${1:-$ROOT_DIR/runtime/backup_restore_check}"

ART="$WORKDIR/artifacts"
WEB="$WORKDIR/web_storage"
ZIP="$WORKDIR/backup.zip"

export ART WEB

echo "[backup_restore_check] workdir=$WORKDIR"
rm -rf "$WORKDIR"
mkdir -p "$ART" "$WEB"

echo "[backup_restore_check] 1) prepare minimal artifacts + sqlite"
python - <<'PY'
import os
from pathlib import Path
from core.infra.web_db import connect, init_db

art = Path(os.environ['ART'])
web = Path(os.environ['WEB'])
(art / 'dv_backup_smoke_001' / 'canonical').mkdir(parents=True, exist_ok=True)
(art / 'dv_backup_smoke_001' / 'canonical' / 'animals.csv').write_text('animal_id\nA001\n', encoding='utf-8')
(web / 'uploads').mkdir(parents=True, exist_ok=True)
(web / 'logs').mkdir(parents=True, exist_ok=True)
(web / 'config_overrides').mkdir(parents=True, exist_ok=True)
(web / 'uploads' / 'sample.txt').write_text('upload', encoding='utf-8')
conn = connect(web / 'web.db')
try:
    init_db(conn)
    conn.execute(
        "INSERT INTO jobs(public_job_id, queue_name, pipeline_key, kind, status, created_at, user, command, args_json, log_path, artifacts_json, result_json, tenant_id, user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            'job_backup_smoke_001', 'default', 'qc', 'qc', 'done',
            '2026-03-09T00:00:00+00:00', 'operator', 'python -m genomeai qc', '{}',
            'logs/job_backup_smoke_001.log', '[]', '{}', 'default', 1,
        ),
    )
    conn.commit()
finally:
    conn.close()
PY

echo "[backup_restore_check] 2) backup -> $ZIP"
python -m genomeai backup --artifacts "$ART" --web-storage "$WEB" --db-path "$WEB/web.db" --out "$ZIP"

echo "[backup_restore_check] 3) wipe destinations"
mv "$ART" "${ART}_WIPED"
mv "$WEB" "${WEB}_WIPED"
mkdir -p "$ART" "$WEB"

echo "[backup_restore_check] 4) restore + smoke-check"
python -m genomeai restore --backup "$ZIP" --artifacts "$ART" --web-storage "$WEB" --db-path "$WEB/web.db" --force --smoke-check

echo "[backup_restore_check] 5) verify essential files"
test -f "$WEB/web.db" || (echo "missing web.db" && exit 2)
test -f "$ART/dv_backup_smoke_001/canonical/animals.csv" || (echo "missing restored artifacts" && exit 2)



echo "[backup_restore_check] 6) cleanup dry-run"
python -m genomeai backup-cleanup --artifacts "$ART" --web-storage "$WEB" --project-root "$ROOT_DIR"

echo "[backup_restore_check] OK"
