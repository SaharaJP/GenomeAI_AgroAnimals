"""Sensor Bridge — facade between sensor_anomaly_v1 and the web_cabinet UI.

Loads sensor data (from demo CSV or, in future, a SQL datasource), runs
``detect_sensor_anomalies``, and returns UI-friendly ``SensorAnomalyAlert``
objects.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Optional

import pandas as pd

from genomeai.sensor_anomaly_v1 import DetectorConfig, detect_sensor_anomalies

_DEMO_SENSORS_CSV = (
    Path(__file__).parents[3] / "data" / "demo" / "demo_farm_v1" / "dm_sensors_daily.csv"
)


@dataclass
class SensorAnomalyAlert:
    animal_id: str
    metric: str          # "activity_count", "rumination_min", "body_temp_c"
    anomaly_type: Literal["data_dropout", "outlier", "baseline_drift"]
    detected_at: date
    severity: Literal["critical", "warning", "info"]
    raw_data: dict


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_severity(row: "pd.Series") -> Literal["critical", "warning", "info"]:
    """Map anomaly_type (and score for outliers) to UI severity."""
    anomaly_type = row.get("anomaly_type", "")
    if anomaly_type == "data_dropout":
        return "critical"
    if anomaly_type == "outlier":
        try:
            score = float(row.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0.0
        return "critical" if abs(score) > 5.0 else "warning"
    if anomaly_type == "baseline_drift":
        return "warning"
    # catch-all for any other anomaly types produced by the detector
    return "warning"


def _row_to_alert(row: "pd.Series", farm_id: str) -> SensorAnomalyAlert:
    """Convert a single anomaly DataFrame row to a SensorAnomalyAlert."""
    details = row.get("details_json", {})
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = {}
    if details is None:
        details = {}

    detected_at = row.get("date")
    if not isinstance(detected_at, date):
        try:
            detected_at = pd.to_datetime(detected_at).date()
        except Exception:
            detected_at = date.today()

    raw_data: dict = {
        "farm_id": farm_id,
        "animal_id": str(row.get("animal_id", "")),
        "metric": str(row.get("metric", "")),
        "anomaly_type": str(row.get("anomaly_type", "")),
        "score": row.get("score"),
        "detector_severity": row.get("severity"),
        **details,
    }

    return SensorAnomalyAlert(
        animal_id=str(row.get("animal_id", "")),
        metric=str(row.get("metric", "")),
        anomaly_type=row.get("anomaly_type", "outlier"),
        detected_at=detected_at,
        severity=_compute_severity(row),
        raw_data=raw_data,
    )


def _load_sensor_df(farm_id: str, lookback_days: int) -> pd.DataFrame:
    """Load and prepare sensor data for the given farm and lookback window.

    Returns an empty DataFrame when no data source is available or the farm_id
    is not found in the demo data.
    """
    if os.environ.get("GENOMEAI_DB_DSN"):
        # Production path: SQL datasource not yet implemented.
        raise NotImplementedError(
            "SQL-backed sensor loading is not implemented in dev mode. "
            "Unset GENOMEAI_DB_DSN to use the demo CSV."
        )

    # Demo path: read from CSV
    if not _DEMO_SENSORS_CSV.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(_DEMO_SENSORS_CSV)
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Column mapping
    rename_map: dict[str, str] = {}
    if "activity_count" in df.columns:
        rename_map["activity_count"] = "activity_steps"
    if "temperature_c" in df.columns:
        rename_map["temperature_c"] = "body_temp_c"
    if rename_map:
        df = df.rename(columns=rename_map)

    df["farm_id"] = farm_id
    df["is_observed_sensors"] = True

    # Parse dates
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"])

    # Apply lookback filter
    cutoff = date.today() - timedelta(days=lookback_days)
    df = df[df["date"] >= cutoff]

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_recent_sensor_anomalies(
    farm_id: str,
    lookback_days: int = 30,
    cfg: Optional[DetectorConfig] = None,
) -> list[SensorAnomalyAlert]:
    """Load sensor data, run detect_sensor_anomalies, return SensorAnomalyAlert list.

    Returns an empty list when:
    - No data file is found
    - The farm_id yields no data rows
    - The detector finds no anomalies (expected for small demo datasets)
    - Any unexpected error occurs during loading or detection
    """
    try:
        df = _load_sensor_df(farm_id, lookback_days)
    except NotImplementedError:
        raise
    except Exception:
        return []

    if df is None or df.empty:
        return []

    try:
        anomalies_df = detect_sensor_anomalies(df, cfg=cfg or DetectorConfig())
    except Exception:
        return []

    if anomalies_df is None or anomalies_df.empty:
        return []

    alerts: list[SensorAnomalyAlert] = []
    for _, row in anomalies_df.iterrows():
        try:
            alerts.append(_row_to_alert(row, farm_id))
        except Exception:
            continue

    return alerts
