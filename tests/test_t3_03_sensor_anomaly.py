from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from genomeai.alerts_v2 import generate_sensor_daily_rule_alerts
from genomeai.sensor_anomaly_v1 import detect_sensor_anomalies


def _mk_cow_day_for_animal(*, animal_id: str = "A1") -> pd.DataFrame:
    d0 = date(2025, 1, 1)
    rows = []
    # 28 days baseline
    for i in range(28):
        dt = d0 + timedelta(days=i)
        rows.append(
            {
                "farm_id": "F1",
                "animal_id": animal_id,
                "date": dt.isoformat(),
                "is_observed_sensors": True,
                "activity_steps": 10000,
                "rumination_min": 500,
                "body_temp_c": 38.5,
            }
        )
    return pd.DataFrame(rows)


def test_detect_outlier_temp_spike() -> None:
    cow = _mk_cow_day_for_animal()
    # temp spike on last day
    cow.loc[cow.index.max(), "body_temp_c"] = 41.0
    # add confirmation: previous day also high enough to pass confirmation
    cow.loc[cow.index.max() - 1, "body_temp_c"] = 40.8
    an = detect_sensor_anomalies(cow)
    assert not an.empty
    assert (an["anomaly_type"] == "temp_spike").any()


def test_detect_dropout_gap() -> None:
    cow = _mk_cow_day_for_animal()
    # last 3 days missing sensors
    cow.loc[cow.index.max() - 2 :, "is_observed_sensors"] = False
    an = detect_sensor_anomalies(cow)
    assert (an["anomaly_type"] == "data_dropout").any()


def test_generate_sensor_daily_rule_alerts_from_mart(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    run_dir = artifacts / "dv_demo" / "marts" / "marts_test"
    run_dir.mkdir(parents=True, exist_ok=True)

    cow = _mk_cow_day_for_animal(animal_id="A77")
    cow.loc[cow.index.max(), "body_temp_c"] = 41.0
    cow.loc[cow.index.max() - 1, "body_temp_c"] = 40.8
    cow.to_pickle(run_dir / "cow_day.pkl")

    alerts = generate_sensor_daily_rule_alerts(artifacts_root=artifacts, data_version="dv_demo")
    # should include TEMP_SPIKE alert
    assert any(a["alert_type"] == "SENSOR.TEMP_SPIKE" and a["object_id"] == "A77" for a in alerts)
