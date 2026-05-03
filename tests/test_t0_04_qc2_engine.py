from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.qc_v2 import run_qc_v2


def test_qc2_engine_produces_issues_and_alerts(tmp_path: Path):
    # Arrange: minimal canonical layer for dv
    dv = "dv_test"
    artifacts = tmp_path / "artifacts"
    canonical = artifacts / dv / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [{"farm_id": "F1", "farm_name": "Farm 1"}, {"farm_id": "F1", "farm_name": "Duplicate"}]
    ).to_csv(canonical / "dm_farms.csv", index=False)

    # animal references existing farm, but has duplicate PK to trigger
    pd.DataFrame(
        [
            {"farm_id": "F1", "animal_id": "A1", "birth_date": "2020-01-01"},
            {"farm_id": "F1", "animal_id": "A1", "birth_date": "2020-01-01"},
        ]
    ).to_csv(canonical / "dm_animals.csv", index=False)

    # Act
    res = run_qc_v2(
        data_version=dv,
        artifacts_root=artifacts,
        rules_path=Path("configs/qc_rules_v2.yaml"),
        qc_run="qc2_test",
    )

    # Assert
    assert res["qc_status"] in {"ERROR", "WARN", "PASS"}
    issues = pd.read_csv(res["outputs"]["qc_issues_csv"])
    assert len(issues) >= 2
    assert {"rule_id", "severity", "dataset"}.issubset(set(issues.columns))

    alerts = pd.read_csv(res["outputs"]["alerts_auto_csv"])
    # For PK duplicate rules: alerts should exist
    assert len(alerts) >= 1
    assert "alert_type" in alerts.columns
