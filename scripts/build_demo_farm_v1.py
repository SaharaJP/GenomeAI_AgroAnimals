#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.demo_farm import build_demo_farm_dataset


def main() -> int:
    ap = argparse.ArgumentParser(description='Build synthetic demo farm dataset v1')
    ap.add_argument('--output-dir', default=str(ROOT / 'data' / 'demo' / 'demo_farm_v1'))
    args = ap.parse_args()
    manifest = build_demo_farm_dataset(Path(args.output_dir))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
