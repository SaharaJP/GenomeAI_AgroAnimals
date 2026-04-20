from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from core.customer_upgrade_discipline import build_customer_upgrade_report
from core.infra.web_db import init_db


def _seed_runtime(root: Path) -> tuple[Path, Path, Path]:
    artifacts = root / 'artifacts'
    web_storage = root / 'web_storage'
    db_path = web_storage / 'web.db'
    (artifacts / 'dv_upgrade_demo' / 'canonical').mkdir(parents=True, exist_ok=True)
    (artifacts / 'dv_upgrade_demo' / 'canonical' / 'animals.csv').write_text('animal_id\nA001\n', encoding='utf-8')
    (web_storage / 'uploads').mkdir(parents=True, exist_ok=True)
    (web_storage / 'logs').mkdir(parents=True, exist_ok=True)
    (web_storage / 'config_overrides').mkdir(parents=True, exist_ok=True)
    (web_storage / 'logs' / 'upgrade_demo.log').write_text('upgrade smoke log\n', encoding='utf-8')
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        conn.commit()
    finally:
        conn.close()
    return artifacts, web_storage, db_path


def main() -> int:
    parser = argparse.ArgumentParser(description='Run repeatable customer upgrade discipline smoke.')
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--report-root', default='artifacts/_ci/customer_upgrade_v1')
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    report_root = Path(args.report_root).resolve()
    seed_root = report_root / '_seed_runtime'
    artifacts_root, web_storage, db_path = _seed_runtime(seed_root)

    report = build_customer_upgrade_report(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        db_path=db_path,
        report_root=report_root,
    )
    print('CUSTOMER_UPGRADE_READY')
    print(json.dumps({
        'report_json_path': report.get('report_json_path'),
        'report_md_path': report.get('report_md_path'),
        'upgrade_ready': (report.get('summary') or {}).get('upgrade_ready'),
        'rollback_recommended': (report.get('summary') or {}).get('rollback_recommended'),
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
