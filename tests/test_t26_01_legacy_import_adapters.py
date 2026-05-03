from __future__ import annotations

import json
from pathlib import Path

from core.interoperability import (
    build_legacy_import_plan,
    legacy_import_adapter_catalog,
    preview_legacy_mapping_diagnostics,
    resolve_legacy_mapping_template,
    run_legacy_import_bundle,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')



def test_t26_01_catalog_templates_and_docs_present() -> None:
    repo = Path(__file__).resolve().parents[1]
    catalog = legacy_import_adapter_catalog()
    keys = {row['adapter_key'] for row in catalog['adapters']}
    assert {'generic_hms_csv_bundle', 'dairycomp_305_basic', 'selex_basic'}.issubset(keys)

    for adapter_key in ('generic_hms_csv_bundle', 'dairycomp_305_basic', 'selex_basic'):
        for dataset_key in ('animals', 'lactations', 'repro_events', 'treatments', 'basic_events'):
            path = resolve_legacy_mapping_template(adapter_key=adapter_key, dataset_key=dataset_key, project_root=repo)
            assert path.exists(), f'missing template: {path}'

    docs = (repo / 'docs' / 'legacy_import_adapters.md').read_text(encoding='utf-8')
    assumptions = (repo / 'docs' / 'assumptions.md').read_text(encoding='utf-8')
    smoke = (repo / 'scripts' / 'smoke_t26_01_legacy_import_adapters.py').read_text(encoding='utf-8')

    assert 'staged adoption' in docs.lower()
    assert 'migration_staging' in docs
    assert 'starter mapping templates' in assumptions.lower()
    assert 'legacy import adapters smoke passed' in smoke



def test_t26_01_run_bundle_reuses_ingest_and_stages_operational_exports(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    exports = tmp_path / 'exports'
    artifacts = tmp_path / 'artifacts'

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
        out_version='dv_t26_01',
    )

    assert res['datasets']['animals']['status'] == 'ingested'
    assert res['datasets']['lactations']['status'] == 'ingested'
    assert res['datasets']['treatments']['status'] == 'ingested'
    assert res['datasets']['repro_events']['status'] == 'staged'
    assert res['datasets']['basic_events']['status'] == 'staged'
    assert res['adoption_plan']['current_ready_stage'] == 'stage_4_basic_events'

    animals_csv = artifacts / 'dv_t26_01' / 'canonical' / 'dm_animals.csv'
    lact_csv = artifacts / 'dv_t26_01' / 'canonical' / 'dm_lactations.csv'
    tx_csv = artifacts / 'dv_t26_01' / 'canonical' / 'dm_treatments.csv'
    repro_preview = artifacts / 'dv_t26_01' / 'migration_staging' / 'repro_events_operational_preview.jsonl'
    basic_preview = artifacts / 'dv_t26_01' / 'migration_staging' / 'basic_events_operational_preview.jsonl'
    bundle_json = artifacts / 'dv_t26_01' / 'metadata' / 'legacy_import_bundle.json'

    assert animals_csv.exists()
    assert lact_csv.exists()
    assert tx_csv.exists()
    assert repro_preview.exists()
    assert basic_preview.exists()
    assert bundle_json.exists()

    repro_rows = [json.loads(line) for line in repro_preview.read_text(encoding='utf-8').splitlines() if line.strip()]
    basic_rows = [json.loads(line) for line in basic_preview.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert repro_rows[0]['event_preview']['event_type'] == 'insemination'
    assert basic_rows[0]['event_preview']['event_type'] == 'pen_move'
    assert basic_rows[1]['event_preview']['event_type'] == 'manual_note'

    reconciliation = res['quality_reconciliation_summary']
    assert reconciliation['schema'] == 'genomeai.legacy_import_reconciliation_summary.v1'
    assert reconciliation['orphan_animal_refs'] == {}



def test_t26_01_diagnostics_are_explainable_and_bounded(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    source = tmp_path / 'basic_events_bad.csv'
    _write(
        source,
        'EventID,AnimalID,FarmID,EventDate,EventType,Comment,PenID\n'
        'BE1,A1,F1,not-a-date,custom_unknown,moved,PEN-2\n',
    )
    diag = preview_legacy_mapping_diagnostics(
        dataset_key='basic_events',
        file_path=source,
        mapping_path=resolve_legacy_mapping_template(adapter_key='generic_hms_csv_bundle', dataset_key='basic_events', project_root=repo),
        project_root=repo,
        max_issues=20,
    )
    codes = {row['code'] for row in diag['issues']}
    assert 'missing_source_column' in codes or 'required_field_not_mapped' not in codes
    assert 'coercion_failed' in codes
    assert 'event_type_will_be_normalized' in codes

    plan = build_legacy_import_plan(adapter_key='generic_hms_csv_bundle', provided_datasets={'animals': source, 'lactations': source, 'basic_events': source})
    assert plan['current_ready_stage'] == 'stage_4_basic_events'
    assert any(stage['stage'] == 'stage_1_master_data' and stage['status'] == 'ready' for stage in plan['stages'])
