from __future__ import annotations

from core.public_interfaces import collect_api_contract, load_public_interfaces_snapshot


def test_t15_11_api_contract_matches_snapshot() -> None:
    snapshot = load_public_interfaces_snapshot()
    assert collect_api_contract() == snapshot["api"]
