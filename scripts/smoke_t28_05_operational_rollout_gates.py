from __future__ import annotations

import argparse
from pathlib import Path

from core.observability.operational_gates import (
    render_operational_rollout_cli_lines,
    run_operational_rollout_gates,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Run operational SLA / rollout gates (T28-05)')
    p.add_argument('--project-root', default='.')
    p.add_argument('--artifacts', default='artifacts')
    p.add_argument('--profile', default='enterprise_ci')
    p.add_argument('--config', default=None)
    p.add_argument('--report-root', default=None)
    p.add_argument('--workdir', default=None)
    p.add_argument('--gate', dest='gates', action='append', default=[])
    return p


def main() -> int:
    args = build_parser().parse_args()
    result = run_operational_rollout_gates(
        project_root=Path(args.project_root).resolve(),
        artifacts_root=Path(args.artifacts).resolve(),
        profile=str(args.profile or 'enterprise_ci'),
        config_path=Path(args.config).resolve() if args.config else None,
        report_root=Path(args.report_root).resolve() if args.report_root else None,
        workdir_root=Path(args.workdir).resolve() if args.workdir else None,
        gates=list(args.gates or []),
    )
    for line in render_operational_rollout_cli_lines(result):
        print(line)
    return 0 if bool((result.get('summary') or {}).get('ok')) else 2


if __name__ == '__main__':
    raise SystemExit(main())
