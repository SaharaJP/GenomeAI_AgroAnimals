from __future__ import annotations

from pathlib import Path

import yaml



def test_t15_12_ci_pytest_gate_list_contains_required_contracts() -> None:
    entries = [
        line.strip()
        for line in Path("ci/pytest_gate.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert "tests/test_t15_11_public_interfaces_contracts.py" in entries
    assert "tests/web/test_t15_11_public_api_contracts.py" in entries
    assert "tests/test_t15_11_config_loader_validator.py" in entries
    assert "tests/test_t15_10_core_security_audit.py" in entries
    assert "tests/test_t16_07_deprecation_policy.py" in entries
    assert "tests/test_t16_08_verify_refactor_warning_gate.py" in entries
    assert "tests/test_t16_08_dependency_warning_audit.py" in entries
    assert "tests/test_t16_09_test_environment_snapshot.py" in entries



def test_t15_12_ci_workflow_has_pytest_smoke_verify_and_failure_artifacts() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/verify_refactor.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["gates"]
    steps = job["steps"]

    step_names = [step.get("name", "") for step in steps]
    assert "Pytest gate" in step_names
    assert "E2E smoke gate" in step_names
    assert "Golden verification gate" in step_names
    assert "Streamlit parity gate" in step_names
    assert "Upload CI artifacts on failure" in step_names

    run_text = "\n".join(str(step.get("run", "")) for step in steps)
    assert "bash scripts/run_ci_gate.sh" in run_text
    assert "python -m web_cabinet.smoke" in run_text
    assert "bash scripts/run_streamlit_parity_gate.sh" in run_text
    assert "python -m genomeai.cli verify_refactor" in run_text

    gate_script = Path("scripts/run_ci_gate.sh").read_text(encoding="utf-8")
    assert "python scripts/report_warning_log.py" in gate_script
    assert "pytest.warning_report.json" in gate_script
    assert "export_test_env_snapshot.py" in gate_script
    assert "python_environment.json" in gate_script

    upload_step = next(step for step in steps if step.get("name") == "Upload CI artifacts on failure")
    assert upload_step["uses"] == "actions/upload-artifact@v4"
    upload_path = str(upload_step["with"]["path"])
    assert "artifacts/_ci" in upload_path
    assert "_tmp/ci_smoke" in upload_path
    assert "_tmp/ci_streamlit_smoke" in upload_path



def test_t15_12_docs_reference_ci_gates_and_project_map() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    project_map = Path("docs/project_map.md").read_text(encoding="utf-8")
    ci_doc = Path("docs/ci_gates.md").read_text(encoding="utf-8")
    deprecation_doc = Path("docs/deprecation_policy.md").read_text(encoding="utf-8")
    verify_doc = Path("docs/verify_refactor_warning_policy.md").read_text(encoding="utf-8")
    dep_doc = Path("docs/dependency_warning_audit.md").read_text(encoding="utf-8")
    env_doc = Path("docs/test_environment_reproducibility.md").read_text(encoding="utf-8")

    assert "docs/project_map.md" in readme
    assert "docs/ci_gates.md" in readme
    assert "docs/streamlit_parity_gates.md" in readme
    assert "docs/dependency_warning_audit.md" in readme
    assert "docs/test_environment_reproducibility.md" in readme
    assert "ci/pytest_gate.txt" in project_map
    assert "docs/streamlit_parity_gates.md" in project_map
    assert "dependency_warning_inventory_v1.json" in project_map
    assert "test_environment_policy_v1.json" in project_map
    assert "web_cabinet.smoke" in ci_doc
    assert "Streamlit parity gate" in ci_doc
    assert "verify_refactor" in ci_doc
    assert "pytest.warning_report.json" in ci_doc
    assert "python_environment.json" in ci_doc
    assert "deprecation_warnings_v1.json" in deprecation_doc
    assert "tests/test_t16_07_deprecation_policy.py" in deprecation_doc
    assert "dependency_warning_inventory_v1.json" in dep_doc
    assert "controlled change" in env_doc
    assert "pytest.warning_report.json" in dep_doc
    assert "RuntimeWarning" in verify_doc
