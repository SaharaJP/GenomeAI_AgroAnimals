from __future__ import annotations

import json
from pathlib import Path

from genomeai.application.refactor_verify import (
    VerifyRefactorCommand,
    execute_verify_refactor,
    parse_scenarios_arg,
    render_verify_refactor_cli_lines,
)
from genomeai.cli import main
from genomeai.application.refactor_verify_command import selected_scenarios
from genomeai.application.refactor_verify_compare import (
    FileDiff,
    ScenarioReport,
    VerifyReport,
    compare_snapshot_dirs,
    render_markdown,
    verify_report_payload,
)
from genomeai.application.refactor_verify_dispatch import build_verify_refactor_dispatch
from genomeai.application.refactor_verify_errors import execute_refactor_verify_action
from genomeai.application.refactor_verify_result import (
    make_golden_updated_result,
    make_operation_failed_result,
    make_update_blocked_result,
    make_verify_execution_result,
)
from genomeai.application.refactor_verify_runtime import (
    SCENARIOS,
    get_scenario_spec,
    resolve_scenario_specs,
    resolve_verify_report_root,
    select_scenario_names,
)
from genomeai.application.refactor_verify_service import (
    perform_update_golden,
    perform_verify_refactor,
)
from genomeai.application import (
    VerifyRefactorCommand as PackageVerifyRefactorCommand,
    execute_verify_refactor as package_execute_verify_refactor,
    parse_scenarios_arg as package_parse_scenarios_arg,
    render_verify_refactor_cli_lines as package_render_verify_refactor_cli_lines,
)
from genomeai.refactor_verify import ensure_golden_inputs, update_golden, verify_refactor, _normalize_audit


def test_t15_01_qc_inputs_are_seeded_with_warning_case(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    golden_root = tmp_path / "golden"

    ensure_golden_inputs(golden_root=golden_root, project_root=repo_root)

    animals_csv = golden_root / "scenarios" / "qc_issues" / "inputs" / "external" / "animals_ext.csv"
    lactations_csv = golden_root / "scenarios" / "qc_issues" / "inputs" / "external" / "lactations_ext.csv"
    animals_text = animals_csv.read_text(encoding="utf-8")
    lact_text = lactations_csv.read_text(encoding="utf-8")

    assert "A003" in animals_text
    assert "19000" in lact_text


def test_t15_01_verify_refactor_passes_on_fresh_standard_golden(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    golden_root = tmp_path / "golden"

    update_golden(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"])
    res = verify_refactor(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"], report_root=tmp_path / "reports")

    assert res["ok"] is True
    assert res["scenarios"][0]["scenario"] == "standard"
    assert res["scenarios"][0]["differences"] == 0


def test_t15_01_verify_refactor_reports_human_readable_diff(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    golden_root = tmp_path / "golden"

    update_golden(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"])
    report_summary = golden_root / "scenarios" / "standard" / "snapshot" / "report_summary.json"
    payload = json.loads(report_summary.read_text(encoding="utf-8"))
    payload["mode_requested"] = "tampered"
    report_summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    res = verify_refactor(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"], report_root=tmp_path / "reports")

    assert res["ok"] is False
    md_path = Path(res["report_md"])
    md_text = md_path.read_text(encoding="utf-8")
    assert "report_summary.json" in md_text
    assert "tampered" in md_text


def test_t15_01_cli_requires_manual_confirmation_and_hides_random_task_id(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    golden_root = tmp_path / "golden"

    exit_code = main([
        "verify_refactor",
        "--project-root",
        str(repo_root),
        "--golden",
        str(golden_root),
        "--update-golden",
    ])
    assert exit_code == 2

    rows = _normalize_audit([
        {
            "tenant_id": "default",
            "username": "admin",
            "role": "admin",
            "action": "verify_refactor.task_seeded",
            "action_group": "verify",
            "object_type": "task",
            "object_id": "random-generated-id",
            "data_version": "dv",
            "run_id": "score_run",
            "status": "OK",
        }
    ])
    assert rows[0]["object_id"] == "<task_id>"


def test_t15_01_update_golden_writes_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    golden_root = tmp_path / "golden"

    res = update_golden(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"])
    manifest_path = Path(res["manifest_path"])
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest_path.exists()
    assert payload["schema"] == "genomeai.golden_manifest.v1"
    assert payload["scenario_count"] == 1
    assert payload["scenarios"][0]["scenario"] == "standard"
    assert payload["scenarios"][0]["snapshot"]["file_count"] > 0


def test_t15_01_verify_refactor_reports_manifest_drift(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    golden_root = tmp_path / "golden"

    update_golden(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"])
    manifest_path = golden_root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["scenarios"][0]["snapshot"]["files"] = []
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    res = verify_refactor(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"], report_root=tmp_path / "reports")

    assert res["ok"] is False
    assert any(row["scenario"] == "golden_manifest" for row in res["scenarios"])
    md_text = Path(res["report_md"]).read_text(encoding="utf-8")
    assert "golden_manifest" in md_text
    assert "manifest.json" in md_text


def test_t15_01_parse_scenarios_arg_trims_and_deduplicates() -> None:
    assert parse_scenarios_arg(" standard, qc_issues,standard ,, qc_issues ") == ["standard", "qc_issues"]


def test_t15_01_application_use_case_blocks_update_without_confirmation(tmp_path: Path) -> None:
    result = execute_verify_refactor(
        VerifyRefactorCommand(
            project_root=tmp_path / "repo",
            golden_root=tmp_path / "golden",
            scenario_names=["standard"],
            update_golden=True,
            confirm_update_golden=False,
        )
    )

    assert result["status"] == "VERIFY_REFACTOR_UPDATE_BLOCKED"
    assert result["exit_code"] == 2
    assert render_verify_refactor_cli_lines(result) == [
        "VERIFY_REFACTOR_UPDATE_BLOCKED",
        "reason=manual confirmation required; pass --i-understand-update-golden",
    ]


def test_t15_01_compare_helper_reports_missing_and_extra_files(tmp_path: Path) -> None:
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    expected.mkdir()
    actual.mkdir()
    (expected / "same.json").write_text('{"ok": true}\n', encoding="utf-8")
    (expected / "missing.json").write_text('{"value": 1}\n', encoding="utf-8")
    (actual / "same.json").write_text('{"ok": true}\n', encoding="utf-8")
    (actual / "extra.json").write_text('{"value": 2}\n', encoding="utf-8")

    report = compare_snapshot_dirs(expected, actual)

    assert report.ok is False
    assert report.compared_files == 1
    assert {(d.kind, d.file) for d in report.differences} == {
        ("missing", "missing.json"),
        ("extra", "extra.json"),
    }


def test_t15_01_compare_helper_renders_stable_markdown_and_json_payload() -> None:
    report = VerifyReport(
        schema="genomeai.verify_refactor_report.v1",
        created_at_utc="2026-03-12T00:00:00+00:00",
        golden_root="/tmp/golden",
        ok=False,
        scenarios=[
            ScenarioReport(
                scenario="standard",
                ok=False,
                compared_files=3,
                differences=[FileDiff(file="report_summary.json", kind="content", detail="tampered")],
                expected_snapshot="/tmp/golden/standard",
                actual_snapshot="/tmp/actual/standard",
            )
        ],
    )

    payload = verify_report_payload(report)
    md = render_markdown(report)

    assert payload["schema"] == "genomeai.verify_refactor_report.v1"
    assert payload["scenarios"][0]["differences"][0]["file"] == "report_summary.json"
    assert "## standard: FAIL" in md
    assert "report_summary.json" in md
    assert "tampered" in md


def test_t15_01_runtime_service_selects_default_scenarios_in_declared_order() -> None:
    assert select_scenario_names() == list(SCENARIOS.keys())
    assert [item.name for item in resolve_scenario_specs(["qc_issues", "standard"])] == ["qc_issues", "standard"]


def test_t15_01_runtime_service_builds_default_report_root_under_artifacts(tmp_path: Path) -> None:
    report_root = resolve_verify_report_root(project_root=tmp_path)

    assert report_root.parent == tmp_path / "artifacts" / "_verify_refactor"
    assert report_root.name.startswith("verify_")


def test_t15_01_refactor_verify_reexports_runtime_symbols_for_backward_compatibility() -> None:
    from genomeai import refactor_verify as facade

    assert facade.get_scenario_spec("standard").expected_qc_status == "PASS"
    assert facade.select_scenario_names(["standard"]) == ["standard"]


def test_t15_01_service_adapter_delegates_verify_call(monkeypatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_verify_refactor(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "report_json": "a", "report_md": "b", "report_root": "c", "golden_manifest": "d", "scenarios": []}

    monkeypatch.setattr("genomeai.refactor_verify.verify_refactor", fake_verify_refactor)

    result = perform_verify_refactor(
        project_root=tmp_path / "repo",
        golden_root=tmp_path / "golden",
        scenario_names=["standard"],
        report_root=tmp_path / "reports",
    )

    assert result["ok"] is True
    assert seen["scenario_names"] == ["standard"]
    assert seen["report_root"] == tmp_path / "reports"


def test_t15_01_service_adapter_delegates_update_golden_call(monkeypatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_update_golden(**kwargs):
        seen.update(kwargs)
        return {
            "ok": True,
            "updated_scenarios": ["standard"],
            "golden_root": str((tmp_path / "golden").resolve()),
            "manifest_path": str((tmp_path / "golden" / "manifest.json").resolve()),
        }

    monkeypatch.setattr("genomeai.refactor_verify.update_golden", fake_update_golden)

    result = perform_update_golden(
        project_root=tmp_path / "repo",
        golden_root=tmp_path / "golden",
        scenario_names=["standard"],
    )

    assert result["ok"] is True
    assert seen["scenario_names"] == ["standard"]
    assert seen["golden_root"] == tmp_path / "golden"


def test_t15_01_result_helper_renders_golden_updated_lines() -> None:
    result = make_golden_updated_result(
        {
            "golden_root": "/tmp/golden",
            "manifest_path": "/tmp/golden/manifest.json",
            "updated_scenarios": ["standard", "qc_issues"],
        }
    )

    assert result["status"] == "VERIFY_REFACTOR_GOLDEN_UPDATED"
    assert render_verify_refactor_cli_lines(result) == [
        "VERIFY_REFACTOR_GOLDEN_UPDATED",
        "golden_root=/tmp/golden",
        "manifest_path=/tmp/golden/manifest.json",
        "updated_scenarios=standard,qc_issues",
    ]


def test_t15_01_result_helper_builds_failed_verify_status() -> None:
    result = make_verify_execution_result(
        {
            "ok": False,
            "golden_manifest": "/tmp/golden/manifest.json",
            "report_json": "/tmp/verify_report.json",
            "report_md": "/tmp/verify_report.md",
            "scenarios": [{"scenario": "standard", "ok": False, "compared_files": 11, "differences": 1}],
        }
    )

    assert result["status"] == "VERIFY_REFACTOR_FAILED"
    assert result["exit_code"] == 2
    assert render_verify_refactor_cli_lines(result) == [
        "VERIFY_REFACTOR_FAILED",
        "golden_manifest=/tmp/golden/manifest.json",
        "report_json=/tmp/verify_report.json",
        "report_md=/tmp/verify_report.md",
        "scenario=standard ok=False compared_files=11 differences=1",
    ]


def test_t15_01_use_case_maps_verify_service_file_not_found_to_failed_result(tmp_path: Path, monkeypatch) -> None:
    def boom(**_kwargs):
        raise FileNotFoundError("golden inputs not found: /tmp/missing")

    monkeypatch.setattr("genomeai.application.refactor_verify_dispatch.perform_verify_refactor", boom)

    result = execute_verify_refactor(
        VerifyRefactorCommand(
            project_root=tmp_path / "repo",
            golden_root=tmp_path / "golden",
            scenario_names=["standard"],
            report_root=tmp_path / "reports",
        )
    )

    assert result["status"] == "VERIFY_REFACTOR_FAILED"
    assert result["error_code"] == "missing_path"
    assert result["error_type"] == "FileNotFoundError"
    assert result["reason"] == "golden inputs not found: /tmp/missing"
    assert render_verify_refactor_cli_lines(result) == [
        "VERIFY_REFACTOR_FAILED",
        "action=verify_refactor",
        "error_type=FileNotFoundError",
        "error_code=missing_path",
        "reason=golden inputs not found: /tmp/missing",
        f"golden_manifest={(tmp_path / 'golden' / 'manifest.json').resolve()}",
        f"report_root={(tmp_path / 'reports').resolve()}",
        "report_json=NA",
        "report_md=NA",
    ]


def test_t15_01_error_helper_maps_validation_error_for_update_golden(tmp_path: Path) -> None:
    result = execute_refactor_verify_action(
        action_name="update_golden",
        operation=lambda: (_ for _ in ()).throw(ValueError("unknown scenarios: ['broken']")),
        success_builder=make_golden_updated_result,
        golden_root=tmp_path / "golden",
    )

    assert result == make_operation_failed_result(
        action_name="update_golden",
        error_type="ValueError",
        error_code="validation_error",
        reason="unknown scenarios: ['broken']",
        golden_manifest=str((tmp_path / "golden" / "manifest.json").resolve()),
        report_root=None,
    )


def test_t15_01_command_helper_returns_none_for_default_scenarios(tmp_path: Path) -> None:
    command = VerifyRefactorCommand(
        project_root=tmp_path / "repo",
        golden_root=tmp_path / "golden",
        scenario_names=[],
    )

    assert selected_scenarios(command) is None


def test_t15_01_dispatch_builder_routes_update_golden_without_report_root(tmp_path: Path) -> None:
    command = VerifyRefactorCommand(
        project_root=tmp_path / "repo",
        golden_root=tmp_path / "golden",
        scenario_names=["standard"],
        update_golden=True,
        confirm_update_golden=True,
    )

    dispatch = build_verify_refactor_dispatch(command)

    assert dispatch.action_name == "update_golden"
    assert dispatch.report_root is None
    assert dispatch.golden_root == tmp_path / "golden"


def test_t15_01_application_refactor_verify_reexports_command_symbols() -> None:
    from genomeai.application import refactor_verify as use_case

    assert use_case.parse_scenarios_arg("standard,standard,qc_issues") == ["standard", "qc_issues"]
    assert use_case.VerifyRefactorCommand.__name__ == "VerifyRefactorCommand"


def test_t15_01_application_package_reexports_public_verify_api() -> None:
    assert PackageVerifyRefactorCommand.__name__ == "VerifyRefactorCommand"
    assert package_parse_scenarios_arg("standard, qc_issues, standard") == ["standard", "qc_issues"]
    assert callable(package_execute_verify_refactor)
    assert callable(package_render_verify_refactor_cli_lines)


def test_t15_01_public_module_all_surfaces_are_explicit() -> None:
    from genomeai.application import refactor_verify_compare as compare_mod
    from genomeai.application import refactor_verify_result as result_mod
    from genomeai.application import refactor_verify_runtime as runtime_mod
    from genomeai.application import refactor_verify_service as service_mod

    assert compare_mod.__all__ == [
        "FileDiff",
        "ScenarioReport",
        "VerifyReport",
        "compare_snapshot_dirs",
        "render_markdown",
        "verify_report_payload",
    ]
    assert runtime_mod.__all__ == [
        "SCENARIOS",
        "ScenarioSpec",
        "get_scenario_spec",
        "golden_manifest_path",
        "resolve_scenario_specs",
        "resolve_verify_report_root",
        "select_scenario_names",
    ]
    assert service_mod.__all__ == ["perform_update_golden", "perform_verify_refactor"]
    assert result_mod.__all__ == [
        "make_golden_updated_result",
        "make_operation_failed_result",
        "make_update_blocked_result",
        "make_verify_execution_result",
        "render_verify_refactor_cli_lines",
    ]
