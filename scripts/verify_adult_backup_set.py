from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.recovery.adult_maintenance import verify_adult_backup_created


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify adult backup set completeness')
    parser.add_argument('--backup-dir', required=True)
    args = parser.parse_args()
    result = verify_adult_backup_created(backup_dir=Path(args.backup_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('ok'):
        print('ADULT_BACKUP_VERIFY_OK')
        return 0
    print('ADULT_BACKUP_VERIFY_FAILED')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
