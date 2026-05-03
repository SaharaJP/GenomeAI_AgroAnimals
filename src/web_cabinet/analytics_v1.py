from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from packages.contracts.analytics_v1 import (
    HealthIssueBreakdown,
    HealthResponse,
    ProductionDayPoint,
    ProductionResponse,
    ProductionSummary,
    ReproLactationDaysOpen,
    ReproductionResponse,
)

from .auth import get_current_user, get_db
from .rbac import require_permissions

router = APIRouter(prefix='/api/analytics', tags=['analytics-v1'])

_DEFAULT_LOOKBACK_DAYS = 180


def _default_start() -> str:
    return (datetime.utcnow().date() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)).isoformat()


def _default_end() -> str:
    return datetime.utcnow().date().isoformat()


def _safe_round(val: Optional[float], digits: int = 4) -> Optional[float]:
    if val is None:
        return None
    return round(val, digits)


def _ecm(milk_kg: float, fat_pct: Optional[float], protein_pct: Optional[float]) -> Optional[float]:
    """Energy-Corrected Milk (Sjaunja 1990): ECM = milk × (0.25 + 12.2×fat_fraction + 7.7×protein_fraction)."""
    if fat_pct is None or protein_pct is None:
        return None
    return milk_kg * (0.25 + 12.2 * fat_pct / 100.0 + 7.7 * protein_pct / 100.0)


def _days_between(start_iso: str, end_iso: str) -> Optional[float]:
    try:
        d1 = date.fromisoformat(str(start_iso))
        d2 = date.fromisoformat(str(end_iso))
        return float((d2 - d1).days)
    except Exception:
        return None


@router.get('/production', response_model=ProductionResponse)
def analytics_production(
    start_date: Optional[str] = Query(default=None, description='ISO date, e.g. 2025-01-01'),
    end_date: Optional[str] = Query(default=None, description='ISO date, e.g. 2025-04-30'),
    farm_id: Optional[str] = Query(default=None),
    group_id: Optional[str] = Query(default=None),
    user=Depends(require_permissions('kpi.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    start = start_date or _default_start()
    end = end_date or _default_end()

    sql = """
        SELECT
            m.date,
            AVG(m.milk_kg) AS avg_milk_kg,
            AVG(m.fat_pct) AS avg_fat_pct,
            AVG(m.protein_pct) AS avg_protein_pct,
            AVG(m.scc_cells_ml) AS avg_scc_cells_ml,
            COUNT(*) AS n_records
        FROM dm_milkings_daily m
        JOIN dm_animals a ON m.tenant_id = a.tenant_id AND m.animal_id = a.animal_id
        WHERE m.tenant_id = ?
          AND m.date >= ?
          AND m.date <= ?
    """
    params: list = [tenant_id, start, end]

    if farm_id:
        sql += ' AND a.farm_id = ?'
        params.append(farm_id)

    sql += ' GROUP BY m.date ORDER BY m.date'

    try:
        rows = list(conn.execute(sql, params).fetchall())
    except Exception:
        rows = []

    time_series: list[ProductionDayPoint] = []
    for row in rows:
        avg_milk = _safe_round(row['avg_milk_kg'], 2)
        avg_fat = _safe_round(row['avg_fat_pct'], 3)
        avg_protein = _safe_round(row['avg_protein_pct'], 3)
        avg_scc = _safe_round(row['avg_scc_cells_ml'], 0)
        ecm = _safe_round(_ecm(avg_milk or 0.0, row['avg_fat_pct'], row['avg_protein_pct']), 2)
        time_series.append(
            ProductionDayPoint(
                date=str(row['date']),
                avg_milk_kg=avg_milk or 0.0,
                ecm_kg=ecm,
                avg_fat_pct=avg_fat,
                avg_protein_pct=avg_protein,
                avg_scc_cells_ml=avg_scc,
                n_records=int(row['n_records']),
            )
        )

    total = sum(p.n_records for p in time_series)
    if time_series:
        agg_milk = _safe_round(sum(p.avg_milk_kg * p.n_records for p in time_series) / total, 2) if total else None
        agg_fat_vals = [p.avg_fat_pct for p in time_series if p.avg_fat_pct is not None]
        agg_protein_vals = [p.avg_protein_pct for p in time_series if p.avg_protein_pct is not None]
        agg_scc_vals = [p.avg_scc_cells_ml for p in time_series if p.avg_scc_cells_ml is not None]
        agg_fat = _safe_round(sum(agg_fat_vals) / len(agg_fat_vals), 3) if agg_fat_vals else None
        agg_protein = _safe_round(sum(agg_protein_vals) / len(agg_protein_vals), 3) if agg_protein_vals else None
        agg_scc = _safe_round(sum(agg_scc_vals) / len(agg_scc_vals), 0) if agg_scc_vals else None
        agg_ecm = _safe_round(_ecm(agg_milk or 0.0, agg_fat, agg_protein), 2) if agg_milk is not None else None
    else:
        agg_milk = agg_fat = agg_protein = agg_scc = agg_ecm = None

    return ProductionResponse(
        start_date=start,
        end_date=end,
        time_series=time_series,
        summary=ProductionSummary(
            avg_milk_kg=agg_milk,
            avg_ecm_kg=agg_ecm,
            avg_fat_pct=agg_fat,
            avg_protein_pct=agg_protein,
            avg_scc_cells_ml=agg_scc,
            total_records=total,
        ),
    )


@router.get('/reproduction', response_model=ReproductionResponse)
def analytics_reproduction(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    farm_id: Optional[str] = Query(default=None),
    group_id: Optional[str] = Query(default=None),
    user=Depends(require_permissions('kpi.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    start = start_date or _default_start()
    end = end_date or _default_end()

    sql = """
        SELECT re.event_type, re.result, re.event_date, re.animal_id
        FROM dm_repro_events re
        JOIN dm_animals a ON re.tenant_id = a.tenant_id AND re.animal_id = a.animal_id
        WHERE re.tenant_id = ?
          AND re.event_date >= ?
          AND re.event_date <= ?
    """
    params: list = [tenant_id, start, end]
    if farm_id:
        sql += ' AND a.farm_id = ?'
        params.append(farm_id)
    sql += ' ORDER BY re.event_date'

    try:
        rows = list(conn.execute(sql, params).fetchall())
    except Exception:
        rows = []

    inseminations = sum(1 for r in rows if r['event_type'] == 'insemination')
    preg_checks = sum(1 for r in rows if r['event_type'] == 'preg_check')
    events_total = len(rows)

    conception_rate: Optional[float] = None
    if inseminations > 0 and preg_checks > 0:
        conception_rate = round(min(preg_checks, inseminations) / inseminations, 4)

    # days_open: join insemination events with lactations to compute DIM at first AI
    days_open_sql = """
        SELECT l.lactation_no, l.calving_date, re.event_date AS insem_date
        FROM dm_repro_events re
        JOIN dm_animals a ON re.tenant_id = a.tenant_id AND re.animal_id = a.animal_id
        JOIN dm_lactations l ON re.tenant_id = l.tenant_id AND re.animal_id = l.animal_id
        WHERE re.tenant_id = ?
          AND re.event_type = 'insemination'
          AND re.event_date >= ?
          AND re.event_date <= ?
    """
    days_params: list = [tenant_id, start, end]
    if farm_id:
        days_open_sql += ' AND a.farm_id = ?'
        days_params.append(farm_id)
    days_open_sql += ' ORDER BY re.animal_id, re.event_date'

    try:
        days_rows = list(conn.execute(days_open_sql, days_params).fetchall())
    except Exception:
        days_rows = []

    # Group by lactation_no and compute avg days_open
    by_lac: dict[Optional[int], list[float]] = {}
    for row in days_rows:
        d = _days_between(str(row['calving_date']), str(row['insem_date']))
        if d is not None and d >= 0:
            lac_no = row['lactation_no']
            by_lac.setdefault(lac_no, []).append(d)

    days_open_by_lactation = [
        ReproLactationDaysOpen(
            lactation_no=lac_no,
            avg_days_open=round(sum(vals) / len(vals), 1),
            n_animals=len(vals),
        )
        for lac_no, vals in sorted(by_lac.items(), key=lambda x: (x[0] is None, x[0]))
    ]

    return ReproductionResponse(
        start_date=start,
        end_date=end,
        conception_rate=conception_rate,
        pregnancy_rate=None,
        days_open_by_lactation=days_open_by_lactation,
        vwp_days=50,
        inseminations=inseminations,
        preg_checks=preg_checks,
        events_total=events_total,
    )


@router.get('/health', response_model=HealthResponse)
def analytics_health(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    farm_id: Optional[str] = Query(default=None),
    group_id: Optional[str] = Query(default=None),
    user=Depends(require_permissions('kpi.view')),
    conn=Depends(get_db),
):
    tenant_id = user.get('tenant_id', 'default')
    start = start_date or _default_start()
    end = end_date or _default_end()

    sql = """
        SELECT he.event_type, COUNT(*) AS cnt
        FROM dm_health_events he
        JOIN dm_animals a ON he.tenant_id = a.tenant_id AND he.animal_id = a.animal_id
        WHERE he.tenant_id = ?
          AND he.event_date >= ?
          AND he.event_date <= ?
    """
    params: list = [tenant_id, start, end]
    if farm_id:
        sql += ' AND a.farm_id = ?'
        params.append(farm_id)
    sql += ' GROUP BY he.event_type ORDER BY cnt DESC'

    try:
        rows = list(conn.execute(sql, params).fetchall())
    except Exception:
        rows = []

    events_total = sum(int(r['cnt']) for r in rows)
    mastitis_count = sum(int(r['cnt']) for r in rows if r['event_type'] == 'mastitis')

    breakdown = [
        HealthIssueBreakdown(
            event_type=str(r['event_type']),
            count=int(r['cnt']),
            pct=round(int(r['cnt']) / events_total * 100, 1) if events_total else 0.0,
        )
        for r in rows
    ]

    return HealthResponse(
        start_date=start,
        end_date=end,
        mastitis_count=mastitis_count,
        health_issues_breakdown=breakdown,
        events_total=events_total,
    )
