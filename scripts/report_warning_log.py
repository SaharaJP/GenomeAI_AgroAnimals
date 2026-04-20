#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.infra.warning_audit import build_warning_origin_report, parse_pytest_warning_log  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) not in {2, 3}:
        print("Usage: report_warning_log.py <pytest.log> [output.json]", file=sys.stderr)
        return 2
    log_path = Path(argv[1])
    out_path = Path(argv[2]) if len(argv) == 3 else None
    text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    report = build_warning_origin_report(parse_pytest_warning_log(text))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if out_path is None:
        print(payload)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        print(f"WARNING_REPORT_OK {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
