from __future__ import annotations

from pathlib import Path

from genomeai.cli import main
from genomeai.contracts import load_contracts_dir
from genomeai.validation import validate_input_dir


def test_a1_ingest_three_datasets_to_one_data_version(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts = tmp_path / "artifacts"
    dv = "dv_test_001"

    rc1 = main(
        [
            "ingest",
            "--dataset",
            "farms",
            "--file",
            str(repo_root / "data/examples/external/farms_ext.csv"),
            "--mapping",
            str(repo_root / "configs/mappings/farms_example.yaml"),
            "--out-version",
            dv,
            "--artifacts",
            str(artifacts),
        ]
    )
    rc2 = main(
        [
            "ingest",
            "--dataset",
            "animals",
            "--file",
            str(repo_root / "data/examples/external/animals_ext.csv"),
            "--mapping",
            str(repo_root / "configs/mappings/animals_example.yaml"),
            "--out-version",
            dv,
            "--artifacts",
            str(artifacts),
        ]
    )
    rc3 = main(
        [
            "ingest",
            "--dataset",
            "lactations",
            "--file",
            str(repo_root / "data/examples/external/lactations_ext.csv"),
            "--mapping",
            str(repo_root / "configs/mappings/lactations_example.yaml"),
            "--out-version",
            dv,
            "--artifacts",
            str(artifacts),
        ]
    )

    # ingest returns 0 (non-fatal issues are logged to jsonl)
    assert rc1 == 0
    assert rc2 == 0
    assert rc3 == 0

    canonical_dir = artifacts / dv / "canonical"
    assert (canonical_dir / "dm_farms.csv").exists()
    assert (canonical_dir / "dm_animals.csv").exists()
    assert (canonical_dir / "dm_lactations.csv").exists()

    contracts = load_contracts_dir(repo_root / "configs/contracts")
    errs, _found = validate_input_dir(canonical_dir, contracts)
    assert errs == []

    # error logs exist
    logs_dir = artifacts / dv / "ingest_logs"
    assert (logs_dir / "dm_farms_errors.jsonl").exists()
    assert (logs_dir / "dm_animals_errors.jsonl").exists()
    assert (logs_dir / "dm_lactations_errors.jsonl").exists()
