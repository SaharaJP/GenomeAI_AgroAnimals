from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.pilot_framework import build_pilot_framework_summary, render_pilot_framework_markdown, render_pilot_framework_cli_lines


def main() -> int:
    parser = argparse.ArgumentParser(description='Smoke runner for pilot framework and reference deployments')
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--report-root', default='artifacts/_ci/pilot_framework_v1')
    args = parser.parse_args()

    summary = build_pilot_framework_summary(project_root=args.project_root)
    report_root = Path(args.report_root)
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / 'pilot_framework_report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_root / 'pilot_framework_report.md').write_text(render_pilot_framework_markdown(summary), encoding='utf-8')
    for line in render_pilot_framework_cli_lines(summary):
        print(line)
    print('PILOT_FRAMEWORK_READY')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
