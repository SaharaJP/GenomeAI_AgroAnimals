#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.release import render_release_smoke_cli_lines, run_release_package_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Unpack a GenomeAI release archive and run packaged smoke checks")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--python", default="")
    parser.add_argument("--report-json", default="")
    args = parser.parse_args()
    result = run_release_package_smoke(
        archive_path=Path(args.archive).resolve(),
        python_executable=(args.python.strip() or None),
    )
    for line in render_release_smoke_cli_lines(result):
        print(line)
    if args.report_json:
        path = Path(args.report_json).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"report_json={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
