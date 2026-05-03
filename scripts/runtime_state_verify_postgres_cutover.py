from __future__ import annotations

import json
from pathlib import Path

from core.infra.runtime_state_storage import RUNTIME_STATE_ENTITIES, runtime_state_storage_diagnostics
from core.infra.web_db import connect, get_settings, init_db


def _legacy_counts(db_path: Path) -> dict[str, int]:
    conn = connect(db_path)
    try:
        init_db(conn)
        return {entity: int(conn.execute(f'SELECT COUNT(*) FROM {entity}').fetchone()[0]) if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (entity,)).fetchone() else 0 for entity in RUNTIME_STATE_ENTITIES}
    finally:
        conn.close()


def main() -> int:
    settings = get_settings()
    diag = runtime_state_storage_diagnostics().as_dict()
    legacy_db = Path(settings.storage_dir) / 'web.db'
    payload = {
        'status': 'baseline_only' if diag['backend'] != 'postgres' else str(diag.get('migration_status') or 'unknown'),
        'runtime_state_storage': diag,
        'legacy_sqlite_counts': _legacy_counts(legacy_db) if legacy_db.exists() else {},
        'note': 'Live PostgreSQL read/write verification should compare old vs new counts, key integrity and lineage sanity in adult-like contour.',
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
