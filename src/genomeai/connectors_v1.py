from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from .contract_precheck import validate_source_by_contract
from .contracts import load_contracts_dir
from .ingest import ingest_dataset
from .versioning import write_json


CONNECTOR_KINDS = {"file", "api_stub", "onec_stub"}
CONNECTOR_RUN_STATUSES = {"success", "partial", "failed", "noop", "stub"}
CONNECTOR_AUTO_RETRY_STATUSES = {"partial", "failed"}
CONNECTOR_TEMP_FILE_SUFFIXES = (".yaml.tmp", ".yml.tmp")
CONNECTOR_TEMP_FILE_PREFIXES = (".__preview__", "bad_ui_")

_DATASET_TO_CONTRACT = {
    "farms": "dm_farms",
    "animals": "dm_animals",
    "lactations": "dm_lactations",
    "testday": "dm_testday",
    "health_events": "dm_health_events",
    "treatments": "dm_treatments",
}


def dataset_contract_name(dataset_key: str) -> str | None:
    return _DATASET_TO_CONTRACT.get(str(dataset_key or '').strip().lower())


def _coerce_non_negative_int(raw: Any, *, field_name: str) -> int:
    try:
        value = int(raw)
    except Exception as e:
        raise ConnectorConfigError(f"{field_name} must be an integer, got: {raw!r}") from e
    if value < 0:
        raise ConnectorConfigError(f"{field_name} must be >= 0, got: {value}")
    return value


def connector_retry_policy(spec_or_raw: ConnectorSpec | dict[str, Any]) -> dict[str, Any]:
    raw = spec_or_raw.raw if isinstance(spec_or_raw, ConnectorSpec) else (spec_or_raw or {})
    payload = raw.get('retry_policy') or {}
    if payload in ('', None):
        payload = {}
    if not isinstance(payload, dict):
        raise ConnectorConfigError('retry_policy must be a mapping when present')
    enabled = bool(payload.get('auto_retry_failed_datasets', payload.get('enabled', False)))
    max_attempts_default = 1 if enabled else 0
    max_attempts = _coerce_non_negative_int(payload.get('max_attempts', max_attempts_default), field_name='retry_policy.max_attempts')
    backoff_sec = _coerce_non_negative_int(payload.get('backoff_sec', 60), field_name='retry_policy.backoff_sec')
    failed_datasets_only = bool(payload.get('failed_datasets_only', True))
    if not failed_datasets_only:
        raise ConnectorConfigError('retry_policy.failed_datasets_only=false is not supported in T13-02; only failed dataset subset retry is allowed')
    statuses_raw = payload.get('retry_on_statuses') or ['partial']
    if isinstance(statuses_raw, str):
        statuses_iter = [part.strip() for part in statuses_raw.split(',')]
    elif isinstance(statuses_raw, (list, tuple, set)):
        statuses_iter = [str(part).strip() for part in statuses_raw]
    else:
        raise ConnectorConfigError('retry_policy.retry_on_statuses must be a string or list')
    statuses = sorted({str(part).strip().lower() for part in statuses_iter if str(part).strip()})
    if not statuses:
        statuses = ['partial']
    unsupported = sorted(set(statuses) - CONNECTOR_AUTO_RETRY_STATUSES)
    if unsupported:
        raise ConnectorConfigError(
            f"retry_policy.retry_on_statuses contains unsupported values: {unsupported}; "
            f"expected subset of {sorted(CONNECTOR_AUTO_RETRY_STATUSES)}"
        )
    return {
        'enabled': bool(enabled and max_attempts > 0),
        'configured_enabled': enabled,
        'max_attempts': max_attempts,
        'backoff_sec': backoff_sec,
        'failed_datasets_only': failed_datasets_only,
        'retry_on_statuses': statuses,
    }


def failed_dataset_keys_from_results(dataset_results: Iterable[dict[str, Any]] | None) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in dataset_results or []:
        dataset_key = str((row or {}).get('dataset_key') or '').strip().lower()
        status = str((row or {}).get('status') or '').strip().lower()
        if dataset_key and status == 'failed' and dataset_key not in seen:
            keys.append(dataset_key)
            seen.add(dataset_key)
    return sorted(keys)


def connector_artifacts_root(project_root: Path) -> Path:
    explicit = os.environ.get('GENOMEAI_ARTIFACTS_ROOT')
    if explicit:
        return Path(explicit).resolve()
    return (project_root / 'artifacts').resolve()


def planned_output_targets(*, dataset_key: str, out_version: str, artifacts_root: Path) -> dict[str, Any]:
    contract_name = dataset_contract_name(dataset_key)
    if not contract_name:
        raise ConnectorConfigError(f"Unsupported dataset_key for planned_output_targets: {dataset_key}")
    base = artifacts_root.resolve() / str(out_version).strip()
    return {
        'dataset_key': str(dataset_key).strip().lower(),
        'contract_name': contract_name,
        'out_version': str(out_version).strip(),
        'canonical_csv': str((base / 'canonical' / f'{contract_name}.csv').resolve()),
        'canonical_parquet': str((base / 'canonical' / f'{contract_name}.parquet').resolve()),
        'ingest_summary_json': str((base / 'metadata' / f'ingest_{contract_name}.json').resolve()),
        'ingest_manifest_json': str((base / 'metadata' / 'ingest_manifest.json').resolve()),
        'error_log_jsonl': str((base / 'ingest_logs' / f'{contract_name}_errors.jsonl').resolve()),
    }


@dataclass(frozen=True)
class DatasetBinding:
    dataset_key: str
    pattern: str | None
    path: str | None
    mapping: str
    required: bool = True


@dataclass(frozen=True)
class ConnectorSpec:
    connector_id: str
    kind: str
    enabled: bool
    schedule: str | None
    source_dir: str | None
    description: str | None
    data_version_template: str | None
    bindings: tuple[DatasetBinding, ...]
    config_path: Path
    raw: dict[str, Any]


class ConnectorConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SelectedFile:
    dataset_key: str
    file_path: Path
    mapping_path: Path
    sha256: str
    modified_at: str


@dataclass(frozen=True)
class ConnectorRunResult:
    ok: bool
    status: str
    connector_id: str
    kind: str
    connector_run_id: str
    trigger_type: str
    data_version: str | None
    message: str
    outputs: dict[str, Any]
    selected_files: list[dict[str, Any]]
    ingest_summaries: list[dict[str, Any]]
    dataset_results: list[dict[str, Any]]



def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()



def new_connector_run_id() -> str:
    return f"connrun_{uuid.uuid4().hex[:12]}"



def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()



def _read_yaml(path: Path) -> dict[str, Any]:
    obj = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(obj, dict):
        raise ConnectorConfigError(f"Connector config must be a mapping: {path}")
    return obj



def load_connector_spec(path: Path, *, project_root: Path | None = None) -> ConnectorSpec:
    path = path.resolve()
    project_root = (project_root or path.parents[2] if len(path.parents) >= 2 else path.parent).resolve()
    raw = _read_yaml(path)

    connector_id = str(raw.get("connector_id") or raw.get("id") or "").strip()
    if not connector_id:
        raise ConnectorConfigError(f"connector_id is required: {path}")

    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in CONNECTOR_KINDS:
        raise ConnectorConfigError(
            f"connector.kind='{kind}' is not supported for {connector_id}; expected one of {sorted(CONNECTOR_KINDS)}"
        )

    datasets = raw.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ConnectorConfigError(f"datasets[] is required and must be non-empty: {connector_id}")

    bindings: list[DatasetBinding] = []
    for idx, item in enumerate(datasets):
        if not isinstance(item, dict):
            raise ConnectorConfigError(f"datasets[{idx}] must be a mapping in {connector_id}")
        dataset_key = str(item.get("dataset_key") or "").strip().lower()
        if dataset_key not in _DATASET_TO_CONTRACT:
            raise ConnectorConfigError(
                f"datasets[{idx}].dataset_key='{dataset_key}' is unsupported in {connector_id}; "
                f"expected one of {sorted(_DATASET_TO_CONTRACT)}"
            )
        mapping = str(item.get("mapping") or "").strip()
        if not mapping:
            raise ConnectorConfigError(f"datasets[{idx}].mapping is required in {connector_id}")
        pattern = str(item.get("pattern") or "").strip() or None
        raw_path = str(item.get("path") or "").strip() or None
        if not pattern and not raw_path:
            raise ConnectorConfigError(
                f"datasets[{idx}] in {connector_id} must define either pattern or path"
            )
        bindings.append(
            DatasetBinding(
                dataset_key=dataset_key,
                pattern=pattern,
                path=raw_path,
                mapping=mapping,
                required=bool(item.get("required", True)),
            )
        )

    source_dir = str(raw.get("source_dir") or raw.get("folder") or "").strip() or None
    if kind == "file" and not source_dir:
        any_abs_path = any(b.path for b in bindings)
        if not any_abs_path:
            raise ConnectorConfigError(f"source_dir is required for file connector {connector_id}")

    spec = ConnectorSpec(
        connector_id=connector_id,
        kind=kind,
        enabled=bool(raw.get("enabled", True)),
        schedule=str(raw.get("schedule") or "").strip() or None,
        source_dir=source_dir,
        description=str(raw.get("description") or "").strip() or None,
        data_version_template=str(raw.get("data_version_template") or "").strip() or None,
        bindings=tuple(bindings),
        config_path=path,
        raw=raw,
    )
    validate_connector_spec(spec, project_root=project_root)
    return spec



def is_connector_temp_file(path: Path) -> bool:
    name = path.name
    return any(name.endswith(sfx) for sfx in CONNECTOR_TEMP_FILE_SUFFIXES) or any(name.startswith(pref) for pref in CONNECTOR_TEMP_FILE_PREFIXES)



def list_connector_temp_files(configs_dir: Path) -> list[Path]:
    configs_dir = configs_dir.resolve()
    if not configs_dir.exists():
        return []
    files = [p for p in sorted(configs_dir.iterdir()) if p.is_file() and is_connector_temp_file(p)]
    return files



def cleanup_connector_temp_files(configs_dir: Path, *, remove: bool = True) -> list[Path]:
    stale_files = list_connector_temp_files(configs_dir)
    if remove:
        for path in stale_files:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                continue
    return stale_files



def load_connector_specs(configs_dir: Path, *, project_root: Path | None = None) -> list[ConnectorSpec]:
    configs_dir = configs_dir.resolve()
    if not configs_dir.exists():
        return []
    specs: list[ConnectorSpec] = []
    for path in sorted(configs_dir.glob("*.y*ml")):
        specs.append(load_connector_spec(path, project_root=project_root or configs_dir.parents[1]))
    return specs



def validate_connector_spec(spec: ConnectorSpec, *, project_root: Path) -> None:
    project_root = project_root.resolve()
    if spec.kind == "file":
        if spec.source_dir:
            source_dir = _resolve_any_path(spec.source_dir, base=project_root)
            if not source_dir.exists() or not source_dir.is_dir():
                raise ConnectorConfigError(
                    f"source_dir does not exist or is not a directory for {spec.connector_id}: {source_dir}"
                )
        for binding in spec.bindings:
            mapping_path = _resolve_any_path(binding.mapping, base=project_root)
            if not mapping_path.exists():
                raise ConnectorConfigError(
                    f"mapping file not found for connector={spec.connector_id} dataset={binding.dataset_key}: {mapping_path}"
                )
            if binding.path:
                file_path = _resolve_binding_file(spec, binding, project_root=project_root)
                if not file_path.exists():
                    raise ConnectorConfigError(
                        f"source file not found for connector={spec.connector_id} dataset={binding.dataset_key}: {file_path}"
                    )
    if spec.schedule:
        # Raises ConnectorConfigError on invalid expression.
        cron_matches(spec.schedule, datetime.now(timezone.utc))
    connector_retry_policy(spec)



def connector_catalog_rows(configs_dir: Path, *, project_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in load_connector_specs(configs_dir, project_root=project_root):
        rows.append(
            {
                "connector_id": spec.connector_id,
                "kind": spec.kind,
                "enabled": spec.enabled,
                "schedule": spec.schedule,
                "source_dir": spec.source_dir,
                "description": spec.description,
                "config_path": str(spec.config_path),
            }
        )
    return rows



def _resolve_any_path(raw: str, *, base: Path) -> Path:
    p = Path(str(raw or "").strip())
    if not p.is_absolute():
        p = (base / p).resolve()
    else:
        p = p.resolve()
    return p



def _resolve_binding_file(spec: ConnectorSpec, binding: DatasetBinding, *, project_root: Path) -> Path:
    if binding.path:
        return _resolve_any_path(binding.path, base=project_root)
    source_dir = _resolve_any_path(spec.source_dir or "", base=project_root)
    matches = sorted(source_dir.glob(binding.pattern or ""))
    if not matches:
        raise FileNotFoundError(
            f"No files matched pattern='{binding.pattern}' for connector={spec.connector_id} dataset={binding.dataset_key}"
        )
    return max(matches, key=lambda p: (p.stat().st_mtime_ns, p.name))


WILDCARD_CHARS = set('*?[]')


DEFAULT_MAPPING_BY_DATASET = {
    "farms": "configs/mappings/farms_example.yaml",
    "animals": "configs/mappings/animals_example.yaml",
    "lactations": "configs/mappings/lactations_example.yaml",
    "testday": "configs/mappings/testday_example.yaml",
    "health_events": "configs/mappings/health_events_example.yaml",
    "treatments": "configs/mappings/treatments_example.yaml",
}



def get_binding(spec: ConnectorSpec, dataset_key: str) -> DatasetBinding | None:
    dataset_key = str(dataset_key or '').strip().lower()
    for binding in spec.bindings:
        if binding.dataset_key == dataset_key:
            return binding
    return None



def upload_target_filename(binding: DatasetBinding, *, original_name: str) -> str:
    original = Path(str(original_name or 'upload.csv')).name or 'upload.csv'
    if binding.path:
        return Path(binding.path).name
    pattern = str(binding.pattern or '').strip()
    if pattern and not any(ch in pattern for ch in WILDCARD_CHARS):
        return Path(pattern).name
    return original



def resolve_upload_target(spec: ConnectorSpec, binding: DatasetBinding, *, project_root: Path, original_name: str) -> Path:
    if spec.kind != 'file':
        raise ConnectorConfigError(
            f"connector={spec.connector_id} kind={spec.kind} does not support file upload staging"
        )
    target_name = upload_target_filename(binding, original_name=original_name)
    if binding.path:
        target = _resolve_any_path(binding.path, base=project_root)
        return target
    source_dir = _resolve_any_path(spec.source_dir or '', base=project_root)
    target = (source_dir / target_name).resolve()
    source_dir_res = source_dir.resolve()
    if source_dir_res not in target.parents and target != source_dir_res:
        raise ConnectorConfigError(
            f"upload target escapes source_dir for connector={spec.connector_id}: {target}"
        )
    return target



def describe_binding_sources(spec: ConnectorSpec, *, project_root: Path, previous_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    previous_state = previous_state or {}
    prev_datasets = previous_state.get('datasets') or {}
    rows: list[dict[str, Any]] = []
    source_dir = _resolve_any_path(spec.source_dir or '', base=project_root) if spec.source_dir else None
    for binding in spec.bindings:
        row: dict[str, Any] = {
            'dataset_key': binding.dataset_key,
            'required': bool(binding.required),
            'pattern': binding.pattern,
            'path': binding.path,
            'mapping': binding.mapping,
            'source_dir': str(source_dir) if source_dir else None,
            'matched_count': 0,
            'selected_file_path': None,
            'selected_modified_at': None,
            'selected_sha256': None,
            'exists': False,
            'last_pulled_file_path': None,
            'last_pulled_sha256': None,
            'last_pulled_modified_at': None,
            'delta_status': 'unknown',
            'delta_reason': None,
            'error': None,
        }
        prev_item = prev_datasets.get(binding.dataset_key) or {}
        row['last_pulled_file_path'] = prev_item.get('file_path')
        row['last_pulled_sha256'] = prev_item.get('sha256')
        row['last_pulled_modified_at'] = prev_item.get('modified_at')
        try:
            if binding.path:
                p = _resolve_any_path(binding.path, base=project_root)
                row['matched_count'] = 1 if p.exists() else 0
                row['selected_file_path'] = str(p)
                if p.exists():
                    st = p.stat()
                    row['exists'] = True
                    row['selected_modified_at'] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
                    row['selected_sha256'] = _sha256_file(p)
                else:
                    row['error'] = f"Source file does not exist: {p}"
            else:
                if source_dir is None:
                    row['error'] = 'source_dir is not configured'
                elif not source_dir.exists():
                    row['error'] = f"source_dir does not exist: {source_dir}"
                else:
                    matches = sorted(source_dir.glob(binding.pattern or ''))
                    row['matched_count'] = len(matches)
                    if matches:
                        sel = max(matches, key=lambda p: (p.stat().st_mtime_ns, p.name))
                        st = sel.stat()
                        row['exists'] = True
                        row['selected_file_path'] = str(sel)
                        row['selected_modified_at'] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
                        row['selected_sha256'] = _sha256_file(sel)
                    else:
                        row['error'] = f"No files matched pattern='{binding.pattern}'"
        except Exception as e:
            row['error'] = f"{type(e).__name__}: {e}"

        if row['error']:
            row['delta_status'] = 'error'
            row['delta_reason'] = row['error']
        elif not row['exists']:
            row['delta_status'] = 'missing'
            row['delta_reason'] = 'current source is missing'
        elif not row['last_pulled_sha256']:
            row['delta_status'] = 'new'
            row['delta_reason'] = 'binding has not been pulled before'
        elif row['selected_sha256'] != row['last_pulled_sha256']:
            row['delta_status'] = 'changed'
            if row['selected_file_path'] != row['last_pulled_file_path']:
                row['delta_reason'] = 'selected source file changed since last pull'
            else:
                row['delta_reason'] = 'source file content changed since last pull'
        else:
            row['delta_status'] = 'unchanged'
            row['delta_reason'] = 'same file/content as last successful pull'
        rows.append(row)
    return rows


def summarize_binding_deltas(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        'total': 0,
        'new': 0,
        'changed': 0,
        'unchanged': 0,
        'missing': 0,
        'error': 0,
        'ready_now': 0,
    }
    for row in rows or []:
        summary['total'] += 1
        status = str((row or {}).get('delta_status') or '').strip().lower()
        if status in summary:
            summary[status] += 1
        if bool((row or {}).get('exists')):
            summary['ready_now'] += 1
    return summary



def summarize_output_targets(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        'total': 0,
        'first_write': 0,
        'refresh': 0,
        'force_refresh': 0,
        'skip_noop': 0,
        'blocked': 0,
        'previous_missing': 0,
    }
    for row in rows or []:
        summary['total'] += 1
        status = str((row or {}).get('target_status') or '').strip().lower()
        if status in summary:
            summary[status] += 1
    return summary



def describe_expected_outputs(
    spec: ConnectorSpec,
    *,
    selected_files: Iterable[dict[str, Any]] | Iterable[SelectedFile],
    sample_data_version: str | None,
    previous_state: dict[str, Any] | None,
    binding_diffs: Iterable[dict[str, Any]] | None,
    artifacts_root: Path,
    will_write: bool,
    force: bool = False,
) -> list[dict[str, Any]]:
    previous_state = previous_state or {}
    previous_data_version = str(previous_state.get('last_data_version') or '').strip() or None
    diff_by_dataset = {
        str((row or {}).get('dataset_key') or '').strip().lower(): (row or {})
        for row in (binding_diffs or [])
        if str((row or {}).get('dataset_key') or '').strip()
    }
    normalized: list[dict[str, Any]] = []
    for item in selected_files or []:
        if isinstance(item, SelectedFile):
            normalized.append({
                'dataset_key': item.dataset_key,
                'file_path': str(item.file_path),
                'mapping_path': str(item.mapping_path),
                'sha256': item.sha256,
                'modified_at': item.modified_at,
            })
        else:
            normalized.append(dict(item))

    rows: list[dict[str, Any]] = []
    for item in normalized:
        dataset_key = str(item.get('dataset_key') or '').strip().lower()
        if not dataset_key:
            continue
        contract_name = dataset_contract_name(dataset_key)
        if not contract_name:
            continue
        current = planned_output_targets(dataset_key=dataset_key, out_version=str(sample_data_version or 'preview'), artifacts_root=artifacts_root)
        previous_targets = planned_output_targets(dataset_key=dataset_key, out_version=previous_data_version, artifacts_root=artifacts_root) if previous_data_version else None
        delta_row = diff_by_dataset.get(dataset_key) or {}
        delta_status = str(delta_row.get('delta_status') or '').strip().lower()
        if not will_write:
            target_status = 'blocked' if delta_status in {'missing', 'error'} else 'skip_noop'
            if delta_status in {'missing', 'error'}:
                target_reason = str(delta_row.get('delta_reason') or 'binding is not ready for pull')
            else:
                target_reason = 'connector is expected to skip ingest because increment state is noop'
        elif not previous_data_version:
            target_status = 'first_write'
            target_reason = 'first connector pull will create canonical outputs for this dataset'
        elif previous_targets and not Path(previous_targets['canonical_csv']).exists():
            target_status = 'previous_missing'
            target_reason = 'previous canonical output is missing on disk; next pull will recreate it in a new data_version'
        elif force and delta_status == 'unchanged':
            target_status = 'force_refresh'
            target_reason = 'forced run will rewrite canonical outputs even though source is unchanged'
        else:
            target_status = 'refresh'
            target_reason = 'next pull will write a new canonical output for this dataset'
        rows.append({
            'dataset_key': dataset_key,
            'contract_name': contract_name,
            'source_file': str(item.get('file_path') or ''),
            'mapping_path': str(item.get('mapping_path') or ''),
            'current_data_version': sample_data_version,
            'previous_data_version': previous_data_version,
            'previous_canonical_csv': previous_targets['canonical_csv'] if previous_targets else None,
            'previous_error_log_jsonl': previous_targets['error_log_jsonl'] if previous_targets else None,
            'current_canonical_csv': current['canonical_csv'],
            'current_canonical_parquet': current['canonical_parquet'],
            'current_ingest_summary_json': current['ingest_summary_json'],
            'current_ingest_manifest_json': current['ingest_manifest_json'],
            'current_error_log_jsonl': current['error_log_jsonl'],
            'target_status': target_status,
            'target_reason': target_reason,
            'delta_status': delta_status or None,
        })
    return rows



def select_files_for_pull(spec: ConnectorSpec, *, project_root: Path, dataset_keys: Iterable[str] | None = None) -> list[SelectedFile]:
    selected: list[SelectedFile] = []
    allowed = {str(k or '').strip().lower() for k in (dataset_keys or []) if str(k or '').strip()}
    for binding in spec.bindings:
        if allowed and binding.dataset_key not in allowed:
            continue
        try:
            file_path = _resolve_binding_file(spec, binding, project_root=project_root)
        except FileNotFoundError as e:
            if binding.required:
                raise ConnectorConfigError(str(e))
            continue
        mapping_path = _resolve_any_path(binding.mapping, base=project_root)
        stat = file_path.stat()
        selected.append(
            SelectedFile(
                dataset_key=binding.dataset_key,
                file_path=file_path,
                mapping_path=mapping_path,
                sha256=_sha256_file(file_path),
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
            )
        )
    return selected



def _state_root(project_root: Path) -> Path:
    explicit = os.environ.get("GENOMEAI_WEB_STORAGE")
    if explicit:
        return (Path(explicit).resolve() / "connectors_state")
    return (project_root / "artifacts" / "_connectors_state").resolve()



def load_connector_state(*, project_root: Path, connector_id: str) -> dict[str, Any]:
    state_path = _state_root(project_root) / f"{connector_id}.json"
    if not state_path.exists():
        return {"connector_id": connector_id, "datasets": {}, "last_data_version": None, "last_connector_run_id": None}
    try:
        obj = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {"connector_id": connector_id, "datasets": {}, "last_data_version": None, "last_connector_run_id": None}
    if not isinstance(obj, dict):
        return {"connector_id": connector_id, "datasets": {}, "last_data_version": None, "last_connector_run_id": None}
    return obj



def save_connector_state(*, project_root: Path, connector_id: str, state: dict[str, Any]) -> Path:
    root = _state_root(project_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{connector_id}.json"
    write_json(path, state)
    return path



def detect_increment(selected: Iterable[SelectedFile], *, previous_state: dict[str, Any]) -> tuple[bool, str]:
    prev = previous_state.get("datasets") or {}
    changed: list[str] = []
    selected_list = list(selected)
    for item in selected_list:
        state_row = prev.get(item.dataset_key) or {}
        if state_row.get("sha256") != item.sha256:
            changed.append(item.dataset_key)
    if not prev:
        return True, "first_pull"
    if changed:
        return True, f"changed datasets: {', '.join(sorted(changed))}"
    return False, "no new or changed files detected"



def render_data_version(spec: ConnectorSpec, *, now: datetime, connector_run_id: str) -> str:
    template = (spec.data_version_template or "").strip()
    if template:
        return now.strftime(template)
    ts = now.strftime("%Y%m%d_%H%M%S")
    return f"dv_{spec.connector_id}_{ts}_{connector_run_id[-4:]}"



def run_connector_spec(
    spec: ConnectorSpec,
    *,
    project_root: Path,
    artifacts_root: Path,
    connector_run_id: str | None = None,
    trigger_type: str = "manual",
    scheduled_slot: str | None = None,
    force: bool = False,
    dataset_keys: Iterable[str] | None = None,
) -> ConnectorRunResult:
    project_root = project_root.resolve()
    artifacts_root = artifacts_root.resolve()
    connector_run_id = str(connector_run_id or new_connector_run_id()).strip()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    requested_dataset_keys = sorted({str(k or '').strip().lower() for k in (dataset_keys or []) if str(k or '').strip()})

    if not spec.enabled:
        return ConnectorRunResult(
            ok=True,
            status="noop",
            connector_id=spec.connector_id,
            kind=spec.kind,
            connector_run_id=connector_run_id,
            trigger_type=trigger_type,
            data_version=None,
            message="Connector is disabled in config",
            outputs={},
            selected_files=[],
            ingest_summaries=[],
            dataset_results=[],
        )

    if spec.kind in {"api_stub", "onec_stub"}:
        status = "stub"
        kind_label = "API" if spec.kind == "api_stub" else "1C"
        return ConnectorRunResult(
            ok=True,
            status=status,
            connector_id=spec.connector_id,
            kind=spec.kind,
            connector_run_id=connector_run_id,
            trigger_type=trigger_type,
            data_version=None,
            message=f"{kind_label} connector is a stub. Real integration is intentionally not implemented in T13-02.",
            outputs={"scheduled_slot": scheduled_slot, "requested_dataset_keys": requested_dataset_keys},
            selected_files=[],
            ingest_summaries=[],
            dataset_results=[],
        )

    selected = select_files_for_pull(spec, project_root=project_root, dataset_keys=requested_dataset_keys)
    if not selected:
        detail = "No source files were selected for pull"
        if requested_dataset_keys:
            detail = f"No source files were selected for requested datasets: {', '.join(requested_dataset_keys)}"
        return ConnectorRunResult(
            ok=True,
            status="noop",
            connector_id=spec.connector_id,
            kind=spec.kind,
            connector_run_id=connector_run_id,
            trigger_type=trigger_type,
            data_version=None,
            message=detail,
            outputs={"scheduled_slot": scheduled_slot, "requested_dataset_keys": requested_dataset_keys},
            selected_files=[],
            ingest_summaries=[],
            dataset_results=[],
        )

    prev_state = load_connector_state(project_root=project_root, connector_id=spec.connector_id)
    should_pull, increment_reason = detect_increment(selected, previous_state=prev_state)
    selected_payload = [
        {
            "dataset_key": s.dataset_key,
            "file_path": str(s.file_path),
            "mapping_path": str(s.mapping_path),
            "sha256": s.sha256,
            "modified_at": s.modified_at,
        }
        for s in selected
    ]
    if not should_pull and not force:
        return ConnectorRunResult(
            ok=True,
            status="noop",
            connector_id=spec.connector_id,
            kind=spec.kind,
            connector_run_id=connector_run_id,
            trigger_type=trigger_type,
            data_version=str(prev_state.get("last_data_version") or "") or None,
            message=increment_reason,
            outputs={
                "scheduled_slot": scheduled_slot,
                "state_path": str((_state_root(project_root) / f'{spec.connector_id}.json').resolve()),
                "requested_dataset_keys": requested_dataset_keys,
            },
            selected_files=selected_payload,
            ingest_summaries=[],
            dataset_results=[
                {
                    "dataset_key": item["dataset_key"],
                    "status": "not_written_noop",
                    "result_reason": increment_reason,
                    "source_file": item["file_path"],
                    "mapping_path": item["mapping_path"],
                }
                for item in selected_payload
            ],
        )

    contracts = load_contracts_dir((project_root / "configs/contracts").resolve())
    data_version = render_data_version(spec, now=now, connector_run_id=connector_run_id)
    if (artifacts_root / data_version).exists():
        data_version = f"{data_version}_{connector_run_id[-4:]}"
    run_dir = artifacts_root / data_version / "connectors" / connector_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ingest_summaries: list[dict[str, Any]] = []
    dataset_results: list[dict[str, Any]] = []
    successful_selected: list[SelectedFile] = []
    failed_dataset_keys: list[str] = []
    for item in selected:
        contract_name = _DATASET_TO_CONTRACT[item.dataset_key]
        contract = contracts.get(contract_name)
        if contract is None:
            err = f"Contract {contract_name} not found for dataset={item.dataset_key} connector={spec.connector_id}"
            dataset_results.append({
                "dataset_key": item.dataset_key,
                "contract_name": contract_name,
                "status": "failed",
                "result_reason": err,
                "error_type": "ConnectorConfigError",
                "error_text": err,
                "source_file": str(item.file_path),
                "mapping_path": str(item.mapping_path),
            })
            failed_dataset_keys.append(item.dataset_key)
            continue
        try:
            validation = validate_source_by_contract(
                dataset_key=item.dataset_key,
                file_path=item.file_path,
                mapping_path=item.mapping_path,
                contract=contract,
            )
            if not validation.ok:
                validation_path = run_dir / f"contract_validation_{contract_name}.json"
                write_json(validation_path, validation.to_dict(preview_limit=50))
                dataset_results.append({
                    "dataset_key": item.dataset_key,
                    "contract_name": contract_name,
                    "status": "failed",
                    "result_reason": f"contract validation failed: {validation.error_count} issue(s)",
                    "error_type": "ContractValidationError",
                    "error_text": "; ".join(validation.top_messages(limit=3))[:1000],
                    "source_file": str(item.file_path),
                    "mapping_path": str(item.mapping_path),
                    "rows_in": validation.rows_in,
                    "contract_version": validation.contract_version,
                    "validation_errors_json": str(validation_path),
                    "validation_error_count": validation.error_count,
                    "validation_preview": validation.top_messages(limit=10),
                })
                failed_dataset_keys.append(item.dataset_key)
                continue
            summary = ingest_dataset(
                dataset_key=item.dataset_key,
                file_path=item.file_path,
                mapping_path=item.mapping_path,
                contract=contract,
                artifacts_root=artifacts_root,
                out_version=data_version,
            )
            ingest_summaries.append(summary)
            successful_selected.append(item)
            dataset_results.append({
                "dataset_key": item.dataset_key,
                "contract_name": contract_name,
                "status": "written",
                "result_reason": "ingest finished successfully",
                "error_type": None,
                "error_text": None,
                "source_file": str(item.file_path),
                "mapping_path": str(item.mapping_path),
                "rows_in": summary.get("rows_in"),
                "rows_out": summary.get("rows_out"),
                "error_count": summary.get("error_count"),
                "contract_version": summary.get("contract_version"),
                "canonical_csv": summary.get("canonical_csv"),
                "canonical_parquet": summary.get("canonical_parquet"),
            })
        except Exception as e:
            dataset_results.append({
                "dataset_key": item.dataset_key,
                "contract_name": contract_name,
                "status": "failed",
                "result_reason": str(e),
                "error_type": type(e).__name__,
                "error_text": str(e),
                "source_file": str(item.file_path),
                "mapping_path": str(item.mapping_path),
            })
            failed_dataset_keys.append(item.dataset_key)

    manifest = {
        "schema": "genomeai.connector_run.v1",
        "connector_id": spec.connector_id,
        "connector_run_id": connector_run_id,
        "kind": spec.kind,
        "trigger_type": trigger_type,
        "scheduled_slot": scheduled_slot,
        "data_version": data_version,
        "created_at_utc": now.isoformat(),
        "increment_reason": increment_reason,
        "requested_dataset_keys": requested_dataset_keys,
        "selected_files": selected_payload,
        "ingest_summaries": ingest_summaries,
        "dataset_results": dataset_results,
        "failed_dataset_keys": failed_dataset_keys_from_results(dataset_results),
    }
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)

    prev_datasets = dict((prev_state.get("datasets") or {}))
    for s in successful_selected:
        prev_datasets[s.dataset_key] = {
            "file_path": str(s.file_path),
            "mapping_path": str(s.mapping_path),
            "sha256": s.sha256,
            "modified_at": s.modified_at,
        }
    state = {
        "connector_id": spec.connector_id,
        "updated_at": utcnow_iso(),
        "last_data_version": data_version if successful_selected else prev_state.get("last_data_version"),
        "last_connector_run_id": connector_run_id,
        "last_status": "success" if successful_selected and not failed_dataset_keys else ("partial" if successful_selected else "failed"),
        "last_failed_dataset_keys": failed_dataset_keys_from_results(dataset_results),
        "datasets": prev_datasets,
    }
    state_path = save_connector_state(project_root=project_root, connector_id=spec.connector_id, state=state)

    failed_dataset_keys = failed_dataset_keys_from_results(dataset_results)

    if successful_selected and failed_dataset_keys:
        status = "partial"
        ok = True
        message = (
            "Connector pull finished with partial failures; written datasets="
            f"{', '.join(sorted(s.dataset_key for s in successful_selected))}; failed datasets={', '.join(sorted(failed_dataset_keys))}."
        )
    elif successful_selected:
        status = "success"
        ok = True
        message = f"Connector pull finished successfully; increment={increment_reason}"
    else:
        status = "failed"
        ok = False
        message = f"Connector pull failed for all selected datasets: {', '.join(sorted(failed_dataset_keys))}"

    return ConnectorRunResult(
        ok=ok,
        status=status,
        connector_id=spec.connector_id,
        kind=spec.kind,
        connector_run_id=connector_run_id,
        trigger_type=trigger_type,
        data_version=data_version,
        message=message,
        outputs={
            "manifest_json": str(manifest_path),
            "state_json": str(state_path),
            "scheduled_slot": scheduled_slot,
            "requested_dataset_keys": requested_dataset_keys,
            "failed_dataset_keys": failed_dataset_keys,
            "retry_policy": connector_retry_policy(spec),
        },
        selected_files=selected_payload,
        ingest_summaries=ingest_summaries,
        dataset_results=dataset_results,
    )


def run_connector_config(
    config_path: Path,
    *,
    project_root: Path,
    artifacts_root: Path,
    connector_run_id: str | None = None,
    trigger_type: str = "manual",
    scheduled_slot: str | None = None,
    force: bool = False,
    dataset_keys: Iterable[str] | None = None,
) -> ConnectorRunResult:
    spec = load_connector_spec(config_path, project_root=project_root)
    return run_connector_spec(
        spec,
        project_root=project_root,
        artifacts_root=artifacts_root,
        connector_run_id=connector_run_id,
        trigger_type=trigger_type,
        scheduled_slot=scheduled_slot,
        force=force,
        dataset_keys=dataset_keys,
    )

def preview_connector_spec(
    spec: ConnectorSpec,
    *,
    project_root: Path,
    artifacts_root: Path | None = None,
    now: datetime | None = None,
    connector_run_id: str | None = None,
    trigger_type: str = "manual_preview",
    scheduled_slot: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    artifacts_root = (artifacts_root or connector_artifacts_root(project_root)).resolve()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    connector_run_id = str(connector_run_id or new_connector_run_id()).strip()
    base = {
        "ok": True,
        "connector_id": spec.connector_id,
        "kind": spec.kind,
        "connector_run_id": connector_run_id,
        "trigger_type": trigger_type,
        "scheduled_slot": scheduled_slot,
        "forced": bool(force),
        "sample_data_version": None,
        "predicted_status": "noop",
        "message": "",
        "increment_reason": None,
        "selected_files": [],
        "ingest_targets": [],
        "binding_diffs": [],
        "diff_summary": {"total": 0, "new": 0, "changed": 0, "unchanged": 0, "missing": 0, "error": 0, "ready_now": 0},
        "expected_outputs": [],
        "output_summary": {"total": 0, "first_write": 0, "refresh": 0, "force_refresh": 0, "skip_noop": 0, "blocked": 0, "previous_missing": 0},
        "next_due_slots": next_due_slots(spec.schedule, start=now, limit=3) if spec.schedule else [],
        "state": load_connector_state(project_root=project_root, connector_id=spec.connector_id),
        "retry_policy": connector_retry_policy(spec),
    }
    if not spec.enabled:
        base["predicted_status"] = "noop"
        base["message"] = "Connector is disabled in config"
        return base
    if spec.kind in {"api_stub", "onec_stub"}:
        kind_label = "API" if spec.kind == "api_stub" else "1C"
        base["predicted_status"] = "stub"
        base["message"] = f"{kind_label} connector is a stub. Real integration is intentionally not implemented in T13-02."
        return base

    binding_diffs = describe_binding_sources(spec, project_root=project_root, previous_state=base["state"])
    base["binding_diffs"] = binding_diffs
    base["diff_summary"] = summarize_binding_deltas(binding_diffs)

    selected = select_files_for_pull(spec, project_root=project_root)
    base["selected_files"] = [
        {
            "dataset_key": s.dataset_key,
            "file_path": str(s.file_path),
            "mapping_path": str(s.mapping_path),
            "sha256": s.sha256,
            "modified_at": s.modified_at,
        }
        for s in selected
    ]
    base["ingest_targets"] = [
        {
            "dataset_key": s.dataset_key,
            "contract_name": _DATASET_TO_CONTRACT[s.dataset_key],
            "mapping_path": str(s.mapping_path),
            "source_file": str(s.file_path),
        }
        for s in selected
    ]
    if not selected:
        base["predicted_status"] = "noop"
        base["message"] = "No source files were selected for pull"
        return base

    prev_state = base["state"] or {}
    should_pull, increment_reason = detect_increment(selected, previous_state=prev_state)
    base["increment_reason"] = increment_reason
    sample_data_version = render_data_version(spec, now=now, connector_run_id=connector_run_id)
    base["sample_data_version"] = sample_data_version
    if not should_pull and not force:
        base["predicted_status"] = "noop"
        base["message"] = increment_reason
        base["sample_data_version"] = str(prev_state.get("last_data_version") or sample_data_version)
        base["expected_outputs"] = describe_expected_outputs(
            spec,
            selected_files=selected,
            sample_data_version=str(prev_state.get("last_data_version") or sample_data_version),
            previous_state=prev_state,
            binding_diffs=binding_diffs,
            artifacts_root=artifacts_root,
            will_write=False,
            force=force,
        )
        base["output_summary"] = summarize_output_targets(base["expected_outputs"])
        return base

    base["predicted_status"] = "success"
    base["expected_outputs"] = describe_expected_outputs(
        spec,
        selected_files=selected,
        sample_data_version=sample_data_version,
        previous_state=prev_state,
        binding_diffs=binding_diffs,
        artifacts_root=artifacts_root,
        will_write=True,
        force=force,
    )
    base["output_summary"] = summarize_output_targets(base["expected_outputs"])
    if force and not should_pull:
        base["message"] = f"Forced pull preview: connector would run despite noop increment state ({increment_reason})."
    else:
        base["message"] = f"Connector preview is valid; pull would run with increment={increment_reason}."
    return base


def preview_connector_config(
    config_path: Path,
    *,
    project_root: Path,
    artifacts_root: Path | None = None,
    now: datetime | None = None,
    connector_run_id: str | None = None,
    trigger_type: str = "manual_preview",
    scheduled_slot: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    spec = load_connector_spec(config_path, project_root=project_root)
    return preview_connector_spec(
        spec,
        project_root=project_root,
        artifacts_root=artifacts_root,
        now=now,
        connector_run_id=connector_run_id,
        trigger_type=trigger_type,
        scheduled_slot=scheduled_slot,
        force=force,
    )


def next_due_slots(expr: str | None, *, start: datetime, limit: int = 3, max_search_days: int = 35) -> list[str]:
    expr = str(expr or "").strip()
    if not expr:
        return []
    current = start.astimezone(timezone.utc).replace(second=0, microsecond=0)
    seen: set[str] = set()
    slots: list[str] = []
    for _ in range(max(1, max_search_days * 24 * 60)):
        current = current + timedelta(minutes=1)
        if cron_matches(expr, current):
            slot = schedule_slot_for(current)
            if slot not in seen:
                slots.append(slot)
                seen.add(slot)
                if len(slots) >= max(1, int(limit or 1)):
                    break
    return slots


def connector_health_snapshot(
    spec: ConnectorSpec,
    *,
    project_root: Path,
    now: datetime | None = None,
    previous_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    validation_error: str | None = None
    try:
        validate_connector_spec(spec, project_root=project_root)
    except Exception as e:
        validation_error = f"{type(e).__name__}: {e}"

    binding_rows: list[dict[str, Any]] = []
    required_total = sum(1 for b in spec.bindings if b.required)
    ready_required = 0
    missing_required: list[str] = []
    if spec.kind == "file":
        binding_rows = describe_binding_sources(spec, project_root=project_root, previous_state=previous_state)
        for row in binding_rows:
            if row.get("required"):
                if row.get("exists"):
                    ready_required += 1
                else:
                    missing_required.append(str(row.get("dataset_key") or ""))
    else:
        ready_required = required_total

    next_slots: list[str] = []
    next_due = None
    if spec.enabled and spec.schedule:
        try:
            next_slots = next_due_slots(spec.schedule, start=now, limit=3)
            next_due = next_slots[0] if next_slots else None
        except Exception as e:
            if validation_error is None:
                validation_error = f"{type(e).__name__}: {e}"

    delta_summary = summarize_binding_deltas(binding_rows)
    pending_bindings = [
        str(r.get("dataset_key") or "")
        for r in binding_rows
        if str(r.get("delta_status") or "") in {"new", "changed"}
    ]

    if not spec.enabled:
        status = "disabled"
        status_reason = "connector_disabled"
    elif validation_error:
        status = "failed"
        status_reason = validation_error
    elif spec.kind != "file":
        status = "stub" if spec.kind in {"api_stub", "onec_stub"} else "ready"
        status_reason = "stub_connector" if status == "stub" else "config_valid"
    elif missing_required:
        status = "warning"
        status_reason = f"missing required bindings: {', '.join(sorted(missing_required))}"
    else:
        status = "ready"
        if pending_bindings:
            status_reason = f"all required bindings resolved; pending increment on: {', '.join(sorted(pending_bindings))}"
        else:
            status_reason = "all required bindings resolved"

    return {
        "status": status,
        "status_reason": status_reason,
        "validation_error": validation_error,
        "required_total": required_total,
        "required_ready": ready_required,
        "missing_required": missing_required,
        "delta_summary": delta_summary,
        "pending_bindings": pending_bindings,
        "next_due": next_due,
        "next_due_slots": next_slots,
        "binding_rows": binding_rows,
    }

def spec_to_form_dict(spec: ConnectorSpec) -> dict[str, Any]:
    retry_policy = connector_retry_policy(spec)
    return {
        "connector_id": spec.connector_id,
        "kind": spec.kind,
        "enabled": bool(spec.enabled),
        "description": spec.description or "",
        "source_dir": spec.source_dir or "",
        "schedule": spec.schedule or "",
        "data_version_template": spec.data_version_template or "",
        "retry_policy_enabled": bool(retry_policy.get('configured_enabled')),
        "retry_policy_max_attempts": int(retry_policy.get('max_attempts') or 0),
        "retry_policy_backoff_sec": int(retry_policy.get('backoff_sec') or 0),
        "retry_policy_status_partial": 'partial' in set(retry_policy.get('retry_on_statuses') or []),
        "retry_policy_status_failed": 'failed' in set(retry_policy.get('retry_on_statuses') or []),
        "datasets": [
            {
                "dataset_key": b.dataset_key,
                "pattern": b.pattern or "",
                "path": b.path or "",
                "mapping": b.mapping,
                "required": bool(b.required),
            }
            for b in spec.bindings
        ],
    }


def default_form_bindings(*, blank_rows: int = 2) -> list[dict[str, Any]]:
    rows = [
        {
            "dataset_key": dataset_key,
            "pattern": f"{dataset_key}.csv",
            "path": "",
            "mapping": mapping,
            "required": dataset_key in {"animals", "lactations"},
        }
        for dataset_key, mapping in DEFAULT_MAPPING_BY_DATASET.items()
    ]
    for _ in range(max(0, int(blank_rows or 0))):
        rows.append({"dataset_key": "", "pattern": "", "path": "", "mapping": "", "required": False})
    return rows


def normalize_form_bindings(bindings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    norm: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, item in enumerate(bindings):
        dataset_key = str((item or {}).get("dataset_key") or "").strip().lower()
        pattern = str((item or {}).get("pattern") or "").strip()
        path = str((item or {}).get("path") or "").strip()
        mapping = str((item or {}).get("mapping") or "").strip()
        required = bool((item or {}).get("required", True))
        touched = any([dataset_key, pattern, path, mapping])
        if not touched:
            continue
        if not dataset_key:
            raise ConnectorConfigError(f"datasets[{idx}].dataset_key is required")
        if dataset_key not in _DATASET_TO_CONTRACT:
            raise ConnectorConfigError(
                f"datasets[{idx}].dataset_key='{dataset_key}' is unsupported; expected one of {sorted(_DATASET_TO_CONTRACT)}"
            )
        if dataset_key in seen:
            raise ConnectorConfigError(f"dataset '{dataset_key}' is duplicated in connector config")
        if not mapping:
            raise ConnectorConfigError(f"datasets[{idx}].mapping is required for dataset={dataset_key}")
        if not pattern and not path:
            raise ConnectorConfigError(f"datasets[{idx}] for dataset={dataset_key} must define pattern or path")
        norm.append(
            {
                "dataset_key": dataset_key,
                "pattern": pattern or None,
                "path": path or None,
                "mapping": mapping,
                "required": required,
            }
        )
        seen.add(dataset_key)
    if not norm:
        raise ConnectorConfigError("At least one dataset binding is required")
    return norm


def save_connector_config(
    *,
    config_path: Path,
    project_root: Path,
    connector_id: str,
    kind: str,
    enabled: bool,
    description: str | None,
    source_dir: str | None,
    schedule: str | None,
    data_version_template: str | None,
    bindings: Iterable[dict[str, Any]],
    retry_policy: dict[str, Any] | None = None,
    preserve_unknown: bool = True,
) -> ConnectorSpec:
    connector_id = str(connector_id or "").strip()
    if not connector_id:
        raise ConnectorConfigError("connector_id is required")
    if any(ch.isspace() for ch in connector_id):
        raise ConnectorConfigError("connector_id must not contain spaces")
    if kind not in CONNECTOR_KINDS:
        raise ConnectorConfigError(f"kind='{kind}' is unsupported; expected one of {sorted(CONNECTOR_KINDS)}")

    datasets = normalize_form_bindings(bindings)
    existing_raw: dict[str, Any] = {}
    if preserve_unknown and config_path.exists():
        try:
            existing_raw = _read_yaml(config_path)
        except Exception:
            existing_raw = {}
    retry_policy_raw = existing_raw.get('retry_policy') if preserve_unknown else None
    raw: dict[str, Any] = {
        "connector_id": connector_id,
        "kind": kind,
        "enabled": bool(enabled),
        "datasets": [],
    }
    if str(description or "").strip():
        raw["description"] = str(description).strip()
    if kind == "file" and str(source_dir or "").strip():
        raw["source_dir"] = str(source_dir).strip()
    if str(schedule or "").strip():
        raw["schedule"] = str(schedule).strip()
    if str(data_version_template or "").strip():
        raw["data_version_template"] = str(data_version_template).strip()
    raw["datasets"] = [
        {k: v for k, v in item.items() if v not in (None, "")}
        for item in datasets
    ]
    retry_policy_provided = retry_policy is not None
    retry_policy = retry_policy or {}
    if retry_policy.get('configured_enabled') or retry_policy.get('enabled'):
        statuses = []
        for status in retry_policy.get('retry_on_statuses') or []:
            st = str(status).strip().lower()
            if st:
                statuses.append(st)
        raw['retry_policy'] = {
            'auto_retry_failed_datasets': True,
            'max_attempts': int(retry_policy.get('max_attempts') or 1),
            'backoff_sec': int(retry_policy.get('backoff_sec') or 60),
            'retry_on_statuses': sorted(dict.fromkeys(statuses or ['partial'])),
            'failed_datasets_only': True,
        }
    elif preserve_unknown and (not retry_policy_provided) and isinstance(retry_policy_raw, dict):
        raw['retry_policy'] = retry_policy_raw
    if preserve_unknown:
        for key, value in existing_raw.items():
            if key not in raw and key not in {"connector_id", "kind", "enabled", "description", "source_dir", "schedule", "data_version_template", "datasets"}:
                raw[key] = value

    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    try:
        tmp_path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
        spec = load_connector_spec(tmp_path, project_root=project_root)
        tmp_path.replace(config_path)
        return load_connector_spec(config_path, project_root=project_root)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise



# ---- cron-like scheduler ----

def _cron_value_matches(token: str, value: int, *, lo: int, hi: int) -> bool:
    token = token.strip()
    if token == "*":
        return True
    for part in token.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        base = part
        if "/" in part:
            base, step_raw = part.split("/", 1)
            if not str(step_raw).isdigit() or int(step_raw) <= 0:
                raise ConnectorConfigError(f"Invalid cron step: '{part}'")
            step = int(step_raw)
        if base == "*":
            if (value - lo) % step == 0:
                return True
            continue
        if "-" in base:
            start_raw, end_raw = base.split("-", 1)
            if not start_raw.isdigit() or not end_raw.isdigit():
                raise ConnectorConfigError(f"Invalid cron range: '{part}'")
            start, end = int(start_raw), int(end_raw)
            if start > end:
                raise ConnectorConfigError(f"Invalid cron range: '{part}'")
            if start <= value <= end and (value - start) % step == 0:
                return True
            continue
        if not base.isdigit():
            raise ConnectorConfigError(f"Invalid cron token: '{part}'")
        if int(base) == value:
            return True
    return False



def cron_matches(expr: str, dt: datetime) -> bool:
    expr = str(expr or "").strip()
    if not expr:
        raise ConnectorConfigError("schedule expression is empty")
    if expr == "@hourly":
        return dt.minute == 0
    if expr == "@daily":
        return dt.minute == 0 and dt.hour == 0
    parts = expr.split()
    if len(parts) != 5:
        raise ConnectorConfigError(
            f"schedule '{expr}' must have 5 cron fields ('minute hour day month weekday') or @hourly/@daily"
        )
    minute, hour, day, month, weekday = parts
    weekday_value = (dt.weekday() + 1) % 7  # Sunday=0 like cron.
    return (
        _cron_value_matches(minute, dt.minute, lo=0, hi=59)
        and _cron_value_matches(hour, dt.hour, lo=0, hi=23)
        and _cron_value_matches(day, dt.day, lo=1, hi=31)
        and _cron_value_matches(month, dt.month, lo=1, hi=12)
        and _cron_value_matches(weekday, weekday_value, lo=0, hi=6)
    )



def schedule_slot_for(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return dt.isoformat()
