from __future__ import annotations

from pathlib import Path

from genomeai.qc import run_qc
from genomeai.score import run_scoring
from genomeai.train import train_productivity_model


def _prep_canonical(tmp_path: Path, data_version: str) -> None:
    canonical_dir = tmp_path / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())


def test_score_exports_xlsx(tmp_path: Path) -> None:
    dv = "dv_test_score"
    _prep_canonical(tmp_path, dv)

    qc = run_qc(data_version=dv, artifacts_root=tmp_path)
    assert qc["qc_status"] in {"PASS", "WARN"}
    qc_run = qc["qc_run"]

    tr = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc_run)
    assert tr["ok"] is True
    mv = tr["model_version"]

    sc = run_scoring(artifacts_root=tmp_path, data_version=dv, model_version=mv)
    assert sc["ok"] is True
    out = sc["outputs"]
    assert Path(out["animal_ranking_xlsx"]).exists()
    assert Path(out["group_summary_xlsx"]).exists()
    assert Path(out["recommendations_xlsx"]).exists()
