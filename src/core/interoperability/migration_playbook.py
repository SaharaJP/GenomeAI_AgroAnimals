from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from core.artifacts import build_support_bundle
from core.audit.events import write_audit
from core.infra.postgres_compat import connect_postgres_compat as _pg_connect
from core.interoperability.legacy_import import build_legacy_import_plan
from core.interoperability.migration_verification import (
    list_migration_candidate_versions,
    list_migration_verification_runs,
    load_migration_verification_manifest,
)
from core.interoperability.parallel_run import (
    list_parallel_run_runs,
    load_parallel_run_manifest,
)
from genomeai.backup_restore import make_backup
from genomeai.versioning import write_json

_REQUIRED_IMPORT_DATASETS = ('animals', 'lactations')
_REQUIRED_RUNTIME_DATASETS = ('animals', 'lactations', 'treatments')
_REQUIRED_TRAINING_ROLES = ('Admin', 'Operator', 'Viewer')


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _new_playbook_run_id() -> str:
    return f"mpb_{_utcnow().strftime('%Y%m%dT%H%M%SZ')}"


def _clean_str(value: Any) -> str:
    return str(value or '').strip()


def _to_export_xlsx(checklist_df: pd.DataFrame, diagnostics_df: pd.DataFrame, summary_rows: list[dict[str, Any]], manifest: Mapping[str, Any]) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as writer:
        checklist_df.to_excel(writer, sheet_name='checklist', index=False)
        diagnostics_df.to_excel(writer, sheet_name='diagnostics', index=False)
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name='summary', index=False)
        pd.DataFrame(list(manifest.get('rollback_criteria') or []), columns=['criterion']).to_excel(writer, sheet_name='rollback', index=False)
        pd.DataFrame(list(manifest.get('assumptions') or []), columns=['assumption']).to_excel(writer, sheet_name='assumptions', index=False)
    return bio.getvalue()


def list_migration_playbook_candidate_versions(*, artifacts_root: Path) -> list[str]:
    return list_migration_candidate_versions(artifacts_root=Path(artifacts_root))


def list_migration_playbook_runs(*, artifacts_root: Path, data_version: str) -> list[str]:
    base = Path(artifacts_root).resolve() / str(data_version) / 'migration_playbook'
    if not base.exists():
        return []
    return sorted([p.name for p in base.iterdir() if p.is_dir() and (p / 'playbook_manifest.json').exists()])


def load_migration_playbook_manifest(*, artifacts_root: Path, data_version: str, playbook_run: str) -> dict[str, Any]:
    path = Path(artifacts_root).resolve() / str(data_version) / 'migration_playbook' / str(playbook_run) / 'playbook_manifest.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _latest_verification(*, artifacts_root: Path, data_version: str) -> tuple[str | None, dict[str, Any] | None]:
    runs = list_migration_verification_runs(artifacts_root=Path(artifacts_root), data_version=str(data_version))
    if not runs:
        return None, None
    run_id = runs[-1]
    return run_id, load_migration_verification_manifest(artifacts_root=Path(artifacts_root), data_version=str(data_version), verification_run=str(run_id))


def _latest_parallel(*, artifacts_root: Path, data_version: str) -> tuple[str | None, dict[str, Any] | None]:
    runs = list_parallel_run_runs(artifacts_root=Path(artifacts_root), data_version=str(data_version))
    if not runs:
        return None, None
    run_id = runs[-1]
    return run_id, load_parallel_run_manifest(artifacts_root=Path(artifacts_root), data_version=str(data_version), parallel_run_id=str(run_id))


def _latest_issue_preview(verification_manifest: Mapping[str, Any] | None, *, limit: int = 8) -> list[dict[str, Any]]:
    if not verification_manifest:
        return []
    issues_csv = Path(str(((verification_manifest.get('outputs') or {}).get('issues_csv') or '')))
    if not issues_csv.exists():
        return []
    try:
        df = pd.read_csv(issues_csv)
    except Exception:
        return []
    if df.empty:
        return []
    keep = [c for c in ['dataset_key', 'severity', 'code', 'message', 'scope_kind', 'scope_key'] if c in df.columns]
    return df[keep].head(limit).to_dict(orient='records')


def _parallel_limitations(parallel_manifest: Mapping[str, Any] | None, *, limit: int = 8) -> list[dict[str, Any]]:
    if not parallel_manifest:
        return []
    path = Path(str(((parallel_manifest.get('outputs') or {}).get('scope_limitations_csv') or '')))
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    if df.empty:
        return []
    keep = [c for c in ['dataset_key', 'trusted_scope', 'runtime_scope', 'message'] if c in df.columns]
    return df[keep].head(limit).to_dict(orient='records')


def _count_status(rows: Iterable[Mapping[str, Any]], status: str) -> int:
    target = str(status).strip().lower()
    return sum(1 for row in rows if _clean_str(row.get('status')).lower() == target)


def _required_import_ready(bundle: Mapping[str, Any]) -> tuple[bool, list[str], int]:
    datasets = dict(bundle.get('datasets') or {})
    missing: list[str] = []
    issue_total = 0
    for key in _REQUIRED_IMPORT_DATASETS:
        meta = dict(datasets.get(key) or {})
        if _clean_str(meta.get('status')) != 'ingested':
            missing.append(key)
        issue_total += int(meta.get('issue_count') or 0)
    return (not missing), missing, issue_total


def _verification_step(verification_manifest: Mapping[str, Any] | None) -> tuple[str, str, list[str], dict[str, int]]:
    if not verification_manifest:
        return 'blocked', 'Нет verification run. Выполните formal migration verification перед cutover preview.', ['Run T26-02 verification toolkit and review mismatches before cutover.'], {'matched': 0, 'mismatch': 0, 'manual_review': 0}
    rows = list(verification_manifest.get('dataset_status_rows') or [])
    matched = _count_status(rows, 'matched')
    mismatch = _count_status(rows, 'mismatch')
    manual = _count_status(rows, 'manual_review')
    issues: list[str] = []
    if mismatch > 0:
        issues.append('Есть datasets со статусом mismatch; cutover preview не должен считаться готовым.')
        return 'blocked', f'Verification: mismatch={mismatch}, manual_review={manual}.', issues, {'matched': matched, 'mismatch': mismatch, 'manual_review': manual}
    if manual > 0:
        issues.append('Есть datasets, требующие ручной проверки, до cutover preview.')
        return 'warning', f'Verification: matched={matched}, manual_review={manual}.', issues, {'matched': matched, 'mismatch': mismatch, 'manual_review': manual}
    return 'ready', f'Verification: matched={matched} datasets, mismatches not found.', issues, {'matched': matched, 'mismatch': mismatch, 'manual_review': manual}


def _parallel_step(parallel_manifest: Mapping[str, Any] | None) -> tuple[str, str, list[str], dict[str, int]]:
    if not parallel_manifest:
        return 'blocked', 'Нет parallel run snapshot. Выполните T26-03 parallel run mode перед cutover preview.', ['Build a fresh parallel run snapshot and validate freshness/trusted scope before cutover.'], {'stale': 0, 'manual_review': 0}
    rows = list(parallel_manifest.get('dataset_rows') or [])
    row_map = {str(row.get('dataset_key') or ''): dict(row) for row in rows}
    stale = 0
    manual = 0
    warnings: list[str] = []
    for key in _REQUIRED_RUNTIME_DATASETS:
        row = row_map.get(key) or {}
        if _clean_str(row.get('runtime_scope')) not in {'read_write', 'read_only_preview'}:
            warnings.append(f'{key}: runtime scope is not ready.')
            manual += 1
        if _clean_str(row.get('trusted_scope')) == 'manual_review':
            warnings.append(f'{key}: trusted scope is manual_review.')
            manual += 1
        if _clean_str(row.get('freshness_status')) == 'stale':
            warnings.append(f'{key}: latest batch export is stale.')
            stale += 1
    if manual > 0:
        return 'blocked', f'Parallel run has manual_review/not_ready scope on required datasets (count={manual}).', warnings, {'stale': stale, 'manual_review': manual}
    if stale > 0:
        return 'warning', f'Parallel run exists but stale batch exports were found (count={stale}).', warnings, {'stale': stale, 'manual_review': manual}
    return 'ready', 'Parallel run snapshot is available for required datasets with bounded trusted scope.', warnings, {'stale': stale, 'manual_review': manual}


def _training_step(trained_roles: Iterable[str], training_notes: str) -> tuple[str, str, list[str], dict[str, Any]]:
    trained = sorted(set([_clean_str(x) for x in trained_roles if _clean_str(x)]))
    missing = [role for role in _REQUIRED_TRAINING_ROLES if role not in trained]
    notes = _clean_str(training_notes)
    if missing:
        return 'manual_action', f'Training incomplete. Missing core roles: {", ".join(missing)}.', ['Complete field training and sign-off for core roles before cutover preview.'], {'trained_roles': trained, 'missing_roles': missing, 'notes': notes}
    return 'ready', f'Training sign-off recorded for roles: {", ".join(trained)}.', [], {'trained_roles': trained, 'missing_roles': missing, 'notes': notes}


def _rollback_step(*, backup_path: Path | None, support_bundle_path: Path | None) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if backup_path is None or not backup_path.exists():
        warnings.append('Preview backup zip is missing.')
    if support_bundle_path is None or not support_bundle_path.exists():
        warnings.append('Support bundle is missing.')
    if warnings:
        return 'blocked', 'Rollback readiness is incomplete.', warnings
    return 'ready', 'Backup preview and support bundle are available for rollback/incident handling.', warnings


def _cutover_preview_step(step_rows: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    bad = [row for row in step_rows if _clean_str(row.get('step_key')) in {'data_import', 'verification', 'parallel_run', 'training', 'rollback_readiness'} and _clean_str(row.get('status')) in {'blocked', 'manual_action'}]
    warn = [row for row in step_rows if _clean_str(row.get('step_key')) in {'data_import', 'verification', 'parallel_run'} and _clean_str(row.get('status')) == 'warning']
    if bad:
        return 'blocked', 'Cutover preview blocked by upstream checklist items.', [f"{row.get('step_key')}: {row.get('summary')}" for row in bad]
    if warn:
        return 'preview_ready', 'Cutover preview allowed with visible warnings; do not treat this as irreversible cutover.', [f"{row.get('step_key')}: {row.get('summary')}" for row in warn]
    return 'preview_ready', 'Cutover preview is ready. Proceed only with preview/backup-confirmed change window.', []


def _overall_readiness(step_rows: list[dict[str, Any]]) -> str:
    cutover = next((row for row in step_rows if _clean_str(row.get('step_key')) == 'cutover_preview'), None)
    if cutover and _clean_str(cutover.get('status')) == 'preview_ready':
        return 'ready_for_cutover_preview'
    if any(_clean_str(row.get('status')) == 'blocked' for row in step_rows):
        return 'blocked'
    return 'manual_review'


def _rollback_criteria() -> list[str]:
    return [
        'Rollback immediately if required dataset verification status moves to mismatch after latest import/verification rerun.',
        'Rollback if field users cannot complete core actions safely in parallel run / post-cutover preview window.',
        'Rollback if fresh batch exports are unavailable and operational scope becomes stale for required datasets.',
        'Rollback if support bundle or deterministic backup preview is missing for the active migration window.',
    ]


def _assumptions() -> list[str]:
    return [
        'Playbook run is preview-only and does not execute irreversible cutover actions.',
        'Freshness/trusted scope inherit the limitations of batch legacy exports and latest verification evidence.',
        'Support bundle and backup preview are created to support incident-ready migration handling and rollback decisions.',
    ]


def _report_md(manifest: Mapping[str, Any]) -> str:
    lines = [
        '# Migration playbook and cutover report',
        '',
        f"- data_version: {manifest.get('data_version')}",
        f"- playbook_run: {manifest.get('playbook_run')}",
        f"- generated_at: {manifest.get('generated_at')}",
        f"- overall_readiness: {manifest.get('overall_readiness')}",
        '',
        '## Checklist',
        '',
    ]
    for row in list(manifest.get('checklist_rows') or []):
        lines.append(f"- [{row.get('status')}] {row.get('label')}: {row.get('summary')}")
        issues = list(row.get('issues') or [])
        for issue in issues[:5]:
            lines.append(f"  - {issue}")
    lines.extend(['', '## Rollback criteria', ''])
    for item in list(manifest.get('rollback_criteria') or []):
        lines.append(f'- {item}')
    lines.extend(['', '## Latest evidence', ''])
    lines.append(f"- legacy_import_bundle: {manifest.get('legacy_import_bundle')}")
    lines.append(f"- latest_verification_run: {manifest.get('latest_verification_run') or 'NA'}")
    lines.append(f"- latest_parallel_run: {manifest.get('latest_parallel_run') or 'NA'}")
    lines.append(f"- backup_preview_zip: {((manifest.get('outputs') or {}).get('backup_preview_zip') or 'NA')}")
    lines.append(f"- support_bundle_zip: {((manifest.get('outputs') or {}).get('support_bundle_zip') or 'NA')}")
    lines.append('')
    return '\n'.join(lines) + '\n'


def run_migration_playbook_and_cutover(
    *,
    project_root: Path,
    artifacts_root: Path,
    web_storage: Path,
    db_path: Path,
    data_version: str,
    playbook_run: str | None = None,
    trained_roles: Iterable[str] | None = None,
    training_notes: str = '',
    build_backup_preview: bool = True,
    collect_support_bundle: bool = True,
    tenant_id: str = 'default',
    user_id: int = 0,
    username: str = 'system',
    role: str = 'Admin',
    request_id: str | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    artifacts_root = Path(artifacts_root).resolve()
    web_storage = Path(web_storage).resolve()
    db_path = Path(db_path).resolve()
    data_version = str(data_version)
    bundle_path = artifacts_root / data_version / 'metadata' / 'legacy_import_bundle.json'
    if not bundle_path.exists():
        raise FileNotFoundError(f'legacy import bundle not found for data_version={data_version}')
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))

    latest_verification_run, verification_manifest = _latest_verification(artifacts_root=artifacts_root, data_version=data_version)
    latest_parallel_run, parallel_manifest = _latest_parallel(artifacts_root=artifacts_root, data_version=data_version)

    playbook_run = str(playbook_run or _new_playbook_run_id())
    run_dir = artifacts_root / data_version / 'migration_playbook' / playbook_run
    run_dir.mkdir(parents=True, exist_ok=True)

    backup_preview_zip = None
    if build_backup_preview:
        backup_preview_zip = run_dir / f'{playbook_run}_backup_preview.zip'
        make_backup(
            artifacts_root=artifacts_root,
            web_storage=web_storage,
            db_path=db_path,
            out_zip=backup_preview_zip,
            project_root=project_root,
        )

    support_bundle_zip = None
    if collect_support_bundle:
        support_bundle_zip = run_dir / f'{playbook_run}_support_bundle.zip'
        build_support_bundle(
            output_zip=support_bundle_zip,
            project_root=project_root,
            artifacts_root=artifacts_root,
            web_storage=web_storage,
            db_path=db_path,
        )

    import_ready, import_missing, import_issue_total = _required_import_ready(bundle)
    import_plan = build_legacy_import_plan(adapter_key=str(bundle.get('adapter_key') or ''), provided_datasets={k: True for k in dict(bundle.get('datasets') or {}).keys()})
    import_status = 'ready' if import_ready and import_issue_total == 0 else ('warning' if import_ready else 'blocked')
    import_summary = 'Required migration datasets were imported into the current canonical/staging bundle.' if import_ready else f'Missing required imported datasets: {", ".join(import_missing)}.'
    import_issues = []
    if import_issue_total > 0:
        import_issues.append(f'Legacy import recorded issue_count={import_issue_total} on required datasets.')
    if import_missing:
        import_issues.append('Run/repair legacy import adapters before cutover preview.')

    verification_status, verification_summary, verification_issues, verification_counts = _verification_step(verification_manifest)
    parallel_status, parallel_summary, parallel_issues, parallel_counts = _parallel_step(parallel_manifest)
    training_status, training_summary, training_issues, training_meta = _training_step(trained_roles or [], training_notes)
    rollback_status, rollback_summary, rollback_issues = _rollback_step(backup_path=backup_preview_zip, support_bundle_path=support_bundle_zip)

    step_rows = [
        {
            'step_key': 'data_import',
            'label': 'Data import and mapping readiness',
            'status': import_status,
            'summary': import_summary,
            'issues': import_issues,
            'details': {'missing_required_datasets': import_missing, 'issue_total': import_issue_total, 'plan': import_plan},
        },
        {
            'step_key': 'verification',
            'label': 'Formal migration verification',
            'status': verification_status,
            'summary': verification_summary,
            'issues': verification_issues,
            'details': {'latest_verification_run': latest_verification_run, **verification_counts},
        },
        {
            'step_key': 'parallel_run',
            'label': 'Parallel run and freshness scope',
            'status': parallel_status,
            'summary': parallel_summary,
            'issues': parallel_issues,
            'details': {'latest_parallel_run': latest_parallel_run, **parallel_counts},
        },
        {
            'step_key': 'training',
            'label': 'User training and field readiness',
            'status': training_status,
            'summary': training_summary,
            'issues': training_issues,
            'details': training_meta,
        },
        {
            'step_key': 'rollback_readiness',
            'label': 'Rollback criteria and support readiness',
            'status': rollback_status,
            'summary': rollback_summary,
            'issues': rollback_issues,
            'details': {
                'backup_preview_zip': str(backup_preview_zip) if backup_preview_zip else '',
                'support_bundle_zip': str(support_bundle_zip) if support_bundle_zip else '',
            },
        },
    ]
    cutover_status, cutover_summary, cutover_issues = _cutover_preview_step(step_rows)
    step_rows.append({
        'step_key': 'cutover_preview',
        'label': 'Cutover preview',
        'status': cutover_status,
        'summary': cutover_summary,
        'issues': cutover_issues,
        'details': {
            'preview_only': True,
            'request_id': request_id,
        },
    })

    overall = _overall_readiness(step_rows)
    rollback_criteria = _rollback_criteria()
    assumptions = _assumptions()

    diagnostics = {
        'latest_import_issue_preview': _latest_issue_preview(verification_manifest),
        'parallel_scope_limitations': _parallel_limitations(parallel_manifest),
        'latest_verification_run': latest_verification_run,
        'latest_parallel_run': latest_parallel_run,
        'request_id': request_id,
    }

    checklist_df = pd.DataFrame([
        {
            'step_key': row['step_key'],
            'label': row['label'],
            'status': row['status'],
            'summary': row['summary'],
            'issues': ' | '.join(list(row.get('issues') or [])),
        }
        for row in step_rows
    ])
    diagnostics_df = pd.DataFrame([
        {'category': 'verification_issue', **item} for item in diagnostics['latest_import_issue_preview']
    ] + [
        {'category': 'parallel_scope_limitation', **item} for item in diagnostics['parallel_scope_limitations']
    ])
    summary_rows = [
        {'metric': 'overall_readiness', 'value': overall},
        {'metric': 'steps_total', 'value': len(step_rows)},
        {'metric': 'blocked', 'value': int((checklist_df['status'] == 'blocked').sum()) if not checklist_df.empty else 0},
        {'metric': 'warning', 'value': int((checklist_df['status'] == 'warning').sum()) if not checklist_df.empty else 0},
        {'metric': 'manual_action', 'value': int((checklist_df['status'] == 'manual_action').sum()) if not checklist_df.empty else 0},
    ]

    checklist_csv = run_dir / 'checklist_rows.csv'
    checklist_xlsx = run_dir / 'checklist_report.xlsx'
    diagnostics_json = run_dir / 'incident_diagnostics.json'
    report_md = run_dir / 'cutover_report.md'
    manifest_path = run_dir / 'playbook_manifest.json'
    checklist_df.to_csv(checklist_csv, index=False, encoding='utf-8')

    manifest = {
        'schema': 'genomeai.migration_playbook_and_cutover.v1',
        'data_version': data_version,
        'playbook_run': playbook_run,
        'generated_at': _utcnow().isoformat(),
        'overall_readiness': overall,
        'legacy_import_bundle': str(bundle_path),
        'adapter_key': str(bundle.get('adapter_key') or ''),
        'latest_verification_run': latest_verification_run,
        'latest_parallel_run': latest_parallel_run,
        'checklist_rows': step_rows,
        'summary_rows': summary_rows,
        'rollback_criteria': rollback_criteria,
        'assumptions': assumptions,
        'diagnostics': diagnostics,
        'outputs': {
            'checklist_csv': str(checklist_csv),
            'checklist_xlsx': str(checklist_xlsx),
            'incident_diagnostics_json': str(diagnostics_json),
            'cutover_report_md': str(report_md),
            'backup_preview_zip': str(backup_preview_zip) if backup_preview_zip else '',
            'support_bundle_zip': str(support_bundle_zip) if support_bundle_zip else '',
        },
    }
    checklist_xlsx.write_bytes(_to_export_xlsx(checklist_df, diagnostics_df, summary_rows, manifest))
    diagnostics_json.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')
    report_md.write_text(_report_md(manifest), encoding='utf-8')
    write_json(manifest_path, manifest)

    conn = _pg_connect()
    try:
        write_audit(
            conn,
            tenant_id=str(tenant_id or 'default'),
            user_id=int(user_id or 0),
            username=str(username or 'system'),
            role=str(role or 'Admin'),
            action='migration.playbook.run',
            object_type='migration_playbook',
            object_id=playbook_run,
            data_version=data_version,
            before=None,
            after={
                'overall_readiness': overall,
                'latest_verification_run': latest_verification_run,
                'latest_parallel_run': latest_parallel_run,
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
    'list_migration_playbook_candidate_versions',
    'list_migration_playbook_runs',
    'load_migration_playbook_manifest',
    'run_migration_playbook_and_cutover',
]
