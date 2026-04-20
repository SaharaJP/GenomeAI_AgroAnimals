from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.public_interfaces import (
    collect_cli_contract,
    collect_python_function_contract,
    load_public_interfaces_snapshot,
)
from genomeai import cli as cli_module


def test_t15_11_cli_and_python_contract_matches_snapshot() -> None:
    snapshot = load_public_interfaces_snapshot()
    assert collect_cli_contract() == snapshot["cli"]
    assert collect_python_function_contract() == snapshot["python"]
    assert "streamlit" not in snapshot


def test_t15_11_verify_refactor_legacy_alias_emits_deprecation(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli_module, "execute_verify_refactor", lambda command: {"exit_code": 0})
    monkeypatch.setattr(cli_module, "render_verify_refactor_cli_lines", lambda result: ["VERIFY_REFACTOR_OK"])

    with pytest.warns(DeprecationWarning, match="verify-refactor"):
        exit_code = cli_module.main([
            "verify-refactor",
            "--project-root",
            ".",
            "--golden",
            "golden",
        ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "VERIFY_REFACTOR_OK" in out


def test_t15_11_public_interfaces_snapshot_has_expected_version_and_deprecations() -> None:
    snapshot = json.loads(Path("docs/public_interfaces.json").read_text(encoding="utf-8"))
    assert snapshot["version"] == 1
    assert {item["name"] for item in snapshot["deprecations"]} >= {
        "verify-refactor",
        "genomeai.application",
        "web_cabinet.audit",
        "web_cabinet.rbac",
    }
