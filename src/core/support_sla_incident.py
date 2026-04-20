from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

DEFAULT_SUPPORT_SLA_CFG = Path('configs/ops/support_sla_incident_v1.yaml')


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _norm_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path}: expected JSON object')
    return payload


def load_support_sla_incident_policy(path: str | Path = DEFAULT_SUPPORT_SLA_CFG) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'Support/SLA config not found: {p}')
    cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    if not isinstance(cfg, Mapping):
        raise ValueError('Support/SLA config must be a mapping')
    support_model = dict(cfg.get('support_model') or {})
    if not support_model:
        raise ValueError('Support/SLA config must contain support_model section')
    severity_levels = dict(support_model.get('severity_levels') or {})
    if not severity_levels:
        raise ValueError('Support/SLA severity_levels are required')
    records = dict(cfg.get('records') or {})
    if not str(records.get('path') or '').strip():
        raise ValueError('Support/SLA records.path is required')
    return dict(cfg)


def _runtime_records_path(*, project_root: Path, web_storage_dir: str | Path | None, cfg: Mapping[str, Any]) -> Path | None:
    rel = str(((cfg.get('records') or {}).get('runtime_relpath') or '')).strip()
    if not rel or web_storage_dir is None:
        return None
    return Path(web_storage_dir).resolve() / rel


def load_support_operating_records(
    *,
    project_root: str | Path = '.',
    web_storage_dir: str | Path | None = None,
    cfg_path: str | Path = DEFAULT_SUPPORT_SLA_CFG,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    cfg = load_support_sla_incident_policy(root / Path(cfg_path))
    runtime_path = _runtime_records_path(project_root=root, web_storage_dir=web_storage_dir, cfg=cfg)
    if runtime_path is not None and runtime_path.exists():
        payload = _load_json(runtime_path)
        payload['_record_source'] = str(runtime_path)
        payload['_record_source_mode'] = 'runtime'
        return payload
    starter_path = root / str((cfg.get('records') or {}).get('path'))
    payload = _load_json(starter_path)
    payload['_record_source'] = str(starter_path)
    payload['_record_source_mode'] = 'starter'
    return payload


def save_support_operating_records(
    payload: Mapping[str, Any],
    *,
    project_root: str | Path = '.',
    web_storage_dir: str | Path,
    cfg_path: str | Path = DEFAULT_SUPPORT_SLA_CFG,
) -> Path:
    root = Path(project_root).resolve()
    cfg = load_support_sla_incident_policy(root / Path(cfg_path))
    runtime_path = _runtime_records_path(project_root=root, web_storage_dir=web_storage_dir, cfg=cfg)
    if runtime_path is None:
        raise ValueError('web_storage_dir is required for runtime support records')
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data.pop('_record_source', None)
    data.pop('_record_source_mode', None)
    runtime_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return runtime_path


def _next_id(prefix: str, existing: Sequence[Mapping[str, Any]]) -> str:
    nums: list[int] = []
    for row in existing:
        raw = str(row.get(f'{prefix.lower()}_id') or row.get('case_id') or row.get('incident_id') or '')
        tail = raw.split('-')[-1]
        if tail.isdigit():
            nums.append(int(tail))
    nxt = (max(nums) if nums else 0) + 1
    return f'{prefix}-{datetime.now(timezone.utc).strftime("%Y%m%d")}-{nxt:03d}'


def append_support_case(
    *,
    project_root: str | Path = '.',
    web_storage_dir: str | Path,
    customer_label: str,
    severity: str,
    title: str,
    pilot_id: str = '',
    linked_surface: str = '',
    support_bundle_ref: str = '',
    diagnostics_ref: str = '',
    release_note_id: str = '',
    known_issue_id: str = '',
    version_linkage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = load_support_operating_records(project_root=project_root, web_storage_dir=web_storage_dir)
    cases = list(payload.get('support_cases') or [])
    entry = {
        'case_id': _next_id('CASE', cases),
        'status': 'open',
        'severity': str(severity or '').strip(),
        'title': str(title or '').strip(),
        'opened_at': _now_iso(),
        'customer_label': str(customer_label or '').strip(),
        'pilot_id': str(pilot_id or '').strip(),
        'linked_surface': str(linked_surface or '').strip(),
        'support_bundle_ref': str(support_bundle_ref or '').strip(),
        'diagnostics_ref': str(diagnostics_ref or '').strip(),
        'release_note_id': str(release_note_id or '').strip(),
        'known_issue_id': str(known_issue_id or '').strip(),
        'version_linkage': {str(k): str(v) for k, v in dict(version_linkage or {}).items() if str(v).strip()},
    }
    cases.append(entry)
    data = dict(payload)
    data['support_cases'] = cases
    data['updated_at'] = _now_iso()
    data['record_mode'] = 'runtime'
    save_support_operating_records(data, project_root=project_root, web_storage_dir=web_storage_dir)
    return entry


def append_incident(
    *,
    project_root: str | Path = '.',
    web_storage_dir: str | Path,
    customer_label: str,
    severity: str,
    title: str,
    pilot_id: str = '',
    linked_surface: str = '',
    support_bundle_ref: str = '',
    diagnostics_ref: str = '',
    release_note_id: str = '',
    known_issue_id: str = '',
    escalation_status: str = '',
    version_linkage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = load_support_operating_records(project_root=project_root, web_storage_dir=web_storage_dir)
    incidents = list(payload.get('incidents') or [])
    entry = {
        'incident_id': _next_id('INC', incidents),
        'status': 'open',
        'severity': str(severity or '').strip(),
        'title': str(title or '').strip(),
        'opened_at': _now_iso(),
        'customer_label': str(customer_label or '').strip(),
        'pilot_id': str(pilot_id or '').strip(),
        'linked_surface': str(linked_surface or '').strip(),
        'support_bundle_ref': str(support_bundle_ref or '').strip(),
        'diagnostics_ref': str(diagnostics_ref or '').strip(),
        'release_note_id': str(release_note_id or '').strip(),
        'known_issue_id': str(known_issue_id or '').strip(),
        'escalation_status': str(escalation_status or '').strip(),
        'version_linkage': {str(k): str(v) for k, v in dict(version_linkage or {}).items() if str(v).strip()},
    }
    incidents.append(entry)
    data = dict(payload)
    data['incidents'] = incidents
    data['updated_at'] = _now_iso()
    data['record_mode'] = 'runtime'
    save_support_operating_records(data, project_root=project_root, web_storage_dir=web_storage_dir)
    return entry


def _latest_report_path(artifacts_root: Path, pattern: str) -> Path | None:
    matches = sorted(artifacts_root.rglob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return matches[0] if matches else None


def _support_bundles_summary(artifacts_root: Path) -> dict[str, Any]:
    bundle_dir = artifacts_root / 'support_bundles'
    files = sorted(bundle_dir.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True) if bundle_dir.exists() else []
    latest = files[0] if files else None
    return {
        'count': len(files),
        'latest_bundle': latest.name if latest else None,
        'latest_bundle_path': str(latest) if latest else None,
    }


def _diagnostics_summary(artifacts_root: Path, cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    mapping = {
        'performance_gates_report.json': 'performance_gates',
        'operational_rollout_gates_report.json': 'operational_rollout_gates',
        'competitive_acceptance_report.json': 'competitive_acceptance',
        'restore_drill_report.json': 'restore_diagnostics',
        'pilot_framework_report.json': 'pilot_framework',
    }
    rows: list[dict[str, Any]] = []
    for filename in list((cfg.get('diagnostics') or {}).get('expected_reports') or []):
        latest = _latest_report_path(artifacts_root, filename)
        rows.append({
            'report_file': filename,
            'diagnostics_ref': mapping.get(filename, filename.replace('.json', '')),
            'available': bool(latest),
            'path': str(latest) if latest else None,
        })
    return rows


def build_support_sla_incident_summary(
    *,
    project_root: str | Path = '.',
    artifacts_dir: str | Path | None = None,
    web_storage_dir: str | Path | None = None,
    cfg_path: str | Path = DEFAULT_SUPPORT_SLA_CFG,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    artifacts_root = Path(artifacts_dir).resolve() if artifacts_dir is not None else root / 'artifacts'
    cfg = load_support_sla_incident_policy(root / Path(cfg_path))
    payload = load_support_operating_records(project_root=root, web_storage_dir=web_storage_dir, cfg_path=cfg_path)

    model = dict(cfg.get('support_model') or {})
    severity_levels = {str(k): dict(v or {}) for k, v in dict(model.get('severity_levels') or {}).items()}
    escalation_paths = {str(k): _norm_list(v) for k, v in dict(model.get('escalation_paths') or {}).items()}
    release_notes = [dict(x) for x in list(payload.get('release_notes') or []) if isinstance(x, Mapping)]
    note_index = {str(x.get('release_note_id') or ''): dict(x) for x in release_notes}
    known_issues = [dict(x) for x in list(payload.get('known_issues') or []) if isinstance(x, Mapping)]
    issue_index = {str(x.get('issue_id') or ''): dict(x) for x in known_issues}
    support_cases = [dict(x) for x in list(payload.get('support_cases') or []) if isinstance(x, Mapping)]
    incidents = [dict(x) for x in list(payload.get('incidents') or []) if isinstance(x, Mapping)]

    def enrich(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        sev = str(out.get('severity') or '')
        sev_meta = severity_levels.get(sev, {})
        note = note_index.get(str(out.get('release_note_id') or ''))
        issue = issue_index.get(str(out.get('known_issue_id') or ''))
        out['severity_label'] = str(sev_meta.get('label') or sev)
        out['response_target_minutes'] = sev_meta.get('response_target_minutes')
        out['escalation_path'] = escalation_paths.get(sev, [])
        out['release_note_title'] = str((note or {}).get('title') or '')
        out['known_issue_title'] = str((issue or {}).get('title') or '')
        out['traceability_ok'] = bool(str(out.get('diagnostics_ref') or '').strip() and str(out.get('support_bundle_ref') or '').strip())
        return out

    support_cases = [enrich(x) for x in support_cases]
    incidents = [enrich(x) for x in incidents]
    known_issues = [
        {
            **dict(x),
            'release_note_title': str((note_index.get(str(x.get('linked_release_note_id') or '')) or {}).get('title') or ''),
        }
        for x in known_issues
    ]

    bundles = _support_bundles_summary(artifacts_root)
    diagnostics = _diagnostics_summary(artifacts_root, cfg)
    critical_incidents = [x for x in incidents if str(x.get('severity') or '').upper() == 'SEV1' and str(x.get('status') or '').lower() != 'closed']
    open_support = [x for x in support_cases if str(x.get('status') or '').lower() != 'closed']
    open_incidents = [x for x in incidents if str(x.get('status') or '').lower() not in {'closed', 'mitigated', 'resolved'}]

    summary = {
        'schema': 'genomeai.support_sla_incident_summary.v1',
        'config_version': int(cfg.get('version') or 1),
        'title': str(model.get('title') or 'Support / SLA / incident model'),
        'record_mode': str(payload.get('record_mode') or payload.get('_record_source_mode') or 'unknown'),
        'synthetic_note': str(payload.get('synthetic_note') or '').strip(),
        'source_paths': {
            'config': str(Path(cfg_path)),
            'records': str((cfg.get('records') or {}).get('path') or ''),
            'runtime_records': str(_runtime_records_path(project_root=root, web_storage_dir=web_storage_dir, cfg=cfg) or ''),
        },
        'severity_levels': severity_levels,
        'escalation_paths': escalation_paths,
        'constraints': _norm_list(model.get('constraints')),
        'support_bundles': bundles,
        'diagnostics_reports': diagnostics,
        'release_notes': release_notes,
        'known_issues': known_issues,
        'support_cases': support_cases,
        'incidents': incidents,
        'summary': {
            'open_support_cases': len(open_support),
            'open_incidents': len(open_incidents),
            'critical_open_incidents': len(critical_incidents),
            'known_issues_open': sum(1 for x in known_issues if str(x.get('status') or '').lower() not in {'closed', 'fixed'}),
            'release_notes_total': len(release_notes),
            'support_bundle_count': int(bundles.get('count') or 0),
            'diagnostics_available': sum(1 for row in diagnostics if row.get('available')),
            'traceable_critical_incidents': sum(1 for x in critical_incidents if x.get('traceability_ok')),
        },
        'traceability_statement': 'All critical incidents must keep a traceable record with diagnostics, support bundle usage and version context.',
    }
    return summary


def _render_table_md(title: str, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return f'## {title}\n\n_No rows._\n'
    header = '| ' + ' | '.join(columns) + ' |'
    sep = '| ' + ' | '.join(['---'] * len(columns)) + ' |'
    body = []
    for row in rows:
        body.append('| ' + ' | '.join(str(row.get(col, '')) for col in columns) + ' |')
    return f'## {title}\n\n' + '\n'.join([header, sep, *body]) + '\n'


def render_support_sla_incident_markdown(payload: Mapping[str, Any]) -> str:
    summary = dict(payload.get('summary') or {})
    lines = [
        '# Support / SLA / incident model',
        '',
        f"- record_mode: `{payload.get('record_mode')}`",
        f"- open_support_cases: `{summary.get('open_support_cases')}`",
        f"- open_incidents: `{summary.get('open_incidents')}`",
        f"- critical_open_incidents: `{summary.get('critical_open_incidents')}`",
        f"- support_bundle_count: `{summary.get('support_bundle_count')}`",
        '',
        '## Constraints',
        '',
    ]
    lines.extend([f'- {x}' for x in list(payload.get('constraints') or [])] or ['- none'])
    lines.extend(['', _render_table_md('Support cases', list(payload.get('support_cases') or []), ['case_id', 'severity_label', 'status', 'customer_label', 'release_note_title'])])
    lines.extend(['', _render_table_md('Incidents', list(payload.get('incidents') or []), ['incident_id', 'severity_label', 'status', 'customer_label', 'release_note_title'])])
    lines.extend(['', _render_table_md('Known issues', list(payload.get('known_issues') or []), ['issue_id', 'severity', 'status', 'title', 'release_note_title'])])
    return '\n'.join(lines).strip() + '\n'


def render_support_sla_incident_cli_lines(payload: Mapping[str, Any]) -> list[str]:
    summary = dict(payload.get('summary') or {})
    return [
        f"SUPPORT_SLA open_support_cases={summary.get('open_support_cases')} open_incidents={summary.get('open_incidents')} critical_open_incidents={summary.get('critical_open_incidents')}",
        f"SUPPORT_SLA support_bundles={summary.get('support_bundle_count')} diagnostics_available={summary.get('diagnostics_available')}",
    ]


__all__ = [
    'DEFAULT_SUPPORT_SLA_CFG',
    'append_incident',
    'append_support_case',
    'build_support_sla_incident_summary',
    'load_support_operating_records',
    'load_support_sla_incident_policy',
    'render_support_sla_incident_cli_lines',
    'render_support_sla_incident_markdown',
    'save_support_operating_records',
]
