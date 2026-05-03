from __future__ import annotations

from pathlib import Path
from typing import Iterable

from core.application.ml_artifacts import (
    list_model_entries as _list_model_entries,
    list_model_versions as _list_model_versions,
    list_scoring_entries as _list_scoring_entries,
    list_scoring_runs as _list_scoring_runs,
)


def save_upload_limited(fileobj, *, dest: Path, max_bytes: int, chunk_bytes: int = 1024 * 1024) -> int:
    """Save an uploaded file-like object to dest with a hard size limit.

    Returns number of written bytes.
    Raises ValueError if size exceeds the limit.
    """
    written = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        while True:
            chunk = fileobj.read(chunk_bytes)
            if not chunk:
                break
            written += len(chunk)
            if max_bytes > 0 and written > max_bytes:
                raise ValueError("upload_too_large")
            f.write(chunk)
    return written


def list_subdirs(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted([p.name for p in path.iterdir() if p.is_dir()])


def list_data_versions(artifacts_root: Path) -> list[str]:
    # Do not treat operational folders as data_version.
    # Older offline pipelines may also create artifacts/runs/ (legacy run layout).
    reserved = {"runs", "backups", "legacy", "tmp"}
    return [d for d in list_subdirs(artifacts_root) if d not in reserved and not d.startswith(".")]


def list_qc_runs(artifacts_root: Path, data_version: str) -> list[str]:
    return list_subdirs(artifacts_root / data_version / "qc")


def list_model_versions(artifacts_root: Path, data_version: str) -> list[str]:
    return _list_model_versions(artifacts_root=artifacts_root, data_version=data_version)


def list_model_entries(artifacts_root: Path, data_version: str) -> list[dict]:
    return _list_model_entries(artifacts_root=artifacts_root, data_version=data_version)


def list_scoring_runs(artifacts_root: Path, data_version: str) -> list[str]:
    return _list_scoring_runs(artifacts_root=artifacts_root, data_version=data_version)


def list_scoring_entries(artifacts_root: Path, data_version: str) -> list[dict]:
    return _list_scoring_entries(artifacts_root=artifacts_root, data_version=data_version)


def list_report_versions(artifacts_root: Path, data_version: str) -> list[str]:
    return list_subdirs(artifacts_root / data_version / "reports")


def list_repro_runs(artifacts_root: Path, data_version: str) -> list[str]:
    """List reproduction runs (T5-01).

    Layout: artifacts/<dv>/repro/runs/<repro_run>/
    """
    return list_subdirs(artifacts_root / data_version / "repro" / "runs")


def safe_join(base: Path, relative: str) -> Path:
    """Prevent path traversal for downloads."""
    rel = Path(relative)
    p = (base / rel).resolve()
    base_res = base.resolve()
    if base_res not in p.parents and p != base_res:
        raise ValueError("Unsafe path")
    return p
