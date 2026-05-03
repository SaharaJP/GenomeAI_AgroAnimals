from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.pedigree_qc import run_pedigree_qc
from genomeai.mating_plan_v1 import run_mating_plan, is_pair_allowed


def _write_canonical(artifacts_root: Path, dv: str, name: str, df: pd.DataFrame) -> Path:
    d = artifacts_root / dv / "canonical"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.csv"
    df.to_csv(p, index=False)
    return p


def test_mating_plan_never_emits_forbidden_pairs(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_test_mp"

    # Pedigree:
    # cow C -> sire S -> sire A
    # bull B -> sire A (forbidden)
    # bull D -> unrelated (allowed)
    animals = pd.DataFrame(
        [
            {"farm_id": "F1", "animal_id": "A", "sex": "M", "sire_animal_id": "", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "S", "sex": "M", "sire_animal_id": "A", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "C", "sex": "F", "sire_animal_id": "S", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "B", "sex": "M", "sire_animal_id": "A", "dam_animal_id": ""},
            {"farm_id": "F1", "animal_id": "D", "sex": "M", "sire_animal_id": "", "dam_animal_id": ""},
        ]
    )
    bulls = pd.DataFrame(
        [
            {"farm_id": "F1", "bull_id": "B", "ebv_milk": 1.0, "ebv_scc": 1.0},
            {"farm_id": "F1", "bull_id": "D", "ebv_milk": 0.5, "ebv_scc": 0.5},
        ]
    )
    lact = pd.DataFrame(
        [
            {"farm_id": "F1", "animal_id": "C", "calving_date": "2025-01-01", "milk_305d_kg": 8000, "scc": 200},
        ]
    )

    _write_canonical(artifacts, dv, "dm_animals", animals)
    _write_canonical(artifacts, dv, "dm_bulls", bulls)
    _write_canonical(artifacts, dv, "dm_lactations", lact)

    ped = run_pedigree_qc(artifacts_root=artifacts, data_version=dv, generations=3)
    assert ped["ok"] is True

    res = run_mating_plan(artifacts_root=artifacts, data_version=dv)
    assert res["ok"] is True
    df = pd.read_csv(res["outputs"]["mating_plan_csv"])

    # forbidden pair must not exist
    assert not ((df["cow_id"] == "C") & (df["bull_id"] == "B")).any()
    # allowed pair can exist
    assert ((df["cow_id"] == "C") & (df["bull_id"] == "D")).any()

    allowed, meta = is_pair_allowed(artifacts_root=artifacts, data_version=dv, cow_id="C", bull_id="B")
    assert allowed is False
    assert meta.get("reason_code") == "COMMON_ANCESTOR_WITHIN_N"
