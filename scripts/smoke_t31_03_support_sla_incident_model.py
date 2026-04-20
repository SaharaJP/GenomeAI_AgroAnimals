from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.support_sla_incident import (
    build_support_sla_incident_summary,
    render_support_sla_incident_cli_lines,
    render_support_sla_incident_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description='Smoke runner for support / SLA / incident model')
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--artifacts-dir', default='artifacts')
    parser.add_argument('--report-root', default='artifacts/_ci/support_sla_incident_v1')
    parser.add_argument('--web-storage-dir', default='web_cabinet/storage')
    args = parser.parse_args()

    payload = build_support_sla_incident_summary(
        project_root=args.project_root,
        artifacts_dir=args.artifacts_dir,
        web_storage_dir=args.web_storage_dir,
    )
    report_root = Path(args.report_root)
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / 'support_sla_incident_report.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    (report_root / 'support_sla_incident_report.md').write_text(render_support_sla_incident_markdown(payload), encoding='utf-8')
    for line in render_support_sla_incident_cli_lines(payload):
        print(line)
    print('SUPPORT_SLA_INCIDENT_READY')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
