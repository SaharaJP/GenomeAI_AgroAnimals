from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from core.infra.environment_snapshot import build_test_environment_snapshot
from core.infra.runtime_auth_storage import auth_storage_diagnostics
from core.infra.runtime_state_storage import build_runtime_state_summary_payload
from core.infra.runtime_storage import resolve_runtime_storage_settings, runtime_storage_diagnostics
from core.infra.queue_runtime import build_queue_runtime_summary_payload
from core.recovery.adult_maintenance import (
    build_adult_backup_metadata_summary,
    build_artifact_integrity_summary,
)
from genomeai.backup_restore import apply_backup_retention, _normalize_db_path, _write_best_effort_audit


_FIXED_ZIP_DT = (1980, 1, 1, 0, 0, 0)

_DEFAULT_ARTIFACT_LIFECYCLE_POLICY: dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "archive_dir": "artifacts/_archive",
    "support_bundle_dir": "artifacts/support_bundles",
    "protected_prefixes": [
        "golden",
        "installers",
        "artifacts/releases",
        "artifacts/_release",
        "artifacts/manifests",
        "artifacts/manifest.json",
        "web_cabinet/storage/web.db",
        "web_cabinet/storage/uploads",
    ],
    "runtime_families": {
        "verify_reports": {
            "enabled": True,
            "root": "artifacts/_verify_refactor",
            "glob": "verify_*",
            "keep_last": 3,
        },
        "ci_scratch": {
            "enabled": True,
            "root": "artifacts/_ci",
            "glob": "*",
            "keep_last": 3,
        },
        "tmp_workdirs": {
            "enabled": True,
            "root": "_tmp",
            "glob": "*",
            "keep_last": 5,
        },
        "runtime_archives": {
            "enabled": True,
            "root": "artifacts/_archive",
            "glob": "*.zip",
            "keep_last": 5,
        },
        "support_bundles": {
            "enabled": True,
            "root": "artifacts/support_bundles",
            "glob": "*.zip",
            "keep_last": 5,
        },
        "web_logs": {
            "enabled": True,
            "root": "web_cabinet/storage/logs",
            "glob": "*.log",
            "keep_last": 20,
        },
    },
    "backup_retention": {
        "enabled": True,
        "include_data_versions_default": False,
    },
    "support_bundle": {
        "include_environment_snapshot": True,
        "include_inventory": True,
        "include_policy_files": True,
        "include_web_db_summary": True,
        "include_latest_verify_report": True,
        "max_log_files": 5,
    },
}


class ArtifactLifecycleError(ValueError):
    """Human-readable artifact lifecycle configuration or integrity error."""


@dataclass(frozen=True)
class RuntimeRoots:
    project_root: Path
    artifacts_root: Path
    web_storage: Path
    db_path: Path
    tmp_root: Path


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _merge_nested(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _resolve_runtime_roots(
    *,
    project_root: str | Path,
    artifacts_root: str | Path | None = None,
    web_storage: str | Path | None = None,
    db_path: str | Path | None = None,
    tmp_root: str | Path | None = None,
) -> RuntimeRoots:
    project_root_path = Path(project_root).resolve()
    artifacts_root_path = Path(artifacts_root).resolve() if artifacts_root is not None else (project_root_path / "artifacts").resolve()
    web_storage_path = Path(web_storage).resolve() if web_storage is not None else (project_root_path / "web_cabinet" / "storage").resolve()
    db_path_path = _normalize_db_path(web_storage_path, Path(db_path).resolve() if db_path is not None else None)
    tmp_root_path = Path(tmp_root).resolve() if tmp_root is not None else (project_root_path / "_tmp").resolve()
    return RuntimeRoots(
        project_root=project_root_path,
        artifacts_root=artifacts_root_path,
        web_storage=web_storage_path,
        db_path=db_path_path,
        tmp_root=tmp_root_path,
    )


def load_artifact_lifecycle_policy(*, project_root: str | Path = ".", config_path: str | Path | None = None) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    path = Path(config_path).resolve() if config_path is not None else (project_root_path / "configs" / "ops" / "artifact_lifecycle_v1.yaml").resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ArtifactLifecycleError(f"{path}: ожидался YAML-объект верхнего уровня")

    cfg = _merge_nested(_json_clone(_DEFAULT_ARTIFACT_LIFECYCLE_POLICY), raw)
    try:
        cfg["version"] = int(cfg.get("version", 1))
    except Exception as exc:
        raise ArtifactLifecycleError(f"{path}: version должен быть целым числом") from exc
    cfg["enabled"] = bool(cfg.get("enabled", True))

    for key in ("archive_dir", "support_bundle_dir"):
        cfg[key] = str(cfg.get(key) or "").strip()
        if not cfg[key]:
            raise ArtifactLifecycleError(f"{path}: {key} должен быть непустой строкой")

    protected = cfg.get("protected_prefixes") or []
    if not isinstance(protected, list):
        raise ArtifactLifecycleError(f"{path}: protected_prefixes должен быть списком")
    cfg["protected_prefixes"] = [str(item).strip().strip("/") for item in protected if str(item).strip()]

    families = cfg.get("runtime_families") or {}
    if not isinstance(families, dict) or not families:
        raise ArtifactLifecycleError(f"{path}: runtime_families должен быть непустым объектом")
    normalized_families: dict[str, Any] = {}
    for family_name, family_raw in families.items():
        if not isinstance(family_raw, dict):
            raise ArtifactLifecycleError(f"{path}: runtime_families.{family_name} должен быть объектом")
        family = dict(family_raw)
        family["enabled"] = bool(family.get("enabled", True))
        family["root"] = str(family.get("root") or "").strip()
        family["glob"] = str(family.get("glob") or "*").strip() or "*"
        try:
            family["keep_last"] = int(family.get("keep_last", 0))
        except Exception as exc:
            raise ArtifactLifecycleError(f"{path}: runtime_families.{family_name}.keep_last должен быть целым числом") from exc
        if family["keep_last"] < 0:
            raise ArtifactLifecycleError(f"{path}: runtime_families.{family_name}.keep_last должен быть >= 0")
        if not family["root"]:
            raise ArtifactLifecycleError(f"{path}: runtime_families.{family_name}.root должен быть непустой строкой")
        normalized_families[str(family_name)] = family
    cfg["runtime_families"] = normalized_families

    backup_retention = cfg.get("backup_retention") or {}
    if not isinstance(backup_retention, dict):
        raise ArtifactLifecycleError(f"{path}: backup_retention должен быть объектом")
    backup_retention["enabled"] = bool(backup_retention.get("enabled", True))
    backup_retention["include_data_versions_default"] = bool(backup_retention.get("include_data_versions_default", False))
    cfg["backup_retention"] = backup_retention

    support_bundle = cfg.get("support_bundle") or {}
    if not isinstance(support_bundle, dict):
        raise ArtifactLifecycleError(f"{path}: support_bundle должен быть объектом")
    for key in [
        "include_environment_snapshot",
        "include_inventory",
        "include_policy_files",
        "include_web_db_summary",
        "include_latest_verify_report",
    ]:
        support_bundle[key] = bool(support_bundle.get(key, True))
    try:
        support_bundle["max_log_files"] = int(support_bundle.get("max_log_files", 5))
    except Exception as exc:
        raise ArtifactLifecycleError(f"{path}: support_bundle.max_log_files должен быть целым числом") from exc
    if support_bundle["max_log_files"] < 0:
        raise ArtifactLifecycleError(f"{path}: support_bundle.max_log_files должен быть >= 0")
    cfg["support_bundle"] = support_bundle

    cfg["path"] = str(path)
    cfg["project_root"] = str(project_root_path)
    return cfg


def _relative_project_path(path: Path, *, roots: RuntimeRoots) -> str:
    for root in [roots.project_root, roots.artifacts_root, roots.web_storage.parent, roots.tmp_root.parent]:
        try:
            return path.resolve().relative_to(root).as_posix()
        except Exception:
            continue
    return path.resolve().as_posix()


def _absolute_family_root(*, roots: RuntimeRoots, family_root: str) -> Path:
    if family_root == "_tmp":
        return roots.tmp_root
    if family_root.startswith("artifacts/"):
        suffix = family_root.split("/", 1)[1]
        return (roots.artifacts_root / suffix).resolve()
    if family_root == "artifacts":
        return roots.artifacts_root
    if family_root.startswith("web_cabinet/storage/"):
        suffix = family_root.split("web_cabinet/storage/", 1)[1]
        return (roots.web_storage / suffix).resolve()
    if family_root == "web_cabinet/storage":
        return roots.web_storage
    return (roots.project_root / family_root).resolve()


def _is_protected(path: Path, *, roots: RuntimeRoots, policy: dict[str, Any]) -> bool:
    rel = _relative_project_path(path, roots=roots).strip("/")
    if not rel:
        return True
    for prefix in policy.get("protected_prefixes") or []:
        cleaned = str(prefix).strip().strip("/")
        if not cleaned:
            continue
        if rel == cleaned or rel.startswith(f"{cleaned}/"):
            return True
    if path.resolve() == roots.db_path.resolve():
        return True
    return False


def _sorted_by_mtime_desc(paths: Iterable[Path]) -> list[Path]:
    return sorted((p.resolve() for p in paths), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def _prune_summary(*, entries: list[Path], keep_last: int, dry_run: bool, roots: RuntimeRoots, policy: dict[str, Any]) -> dict[str, Any]:
    sorted_entries = _sorted_by_mtime_desc(entries)
    kept = sorted_entries[:keep_last] if keep_last > 0 else []
    candidates = [p for p in sorted_entries[keep_last:] if not _is_protected(p, roots=roots, policy=policy)]
    deleted: list[str] = []
    errors: list[dict[str, str]] = []
    if not dry_run:
        for path in candidates:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                deleted.append(str(path))
            except Exception as exc:
                errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    return {
        "root": _relative_project_path(entries[0].parent if entries else Path("."), roots=roots),
        "keep_last": int(keep_last),
        "total_entries": len(sorted_entries),
        "kept_paths": [str(p) for p in kept],
        "delete_candidates": [str(p) for p in candidates],
        "deleted_paths": deleted,
        "errors": errors,
        "dry_run": bool(dry_run),
    }


def _collect_family_entries(*, family_name: str, family: dict[str, Any], roots: RuntimeRoots, policy: dict[str, Any]) -> list[Path]:
    root = _absolute_family_root(roots=roots, family_root=str(family["root"]))
    if not root.exists():
        return []
    entries = [p.resolve() for p in root.glob(str(family.get("glob") or "*")) if p.exists()]
    filtered: list[Path] = []
    for path in entries:
        if _is_protected(path, roots=roots, policy=policy):
            continue
        filtered.append(path)
    return filtered


def collect_runtime_inventory(
    *,
    project_root: str | Path = ".",
    artifacts_root: str | Path | None = None,
    web_storage: str | Path | None = None,
    db_path: str | Path | None = None,
    tmp_root: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    roots = _resolve_runtime_roots(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        db_path=db_path,
        tmp_root=tmp_root,
    )
    policy = load_artifact_lifecycle_policy(project_root=roots.project_root, config_path=config_path)
    families_summary: dict[str, Any] = {}
    for family_name, family in (policy.get("runtime_families") or {}).items():
        root = _absolute_family_root(roots=roots, family_root=str(family["root"]))
        entries = _collect_family_entries(family_name=family_name, family=family, roots=roots, policy=policy)
        families_summary[family_name] = {
            "enabled": bool(family.get("enabled", True)),
            "root": str(root),
            "glob": str(family.get("glob") or "*"),
            "keep_last": int(family.get("keep_last") or 0),
            "entries": [str(p) for p in _sorted_by_mtime_desc(entries)],
        }
    return {
        "policy_path": str(policy["path"]),
        "project_root": str(roots.project_root),
        "artifacts_root": str(roots.artifacts_root),
        "web_storage": str(roots.web_storage),
        "db_path": str(roots.db_path),
        "families": families_summary,
    }


def cleanup_runtime_outputs(
    *,
    project_root: str | Path = ".",
    artifacts_root: str | Path | None = None,
    web_storage: str | Path | None = None,
    db_path: str | Path | None = None,
    tmp_root: str | Path | None = None,
    config_path: str | Path | None = None,
    dry_run: bool = True,
    include_data_versions: bool | None = None,
) -> dict[str, Any]:
    roots = _resolve_runtime_roots(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        db_path=db_path,
        tmp_root=tmp_root,
    )
    policy = load_artifact_lifecycle_policy(project_root=roots.project_root, config_path=config_path)
    if not policy.get("enabled", True):
        raise ArtifactLifecycleError("artifact lifecycle policy disabled")

    families_summary: dict[str, Any] = {}
    for family_name, family in (policy.get("runtime_families") or {}).items():
        root = _absolute_family_root(roots=roots, family_root=str(family["root"]))
        if not bool(family.get("enabled", True)):
            families_summary[family_name] = {
                "enabled": False,
                "root": str(root),
                "delete_candidates": [],
                "deleted_paths": [],
                "kept_paths": [],
                "errors": [],
                "dry_run": bool(dry_run),
            }
            continue
        entries = _collect_family_entries(family_name=family_name, family=family, roots=roots, policy=policy)
        summary = _prune_summary(
            entries=entries,
            keep_last=int(family.get("keep_last") or 0),
            dry_run=dry_run,
            roots=roots,
            policy=policy,
        )
        summary.update({"enabled": True, "root": str(root), "glob": str(family.get("glob") or "*")})
        families_summary[family_name] = summary

    include_dvs = bool(policy["backup_retention"].get("include_data_versions_default", False)) if include_data_versions is None else bool(include_data_versions)
    backup_summary: dict[str, Any]
    if bool(policy.get("backup_retention", {}).get("enabled", True)):
        backup_summary = apply_backup_retention(
            artifacts_root=roots.artifacts_root,
            web_storage=roots.web_storage,
            db_path=roots.db_path,
            project_root=roots.project_root,
            dry_run=dry_run,
            include_data_versions=include_dvs,
        )
    else:
        backup_summary = {
            "ok": True,
            "disabled": True,
            "dry_run": bool(dry_run),
            "backups": {"delete_candidates": [], "deleted_paths": [], "errors": []},
            "restore_snapshots": {"families": {}, "dry_run": bool(dry_run)},
            "data_versions": {"delete_candidates": [], "deleted_paths": [], "errors": [], "dry_run": bool(dry_run)},
        }

    batch_id = f"artifact_cleanup_{len(families_summary)}_{'dry' if dry_run else 'apply'}"
    summary = {
        "ok": True,
        "batch_id": batch_id,
        "dry_run": bool(dry_run),
        "policy_path": str(policy["path"]),
        "runtime_families": families_summary,
        "backup_retention": backup_summary,
        "artifacts_root": str(roots.artifacts_root),
        "web_storage": str(roots.web_storage),
        "tmp_root": str(roots.tmp_root),
    }
    _write_best_effort_audit(
        db_path=roots.db_path,
        action="artifact.cleanup",
        object_id=batch_id,
        after={
            "dry_run": bool(dry_run),
            "families_deleted": {
                family_name: len((family or {}).get("deleted_paths") or [])
                for family_name, family in families_summary.items()
            },
            "backups_deleted": len((backup_summary.get("backups") or {}).get("deleted_paths") or []),
        },
    )
    return summary


def _iter_nested_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        return []
    return sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.as_posix())


def _fixed_zip_write_bytes(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname)
    info.date_time = _FIXED_ZIP_DT
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


def _fixed_zip_write_file(zf: zipfile.ZipFile, path: Path, *, arcname: str) -> None:
    _fixed_zip_write_bytes(zf, arcname, path.read_bytes())


def _archive_entries_for_family(family_name: str, entries: Iterable[Path]) -> list[tuple[str, Path]]:
    archived: list[tuple[str, Path]] = []
    for entry in sorted((p.resolve() for p in entries), key=lambda p: p.as_posix()):
        if entry.is_file():
            archived.append((f"runtime/{family_name}/{entry.name}", entry))
            continue
        base = f"runtime/{family_name}/{entry.name}"
        for file_path in _iter_nested_files(entry):
            rel = file_path.relative_to(entry).as_posix()
            archived.append((f"{base}/{rel}", file_path))
    return archived


def archive_runtime_outputs(
    *,
    output_zip: str | Path,
    project_root: str | Path = ".",
    artifacts_root: str | Path | None = None,
    web_storage: str | Path | None = None,
    db_path: str | Path | None = None,
    tmp_root: str | Path | None = None,
    config_path: str | Path | None = None,
    families: Iterable[str] | None = None,
    scope: str = "all",
) -> dict[str, Any]:
    roots = _resolve_runtime_roots(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        db_path=db_path,
        tmp_root=tmp_root,
    )
    policy = load_artifact_lifecycle_policy(project_root=roots.project_root, config_path=config_path)
    inventory = collect_runtime_inventory(
        project_root=roots.project_root,
        artifacts_root=roots.artifacts_root,
        web_storage=roots.web_storage,
        db_path=roots.db_path,
        tmp_root=roots.tmp_root,
        config_path=policy["path"],
    )

    selected_families = list(families or ["verify_reports", "ci_scratch", "tmp_workdirs", "web_logs"])
    unknown = [name for name in selected_families if name not in inventory["families"]]
    if unknown:
        raise ArtifactLifecycleError(f"unknown lifecycle families: {unknown}")
    if scope not in {"all", "delete_candidates"}:
        raise ArtifactLifecycleError("archive scope must be one of: all, delete_candidates")

    output_path = Path(output_zip).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "schema": "genomeai.runtime_archive.v1",
        "scope": scope,
        "families": selected_families,
        "policy_path": str(policy["path"]),
        "entries": [],
    }
    archive_items: list[tuple[str, Path]] = []
    for family_name in selected_families:
        family = policy["runtime_families"][family_name]
        entries = _collect_family_entries(family_name=family_name, family=family, roots=roots, policy=policy)
        if scope == "delete_candidates":
            entries = _sorted_by_mtime_desc(entries)[int(family.get("keep_last") or 0) :]
        archive_items.extend(_archive_entries_for_family(family_name, entries))

    with zipfile.ZipFile(output_path, "w") as zf:
        for arcname, file_path in sorted(archive_items, key=lambda item: item[0]):
            _fixed_zip_write_file(zf, file_path, arcname=arcname)
            manifest["entries"].append({"path": arcname, "size": int(file_path.stat().st_size)})
        _fixed_zip_write_bytes(zf, "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    _write_best_effort_audit(
        db_path=roots.db_path,
        action="artifact.archive",
        object_id=output_path.stem,
        after={"output_zip": str(output_path), "entries": len(manifest["entries"]), "scope": scope},
    )
    return {
        "ok": True,
        "archive_zip": str(output_path),
        "entry_count": len(manifest["entries"]),
        "families": selected_families,
        "scope": scope,
    }


def _latest_verify_report_dir(artifacts_root: Path) -> Optional[Path]:
    root = artifacts_root / "_verify_refactor"
    if not root.exists():
        return None
    candidates = [p for p in root.glob("verify_*") if p.is_dir()]
    if not candidates:
        return None
    return _sorted_by_mtime_desc(candidates)[0]


def _collect_web_db_summary(db_path: Path) -> dict[str, Any]:
    return {"backend": "postgres", "note": "sqlite not used"}


def build_support_bundle(
    *,
    output_zip: str | Path,
    project_root: str | Path = ".",
    artifacts_root: str | Path | None = None,
    web_storage: str | Path | None = None,
    db_path: str | Path | None = None,
    tmp_root: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    roots = _resolve_runtime_roots(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        db_path=db_path,
        tmp_root=tmp_root,
    )
    policy = load_artifact_lifecycle_policy(project_root=roots.project_root, config_path=config_path)
    support_cfg = dict(policy.get("support_bundle") or {})
    output_path = Path(output_zip).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    runtime = resolve_runtime_storage_settings(project_root=roots.project_root, storage_dir=roots.web_storage, sqlite_db_path=roots.db_path)
    manifest: dict[str, Any] = {
        "schema": "genomeai.support_bundle.v1",
        "policy_path": str(policy["path"]),
        "runtime_storage_backend": runtime.backend,
        "entries": [],
    }
    extra_json_payloads: list[tuple[str, bytes]] = []
    extra_file_paths: list[tuple[str, Path]] = []

    if support_cfg.get("include_environment_snapshot", True):
        extra_json_payloads.append(
            (
                "diagnostics/environment_snapshot.json",
                (json.dumps(build_test_environment_snapshot(), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        )

    if support_cfg.get("include_inventory", True):
        inventory = collect_runtime_inventory(
            project_root=roots.project_root,
            artifacts_root=roots.artifacts_root,
            web_storage=roots.web_storage,
            db_path=roots.db_path,
            tmp_root=roots.tmp_root,
            config_path=policy["path"],
        )
        for volatile_family in ["support_bundles", "runtime_archives"]:
            family = (inventory.get("families") or {}).get(volatile_family)
            if isinstance(family, dict):
                family["entries"] = []
        extra_json_payloads.append(
            (
                "diagnostics/runtime_inventory.json",
                (json.dumps(inventory, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        )

    extra_json_payloads.append(
        (
            "diagnostics/runtime_storage_summary.json",
            (json.dumps(runtime_storage_diagnostics(runtime).as_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    )
    extra_json_payloads.append(
        (
            "diagnostics/runtime_state_summary.json",
            (json.dumps(build_runtime_state_summary_payload(), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    )
    extra_json_payloads.append(
        (
            "diagnostics/auth_diagnostics.json",
            (json.dumps(auth_storage_diagnostics().as_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    )
    extra_json_payloads.append(
        (
            "diagnostics/queue_runtime_summary.json",
            (json.dumps(build_queue_runtime_summary_payload(queue_names=["default"]), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    )
    extra_json_payloads.append(
        (
            "diagnostics/backup_metadata.json",
            (json.dumps(build_adult_backup_metadata_summary(artifacts_root=roots.artifacts_root), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    )
    extra_json_payloads.append(
        (
            "diagnostics/artifact_integrity_summary.json",
            (json.dumps(build_artifact_integrity_summary(artifacts_root=roots.artifacts_root), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    )

    maintenance_dir = roots.artifacts_root / "system" / "maintenance"
    for raw_name in ["latest_backup_metadata.json", "latest_restore_metadata.json"]:
        raw_path = maintenance_dir / raw_name
        if raw_path.exists() and raw_path.is_file():
            extra_file_paths.append((f"maintenance/{raw_name}", raw_path))

    if support_cfg.get("include_web_db_summary", True) and runtime.backend == "sqlite":
        extra_json_payloads.append(
            (
                "diagnostics/web_db_summary.json",
                (json.dumps(_collect_web_db_summary(roots.db_path), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
        )

    if support_cfg.get("include_policy_files", True):
        policy_path = Path(str(policy["path"]))
        if policy_path.exists():
            extra_file_paths.append(("configs/artifact_lifecycle_v1.yaml", policy_path))
        backup_cfg_path = roots.project_root / "configs" / "ops" / "backup_retention_v1.yaml"
        if backup_cfg_path.exists():
            extra_file_paths.append(("configs/backup_retention_v1.yaml", backup_cfg_path))

    if support_cfg.get("include_latest_verify_report", True):
        verify_dir = _latest_verify_report_dir(roots.artifacts_root)
        if verify_dir is not None:
            for name in ["verify_report.json", "verify_report.md"]:
                path = verify_dir / name
                if path.exists():
                    extra_file_paths.append((f"verify/{verify_dir.name}/{name}", path))

    max_log_files = int(support_cfg.get("max_log_files", 5))
    if max_log_files > 0:
        logs_dir = roots.web_storage / "logs"
        log_files = _sorted_by_mtime_desc([p for p in logs_dir.glob("*.log") if p.is_file()])[:max_log_files] if logs_dir.exists() else []
        for path in sorted(log_files, key=lambda item: item.name):
            extra_file_paths.append((f"logs/{path.name}", path))

    with zipfile.ZipFile(output_path, "w") as zf:
        for arcname, payload in sorted(extra_json_payloads, key=lambda item: item[0]):
            _fixed_zip_write_bytes(zf, arcname, payload)
            manifest["entries"].append({"path": arcname, "size": len(payload)})
        for arcname, path in sorted(extra_file_paths, key=lambda item: item[0]):
            _fixed_zip_write_file(zf, path, arcname=arcname)
            manifest["entries"].append({"path": arcname, "size": int(path.stat().st_size)})
        _fixed_zip_write_bytes(zf, "manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    _write_best_effort_audit(
        db_path=roots.db_path,
        action="artifact.support_bundle",
        object_id=output_path.stem,
        after={"output_zip": str(output_path), "entries": len(manifest["entries"]), "policy_path": str(policy["path"])} ,
    )
    return {
        "ok": True,
        "bundle_zip": str(output_path),
        "entry_count": len(manifest["entries"]),
        "policy_path": str(policy["path"]),
    }


__all__ = [
    "ArtifactLifecycleError",
    "RuntimeRoots",
    "archive_runtime_outputs",
    "build_support_bundle",
    "cleanup_runtime_outputs",
    "collect_runtime_inventory",
    "load_artifact_lifecycle_policy",
]
