from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from genomeai.sensor_anomaly_v1 import detect_sensor_anomalies

_CSV = Path(__file__).parents[1] / "data" / "demo" / "investor_v1" / "dm_sensors_daily.csv"

# Expected: one anomaly per seeded cow, no others
_SEEDED = {
    "4821": "rumination_drop",  # Звёздочка: pre-mastitis rumination drop
    "3891": "data_dropout",     # Малина: sensor dropout (broken sensor)
    "3142": "temp_spike",       # Ночка: elevated body temperature
}


@pytest.mark.skipif(not _CSV.exists(), reason="dm_sensors_daily.csv not yet generated — run scripts/generate_synthetic_sensors.py")
def test_detect_sensor_anomalies_investor_v1_exactly_3_seeded() -> None:
    """detect_sensor_anomalies must find exactly the 3 seeded anomalies and nothing else."""
    df = pd.read_csv(_CSV)
    df = df.rename(columns={"activity_count": "activity_steps", "temperature_c": "body_temp_c"})
    df["farm_id"] = "INV_FARM_001"

    anomalies = detect_sensor_anomalies(df)

    found: dict[str, str] = {
        str(row["animal_id"]): str(row["anomaly_type"])
        for _, row in anomalies.iterrows()
    }

    assert len(anomalies) == 3, (
        f"Expected exactly 3 anomalies, got {len(anomalies)}.\n"
        f"Detected: {anomalies[['animal_id', 'anomaly_type']].to_string(index=False)}"
    )
    assert set(found.keys()) == set(_SEEDED.keys()), (
        f"Expected anomaly animals {set(_SEEDED.keys())}, got {set(found.keys())}"
    )
    for animal_id, expected_type in _SEEDED.items():
        assert found[animal_id] == expected_type, (
            f"Animal {animal_id}: expected {expected_type!r}, got {found[animal_id]!r}"
        )


def test_sensor_csv_exists_and_has_expected_shape() -> None:
    """dm_sensors_daily.csv must exist and cover 350 animals × 180 days."""
    assert _CSV.exists(), (
        "data/demo/investor_v1/dm_sensors_daily.csv is missing. "
        "Run: python scripts/generate_synthetic_sensors.py"
    )
    df = pd.read_csv(_CSV)
    n_animals = df["animal_id"].nunique()
    n_dates = df["date"].nunique()
    assert n_animals == 350, f"Expected 350 animals, got {n_animals}"
    assert n_dates == 180, f"Expected 180 dates, got {n_dates}"
    assert set(df.columns) >= {"animal_id", "date", "activity_count", "rumination_min", "lying_min", "temperature_c"}
