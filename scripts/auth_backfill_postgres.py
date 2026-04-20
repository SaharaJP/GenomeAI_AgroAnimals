from __future__ import annotations

import json
from pathlib import Path

from core.infra.web_db import connect, get_settings
from core.infra.runtime_auth_storage import auth_storage_diagnostics


def main() -> int:
    settings = get_settings()
    diag = auth_storage_diagnostics(settings=settings).as_dict()
    if diag['backend'] != 'postgres':
        raise SystemExit('auth_backfill_postgres requires GENOMEAI_RUNTIME_STORAGE_BACKEND=postgres')
    legacy_db = Path(settings.storage_dir) / 'web.db'
    if not legacy_db.exists():
        raise SystemExit(f'legacy sqlite not found: {legacy_db}')
    conn = connect(legacy_db)
    try:
        users = conn.execute("SELECT COUNT(*) FROM users_v2").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM auth_sessions_v1").fetchone()[0]
        lineage = conn.execute("SELECT COUNT(*) FROM auth_session_refresh_lineage_v1").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM auth_failed_attempts_v1").fetchone()[0]
    finally:
        conn.close()
    print(json.dumps({
        'status': 'baseline_only',
        'legacy_counts': {
            'users_v2': int(users),
            'auth_sessions_v1': int(sessions),
            'auth_session_refresh_lineage_v1': int(lineage),
            'auth_failed_attempts_v1': int(failed),
        },
        'note': 'Explicit baseline tool only. Real Postgres backfill/write phase must run in adult-like environment.',
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
