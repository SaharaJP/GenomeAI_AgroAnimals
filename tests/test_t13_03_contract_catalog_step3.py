from pathlib import Path
import json

from genomeai.cli import main
from genomeai.contracts_catalog import build_contract_catalog, render_contract_catalog_markdown


def test_build_contract_catalog_includes_mapping_template_rows_and_summary():
    repo = Path(__file__).resolve().parents[1]
    manifest = build_contract_catalog(
        contracts_dir=repo / "configs" / "contracts",
        catalog_path=repo / "configs" / "contracts" / "catalog.json",
    )
    assert manifest["dataset_count"] >= 6
    assert manifest["mapping_template_count"] >= 9
    assert "master_data" in manifest["domains"]
    animals = next(x for x in manifest["datasets"] if x["dataset"] == "dm_animals")
    assert animals["mapping_template_count"] >= 4
    assert any(row["source_system"] == "selex" for row in animals["mapping_template_rows"])
    assert animals["qc_status_counts"]["covered"] >= 1


def test_cli_contracts_catalog_writes_json_and_markdown_step3(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    out_json = tmp_path / "contract_catalog.json"
    out_md = tmp_path / "contract_catalog.md"
    rc = main([
        "contracts-catalog",
        "--contracts",
        str(repo / "configs" / "contracts"),
        "--catalog",
        str(repo / "configs" / "contracts" / "catalog.json"),
        "--output",
        str(out_json),
        "--markdown-output",
        str(out_md),
    ])
    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["schema"] == "genomeai.data_contract_catalog.v1"
    md = out_md.read_text(encoding="utf-8")
    assert "# GenomeAI AgroAnimals — Data Contracts Catalog" in md
    assert "## dm_animals" in md


def test_render_contract_catalog_markdown_mentions_qc_and_templates():
    repo = Path(__file__).resolve().parents[1]
    manifest = build_contract_catalog(
        contracts_dir=repo / "configs" / "contracts",
        catalog_path=repo / "configs" / "contracts" / "catalog.json",
    )
    text = render_contract_catalog_markdown(manifest)
    assert "QC coverage" in text
    assert "Reusable mapping templates" not in text  # markdown uses section title without UI copy
    assert "### Mapping templates" in text
