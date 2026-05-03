from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.commercial_readiness_gate import (
    build_commercial_readiness_report,
    render_commercial_readiness_cli_lines,
    render_commercial_readiness_markdown,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--project-root', default='.')
    ap.add_argument('--artifacts-root', default='artifacts')
    ap.add_argument('--report-root', required=True)
    args = ap.parse_args()

    report_root = Path(args.report_root).resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    report = build_commercial_readiness_report(project_root=args.project_root, artifacts_root=args.artifacts_root)
    (report_root / 'commercial_readiness_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    (report_root / 'commercial_readiness_report.md').write_text(
        render_commercial_readiness_markdown(report),
        encoding='utf-8',
    )
    manifest = {
        'schema': 'genomeai.commercial_readiness_evidence_pack.v1',
        'generated_at': report.get('generated_at'),
        'sections': report.get('evidence_pack', {}).get('sections', []),
        'coverage_rate': report.get('evidence_pack', {}).get('coverage_rate'),
    }
    (report_root / 'commercial_readiness_evidence_pack.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    for line in render_commercial_readiness_cli_lines(report):
        print(line)
    print('COMMERCIAL_READINESS_GATE_READY')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
