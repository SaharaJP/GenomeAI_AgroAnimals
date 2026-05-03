from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.recovery.adult_maintenance import verify_adult_restore_performed


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify adult restore state and required artifacts')
    parser.add_argument('--artifacts-root', required=True)
    parser.add_argument('--require-artifact', action='append', default=[])
    args = parser.parse_args()
    result = verify_adult_restore_performed(
        artifacts_root=Path(args.artifacts_root),
        required_artifact_paths=list(args.require_artifact or []),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('ok'):
        print('ADULT_RESTORE_VERIFY_OK')
        return 0
    print('ADULT_RESTORE_VERIFY_FAILED')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
