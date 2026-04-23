from __future__ import annotations

import json
from pathlib import Path

from core.infra.environment_snapshot import (
    build_test_environment_snapshot,
    declared_dependency_specs,
    load_test_environment_policy,
    requirement_name,
)


def test_t16_09_requirement_name_parser_handles_specs_and_markers() -> None:
    assert requirement_name("pandas>=2.0") == "pandas"
    assert requirement_name("python-multipart>=0.0.9") == "python-multipart"
    assert requirement_name("uvicorn[standard]>=0.30 ; python_version >= '3.10'") == "uvicorn"



def test_t16_09_declared_dependencies_include_runtime_and_optional_groups() -> None:
    declared = declared_dependency_specs()
    assert declared["pandas"]["group"] == "runtime"
    assert declared["fastapi"]["requirement"] == "fastapi>=0.110"
    assert declared["streamlit"]["group"] == "optional:ui"



def test_t16_09_environment_snapshot_contains_policy_and_versions() -> None:
    snapshot = build_test_environment_snapshot()
    assert snapshot["version"] == 1
    assert snapshot["policy_version"] == 1
    assert snapshot["requires_python"] == ">=3.10"

    packages = {item["name"]: item for item in snapshot["packages"]}
    assert packages["pandas"]["installed_version"]
    assert packages["pandas"]["declared_requirement"] == "pandas>=2.0"
    assert packages["pytest"]["installed_version"]
    assert packages["python-multipart"]["distribution"] == "python-multipart"
    assert packages["ddtrace"]["role"] == "dependency-observability"



def test_t16_09_environment_policy_is_json_serializable_and_documents_upgrade_rules() -> None:
    payload = load_test_environment_policy()
    encoded = json.dumps(payload, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["version"] == 1
    assert decoded["upgrade_policy"]["separate_controlled_change_required"] is True
    assert any(item["name"] == "numpy" for item in decoded["packages"])



def test_t16_09_ci_gate_writes_environment_snapshot_artifact() -> None:
    gate_script = Path("scripts/run_ci_gate.sh").read_text(encoding="utf-8")
    ci_doc = Path("docs/ci_gates.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    project_map = Path("docs/project_map.md").read_text(encoding="utf-8")
    policy_doc = Path("docs/test_environment_reproducibility.md").read_text(encoding="utf-8")

    assert "export_test_env_snapshot.py" in gate_script
    assert "python_environment.json" in gate_script
    assert "python_environment.json" in ci_doc
    assert "docs/test_environment_reproducibility.md" in readme
    assert "test_environment_policy_v1.json" in project_map
    assert "controlled change" in policy_doc
