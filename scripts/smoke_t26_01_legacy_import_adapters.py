from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from core.interoperability import run_legacy_import_bundle


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='t26_01_smoke_') as td:
        base = Path(td)
        exports = base / 'exports'
        artifacts = base / 'artifacts'
        _write(
            exports / 'animals.csv',
            "AnimalID,FarmID,EarTag,Breed,Sex,BirthDate,Alive,Status\nA1,F1,1001,Holstein,F,2024-01-01,true,active\n",
        )
        _write(
            exports / 'lactations.csv',
            "AnimalID,LactNo,CalvingDate,DryoffDate,DIM,Milk305Kg,FatPct,ProteinPct\nA1,1,2025-01-01,2025-10-01,250,10250,3.9,3.2\n",
        )
        _write(
            exports / 'repro_events.csv',
            "ReproEventID,AnimalID,FarmID,LactationID,EventDate,EventType,Result,BullID,Technician,Method,Notes\nRE1,A1,F1,L1,2025-02-01,insemination,,B1,tech,synch,first\n",
        )
        _write(
            exports / 'treatments.csv',
            "TreatmentID,AnimalID,StartDate,EndDate,TreatmentType,ReasonEventID,WithdrawalEndDate\nTR1,A1,2025-03-01,2025-03-02,antibiotic,HE1,2025-03-05\n",
        )
        _write(
            exports / 'basic_events.csv',
            "EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID,ReasonCode\nBE1,A1,F1,2025-03-10,pen_move,moved,PEN-2,pen_rebalance\n",
        )
        res = run_legacy_import_bundle(
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
            out_version='dv_t26_01_smoke',
        )
        assert res['datasets']['animals']['status'] == 'ingested'
        assert res['datasets']['repro_events']['status'] == 'staged'
        assert (artifacts / 'dv_t26_01_smoke' / 'canonical' / 'dm_animals.csv').exists()
        assert (artifacts / 'dv_t26_01_smoke' / 'migration_staging' / 'repro_events_operational_preview.jsonl').exists()
    print('OK: legacy import adapters smoke passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
