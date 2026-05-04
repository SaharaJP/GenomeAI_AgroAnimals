from __future__ import annotations

import sqlite3
from pathlib import Path

from core.interoperability import (
    run_legacy_import_bundle,
    run_migration_playbook_and_cutover,
    run_migration_verification_toolkit,
    run_parallel_run_mode,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    base = repo / 'tmp' / 'smoke_t26_05'
    if base.exists():
        import shutil
        shutil.rmtree(base)
    exports = base / 'exports'
    artifacts = base / 'artifacts'
    web_storage = base / 'web_storage'
    web_storage.mkdir(parents=True, exist_ok=True)
    for sub in ['uploads', 'logs', 'config_overrides']:
        (web_storage / sub).mkdir(parents=True, exist_ok=True)
    db_path = web_storage / 'web.db'
    # Create empty SQLite stub — db_path is an audit-context marker only post-T34 cutover
    sqlite3.connect(str(db_path)).close()

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
''')
    _write(exports / 'treatments.csv', '''TreatmentID,AnimalID,StartDate,EndDate,TreatmentType,ReasonEventID,WithdrawalEndDate
TR1,A1,2025-03-01,2025-03-02,antibiotic,HE1,2025-03-05
''')
    _write(exports / 'basic_events.csv', '''EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID,ReasonCode
BE1,A1,F1,2025-03-10,pen_move,moved,PEN-2,pen_rebalance
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
        out_version='dv_smoke_t26_05',
    )
    run_migration_verification_toolkit(project_root=repo, artifacts_root=artifacts, data_version='dv_smoke_t26_05', db_path=db_path)
    run_parallel_run_mode(project_root=repo, artifacts_root=artifacts, data_version='dv_smoke_t26_05', db_path=db_path)
    manifest = run_migration_playbook_and_cutover(
        project_root=repo,
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        data_version='dv_smoke_t26_05',
        trained_roles=['Admin', 'Operator', 'Viewer'],
        training_notes='smoke sign-off',
    )
    outputs = manifest.get('outputs') or {}
    for key in ['checklist_csv', 'checklist_xlsx', 'incident_diagnostics_json', 'cutover_report_md', 'backup_preview_zip', 'support_bundle_zip']:
        path = Path(str(outputs.get(key) or ''))
        if not path.exists():
            raise SystemExit(f'missing_output:{key}')
    print('OK: migration playbook and cutover smoke passed')


if __name__ == '__main__':
    main()
