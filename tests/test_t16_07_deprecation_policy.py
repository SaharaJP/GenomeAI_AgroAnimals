from __future__ import annotations

import importlib
import sys
import warnings

import pytest

from core.infra.deprecation_policy import assert_warning_policy, load_deprecation_policy
from genomeai import cli as cli_module


@pytest.mark.filterwarnings("always")
def test_t16_07_documented_shim_import_warnings_match_allowlist_and_budget() -> None:
    policy = load_deprecation_policy()
    shim_rules = policy.rules_for("import")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for rule in shim_rules:
            sys.modules.pop(rule.trigger_target, None)
            importlib.import_module(rule.trigger_target)

    report = assert_warning_policy(caught, shim_rules)

    assert len([item for item in caught if issubclass(item.category, DeprecationWarning)]) == len(shim_rules)
    assert all(report.matched_counts[rule.name] == 1 for rule in shim_rules)


@pytest.mark.filterwarnings("always")
def test_t16_07_verify_refactor_cli_alias_warning_is_documented(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = load_deprecation_policy()
    rule = policy.rule_by_name("verify-refactor-cli-alias")

    monkeypatch.setattr(cli_module, "execute_verify_refactor", lambda command: {"exit_code": 0})
    monkeypatch.setattr(cli_module, "render_verify_refactor_cli_lines", lambda result: ["VERIFY_REFACTOR_OK"])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        exit_code = cli_module.main([
            "verify-refactor",
            "--project-root",
            ".",
            "--golden",
            "golden",
        ])

    assert exit_code == 0
    report = assert_warning_policy(caught, [rule])
    assert report.matched_counts[rule.name] == 1


@pytest.mark.filterwarnings("always")
def test_t16_07_warning_gate_rejects_undocumented_deprecations() -> None:
    policy = load_deprecation_policy()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn("brand new undocumented shim warning", DeprecationWarning, stacklevel=1)

    with pytest.raises(AssertionError, match="Unexpected deprecation warnings"):
        assert_warning_policy(caught, policy.rules)


@pytest.mark.filterwarnings("always")
def test_t16_07_warning_gate_rejects_budget_overflow() -> None:
    policy = load_deprecation_policy()
    rule = policy.rule_by_name("genomeai.application")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn(
            "genomeai.application is deprecated; import from core.application instead.",
            DeprecationWarning,
            stacklevel=1,
        )
        warnings.warn(
            "genomeai.application is deprecated; import from core.application instead.",
            DeprecationWarning,
            stacklevel=1,
        )

    with pytest.raises(AssertionError, match="budget exceeded"):
        assert_warning_policy(caught, [rule])
