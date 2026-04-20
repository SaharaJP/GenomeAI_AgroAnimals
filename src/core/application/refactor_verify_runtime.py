from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.domain import ScenarioSpec


SCENARIOS: dict[str, ScenarioSpec] = {
    "standard": ScenarioSpec(
        name="standard",
        description="Базовый smoke-сценарий без QC-ошибок.",
        data_version="dv_refactor_standard",
        qc_run="qc_refactor_standard",
        model_version="model_refactor_standard",
        scoring_run="score_refactor_standard",
        report_version="report_refactor_standard",
        expected_qc_status="PASS",
    ),
    "qc_issues": ScenarioSpec(
        name="qc_issues",
        description="Сценарий с QC warnings, но без блокировки train/score/report.",
        data_version="dv_refactor_qc_issues",
        qc_run="qc_refactor_qc_issues",
        model_version="model_refactor_qc_issues",
        scoring_run="score_refactor_qc_issues",
        report_version="report_refactor_qc_issues",
        expected_qc_status="WARN",
    ),
}


def select_scenario_names(scenario_names: Iterable[str] | None = None) -> list[str]:
    selected = list(scenario_names or SCENARIOS.keys())
    unknown = [name for name in selected if name not in SCENARIOS]
    if unknown:
        raise ValueError(f"unknown scenarios: {unknown}")
    return selected


def get_scenario_spec(scenario_name: str) -> ScenarioSpec:
    try:
        return SCENARIOS[scenario_name]
    except KeyError as exc:
        raise ValueError(f"unknown scenario: {scenario_name}") from exc


def resolve_scenario_specs(scenario_names: Iterable[str] | None = None) -> list[ScenarioSpec]:
    return [get_scenario_spec(name) for name in select_scenario_names(scenario_names)]


def resolve_verify_report_root(*, project_root: Path, report_root: Path | None = None) -> Path:
    base_root = report_root or (project_root / "artifacts" / "_verify_refactor")
    return base_root / datetime.now(timezone.utc).strftime("verify_%Y%m%d_%H%M%S")


def golden_manifest_path(golden_root: Path) -> Path:
    return golden_root / "manifest.json"


__all__ = [
    "SCENARIOS",
    "ScenarioSpec",
    "get_scenario_spec",
    "golden_manifest_path",
    "resolve_scenario_specs",
    "resolve_verify_report_root",
    "select_scenario_names",
]
