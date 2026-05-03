from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.infra.warning_governance import (
    analyze_warning_governance,
    assert_warning_governance,
    build_warning_governance_report,
    load_dependency_update_policy,
    load_warning_governance_policy,
    parse_warning_sources,
)


PROJECT_WARNING = "/repo/web_cabinet/observability.py:6: DeprecationWarning: web_cabinet.observability is deprecated; import from core.observability instead."
DEPENDENCY_WARNING = "/venv/lib/python3.11/site-packages/python_multipart/__init__.py:10: PendingDeprecationWarning: Please use import python_multipart instead."
PROJECT_RUNTIME_WARNING = "/repo/src/genomeai/economics_v2.py:42: RuntimeWarning: divide by zero encountered in log"


def test_t17_08_policy_and_dependency_notes_are_machine_readable() -> None:
    policy = load_warning_governance_policy()
    dep_policy = load_dependency_update_policy()

    assert policy.version == 1
    assert any(rule.name == "python-multipart-known-issue" for rule in policy.allowlist)
    assert any(rule.name == "project-runtime-warning" for rule in policy.denylist)
    assert dep_policy["upgrade_policy"]["separate_controlled_change_required"] is True
    assert "warning governance report" in dep_policy["upgrade_policy"]["validate_with"]



def test_t17_08_warning_governance_allows_documented_project_deprecations_and_known_dependency_warning(
    tmp_path: Path,
) -> None:
    pytest_log = tmp_path / "pytest.log"
    pytest_log.write_text(PROJECT_WARNING + "\n" + DEPENDENCY_WARNING + "\n", encoding="utf-8")

    evidence, source_files = parse_warning_sources({"pytest": pytest_log})
    report = analyze_warning_governance(evidence, load_warning_governance_policy(), source_files=source_files)
    assert_warning_governance(report)

    assert report.total == 2
    assert report.by_origin == {"dependency": 1, "project": 1}
    assert report.by_dependency == {"python_multipart": 1}
    assert report.matched_counts["deprecation:web_cabinet.observability"] == 1
    assert report.matched_counts["python-multipart-known-issue"] == 1



def test_t17_08_warning_governance_rejects_undocumented_project_warning(tmp_path: Path) -> None:
    pytest_log = tmp_path / "pytest.log"
    pytest_log.write_text(
        "/repo/src/genomeai/score.py:5: DeprecationWarning: totally new undocumented warning\n",
        encoding="utf-8",
    )

    report = build_warning_governance_report({"pytest": pytest_log})
    assert report["status"] == "failed"
    assert report["unexpected"]
    assert "totally new undocumented warning" in report["failure_message"]



def test_t17_08_warning_governance_rejects_denylisted_project_runtime_warning(tmp_path: Path) -> None:
    pytest_log = tmp_path / "pytest.log"
    pytest_log.write_text(PROJECT_RUNTIME_WARNING + "\n", encoding="utf-8")

    report = build_warning_governance_report({"pytest": pytest_log})
    assert report["status"] == "failed"
    assert report["denylisted"]
    assert "project-runtime-warning" in report["failure_message"]



def test_t17_08_ci_and_docs_reference_warning_governance_gate() -> None:
    workflow = Path(".github/workflows/verify_refactor.yml").read_text(encoding="utf-8")
    ci_doc = Path("docs/ci_gates.md").read_text(encoding="utf-8")
    project_map = Path("docs/project_map.md").read_text(encoding="utf-8")
    gate_script = Path("scripts/run_warning_governance_gate.sh").read_text(encoding="utf-8")
    warning_doc = Path("docs/warning_governance.md").read_text(encoding="utf-8") if Path("docs/warning_governance.md").exists() else ""

    assert "Warning governance gate" in workflow
    assert "warning_governance_report.json" in workflow
    assert "run_warning_governance_gate.sh" in workflow
    assert "warning_governance_report.json" in ci_doc
    assert "warning_governance_v1.json" in project_map
    assert "check_warning_governance.py" in gate_script
    assert "dependency_update_policy_v1.json" in warning_doc



def test_t17_08_report_is_json_serializable(tmp_path: Path) -> None:
    pytest_log = tmp_path / "pytest.log"
    smoke_log = tmp_path / "smoke.log"
    pytest_log.write_text(PROJECT_WARNING + "\n", encoding="utf-8")
    smoke_log.write_text("", encoding="utf-8")

    report = build_warning_governance_report({"pytest": pytest_log, "web_smoke": smoke_log})
    encoded = json.dumps(report, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["status"] == "ok"
    assert decoded["totals"]["by_source"] == {"pytest": 1}
