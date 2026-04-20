from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.qc import run_qc


def _prep_canonical(tmp_path: Path, data_version: str) -> Path:
    canonical_dir = tmp_path / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    # copy files
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        src = base / fn
        dst = canonical_dir / fn
        dst.write_bytes(src.read_bytes())
    return canonical_dir


def test_qc_warn_on_animals_without_lactations(tmp_path: Path) -> None:
    dv = "dv_test_warn"
    _prep_canonical(tmp_path, dv)

    summary = run_qc(data_version=dv, artifacts_root=tmp_path)
    assert summary["qc_status"] in {"WARN", "PASS"}
    out_dir = Path(summary["outputs"]["qc_report_xlsx"]).resolve().parent
    assert (out_dir / "qc_report.xlsx").exists()
    assert (out_dir / "bad_rows.csv").exists()
    assert (out_dir / "qc_summary.json").exists()


def test_qc_error_on_duplicate_pk(tmp_path: Path) -> None:
    dv = "dv_test_error"
    canonical_dir = _prep_canonical(tmp_path, dv)

    # Introduce duplicate animal_id
    animals_path = canonical_dir / "dm_animals.csv"
    df = pd.read_csv(animals_path)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    df.to_csv(animals_path, index=False)

    summary = run_qc(data_version=dv, artifacts_root=tmp_path)
    assert summary["qc_status"] == "ERROR"
    out_dir = Path(summary["outputs"]["qc_report_xlsx"]).resolve().parent
    bad = pd.read_csv(out_dir / "bad_rows.csv")
    assert len(bad) > 0
