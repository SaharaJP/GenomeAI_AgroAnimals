from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ops.production_lockdown import ProductionLockdownError, production_lockdown_report, validate_production_lockdown


def main() -> int:
    parser = argparse.ArgumentParser(description="GenomeAI production profile lockdown gate")
    parser.add_argument("--json-out", default="", help="Optional path to write lockdown report JSON")
    args = parser.parse_args()

    report = production_lockdown_report()
    payload = report.as_dict()
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if report.adult_mode:
        try:
            validate_production_lockdown()
        except ProductionLockdownError as exc:
            print(f"production_lockdown_failed: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
