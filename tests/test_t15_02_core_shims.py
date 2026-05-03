from __future__ import annotations

import importlib
import sys
import warnings
from pathlib import Path

from genomeai.cli import main
from genomeai.refactor_verify import verify_refactor as legacy_verify_refactor


def _reload_module(name: str):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_t15_02_legacy_application_import_warns_and_points_to_core_module() -> None:
    sys.modules.pop("genomeai.application.refactor_verify", None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy_mod = importlib.import_module("genomeai.application.refactor_verify")

    core_mod = importlib.import_module("core.application.refactor_verify")
    assert legacy_mod.__file__ == core_mod.__file__
    assert legacy_mod.__name__ == "core.application.refactor_verify"
    assert sys.modules["genomeai.application.refactor_verify"].__file__ == core_mod.__file__
    assert any(
        item.category is DeprecationWarning
        and "genomeai.application.refactor_verify is deprecated" in str(item.message)
        for item in caught
    )


def test_t15_02_legacy_service_import_warns_and_points_to_core_infra_module() -> None:
    sys.modules.pop("genomeai.application.refactor_verify_service", None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        legacy_mod = importlib.import_module("genomeai.application.refactor_verify_service")

    core_mod = importlib.import_module("core.infra.refactor_verify_service")
    assert legacy_mod.__file__ == core_mod.__file__
    assert legacy_mod.__name__ == "core.infra.refactor_verify_service"
    assert sys.modules["genomeai.application.refactor_verify_service"].__file__ == core_mod.__file__
    assert any(
        item.category is DeprecationWarning
        and "genomeai.application.refactor_verify_service is deprecated" in str(item.message)
        for item in caught
    )


def test_t15_02_cli_verify_refactor_remains_backward_compatible(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report_root = tmp_path / "reports"

    exit_code = main(
        [
            "verify_refactor",
            "--project-root",
            str(repo_root),
            "--golden",
            str(repo_root / "golden"),
            "--report-root",
            str(report_root),
            "--scenarios",
            "standard",
        ]
    )

    assert exit_code == 0
    generated = sorted(report_root.glob("verify_*/verify_report.json"))
    assert generated, "verify_refactor CLI did not create verify_report.json"


def test_t15_02_legacy_facade_still_uses_core_runtime_symbols() -> None:
    runtime_mod = importlib.import_module("core.application.refactor_verify_runtime")
    assert legacy_verify_refactor.__globals__["get_scenario_spec"] is runtime_mod.get_scenario_spec
    assert legacy_verify_refactor.__globals__["select_scenario_names"] is runtime_mod.select_scenario_names
