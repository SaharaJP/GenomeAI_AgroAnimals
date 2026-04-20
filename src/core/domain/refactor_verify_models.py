from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class VerifyRefactorCommand:
    project_root: Path
    golden_root: Path
    scenario_names: list[str]
    report_root: Path | None = None
    update_golden: bool = False
    confirm_update_golden: bool = False


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    description: str
    data_version: str
    qc_run: str
    model_version: str
    scoring_run: str
    report_version: str
    expected_qc_status: str


@dataclass
class FileDiff:
    file: str
    kind: str
    detail: str


@dataclass
class ScenarioReport:
    scenario: str
    ok: bool
    compared_files: int
    differences: list[FileDiff]
    expected_snapshot: str
    actual_snapshot: str


@dataclass
class VerifyReport:
    schema: str
    created_at_utc: str
    golden_root: str
    ok: bool
    scenarios: list[ScenarioReport]


@dataclass(frozen=True)
class VerifyRefactorDispatch:
    action_name: str
    operation: Callable[[], dict[str, Any]]
    success_builder: Callable[[dict[str, Any]], dict[str, Any]]
    golden_root: Path
    report_root: Path | None = None


__all__ = [
    "FileDiff",
    "ScenarioReport",
    "ScenarioSpec",
    "VerifyRefactorCommand",
    "VerifyRefactorDispatch",
    "VerifyReport",
]
