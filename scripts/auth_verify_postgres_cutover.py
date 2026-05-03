from __future__ import annotations

import json
from core.infra.web_db import get_settings
from core.infra.runtime_auth_storage import auth_storage_diagnostics


def main() -> int:
    settings = get_settings()
    diag = auth_storage_diagnostics(settings=settings).as_dict()
    print(json.dumps({
        'status': 'baseline_only',
        'auth_runtime_storage': diag,
        'note': 'This verifies config/guard posture. Live Postgres query proof must be executed separately.',
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
