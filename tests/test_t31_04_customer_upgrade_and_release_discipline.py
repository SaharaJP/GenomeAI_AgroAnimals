from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from core.customer_upgrade_discipline import build_customer_upgrade_report, load_customer_upgrade_policy, load_release_notes
from core.infra.web_db import init_db

ROOT = Path(__file__).resolve().parents[1]


def _seed_runtime(root: Path) -> tuple[Path, Path, Path]:
    artifacts = root / 'artifacts'
    web_storage = root / 'web_storage'
    db_path = web_storage / 'web.db'
    (artifacts / 'dv_upgrade_test' / 'canonical').mkdir(parents=True, exist_ok=True)
    (artifacts / 'dv_upgrade_test' / 'canonical' / 'animals.csv').write_text('animal_id\nA001\n', encoding='utf-8')
    (web_storage / 'uploads').mkdir(parents=True, exist_ok=True)
    (web_storage / 'logs').mkdir(parents=True, exist_ok=True)
    (web_storage / 'config_overrides').mkdir(parents=True, exist_ok=True)
    (web_storage / 'logs' / 'runtime.log').write_text('runtime ok\n', encoding='utf-8')
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        conn.commit()
    finally:
        conn.close()
    return artifacts, web_storage, db_path


def test_t31_04_builds_repeatable_upgrade_report(tmp_path: Path) -> None:
    artifacts, web_storage, db_path = _seed_runtime(tmp_path / 'runtime')
    report = build_customer_upgrade_report(
        project_root='.',
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        report_root=tmp_path / 'report',
    )
    assert report['schema'] == 'genomeai.customer_upgrade_report.v1'
    assert report['summary']['pre_upgrade_ok'] is True
    assert report['summary']['backup_ready'] is True
    assert report['summary']['rollback_ready'] is True
    assert report['summary']['post_upgrade_ok'] is True
    assert report['summary']['upgrade_ready'] is True
    assert Path(report['report_json_path']).exists()
    assert Path(report['report_md_path']).exists()
    assert Path(report['artifacts']['backup_preview']['backup_zip']).exists()
    assert Path(report['artifacts']['support_bundle']['bundle_zip']).exists()


def test_t31_04_policy_and_release_notes_are_explicit() -> None:
    policy = load_customer_upgrade_policy(project_root='.')
    notes = load_release_notes(project_root='.', policy=policy)
    assert policy['report_dir'] == 'artifacts/customer_upgrade_v1'
    assert any(item['criterion_id'] == 'restore_drill_failed' for item in policy['rollback_criteria'])
    assert notes['ok'] is True
    assert 'support bundle' in ' '.join((notes.get('notes') or [])[0].get('upgrade_notes') or []).lower()


def test_t31_04_page_docs_and_wiring_are_present() -> None:
    page = (ROOT / 'streamlit_app/pages/77_Customer_Upgrade_And_Release_Discipline.py').read_text(encoding='utf-8')
    widget = (ROOT / 'streamlit_app/customer_upgrade_discipline.py').read_text(encoding='utf-8')
    docs = (ROOT / 'docs/customer_upgrade_and_release_discipline.md').read_text(encoding='utf-8')
    ia = (ROOT / 'configs/ui/ia_v3.yaml').read_text(encoding='utf-8')
    assumptions = (ROOT / 'docs/assumptions.md').read_text(encoding='utf-8')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    project_map = (ROOT / 'docs/project_map.md').read_text(encoding='utf-8')
    pytest_gate = (ROOT / 'ci/pytest_gate.txt').read_text(encoding='utf-8')
    admin_page = (ROOT / 'streamlit_app/pages/37_Admin_Observability_Release.py').read_text(encoding='utf-8')
    admin_console = (ROOT / 'streamlit_app/admin_console.py').read_text(encoding='utf-8')

    assert 'render_customer_upgrade_widget' in widget
    assert 'Customer upgrade и release discipline' in widget
    assert 'pages/77_Customer_Upgrade_And_Release_Discipline.py' in ia
    assert 'customer_upgrade_and_release_discipline' in ia
    assert 'repeatable upgrade path' in docs.lower()
    assert 'T31-04 — Upgrade / release / customer environment discipline' in assumptions
    assert 'docs/customer_upgrade_and_release_discipline.md' in readme
    assert 'customer upgrade' in project_map.lower()
    assert 'tests/test_t31_04_customer_upgrade_and_release_discipline.py' in pytest_gate
    assert 'customer_upgrade' in admin_page
    assert 'customer_upgrade_diagnostics' in admin_console


def test_t31_04_smoke_runner_writes_reports(tmp_path: Path) -> None:
    report_root = tmp_path / 'customer_upgrade_report'
    cmd = [
        sys.executable,
        'scripts/smoke_t31_04_customer_upgrade_discipline.py',
        '--project-root',
        '.',
        '--report-root',
        str(report_root),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    assert 'CUSTOMER_UPGRADE_READY' in proc.stdout
    payload = json.loads((report_root / 'customer_upgrade_report.json').read_text(encoding='utf-8'))
    assert payload['summary']['upgrade_ready'] is True
    assert (report_root / 'customer_upgrade_report.md').exists()
