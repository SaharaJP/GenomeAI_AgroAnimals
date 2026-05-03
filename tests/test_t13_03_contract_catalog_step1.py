from pathlib import Path
import json

from genomeai.cli import main
from genomeai.contracts_catalog import build_contract_catalog


def test_build_contract_catalog_contains_versions_and_examples():
    repo = Path(__file__).resolve().parents[1]
    manifest = build_contract_catalog(
        contracts_dir=repo / "configs" / "contracts",
        catalog_path=repo / "configs" / "contracts" / "catalog.json",
    )
    assert manifest["schema"] == "genomeai.data_contract_catalog.v1"
    assert manifest["dataset_count"] >= 6
    animals = next(x for x in manifest["datasets"] if x["dataset"] == "dm_animals")
    assert animals["contract_version"] == "1.0.0"
    assert "animal_id" in animals["required_fields"]
    assert animals["mapping_templates"]
    assert animals["example_files"]
    assert animals["qc_coverage"]["qc.cross_dataset_links"] == "covered"


def test_cli_contracts_catalog_writes_json(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    out = tmp_path / "contract_catalog.json"
    rc = main([
        "contracts-catalog",
        "--contracts",
        str(repo / "configs" / "contracts"),
        "--catalog",
        str(repo / "configs" / "contracts" / "catalog.json"),
        "--output",
        str(out),
    ])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "genomeai.data_contract_catalog.v1"
    assert any(item["dataset"] == "dm_farms" for item in payload["datasets"])
