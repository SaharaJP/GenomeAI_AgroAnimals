from __future__ import annotations

import sys
from pathlib import Path

REQUIRED_FILES = [
    'docs/production_operability_and_supportability.md',
    'configs/ops/metrics_contract_v1.json',
    'configs/ops/release_checklist_v1.json',
    'configs/ops/rollback_checklist_v1.json',
    'configs/ops/incident_first_troubleshooting_v1.json',
    'scripts/check_production_operability.py',
]
REQUIRED_APP_SNIPPETS = [
    '/api/operability',
    '/api/metrics-contract',
    '/admin/operability',
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).exists()]
    app_text = (root / 'src/web_cabinet/app.py').read_text(encoding='utf-8')
    missing_snippets = [snippet for snippet in REQUIRED_APP_SNIPPETS if snippet not in app_text]
    if missing or missing_snippets:
        if missing:
            print('missing files:')
            for rel in missing:
                print(f' - {rel}')
        if missing_snippets:
            print('missing app routes:')
            for snippet in missing_snippets:
                print(f' - {snippet}')
        return 1
    print('docs_to_code_consistency=ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
