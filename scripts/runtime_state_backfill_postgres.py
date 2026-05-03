from __future__ import annotations

import json
from pathlib import Path

from core.infra.runtime_state_storage import RUNTIME_STATE_ENTITIES, runtime_state_storage_diagnostics
from core.infra.web_db import connect, get_settings, init_db


def _legacy_counts(db_path: Path) -> dict[str, int]:
    conn = connect(db_path)
    try:
        init_db(conn)
        out: dict[str, int] = {}
        for entity in RUNTIME_STATE_ENTITIES:
            try:
                out[entity] = int(conn.execute(f'SELECT COUNT(*) FROM {entity}').fetchone()[0])
            except Exception:
                out[entity] = 0
        return out
    finally:
        conn.close()


def main() -> int:
    settings = get_settings()
    diag = runtime_state_storage_diagnostics().as_dict()
    if diag['backend'] != 'postgres':
        raise SystemExit('runtime_state_backfill_postgres requires GENOMEAI_RUNTIME_STORAGE_BACKEND=postgres')
    legacy_db = Path(settings.storage_dir) / 'web.db'
    if not legacy_db.exists():
        raise SystemExit(f'legacy sqlite not found: {legacy_db}')
    print(json.dumps({
        'status': 'baseline_only',
        'runtime_state_storage': diag,
        'legacy_sqlite_counts': _legacy_counts(legacy_db),
        'note': 'This stage prepares explicit entity inventory and legacy counts. Real row-copy/backfill must run in adult-like PostgreSQL environment.',
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
