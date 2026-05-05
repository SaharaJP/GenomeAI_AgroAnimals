"""Sensor Bridge — facade for sensor anomaly detection from milking/health data."""
from __future__ import annotations

from web_cabinet.analytics.cache import cached

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

_DEMO_DATA = Path(__file__).parents[2] / "data" / "demo" / "investor_v1"


@dataclass
class SensorAnomaly:
    animal_id: Optional[str]
    farm_id: str
    anomaly_type: str  # "scc_spike", "yield_drop", "health_event"
    detected_at: date
    value: Optional[float]
    threshold: Optional[float]
    description: str


def detect_recent_sensor_anomalies(
    farm_id: str,
    *,
    lookback_days: int = 14,
) -> list[SensorAnomaly]:
    """Detect SCC spike and yield-drop anomalies over the lookback window.

    Falls back to demo CSV data. Returns empty list on any data error.
    Validation runs before the cache so an empty farm_id always raises.
    """
    if not farm_id:
        raise ValueError("farm_id must not be empty")
    return _detect_sensor_anomalies_cached(farm_id, lookback_days=lookback_days)


@cached(ttl=120)
def _detect_sensor_anomalies_cached(
    farm_id: str,
    *,
    lookback_days: int = 14,
) -> list[SensorAnomaly]:
    try:
        return _from_demo_csv(farm_id, lookback_days)
    except Exception:
        return []


def _from_demo_csv(farm_id: str, lookback_days: int) -> list[SensorAnomaly]:
    import pandas as pd

    today = date.today()
    cutoff = today - timedelta(days=lookback_days)
    anomalies: list[SensorAnomaly] = []

    mk_path = _DEMO_DATA / "dm_milkings_daily.csv"
    if not mk_path.exists():
        return []
    mk = pd.read_csv(mk_path)
    if mk.empty:
        return []

    # Tenant isolation: filter by tenant_id or farm_id column when present.
    _tenant_col = next((c for c in ("tenant_id", "farm_id") if c in mk.columns), None)
    if _tenant_col:
        mk = mk[mk[_tenant_col] == farm_id]
    if mk.empty:
        return []

    date_col = next((c for c in ("date", "milking_date") if c in mk.columns), None)
    if date_col:
        mk[date_col] = pd.to_datetime(mk[date_col], errors="coerce")
        recent = mk[mk[date_col] >= pd.Timestamp(cutoff)].copy()
    else:
        recent = mk.copy()

    # --- SCC spike: cells/mL > 200 000 ---
    if "scc_cells_ml" in recent.columns and date_col:
        scc_num = pd.to_numeric(recent["scc_cells_ml"], errors="coerce")
        high_scc = recent[scc_num > 200_000]
        for _, row in high_scc.head(20).iterrows():
            scc_val = float(pd.to_numeric(row["scc_cells_ml"], errors="coerce"))
            det = row[date_col].date() if pd.notna(row[date_col]) else today
            anomalies.append(
                SensorAnomaly(
                    animal_id=str(row.get("animal_id") or "") or None,
                    farm_id=farm_id,
                    anomaly_type="scc_spike",
                    detected_at=det,
                    value=round(scc_val / 1000, 1),
                    threshold=200.0,
                    description=f"SCC {round(scc_val / 1000)}k exceeds 200k threshold",
                )
            )

    # --- Yield drop: >10% decline vs prior 7-day window ---
    if "milk_kg" in mk.columns and date_col:
        recent_7d = mk[mk[date_col] >= pd.Timestamp(today - timedelta(days=7))]
        prior_7d = mk[
            (mk[date_col] >= pd.Timestamp(today - timedelta(days=14)))
            & (mk[date_col] < pd.Timestamp(today - timedelta(days=7)))
        ]
        if not recent_7d.empty and not prior_7d.empty:
            for animal_id in recent_7d["animal_id"].unique():
                r_avg = recent_7d[recent_7d["animal_id"] == animal_id]["milk_kg"].mean()
                p_avg = prior_7d[prior_7d["animal_id"] == animal_id]["milk_kg"].mean()
                if p_avg > 0 and (p_avg - r_avg) / p_avg > 0.10:
                    anomalies.append(
                        SensorAnomaly(
                            animal_id=str(animal_id),
                            farm_id=farm_id,
                            anomaly_type="yield_drop",
                            detected_at=today,
                            value=round(r_avg, 1),
                            threshold=round(p_avg * 0.9, 1),
                            description=(
                                f"Yield dropped {round((p_avg - r_avg) / p_avg * 100)}%"
                                " vs prior 7-day period"
                            ),
                        )
                    )

    return anomalies[:50]
