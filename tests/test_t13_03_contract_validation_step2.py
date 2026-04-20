from __future__ import annotations

from pathlib import Path

from genomeai.contract_precheck import validate_source_by_contract
from genomeai.contracts import load_contracts_dir


def test_contract_precheck_reports_missing_columns_and_bad_allowed_values(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    contracts = load_contracts_dir(repo_root / "configs" / "contracts")
    src = tmp_path / "animals_bad.csv"
    src.write_text(
        "AnimalID,EarTag,Breed,Sex,Birth,Alive,Status\n"
        "A1,1001,HO,X,2022-01-01,true,active\n",
        encoding="utf-8",
    )

    result = validate_source_by_contract(
        dataset_key="animals",
        file_path=src,
        mapping_path=repo_root / "configs" / "mappings" / "animals_example.yaml",
        contract=contracts["dm_animals"],
    )

    assert result.ok is False
    text = "\n".join(result.top_messages(limit=10))
    assert "Колонка из mapping не найдена" in text
    assert "FarmID" in text
    assert "allowed_values" in text
