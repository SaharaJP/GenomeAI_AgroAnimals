from __future__ import annotations

import hashlib
import json
import os
import random
import string
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from core.common.time import utc_isoformat, utc_timestamp_compact
from core.domain import RunMeta, RunMetadata, RunVersions, run_metadata_to_legacy_dict


def _utc_now_iso() -> str:
    return utc_isoformat()


def generate_run_id(prefix: str = "run") -> str:
    ts = utc_timestamp_compact()
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{ts}_{suffix}"


def compute_data_version(input_path: Path, include_globs: Optional[List[str]] = None) -> str:
    """Deterministic sha256 for a directory or file set."""
    input_path = input_path.resolve()
    h = hashlib.sha256()

    if input_path.is_file():
        h.update(input_path.read_bytes())
        return h.hexdigest()

    patterns = include_globs or ["*.csv"]
    files: List[Path] = []
    for pat in patterns:
        files.extend(input_path.rglob(pat))
    files = sorted([f for f in files if f.is_file()], key=lambda p: str(p.relative_to(input_path)).lower())

    for f in files:
        rel = str(f.relative_to(input_path)).replace(os.sep, "/")
        fh = hashlib.sha256(f.read_bytes()).hexdigest()
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
        h.update(fh.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def init_run_dir(artifacts_root: Path, run_id: str) -> Path:
    run_dir = artifacts_root / "runs" / run_id
    (run_dir / "versions").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bootstrap_run(artifacts_root: Path, run_id: Optional[str] = None) -> Tuple[str, Path]:
    rid = run_id or generate_run_id()
    run_dir = init_run_dir(artifacts_root, rid)

    meta = RunMeta(run_id=rid, created_at_utc=_utc_now_iso())
    versions = RunVersions(
        data_version=None,
        qc_run=None,
        model_version=None,
        scoring_run=None,
        report_version=None,
        decision_log=str((run_dir / "logs" / "decision_log.jsonl").resolve()),
    )

    write_json(run_dir / "metadata.json", run_metadata_to_legacy_dict(meta))
    write_json(run_dir / "versions.json", asdict(versions))

    (run_dir / "logs" / "decision_log.jsonl").write_text("", encoding="utf-8")
    return rid, run_dir


# --- Target run layout (T0-03) -------------------------------------------------

def get_run_root(*, artifacts_root: Path, data_version: str, run_id: str) -> Path:
    """Return Target run root: artifacts/<data_version>/runs/<run_id>"""
    artifacts_root = Path(artifacts_root).resolve()
    return artifacts_root / data_version / "runs" / run_id

def ensure_run_dir(artifacts_root: str | Path, data_version: str, run_id: str) -> Path:
    """Create and return Target run root: artifacts/<data_version>/runs/<run_id>."""
    run_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=run_id)
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def write_run_manifest(*, run_root: Path, manifest: dict) -> Path:
    """Write run_manifest.json into run_root."""
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    path = run_root / "run_manifest.json"
    write_json(path, manifest)
    return path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksums(*, run_root: Path, include_subdirs: list[str] | None = None) -> Path:
    """Compute sha256 for files under run_root (optionally selected subdirs) and write checksums.json."""
    run_root = Path(run_root)
    checksums: dict[str, str] = {}
    if include_subdirs:
        roots = [run_root / s for s in include_subdirs]
    else:
        roots = [run_root]
    for r in roots:
        if not r.exists():
            continue
        for p in r.rglob("*"):
            if p.is_file() and p.name not in {"checksums.json"}:
                rel = str(p.relative_to(run_root))
                checksums[rel] = _sha256_file(p)
    path = run_root / "checksums.json"
    write_json(path, {"sha256": checksums, "generated_at": _utc_now_iso()})
    return path


def copy_tree_into_run(*, src_dir: Path, run_root: Path, subdir: str) -> Path:
    """Copy artifacts from src_dir into run_root/<subdir>/ (best-effort)."""
    src_dir = Path(src_dir)
    dst_dir = Path(run_root) / subdir
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        return dst_dir
    for p in src_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src_dir)
            out = dst_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            # overwrite to keep deterministic reruns
            out.write_bytes(p.read_bytes())
    return dst_dir
