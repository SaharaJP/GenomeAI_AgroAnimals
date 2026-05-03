from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .contracts import DatasetContract, load_contracts_dir
from .versioning import write_json


_DEFAULT_OPTIONAL_DATASETS = {
    "dm_testday",
    "dm_health_events",
    "dm_treatments",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_contract_catalog_config(path: Path) -> Dict[str, Dict[str, Any]]:
    path = path.resolve()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("datasets", []) if isinstance(raw, dict) else []
    result: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        dataset = str(item.get("dataset") or "").strip()
        if not dataset:
            continue
        result[dataset] = item
    return result


def _detect_example_files(*, dataset: str, project_root: Path) -> List[str]:
    candidates = [
        project_root / "data" / "examples" / f"{dataset}.csv",
        project_root / "data" / "examples" / "external" / f"{dataset}.csv",
        project_root / "data" / "fixtures" / "target_v2" / f"{dataset}.csv",
    ]
    found: List[str] = []
    for path in candidates:
        if path.exists():
            found.append(str(path.resolve()))
    return found


def _detect_mapping_templates(*, dataset: str, project_root: Path) -> List[str]:
    dataset_key = dataset.replace("dm_", "")
    candidates = [
        project_root / "configs" / "mappings" / f"{dataset_key}_example.yaml",
        project_root / "configs" / "mappings" / f"{dataset}_example.yaml",
    ]
    templates_root = project_root / "configs" / "mappings" / "templates"
    if templates_root.exists():
        candidates.extend(sorted(templates_root.glob(f"*/{dataset_key}.yaml")))
        candidates.extend(sorted(templates_root.glob(f"*/{dataset}.yaml")))
    found: List[str] = []
    for path in candidates:
        if path.exists():
            resolved = str(path.resolve())
            if resolved not in found:
                found.append(resolved)
    return found


def _relpath(path: Path, *, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path.resolve())


def _example_file_rows(paths: List[str], *, project_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in paths:
        p = Path(raw).resolve()
        rows.append(
            {
                "path": str(p),
                "relative_path": _relpath(p, project_root=project_root),
                "exists": p.exists(),
            }
        )
    return rows


def _mapping_template_rows(paths: List[str], *, project_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        p = Path(raw).resolve()
        if str(p) in seen:
            continue
        seen.add(str(p))
        payload: Dict[str, Any] = {}
        if p.exists():
            try:
                loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                if isinstance(loaded, dict):
                    payload = loaded
            except Exception:
                payload = {}
        relative = _relpath(p, project_root=project_root)
        parts = Path(relative).parts
        source_system = "custom"
        if len(parts) >= 4 and parts[:3] == ("configs", "mappings", "templates"):
            source_system = parts[3]
        elif p.name.endswith("_example.yaml"):
            source_system = "example"
        columns = payload.get("columns") if isinstance(payload.get("columns"), dict) else {}
        constants = payload.get("constants") if isinstance(payload.get("constants"), dict) else {}
        dataset_key = str(payload.get("dataset") or p.stem or "").strip()
        rows.append(
            {
                "path": str(p),
                "relative_path": relative,
                "template_name": p.stem,
                "source_system": source_system,
                "dataset_key": dataset_key,
                "column_count": len(columns),
                "constants_count": len(constants),
                "dayfirst": bool(payload.get("dayfirst", False)),
                "exists": p.exists(),
            }
        )
    return rows


def _qc_status_counts(qc_coverage: Dict[str, str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in qc_coverage.values():
        key = str(value or "unknown").strip().lower() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _entry_from_contract(contract: DatasetContract, *, meta: Optional[Dict[str, Any]], project_root: Path) -> Dict[str, Any]:
    meta = meta or {}
    required_for_mvp = bool(meta.get("required_for_mvp", contract.dataset not in _DEFAULT_OPTIONAL_DATASETS))
    examples = [str(x) for x in meta.get("example_files", []) if str(x).strip()]
    if not examples:
        examples = _detect_example_files(dataset=contract.dataset, project_root=project_root)

    mapping_templates = [str(x) for x in meta.get("mapping_templates", []) if str(x).strip()]
    if not mapping_templates:
        mapping_templates = _detect_mapping_templates(dataset=contract.dataset, project_root=project_root)

    qc_coverage = meta.get("qc_coverage") if isinstance(meta.get("qc_coverage"), dict) else {}
    source_systems = meta.get("source_systems") if isinstance(meta.get("source_systems"), list) else []

    field_rows: List[Dict[str, Any]] = []
    for fs in contract.fields:
        field_rows.append(
            {
                "name": fs.name,
                "type": fs.type,
                "required": fs.required,
                "allowed_values": list(fs.allowed_values or []),
                "description": fs.description,
            }
        )

    mapping_template_rows = _mapping_template_rows(mapping_templates, project_root=project_root)
    example_file_rows = _example_file_rows(examples, project_root=project_root)
    qc_coverage_norm = {str(k): str(v) for k, v in qc_coverage.items()}
    qc_status_counts = _qc_status_counts(qc_coverage_norm)
    effective_sources = [str(x) for x in source_systems if str(x).strip()]
    for row in mapping_template_rows:
        source = str(row.get("source_system") or "").strip()
        if source and source not in effective_sources and source != "example":
            effective_sources.append(source)

    return {
        "dataset": contract.dataset,
        "contract_version": contract.contract_version,
        "status": str(meta.get("status") or "active"),
        "domain": str(meta.get("domain") or "canonical"),
        "required_for_mvp": required_for_mvp,
        "description": contract.description,
        "primary_key": list(contract.primary_key or []),
        "foreign_keys": list(contract.foreign_keys or []),
        "field_count": len(contract.fields),
        "required_field_count": len(contract.required_fields),
        "required_fields": list(contract.required_fields),
        "notes": list(contract.notes or []),
        "source_systems": effective_sources,
        "mapping_templates": mapping_templates,
        "mapping_template_rows": mapping_template_rows,
        "mapping_template_count": len(mapping_template_rows),
        "example_files": examples,
        "example_file_rows": example_file_rows,
        "example_file_count": len(example_file_rows),
        "qc_coverage": qc_coverage_norm,
        "qc_status_counts": qc_status_counts,
        "fields": field_rows,
    }


def _catalog_summary(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    domains = sorted({str(item.get("domain") or "").strip() for item in entries if str(item.get("domain") or "").strip()})
    statuses = sorted({str(item.get("status") or "").strip() for item in entries if str(item.get("status") or "").strip()})
    source_systems = sorted({str(src).strip() for item in entries for src in item.get("source_systems", []) if str(src).strip()})
    qc_counts: Dict[str, int] = {}
    for item in entries:
        for key, value in (item.get("qc_status_counts") or {}).items():
            qc_counts[str(key)] = qc_counts.get(str(key), 0) + int(value)
    return {
        "dataset_count": len(entries),
        "required_for_mvp_count": sum(1 for item in entries if item.get("required_for_mvp")),
        "mapping_template_count": sum(int(item.get("mapping_template_count") or 0) for item in entries),
        "example_file_count": sum(int(item.get("example_file_count") or 0) for item in entries),
        "domains": domains,
        "statuses": statuses,
        "source_systems": source_systems,
        "qc_status_counts": qc_counts,
    }


def build_contract_catalog(
    *,
    contracts_dir: Path,
    catalog_path: Optional[Path] = None,
) -> Dict[str, Any]:
    contracts_dir = contracts_dir.resolve()
    project_root = contracts_dir.parent.parent.resolve()
    catalog_meta = load_contract_catalog_config(catalog_path or (contracts_dir / "catalog.json"))
    contracts = load_contracts_dir(contracts_dir)

    entries = [_entry_from_contract(contract, meta=catalog_meta.get(dataset), project_root=project_root) for dataset, contract in sorted(contracts.items())]
    return {
        "schema": "genomeai.data_contract_catalog.v1",
        "generated_at_utc": _utc_now_iso(),
        "contracts_dir": str(contracts_dir),
        "project_root": str(project_root),
        "datasets": entries,
        **_catalog_summary(entries),
    }


def render_contract_catalog_markdown(manifest: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# GenomeAI AgroAnimals — Data Contracts Catalog")
    lines.append("")
    lines.append(f"- Generated at (UTC): {manifest.get('generated_at_utc', 'n/a')}")
    lines.append(f"- Dataset count: {manifest.get('dataset_count', 0)}")
    lines.append(f"- Required for MVP: {manifest.get('required_for_mvp_count', 0)}")
    lines.append(f"- Mapping templates: {manifest.get('mapping_template_count', 0)}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Dataset | Version | Domain | Status | Required | Required fields | Mapping templates | QC coverage |")
    lines.append("|---|---|---|---|---:|---:|---:|---|")
    for item in manifest.get("datasets", []):
        qc = item.get("qc_status_counts") or {}
        qc_text = ", ".join(f"{k}:{v}" for k, v in sorted(qc.items())) or "—"
        lines.append(
            f"| {item.get('dataset','')} | {item.get('contract_version','')} | {item.get('domain','')} | {item.get('status','')} | {'yes' if item.get('required_for_mvp') else 'no'} | {item.get('required_field_count',0)} | {item.get('mapping_template_count',0)} | {qc_text} |"
        )
    for item in manifest.get("datasets", []):
        lines.append("")
        lines.append(f"## {item.get('dataset','')}")
        lines.append("")
        lines.append(f"- Contract version: {item.get('contract_version', '')}")
        lines.append(f"- Domain/status: {item.get('domain', '')} / {item.get('status', '')}")
        lines.append(f"- Required for MVP: {'yes' if item.get('required_for_mvp') else 'no'}")
        lines.append(f"- Source systems: {', '.join(item.get('source_systems') or []) or '—'}")
        lines.append(f"- Required fields: {', '.join(item.get('required_fields') or []) or '—'}")
        if item.get("description"):
            lines.append(f"- Description: {item['description']}")
        if item.get("notes"):
            lines.append(f"- Notes: {'; '.join(item['notes'])}")
        lines.append("")
        lines.append("### Fields")
        lines.append("")
        lines.append("| Field | Type | Required | Allowed values | Description |")
        lines.append("|---|---|---|---|---|")
        for field in item.get("fields", []):
            allowed = ", ".join(field.get("allowed_values") or []) or "—"
            lines.append(
                f"| {field.get('name','')} | {field.get('type','')} | {'yes' if field.get('required') else 'no'} | {allowed} | {field.get('description','')} |"
            )
        lines.append("")
        lines.append("### Mapping templates")
        lines.append("")
        if item.get("mapping_template_rows"):
            lines.append("| Source | Path | Columns | Dayfirst |")
            lines.append("|---|---|---:|---|")
            for row in item.get("mapping_template_rows", []):
                lines.append(
                    f"| {row.get('source_system','')} | {row.get('relative_path','')} | {row.get('column_count',0)} | {'yes' if row.get('dayfirst') else 'no'} |"
                )
        else:
            lines.append("—")
        lines.append("")
        lines.append("### Example files")
        lines.append("")
        if item.get("example_file_rows"):
            for row in item.get("example_file_rows", []):
                lines.append(f"- {row.get('relative_path', row.get('path', ''))}")
        else:
            lines.append("- —")
    return "\n".join(lines).strip() + "\n"


def validate_contract_catalog_versions(
    manifest: Dict[str, Any],
    *,
    contracts_dir: Path,
) -> Dict[str, Any]:
    contracts = load_contracts_dir(contracts_dir.resolve())
    issues: List[str] = []
    checked = 0
    for item in list(manifest.get("datasets") or []):
        if not isinstance(item, dict):
            continue
        dataset = str(item.get("dataset") or "").strip()
        if not dataset:
            issues.append("catalog entry without dataset name")
            continue
        checked += 1
        contract = contracts.get(dataset)
        if contract is None:
            issues.append(f"contract file is missing for dataset={dataset}")
            continue
        manifest_version = str(item.get("contract_version") or "").strip()
        if manifest_version != contract.contract_version:
            issues.append(
                f"contract version mismatch for dataset={dataset}: catalog={manifest_version or '—'} actual={contract.contract_version}"
            )
        field_names = {str(x.get('name') or '').strip() for x in list(item.get('fields') or []) if isinstance(x, dict)}
        required_fields = [str(x).strip() for x in list(item.get('required_fields') or []) if str(x).strip()]
        missing_required = [x for x in required_fields if x not in field_names]
        if missing_required:
            issues.append(f"required_fields are absent from fields list for dataset={dataset}: {', '.join(sorted(missing_required))}")
        for row in list(item.get('mapping_template_rows') or []):
            if not isinstance(row, dict):
                continue
            dataset_key = str(row.get('dataset_key') or '').strip()
            relative_path = str(row.get('relative_path') or row.get('path') or '').strip()
            if dataset_key and dataset_key not in {dataset.replace('dm_', ''), dataset}:
                issues.append(
                    f"mapping template dataset_key mismatch for dataset={dataset}: template={relative_path} dataset_key={dataset_key}"
                )
    return {
        'ok': not issues,
        'checked_datasets': checked,
        'issue_count': len(issues),
        'issues': issues,
    }


def write_contract_catalog(
    *,
    output_path: Path,
    contracts_dir: Path,
    catalog_path: Optional[Path] = None,
    markdown_output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    manifest = build_contract_catalog(contracts_dir=contracts_dir, catalog_path=catalog_path)
    write_json(output_path, manifest)
    if markdown_output_path is not None:
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_output_path.write_text(render_contract_catalog_markdown(manifest), encoding="utf-8")
    return manifest
