from __future__ import annotations

from pathlib import Path
from typing import List, Optional


def qc2_run_roots(*, artifacts_root: str | Path, data_version: str) -> List[Path]:
    """Return supported QC2 run roots in canonical priority order.

    Preferred layout after T15-06 refactor:
        artifacts/<data_version>/qc2/<qc_run>

    Backward-compatible legacy layout:
        artifacts/qc2/<data_version>/<qc_run>
    """
    base = Path(artifacts_root)
    roots = [base / data_version / "qc2", base / "qc2" / data_version]
    out: List[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def find_latest_qc2_run_dir(*, artifacts_root: str | Path, data_version: str) -> Optional[Path]:
    """Resolve the latest QC2 run directory across supported layouts.

    Canonical layout has priority over legacy layout. Within the selected root,
    the latest lexicographically sorted run directory is returned to preserve the
    existing qc_run naming contract (`qc2_YYYYMMDD_HHMMSS_*`).
    """
    for base in qc2_run_roots(artifacts_root=artifacts_root, data_version=data_version):
        if not base.exists():
            continue
        runs = sorted([p for p in base.iterdir() if p.is_dir()])
        if runs:
            return runs[-1]
    return None


def find_latest_qc2_run(*, artifacts_root: str | Path, data_version: str) -> Optional[str]:
    run_dir = find_latest_qc2_run_dir(artifacts_root=artifacts_root, data_version=data_version)
    return run_dir.name if run_dir is not None else None


def resolve_qc2_out_dir(*, artifacts_root: str | Path, data_version: str, qc_run: str) -> Optional[Path]:
    """Resolve a concrete qc2 run directory across canonical and legacy layouts.

    Canonical layout is preferred if both locations exist.
    """
    for base in qc2_run_roots(artifacts_root=artifacts_root, data_version=data_version):
        out_dir = base / qc_run
        if out_dir.exists():
            return out_dir
    return None
