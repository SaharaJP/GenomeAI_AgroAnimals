from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.pedigree_qc import run_pedigree_qc


def _write_canonical(artifacts_root: Path, dv: str, name: str, df: pd.DataFrame) -> Path:
    d = artifacts_root / dv / "canonical"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.csv"
    df.to_csv(p, index=False)
    return p


def test_pedigree_detects_cycles(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_test"

    animals = pd.DataFrame(
        [
            {"farm_id": "F1", "animal_id": "A", "sire_animal_id": "B", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "B", "sire_animal_id": "A", "dam_animal_id": ""},
        ]
    )
    bulls = pd.DataFrame([{"farm_id": "F1", "bull_id": "A"}])

    _write_canonical(artifacts, dv, "dm_animals", animals)
    _write_canonical(artifacts, dv, "dm_bulls", bulls)

    res = run_pedigree_qc(artifacts_root=artifacts, data_version=dv, generations=3)
    assert res["ok"] is True

    issues = pd.read_csv(res["outputs"]["qc_issues_csv"])
    assert (issues["rule_id"] == "P005_CYCLE").any()


def test_inbreeding_common_ancestor_ban(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_test2"

    # Pedigree:
    # cow C -> sire S -> sire A
    # bull B -> sire A
    animals = pd.DataFrame(
        [
            {"farm_id": "F1", "animal_id": "A", "sire_animal_id": "", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "S", "sire_animal_id": "A", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "C", "sire_animal_id": "S", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "B", "sire_animal_id": "A", "dam_animal_id": ""},
        ]
    )
    bulls = pd.DataFrame([{"farm_id": "F1", "bull_id": "B"}])

    _write_canonical(artifacts, dv, "dm_animals", animals)
    _write_canonical(artifacts, dv, "dm_bulls", bulls)

    res = run_pedigree_qc(artifacts_root=artifacts, data_version=dv, generations=3)
    assert res["ok"] is True

    constraints = pd.read_csv(res["outputs"]["constraints_csv"])
    row = constraints.loc[(constraints["cow_id"] == "C") & (constraints["bull_id"] == "B")].iloc[0]
    assert bool(row["allowed"]) is False
    assert row["reason_code"] == "COMMON_ANCESTOR_WITHIN_N"
    assert "A" in str(row["common_ancestors"]).split(",")
