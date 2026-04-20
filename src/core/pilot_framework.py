from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

DEFAULT_PILOT_FRAMEWORK_CFG = Path('configs/ops/pilot_framework_v1.yaml')


@dataclass(frozen=True)
class PilotSupportCase:
    case_id: str
    status: str
    severity: str
    title: str
    opened_at: str
    linked_versions: dict[str, str]


@dataclass(frozen=True)
class PilotIncident:
    incident_id: str
    status: str
    severity: str
    title: str
    opened_at: str
    linked_surface: str
    diagnostics_ref: str


@dataclass(frozen=True)
class PilotSuccessCriterion:
    criterion_key: str
    status: str
    target: str
    current: str


@dataclass(frozen=True)
class PilotRecord:
    pilot_id: str
    customer_label: str
    status: str
    edition: str
    duration_weeks: int
    scope: dict[str, Any]
    expected_outcomes: tuple[str, ...]
    success_criteria: tuple[PilotSuccessCriterion, ...]
    roles: dict[str, tuple[str, ...]]
    versions: dict[str, str]
    support_cases: tuple[PilotSupportCase, ...]
    incidents: tuple[PilotIncident, ...]
    manual_evidence: tuple[dict[str, Any], ...]
    reference_deployment: dict[str, Any]
    assumptions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()]


def load_pilot_framework_config(path: str | Path = DEFAULT_PILOT_FRAMEWORK_CFG) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'Pilot framework config not found: {p}')
    cfg = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    if not isinstance(cfg, Mapping):
        raise ValueError('Pilot framework config must be a mapping')
    framework = dict(cfg.get('framework') or {})
    if not framework:
        raise ValueError('Pilot framework config must contain framework section')
    statuses = dict(framework.get('statuses') or {})
    if not statuses:
        raise ValueError('Pilot framework statuses are required')
    target_range = list(framework.get('target_pilot_range') or [])
    if len(target_range) != 2:
        raise ValueError('Pilot framework target_pilot_range must contain 2 integers')
    records = dict(cfg.get('records') or {})
    if not str(records.get('path') or '').strip():
        raise ValueError('Pilot framework records.path is required')
    return dict(cfg)


def load_pilot_records(dataset_path: str | Path) -> dict[str, Any]:
    p = Path(dataset_path)
    if not p.exists():
        raise FileNotFoundError(f'Pilot records file not found: {p}')
    payload = json.loads(p.read_text(encoding='utf-8'))
    if str(payload.get('schema') or '') != 'genomeai.pilot_framework_records.v1':
        raise ValueError('Pilot records schema mismatch')
    if not isinstance(payload.get('pilots'), list):
        raise ValueError('Pilot records must contain pilots list')
    return payload


def _build_record(raw: Mapping[str, Any]) -> PilotRecord:
    support_cases = tuple(
        PilotSupportCase(
            case_id=str(item.get('case_id') or '').strip(),
            status=str(item.get('status') or '').strip(),
            severity=str(item.get('severity') or '').strip(),
            title=str(item.get('title') or '').strip(),
            opened_at=str(item.get('opened_at') or '').strip(),
            linked_versions={str(k): str(v) for k, v in dict(item.get('linked_versions') or {}).items() if str(v).strip()},
        )
        for item in list(raw.get('support_cases') or []) if isinstance(item, Mapping)
    )
    incidents = tuple(
        PilotIncident(
            incident_id=str(item.get('incident_id') or '').strip(),
            status=str(item.get('status') or '').strip(),
            severity=str(item.get('severity') or '').strip(),
            title=str(item.get('title') or '').strip(),
            opened_at=str(item.get('opened_at') or '').strip(),
            linked_surface=str(item.get('linked_surface') or '').strip(),
            diagnostics_ref=str(item.get('diagnostics_ref') or '').strip(),
        )
        for item in list(raw.get('incidents') or []) if isinstance(item, Mapping)
    )
    criteria = tuple(
        PilotSuccessCriterion(
            criterion_key=str(item.get('criterion_key') or '').strip(),
            status=str(item.get('status') or '').strip(),
            target=str(item.get('target') or '').strip(),
            current=str(item.get('current') or '').strip(),
        )
        for item in list(raw.get('success_criteria') or []) if isinstance(item, Mapping)
    )
    roles = {
        'customer': tuple(_norm_list((raw.get('roles') or {}).get('customer'))),
        'genomeai': tuple(_norm_list((raw.get('roles') or {}).get('genomeai'))),
    }
    record = PilotRecord(
        pilot_id=str(raw.get('pilot_id') or '').strip(),
        customer_label=str(raw.get('customer_label') or '').strip(),
        status=str(raw.get('status') or '').strip(),
        edition=str(raw.get('edition') or '').strip(),
        duration_weeks=int(raw.get('duration_weeks') or 0),
        scope=dict(raw.get('scope') or {}),
        expected_outcomes=tuple(_norm_list(raw.get('expected_outcomes'))),
        success_criteria=criteria,
        roles=roles,
        versions={str(k): str(v) for k, v in dict(raw.get('versions') or {}).items() if str(v).strip()},
        support_cases=support_cases,
        incidents=incidents,
        manual_evidence=tuple(dict(x) for x in list(raw.get('manual_evidence') or []) if isinstance(x, Mapping)),
        reference_deployment=dict(raw.get('reference_deployment') or {}),
        assumptions=tuple(_norm_list(raw.get('assumptions'))),
    )
    if not record.pilot_id or not record.customer_label:
        raise ValueError('Pilot record pilot_id and customer_label are required')
    return record


def build_pilot_framework_summary(*, project_root: str | Path = '.', cfg_path: str | Path = DEFAULT_PILOT_FRAMEWORK_CFG) -> dict[str, Any]:
    root = Path(project_root)
    cfg = load_pilot_framework_config(root / Path(cfg_path))
    framework = dict(cfg.get('framework') or {})
    records_cfg = dict(cfg.get('records') or {})
    dataset_path = root / str(records_cfg.get('path'))
    payload = load_pilot_records(dataset_path)
    statuses = dict(framework.get('statuses') or {})
    records = [_build_record(item) for item in list(payload.get('pilots') or []) if isinstance(item, Mapping)]

    for rec in records:
        if rec.status not in statuses:
            raise ValueError(f'Unknown pilot status: {rec.status}')

    target_min, target_max = [int(x) for x in list(framework.get('target_pilot_range') or [0, 0])]
    status_counts = {key: 0 for key in statuses.keys()}
    open_support = 0
    open_incidents = 0
    referenceable = 0
    version_linkage_ok = 0
    reference_rows: list[dict[str, Any]] = []
    pilot_rows: list[dict[str, Any]] = []

    required_reference_evidence = tuple(_norm_list((framework.get('reference_deployment_rules') or {}).get('required_manual_evidence')))
    for rec in records:
        status_counts[rec.status] = status_counts.get(rec.status, 0) + 1
        open_support += sum(1 for case in rec.support_cases if case.status.lower() != 'closed')
        open_incidents += sum(1 for inc in rec.incidents if inc.status.lower() not in {'closed', 'mitigated', 'resolved'})
        required_versions = {'data_version', 'report_version', 'decision_log'}
        versions_ok = required_versions.issubset(set(rec.versions.keys()))
        if versions_ok:
            version_linkage_ok += 1
        evidence_map = {str(x.get('key') or ''): bool(x.get('present')) for x in rec.manual_evidence}
        missing_ref_evidence = [key for key in required_reference_evidence if not evidence_map.get(key)]
        is_referenceable = bool(rec.reference_deployment.get('referenceable')) and not missing_ref_evidence
        if is_referenceable:
            referenceable += 1
        reference_rows.append({
            'pilot_id': rec.pilot_id,
            'customer_label': rec.customer_label,
            'status': rec.status,
            'edition': rec.edition,
            'reference_candidate': bool(rec.reference_deployment.get('candidate')),
            'referenceable': is_referenceable,
            'blockers': missing_ref_evidence or ([str(rec.reference_deployment.get('reason') or '').strip()] if not is_referenceable else []),
            'support_cases_open': sum(1 for case in rec.support_cases if case.status.lower() != 'closed'),
            'incidents_open': sum(1 for inc in rec.incidents if inc.status.lower() not in {'closed', 'mitigated', 'resolved'}),
            'versions': dict(rec.versions),
        })
        pilot_rows.append({
            'pilot_id': rec.pilot_id,
            'customer_label': rec.customer_label,
            'status': rec.status,
            'status_label': str((statuses.get(rec.status) or {}).get('label') or rec.status),
            'edition': rec.edition,
            'duration_weeks': rec.duration_weeks,
            'farms': int((rec.scope or {}).get('farms') or 0),
            'sites': int((rec.scope or {}).get('sites') or 0),
            'roles': list((rec.scope or {}).get('roles') or []),
            'support_cases_open': sum(1 for case in rec.support_cases if case.status.lower() != 'closed'),
            'incidents_open': sum(1 for inc in rec.incidents if inc.status.lower() not in {'closed', 'mitigated', 'resolved'}),
            'version_linkage_ok': versions_ok,
            'reference_candidate': bool(rec.reference_deployment.get('candidate')),
            'referenceable': is_referenceable,
        })

    summary = {
        'schema': 'genomeai.pilot_framework_summary.v1',
        'config_version': int(cfg.get('version') or 1),
        'framework_title': str(framework.get('title') or 'Pilot framework'),
        'record_mode': str(payload.get('record_mode') or 'unknown'),
        'synthetic_note': str(payload.get('synthetic_note') or '').strip(),
        'target_pilot_range': [target_min, target_max],
        'pilot_count': len(records),
        'pilot_range_ok': target_min <= len(records) <= target_max,
        'status_counts': status_counts,
        'open_support_cases': open_support,
        'open_incidents': open_incidents,
        'referenceable_count': referenceable,
        'version_linkage_ok_count': version_linkage_ok,
        'framework_notes': _norm_list(framework.get('notes')),
        'framework_success_criteria': list(framework.get('success_criteria') or []),
        'role_model': dict(framework.get('role_model') or {}),
        'expected_outcomes': _norm_list(framework.get('expected_outcomes')),
        'reference_rules': dict(framework.get('reference_deployment_rules') or {}),
        'pilot_rows': pilot_rows,
        'reference_deployments': reference_rows,
        'pilots': [rec.as_dict() for rec in records],
        'source_paths': {
            'config': str(Path(cfg_path)),
            'records': str(records_cfg.get('path') or ''),
        },
        'ready_for_reference_claims': referenceable > 0,
        'traceability_statement': 'Every pilot record preserves linkage to versions, support cases and incidents. Referenceability is blocked until explicit evidence is attached.',
    }
    return summary


def render_pilot_framework_markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        '# Pilot framework and reference deployments',
        '',
        str(summary.get('traceability_statement') or ''),
        '',
        f"- pilot_count: `{summary.get('pilot_count')}`",
        f"- target_range: `{summary.get('target_pilot_range')}`",
        f"- pilot_range_ok: `{str(bool(summary.get('pilot_range_ok'))).lower()}`",
        f"- open_support_cases: `{summary.get('open_support_cases')}`",
        f"- open_incidents: `{summary.get('open_incidents')}`",
        f"- referenceable_count: `{summary.get('referenceable_count')}`",
        '',
        '## Framework notes',
    ]
    for item in summary.get('framework_notes') or []:
        lines.append(f'- {item}')
    lines.extend(['', '## Pilot status board'])
    for row in summary.get('pilot_rows') or []:
        lines.extend([
            '',
            f"### {row.get('customer_label')}",
            f"- pilot_id: `{row.get('pilot_id')}`",
            f"- status: `{row.get('status_label')}`",
            f"- duration_weeks: `{row.get('duration_weeks')}`",
            f"- farms/sites: `{row.get('farms')}` / `{row.get('sites')}`",
            f"- support_cases_open: `{row.get('support_cases_open')}`",
            f"- incidents_open: `{row.get('incidents_open')}`",
            f"- version_linkage_ok: `{str(bool(row.get('version_linkage_ok'))).lower()}`",
            f"- referenceable: `{str(bool(row.get('referenceable'))).lower()}`",
        ])
    lines.extend(['', '## Reference deployment records'])
    for row in summary.get('reference_deployments') or []:
        lines.extend([
            '',
            f"### {row.get('customer_label')}",
            f"- candidate: `{str(bool(row.get('reference_candidate'))).lower()}`",
            f"- referenceable: `{str(bool(row.get('referenceable'))).lower()}`",
        ])
        blockers = list(row.get('blockers') or [])
        if blockers:
            lines.append('- blockers:')
            for item in blockers:
                lines.append(f'  - {item}')
    return '\n'.join(lines)


def render_pilot_framework_cli_lines(summary: Mapping[str, Any]) -> list[str]:
    return [
        f"PILOT_FRAMEWORK pilots={summary.get('pilot_count')} target_range={summary.get('target_pilot_range')}",
        f"PILOT_FRAMEWORK open_support_cases={summary.get('open_support_cases')} open_incidents={summary.get('open_incidents')}",
        f"PILOT_FRAMEWORK referenceable_count={summary.get('referenceable_count')} ready_for_reference_claims={summary.get('ready_for_reference_claims')}",
    ]


__all__ = [
    'DEFAULT_PILOT_FRAMEWORK_CFG',
    'PilotRecord',
    'PilotSupportCase',
    'PilotIncident',
    'PilotSuccessCriterion',
    'load_pilot_framework_config',
    'load_pilot_records',
    'build_pilot_framework_summary',
    'render_pilot_framework_markdown',
    'render_pilot_framework_cli_lines',
]
