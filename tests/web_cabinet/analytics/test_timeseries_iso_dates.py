"""Verifies that the analytics timeseries builders include `iso_dates`
parallel to `labels`, so frontend QC/event overlays can align by date
against the chart's actual date axis.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

import pytest

from web_cabinet.analytics.timeseries_bridge import (
    _empty_production,
    build_health_timeseries,
    build_production_timeseries,
    build_reproduction_timeseries,
)


class _DictRow(dict):
    """Row supporting both dict-style and tuple-style access via __getitem__."""

    def __getitem__(self, key: Any):  # noqa: D401
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _sql, _params):
        return _FakeCursor(self._rows)


def test_empty_production_has_iso_dates() -> None:
    payload = _empty_production()
    assert "iso_dates" in payload
    for chart in payload["charts"].values():
        assert "iso_dates" in chart
        assert chart["iso_dates"] == []


def test_production_iso_dates_parallel_to_labels() -> None:
    today = _dt.date.today()
    rows = [
        _DictRow(
            date=today - _dt.timedelta(days=days),
            avg_milk=30.0,
            avg_fat=4.0,
            avg_protein=3.3,
            avg_scc=180_000,
        )
        for days in (28, 21, 14, 7, 0)
    ]
    payload = build_production_timeseries(_FakeConn(rows), farm_id="F1")

    labels = payload["labels"]
    iso_dates = payload["iso_dates"]
    assert len(labels) == len(iso_dates), "labels and iso_dates must have equal length"
    assert all(len(s) == 10 for s in iso_dates), "iso_dates must be YYYY-MM-DD"
    # Each iso_date must parse to a Monday (weekday 0)
    for s in iso_dates:
        assert _dt.date.fromisoformat(s).weekday() == 0
    # Per-chart parallel arrays must mirror tab-level
    for chart_id, chart in payload["charts"].items():
        assert chart["iso_dates"] == iso_dates, f"chart {chart_id} iso_dates drifted"


def test_health_iso_dates_parallel_to_labels() -> None:
    today = _dt.date.today()
    rows = [
        _DictRow(event_date=today - _dt.timedelta(days=d), event_type="mastitis")
        for d in (35, 21, 7)
    ]
    payload = build_health_timeseries(_FakeConn(rows), farm_id="F1")
    assert "iso_dates" in payload
    assert len(payload["labels"]) == len(payload["iso_dates"])


def test_reproduction_iso_dates_parallel_to_labels() -> None:
    today = _dt.date.today()
    rows = [
        _DictRow(event_date=today - _dt.timedelta(days=d), event_type="insemination", result="pregnant")
        for d in (28, 14, 0)
    ]
    payload = build_reproduction_timeseries(_FakeConn(rows), farm_id="F1")
    assert "iso_dates" in payload
    assert len(payload["labels"]) == len(payload["iso_dates"])


@pytest.mark.parametrize("builder", [build_health_timeseries, build_reproduction_timeseries])
def test_empty_health_repro_have_iso_dates(builder) -> None:
    payload = builder(_FakeConn([]), farm_id="F1")
    assert payload["iso_dates"] == []
    for chart in payload["charts"].values():
        assert chart["iso_dates"] == []
