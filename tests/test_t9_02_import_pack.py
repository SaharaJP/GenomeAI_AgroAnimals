from __future__ import annotations

import json
from pathlib import Path

from genomeai.migration_pack_import import import_pilot_pack
from genomeai.pack import build_pilot_pack


def _prep_minimal_layers(root: Path, *, dv: str, qc_run: str, mv: str, sr: str, rv: str) -> None:
    base = root / dv
    # canonical
    (base / "canonical").mkdir(parents=True, exist_ok=True)
    (base / "canonical" / "dm_farms.csv").write_text("farm_id\nF1\n", encoding="utf-8")

    # qc
    qc_dir = base / "qc" / qc_run
    qc_dir.mkdir(parents=True, exist_ok=True)
    (qc_dir / "summary.json").write_text("{\"ok\": true}\n", encoding="utf-8")

    # model
    model_dir = base / "models" / mv
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.bin").write_bytes(b"dummy-model")

    # scoring (decision log template expects scored_latest.csv optionally)
    scoring_dir = base / "scoring" / sr
    scoring_dir.mkdir(parents=True, exist_ok=True)
    (scoring_dir / "scored_latest.csv").write_text(
        "animal_id,lactation_no,action\nA1,1,OBSERVE\n",
        encoding="utf-8",
    )

    # report
    report_dir = base / "reports" / rv
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.docx").write_bytes(b"dummy-report")

    # decisions dir (will be filled by pack builder)
    (base / "decisions").mkdir(parents=True, exist_ok=True)


def test_t9_02_import_pack_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=True)

    dv = "dv_import_test"
    qc_run = "qc_test"
    mv = "model_test"
    sr = "scoring_test"
    rv = "report_test"

    _prep_minimal_layers(src, dv=dv, qc_run=qc_run, mv=mv, sr=sr, rv=rv)

    pack = build_pilot_pack(
        artifacts_root=src,
        data_version=dv,
        qc_run=qc_run,
        model_version=mv,
        scoring_run=sr,
        report_version=rv,
        pack_id="pilot_import_test",
    )
    assert pack.get("ok") is True

    pack_zip = Path(pack["pack_zip"]).resolve()
    assert pack_zip.exists()

    imp = import_pilot_pack(pack_zip=pack_zip, artifacts_root=dst, verify=True, force=False)
    assert imp.get("ok") is True

    base = dst / dv
    assert (base / "canonical").exists()
    assert (base / "qc" / qc_run).exists()
    assert (base / "models" / mv).exists()
    assert (base / "scoring" / sr).exists()
    assert (base / "reports" / rv).exists()
    assert (base / "decisions").exists()

    mf = Path(imp["import_manifest_json"])
    assert mf.exists()
    payload = json.loads(mf.read_text(encoding="utf-8"))
    assert payload.get("schema") == "genomeai.import_pilot_pack.v1"
