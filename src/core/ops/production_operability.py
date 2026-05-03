from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.infra.queue_runtime import build_queue_runtime_summary_payload
from core.infra.runtime_auth_storage import auth_storage_diagnostics
from core.infra.runtime_state_storage import runtime_state_storage_diagnostics
from core.infra.runtime_storage import resolve_runtime_storage_settings, runtime_storage_diagnostics
from core.infra.web_db import get_settings
from core.ops.production_lockdown import production_lockdown_report
from core.recovery.adult_maintenance import build_adult_backup_metadata_summary, build_artifact_integrity_summary
from core.release import load_release_metadata, render_release_stamp
from core.support_sla_incident import build_support_sla_incident_summary


@dataclass(frozen=True)
class ProductionOperabilityReport:
    profile: str
    release: dict[str, Any]
    observability: dict[str, Any]
    supportability: dict[str, Any]
    maintainability: dict[str, Any]
    diagnostics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_project_root(root: Path) -> Path:
    candidates = [root, *root.parents[:3]]
    for candidate in candidates:
        if (candidate / 'configs/ops/release_checklist_v1.json').exists():
            return candidate
    return root


def _load_json(root: Path, rel: str) -> dict[str, Any]:
    root = _resolve_project_root(root)
    path = root / rel
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path}: expected JSON object')
    return payload


def metrics_contract(project_root: str | Path | None = None) -> dict[str, Any]:
    root = _resolve_project_root(Path(project_root or get_settings().project_root).resolve())
    payload = _load_json(root, 'configs/ops/metrics_contract_v1.json')
    payload['source'] = 'configs/ops/metrics_contract_v1.json'
    return payload


def build_production_operability_report(*, settings: Any | None = None) -> ProductionOperabilityReport:
    settings = settings or get_settings()
    root = _resolve_project_root(Path(settings.project_root).resolve())
    runtime = runtime_storage_diagnostics(resolve_runtime_storage_settings(project_root=settings.project_root, storage_dir=settings.storage_dir, sqlite_db_path=settings.db_path)).as_dict()
    state = runtime_state_storage_diagnostics().as_dict()
    auth = auth_storage_diagnostics(settings=settings).as_dict()
    queue = build_queue_runtime_summary_payload(queue_names=['default'])
    lockdown = production_lockdown_report(settings=settings).as_dict()
    release_meta = load_release_metadata(project_root=settings.project_root)
    release_steps = _load_json(root, 'configs/ops/release_checklist_v1.json')
    rollback_steps = _load_json(root, 'configs/ops/rollback_checklist_v1.json')
    incident_flow = _load_json(root, 'configs/ops/incident_first_troubleshooting_v1.json')
    metric_contract = metrics_contract(root)
    artifact_integrity = build_artifact_integrity_summary(artifacts_root=settings.artifacts_root)
    backup_metadata = build_adult_backup_metadata_summary(artifacts_root=settings.artifacts_root)
    support_summary = build_support_sla_incident_summary(project_root=root, artifacts_dir=settings.artifacts_root, web_storage_dir=settings.storage_dir)
    release = {
        'version': str(release_meta.get('version') or ''),
        'build_stamp': render_release_stamp(release_meta),
        'release_checklist': release_steps,
        'rollback_checklist': rollback_steps,
        'compatibility_window_rule': release_steps.get('compatibility_window_rule'),
        'evidence_requirements': list(release_steps.get('evidence_requirements') or []),
    }
    observability = {
        'structured_logs_enabled': True,
        'metrics_contract': metric_contract,
        'required_correlation_ids': list(metric_contract.get('required_correlation_ids') or []),
        'required_log_labels': list(metric_contract.get('required_log_labels') or []),
        'runtime_labels': {
            'storage_backend': runtime.get('backend'),
            'queue_backend': queue.get('backend'),
            'auth_backend': auth.get('backend'),
            'auth_mode': 'server_session_rbac_only' if not bool(auth.get('legacy_cookie_fallback_allowed')) else 'compat_legacy_cookie_allowed',
        },
    }
    supportability = {
        'incident_first_troubleshooting': incident_flow,
        'support_bundle_expected_sections': [
            'runtime_storage_summary', 'runtime_state_summary', 'auth_diagnostics', 'queue_runtime_summary', 'backup_metadata', 'artifact_integrity_summary'
        ],
        'support_records': {
            'open_cases': len(list(support_summary.get('support_cases') or [])),
            'open_incidents': len(list(support_summary.get('incidents') or [])),
            'record_source_mode': support_summary.get('_record_source_mode'),
        },
        'backup_metadata': backup_metadata,
        'artifact_integrity': artifact_integrity,
    }
    maintainability = {
        'boundaries': {
            'runtime_storage_backend': runtime.get('backend'),
            'runtime_state_backend': state.get('backend'),
            'queue_backend': queue.get('backend'),
            'auth_backend': auth.get('backend'),
        },
        'configuration_hygiene': {
            'explicit_profile': runtime.get('profile'),
            'lockdown_active': lockdown.get('lockdown_active'),
            'compatibility_flags': lockdown.get('compatibility_flags'),
        },
        'testability_of_production_paths': {
            'release_gate_file': 'ci/pytest_gate.txt',
            'docs_to_code_check_script': 'scripts/check_docs_to_code_consistency.py',
            'operability_check_script': 'scripts/check_production_operability.py',
        },
    }
    diagnostics = {
        'runtime_storage': runtime,
        'runtime_state': state,
        'auth_runtime': auth,
        'queue_runtime': queue,
        'production_lockdown': lockdown,
    }
    return ProductionOperabilityReport(
        profile=str(runtime.get('profile') or 'unknown'),
        release=release,
        observability=observability,
        supportability=supportability,
        maintainability=maintainability,
        diagnostics=diagnostics,
    )


def validate_production_operability(*, settings: Any | None = None) -> ProductionOperabilityReport:
    report = build_production_operability_report(settings=settings)
    contract = report.observability.get('metrics_contract') or {}
    required_ids = set(contract.get('required_correlation_ids') or [])
    if not {'request_id', 'job_id', 'run_id', 'user_id', 'tenant_id'}.issubset(required_ids):
        raise RuntimeError('metrics contract missing required correlation ids')
    expected_sections = set(report.supportability.get('support_bundle_expected_sections') or [])
    if not {'runtime_storage_summary', 'runtime_state_summary', 'auth_diagnostics', 'queue_runtime_summary'}.issubset(expected_sections):
        raise RuntimeError('support bundle expected sections incomplete')
    return report


__all__ = ['ProductionOperabilityReport', 'build_production_operability_report', 'metrics_contract', 'validate_production_operability']
