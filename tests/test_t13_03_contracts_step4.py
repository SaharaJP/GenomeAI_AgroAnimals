from __future__ import annotations

from pathlib import Path

from genomeai.contracts_catalog import build_contract_catalog, validate_contract_catalog_versions


def test_contract_catalog_versions_are_consistent() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = build_contract_catalog(
        contracts_dir=repo_root / "configs" / "contracts",
        catalog_path=repo_root / "configs" / "contracts" / "catalog.json",
    )
    result = validate_contract_catalog_versions(manifest, contracts_dir=repo_root / "configs" / "contracts")
    assert result["ok"] is True
    assert result["checked_datasets"] >= 3
    assert result["issue_count"] == 0


def test_contract_catalog_versions_detect_mismatch() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = build_contract_catalog(
        contracts_dir=repo_root / "configs" / "contracts",
        catalog_path=repo_root / "configs" / "contracts" / "catalog.json",
    )
    datasets = list(manifest["datasets"])
    datasets[0] = dict(datasets[0])
    datasets[0]["contract_version"] = "9.9.9"
    broken = {**manifest, "datasets": datasets}
    result = validate_contract_catalog_versions(broken, contracts_dir=repo_root / "configs" / "contracts")
    assert result["ok"] is False
    assert result["issue_count"] >= 1
    assert any("contract version mismatch" in issue for issue in result["issues"])
