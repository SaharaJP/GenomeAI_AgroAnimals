from __future__ import annotations

import json
import sys
from pathlib import Path

from core.infra.environment_snapshot import build_test_environment_snapshot


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python scripts/export_test_env_snapshot.py <output-json>", file=sys.stderr)
        return 2
    output_path = Path(args[0])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_test_environment_snapshot()
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
