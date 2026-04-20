from __future__ import annotations

import json
import sysconfig
from pathlib import Path

from core.infra.warning_audit import (
    build_warning_origin_report,
    classify_warning_filename,
    load_dependency_warning_inventory,
    parse_pytest_warning_log,
)


def test_t16_08_classify_warning_filename_separates_project_dependency_and_stdlib() -> None:
    project_origin, project_pkg = classify_warning_filename(Path("src/genomeai/score.py").resolve())
    assert (project_origin, project_pkg) == ("project", None)

    dep_origin, dep_pkg = classify_warning_filename(
        "/opt/venv/lib/python3.11/site-packages/ddtrace/internal/module.py"
    )
    assert dep_origin == "dependency"
    assert dep_pkg == "ddtrace"

    stdlib_path = Path(sysconfig.get_paths()["stdlib"]) / "warnings.py"
    stdlib_origin, stdlib_pkg = classify_warning_filename(stdlib_path)
    assert (stdlib_origin, stdlib_pkg) == ("stdlib", None)



def test_t16_08_parse_pytest_warning_log_and_group_by_origin() -> None:
    log_text = """
=============================== warnings summary ===============================
/mnt/data/t16_next/src/genomeai/score.py:9: DeprecationWarning: project shim warning
/opt/venv/lib/python3.11/site-packages/ddtrace/internal/module.py:300: RuntimeWarning: dependency warning
""".strip()

    entries = parse_pytest_warning_log(log_text)
    assert len(entries) == 2
    assert entries[0].origin == "project"
    assert entries[1].origin == "dependency"
    assert entries[1].package == "ddtrace"

    report = build_warning_origin_report(entries)
    assert report["total"] == 2
    assert report["by_origin"] == {"dependency": 1, "project": 1}
    assert report["by_dependency"] == {"ddtrace": 1}



def test_t16_08_dependency_inventory_has_versions_and_policy() -> None:
    payload = load_dependency_warning_inventory()

    assert payload["version"] == 1
    tested = payload["tested_environment"]["packages"]
    assert tested["python-multipart"]
    assert tested["ddtrace"]

    observed = payload["observed_in_targeted_ci"]["dependency_warning_origins"]
    names = {item["package"] for item in observed}
    assert {"python-multipart", "ddtrace"}.issubset(names)

    policy = payload["upgrade_policy"]
    assert policy["upgrade_in_separate_change_when"]
    assert policy["document_only_when"]



def test_t16_08_report_script_contract_can_be_consumed_as_json() -> None:
    log_text = "/opt/venv/lib/python3.11/site-packages/python_multipart/__init__.py:10: PendingDeprecationWarning: Please use import python_multipart instead."
    report = build_warning_origin_report(parse_pytest_warning_log(log_text))
    encoded = json.dumps(report, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded["by_origin"] == {"dependency": 1}
    assert decoded["by_dependency"] == {"python_multipart": 1}
