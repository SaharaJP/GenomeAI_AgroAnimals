from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.audit.events import write_audit
from core.infra.web_db import connect, init_db
from core.interoperability.migration_verification import (
    list_migration_verification_runs,
    load_migration_verification_manifest,
)
from genomeai.versioning import write_json


_FRESH_HOURS_FRESH = 24.0
_FRESH_HOURS_AGING = 72.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _new_parallel_run_id() -> str:
    return 'prun_' + _utcnow().strftime('%Y%m%d_%H%M%S')


def _clean_str(value: Any) -> str:
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except Exception:
        pass
    return str(value).strip()


def _iso_from_ts(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(microsecond=0).isoformat()


def _mtime(path: Path | None) -> float | None:
    if not path:
        return None
    try:
        return path.stat().st_mtime if path.exists() else None
    except Exception:
        return None


def _hours_since(ts: float | None, *, now: datetime) -> float | None:
    if ts is None:
        return None
    return round((now.timestamp() - float(ts)) / 3600.0, 2)


def _minutes_between(newer: float | None, older: float | None) -> float | None:
    if newer is None or older is None:
        return None
    if newer < older:
        return 0.0
    return round((float(newer) - float(older)) / 60.0, 2)


def _freshness_status(export_age_hours: float | None) -> str:
    if export_age_hours is None:
        return 'unknown'
    if export_age_hours <= _FRESH_HOURS_FRESH:
        return 'fresh'
    if export_age_hours <= _FRESH_HOURS_AGING:
        return 'aging'
    return 'stale'


def _source_system_label(adapter_key: str) -> str:
    key = str(adapter_key or '').strip().lower()
    if key == 'dairycomp_305_basic':
        return 'DairyComp 305 batch export'
    if key == 'selex_basic':
        return 'СЕЛЭКС batch export'
    if key == 'generic_hms_csv_bundle':
        return 'Legacy HMS CSV batch export'
    return key or 'legacy batch export'


def _primary_output(dataset_meta: Mapping[str, Any]) -> Path | None:
    outputs = dict(dataset_meta.get('outputs') or {})
    for key in ('canonical_csv', 'staging_csv', 'operational_preview_jsonl', 'canonical_parquet'):
        value = _clean_str(outputs.get(key))
        if value:
            path = Path(value).resolve()
            if path.exists():
                return path
    return None


def _latest_verification_statuses(*, artifacts_root: Path, data_version: str) -> tuple[str | None, dict[str, str]]:
    runs = list_migration_verification_runs(artifacts_root=Path(artifacts_root), data_version=str(data_version))
    if not runs:
        return None, {}
    latest = runs[-1]
    manifest = load_migration_verification_manifest(artifacts_root=Path(artifacts_root), data_version=str(data_version), verification_run=str(latest))
    rows = list(manifest.get('dataset_status_rows') or [])
    mapping = {str(row.get('dataset_key') or ''): str(row.get('status') or '') for row in rows if str(row.get('dataset_key') or '').strip()}
    return latest, mapping


def _dataset_scope_status(*, dataset_key: str, import_status: str, issue_count: int, freshness_status: str, verification_status: str | None) -> tuple[str, str, list[str]]:
    limitations: list[str] = [
        'Legacy contour remains batch-based. GenomeAI must not be treated as near-real-time unless upstream source changes.'
    ]
    runtime_scope = 'read_only_preview'
    trusted_scope = 'reference_only'
    if import_status == 'ingested':
        runtime_scope = 'read_write'
        trusted_scope = 'trusted'
    elif import_status == 'staged':
        runtime_scope = 'read_only_preview'
        trusted_scope = 'reference_only'
        limitations.append('Dataset is staged only and is not appended directly into runtime append-only tables.')
    else:
        runtime_scope = 'not_ready'
        trusted_scope = 'manual_review'
        limitations.append('Dataset import is incomplete; operator should treat the scope as migration-only.')

    if issue_count > 0 and trusted_scope == 'trusted':
        trusted_scope = 'trusted_with_warnings'
        limitations.append('Mapping/QC issues were recorded during legacy import; review diagnostics before relying on this scope.')
    elif issue_count > 0:
        limitations.append('Mapping/QC issues were recorded during legacy import; review diagnostics before relying on this scope.')

    if freshness_status == 'stale':
        limitations.append('Latest batch export is stale; trusted scope is limited by export age.')
    elif freshness_status == 'aging':
        limitations.append('Latest batch export is aging; daily use is acceptable only for bounded operational checks.')
    elif freshness_status == 'unknown':
        limitations.append('Freshness could not be derived from the source file timestamp.')

    ver = str(verification_status or '').strip().lower()
    if ver == 'mismatch':
        trusted_scope = 'manual_review'
        limitations.append('Latest migration verification reported mismatches for this dataset.')
    elif ver == 'manual_review' and trusted_scope == 'trusted':
        trusted_scope = 'trusted_with_warnings'
        limitations.append('Latest migration verification flagged manual review items for this dataset.')
    elif ver == 'matched' and trusted_scope == 'trusted':
        limitations.append('Latest migration verification matched this dataset.')

    if dataset_key in {'repro_events', 'basic_events'} and import_status == 'staged':
        limitations.append('Operational events remain in preview/staged mode during parallel run; legacy HMS remains the source of execution truth.')

    return runtime_scope, trusted_scope, limitations


def list_parallel_run_candidate_versions(*, artifacts_root: Path) -> list[str]:
    base = Path(artifacts_root).resolve()
    if not base.exists():
        return []
    out: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if (child / 'metadata' / 'legacy_import_bundle.json').exists():
            out.append(child.name)
    return out


def list_parallel_run_runs(*, artifacts_root: Path, data_version: str) -> list[str]:
    base = Path(artifacts_root).resolve() / str(data_version) / 'parallel_run'
    if not base.exists():
        return []
    return sorted([p.name for p in base.iterdir() if p.is_dir() and (p / 'parallel_run_manifest.json').exists()])


def load_parallel_run_manifest(*, artifacts_root: Path, data_version: str, parallel_run_id: str) -> dict[str, Any]:
    path = Path(artifacts_root).resolve() / str(data_version) / 'parallel_run' / str(parallel_run_id) / 'parallel_run_manifest.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _to_export_xlsx(dataset_df: pd.DataFrame, limitation_df: pd.DataFrame, summary_rows: list[dict[str, Any]], manifest: Mapping[str, Any]) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        dataset_df.to_excel(writer, sheet_name='dataset_status', index=False)
        limitation_df.to_excel(writer, sheet_name='scope_limitations', index=False)
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name='summary', index=False)
        pd.DataFrame(list(manifest.get('assumptions') or []), columns=['assumption']).to_excel(writer, sheet_name='assumptions', index=False)
    return bio.getvalue()


def run_parallel_run_mode(
    *,
    project_root: Path,
    artifacts_root: Path,
    data_version: str,
    parallel_run_id: str | None = None,
    db_path: Path | None = None,
    tenant_id: str = 'default',
    user_id: int = 0,
    username: str = 'system',
    role: str = 'Admin',
    request_id: str | None = None,
) -> dict[str, Any]:
    _ = Path(project_root).resolve()
    artifacts_root = Path(artifacts_root).resolve()
    data_version = str(data_version)
    bundle_path = artifacts_root / data_version / 'metadata' / 'legacy_import_bundle.json'
    if not bundle_path.exists():
        raise FileNotFoundError(f'legacy import bundle not found for data_version={data_version}')
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
    now = _utcnow()
    parallel_run_id = str(parallel_run_id or _new_parallel_run_id())
    run_dir = artifacts_root / data_version / 'parallel_run' / parallel_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    latest_verification_run, verification_statuses = _latest_verification_statuses(artifacts_root=artifacts_root, data_version=data_version)
    source_system = _source_system_label(str(bundle.get('adapter_key') or ''))

    dataset_rows: list[dict[str, Any]] = []
    limitation_rows: list[dict[str, Any]] = []
    for dataset_key, dataset_meta in dict(bundle.get('datasets') or {}).items():
        source_file = Path(str(dataset_meta.get('source_file') or '')).resolve() if _clean_str(dataset_meta.get('source_file')) else None
        output_path = _primary_output(dataset_meta)
        source_mtime = _mtime(source_file)
        import_mtime = _mtime(output_path)
        export_age_hours = _hours_since(source_mtime, now=now)
        imported_age_hours = _hours_since(import_mtime, now=now)
        sync_lag_minutes = _minutes_between(import_mtime, source_mtime)
        freshness_status = _freshness_status(export_age_hours)
        runtime_scope, trusted_scope, limitations = _dataset_scope_status(
            dataset_key=str(dataset_key),
            import_status=str(dataset_meta.get('status') or ''),
            issue_count=int(dataset_meta.get('issue_count') or 0),
            freshness_status=freshness_status,
            verification_status=verification_statuses.get(str(dataset_key)),
        )
        row = {
            'dataset_key': str(dataset_key),
            'source_system': source_system,
            'import_status': str(dataset_meta.get('status') or ''),
            'runtime_scope': runtime_scope,
            'trusted_scope': trusted_scope,
            'freshness_status': freshness_status,
            'source_export_ts': _iso_from_ts(source_mtime),
            'genomeai_import_ts': _iso_from_ts(import_mtime),
            'export_age_hours': export_age_hours,
            'imported_age_hours': imported_age_hours,
            'sync_lag_minutes': sync_lag_minutes,
            'issue_count': int(dataset_meta.get('issue_count') or 0),
            'rows_out': int(dataset_meta.get('rows_out') or 0),
            'verification_status': verification_statuses.get(str(dataset_key)) or 'not_run',
            'source_file': str(source_file) if source_file else '',
            'output_path': str(output_path) if output_path else '',
            'scope_limitations': ' | '.join(limitations),
        }
        dataset_rows.append(row)
        for message in limitations:
            limitation_rows.append({
                'dataset_key': str(dataset_key),
                'trusted_scope': trusted_scope,
                'runtime_scope': runtime_scope,
                'message': message,
            })

    dataset_df = pd.DataFrame(dataset_rows)
    limitation_df = pd.DataFrame(limitation_rows)
    if not dataset_df.empty:
        dataset_df = dataset_df.sort_values(['trusted_scope', 'dataset_key']).reset_index(drop=True)

    summary_rows = [
        {'metric': 'datasets_total', 'value': int(len(dataset_df))},
        {'metric': 'trusted', 'value': int((dataset_df['trusted_scope'] == 'trusted').sum()) if not dataset_df.empty else 0},
        {'metric': 'trusted_with_warnings', 'value': int((dataset_df['trusted_scope'] == 'trusted_with_warnings').sum()) if not dataset_df.empty else 0},
        {'metric': 'reference_only', 'value': int((dataset_df['trusted_scope'] == 'reference_only').sum()) if not dataset_df.empty else 0},
        {'metric': 'manual_review', 'value': int((dataset_df['trusted_scope'] == 'manual_review').sum()) if not dataset_df.empty else 0},
        {'metric': 'stale_batch', 'value': int((dataset_df['freshness_status'] == 'stale').sum()) if not dataset_df.empty else 0},
    ]

    assumptions = [
        'Parallel run mode is batch-based and inherits the freshness of the latest legacy export file.',
        'Source export timestamp is derived from file mtime; it is not a guaranteed HMS transaction timestamp.',
        'Staged operational datasets remain read-only preview during parallel run and must not be treated as day-1 cutover truth.',
    ]

    dataset_csv = run_dir / 'dataset_status.csv'
    limitation_csv = run_dir / 'scope_limitations.csv'
    dataset_xlsx = run_dir / 'parallel_run_report.xlsx'
    manifest_path = run_dir / 'parallel_run_manifest.json'
    dataset_df.to_csv(dataset_csv, index=False, encoding='utf-8')
    limitation_df.to_csv(limitation_csv, index=False, encoding='utf-8')
    dataset_xlsx.write_bytes(_to_export_xlsx(dataset_df, limitation_df, summary_rows, {'assumptions': assumptions}))

    manifest = {
        'schema': 'genomeai.parallel_run_manifest.v1',
        'data_version': data_version,
        'parallel_run_id': parallel_run_id,
        'generated_at': now.isoformat(),
        'legacy_import_bundle': str(bundle_path),
        'adapter_key': str(bundle.get('adapter_key') or ''),
        'source_system': source_system,
        'latest_verification_run': latest_verification_run,
        'summary_rows': summary_rows,
        'dataset_rows': dataset_rows,
        'assumptions': assumptions,
        'outputs': {
            'dataset_status_csv': str(dataset_csv),
            'scope_limitations_csv': str(limitation_csv),
            'parallel_run_xlsx': str(dataset_xlsx),
        },
    }
    write_json(manifest_path, manifest)

    if db_path is not None:
        db_path = Path(db_path).resolve()
        conn = connect(db_path)
        try:
            init_db(conn)
            write_audit(
                conn,
                tenant_id=str(tenant_id or 'default'),
                user_id=int(user_id or 0),
                username=str(username or 'system'),
                role=str(role or 'Admin'),
                action='migration.parallel_run.snapshot',
                object_type='parallel_run',
                object_id=parallel_run_id,
                data_version=data_version,
                before=None,
                after={
                    'parallel_run_id': parallel_run_id,
                    'adapter_key': manifest['adapter_key'],
                    'source_system': source_system,
                    'latest_verification_run': latest_verification_run,
                    'summary_rows': summary_rows,
                    'request_id': request_id,
                },
                status='OK',
            )
            conn.commit()
        finally:
            conn.close()

    return manifest


__all__ = [
    'list_parallel_run_candidate_versions',
    'list_parallel_run_runs',
    'load_parallel_run_manifest',
    'run_parallel_run_mode',
]
