from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from core.interoperability import run_legacy_import_bundle, run_migration_verification_toolkit


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='t26_02_smoke_') as td:
        base = Path(td)
        exports = base / 'exports'
        artifacts = base / 'artifacts'
        db_path = base / 'web.db'
        # Create empty SQLite stub — db_path is passed to the migration toolkit
        # only as an audit-context marker (no legacy schema needed post-T34 cutover)
        sqlite3.connect(str(db_path)).close()

        _write(exports / 'animals.csv', 'AnimalID,FarmID,EarTag,Breed,Sex,BirthDate,Alive,Status\nA1,F1,1001,Holstein,F,2024-01-01,true,active\nA2,F1,1002,Holstein,F,2024-02-01,true,active\n')
        _write(exports / 'lactations.csv', 'AnimalID,LactNo,CalvingDate,DryoffDate,DIM,Milk305Kg,FatPct,ProteinPct\nA1,1,2025-01-01,2025-10-01,250,10250,3.9,3.2\nA2,1,2025-02-01,2025-11-01,220,9800,3.8,3.1\n')
        _write(exports / 'repro_events.csv', 'ReproEventID,AnimalID,FarmID,LactationID,EventDate,EventType,Result,BullID,Technician,Method,Notes\nRE1,A1,F1,L1,2025-02-01,insemination,,B1,tech,synch,first\nRE2,A2,F1,L1,2025-03-01,preg_check,positive,B2,tech,manual,confirmed\n')
        _write(exports / 'treatments.csv', 'TreatmentID,AnimalID,StartDate,EndDate,TreatmentType,ReasonEventID,WithdrawalEndDate\nTR1,A1,2025-03-01,2025-03-02,antibiotic,HE1,2025-03-05\n')
        _write(exports / 'basic_events.csv', 'EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID,ReasonCode\nBE1,A1,F1,2025-03-10,pen_move,moved,PEN-2,pen_rebalance\n')

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
            out_version='dv_t26_02_smoke',
        )
        # introduce one bounded mismatch
        canonical_animals = artifacts / 'dv_t26_02_smoke' / 'canonical' / 'dm_animals.csv'
        text = canonical_animals.read_text(encoding='utf-8')
        canonical_animals.write_text(text + 'A3,F1,1003,Holstein,F,2024-03-01,True,active\n', encoding='utf-8')

        manifest = run_migration_verification_toolkit(
            project_root=repo,
            artifacts_root=artifacts,
            data_version='dv_t26_02_smoke',
            db_path=db_path,
            tenant_id='default',
            user_id=1,
            username='smoke',
            role='Admin',
        )
        assert manifest['schema'] == 'genomeai.migration_verification_toolkit.v1'
        assert (artifacts / 'dv_t26_02_smoke' / 'migration_verification' / manifest['verification_run'] / 'compare_rows.csv').exists()
    print('OK: migration verification toolkit smoke passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
