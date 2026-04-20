from __future__ import annotations

from pathlib import Path

from genomeai.qc import run_qc
from genomeai.train import train_productivity_model


def _prep_canonical(tmp_path: Path, data_version: str) -> None:
    canonical_dir = tmp_path / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())


def test_train_creates_model_artifacts(tmp_path: Path) -> None:
    dv = "dv_test_train"
    _prep_canonical(tmp_path, dv)

    qc = run_qc(data_version=dv, artifacts_root=tmp_path)
    assert qc["qc_status"] in {"PASS", "WARN"}
    qc_run = qc["qc_run"]

    res = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc_run)
    assert res["ok"] is True
    mv = res["model_version"]
    model_dir = Path(res["model_dir"])
    assert model_dir.exists()
    assert (model_dir / "model.joblib").exists()
    assert (model_dir / "model_card.md").exists()
    assert (model_dir / "model_card.json").exists()
    assert (model_dir / "train_summary.json").exists()
    assert (tmp_path / dv / "models" / mv).exists()


def test_retrain_produces_new_model_version(tmp_path: Path) -> None:
    dv = "dv_test_retrain"
    _prep_canonical(tmp_path, dv)
    qc = run_qc(data_version=dv, artifacts_root=tmp_path)
    assert qc["qc_status"] in {"PASS", "WARN"}
    qc_run = qc["qc_run"]

    r1 = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc_run)
    r2 = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc_run)
    assert r1["ok"] and r2["ok"]
    assert r1["model_version"] != r2["model_version"]