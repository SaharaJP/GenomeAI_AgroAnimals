from __future__ import annotations

import json
from pathlib import Path

from genomeai.qc_v2 import run_qc_v2


def _write_csv(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_qc2_registers_metadata_and_run_layout(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    data_version = "dv_reg"
    canonical = artifacts / data_version / "canonical"

    _write_csv(canonical / "dm_farms.csv", "farm_id\nF1\n")
    _write_csv(canonical / "dm_animals.csv", "farm_id,animal_id,birth_date,sex\nF1,A1,2030-01-01,F\n")

    result = run_qc_v2(
        artifacts_root=artifacts,
        data_version=data_version,
        rules_path=Path("configs/qc_rules_v2.yaml"),
        qc_run="qc2_test_reg",
    )

    outputs = result["outputs"]
    manifest_path = Path(outputs["metadata_manifest_json"])
    run_manifest_path = Path(outputs["run_manifest_json"])
    run_checksums_path = Path(outputs["run_checksums_json"])
    run_dir = Path(outputs["run_dir"])

    assert manifest_path.exists()
    assert run_manifest_path.exists()
    assert run_checksums_path.exists()
    assert run_dir.exists()
    assert (run_dir / "qc_summary.json").exists()
    assert (run_dir / "alerts_auto.csv").exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "genomeai.qc2_manifest.v1"
    assert manifest["latest"] == "qc2_test_reg"
    assert manifest["runs"]["qc2_test_reg"]["config_version"] == result["config_version"]
    assert manifest["runs"]["qc2_test_reg"]["qc_issues_csv"].endswith("/qc_issues.csv")

    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    assert run_manifest["step"] == "qc2"
    assert run_manifest["run_id"] == "qc2_test_reg"
    assert run_manifest["lineage"]["config_version"] == result["config_version"]
    assert run_manifest["outputs"]["alerts_auto_csv"].endswith("/alerts_auto.csv")

    checksums = json.loads(run_checksums_path.read_text(encoding="utf-8"))
    assert "qc2/qc_summary.json" in checksums["sha256"]
    assert "qc2/qc_issues.csv" in checksums["sha256"]
    assert "qc2/alerts_auto.csv" in checksums["sha256"]
