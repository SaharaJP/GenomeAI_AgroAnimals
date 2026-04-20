from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from genomeai.alerts_v2 import generate_from_qc2


DV = "dv_t15_06_alerts"
QC_RUN = "qc2_20990101_000000_test"


def _write_qc2_alerts(run_dir: Path, *, message: str, rule_id: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "tenant_id": "default",
                "alert_id": f"al_{rule_id}",
                "farm_id": "F1",
                "alert_date": "2099-01-01",
                "severity": "MAJOR",
                "alert_type": "QC.PK_DUPLICATE",
                "entity_type": "dataset",
                "entity_id": "dm_animals",
                "message": message,
                "source_rule_id": rule_id,
                "qc_run": QC_RUN,
                "data_version": DV,
            }
        ]
    ).to_csv(run_dir / "alerts_auto.csv", index=False)


def test_generate_from_qc2_supports_canonical_layout(tmp_path: Path):
    artifacts_root = tmp_path / "artifacts"
    canonical_run_dir = artifacts_root / DV / "qc2" / QC_RUN
    _write_qc2_alerts(canonical_run_dir, message="Duplicate animal_id", rule_id="pk_animals")

    out = generate_from_qc2(artifacts_root=artifacts_root, data_version=DV, today=date(2099, 1, 1))

    assert len(out) == 1
    alert = out[0]
    assert alert["qc_run"] == QC_RUN
    assert alert["data_version"] == DV
    assert alert["cause"] == "Duplicate animal_id"
    assert alert["why"]["qc_rule_id"] == "pk_animals"
    assert str(canonical_run_dir / "alerts_auto.csv") == alert["attachments"][0]["path"]


def test_generate_from_qc2_prefers_canonical_layout_over_legacy(tmp_path: Path):
    artifacts_root = tmp_path / "artifacts"
    canonical_run_dir = artifacts_root / DV / "qc2" / QC_RUN
    legacy_run_dir = artifacts_root / "qc2" / DV / QC_RUN
    _write_qc2_alerts(canonical_run_dir, message="Canonical qc2 alert", rule_id="canonical_rule")
    _write_qc2_alerts(legacy_run_dir, message="Legacy qc2 alert", rule_id="legacy_rule")

    out = generate_from_qc2(artifacts_root=artifacts_root, data_version=DV, today=date(2099, 1, 1))

    assert len(out) == 1
    alert = out[0]
    assert alert["cause"] == "Canonical qc2 alert"
    assert alert["why"]["qc_rule_id"] == "canonical_rule"
    assert str(canonical_run_dir / "alerts_auto.csv") == alert["attachments"][0]["path"]
