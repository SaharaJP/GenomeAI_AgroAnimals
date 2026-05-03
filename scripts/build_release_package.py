#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from core.release import build_release_package, render_release_cli_lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reproducible GenomeAI release archive")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--out", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--build-stamp", default="")
    parser.add_argument("--release-channel", default="")
    parser.add_argument("--source-date-epoch", default=None, type=int)
    args = parser.parse_args()
    result = build_release_package(
        project_root=Path(args.project_root).resolve(),
        out_path=(Path(args.out).resolve() if args.out else None),
        config_path=args.config,
        build_stamp=(args.build_stamp.strip() or None),
        release_channel=(args.release_channel.strip() or None),
        source_date_epoch=args.source_date_epoch,
    )
    for line in render_release_cli_lines(result):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
