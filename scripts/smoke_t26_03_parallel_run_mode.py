from __future__ import annotations

import tempfile
from pathlib import Path

from core.interoperability import run_legacy_import_bundle, run_parallel_run_mode


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        exports = tmp / 'exports'
        artifacts = tmp / 'artifacts'
        _write(exports / 'animals.csv', 'AnimalID,FarmID,EarTag,Breed,Sex,BirthDate,Alive,Status\nA1,F1,1001,Holstein,F,2024-01-01,true,active\n')
        _write(exports / 'lactations.csv', 'AnimalID,LactNo,CalvingDate,DryoffDate,DIM,Milk305Kg,FatPct,ProteinPct\nA1,1,2025-01-01,2025-10-01,250,10250,3.9,3.2\n')
        _write(exports / 'basic_events.csv', 'EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID,ReasonCode\nBE1,A1,F1,2025-03-10,pen_move,moved,PEN-2,pen_rebalance\n')
        run_legacy_import_bundle(
            adapter_key='generic_hms_csv_bundle',
            dataset_files={'animals': exports / 'animals.csv', 'lactations': exports / 'lactations.csv', 'basic_events': exports / 'basic_events.csv'},
            project_root=repo,
            artifacts_root=artifacts,
            out_version='dv_t26_03',
        )
        manifest = run_parallel_run_mode(project_root=repo, artifacts_root=artifacts, data_version='dv_t26_03')
        assert manifest['schema'] == 'genomeai.parallel_run_manifest.v1'
        assert (artifacts / 'dv_t26_03' / 'parallel_run' / manifest['parallel_run_id'] / 'parallel_run_manifest.json').exists()
    print('OK: parallel run mode smoke passed')


if __name__ == '__main__':
    main()
