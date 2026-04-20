from __future__ import annotations

from pathlib import Path


def test_t34_07_ci_gate_lists_lockdown_tests() -> None:
    gate = (Path(__file__).resolve().parents[1] / 'ci' / 'pytest_gate.txt').read_text(encoding='utf-8')
    assert 'tests/test_t34_07_production_lockdown.py' in gate
    assert 'tests/web/test_t34_07_production_profile_diagnostics.py' in gate
