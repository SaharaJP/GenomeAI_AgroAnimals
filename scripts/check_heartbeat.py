from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(2)
    path = Path(sys.argv[1])
    max_age = int(sys.argv[2])
    if not path.exists():
        raise SystemExit(1)
    payload = json.loads(path.read_text(encoding="utf-8"))
    ts = parse_iso(str(payload.get("ts") or ""))
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if payload.get("status") != "ok" or age > max_age:
        raise SystemExit(1)
