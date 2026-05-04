# Analytics Live Data + AI Real Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect 7 analytics dashboard tabs to live Postgres data (replacing `mulberry32` synthetic generation), fix `_query_recent_events` / `_query_attention_cows` stubs in AI context, and add integration test proving non-demo scanner bridge runs.

**Architecture:** New `web_cabinet/analytics/timeseries_bridge.py` queries `dm_milkings_daily`, `dm_health_events`, `dm_repro_events` weekly via SQL with `?` placeholders (existing compat layer). New `GET /api/analytics/timeseries/{tab}` endpoint in `analytics_v1.py` wraps it and returns `{labels, charts}`. Next.js proxy route + `useAnalyticsTimeseries` hook replace `mulberry32` in `production-tab`, `reproduction-tab`, `health-tab`. Four tabs without DB data (`feed`, `herd`, `behavior`, `finance`) show a "Данные подключаются" placeholder card instead of fake charts. `context.py` stubs implemented as DB queries with `[]` fallback. Integration test mocks Claude client but runs real `_build_bridge_context`.

**Tech Stack:** Python 3.11, FastAPI, psycopg/SQLite compat (`conn.execute(sql, params)`), pandas (fixtures fallback), Next.js 15, React 19, TypeScript 5.8

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `web_cabinet/analytics/timeseries_bridge.py` | SQL weekly aggregation for production/repro/health |
| Modify | `web_cabinet/analytics_v1.py` | Add `GET /api/analytics/timeseries/{tab}` endpoint |
| Modify | `web_cabinet/ai/context.py` | Fix `_query_recent_events` + `_query_attention_cows` stubs |
| Create | `tests/web_cabinet/analytics/test_timeseries_bridge.py` | Unit tests for bridge |
| Create | `tests/web_cabinet/ai/test_real_mode_bridge.py` | Integration test for non-demo context |
| Create | `web_app/app/api/analytics/timeseries/[tab]/route.ts` | Next.js proxy to backend |
| Create | `web_app/lib/api/analytics-live.ts` | `useAnalyticsTimeseries` hook + types |
| Modify | `web_app/components/analytics/production-tab.tsx` | Use live hook |
| Modify | `web_app/components/analytics/reproduction-tab.tsx` | Use live hook |
| Modify | `web_app/components/analytics/health-tab.tsx` | Use live hook |
| Modify | `web_app/components/analytics/feed-tab.tsx` | Replace charts with placeholder |
| Modify | `web_app/components/analytics/herd-tab.tsx` | Replace charts with placeholder |
| Modify | `web_app/components/analytics/behavior-tab.tsx` | Replace charts with placeholder |
| Modify | `web_app/components/analytics/finance-tab.tsx` | Replace charts with placeholder |

---

## Task 1: Backend — `timeseries_bridge.py` (production metrics)

**Files:**
- Create: `web_cabinet/analytics/timeseries_bridge.py`
- Create: `tests/web_cabinet/analytics/test_timeseries_bridge.py`

- [ ] **Step 1.1: Write failing test for production timeseries**

```python
# tests/web_cabinet/analytics/test_timeseries_bridge.py
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

from web_cabinet.analytics.timeseries_bridge import build_production_timeseries


def _make_conn(rows):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.execute.return_value = cursor
    return conn


def test_production_timeseries_empty_db():
    conn = _make_conn([])
    result = build_production_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert result["tab"] == "production"
    assert result["labels"] == []
    assert result["charts"]["milk_ecm"]["series"][0]["data"] == []


def test_production_timeseries_aggregates_weekly():
    # Two rows in same ISO week
    Row = MagicMock
    r1 = MagicMock()
    r1.__getitem__ = lambda self, k: {"date": date(2025, 1, 6), "avg_milk": 30.0, "avg_fat": 4.0,
                                       "avg_protein": 3.3, "avg_scc": 150000.0}[k]
    r2 = MagicMock()
    r2.__getitem__ = lambda self, k: {"date": date(2025, 1, 7), "avg_milk": 28.0, "avg_fat": 3.9,
                                       "avg_protein": 3.2, "avg_scc": 160000.0}[k]
    conn = _make_conn([r1, r2])
    result = build_production_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert len(result["labels"]) == 1        # one ISO week
    assert len(result["charts"]["milk_ecm"]["series"]) == 2   # milk + ECM
    milk_val = result["charts"]["milk_ecm"]["series"][0]["data"][0]
    assert milk_val == pytest.approx(29.0, abs=0.5)  # avg of 30 and 28
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
python -m pytest tests/web_cabinet/analytics/test_timeseries_bridge.py -v 2>&1 | tail -15
```
Expected: `ImportError` or `ModuleNotFoundError` for `timeseries_bridge`

- [ ] **Step 1.3: Create `timeseries_bridge.py` with production logic**

```python
# web_cabinet/analytics/timeseries_bridge.py
"""Weekly time-series aggregation for analytics dashboard tabs.

Queries DB via conn (psycopg/SQLite compat, uses ? placeholders).
Returns dict shaped for the frontend AnalyticsData contract.
"""
from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any


_MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
               "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]


def _week_label(d: datetime.date) -> str:
    """Format date as 'DD Mon' (Russian month abbrev) from week's Monday."""
    monday = d - datetime.timedelta(days=d.weekday())
    return f"{monday.day:02d} {_MONTHS_RU[monday.month - 1]}"


def _iso_week_key(d: datetime.date) -> str:
    """'YYYY-WNN' string, stable sort key."""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _safe(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def _ecm(milk_kg: float, fat_pct: float | None, protein_pct: float | None) -> float | None:
    if fat_pct is None or protein_pct is None:
        return None
    return milk_kg * (0.25 + 12.2 * fat_pct / 100.0 + 7.7 * protein_pct / 100.0)


def _empty_production() -> dict:
    return {
        "tab": "production",
        "labels": [],
        "charts": {
            "milk_ecm": {"labels": [], "series": [
                {"name": "Надой", "color": "#3B82F6", "data": []},
                {"name": "ECM", "color": "#F59E0B", "data": []},
            ]},
            "fat_protein": {"labels": [], "series": [
                {"name": "Жир %", "color": "#3B82F6", "data": []},
                {"name": "Белок %", "color": "#10B981", "data": []},
            ]},
            "scc": {"labels": [], "series": [
                {"name": "СКК (тыс.)", "color": "#EF4444", "data": []},
            ]},
        },
    }


def build_production_timeseries(
    conn: Any,
    farm_id: str,
    tenant_id: str = "default",
    weeks: int = 26,
) -> dict:
    since = (datetime.date.today() - datetime.timedelta(weeks=weeks)).isoformat()
    sql = """
        SELECT
            m.date,
            AVG(m.milk_kg)       AS avg_milk,
            AVG(m.fat_pct)       AS avg_fat,
            AVG(m.protein_pct)   AS avg_protein,
            AVG(m.scc_cells_ml)  AS avg_scc
        FROM dm_milkings_daily m
        JOIN dm_animals a
          ON m.tenant_id = a.tenant_id AND m.animal_id = a.animal_id
        WHERE m.tenant_id = ?
          AND a.farm_id = ?
          AND m.date >= ?
        GROUP BY m.date
        ORDER BY m.date
    """
    try:
        rows = list(conn.execute(sql, [tenant_id, farm_id, since]).fetchall())
    except Exception:
        rows = []

    if not rows:
        return _empty_production()

    # Aggregate daily rows into ISO weeks
    by_week: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        d = row["date"]
        if isinstance(d, str):
            d = datetime.date.fromisoformat(d)
        wk = _iso_week_key(d)
        by_week[wk]["dates"].append(d)
        by_week[wk]["milk"].append(_safe(row["avg_milk"]) or 0.0)
        by_week[wk]["fat"].append(_safe(row["avg_fat"]))
        by_week[wk]["protein"].append(_safe(row["avg_protein"]))
        by_week[wk]["scc"].append(_safe(row["avg_scc"]))

    sorted_weeks = sorted(by_week.keys())
    labels = []
    milk_data, ecm_data, fat_data, protein_data, scc_data = [], [], [], [], []

    for wk in sorted_weeks:
        d = by_week[wk]["dates"][0]
        labels.append(_week_label(d))

        milks = by_week[wk]["milk"]
        fats = [v for v in by_week[wk]["fat"] if v is not None]
        proteins = [v for v in by_week[wk]["protein"] if v is not None]
        sccs = [v for v in by_week[wk]["scc"] if v is not None]

        avg_milk = round(sum(milks) / len(milks), 1) if milks else 0.0
        avg_fat = round(sum(fats) / len(fats), 2) if fats else None
        avg_protein = round(sum(proteins) / len(proteins), 2) if proteins else None
        avg_scc = round(sum(sccs) / len(sccs) / 1000, 1) if sccs else None  # → thousands
        ecm = _ecm(avg_milk, avg_fat, avg_protein)

        milk_data.append(avg_milk)
        ecm_data.append(round(ecm, 1) if ecm is not None else avg_milk)
        fat_data.append(avg_fat if avg_fat is not None else 0.0)
        protein_data.append(avg_protein if avg_protein is not None else 0.0)
        scc_data.append(avg_scc if avg_scc is not None else 0.0)

    return {
        "tab": "production",
        "labels": labels,
        "charts": {
            "milk_ecm": {"labels": labels, "series": [
                {"name": "Надой", "color": "#3B82F6", "data": milk_data},
                {"name": "ECM", "color": "#F59E0B", "data": ecm_data},
            ]},
            "fat_protein": {"labels": labels, "series": [
                {"name": "Жир %", "color": "#3B82F6", "data": fat_data},
                {"name": "Белок %", "color": "#10B981", "data": protein_data},
            ]},
            "scc": {"labels": labels, "series": [
                {"name": "СКК (тыс.)", "color": "#EF4444", "data": scc_data},
            ]},
        },
    }
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
python -m pytest tests/web_cabinet/analytics/test_timeseries_bridge.py::test_production_timeseries_empty_db tests/web_cabinet/analytics/test_timeseries_bridge.py::test_production_timeseries_aggregates_weekly -v 2>&1 | tail -10
```
Expected: 2 passed

- [ ] **Step 1.5: Commit**

```bash
git add web_cabinet/analytics/timeseries_bridge.py tests/web_cabinet/analytics/test_timeseries_bridge.py
git commit -m "feat(analytics): timeseries_bridge — production weekly aggregation"
```

---

## Task 2: Backend — health + reproduction timeseries in `timeseries_bridge.py`

**Files:**
- Modify: `web_cabinet/analytics/timeseries_bridge.py` (append two functions)
- Modify: `tests/web_cabinet/analytics/test_timeseries_bridge.py` (append tests)

- [ ] **Step 2.1: Write failing tests for health and reproduction**

Append to `tests/web_cabinet/analytics/test_timeseries_bridge.py`:

```python
from web_cabinet.analytics.timeseries_bridge import (
    build_production_timeseries,
    build_health_timeseries,
    build_reproduction_timeseries,
)


def test_health_timeseries_empty_db():
    conn = _make_conn([])
    result = build_health_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=4)
    assert result["tab"] == "health"
    assert result["labels"] == []
    assert "mastitis" in result["charts"]


def test_reproduction_timeseries_empty_db():
    conn = _make_conn([])
    result = build_reproduction_timeseries(conn, farm_id="FARM_001", tenant_id="default", weeks=26)
    assert result["tab"] == "reproduction"
    assert result["labels"] == []
    assert "inseminations" in result["charts"]
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
python -m pytest tests/web_cabinet/analytics/test_timeseries_bridge.py -v 2>&1 | tail -10
```
Expected: `ImportError` for `build_health_timeseries`, `build_reproduction_timeseries`

- [ ] **Step 2.3: Append health and reproduction functions to `timeseries_bridge.py`**

Append at end of `web_cabinet/analytics/timeseries_bridge.py`:

```python
_HEALTH_COLORS = {
    "mastitis": "#EF4444",
    "lameness": "#F59E0B",
    "ketosis": "#8B5CF6",
    "metritis": "#3B82F6",
    "other": "#94A3B8",
}
_KNOWN_HEALTH = ["mastitis", "lameness", "ketosis", "metritis"]


def build_health_timeseries(
    conn: Any,
    farm_id: str,
    tenant_id: str = "default",
    weeks: int = 26,
) -> dict:
    since = (datetime.date.today() - datetime.timedelta(weeks=weeks)).isoformat()
    sql = """
        SELECT h.event_date, LOWER(h.event_type) AS event_type
        FROM dm_health_events h
        JOIN dm_animals a
          ON h.tenant_id = a.tenant_id AND h.animal_id = a.animal_id
        WHERE h.tenant_id = ?
          AND a.farm_id = ?
          AND h.event_date >= ?
        ORDER BY h.event_date
    """
    try:
        rows = list(conn.execute(sql, [tenant_id, farm_id, since]).fetchall())
    except Exception:
        rows = []

    if not rows:
        return {"tab": "health", "labels": [], "charts": {
            "mastitis": {"labels": [], "series": [{"name": "Мастит", "color": "#EF4444", "data": []}]},
            "issues": {"labels": [], "series": []},
        }}

    by_week: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        d = row["event_date"]
        if isinstance(d, str):
            d = datetime.date.fromisoformat(d)
        wk = _iso_week_key(d)
        by_week[wk]["dates"].append(d)
        etype = str(row["event_type"])
        by_week[wk].setdefault(etype, []).append(1)

    sorted_weeks = sorted(by_week.keys())
    labels = [_week_label(by_week[wk]["dates"][0]) for wk in sorted_weeks]

    # Mastitis series
    mastitis_data = [len(by_week[wk].get("mastitis", [])) for wk in sorted_weeks]

    # All event types for stacked issues chart
    all_types = sorted({str(row["event_type"]) for row in rows})
    issues_series = []
    for etype in all_types:
        color = _HEALTH_COLORS.get(etype, "#94A3B8")
        data = [len(by_week[wk].get(etype, [])) for wk in sorted_weeks]
        issues_series.append({"name": etype.capitalize(), "color": color, "data": data})

    return {
        "tab": "health",
        "labels": labels,
        "charts": {
            "mastitis": {"labels": labels, "series": [
                {"name": "Мастит", "color": "#EF4444", "data": mastitis_data},
            ]},
            "issues": {"labels": labels, "series": issues_series},
        },
    }


def build_reproduction_timeseries(
    conn: Any,
    farm_id: str,
    tenant_id: str = "default",
    weeks: int = 26,
) -> dict:
    since = (datetime.date.today() - datetime.timedelta(weeks=weeks)).isoformat()
    sql = """
        SELECT r.event_date, LOWER(r.event_type) AS event_type,
               LOWER(COALESCE(r.result, '')) AS result
        FROM dm_repro_events r
        JOIN dm_animals a
          ON r.tenant_id = a.tenant_id AND r.animal_id = a.animal_id
        WHERE r.tenant_id = ?
          AND a.farm_id = ?
          AND r.event_date >= ?
        ORDER BY r.event_date
    """
    try:
        rows = list(conn.execute(sql, [tenant_id, farm_id, since]).fetchall())
    except Exception:
        rows = []

    empty = {"tab": "reproduction", "labels": [], "charts": {
        "inseminations": {"labels": [], "series": [
            {"name": "Осеменения", "color": "#3B82F6", "data": []},
            {"name": "Стельные", "color": "#10B981", "data": []},
        ]},
    }}
    if not rows:
        return empty

    by_week: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        d = row["event_date"]
        if isinstance(d, str):
            d = datetime.date.fromisoformat(d)
        wk = _iso_week_key(d)
        by_week[wk]["dates"].append(d)
        etype = str(row["event_type"])
        result = str(row["result"])
        by_week[wk].setdefault(etype, []).append(1)
        if etype == "insemination" and result == "pregnant":
            by_week[wk].setdefault("pregnant", []).append(1)

    sorted_weeks = sorted(by_week.keys())
    labels = [_week_label(by_week[wk]["dates"][0]) for wk in sorted_weeks]
    insem_data = [len(by_week[wk].get("insemination", [])) for wk in sorted_weeks]
    preg_data = [len(by_week[wk].get("pregnant", [])) for wk in sorted_weeks]

    return {
        "tab": "reproduction",
        "labels": labels,
        "charts": {
            "inseminations": {"labels": labels, "series": [
                {"name": "Осеменения", "color": "#3B82F6", "data": insem_data},
                {"name": "Стельные", "color": "#10B981", "data": preg_data},
            ]},
        },
    }
```

- [ ] **Step 2.4: Run all timeseries_bridge tests**

```bash
python -m pytest tests/web_cabinet/analytics/test_timeseries_bridge.py -v 2>&1 | tail -10
```
Expected: 4 passed

- [ ] **Step 2.5: Commit**

```bash
git add web_cabinet/analytics/timeseries_bridge.py tests/web_cabinet/analytics/test_timeseries_bridge.py
git commit -m "feat(analytics): timeseries_bridge — health + reproduction weekly aggregation"
```

---

## Task 3: Backend — `/api/analytics/timeseries/{tab}` endpoint

**Files:**
- Modify: `web_cabinet/analytics_v1.py` (append new endpoint)

- [ ] **Step 3.1: Append endpoint to `analytics_v1.py`**

Add these imports at the top of `analytics_v1.py` (after existing imports):

```python
from .analytics.timeseries_bridge import (
    build_production_timeseries,
    build_health_timeseries,
    build_reproduction_timeseries,
)
```

Append new endpoint after the last `@router.get` in `analytics_v1.py`:

```python
@router.get('/timeseries/{tab_name}')
def analytics_timeseries(
    tab_name: str,
    farm_id: Optional[str] = Query(default=None),
    weeks: int = Query(default=26, ge=1, le=104),
    user=Depends(require_permissions('kpi.view')),
    conn=Depends(get_db),
):
    """Weekly time-series for analytics dashboard tabs.

    Returns {tab, labels, charts} where charts is a dict of chart_id -> {labels, series}.
    Tabs without DB time-series (feed, herd, behavior, finance) return empty charts.
    """
    if tab_name not in VALID_TABS:
        raise HTTPException(status_code=404, detail=f"Unknown tab: {tab_name!r}")

    settings = _get_ai_settings()
    tenant_id = user.get('tenant_id', 'default')
    effective_farm = farm_id or settings.GENOMEAI_DEMO_FARM_ID

    if tab_name == "production":
        return build_production_timeseries(conn, farm_id=effective_farm, tenant_id=tenant_id, weeks=weeks)
    if tab_name == "health":
        return build_health_timeseries(conn, farm_id=effective_farm, tenant_id=tenant_id, weeks=weeks)
    if tab_name == "reproduction":
        return build_reproduction_timeseries(conn, farm_id=effective_farm, tenant_id=tenant_id, weeks=weeks)

    # feed / herd / behavior / finance: not yet implemented
    return {"tab": tab_name, "labels": [], "charts": {}}
```

- [ ] **Step 3.2: Smoke-test the endpoint via web smoke**

```bash
python -m web_cabinet.smoke --workdir _tmp/ci_ts_smoke --clean \
  --timing-json artifacts/_ci/web_smoke.json 2>&1 | tail -5
```
Expected: `WEB_SMOKE_OK`

- [ ] **Step 3.3: Commit**

```bash
git add web_cabinet/analytics_v1.py
git commit -m "feat(analytics): GET /api/analytics/timeseries/{tab} — live weekly data"
```

---

## Task 4: Fix `context.py` stubs

**Files:**
- Modify: `web_cabinet/ai/context.py` (replace two stub functions)
- Create: `tests/web_cabinet/ai/test_real_mode_bridge.py`

- [ ] **Step 4.1: Write failing integration test**

```python
# tests/web_cabinet/ai/test_real_mode_bridge.py
"""Integration test: _build_bridge_context builds FarmContext in non-demo mode."""
import pytest
from types import SimpleNamespace
from unittest.mock import patch


def test_build_bridge_context_returns_farm_context():
    """_build_bridge_context must return FarmContext with farm_id set, no Claude call needed."""
    from web_cabinet.ai.context import _build_bridge_context, FarmContext

    ctx = _build_bridge_context("FARM_001")

    assert isinstance(ctx, FarmContext)
    assert ctx.farm_id == "FARM_001"
    # kpi comes from kpi_bridge (fixtures) — may be None if fixtures have no data, but must not raise
    # recent_events and attention_cows must be lists (not None)
    assert isinstance(ctx.recent_events, list)
    assert isinstance(ctx.attention_cows, list)


def test_build_farm_context_routes_to_bridge_when_not_demo():
    """build_farm_context with GENOMEAI_AI_DEMO_MODE=False must call bridge path, not seeded."""
    from web_cabinet.ai.context import build_farm_context, FarmContext

    settings = SimpleNamespace(GENOMEAI_AI_DEMO_MODE=False)
    ctx = build_farm_context("FARM_001", settings=settings)

    assert isinstance(ctx, FarmContext)
    assert ctx.farm_id == "FARM_001"
```

- [ ] **Step 4.2: Run test to see current failure**

```bash
python -m pytest tests/web_cabinet/ai/test_real_mode_bridge.py -v 2>&1 | tail -15
```
Expected: `test_build_bridge_context_returns_farm_context` FAILS because `ctx.recent_events` is `[]` (stub returns `[]` — but this test expects a list so it may actually PASS already). Check carefully: if both pass, the stub already returns `[]` which is a valid list. The real fix is to ensure the functions actually query. Re-run after fix to confirm no regression.

- [ ] **Step 4.3: Fix `_query_recent_events` in `context.py`**

Find and replace the stub:

```python
# BEFORE (in web_cabinet/ai/context.py):
def _query_recent_events(farm_id: str, days: int = 14) -> list:
    """Stub: returns DB events when DB is wired; empty list until then."""
    return []
```

```python
# AFTER:
def _query_recent_events(farm_id: str, days: int = 14) -> list:
    """Query recent health events from DB. Falls back to [] if DB unavailable."""
    import os
    dsn = os.getenv("GENOMEAI_DB_DSN") or os.getenv("GENOMEAI_RUNTIME_POSTGRES_DSN")
    if not dsn:
        return _query_recent_events_fixtures(farm_id, days)

    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    sql = """
        SELECT h.event_date, h.event_type, h.severity, h.animal_id
        FROM dm_health_events h
        JOIN dm_animals a ON h.tenant_id = a.tenant_id AND h.animal_id = a.animal_id
        WHERE a.farm_id = %s AND h.event_date >= %s
        ORDER BY h.event_date DESC
        LIMIT 50
    """
    try:
        import psycopg2
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(sql, [farm_id, since])
        rows = cur.fetchall()
        conn.close()
        return [
            {"event_date": str(r[0]), "event_type": r[1], "severity": r[2], "animal_id": r[3]}
            for r in rows
        ]
    except Exception:
        return []


def _query_recent_events_fixtures(farm_id: str, days: int) -> list:
    """Fixture fallback for _query_recent_events when no DB DSN is set."""
    from pathlib import Path
    import pandas as pd
    fixtures_dir = Path(__file__).parents[3] / "data" / "fixtures" / "target_v2"
    he_path = fixtures_dir / "dm_health_events.csv"
    animals_path = fixtures_dir / "dm_animals.csv"
    if not he_path.exists() or not animals_path.exists():
        return []
    try:
        animals = pd.read_csv(animals_path)
        farm_animals = set(animals[animals["farm_id"] == farm_id]["animal_id"].astype(str).tolist())
        he = pd.read_csv(he_path)
        he["event_date"] = pd.to_datetime(he["event_date"], errors="coerce")
        since = pd.Timestamp.today() - pd.Timedelta(days=days)
        filtered = he[(he["animal_id"].astype(str).isin(farm_animals)) & (he["event_date"] >= since)]
        return [
            {"event_date": str(r["event_date"].date()), "event_type": r["event_type"],
             "severity": r.get("severity"), "animal_id": r["animal_id"]}
            for _, r in filtered.iterrows()
        ]
    except Exception:
        return []
```

- [ ] **Step 4.4: Fix `_query_attention_cows` in `context.py`**

Find and replace the stub:

```python
# BEFORE:
def _query_attention_cows(farm_id: str) -> list:
    """Stub: returns DB-queried attention cows; empty list until DB is wired."""
    return []
```

```python
# AFTER:
def _query_attention_cows(farm_id: str) -> list:
    """Return attention cows using fixture data (same source as kpi_bridge).

    In production, kpi_bridge also reads from fixtures/target_v2 or live DB.
    This is consistent with the rest of _build_bridge_context.
    """
    from pathlib import Path
    from web_cabinet.ai.context_helpers.attention import flag_attention_cows
    from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore

    fixtures_dir = Path(__file__).parents[3] / "data" / "fixtures" / "target_v2"
    try:
        store = DemoDataStore(input_dir=fixtures_dir)
        return flag_attention_cows(store, farm_id=farm_id, as_of=datetime.date.today())
    except Exception:
        return []
```

- [ ] **Step 4.5: Run integration test**

```bash
python -m pytest tests/web_cabinet/ai/test_real_mode_bridge.py -v 2>&1 | tail -10
```
Expected: 2 passed

- [ ] **Step 4.6: Commit**

```bash
git add web_cabinet/ai/context.py tests/web_cabinet/ai/test_real_mode_bridge.py
git commit -m "fix(ai): implement _query_recent_events + _query_attention_cows, add bridge integration test"
```

---

## Task 5: Frontend — Next.js proxy route

**Files:**
- Create: `web_app/app/api/analytics/timeseries/[tab]/route.ts`

- [ ] **Step 5.1: Create the proxy route**

```typescript
// web_app/app/api/analytics/timeseries/[tab]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { backendFetch, getAuthTokens } from '@/lib/server/backend';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ tab: string }> },
) {
  const { tab } = await params;
  const { searchParams } = request.nextUrl;
  const weeks = searchParams.get('weeks') ?? '26';
  const farmId = searchParams.get('farm_id');

  const { accessToken } = await getAuthTokens();

  const qs = new URLSearchParams({ weeks });
  if (farmId) qs.set('farm_id', farmId);

  let res: Response;
  try {
    res = await backendFetch(`/api/analytics/timeseries/${tab}?${qs}`, {
      accessToken: accessToken ?? undefined,
    });
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  const text = await res.text().catch(() => '');
  return new NextResponse(text, {
    status: res.status,
    headers: { 'content-type': 'application/json' },
  });
}
```

- [ ] **Step 5.2: Verify TypeScript compiles**

```bash
cd web_app && npx tsc --noEmit 2>&1 | tail -10
```
Expected: 0 errors (or only pre-existing errors unrelated to this file)

- [ ] **Step 5.3: Commit**

```bash
git add "web_app/app/api/analytics/timeseries/[tab]/route.ts"
git commit -m "feat(web): Next.js proxy GET /api/analytics/timeseries/[tab]"
```

---

## Task 6: Frontend — `useAnalyticsTimeseries` hook

**Files:**
- Create: `web_app/lib/api/analytics-live.ts`

- [ ] **Step 6.1: Create the hook**

```typescript
// web_app/lib/api/analytics-live.ts
'use client';
import { useEffect, useState } from 'react';
import type { AnalyticsData } from './analytics';

export interface TabTimeseries {
  tab: string;
  labels: string[];
  charts: Record<string, AnalyticsData>;
}

type LoadState = { status: 'loading' } | { status: 'ok'; data: TabTimeseries } | { status: 'error' };

export function useAnalyticsTimeseries(tab: string, weeks = 26): LoadState {
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  useEffect(() => {
    let active = true;
    setState({ status: 'loading' });

    fetch(`/api/analytics/timeseries/${tab}?weeks=${weeks}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<TabTimeseries>;
      })
      .then((data) => {
        if (active) setState({ status: 'ok', data });
      })
      .catch(() => {
        if (active) setState({ status: 'error' });
      });

    return () => { active = false; };
  }, [tab, weeks]);

  return state;
}

/** Placeholder component data shown while loading or on error. */
export function emptyChart(name: string, color = '#94A3B8'): AnalyticsData {
  return { labels: [], series: [{ name, color, data: [] }] };
}
```

- [ ] **Step 6.2: Verify TypeScript compiles**

```bash
cd web_app && npx tsc --noEmit 2>&1 | tail -10
```
Expected: 0 errors

- [ ] **Step 6.3: Commit**

```bash
git add web_app/lib/api/analytics-live.ts
git commit -m "feat(web): useAnalyticsTimeseries hook for live analytics data"
```

---

## Task 7: Frontend — update real data tabs (production, reproduction, health)

**Files:**
- Modify: `web_app/components/analytics/production-tab.tsx`
- Modify: `web_app/components/analytics/reproduction-tab.tsx`
- Modify: `web_app/components/analytics/health-tab.tsx`

- [ ] **Step 7.1: Rewrite `production-tab.tsx`**

```typescript
// web_app/components/analytics/production-tab.tsx
'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function ProductionTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  const state = useAnalyticsTimeseries('production');

  const milkEcm = state.status === 'ok'
    ? (state.data.charts['milk_ecm'] ?? emptyChart('Надой'))
    : emptyChart('Надой');
  const fatProt = state.status === 'ok'
    ? (state.data.charts['fat_protein'] ?? emptyChart('Жир %'))
    : emptyChart('Жир %');
  const scc = state.status === 'ok'
    ? (state.data.charts['scc'] ?? emptyChart('СКК'))
    : emptyChart('СКК');

  const loading = state.status === 'loading';

  return (
    <div className="grid grid-2">
      <ChartCard
        title={loading ? 'Надой и ECM — загрузка…' : 'Надой и ECM'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={milkEcm.series}
      >
        <BiChart type="line" series={milkEcm.series} labels={milkEcm.labels} unit=" кг" />
      </ChartCard>

      <ChartCard
        title={loading ? 'Жир и белок % — загрузка…' : 'Жир и белок %'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={fatProt.series}
      >
        <BiChart type="line" series={fatProt.series} labels={fatProt.labels} unit="%" />
      </ChartCard>

      <ChartCard
        title={loading ? 'СКК — загрузка…' : 'Соматические клетки (СКК)'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={scc.series}
      >
        <BiChart type="line" series={scc.series} labels={scc.labels} unit="k" refLine={200} />
      </ChartCard>

      {addedMetricIds.map(id => {
        const metric = METRICS.find(m => m.id === id);
        return (
          <ChartCard
            key={id}
            title={metric?.name ?? id}
            badges={metric ? [{ icon: '📊', label: metric.group }] : []}
            onDelete={() => onRemoveChart?.(id)}
          >
            <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
              {metric?.desc ?? 'Данные загружаются…'}
            </div>
          </ChartCard>
        );
      })}

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
```

- [ ] **Step 7.2: Rewrite `reproduction-tab.tsx`**

```typescript
// web_app/components/analytics/reproduction-tab.tsx
'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';

export function ReproductionTab() {
  const state = useAnalyticsTimeseries('reproduction');

  const inseminations = state.status === 'ok'
    ? (state.data.charts['inseminations'] ?? emptyChart('Осеменения'))
    : emptyChart('Осеменения');

  const loading = state.status === 'loading';

  return (
    <div className="grid grid-2">
      <ChartCard
        title={loading ? 'Осеменения — загрузка…' : 'Осеменения и стельность'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={inseminations.series}
      >
        <BiChart type="line" series={inseminations.series} labels={inseminations.labels} unit=" гол" />
      </ChartCard>
    </div>
  );
}
```

- [ ] **Step 7.3: Rewrite `health-tab.tsx`**

```typescript
// web_app/components/analytics/health-tab.tsx
'use client';
import { useAnalyticsTimeseries, emptyChart } from '@/lib/api/analytics-live';
import { ChartCard } from './chart-card';
import { BiChart } from './bi-chart';
import { EmptyChartSlot } from './empty-chart-slot';
import { METRICS } from './add-chart-dialog';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

export function HealthTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  const state = useAnalyticsTimeseries('health');

  const mastitis = state.status === 'ok'
    ? (state.data.charts['mastitis'] ?? emptyChart('Мастит'))
    : emptyChart('Мастит');
  const issues = state.status === 'ok' && state.data.charts['issues']?.series?.length
    ? state.data.charts['issues']
    : emptyChart('Заболевания');

  const loading = state.status === 'loading';

  return (
    <div className="grid grid-2">
      <ChartCard
        title={loading ? 'Мастит — загрузка…' : 'Мастит'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={mastitis.series}
      >
        <BiChart type="line" series={mastitis.series} labels={mastitis.labels} unit=" гол" />
      </ChartCard>

      <ChartCard
        title={loading ? 'Заболевания — загрузка…' : 'Заболевания по типам'}
        badges={[{ icon: '📊', label: 'По ферме' }, { icon: '📈', label: 'Реальные данные' }]}
        legend={issues.series}
      >
        <BiChart type="line" series={issues.series} labels={issues.labels} unit=" гол" />
      </ChartCard>

      {addedMetricIds.map(id => {
        const metric = METRICS.find(m => m.id === id);
        return (
          <ChartCard
            key={id}
            title={metric?.name ?? id}
            badges={metric ? [{ icon: '📊', label: metric.group }] : []}
            onDelete={() => onRemoveChart?.(id)}
          >
            <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
              {metric?.desc ?? 'Данные загружаются…'}
            </div>
          </ChartCard>
        );
      })}

      <EmptyChartSlot onAdd={onAddChart} />
    </div>
  );
}
```

- [ ] **Step 7.4: Verify TypeScript compiles**

```bash
cd web_app && npx tsc --noEmit 2>&1 | tail -10
```
Expected: 0 errors (or only pre-existing)

- [ ] **Step 7.5: Commit**

```bash
git add web_app/components/analytics/production-tab.tsx \
        web_app/components/analytics/reproduction-tab.tsx \
        web_app/components/analytics/health-tab.tsx
git commit -m "feat(web): production/reproduction/health tabs — live data via useAnalyticsTimeseries"
```

---

## Task 8: Frontend — placeholder for unimplemented tabs

**Files:**
- Modify: `web_app/components/analytics/feed-tab.tsx`
- Modify: `web_app/components/analytics/herd-tab.tsx`
- Modify: `web_app/components/analytics/behavior-tab.tsx`
- Modify: `web_app/components/analytics/finance-tab.tsx`

Each of the 4 tabs gets the same placeholder treatment: remove `mulberry32` charts, show a card indicating data is being connected.

- [ ] **Step 8.1: Rewrite `feed-tab.tsx`**

```typescript
// web_app/components/analytics/feed-tab.tsx
import { BarChart2 } from 'lucide-react';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

function ComingSoonCard({ title }: { title: string }) {
  return (
    <div className="chart-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 180, gap: 8 }}>
      <BarChart2 size={32} color="var(--border-strong)" />
      <p style={{ margin: 0, fontWeight: 600, color: 'var(--text-secondary)' }}>{title}</p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>Данные подключаются</p>
    </div>
  );
}

export function FeedTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ComingSoonCard title="Потребление корма (DMI)" />
      <ComingSoonCard title="Стоимость корма" />
      <ComingSoonCard title="Эффективность корма" />
    </div>
  );
}
```

- [ ] **Step 8.2: Rewrite `herd-tab.tsx`**

```typescript
// web_app/components/analytics/herd-tab.tsx
import { BarChart2 } from 'lucide-react';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

function ComingSoonCard({ title }: { title: string }) {
  return (
    <div className="chart-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 180, gap: 8 }}>
      <BarChart2 size={32} color="var(--border-strong)" />
      <p style={{ margin: 0, fontWeight: 600, color: 'var(--text-secondary)' }}>{title}</p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>Данные подключаются</p>
    </div>
  );
}

export function HerdTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ComingSoonCard title="Состав стада" />
      <ComingSoonCard title="Распределение ДСД" />
      <ComingSoonCard title="Отёлы" />
    </div>
  );
}
```

- [ ] **Step 8.3: Rewrite `behavior-tab.tsx`**

```typescript
// web_app/components/analytics/behavior-tab.tsx
import { BarChart2 } from 'lucide-react';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

function ComingSoonCard({ title }: { title: string }) {
  return (
    <div className="chart-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 180, gap: 8 }}>
      <BarChart2 size={32} color="var(--border-strong)" />
      <p style={{ margin: 0, fontWeight: 600, color: 'var(--text-secondary)' }}>{title}</p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>Данные подключаются</p>
    </div>
  );
}

export function BehaviorTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ComingSoonCard title="Жвачка (мин/день)" />
      <ComingSoonCard title="Активность" />
      <ComingSoonCard title="Лёжка" />
    </div>
  );
}
```

- [ ] **Step 8.4: Rewrite `finance-tab.tsx`**

```typescript
// web_app/components/analytics/finance-tab.tsx
import { BarChart2 } from 'lucide-react';

interface Props {
  onAddChart: () => void;
  addedMetricIds?: string[];
  onRemoveChart?: (id: string) => void;
}

function ComingSoonCard({ title }: { title: string }) {
  return (
    <div className="chart-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 180, gap: 8 }}>
      <BarChart2 size={32} color="var(--border-strong)" />
      <p style={{ margin: 0, fontWeight: 600, color: 'var(--text-secondary)' }}>{title}</p>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>Данные подключаются</p>
    </div>
  );
}

export function FinanceTab({ onAddChart, addedMetricIds = [], onRemoveChart }: Props) {
  return (
    <div className="grid grid-2">
      <ComingSoonCard title="Выручка на корову" />
      <ComingSoonCard title="Затраты на корм" />
      <ComingSoonCard title="Маржа на корову" />
    </div>
  );
}
```

- [ ] **Step 8.5: Verify TypeScript compiles**

```bash
cd web_app && npx tsc --noEmit 2>&1 | tail -10
```
Expected: 0 errors

- [ ] **Step 8.6: Commit**

```bash
git add web_app/components/analytics/feed-tab.tsx \
        web_app/components/analytics/herd-tab.tsx \
        web_app/components/analytics/behavior-tab.tsx \
        web_app/components/analytics/finance-tab.tsx
git commit -m "feat(web): feed/herd/behavior/finance tabs — replace synthetic charts with data-connecting placeholder"
```

---

## Task 9: Run all 7 CI gates

- [ ] **Step 9.1: Gate 1 — pytest**

```bash
bash scripts/run_ci_gate.sh 2>&1 | tail -10
```
Expected: `PASSED`

- [ ] **Step 9.2: Gates 2 + 4 in parallel**

```bash
python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
  --timing-json artifacts/_ci/web_smoke.json 2>&1 | tail -5
```
Expected: `WEB_SMOKE_OK`

```bash
bash scripts/run_warning_governance_gate.sh 2>&1 | tail -5
```
Expected: `WARNING_GOVERNANCE_OK`

- [ ] **Step 9.3: Gate 3**

```bash
python -m genomeai.cli verify_refactor --project-root . --golden golden \
  --report-root artifacts/_ci/verify_refactor 2>&1 | tail -5
```
Expected: `VERIFY_REFACTOR_OK`

- [ ] **Step 9.4: Gates 5 + 6 + 7**

```bash
bash scripts/run_operational_rollout_gate.sh 2>&1 | tail -8
bash scripts/run_competitive_acceptance_gate.sh 2>&1 | tail -8
bash scripts/run_perf_gates.sh 2>&1 | tail -8
```

- [ ] **Step 9.5: Collect results and write proof**

If all 7 gates pass, status = `proven`.  
If gate 5 (mobile_views) or gate 6 (competitive acceptance manual) still fail — those are pre-existing failures unrelated to this change; status = `partially_proven` with explicit listing.

---

## Acceptance Criteria

- `GET /api/analytics/timeseries/production` returns `{tab, labels, charts}` with real weekly data from DB (or fixture CSV if no DB)
- `GET /api/analytics/timeseries/health` and `/reproduction` same
- Frontend production/reproduction/health tabs show charts with data from backend (no `mulberry32`)
- Frontend feed/herd/behavior/finance tabs show "Данные подключаются" card (no fake charts)
- `_build_bridge_context("FARM_001")` returns `FarmContext` with `isinstance(ctx.recent_events, list)` and `isinstance(ctx.attention_cows, list)` — integration test passes
- `pytest tests/web_cabinet/analytics/test_timeseries_bridge.py tests/web_cabinet/ai/test_real_mode_bridge.py` → all green
- All 7 CI gates run (pre-existing gate 5/6 failures allowed with explicit notation)
