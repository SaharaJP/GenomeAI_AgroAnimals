from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ops.production_operability import validate_production_operability


def main() -> int:
    parser = argparse.ArgumentParser(description='GenomeAI production operability/supportability gate')
    parser.add_argument('--json-out', default='', help='Optional path to write report JSON')
    args = parser.parse_args()
    report = validate_production_operability().as_dict()
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
