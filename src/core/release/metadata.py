from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_SOURCE_DATE_EPOCH = 315532800
_DEFAULT_RELEASE_CHANNEL = "dev"
_DEFAULT_BUILD_STAMP = "local"
_METADATA_RELATIVE_CANDIDATES: tuple[str, ...] = (
    "release/release_stamp.json",
    "installers/releases/release_stamp.json",
)


class ReleaseMetadataError(ValueError):
    """Human-readable release metadata/configuration error."""


def _read_project_version(project_root: Path) -> str:
    candidates = [project_root / "pyproject.toml", project_root.parent / "pyproject.toml"]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version") and "=" in stripped:
                value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    return "0.0.1"


def _int_or_none(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception as exc:
        raise ReleaseMetadataError(f"source_date_epoch/build number должен быть целым числом, получено: {raw}") from exc


def _iso_from_epoch(epoch: int | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).replace(microsecond=0).isoformat()


def _json_load_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ReleaseMetadataError(f"{path}: ожидался JSON-объект")
    return raw


def _discover_metadata_path(project_root: Path, explicit_path: str | Path | None = None) -> Path | None:
    if explicit_path is not None:
        return Path(explicit_path).resolve()
    env_path = str(os.environ.get("GENOMEAI_RELEASE_METADATA") or "").strip()
    if env_path:
        return Path(env_path).resolve()
    for rel in _METADATA_RELATIVE_CANDIDATES:
        candidate = (project_root / rel).resolve()
        if candidate.exists():
            return candidate
    return None


def load_release_metadata(
    *,
    project_root: str | Path = ".",
    metadata_path: str | Path | None = None,
    build_stamp: str | None = None,
    release_channel: str | None = None,
    source_date_epoch: int | None = None,
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    discovered_metadata_path = _discover_metadata_path(project_root_path, explicit_path=metadata_path)
    embedded = _json_load_if_exists(discovered_metadata_path) if discovered_metadata_path else {}
    version = str(embedded.get("version") or _read_project_version(project_root_path)).strip() or "0.0.1"

    epoch = source_date_epoch
    if epoch is None:
        epoch = _int_or_none(embedded.get("source_date_epoch"))
    if epoch is None:
        epoch = _int_or_none(os.environ.get("SOURCE_DATE_EPOCH"))
    if epoch is None:
        epoch = _DEFAULT_SOURCE_DATE_EPOCH

    channel = (
        str(release_channel or embedded.get("release_channel") or os.environ.get("GENOMEAI_RELEASE_CHANNEL") or _DEFAULT_RELEASE_CHANNEL)
        .strip()
        or _DEFAULT_RELEASE_CHANNEL
    )
    stamp = (
        str(build_stamp or embedded.get("build_stamp") or os.environ.get("GENOMEAI_BUILD_STAMP") or _DEFAULT_BUILD_STAMP)
        .strip()
        or _DEFAULT_BUILD_STAMP
    )
    commit = str(embedded.get("git_commit") or os.environ.get("GENOMEAI_GIT_COMMIT") or "").strip() or None
    build_number = _int_or_none(embedded.get("build_number") or os.environ.get("GENOMEAI_BUILD_NUMBER"))
    metadata = {
        "schema": "genomeai.release.metadata.v1",
        "version": version,
        "build_stamp": stamp,
        "release_channel": channel,
        "source_date_epoch": int(epoch),
        "build_time_utc": _iso_from_epoch(epoch),
        "git_commit": commit,
        "build_number": build_number,
        "project_root": str(project_root_path),
        "metadata_path": str(discovered_metadata_path) if discovered_metadata_path else None,
        "display": f"GenomeAI AgroAnimals {version} ({channel}/{stamp})",
    }
    return metadata


def render_release_stamp(metadata: dict[str, Any]) -> str:
    version = str(metadata.get("version") or "0.0.1")
    channel = str(metadata.get("release_channel") or _DEFAULT_RELEASE_CHANNEL)
    build_stamp = str(metadata.get("build_stamp") or _DEFAULT_BUILD_STAMP)
    return f"v{version} · {channel}/{build_stamp}"


__all__ = ["ReleaseMetadataError", "load_release_metadata", "render_release_stamp"]
