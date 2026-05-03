from __future__ import annotations

import json
import zipfile
from pathlib import Path

from genomeai.decision_log import init_decision_log
from genomeai.pack import build_pilot_pack
from genomeai.qc import run_qc
from genomeai.report import run_report
from genomeai.score import run_scoring
from genomeai.train import train_productivity_model


def _prep_canonical(tmp_path: Path, data_version: str) -> None:
    canonical_dir = tmp_path / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)

    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())


def test_a6_pack_builds_zip_and_manifest(tmp_path: Path) -> None:
    dv = "dv_test_pack"
    _prep_canonical(tmp_path, dv)

    qc = run_qc(data_version=dv, artifacts_root=tmp_path)
    assert qc["qc_status"] in {"PASS", "WARN"}
    qr = qc["qc_run"]

    tr = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qr)
    assert tr["ok"] is True
    mv = tr["model_version"]

    sc = run_scoring(artifacts_root=tmp_path, data_version=dv, model_version=mv)
    assert sc["ok"] is True
    sr = sc["scoring_run"]

    rep = run_report(
        artifacts_root=tmp_path,
        data_version=dv,
        qc_run=qr,
        model_version=mv,
        scoring_run=sr,
        mode="fallback",
        make_pdf=False,
    )
    assert rep["ok"] is True
    rv = rep["report_version"]

    # Ensure decision log exists
    paths = init_decision_log(artifacts_root=tmp_path, data_version=dv, scoring_run=sr, user="tester")
    assert Path(paths["csv"]).exists()

    pack = build_pilot_pack(
        artifacts_root=tmp_path,
        data_version=dv,
        qc_run=qr,
        model_version=mv,
        scoring_run=sr,
        report_version=rv,
    )
    assert pack["ok"] is True
    assert Path(pack["pack_zip"]).exists()
    assert Path(pack["pack_dir"]).exists()

    versions_json = Path(pack["pack_dir"]) / "versions.json"
    manifest_json = Path(pack["pack_dir"]) / "pack_manifest.json"
    assert versions_json.exists()
    assert manifest_json.exists()

    versions = json.loads(versions_json.read_text(encoding="utf-8"))
    assert versions["data_version"] == dv
    assert versions["qc_run"] == qr
    assert versions["model_version"] == mv
    assert versions["scoring_run"] == sr
    assert versions["report_version"] == rv

    # Zip contains decision log
    with zipfile.ZipFile(pack["pack_zip"], "r") as zf:
        names = set(zf.namelist())
        assert "decisions/decision_log.csv" in names
        assert "versions.json" in names
        assert "pack_manifest.json" in names
