from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from core.infra.web_db import init_db
from core.interoperability import (
    list_migration_candidate_versions,
    list_migration_verification_runs,
    load_migration_verification_manifest,
    run_legacy_import_bundle,
    run_migration_verification_toolkit,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')



def _seed_bundle(repo: Path, base: Path, *, out_version: str = 'dv_t26_02') -> tuple[Path, Path]:
    exports = base / 'exports'
    artifacts = base / 'artifacts'
    _write(
        exports / 'animals.csv',
        'AnimalID,FarmID,EarTag,Breed,Sex,BirthDate,Alive,Status\n'
        'A1,F1,1001,Holstein,F,2024-01-01,true,active\n'
        'A2,F1,1002,Holstein,F,2024-02-01,true,active\n',
    )
    _write(
        exports / 'lactations.csv',
        'AnimalID,LactNo,CalvingDate,DryoffDate,DIM,Milk305Kg,FatPct,ProteinPct\n'
        'A1,1,2025-01-01,2025-10-01,250,10250,3.9,3.2\n'
        'A2,1,2025-02-01,2025-11-01,220,9800,3.8,3.1\n',
    )
    _write(
        exports / 'repro_events.csv',
        'ReproEventID,AnimalID,FarmID,LactationID,EventDate,EventType,Result,BullID,Technician,Method,Notes\n'
        'RE1,A1,F1,L1,2025-02-01,insemination,,B1,tech,synch,first\n'
        'RE2,A2,F1,L1,2025-03-01,preg_check,positive,B2,tech,manual,confirmed\n',
    )
    _write(
        exports / 'treatments.csv',
        'TreatmentID,AnimalID,StartDate,EndDate,TreatmentType,ReasonEventID,WithdrawalEndDate\n'
        'TR1,A1,2025-03-01,2025-03-02,antibiotic,HE1,2025-03-05\n',
    )
    _write(
        exports / 'basic_events.csv',
        'EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID,ReasonCode\n'
        'BE1,A1,F1,2025-03-10,pen_move,moved,PEN-2,pen_rebalance\n'
        'BE2,A2,F1,2025-03-11,manual_note,watch closely,,manual_note_added\n',
    )
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
        out_version=out_version,
    )
    return exports, artifacts



def test_t26_02_verification_run_is_versioned_exportable_and_audited(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    _exports, artifacts = _seed_bundle(repo, tmp_path)

    # introduce one bounded mismatch in new system side
    animals_csv = artifacts / 'dv_t26_02' / 'canonical' / 'dm_animals.csv'
    animals = pd.read_csv(animals_csv)
    animals = pd.concat([animals, pd.DataFrame([{'animal_id': 'A3', 'farm_id': 'F1', 'ear_tag': '1003', 'breed': 'Holstein', 'sex': 'F', 'birth_date': '2024-03-01', 'is_alive': True, 'status': 'active'}])], ignore_index=True)
    animals.to_csv(animals_csv, index=False)

    db_path = tmp_path / 'web.db'
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
    finally:
        conn.close()

    manifest = run_migration_verification_toolkit(
        project_root=repo,
        artifacts_root=artifacts,
        data_version='dv_t26_02',
        verification_run='mvfy_test_1',
        db_path=db_path,
        tenant_id='default',
        user_id=7,
        username='verifier',
        role='Admin',
    )

    run_dir = artifacts / 'dv_t26_02' / 'migration_verification' / 'mvfy_test_1'
    assert manifest['schema'] == 'genomeai.migration_verification_toolkit.v1'
    assert (run_dir / 'verification_manifest.json').exists()
    assert (run_dir / 'compare_rows.csv').exists()
    assert (run_dir / 'compare_rows.xlsx').exists()
    assert (run_dir / 'dataset_status.csv').exists()
    assert (run_dir / 'issues.csv').exists()

    compare_df = pd.read_csv(run_dir / 'compare_rows.csv')
    assert 'mismatch' in set(compare_df['status'])
    headcount_row = compare_df[(compare_df['dataset_key'] == 'animals') & (compare_df['metric_code'] == 'headcount') & (compare_df['scope_kind'] == 'global')].iloc[0]
    assert int(headcount_row['legacy_value']) == 2
    assert int(headcount_row['new_value']) == 3

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT action, object_type, object_id, data_version FROM audit_log WHERE action='migration.verification.run'").fetchall()
    assert rows
    assert rows[0][1] == 'migration_verification'
    assert rows[0][2] == 'mvfy_test_1'
    assert rows[0][3] == 'dv_t26_02'



def test_t26_02_toolkit_surfaces_matched_mismatch_and_manual_review_with_drilldown(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    _exports, artifacts = _seed_bundle(repo, tmp_path)

    # mismatch in basic events group drilldown and manual review in lactation KPI
    basic_csv = artifacts / 'dv_t26_02' / 'migration_staging' / 'basic_events.csv'
    basic = pd.read_csv(basic_csv)
    basic.loc[basic['event_id'] == 'BE1', 'pen_id'] = 'PEN-X'
    basic = pd.concat([basic, pd.DataFrame([{'event_id':'BE3','animal_id':'A1','farm_id':'F1','event_date':'2025-03-12','event_type':'manual_note','comment':'extra','pen_id':'PEN-X','reason_code':'manual_note_added'}])], ignore_index=True)
    basic.to_csv(basic_csv, index=False)

    lact_csv = artifacts / 'dv_t26_02' / 'canonical' / 'dm_lactations.csv'
    lact = pd.read_csv(lact_csv)
    lact = lact.drop(columns=['milk_305d_kg'])
    lact.to_csv(lact_csv, index=False)

    manifest = run_migration_verification_toolkit(
        project_root=repo,
        artifacts_root=artifacts,
        data_version='dv_t26_02',
        verification_run='mvfy_test_2',
    )
    compare_df = pd.read_csv(Path(manifest['outputs']['compare_rows_csv']))
    assert {'matched', 'mismatch', 'manual_review'}.issubset(set(compare_df['status']))

    manual = compare_df[(compare_df['dataset_key'] == 'lactations') & (compare_df['metric_code'] == 'avg_milk_305_kg') & (compare_df['status'] == 'manual_review')]
    assert not manual.empty

    group_rows = compare_df[(compare_df['dataset_key'] == 'basic_events') & (compare_df['scope_kind'] == 'group')]
    assert not group_rows.empty
    assert any(str(x).startswith('group:') for x in group_rows['scope_key'].tolist())
    assert any(str(x).endswith('PEN-X') for x in group_rows['scope_key'].tolist())



def test_t26_02_candidate_listing_docs_and_manifest_reload(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    _exports, artifacts = _seed_bundle(repo, tmp_path)
    manifest = run_migration_verification_toolkit(
        project_root=repo,
        artifacts_root=artifacts,
        data_version='dv_t26_02',
        verification_run='mvfy_test_3',
    )

    versions = list_migration_candidate_versions(artifacts_root=artifacts)
    runs = list_migration_verification_runs(artifacts_root=artifacts, data_version='dv_t26_02')
    loaded = load_migration_verification_manifest(artifacts_root=artifacts, data_version='dv_t26_02', verification_run='mvfy_test_3')

    assert 'dv_t26_02' in versions
    assert 'mvfy_test_3' in runs
    assert loaded['verification_run'] == manifest['verification_run']

    docs = (repo / 'docs' / 'migration_verification_toolkit.md').read_text(encoding='utf-8')
    smoke = (repo / 'scripts' / 'smoke_t26_02_migration_verification_toolkit.py').read_text(encoding='utf-8')
    page = (repo / 'streamlit_app' / 'pages' / '60_Migration_Verification_Toolkit.py').read_text(encoding='utf-8')
    assert 'manual_review' in docs
    assert 'farm' in docs.lower() and 'group' in docs.lower()
    assert 'migration verification toolkit smoke passed' in smoke
    assert 'Run verification' in page
