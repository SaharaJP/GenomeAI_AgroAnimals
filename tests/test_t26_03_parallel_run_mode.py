from __future__ import annotations

import os
from pathlib import Path

from core.interoperability import (
    list_parallel_run_candidate_versions,
    list_parallel_run_runs,
    load_parallel_run_manifest,
    run_legacy_import_bundle,
    run_migration_verification_toolkit,
    run_parallel_run_mode,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


ANIMALS_CSV = (
    'AnimalID,FarmID,EarTag,Breed,Sex,BirthDate,Alive,Status\n'
    'A1,F1,1001,Holstein,F,2024-01-01,true,active\n'
    'A2,F1,1002,Holstein,F,2024-02-01,true,active\n'
)
LACTATIONS_CSV = (
    'AnimalID,LactNo,CalvingDate,DryoffDate,DIM,Milk305Kg,FatPct,ProteinPct\n'
    'A1,1,2025-01-01,2025-10-01,250,10250,3.9,3.2\n'
    'A2,1,2025-02-01,2025-11-01,220,9800,3.8,3.1\n'
)
REPRO_EVENTS_CSV = (
    'ReproEventID,AnimalID,FarmID,LactationID,EventDate,EventType,Result,BullID,Technician,Method,Notes\n'
    'RE1,A1,F1,L1,2025-02-01,insemination,,B1,tech,synch,first\n'
)
TREATMENTS_CSV = (
    'TreatmentID,AnimalID,StartDate,EndDate,TreatmentType,ReasonEventID,WithdrawalEndDate\n'
    'TR1,A1,2025-03-01,2025-03-02,antibiotic,HE1,2025-03-05\n'
)
BASIC_EVENTS_CSV = (
    'EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID,ReasonCode\n'
    'BE1,A1,F1,2025-03-10,pen_move,moved,PEN-X,pen_rebalance\n'
)


def _seed_bundle(repo: Path, tmp_path: Path, *, stale: bool = False) -> Path:
    exports = tmp_path / 'exports'
    artifacts = tmp_path / 'artifacts'
    _write(exports / 'animals.csv', ANIMALS_CSV)
    _write(exports / 'lactations.csv', LACTATIONS_CSV)
    _write(exports / 'repro_events.csv', REPRO_EVENTS_CSV)
    _write(exports / 'treatments.csv', TREATMENTS_CSV)
    _write(exports / 'basic_events.csv', BASIC_EVENTS_CSV)
    if stale:
        old = 1700000000
        for name in ('animals.csv', 'lactations.csv', 'repro_events.csv', 'treatments.csv', 'basic_events.csv'):
            os.utime(exports / name, (old, old))
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
        out_version='dv_t26_03',
    )
    return artifacts


def test_t26_03_docs_and_smoke_present() -> None:
    repo = Path(__file__).resolve().parents[1]
    docs = (repo / 'docs' / 'parallel_run_mode.md').read_text(encoding='utf-8')
    assumptions = (repo / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    smoke = (repo / 'scripts' / 'smoke_t26_03_parallel_run_mode.py').read_text(encoding='utf-8')
    page = (repo / 'streamlit_app' / 'pages' / '61_Parallel_Run_Mode.py').read_text(encoding='utf-8')
    assert 'trusted scope' in docs.lower()
    assert 'batch-based' in docs.lower()
    assert 'T26-03' in assumptions
    assert 'parallel run mode smoke passed' in smoke
    assert 'Parallel run mode' in page


def test_t26_03_parallel_run_builds_versioned_snapshot_and_scope_rows(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    artifacts = _seed_bundle(repo, tmp_path, stale=True)

    manifest = run_parallel_run_mode(project_root=repo, artifacts_root=artifacts, data_version='dv_t26_03')
    assert manifest['schema'] == 'genomeai.parallel_run_manifest.v1'
    rows = {row['dataset_key']: row for row in manifest['dataset_rows']}
    assert rows['animals']['runtime_scope'] == 'read_write'
    assert rows['animals']['freshness_status'] == 'stale'
    assert rows['repro_events']['runtime_scope'] == 'read_only_preview'
    assert rows['repro_events']['trusted_scope'] == 'reference_only'
    assert manifest['source_system'] == 'Legacy HMS CSV batch export'

    run_dir = artifacts / 'dv_t26_03' / 'parallel_run' / manifest['parallel_run_id']
    assert (run_dir / 'dataset_status.csv').exists()
    assert (run_dir / 'scope_limitations.csv').exists()
    assert (run_dir / 'parallel_run_report.xlsx').exists()

    versions = list_parallel_run_candidate_versions(artifacts_root=artifacts)
    assert 'dv_t26_03' in versions
    runs = list_parallel_run_runs(artifacts_root=artifacts, data_version='dv_t26_03')
    assert manifest['parallel_run_id'] in runs
    loaded = load_parallel_run_manifest(artifacts_root=artifacts, data_version='dv_t26_03', parallel_run_id=manifest['parallel_run_id'])
    assert loaded['parallel_run_id'] == manifest['parallel_run_id']


def test_t26_03_parallel_run_uses_latest_verification_for_manual_review(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    artifacts = _seed_bundle(repo, tmp_path, stale=False)
    animals_csv = artifacts / 'dv_t26_03' / 'canonical' / 'dm_animals.csv'
    lines = animals_csv.read_text(encoding='utf-8').splitlines()
    animals_csv.write_text('\n'.join(lines[:2]) + '\n', encoding='utf-8')

    verification = run_migration_verification_toolkit(project_root=repo, artifacts_root=artifacts, data_version='dv_t26_03')
    assert verification['summary_rows']
    manifest = run_parallel_run_mode(project_root=repo, artifacts_root=artifacts, data_version='dv_t26_03')
    rows = {row['dataset_key']: row for row in manifest['dataset_rows']}
    assert rows['animals']['verification_status'] == 'mismatch'
    assert rows['animals']['trusted_scope'] == 'manual_review'
