"""Weekly time-series aggregation for analytics dashboard tabs.

Queries DB via conn (psycopg/SQLite compat, uses ? placeholders).
Returns dict shaped for the frontend AnalyticsData contract.
"""
from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from typing import Any

_log = logging.getLogger(__name__)


_MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
               "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]


def _week_label(d: datetime.date) -> str:
    monday = d - datetime.timedelta(days=d.weekday())
    return f"{monday.day:02d} {_MONTHS_RU[monday.month - 1]}"


def _iso_week_key(d: datetime.date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _safe(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f
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
        _log.exception("timeseries_bridge: DB query failed for farm=%s tab=production", farm_id)
        rows = []

    if not rows:
        return _empty_production()

    by_week: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        d = row["date"]
        if isinstance(d, str):
            d = datetime.date.fromisoformat(d)
        wk = _iso_week_key(d)
        by_week[wk]["dates"].append(d)
        by_week[wk]["milk"].append(_safe(row["avg_milk"]))
        by_week[wk]["fat"].append(_safe(row["avg_fat"]))
        by_week[wk]["protein"].append(_safe(row["avg_protein"]))
        by_week[wk]["scc"].append(_safe(row["avg_scc"]))

    sorted_weeks = sorted(by_week.keys())
    labels = []
    milk_data, ecm_data, fat_data, protein_data, scc_data = [], [], [], [], []

    for wk in sorted_weeks:
        d = min(by_week[wk]["dates"])
        labels.append(_week_label(d))

        milks = [v for v in by_week[wk]["milk"] if v is not None]
        fats = [v for v in by_week[wk]["fat"] if v is not None]
        proteins = [v for v in by_week[wk]["protein"] if v is not None]
        sccs = [v for v in by_week[wk]["scc"] if v is not None]

        avg_milk = round(sum(milks) / len(milks), 1) if milks else 0.0
        avg_fat = round(sum(fats) / len(fats), 2) if fats else None
        avg_protein = round(sum(proteins) / len(proteins), 2) if proteins else None
        avg_scc = round(sum(sccs) / len(sccs) / 1000, 1) if sccs else None
        ecm = _ecm(avg_milk, avg_fat, avg_protein)

        milk_data.append(avg_milk)
        # ECM falls back to milk yield when fat/protein unavailable — avoids chart gap
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
        _log.exception("timeseries_bridge: DB query failed for farm=%s tab=health", farm_id)
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
    labels = [_week_label(min(by_week[wk]["dates"])) for wk in sorted_weeks]

    mastitis_data = [len(by_week[wk].get("mastitis", [])) for wk in sorted_weeks]

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
        _log.exception("timeseries_bridge: DB query failed for farm=%s tab=reproduction", farm_id)
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
    labels = [_week_label(min(by_week[wk]["dates"])) for wk in sorted_weeks]
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
