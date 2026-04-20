from __future__ import annotations

import argparse
from pathlib import Path

from core.observability.competitive_acceptance import (
    render_competitive_acceptance_cli_lines,
    run_competitive_acceptance_set,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Run competitive acceptance set (T30-01)')
    p.add_argument('--project-root', default='.')
    p.add_argument('--artifacts', default='artifacts')
    p.add_argument('--profile', default='legacy_replacement_ci')
    p.add_argument('--config', default=None)
    p.add_argument('--report-root', default=None)
    p.add_argument('--scenario', dest='scenarios', action='append', default=[])
    return p


def main() -> int:
    args = build_parser().parse_args()
    result = run_competitive_acceptance_set(
        project_root=Path(args.project_root).resolve(),
        artifacts_root=Path(args.artifacts).resolve(),
        profile=str(args.profile or 'legacy_replacement_ci'),
        config_path=Path(args.config).resolve() if args.config else None,
        report_root=Path(args.report_root).resolve() if args.report_root else None,
        scenarios=list(args.scenarios or []),
    )
    for line in render_competitive_acceptance_cli_lines(result):
        print(line)
    return 0 if bool((result.get('summary') or {}).get('ready_for_competitive_uat')) else 2


if __name__ == '__main__':
    raise SystemExit(main())
