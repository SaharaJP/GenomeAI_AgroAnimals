from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _existing_resolved_names(*names: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        item = str(name or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _list_subdirs(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted([p.name for p in path.iterdir() if p.is_dir()])


def _order_with_latest_last(names: list[str], latest: str | None) -> list[str]:
    ordered = sorted(_existing_resolved_names(*names))
    latest_name = str(latest or "").strip()
    if latest_name and latest_name in ordered:
        ordered = [name for name in ordered if name != latest_name] + [latest_name]
    return ordered


def _model_manifest_path(artifacts_root: Path, data_version: str) -> Path:
    return Path(artifacts_root) / data_version / "metadata" / "model_manifest.json"


def _scoring_manifest_path(artifacts_root: Path, data_version: str) -> Path:
    return Path(artifacts_root) / data_version / "metadata" / "scoring_manifest.json"


def load_model_registry(*, artifacts_root: Path, data_version: str) -> dict[str, Any]:
    return _read_json_dict(_model_manifest_path(Path(artifacts_root), data_version))


def load_scoring_registry(*, artifacts_root: Path, data_version: str) -> dict[str, Any]:
    return _read_json_dict(_scoring_manifest_path(Path(artifacts_root), data_version))


def resolve_model_dir(*, artifacts_root: Path, data_version: str, model_version: str) -> Path:
    artifacts_root = Path(artifacts_root)
    model_version = str(model_version).strip()
    run_dir = artifacts_root / data_version / "runs" / model_version / "model"
    legacy_dir = artifacts_root / data_version / "models" / model_version
    if run_dir.exists():
        return run_dir
    return legacy_dir


def resolve_scoring_dir(*, artifacts_root: Path, data_version: str, scoring_run: str) -> Path:
    artifacts_root = Path(artifacts_root)
    scoring_run = str(scoring_run).strip()
    run_dir = artifacts_root / data_version / "runs" / scoring_run / "scoring"
    legacy_dir = artifacts_root / data_version / "scoring" / scoring_run
    if run_dir.exists():
        return run_dir
    return legacy_dir


def list_model_versions(*, artifacts_root: Path, data_version: str) -> list[str]:
    artifacts_root = Path(artifacts_root)
    manifest = load_model_registry(artifacts_root=artifacts_root, data_version=data_version)
    latest = str(manifest.get("latest") or "").strip() or None
    manifest_names = list((manifest.get("models") or {}).keys()) if isinstance(manifest.get("models"), dict) else []
    dir_names = _list_subdirs(artifacts_root / data_version / "models")
    run_names: list[str] = []
    runs_dir = artifacts_root / data_version / "runs"
    if runs_dir.exists():
        for path in runs_dir.iterdir():
            if path.is_dir() and (path / "model").exists():
                run_names.append(path.name)
    return _order_with_latest_last([*manifest_names, *dir_names, *run_names], latest)


def list_scoring_runs(*, artifacts_root: Path, data_version: str) -> list[str]:
    artifacts_root = Path(artifacts_root)
    manifest = load_scoring_registry(artifacts_root=artifacts_root, data_version=data_version)
    latest = str(manifest.get("latest") or "").strip() or None
    manifest_names = list((manifest.get("scoring_runs") or {}).keys()) if isinstance(manifest.get("scoring_runs"), dict) else []
    dir_names = _list_subdirs(artifacts_root / data_version / "scoring")
    run_names: list[str] = []
    runs_dir = artifacts_root / data_version / "runs"
    if runs_dir.exists():
        for path in runs_dir.iterdir():
            if path.is_dir() and (path / "scoring").exists():
                run_names.append(path.name)
    return _order_with_latest_last([*manifest_names, *dir_names, *run_names], latest)


def find_latest_model_version(*, artifacts_root: Path, data_version: str) -> str | None:
    manifest = load_model_registry(artifacts_root=artifacts_root, data_version=data_version)
    latest = str(manifest.get("latest") or "").strip()
    if latest and resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=latest).exists():
        return latest

    candidates: list[tuple[float, str]] = []
    for name in list_model_versions(artifacts_root=artifacts_root, data_version=data_version):
        path = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=name)
        card = path / "model_card.json"
        marker = card if card.exists() else path
        if marker.exists():
            candidates.append((marker.stat().st_mtime, name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def find_latest_scoring_run(*, artifacts_root: Path, data_version: str) -> str | None:
    manifest = load_scoring_registry(artifacts_root=artifacts_root, data_version=data_version)
    latest = str(manifest.get("latest") or "").strip()
    if latest and resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=latest).exists():
        return latest

    candidates: list[tuple[float, str]] = []
    for name in list_scoring_runs(artifacts_root=artifacts_root, data_version=data_version):
        path = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=name)
        scored = path / "scored_latest.csv"
        marker = scored if scored.exists() else path
        if marker.exists():
            candidates.append((marker.stat().st_mtime, name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _safe_relative_to(path: Path, base: Path) -> str | None:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except Exception:
        return None


def _existing_relpath(path: Path, *, artifacts_root: Path) -> str | None:
    if not path.exists():
        return None
    return _safe_relative_to(path, artifacts_root)


def _output_relpath(raw_value: Any, *, artifacts_root: Path, fallback: Path | None = None) -> str | None:
    text = str(raw_value or "").strip()
    candidates: list[Path] = []
    if text:
        p = Path(text)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates.append((artifacts_root / p).resolve())
    if fallback is not None:
        candidates.append(fallback)
    for candidate in candidates:
        rel = _safe_relative_to(candidate, artifacts_root)
        if rel:
            return rel
    return None



def _normalize_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_dict(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_normalize_dict(v) for v in value]
    return value


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_model_surface_snapshot(*, artifacts_root: Path, data_version: str, model_version: str) -> dict[str, Any]:
    artifacts_root = Path(artifacts_root)
    model_dir = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    card = load_model_card(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    summary = load_train_summary(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    metrics = card.get("metrics") if isinstance(card.get("metrics"), dict) else summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    split = card.get("split") if isinstance(card.get("split"), dict) else summary.get("split") if isinstance(summary.get("split"), dict) else {}
    features = card.get("features") if isinstance(card.get("features"), dict) else summary.get("features") if isinstance(summary.get("features"), dict) else {}
    limitations = card.get("limitations") if isinstance(card.get("limitations"), dict) else summary.get("limitations") if isinstance(summary.get("limitations"), dict) else {}
    return {
        "data_version": data_version,
        "model_version": str(model_version),
        "config_version": card.get("config_version") or summary.get("config_version"),
        "seed": card.get("seed") if "seed" in card else summary.get("seed"),
        "target": card.get("target") or summary.get("target"),
        "qc_run": card.get("qc_run") or summary.get("qc_run"),
        "qc_status": card.get("qc_status") or summary.get("qc_status"),
        "metrics": _normalize_dict(metrics),
        "split": _normalize_dict(split),
        "features": _normalize_dict(features),
        "limitations": _normalize_dict(limitations),
        "artifacts": {
            "test_predictions_csv_sha256": _sha256_file(model_dir / "test_predictions.csv"),
            "explainability_profile_json_sha256": _sha256_file(model_dir / "explainability_profile.json"),
            "model_card_json_exists": bool((model_dir / "model_card.json").exists()),
            "train_summary_json_exists": bool((model_dir / "train_summary.json").exists()),
        },
    }


def build_scoring_surface_snapshot(*, artifacts_root: Path, data_version: str, scoring_run: str) -> dict[str, Any]:
    artifacts_root = Path(artifacts_root)
    scoring_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)
    summary = load_scoring_summary(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)
    row_counts = summary.get("row_counts") if isinstance(summary.get("row_counts"), dict) else {}
    inputs = summary.get("inputs") if isinstance(summary.get("inputs"), dict) else {}
    return {
        "data_version": data_version,
        "scoring_run": str(scoring_run),
        "model_version": summary.get("model_version"),
        "config_version": summary.get("config_version"),
        "seed": summary.get("seed"),
        "status": summary.get("status"),
        "row_counts": _normalize_dict(row_counts),
        "input_features": _normalize_dict(inputs.get("features") if isinstance(inputs.get("features"), dict) else {}),
        "artifacts": {
            "scored_latest_csv_sha256": _sha256_file(scoring_dir / "scored_latest.csv"),
            "group_summary_csv_sha256": _sha256_file(scoring_dir / "group_summary.csv"),
            "productivity_explanations_csv_sha256": _sha256_file(scoring_dir / "productivity_explanations.csv"),
            "scoring_summary_json_exists": bool((scoring_dir / "scoring_summary.json").exists()),
        },
    }


def load_model_card(*, artifacts_root: Path, data_version: str, model_version: str) -> dict[str, Any]:
    model_dir = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    return _read_json_dict(model_dir / "model_card.json")


def load_train_summary(*, artifacts_root: Path, data_version: str, model_version: str) -> dict[str, Any]:
    model_dir = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
    return _read_json_dict(model_dir / "train_summary.json")


def load_scoring_summary(*, artifacts_root: Path, data_version: str, scoring_run: str) -> dict[str, Any]:
    scoring_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)
    return _read_json_dict(scoring_dir / "scoring_summary.json")


def list_model_entries(*, artifacts_root: Path, data_version: str) -> list[dict[str, Any]]:
    artifacts_root = Path(artifacts_root)
    manifest = load_model_registry(artifacts_root=artifacts_root, data_version=data_version)
    latest = str(manifest.get("latest") or "").strip()
    reg_models = manifest.get("models") if isinstance(manifest.get("models"), dict) else {}
    rows: list[dict[str, Any]] = []
    for model_version in list_model_versions(artifacts_root=artifacts_root, data_version=data_version):
        model_dir = resolve_model_dir(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
        reg_entry = reg_models.get(model_version) if isinstance(reg_models, dict) else {}
        card = load_model_card(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
        train_summary = load_train_summary(artifacts_root=artifacts_root, data_version=data_version, model_version=model_version)
        metrics = card.get("metrics") if isinstance(card.get("metrics"), dict) else reg_entry.get("metrics") if isinstance(reg_entry, dict) else {}
        rows.append(
            {
                "model_version": model_version,
                "is_latest": bool(model_version == latest),
                "created_at_utc": card.get("created_at_utc") or train_summary.get("created_at_utc") or (reg_entry or {}).get("created_at_utc"),
                "config_version": card.get("config_version") or train_summary.get("config_version") or (reg_entry or {}).get("config_version"),
                "seed": card.get("seed") if "seed" in card else train_summary.get("seed") if "seed" in train_summary else (reg_entry or {}).get("seed"),
                "metrics": metrics if isinstance(metrics, dict) else {},
                "dir_relpath": _existing_relpath(model_dir, artifacts_root=artifacts_root),
                "model_card_json_relpath": _existing_relpath(model_dir / "model_card.json", artifacts_root=artifacts_root),
                "model_card_md_relpath": _existing_relpath(model_dir / "model_card.md", artifacts_root=artifacts_root),
                "train_summary_relpath": _existing_relpath(model_dir / "train_summary.json", artifacts_root=artifacts_root),
            }
        )
    return rows


def list_scoring_entries(*, artifacts_root: Path, data_version: str) -> list[dict[str, Any]]:
    artifacts_root = Path(artifacts_root)
    manifest = load_scoring_registry(artifacts_root=artifacts_root, data_version=data_version)
    latest = str(manifest.get("latest") or "").strip()
    reg_runs = manifest.get("scoring_runs") if isinstance(manifest.get("scoring_runs"), dict) else {}
    rows: list[dict[str, Any]] = []
    for scoring_run in list_scoring_runs(artifacts_root=artifacts_root, data_version=data_version):
        scoring_dir = resolve_scoring_dir(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)
        reg_entry = reg_runs.get(scoring_run) if isinstance(reg_runs, dict) else {}
        summary = load_scoring_summary(artifacts_root=artifacts_root, data_version=data_version, scoring_run=scoring_run)
        outputs = summary.get("outputs") if isinstance(summary.get("outputs"), dict) else {}
        row_counts = summary.get("row_counts") if isinstance(summary.get("row_counts"), dict) else (reg_entry.get("row_counts") if isinstance(reg_entry, dict) else {})
        rows.append(
            {
                "scoring_run": scoring_run,
                "is_latest": bool(scoring_run == latest),
                "created_at_utc": summary.get("created_at_utc") or (reg_entry or {}).get("created_at_utc"),
                "model_version": summary.get("model_version") or (reg_entry or {}).get("model_version"),
                "config_version": summary.get("config_version") or (reg_entry or {}).get("config_version"),
                "seed": summary.get("seed") if "seed" in summary else (reg_entry or {}).get("seed"),
                "row_counts": row_counts if isinstance(row_counts, dict) else {},
                "status": summary.get("status") or (reg_entry or {}).get("status"),
                "dir_relpath": _existing_relpath(scoring_dir, artifacts_root=artifacts_root),
                "scoring_summary_relpath": _existing_relpath(scoring_dir / "scoring_summary.json", artifacts_root=artifacts_root),
                "animal_ranking_relpath": _output_relpath(outputs.get("animal_ranking_xlsx"), artifacts_root=artifacts_root, fallback=scoring_dir / "exports" / "animal_ranking.xlsx"),
                "group_summary_relpath": _output_relpath(outputs.get("group_summary_xlsx"), artifacts_root=artifacts_root, fallback=scoring_dir / "exports" / "group_summary.xlsx"),
                "recommendations_relpath": _output_relpath(outputs.get("recommendations_xlsx"), artifacts_root=artifacts_root, fallback=scoring_dir / "exports" / "recommendations.xlsx"),
                "scored_latest_relpath": _output_relpath(outputs.get("scored_latest_csv"), artifacts_root=artifacts_root, fallback=scoring_dir / "scored_latest.csv"),
                "explanations_relpath": _output_relpath(outputs.get("explanations_csv"), artifacts_root=artifacts_root, fallback=scoring_dir / "productivity_explanations.csv"),
            }
        )
    return rows


__all__ = [
    "build_model_surface_snapshot",
    "build_scoring_surface_snapshot",
    "find_latest_model_version",
    "find_latest_scoring_run",
    "list_model_entries",
    "list_model_versions",
    "list_scoring_entries",
    "list_scoring_runs",
    "load_model_card",
    "load_model_registry",
    "load_scoring_registry",
    "load_scoring_summary",
    "load_train_summary",
    "resolve_model_dir",
    "resolve_scoring_dir",
]
