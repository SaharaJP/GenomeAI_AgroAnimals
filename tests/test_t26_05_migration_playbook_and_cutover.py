from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from core.infra.web_db import init_db
from core.interoperability import (
    list_migration_playbook_candidate_versions,
    list_migration_playbook_runs,
    load_migration_playbook_manifest,
    run_legacy_import_bundle,
    run_migration_playbook_and_cutover,
    run_migration_verification_toolkit,
    run_parallel_run_mode,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _seed(repo: Path, base: Path) -> tuple[Path, Path, Path]:
    exports = base / 'exports'
    artifacts = base / 'artifacts'
    web_storage = base / 'web_storage'
    web_storage.mkdir(parents=True, exist_ok=True)
    for sub in ['uploads', 'logs', 'config_overrides']:
        (web_storage / sub).mkdir(parents=True, exist_ok=True)
    db_path = web_storage / 'web.db'
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
    finally:
        conn.close()

    _write(exports / 'animals.csv', '''AnimalID,FarmID,EarTag,Breed,Sex,BirthDate,Alive,Status
A1,F1,1001,Holstein,F,2024-01-01,true,active
A2,F1,1002,Holstein,F,2024-02-01,true,active
''')
    _write(exports / 'lactations.csv', '''AnimalID,LactNo,CalvingDate,DryoffDate,DIM,Milk305Kg,FatPct,ProteinPct
A1,1,2025-01-01,2025-10-01,250,10250,3.9,3.2
A2,1,2025-02-01,2025-11-01,220,9800,3.8,3.1
''')
    _write(exports / 'repro_events.csv', '''ReproEventID,AnimalID,FarmID,LactationID,EventDate,EventType,Result,BullID,Technician,Method,Notes
RE1,A1,F1,L1,2025-02-01,insemination,,B1,tech,synch,first
RE2,A2,F1,L1,2025-03-01,preg_check,positive,B2,tech,manual,confirmed
''')
    _write(exports / 'treatments.csv', '''TreatmentID,AnimalID,StartDate,EndDate,TreatmentType,ReasonEventID,WithdrawalEndDate
TR1,A1,2025-03-01,2025-03-02,antibiotic,HE1,2025-03-05
''')
    _write(exports / 'basic_events.csv', '''EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID,ReasonCode
BE1,A1,F1,2025-03-10,pen_move,moved,PEN-2,pen_rebalance
BE2,A2,F1,2025-03-11,manual_note,watch closely,,manual_note_added
''')

    run_legacy_import_bundle(
        adapter_key='generic_hms_csv_bundle',
        dataset_files={
            'animals': exports / 'animals.csv',
            'lactations': exports / 'lactations.csv',
            'repro_events': exports / 'repro_events.csv',
            'treatments': exports / 'treatments.csv',
            'basic_events': exports / 'basic_events.csv',
        },
        project_root=repo,
        artifacts_root=artifacts,
        out_version='dv_t26_05',
    )
    run_migration_verification_toolkit(project_root=repo, artifacts_root=artifacts, data_version='dv_t26_05', db_path=db_path)
    run_parallel_run_mode(project_root=repo, artifacts_root=artifacts, data_version='dv_t26_05', db_path=db_path)
    return artifacts, web_storage, db_path


def test_t26_05_playbook_creates_versioned_outputs_backup_support_bundle_and_audit(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    artifacts, web_storage, db_path = _seed(repo, tmp_path)
    manifest = run_migration_playbook_and_cutover(
        project_root=repo,
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        data_version='dv_t26_05',
        playbook_run='mpb_test_1',
        trained_roles=['Admin', 'Operator', 'Viewer'],
        training_notes='core team trained',
    )
    assert manifest['schema'] == 'genomeai.migration_playbook_and_cutover.v1'
    assert manifest['overall_readiness'] == 'ready_for_cutover_preview'
    run_dir = artifacts / 'dv_t26_05' / 'migration_playbook' / 'mpb_test_1'
    assert (run_dir / 'checklist_rows.csv').exists()
    assert (run_dir / 'checklist_report.xlsx').exists()
    assert (run_dir / 'incident_diagnostics.json').exists()
    assert (run_dir / 'cutover_report.md').exists()
    assert Path(manifest['outputs']['backup_preview_zip']).exists()
    assert Path(manifest['outputs']['support_bundle_zip']).exists()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT action, object_type, object_id, data_version FROM audit_log WHERE action='migration.playbook.run'").fetchall()
    assert rows and rows[0][1] == 'migration_playbook' and rows[0][2] == 'mpb_test_1' and rows[0][3] == 'dv_t26_05'


def test_t26_05_playbook_blocks_preview_when_training_missing_and_lists_runs(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    artifacts, web_storage, db_path = _seed(repo, tmp_path)
    manifest = run_migration_playbook_and_cutover(
        project_root=repo,
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        data_version='dv_t26_05',
        playbook_run='mpb_test_2',
        trained_roles=['Admin'],
        training_notes='admin only',
    )
    rows = pd.read_csv(Path(manifest['outputs']['checklist_csv']))
    training = rows[rows['step_key'] == 'training'].iloc[0]
    cutover = rows[rows['step_key'] == 'cutover_preview'].iloc[0]
    assert training['status'] == 'manual_action'
    assert cutover['status'] == 'blocked'
    versions = list_migration_playbook_candidate_versions(artifacts_root=artifacts)
    runs = list_migration_playbook_runs(artifacts_root=artifacts, data_version='dv_t26_05')
    loaded = load_migration_playbook_manifest(artifacts_root=artifacts, data_version='dv_t26_05', playbook_run='mpb_test_2')
    assert 'dv_t26_05' in versions
    assert 'mpb_test_2' in runs
    assert loaded['playbook_run'] == 'mpb_test_2'


def test_t26_05_docs_smoke_and_page_present(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    docs = (repo / 'docs' / 'migration_playbook_and_cutover.md').read_text(encoding='utf-8')
    smoke = (repo / 'scripts' / 'smoke_t26_05_migration_playbook_and_cutover.py').read_text(encoding='utf-8')
    page = (repo / 'streamlit_app' / 'pages' / '62_Migration_Playbook_And_Cutover.py').read_text(encoding='utf-8')
    ia = (repo / 'configs' / 'ui' / 'ia_v3.yaml').read_text(encoding='utf-8')
    assert 'cutover preview' in docs.lower()
    assert 'rollback' in docs.lower()
    assert 'migration playbook and cutover smoke passed' in smoke
    assert 'Build playbook / cutover preview' in page
    assert '62_Migration_Playbook_And_Cutover.py' in ia
