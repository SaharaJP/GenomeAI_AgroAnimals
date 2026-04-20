from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import yaml

from .metadata import load_release_metadata

_DEFAULT_RELEASE_PACKAGING_POLICY: dict[str, Any] = {
    "version": 1,
    "archive_dir": "installers/releases",
    "package_basename": "genomeai_agroanimals_release",
    "root_dir_template": "genomeai_agroanimals_{version}_{build_stamp}",
    "include_paths": [
        ".dockerignore",
        ".gitignore",
        "README.md",
        "pyproject.toml",
        "ci",
        "configs",
        "data/examples",
        "deploy",
        "docs",
        "genomeai",
        "installers",
        "scripts",
        "src",
        "mobile_android",
        "web_app",
        "web_cabinet",
    ],
    "exclude_globs": [
        ".git/**",
        ".venv/**",
        "**/__pycache__/**",
        "**/*.pyc",
        "**/*.pyo",
        ".pytest_cache/**",
        ".mypy_cache/**",
        ".ruff_cache/**",
        "artifacts/**",
        "_tmp/**",
        "build/**",
        "dist/**",
        "installers/releases/**",
        "web_cabinet/storage/**",
        "runtime/**",
    ],
    "embedded_metadata_path": "release/release_stamp.json",
    "embedded_manifest_path": "release/manifest.json",
    "embedded_checksums_path": "release/SHA256SUMS",
}


class ReleasePackagingError(ValueError):
    """Human-readable release packaging error."""


@dataclass(frozen=True)
class PackageFile:
    relative_path: str
    source_path: Path | None
    content_bytes: bytes


_FIXED_ZIP_EPOCH = 315532800


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _read_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ReleasePackagingError(f"{path}: ожидался YAML-объект верхнего уровня")
    return raw


def load_release_packaging_policy(*, project_root: str | Path = ".", config_path: str | Path | None = None) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    path = Path(config_path).resolve() if config_path is not None else (project_root_path / "configs" / "ops" / "release_packaging_v1.yaml").resolve()
    raw = _read_yaml_dict(path)
    cfg = _deep_merge(_json_clone(_DEFAULT_RELEASE_PACKAGING_POLICY), raw)
    try:
        cfg["version"] = int(cfg.get("version", 1))
    except Exception as exc:
        raise ReleasePackagingError(f"{path}: version должен быть целым числом") from exc
    for key in ["archive_dir", "package_basename", "root_dir_template", "embedded_metadata_path", "embedded_manifest_path", "embedded_checksums_path"]:
        value = str(cfg.get(key) or "").strip().strip("/")
        if not value:
            raise ReleasePackagingError(f"{path}: {key} должен быть непустой строкой")
        cfg[key] = value
    include_paths = cfg.get("include_paths") or []
    if not isinstance(include_paths, list) or not include_paths:
        raise ReleasePackagingError(f"{path}: include_paths должен быть непустым списком")
    cfg["include_paths"] = [str(item).strip().strip("/") for item in include_paths if str(item).strip()]
    exclude_globs = cfg.get("exclude_globs") or []
    if not isinstance(exclude_globs, list):
        raise ReleasePackagingError(f"{path}: exclude_globs должен быть списком")
    cfg["exclude_globs"] = [str(item).strip() for item in exclude_globs if str(item).strip()]
    cfg["path"] = str(path)
    cfg["project_root"] = str(project_root_path)
    return cfg


def _is_excluded(rel_path: str, exclude_globs: Iterable[str]) -> bool:
    value = rel_path.replace(os.sep, "/")
    return any(fnmatch.fnmatch(value, str(pattern).replace(os.sep, "/")) for pattern in exclude_globs)


def _iter_included_files(*, project_root: Path, policy: dict[str, Any]) -> list[Path]:
    seen: dict[str, Path] = {}
    for raw in policy.get("include_paths") or []:
        rel = str(raw).strip().strip("/")
        if not rel:
            continue
        path = (project_root / rel).resolve()
        if not path.exists():
            continue
        if path.is_file():
            rel_file = path.relative_to(project_root).as_posix()
            if not _is_excluded(rel_file, policy.get("exclude_globs") or []):
                seen[rel_file] = path
            continue
        for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
            rel_file = file_path.relative_to(project_root).as_posix()
            if _is_excluded(rel_file, policy.get("exclude_globs") or []):
                continue
            seen[rel_file] = file_path.resolve()
    if not seen:
        raise ReleasePackagingError("release packaging policy selected zero files")
    return [seen[key] for key in sorted(seen)]


def _slug(value: str) -> str:
    safe = []
    for char in str(value):
        safe.append(char if char.isalnum() or char in {"-", "_", "."} else "-")
    text = "".join(safe).strip("-._")
    return text or "release"


def _zip_datetime_from_epoch(epoch: int | None) -> tuple[int, int, int, int, int, int]:
    import datetime as _dt
    ts = int(epoch or _FIXED_ZIP_EPOCH)
    if ts < _FIXED_ZIP_EPOCH:
        ts = _FIXED_ZIP_EPOCH
    dt = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_zip_bytes(zf: zipfile.ZipFile, name: str, payload: bytes, *, date_time: tuple[int, int, int, int, int, int]) -> None:
    info = zipfile.ZipInfo(name, date_time=date_time)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    zf.writestr(info, payload)


def build_release_package(*, project_root: str | Path = ".", out_path: str | Path | None = None, config_path: str | Path | None = None, build_stamp: str | None = None, release_channel: str | None = None, source_date_epoch: int | None = None) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    policy = load_release_packaging_policy(project_root=project_root_path, config_path=config_path)
    metadata = load_release_metadata(project_root=project_root_path, build_stamp=build_stamp, release_channel=release_channel, source_date_epoch=source_date_epoch)
    root_dir_name = policy["root_dir_template"].format(version=_slug(str(metadata.get("version") or "0.0.1")), build_stamp=_slug(str(metadata.get("build_stamp") or "local")), release_channel=_slug(str(metadata.get("release_channel") or "dev")))
    archive_dir = (project_root_path / policy["archive_dir"]).resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    if out_path is None:
        archive_name = f"{policy['package_basename']}_{_slug(str(metadata['version']))}_{_slug(str(metadata['build_stamp']))}.zip"
        archive_path = archive_dir / archive_name
    else:
        archive_path = Path(out_path).resolve()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
    files = _iter_included_files(project_root=project_root_path, policy=policy)
    package_files = [PackageFile(relative_path=path.relative_to(project_root_path).as_posix(), source_path=path, content_bytes=path.read_bytes()) for path in files]
    embedded_metadata_payload = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    package_files.append(PackageFile(relative_path=policy["embedded_metadata_path"], source_path=None, content_bytes=embedded_metadata_payload))
    package_files = sorted(package_files, key=lambda item: item.relative_path)
    manifest_files = []
    checksums_lines = []
    total_bytes = 0
    for item in package_files:
        checksum = _sha256_bytes(item.content_bytes)
        total_bytes += len(item.content_bytes)
        manifest_files.append({"path": item.relative_path, "size": len(item.content_bytes), "sha256": checksum, "source": item.source_path.relative_to(project_root_path).as_posix() if item.source_path is not None else "generated"})
        checksums_lines.append(f"{checksum}  {item.relative_path}")
    manifest = {"schema": "genomeai.release.manifest.v1", "version": 1, "policy_version": int(policy.get("version", 1)), "root_dir": root_dir_name, "metadata": metadata, "files": manifest_files, "file_count": len(manifest_files), "payload_bytes": total_bytes}
    manifest_payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    checksums_payload = ("\n".join(checksums_lines) + "\n").encode("utf-8")
    zip_date_time = _zip_datetime_from_epoch(int(metadata.get("source_date_epoch") or _FIXED_ZIP_EPOCH))
    with zipfile.ZipFile(archive_path, "w") as zf:
        for item in package_files:
            _write_zip_bytes(zf, f"{root_dir_name}/{item.relative_path}", item.content_bytes, date_time=zip_date_time)
        _write_zip_bytes(zf, f"{root_dir_name}/{policy['embedded_manifest_path']}", manifest_payload, date_time=zip_date_time)
        _write_zip_bytes(zf, f"{root_dir_name}/{policy['embedded_checksums_path']}", checksums_payload, date_time=zip_date_time)
    sidecar_manifest_path = archive_path.with_suffix(".manifest.json")
    sidecar_checksums_path = archive_path.with_suffix(".sha256")
    archive_checksum = _sha256_file(archive_path)
    sidecar_manifest_path.write_bytes(manifest_payload)
    sidecar_checksums_path.write_text(f"{archive_checksum}  {archive_path.name}\n", encoding="utf-8")
    return {"ok": True, "archive_path": str(archive_path), "manifest_path": str(sidecar_manifest_path), "archive_checksum_path": str(sidecar_checksums_path), "archive_sha256": archive_checksum, "metadata": metadata, "policy": {"path": policy.get("path"), "version": policy.get("version"), "include_paths": list(policy.get("include_paths") or []), "exclude_globs": list(policy.get("exclude_globs") or [])}, "file_count": len(manifest_files), "root_dir": root_dir_name}


def verify_release_manifest(*, extracted_root: str | Path, manifest_rel_path: str = "release/manifest.json") -> dict[str, Any]:
    extracted_root_path = Path(extracted_root).resolve()
    manifest_path = (extracted_root_path / manifest_rel_path).resolve()
    if not manifest_path.exists():
        raise ReleasePackagingError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files") or []
    if not isinstance(files, list):
        raise ReleasePackagingError(f"{manifest_path}: files должен быть списком")
    mismatches = []
    verified = 0
    for item in files:
        if not isinstance(item, dict):
            mismatches.append("manifest entry is not an object")
            continue
        rel = str(item.get("path") or "").strip()
        expected = str(item.get("sha256") or "").strip()
        target = (extracted_root_path / rel).resolve()
        if not rel or not target.exists() or not target.is_file():
            mismatches.append(f"missing file: {rel}")
            continue
        actual = _sha256_file(target)
        if actual != expected:
            mismatches.append(f"checksum mismatch: {rel}")
            continue
        verified += 1
    return {"ok": not mismatches, "manifest_path": str(manifest_path), "verified_files": verified, "mismatches": mismatches, "metadata": manifest.get("metadata") or {}, "file_count": len(files)}


def _find_single_root_dir(extract_dir: Path) -> Path:
    dirs = [p for p in extract_dir.iterdir() if p.is_dir()]
    if len(dirs) != 1:
        raise ReleasePackagingError(f"ожидалась одна корневая директория в archive, найдено: {len(dirs)}")
    return dirs[0].resolve()


def run_release_package_smoke(*, archive_path: str | Path, python_executable: str | None = None) -> dict[str, Any]:
    archive_path_obj = Path(archive_path).resolve()
    if not archive_path_obj.exists():
        raise ReleasePackagingError(f"archive not found: {archive_path_obj}")
    timings: dict[str, float] = {}
    report: dict[str, Any] = {"archive_path": str(archive_path_obj), "steps": [], "ok": False}
    py_exec = python_executable or sys.executable
    temp_root = Path(tempfile.mkdtemp(prefix="genomeai_release_smoke_"))
    try:
        started = perf_counter()
        with zipfile.ZipFile(archive_path_obj) as zf:
            zf.extractall(temp_root)
        timings["extract"] = max(0.0, perf_counter() - started)
        extracted_root = _find_single_root_dir(temp_root)
        started = perf_counter()
        manifest_report = verify_release_manifest(extracted_root=extracted_root)
        timings["verify_manifest"] = max(0.0, perf_counter() - started)
        if not manifest_report.get("ok"):
            raise ReleasePackagingError("manifest verification failed: " + "; ".join(manifest_report.get("mismatches") or []))
        env = os.environ.copy()
        existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
        env["PYTHONPATH"] = str(extracted_root / "src") + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env["GENOMEAI_PROJECT_ROOT"] = str(extracted_root)
        env["GENOMEAI_RELEASE_METADATA"] = str(extracted_root / "release" / "release_stamp.json")
        env["GENOMEAI_ARTIFACTS_ROOT"] = str(extracted_root / "_tmp" / "release_smoke_artifacts")
        env["GENOMEAI_WEB_STORAGE"] = str(extracted_root / "_tmp" / "release_smoke_web_storage")
        env["GENOMEAI_WEB_DISABLE_WORKER"] = "1"
        started = perf_counter()
        cli_proc = subprocess.run([py_exec, "-m", "genomeai.cli", "version", "--format", "json"], cwd=str(extracted_root), env=env, check=False, capture_output=True, text=True)
        timings["cli_version"] = max(0.0, perf_counter() - started)
        if cli_proc.returncode != 0:
            raise ReleasePackagingError(f"packaged CLI version failed: {cli_proc.stderr or cli_proc.stdout}")
        cli_json = json.loads(cli_proc.stdout)
        started = perf_counter()
        inline = (
            "import json; "
            "from fastapi.testclient import TestClient; "
            "from web_cabinet.app import app; "
            "client=TestClient(app); "
            "health=client.get('/healthz'); "
            "release=client.get('/api/release'); "
            "login=client.get('/login'); "
            "payload={"
            "'health_status': health.status_code,"
            "'release_status': release.status_code,"
            "'login_status': login.status_code,"
            "'release': release.json(),"
            "'version_header': health.headers.get('X-GenomeAI-Version'),"
            "'build_header': health.headers.get('X-GenomeAI-Build-Stamp'),"
            "'login_contains_version': 'GenomeAI AgroAnimals' in login.text and 'v' in login.text"
            "}; "
            "print(json.dumps(payload, ensure_ascii=False))"
        )
        api_check = subprocess.run([py_exec, "-c", inline], cwd=str(extracted_root), env=env, check=False, capture_output=True, text=True)
        timings["api_release"] = max(0.0, perf_counter() - started)
        if api_check.returncode != 0:
            raise ReleasePackagingError(f"packaged API smoke failed: {api_check.stderr or api_check.stdout}")
        api_json = json.loads(api_check.stdout)
        if int(api_json.get("health_status") or 0) != 200:
            raise ReleasePackagingError(f"/healthz returned {api_json.get('health_status')}")
        if int(api_json.get("release_status") or 0) != 200:
            raise ReleasePackagingError(f"/api/release returned {api_json.get('release_status')}")
        if int(api_json.get("login_status") or 0) != 200:
            raise ReleasePackagingError(f"/login returned {api_json.get('login_status')}")
        report.update({"ok": True, "extracted_root": str(extracted_root), "manifest": manifest_report, "cli": cli_json, "api": api_json, "timings": timings})
        return report
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def render_release_cli_lines(result: dict[str, Any]) -> list[str]:
    lines = ["RELEASE_BUILD_OK" if result.get("ok") else "RELEASE_BUILD_FAILED"]
    lines.append(f"archive_path={result.get('archive_path')}")
    lines.append(f"manifest_path={result.get('manifest_path')}")
    lines.append(f"archive_sha256={result.get('archive_sha256')}")
    lines.append(f"file_count={result.get('file_count')}")
    metadata = result.get("metadata") or {}
    lines.append(f"version={metadata.get('version')}")
    lines.append(f"build_stamp={metadata.get('build_stamp')}")
    lines.append(f"release_channel={metadata.get('release_channel')}")
    return lines


def render_release_smoke_cli_lines(result: dict[str, Any]) -> list[str]:
    lines = ["RELEASE_SMOKE_OK" if result.get("ok") else "RELEASE_SMOKE_FAILED"]
    lines.append(f"archive_path={result.get('archive_path')}")
    lines.append(f"manifest_ok={bool((result.get('manifest') or {}).get('ok'))}")
    cli = result.get("cli") or {}
    lines.append(f"cli_version={cli.get('version')}")
    lines.append(f"cli_build_stamp={cli.get('build_stamp')}")
    api = result.get("api") or {}
    lines.append(f"api_health_status={api.get('health_status')}")
    lines.append(f"api_release_status={api.get('release_status')}")
    for key, value in sorted((result.get("timings") or {}).items()):
        lines.append(f"timing_{key}={value:.3f}")
    return lines


__all__ = ["ReleasePackagingError", "build_release_package", "load_release_packaging_policy", "render_release_cli_lines", "render_release_smoke_cli_lines", "run_release_package_smoke", "verify_release_manifest"]
