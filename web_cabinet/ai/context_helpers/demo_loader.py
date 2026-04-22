"""CSV-backed data store for demo/test use — mirrors the DB interface used by tools."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

_DEMO_DIR = Path(__file__).resolve().parents[4] / "data" / "demo" / "demo_farm_v1"


class DemoDataStore:
    """
    Loads demo farm CSVs on first access (lazy) and exposes them as DataFrames.

    In production the tools query Postgres via SQLAlchemy; in demo/test mode
    they receive a DemoDataStore injected via dependency.

    Use `DemoDataStore.from_dataframes(**frames)` to build a store from
    arbitrary DataFrames for tests.
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._dir: Optional[Path] = Path(base_dir) if base_dir else _DEMO_DIR
        self._cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # factory
    # ------------------------------------------------------------------

    @classmethod
    def from_dataframes(cls, **frames: pd.DataFrame) -> "DemoDataStore":
        """Build a store from pre-constructed DataFrames (for unit tests)."""
        store = cls.__new__(cls)
        store._dir = None
        store._cache = {k: v.copy() for k, v in frames.items()}
        return store

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _load(self, name: str) -> pd.DataFrame:
        if name not in self._cache:
            if self._dir is None:
                return pd.DataFrame()
            path = self._dir / f"{name}.csv"
            self._cache[name] = pd.read_csv(path) if path.exists() else pd.DataFrame()
        return self._cache[name]

    # ------------------------------------------------------------------
    # table accessors
    # ------------------------------------------------------------------

    def animals(self) -> pd.DataFrame:
        return self._load("dm_animals")

    def milkings(self) -> pd.DataFrame:
        return self._load("dm_milkings_daily")

    def lactations(self) -> pd.DataFrame:
        return self._load("dm_lactations")

    def testday(self) -> pd.DataFrame:
        return self._load("dm_testday")

    def sensors(self) -> pd.DataFrame:
        return self._load("dm_sensors_daily")

    def health_events(self) -> pd.DataFrame:
        return self._load("dm_health_events")

    def treatments(self) -> pd.DataFrame:
        return self._load("dm_treatments")

    def repro_events(self) -> pd.DataFrame:
        return self._load("dm_repro_events")

    def economics(self) -> pd.DataFrame:
        return self._load("dm_economics_daily")

    def prices(self) -> pd.DataFrame:
        return self._load("dm_prices")

    def farms(self) -> pd.DataFrame:
        return self._load("dm_farms")

    def alerts(self) -> pd.DataFrame:
        return self._load("dm_alerts")

    def pens(self) -> pd.DataFrame:
        return self._load("dm_pens")

    def pen_moves(self) -> pd.DataFrame:
        return self._load("dm_pen_moves")

    def decisions(self) -> pd.DataFrame:
        return self._load("dm_decisions")
