from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def perform_verify_refactor(
    *,
    project_root: Path,
    golden_root: Path,
    scenario_names: Iterable[str] | None = None,
    report_root: Path | None = None,
) -> dict[str, Any]:
    from genomeai.refactor_verify import verify_refactor

    return verify_refactor(
        project_root=project_root,
        golden_root=golden_root,
        scenario_names=scenario_names,
        report_root=report_root,
    )


def perform_update_golden(
    *,
    project_root: Path,
    golden_root: Path,
    scenario_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    from genomeai.refactor_verify import update_golden

    return update_golden(
        project_root=project_root,
        golden_root=golden_root,
        scenario_names=scenario_names,
    )


__all__ = [
    "perform_update_golden",
    "perform_verify_refactor",
]
