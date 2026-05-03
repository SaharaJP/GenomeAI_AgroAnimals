from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.domain import model_dump_compat
from core.domain.enums import ANIMAL_EVENT_TYPES
from core.operational.animal_events import normalize_legacy_operational_event
from genomeai.contract_precheck import validate_source_by_contract
from genomeai.contracts import load_contracts_dir
from genomeai.ingest import _coerce_field, _read_tabular, ingest_dataset, load_mapping_yaml
from genomeai.versioning import write_json


_CONTRACT_DATASETS: dict[str, str] = {
    'animals': 'dm_animals',
    'lactations': 'dm_lactations',
    'treatments': 'dm_treatments',
    'health_events': 'dm_health_events',
}

_STAGE_SCHEMAS: dict[str, dict[str, Any]] = {
    'repro_events': {
        'required_fields': ('repro_event_id', 'animal_id', 'event_date', 'event_type'),
        'field_types': {
            'repro_event_id': 'string',
            'animal_id': 'string',
            'farm_id': 'string',
            'lactation_id': 'string',
            'event_date': 'date',
            'event_type': 'string',
            'result': 'string',
            'bull_id': 'string',
            'technician': 'string',
            'method': 'string',
            'notes': 'string',
        },
    },
    'basic_events': {
        'required_fields': ('event_id', 'animal_id', 'event_date', 'event_type'),
        'field_types': {
            'event_id': 'string',
            'animal_id': 'string',
            'farm_id': 'string',
            'event_date': 'date',
            'event_type': 'string',
            'comment': 'string',
            'pen_id': 'string',
            'reason_code': 'string',
        },
    },
}

_ALLOWED_BASIC_EVENT_TYPES = {
    'heat',
    'insemination',
    'preg_check',
    'calving',
    'dry_off',
    'treatment',
    'cull',
    'death',
    'pen_move',
    'manual_note',
    'custom_operational_event',
}


@dataclass(slots=True)
class LegacyImportIssue:
    dataset_key: str
    severity: str
    code: str
    message: str
    row: int | None = None
    source_column: str | None = None
    target_field: str | None = None
    sample_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LegacyImportDatasetResult:
    dataset_key: str
    status: str
    source_file: str
    mapping_file: str
    rows_in: int
    rows_out: int
    issue_count: int
    issue_preview: list[dict[str, Any]]
    outputs: dict[str, Any]
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            'dataset_key': self.dataset_key,
            'status': self.status,
            'source_file': self.source_file,
            'mapping_file': self.mapping_file,
            'rows_in': self.rows_in,
            'rows_out': self.rows_out,
            'issue_count': self.issue_count,
            'issue_preview': list(self.issue_preview),
            'outputs': dict(self.outputs),
            'assumptions': list(self.assumptions),
        }


def legacy_import_adapter_catalog() -> dict[str, Any]:
    return {
        'schema': 'genomeai.legacy_import_adapter_catalog.v1',
        'adapters': [
            {
                'adapter_key': 'generic_hms_csv_bundle',
                'label': 'Generic HMS CSV bundle',
                'supported_datasets': ['animals', 'lactations', 'repro_events', 'treatments', 'basic_events'],
                'description': 'Generic CSV/XLSX exports from legacy herd-management systems using explicit column mapping templates.',
            },
            {
                'adapter_key': 'dairycomp_305_basic',
                'label': 'DairyComp 305 basic exports',
                'supported_datasets': ['animals', 'lactations', 'repro_events', 'treatments', 'basic_events'],
                'description': 'Practical starter templates for DairyComp-like CSV exports. Requires reconciliation and field-by-field validation.',
            },
            {
                'adapter_key': 'selex_basic',
                'label': 'СЕЛЭКС basic exports',
                'supported_datasets': ['animals', 'lactations', 'repro_events', 'treatments', 'basic_events'],
                'description': 'Starter templates for common СЕЛЭКС-style exports. Assumptions are explicit in YAML templates and diagnostics.',
            },
        ],
    }


def resolve_legacy_mapping_template(*, adapter_key: str, dataset_key: str, project_root: Path) -> Path:
    path = Path(project_root).resolve() / 'configs' / 'mappings' / 'legacy' / str(adapter_key).strip() / f'{str(dataset_key).strip()}.yaml'
    if not path.exists():
        raise FileNotFoundError(f'legacy mapping template not found: adapter={adapter_key} dataset={dataset_key}')
    return path


def build_legacy_import_plan(*, adapter_key: str, provided_datasets: Mapping[str, Any]) -> dict[str, Any]:
    present = sorted([str(k) for k, v in dict(provided_datasets or {}).items() if v])
    stages: list[dict[str, Any]] = []
    ready_stage = 'none'
    if {'animals', 'lactations'}.issubset(set(present)):
        ready_stage = 'stage_1_master_data'
        stages.append({'stage': 'stage_1_master_data', 'status': 'ready', 'datasets': ['animals', 'lactations']})
    else:
        stages.append({'stage': 'stage_1_master_data', 'status': 'blocked', 'datasets': ['animals', 'lactations'], 'missing': sorted(set(['animals', 'lactations']) - set(present))})
    if 'repro_events' in present:
        ready_stage = 'stage_2_reproduction'
        stages.append({'stage': 'stage_2_reproduction', 'status': 'ready', 'datasets': ['repro_events']})
    else:
        stages.append({'stage': 'stage_2_reproduction', 'status': 'optional', 'datasets': ['repro_events']})
    if 'treatments' in present:
        ready_stage = 'stage_3_treatments'
        stages.append({'stage': 'stage_3_treatments', 'status': 'ready', 'datasets': ['treatments']})
    else:
        stages.append({'stage': 'stage_3_treatments', 'status': 'optional', 'datasets': ['treatments']})
    if 'basic_events' in present:
        ready_stage = 'stage_4_basic_events'
        stages.append({'stage': 'stage_4_basic_events', 'status': 'ready', 'datasets': ['basic_events']})
    else:
        stages.append({'stage': 'stage_4_basic_events', 'status': 'optional', 'datasets': ['basic_events']})
    return {
        'schema': 'genomeai.legacy_import_plan.v1',
        'adapter_key': str(adapter_key),
        'provided_datasets': present,
        'current_ready_stage': ready_stage,
        'stages': stages,
    }



def _mapping_duplicate_targets(mapping: Mapping[str, Any]) -> list[str]:
    counts: dict[str, int] = {}
    for _src, target in dict(mapping.get('columns') or {}).items():
        tgt = str(target)
        counts[tgt] = counts.get(tgt, 0) + 1
    return sorted([target for target, count in counts.items() if count > 1])



def _normalized_frame(*, file_path: Path, mapping_path: Path, known_fields: list[str], dayfirst: bool | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    mapping = load_mapping_yaml(mapping_path)
    if dayfirst is None:
        dayfirst = bool(mapping.get('dayfirst', False))
    df_raw = _read_tabular(file_path, mapping)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]
    col_map = {str(k): str(v) for k, v in dict(mapping.get('columns') or {}).items()}
    df = df_raw.rename(columns=col_map).copy()
    constants = mapping.get('constants') or {}
    if isinstance(constants, dict):
        for key, value in constants.items():
            df[str(key)] = value
    for field in known_fields:
        if field not in df.columns:
            df[field] = pd.NA
    df = df[[field for field in known_fields if field in df.columns]]
    return df_raw, df, {'mapping': mapping, 'dayfirst': bool(dayfirst), 'column_map': col_map}



def _clean_optional_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    raw = str(value).strip()
    return raw or None


def _add_issue(issues: list[LegacyImportIssue], *, dataset_key: str, severity: str, code: str, message: str, row: int | None = None, source_column: str | None = None, target_field: str | None = None, sample_value: Any = None) -> None:
    issues.append(LegacyImportIssue(
        dataset_key=str(dataset_key),
        severity=str(severity),
        code=str(code),
        message=str(message),
        row=row,
        source_column=source_column,
        target_field=target_field,
        sample_value=None if sample_value in (None, '') or pd.isna(sample_value) else str(sample_value),
    ))



def preview_legacy_mapping_diagnostics(*, dataset_key: str, file_path: Path, mapping_path: Path, project_root: Path, max_issues: int = 50) -> dict[str, Any]:
    dataset_key = str(dataset_key).strip()
    issues: list[LegacyImportIssue] = []
    if dataset_key in _CONTRACT_DATASETS:
        contracts = load_contracts_dir((Path(project_root).resolve() / 'configs' / 'contracts'))
        contract = contracts[_CONTRACT_DATASETS[dataset_key]]
        result = validate_source_by_contract(dataset_key=dataset_key, file_path=file_path, mapping_path=mapping_path, contract=contract, max_issues=max_issues)
        for item in result.issues[:max_issues]:
            _add_issue(
                issues,
                dataset_key=dataset_key,
                severity='error',
                code='contract_validation',
                message=item.message,
                row=item.row,
                source_column=item.source_column,
                target_field=item.target_field,
                sample_value=item.sample_value,
            )
        df_raw, _df, meta = _normalized_frame(file_path=file_path, mapping_path=mapping_path, known_fields=contract.field_names)
        extra_source_cols = sorted(set(df_raw.columns) - set(meta['column_map'].keys()))
        for col in extra_source_cols[:max(0, max_issues - len(issues))]:
            _add_issue(issues, dataset_key=dataset_key, severity='warn', code='unused_source_column', message='Колонка входного файла не используется mapping.', source_column=str(col))
        for target in _mapping_duplicate_targets(meta['mapping']):
            _add_issue(issues, dataset_key=dataset_key, severity='error', code='duplicate_target_mapping', message='Несколько source columns пишут в одно canonical поле.', target_field=target)
        return {
            'schema': 'genomeai.legacy_mapping_diagnostics.v1',
            'dataset_key': dataset_key,
            'rows_in': int(len(df_raw)),
            'issue_count': len(issues),
            'issues': [issue.to_dict() for issue in issues[:max_issues]],
        }

    schema = _STAGE_SCHEMAS.get(dataset_key)
    if not schema:
        raise ValueError(f'unsupported legacy dataset_key: {dataset_key}')
    known_fields = sorted(set(schema['field_types'].keys()))
    df_raw, df, meta = _normalized_frame(file_path=file_path, mapping_path=mapping_path, known_fields=known_fields)
    mapped_targets = set(df.columns)
    for src in meta['column_map'].keys():
        if src not in set(df_raw.columns):
            _add_issue(issues, dataset_key=dataset_key, severity='error', code='missing_source_column', message='Колонка из mapping не найдена во входном файле.', source_column=src, target_field=meta['column_map'].get(src))
    for target in _mapping_duplicate_targets(meta['mapping']):
        _add_issue(issues, dataset_key=dataset_key, severity='error', code='duplicate_target_mapping', message='Несколько source columns пишут в одно canonical поле.', target_field=target)
    for field in schema['required_fields']:
        if field not in mapped_targets:
            _add_issue(issues, dataset_key=dataset_key, severity='error', code='required_field_not_mapped', message='Обязательное поле staging schema не заполняется mapping/константами.', target_field=field)
    for field, typ in schema['field_types'].items():
        coerced, ok_mask = _coerce_field(df, field, typ, dayfirst=meta['dayfirst'])
        bad_idx = ok_mask[~ok_mask].index.tolist()
        for idx in bad_idx[:max(0, max_issues - len(issues))]:
            _add_issue(issues, dataset_key=dataset_key, severity='error', code='coercion_failed', message=f'Значение не приводится к типу {typ}.', row=int(idx) + 2, target_field=field, sample_value=df.loc[idx, field])
        df[field] = coerced
    for field in schema['required_fields']:
        missing = df[field].isna() | (df[field].astype('string').str.strip() == '')
        for idx in missing[missing].index.tolist()[:max(0, max_issues - len(issues))]:
            _add_issue(issues, dataset_key=dataset_key, severity='error', code='required_field_empty', message='Обязательное поле пустое после mapping/нормализации.', row=int(idx) + 2, target_field=field)
    if dataset_key == 'basic_events':
        for idx, value in enumerate(df.get('event_type', pd.Series(dtype=object)).astype('string').fillna('')):
            event_type = str(value).strip().lower()
            if event_type and event_type not in _ALLOWED_BASIC_EVENT_TYPES:
                _add_issue(issues, dataset_key=dataset_key, severity='warn', code='event_type_will_be_normalized', message='Тип события вне bounded taxonomy; будет нормализован в custom_operational_event.', row=idx + 2, target_field='event_type', sample_value=event_type)
                if len(issues) >= max_issues:
                    break
    extra_source_cols = sorted(set(df_raw.columns) - set(meta['column_map'].keys()))
    for col in extra_source_cols[:max(0, max_issues - len(issues))]:
        _add_issue(issues, dataset_key=dataset_key, severity='warn', code='unused_source_column', message='Колонка входного файла не используется mapping.', source_column=str(col))
    return {
        'schema': 'genomeai.legacy_mapping_diagnostics.v1',
        'dataset_key': dataset_key,
        'rows_in': int(len(df_raw)),
        'issue_count': len(issues),
        'issues': [issue.to_dict() for issue in issues[:max_issues]],
    }



def _write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')



def _stage_operational_dataset(*, dataset_key: str, file_path: Path, mapping_path: Path, project_root: Path, artifacts_root: Path, out_version: str, max_issues: int = 100) -> LegacyImportDatasetResult:
    schema = _STAGE_SCHEMAS[dataset_key]
    diagnostics = preview_legacy_mapping_diagnostics(dataset_key=dataset_key, file_path=file_path, mapping_path=mapping_path, project_root=project_root, max_issues=max_issues)
    known_fields = sorted(set(schema['field_types'].keys()))
    df_raw, df, meta = _normalized_frame(file_path=file_path, mapping_path=mapping_path, known_fields=known_fields)
    for field, typ in schema['field_types'].items():
        coerced, _ok = _coerce_field(df, field, typ, dayfirst=meta['dayfirst'])
        df[field] = coerced
    base = Path(artifacts_root).resolve() / str(out_version)
    staging_dir = base / 'migration_staging'
    meta_dir = base / 'metadata'
    staging_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    staged_csv = staging_dir / f'{dataset_key}.csv'
    df.to_csv(staged_csv, index=False, encoding='utf-8')

    preview_rows: list[dict[str, Any]] = []
    preview_issues: list[LegacyImportIssue] = []
    if dataset_key == 'repro_events':
        for idx, row in df.iterrows():
            try:
                event = normalize_legacy_operational_event(source_table='dm_repro_events', row=row.to_dict(), tenant_id='default')
                preview_rows.append({
                    'dataset_key': dataset_key,
                    'row_number': int(idx) + 2,
                    'event_preview': model_dump_compat(event),
                })
            except Exception as exc:
                _add_issue(preview_issues, dataset_key=dataset_key, severity='error', code='operational_preview_failed', message=str(exc), row=int(idx) + 2)
    elif dataset_key == 'basic_events':
        for idx, row in df.iterrows():
            raw_type = str(row.get('event_type') or '').strip().lower()
            normalized = raw_type if raw_type in _ALLOWED_BASIC_EVENT_TYPES else 'custom_operational_event'
            if raw_type and normalized != raw_type:
                _add_issue(preview_issues, dataset_key=dataset_key, severity='warn', code='event_type_normalized', message='Тип события нормализован в custom_operational_event.', row=int(idx) + 2, target_field='event_type', sample_value=raw_type)
            preview_rows.append({
                'dataset_key': dataset_key,
                'row_number': int(idx) + 2,
                'event_preview': {
                    'animal_id': str(_clean_optional_str(row.get('animal_id')) or ''),
                    'farm_id': _clean_optional_str(row.get('farm_id')),
                    'event_type': normalized,
                    'event_ts': str(row.get('event_date') or ''),
                    'source': 'migration',
                    'source_ref': f'basic_events:{row.get("event_id") or idx}',
                    'reason_code': _clean_optional_str(row.get('reason_code')),
                    'linked_object_type': ('pen' if _clean_optional_str(row.get('pen_id')) else None),
                    'linked_object_id': _clean_optional_str(row.get('pen_id')),
                    'payload': {
                        'comment': _clean_optional_str(row.get('comment')),
                        'legacy_event_id': _clean_optional_str(row.get('event_id')),
                        'legacy_event_type': raw_type,
                    },
                },
            })
    preview_jsonl = staging_dir / f'{dataset_key}_operational_preview.jsonl'
    _write_ndjson(preview_jsonl, preview_rows)
    all_issues = [LegacyImportIssue(**issue) for issue in diagnostics['issues']] + preview_issues
    assumptions = [
        'Stage-only import: rows are normalized into migration_staging and operational preview, not directly appended into append-only runtime tables.',
        'Reconciliation remains explicit; imported previews must be reviewed before staged adoption.',
    ]
    summary = {
        'schema': 'genomeai.legacy_import_stage_summary.v1',
        'dataset_key': dataset_key,
        'rows_in': int(len(df_raw)),
        'rows_out': int(len(df)),
        'issue_count': len(all_issues),
        'staging_csv': str(staged_csv),
        'operational_preview_jsonl': str(preview_jsonl),
    }
    write_json(meta_dir / f'legacy_import_{dataset_key}.json', summary)
    return LegacyImportDatasetResult(
        dataset_key=dataset_key,
        status='staged',
        source_file=str(file_path),
        mapping_file=str(mapping_path),
        rows_in=int(len(df_raw)),
        rows_out=int(len(df)),
        issue_count=len(all_issues),
        issue_preview=[issue.to_dict() for issue in all_issues[:max_issues]],
        outputs={'staging_csv': str(staged_csv), 'operational_preview_jsonl': str(preview_jsonl)},
        assumptions=assumptions,
    )



def _reconciliation_summary(*, dataset_results: Mapping[str, LegacyImportDatasetResult], artifacts_root: Path, out_version: str) -> dict[str, Any]:
    base = Path(artifacts_root).resolve() / str(out_version)
    summary: dict[str, Any] = {
        'schema': 'genomeai.legacy_import_reconciliation_summary.v1',
        'orphan_animal_refs': {},
        'warnings': [],
    }
    animals_path = base / 'canonical' / 'dm_animals.csv'
    animal_ids: set[str] = set()
    if animals_path.exists():
        animals = pd.read_csv(animals_path)
        animal_ids = {str(v).strip() for v in animals.get('animal_id', pd.Series(dtype=object)).astype(str).tolist() if str(v).strip()}
    for key, result in dataset_results.items():
        candidate_path = result.outputs.get('canonical_csv') or result.outputs.get('staging_csv')
        if not candidate_path:
            continue
        path = Path(candidate_path)
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if 'animal_id' in df.columns and animal_ids:
            refs = {str(v).strip() for v in df['animal_id'].astype(str).tolist() if str(v).strip()}
            missing = sorted(refs - animal_ids)
            if missing:
                summary['orphan_animal_refs'][key] = missing[:20]
    if 'treatments' in dataset_results and 'health_events' not in dataset_results:
        summary['warnings'].append('Treatments imported without health_events: reason_event_id reconciliation may remain unresolved.')
    if 'repro_events' in dataset_results and 'animals' not in dataset_results:
        summary['warnings'].append('Reproduction rows imported without animals dataset: staged adoption should remain read-only until animal reconciliation is completed.')
    return summary



def run_legacy_import_bundle(*, adapter_key: str, dataset_files: Mapping[str, Path], project_root: Path, artifacts_root: Path, out_version: str, template_overrides: Mapping[str, Path] | None = None, max_issue_preview: int = 100) -> dict[str, Any]:
    root = Path(project_root).resolve()
    artifacts_root = Path(artifacts_root).resolve()
    dataset_files = {str(k): Path(v).resolve() for k, v in dict(dataset_files or {}).items()}
    template_overrides = {str(k): Path(v).resolve() for k, v in dict(template_overrides or {}).items()}
    contracts = load_contracts_dir(root / 'configs' / 'contracts')

    results: dict[str, LegacyImportDatasetResult] = {}
    diagnostics: dict[str, Any] = {}
    assumptions: list[str] = [
        'Legacy import adapters are starter templates. They do not guarantee perfect one-click migration without reconciliation.',
        'Staged adoption is preferred over full cutover: master data first, then reproduction/treatments/basic events.',
    ]

    for dataset_key, file_path in dataset_files.items():
        mapping_path = template_overrides.get(dataset_key) or resolve_legacy_mapping_template(adapter_key=adapter_key, dataset_key=dataset_key, project_root=root)
        diagnostics[dataset_key] = preview_legacy_mapping_diagnostics(dataset_key=dataset_key, file_path=file_path, mapping_path=mapping_path, project_root=root, max_issues=max_issue_preview)
        if dataset_key in _CONTRACT_DATASETS:
            contract = contracts[_CONTRACT_DATASETS[dataset_key]]
            summary = ingest_dataset(
                dataset_key=dataset_key,
                file_path=file_path,
                mapping_path=mapping_path,
                contract=contract,
                artifacts_root=artifacts_root,
                out_version=out_version,
                max_error_examples=max_issue_preview,
            )
            results[dataset_key] = LegacyImportDatasetResult(
                dataset_key=dataset_key,
                status='ingested',
                source_file=str(file_path),
                mapping_file=str(mapping_path),
                rows_in=int(summary.get('rows_in') or 0),
                rows_out=int(summary.get('rows_out') or 0),
                issue_count=int(diagnostics[dataset_key].get('issue_count') or 0),
                issue_preview=list(diagnostics[dataset_key].get('issues') or [])[:max_issue_preview],
                outputs={'canonical_csv': str(summary.get('canonical_csv') or ''), 'canonical_parquet': summary.get('canonical_parquet')},
                assumptions=['Current ingest pipeline is reused; no mobile/import-only business logic is introduced.'],
            )
        elif dataset_key in _STAGE_SCHEMAS:
            results[dataset_key] = _stage_operational_dataset(dataset_key=dataset_key, file_path=file_path, mapping_path=mapping_path, project_root=root, artifacts_root=artifacts_root, out_version=out_version, max_issues=max_issue_preview)
        else:
            raise ValueError(f'unsupported legacy dataset_key: {dataset_key}')

    plan = build_legacy_import_plan(adapter_key=adapter_key, provided_datasets=dataset_files)
    reconciliation = _reconciliation_summary(dataset_results=results, artifacts_root=artifacts_root, out_version=out_version)
    total_issues = sum(int(item.issue_count) for item in results.values())
    summary = {
        'schema': 'genomeai.legacy_import_bundle.v1',
        'adapter_key': str(adapter_key),
        'out_version': str(out_version),
        'datasets': {key: item.to_dict() for key, item in results.items()},
        'migration_diagnostics': diagnostics,
        'quality_reconciliation_summary': reconciliation,
        'adoption_plan': plan,
        'assumptions': assumptions,
        'issue_count_total': int(total_issues),
    }
    meta_dir = artifacts_root / str(out_version) / 'metadata'
    meta_dir.mkdir(parents=True, exist_ok=True)
    write_json(meta_dir / 'legacy_import_bundle.json', summary)
    return summary


__all__ = [
    'build_legacy_import_plan',
    'legacy_import_adapter_catalog',
    'preview_legacy_mapping_diagnostics',
    'resolve_legacy_mapping_template',
    'run_legacy_import_bundle',
]
