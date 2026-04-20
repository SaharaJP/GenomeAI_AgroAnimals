from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from genomeai.connectors_v1 import dataset_contract_name


def _read_yaml(path: Path) -> dict[str, Any]:
    obj = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(obj, dict):
        raise ValueError(f'Connector catalog entry must be a mapping: {path}')
    return obj


def _norm_list(raw: Any) -> list[str]:
    if raw in (None, ''):
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, (list, tuple, set)):
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            value = str(item or '').strip()
            if value and value not in seen:
                out.append(value)
                seen.add(value)
        return out
    return []


def _resolve_rel(path_value: str | None, *, project_root: Path) -> str | None:
    raw = str(path_value or '').strip()
    if not raw:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (project_root / p).resolve()
    return str(p)


def load_farm_connector_catalog(catalog_dir: Path, *, project_root: Path) -> list[dict[str, Any]]:
    catalog_dir = catalog_dir.resolve()
    project_root = project_root.resolve()
    rows: list[dict[str, Any]] = []
    if not catalog_dir.exists():
        return rows
    for path in sorted(catalog_dir.glob('*.y*ml')):
        raw = _read_yaml(path)
        adapter_id = str(raw.get('adapter_id') or raw.get('id') or '').strip()
        if not adapter_id:
            raise ValueError(f'adapter_id is required in {path}')
        supported_datasets = [str(x).strip().lower() for x in _norm_list(raw.get('supported_datasets')) if str(x).strip()]
        contracts = _norm_list(raw.get('data_contracts'))
        if not contracts:
            contracts = [c for c in (dataset_contract_name(key) for key in supported_datasets) if c]
        mapping_templates = [x for x in (_resolve_rel(v, project_root=project_root) for v in _norm_list(raw.get('reusable_mapping_templates'))) if x]
        row = {
            'adapter_id': adapter_id,
            'label': str(raw.get('label') or adapter_id).strip(),
            'source_system': str(raw.get('source_system') or raw.get('vendor') or '').strip() or adapter_id,
            'system_family': str(raw.get('system_family') or 'farm_system').strip(),
            'connector_kind': str(raw.get('connector_kind') or 'file').strip().lower(),
            'export_mode': str(raw.get('export_mode') or 'batch_export').strip(),
            'default_schedule': str(raw.get('default_schedule') or '').strip() or None,
            'description': str(raw.get('description') or '').strip() or None,
            'supported_datasets': supported_datasets,
            'data_contracts': contracts,
            'reusable_mapping_templates': mapping_templates,
            'representative_config_path': _resolve_rel(str(raw.get('representative_config_path') or ''), project_root=project_root),
            'diagnostics_profile': dict(raw.get('diagnostics') or {}),
            'limitations': _norm_list(raw.get('limitations')),
            'staged_adoption_note': str(raw.get('staged_adoption_note') or '').strip() or None,
            'config_path': str(path.resolve()),
        }
        rows.append(row)
    rows.sort(key=lambda row: (str(row.get('source_system') or ''), str(row.get('adapter_id') or '')))
    return rows


def summarize_farm_connector_catalog(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        'total': len(rows or []),
        'file': 0,
        'api_stub': 0,
        'onec_stub': 0,
        'datasets_supported': 0,
        'contracts_supported': 0,
    }
    datasets: set[str] = set()
    contracts: set[str] = set()
    for row in rows or []:
        kind = str(row.get('connector_kind') or '').strip().lower()
        if kind in summary:
            summary[kind] += 1
        datasets.update(str(x).strip().lower() for x in (row.get('supported_datasets') or []) if str(x).strip())
        contracts.update(str(x).strip() for x in (row.get('data_contracts') or []) if str(x).strip())
    summary['datasets_supported'] = len(datasets)
    summary['contracts_supported'] = len(contracts)
    return summary


__all__ = ['load_farm_connector_catalog', 'summarize_farm_connector_catalog']
